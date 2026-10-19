# Logos Match v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Logos Match v0.2 — versioned spreadsheets, live progress and detailed history of each collection in the panel, and the "one posto per machine" lock through a shared network folder.

**Architecture:** Changes stay inside `WebPosto_API/apps/match/`. The DB gains `execucao`/`execucao_item` (migration 3) and `instalacao.pasta_rede` (migration 4). Collection reports progress through a callback. A new module `registro_rede.py` owns the shared-folder lock; the panel, the import path, the collection and the CLI call it.

**Tech Stack:** as v0.1 (Python, FastAPI + Jinja2, SQLite, openpyxl, PyInstaller, Inno Setup).

**Spec:** `docs/superpowers/specs/2026-10-18-logos-match-design.md` — §13 (approved 19/10/2026), plus everything binding in §1–§12.

## Global Constraints

- Run tests from `WebPosto_API`: `.venv/Scripts/python -m pytest -o addopts="" -p no:warnings tests/unit/match tests/unit/cash_reconciliation tests/unit/test_segredos.py -q`. Baseline today: 794 passed. All must stay green.
- Fuso America/Recife; display `dd/mm/aaaa HH:mm`; ISO UTC in storage.
- Exceptions are logged only as `type(exc).__name__`; user-facing text never uses `str(exc)` (use `explicar.erro_pt` / `canais.erro_envio_pt`).
- No secrets in the shared folder, logs, HTML, xlsx or exports.
- Panel: the session stores only `usuario_id`; every route authorizes with `acesso.pode_agora` / `postos_visiveis_agora`; every POST needs CSRF; CSP keeps `script-src 'none'` (no JavaScript).
- Commit messages in Portuguese ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Shared folder unreachable** (OneDrive paused, network drive offline). Expected: registering, importing or reactivating a posto is refused with "A pasta da rede não está acessível agora. Tente de novo quando ela estiver disponível." Collection still runs and the result message gets the line "Não foi possível conferir a pasta da rede." (test in Task 4).
2. **Same PC reinstalled** (new `id_instalacao`). Expected: its old postos show as "pertence a outra máquina" with the same machine name, and "Assumir posto" fixes it (test in Task 5).
3. **Two clicks on "Coletar agora"**: the second lands on the in-progress page, which shows the running execution, never a false "nada coletado" (test in Task 3).
4. **Spreadsheet open in Excel while a new version is written.** Versions never overwrite, so writing `_vN+1` works. Downloading the open file still works, because it is only read (test in Task 1).
5. **OneDrive conflict copy** `74014-PCNOME.json` next to `74014.json`. Expected: the oldest `registrado_em` among all copies wins (test in Task 4).

---

### Task 1: Versioned spreadsheet

**Files:**
- Modify: `apps/match/relatorio_xlsx.py`, `apps/match/rotina.py` (`limpar_antigos`), `apps/match/painel/rotas.py` (`/planilha`)
- Test: `tests/unit/match/test_relatorio_xlsx.py`, `tests/unit/match/test_rotina.py`, `tests/unit/match/test_painel.py`

**Interfaces:**
- Produces:
  - `relatorio_xlsx.versoes(posto_id: int, dia: date, apelido: str | None) -> list[Path]`: oldest to newest. The base name is version 1; then `_v2`, `_v3`…
  - `relatorio_xlsx.mais_recente(con, posto_id: int, dia: date) -> Path | None`
  - `relatorio_xlsx.gerar(con, posto_id, dia, destino=None) -> Path`: same signature. With `destino=None`:
    - if no version exists, write the base name;
    - if the newest version holds the same data, return it unchanged;
    - otherwise write the next `_vN`.
- "Same data" = SHA-256 of the cell values of every sheet in order (`ws.iter_rows(values_only=True)`), not of the file bytes, because xlsx bytes differ on every save.

- [ ] **Step 1: Failing tests.**
  - `test_primeira_versao_sem_sufixo`
  - `test_dados_iguais_reaproveita_ultima`: call `gerar` twice with no change → same path, only 1 file.
  - `test_dados_mudaram_cria_v2_e_v3`: change one divergência between calls → `..._17-10-2026_v2.xlsx`, then `_v3`; v1 unchanged on disk.
  - `test_versao_aberta_no_excel_nao_impede_nova`: open v1 with `open(p, "rb")` held during the next `gerar` → v2 is created.
  - `test_limpar_antigos_apaga_versoes`: `Logos_X_17-09-2025_v2.xlsx` is deleted under the 13-month rule.
  - `test_baixar_planilha_usa_mais_recente`: the `/planilha` response body equals the bytes of the newest version.
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3: Implement.** Parse the version with the regex `^(Logos_.+_\d{2}-\d{2}-\d{4})(?:_v(\d+))?\.xlsx$`. `limpar_antigos` uses the same regex to read the date. `/planilha` uses `mais_recente`, and generates only when it returns `None`.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `feat(match): planilha com versões e reaproveitamento quando os dados não mudam`.

### Task 2: Execution record and progress

**Files:**
- Modify: `apps/match/banco.py` (migration 3), `apps/match/coletas.py`, `apps/match/rotina.py`, `apps/match/canais/envio.py`, `apps/match/agendador.py`, `apps/match/__main__.py`, `apps/match/painel/rotas.py` (only the `executar` call sites)
- Test: `tests/unit/match/test_banco.py`, `test_rotina.py`, `test_coletas.py`

**Interfaces:**
- Migration 3:
  - `CREATE TABLE execucao(id INTEGER PRIMARY KEY AUTOINCREMENT, iniciada_em TEXT NOT NULL, terminada_em TEXT, origem TEXT NOT NULL CHECK (origem IN ('agendada','repescagem','recuperacao','painel','bandeja')), usuario_id INTEGER REFERENCES usuario(id), dia TEXT NOT NULL, situacao TEXT NOT NULL CHECK (situacao IN ('em_andamento','concluida','falhou')))`
  - `CREATE TABLE execucao_item(id INTEGER PRIMARY KEY AUTOINCREMENT, execucao_id INTEGER NOT NULL REFERENCES execucao(id), posto_id INTEGER NOT NULL, fonte TEXT NOT NULL, situacao TEXT NOT NULL CHECK (situacao IN ('aguardando','coletando','ok','sem_movimento','sem_comparacao','erro','verificacao_humana')), mensagem TEXT, iniciada_em TEXT, terminada_em TEXT, UNIQUE(execucao_id, posto_id, fonte))`
  - `ALTER TABLE envio ADD COLUMN execucao_id INTEGER`
- On startup, executions left `em_andamento` from a crash are marked `falhou` with `terminada_em = now`. Do this in `rotina` when the scheduler/app starts: `rotina.fechar_orfas(con) -> int`.
- `banco` helpers:
  - `abrir_execucao(con, origem, usuario_id, dia) -> int`
  - `item_execucao(con, execucao_id, posto_id, fonte, situacao, mensagem=None) -> None` (upsert; sets `iniciada_em` when it moves to `coletando` and `terminada_em` on any final state)
  - `fechar_execucao(con, execucao_id, situacao) -> None`
  - `execucao_atual(con) -> Row | None` (the newest `em_andamento`)
  - `itens_execucao(con, execucao_id) -> list[Row]`
  - `ultimas_execucoes(con, limite=30) -> list[Row]`
  - `envios_da_execucao(con, execucao_id) -> list[Row]`
- `coletas.coletar_todos(..., ao_progresso: Callable[[int, str, str, str | None], None] | None = None)` and `coletar_posto(..., ao_progresso=None)`. Call it with `(posto_id, fonte, "coletando", None)` before each source and with `(posto_id, fonte, resultado.situacao, resultado.mensagem)` after.
- `rotina.executar(con, *, dia=None, so_falhas=False, visivel=False, posto_id=None, origem: str = "painel", usuario_id: int | None = None)`:
  - opens the execution (only after taking the lock);
  - writes every active posto × fonte as `aguardando`;
  - passes `ao_progresso`;
  - closes it `concluida` (`falhou` on an exception, which is re-raised).
  - Callers pass origin: agendador `agendada` / `repescagem` / `recuperacao`; tray `bandeja`; panel `painel` with `usuario_id`.
- `envio.enviar_dia(con, resultados, dia, execucao_id: int | None = None)` fills `envio.execucao_id`.

- [ ] **Step 1: Failing tests.**
  - `test_migracao_3_de_banco_v2` (a v2 DB upgrades and keeps its data)
  - `test_execucao_registra_itens_e_fecha`
  - `test_execucao_falha_fica_falhou`
  - `test_fechar_orfas`
  - `test_ao_progresso_chamado_coletando_e_final`
  - `test_origem_agendada_e_repescagem` (agendador passes the origin)
  - `test_envio_grava_execucao_id`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `feat(match): registro de execuções e progresso por posto/fonte`.

### Task 3: Panel — collection in progress and detailed history

**Files:**
- Modify: `apps/match/painel/rotas.py`, `apps/match/painel/templates/` (new `andamento.html`; `historico.html` reworked; links in `base.html`/`hoje.html`)
- Test: `tests/unit/match/test_painel.py`

**Interfaces:**
- `GET /coleta`:
  - Permission: `Acao.VER`.
  - Content: the current execution, or the latest one with a "Concluída às dd/mm/aaaa HH:mm" banner. Table of posto × fonte limited to `postos_visiveis_agora` (label, state in Portuguese, message, elapsed time). Header: origin, who triggered it, start time.
  - While `em_andamento`, the template emits `<meta http-equiv="refresh" content="3">`; otherwise it does not.
  - State labels: aguardando → "Aguardando", coletando → "Coletando…", ok → "OK", sem_movimento → "Sem movimento", sem_comparacao → "Sem comparação com webPosto", erro → "Erro", verificacao_humana → "Precisa de verificação humana".
- `POST /coletar` redirects (303) to `/coleta` after starting, and also when `rotina.em_andamento()` is true. The flash "Já existe uma coleta em andamento." appears on `/coleta`.
- `GET /historico`:
  - One row per execution: start, end, duration (`Xm Ys`), origin in Portuguese, user name (or "Agendada"/"Bandeja"), situation, and per posto/fonte the final state.
  - Spreadsheet versions of that day per visible posto: links to `/planilha?posto_id=&dia=&versao=N`. Add an optional `versao: int | None` to `/planilha`, served only if that version exists, else 404.
  - Sends of that execution (canal type, ok/erro, error text). Shown only to `CONFIGURAR`, keeping the earlier ruling.
  - Gerente/conferente see only executions that touched their postos, and only the lines for their postos.

- [ ] **Step 1: Failing tests.**
  - `test_andamento_tem_refresh_quando_em_andamento`
  - `test_andamento_sem_refresh_quando_concluida`
  - `test_andamento_so_postos_visiveis`
  - `test_coletar_redireciona_para_andamento`
  - `test_coletar_duplo_mostra_em_andamento` (Review Focus 3)
  - `test_historico_mostra_execucao_duracao_origem`
  - `test_historico_versoes_da_planilha`
  - `test_planilha_versao_especifica_e_404`
  - `test_historico_gerente_so_seus_postos`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `feat(match): acompanhamento da coleta ao vivo e histórico detalhado`.

### Task 4: Shared-folder registry module

**Files:**
- Create: `apps/match/registro_rede.py`
- Modify: `apps/match/banco.py` (migration 4: `ALTER TABLE instalacao ADD COLUMN pasta_rede TEXT`; helpers `pasta_rede(con) -> Path | None`, `salvar_pasta_rede(con, caminho: str | None)`)
- Test: `tests/unit/match/test_registro_rede.py`

**Interfaces:**
- `class PastaIndisponivel(Exception)`
- `@dataclass Dono(id_instalacao: str, maquina: str, usuario_windows: str, posto_nome: str, registrado_em: str)`
- `chave_posto(posto: Row) -> str | None`: `str(empresa_codigo_webposto)`, else the CNPJ digits, else `None`.
- `pasta_postos(pasta: Path) -> Path`: `pasta / "LogosMatch" / "postos"`. Created on demand.
- `dono(pasta: Path, chave: str) -> Dono | None`:
  - Reads `<chave>.json` and every conflict copy `<chave>-*.json`, and returns the one with the oldest `registrado_em`.
  - Unreadable or invalid JSON is ignored.
  - Folder missing or not accessible → `PastaIndisponivel`.
- `registrar(pasta: Path, chave: str, id_instalacao: str, posto_nome: str) -> Dono`:
  - If another installation owns the key → raise `PostoDeOutraMaquina(dono)`.
  - Otherwise write `<chave>.json` atomically (temp file + `os.replace`) with `maquina=socket.gethostname()`, `usuario_windows=getpass.getuser()` and `registrado_em` ISO UTC; keep the original `registrado_em` if it is ours.
- `class PostoDeOutraMaquina(Exception)` with attribute `dono: Dono`.
- `assumir(pasta, chave, id_instalacao, posto_nome) -> Dono`: overwrites `<chave>.json`, deletes the conflict copies, sets `registrado_em = now`.
- `liberar(pasta, chave, id_instalacao) -> bool`: deletes only if ours.
- `mensagem_bloqueio(dono: Dono) -> str` = `"Este posto já está cadastrado na máquina {maquina} desde {dd/mm/aaaa HH:mm}. Desative lá ou use 'Assumir posto'."` (Recife time).
- `MSG_INDISPONIVEL = "A pasta da rede não está acessível agora. Tente de novo quando ela estiver disponível."`

- [ ] **Step 1: Failing tests** (use `tmp_path` as the "network folder"):
  - `test_chave_por_codigo_cnpj_ou_nada`
  - `test_registrar_e_dono`
  - `test_outra_instalacao_bloqueia_com_mensagem` (exact text with the machine name and the formatted date)
  - `test_reregistrar_proprio_mantem_data`
  - `test_copia_de_conflito_mais_antiga_vence` (Review Focus 5)
  - `test_json_invalido_ignorado`
  - `test_pasta_inexistente_levanta_indisponivel`
  - `test_assumir_sobrescreve_e_remove_copias`
  - `test_liberar_so_o_proprio`
  - `test_registro_sem_segredos` (the JSON keys are exactly the five `Dono` fields)
  - `test_migracao_4`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `feat(match): registro de postos na pasta da rede`.

### Task 5: Integrate the lock (panel, import, collection, CLI, installer) and release 0.2.0

**Files:**
- Modify:
  - `apps/match/painel/rotas.py` + templates (`agenda.html` or a new "Configurações" section for the folder; `postos.html`)
  - `apps/match/unidades.py` (`importar_units_json`, `importar_config`)
  - `apps/match/coletas.py`
  - `apps/match/__main__.py` (flag `--liberar-postos`)
  - `apps/match/build/instalador.iss` (uninstall calls `--liberar-postos` before `--apagar-credenciais`, only when "apagar dados" is chosen)
  - `apps/match/__init__.py` (`VERSAO = "0.2.0"`)
  - `apps/match/README.md`
- Test: `tests/unit/match/test_painel.py`, `test_unidades.py`, `test_coletas.py`, `test_main.py`

**Interfaces / rules:**
- **Panel — Pasta da rede** (admin, `CONFIGURAR`):
  - field with the path + "Salvar" (validates that the folder exists and is writable by creating `LogosMatch/postos`) + "Desligar".
  - On save, register every active posto that has a key. Conflicts are listed with `mensagem_bloqueio`, and those postos are deactivated with that reason shown.
- **With the folder on:**
  - Creating, editing a key, or reactivating a posto: requires `chave_posto` ("Informe o código do webPosto ou o CNPJ para proteger este posto contra cadastro em duas máquinas."), then `registrar`.
  - `PostoDeOutraMaquina` → 409 with `mensagem_bloqueio`, nothing saved.
  - `PastaIndisponivel` → 503 with `MSG_INDISPONIVEL`, nothing saved.
  - Deactivating a posto calls `liberar`; errors are ignored with a type-name log line.
- **Postos list:** shows "Protegido (esta máquina)" / "Sem proteção". For a posto owned by another installation, it shows "Pertence à máquina {maquina}" and a POST button `/postos/{id}/assumir` (admin, confirmation checkbox "Confirmo que a outra máquina não coleta mais este posto", `acesso.registrar(..., "assumir_posto", f"posto={id}")`).
- **Imports:** a posto owned by another installation is skipped and reported in the import result. A folder that is unreachable fails the whole import with `MSG_INDISPONIVEL`, before any insert.
- **Collection** (`coletar_posto`), when the folder is on and the posto has a key:
  - `dono` is another installation → every source of that posto becomes `erro` with `"O posto {nome} agora é coletado pela máquina {maquina}."` and no adapter is called.
  - `PastaIndisponivel` → collect normally and append `"\nNão foi possível conferir a pasta da rede."` to each source message.
- **CLI:** `LogosMatchCLI.exe --liberar-postos` calls `liberar` for every posto of this installation and prints `"N posto(s) liberado(s) na pasta da rede."` (exit 0). Without the folder it prints `"Pasta da rede não configurada."` (exit 0). With the folder unreachable it prints `MSG_INDISPONIVEL` (exit 1).

- [ ] **Step 1: Failing tests.**
  - `test_pasta_rede_salvar_registra_ativos`
  - `test_cadastro_bloqueado_outra_maquina_409`
  - `test_cadastro_pasta_indisponivel_503` (Review Focus 1)
  - `test_cadastro_exige_codigo_ou_cnpj_com_pasta`
  - `test_assumir_posto_admin_e_log`
  - `test_reinstalado_mostra_mesma_maquina_e_assume` (Review Focus 2)
  - `test_importar_pula_posto_de_outra_maquina`
  - `test_coleta_nao_roda_posto_de_outra_maquina`
  - `test_coleta_segue_com_pasta_indisponivel` (Review Focus 1)
  - `test_cli_liberar_postos`
  - `test_desativar_libera`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement. In the README, document the network folder (a folder the machines sync, e.g. `OneDrive\LogosMatch-Rede`), "Assumir posto" and the new screens.
- [ ] **Step 4:** Run the full suite and confirm it is green. Rebuild with `powershell -File apps/match/build/build.ps1` → `dist/LogosMatch-Setup-0.2.0.exe`. Run `dist/LogosMatch/LogosMatchCLI.exe --verificar` (exit 0).
- [ ] **Step 5:** Commit `feat(match): bloqueio de posto entre máquinas pela pasta da rede; versão 0.2.0`.
