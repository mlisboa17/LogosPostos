# Logos Match — Extratos OFX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every time a new OFX statement lands in the extratos folder, Logos Match does the work itself:
- recognises the bank account and files the statement under the right posto;
- imports into the webPosto bank account only the days webPosto does not have yet, after approval in the panel or on Telegram;
- lists the financial entries that are missing in webPosto (camada 2, list-only for now);
- tracks trust per entry type, so it can later run on its own.

**Architecture:** New package `apps/match/extratos/`, plus migration 6 in `banco.py`.

It reuses three pieces of `src/modules/cash_reconciliation`:
- `adapters/extrato_reader.ler_ofx` to parse statements;
- `adapters/webposto_escrita_ofx.enviar_ofx_webposto` for the authorized OFX import, given two new injection points so the app needs no `.env`;
- `application/despesas_sem_lancamento.identificar_despesas_sem_lancamento` for camada 2.

Approvals are shared by both layers and can come from the panel or from Telegram inline buttons. Telegram buttons work through a polling thread inside the app.

**Tech Stack:** as v0.3 (Python, FastAPI + Jinja2 without JS, SQLite, APScheduler, httpx, PyInstaller, Inno Setup).

**Spec:** `docs/superpowers/specs/2026-10-18-logos-match-design.md` — §14 (approved 01/11/2026). §1–§13 still bind.

## Global Constraints

- Run tests from `WebPosto_API`: `.venv/Scripts/python -m pytest -o addopts="" -p no:warnings tests/unit/match tests/unit/cash_reconciliation tests/unit/test_segredos.py -q`. Measure the baseline before Task 1 and keep everything green.
- Exceptions are logged only as `type(exc).__name__`. Never put `str(exc)` in user text. No secrets in logs, HTML, DB rows or Telegram callback data.
- Times: America/Recife; display `dd/mm/aaaa HH:mm`; store ISO UTC. Money: `Decimal`, stored as TEXT.
- Panel rules:
  - the session stores only `usuario_id`;
  - authorize with `acesso.pode_agora` / `postos_visiveis_agora`;
  - CSRF on every POST;
  - no JavaScript (meta refresh allowed).
- **Writing to webPosto only through `enviar_ofx_webposto`.**
  - Its barrier stays: only `IMPORTAR_APENAS_DIAS_INEXISTENTES_SISTEMA`, ≤7 days per send, only past days, account checked against `V1/CONTAS`, local send history.
  - Camada 2 writes **nothing** to webPosto in this plan.
- Robot and existing CLI behaviour stay unchanged. The `.env` locks still apply whenever no explicit authorization is injected.
- Never launch the installed Logos Match from this shell. Claude's MSIX virtualization redirects `%LOCALAPPDATA%`; use `LOGOS_MATCH_DIR` with a temp dir for any smoke test.
- Commits in Portuguese, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Version at the end: `0.4.0`.

## Review Focus

1. **The same OFX dropped twice, or an overlapping period downloaded again** (e.g. 01–31/10, then 15/10–15/11). Expected: lines already read (same FITID or same fallback hash) never enter twice, and the second file's preview only counts the new lines and days. Test in Task 2.
2. **An approval clicked twice** (panel and Telegram both, or a double tap). Expected: one import only; the second click answers "Já resolvido" (test in Task 4 and Task 3).
3. **The Telegram bot token is also polled by the LOGOS robot.** getUpdates returns 409 Conflict. Expected: the app stops polling for that channel, shows "Este bot já é usado por outro programa; crie um bot só para o Logos Match." on the channel page, and approvals keep working in the panel (test in Task 4).
4. **A file that is not a valid OFX, or from an unknown bank or account.** Expected: an invalid file is moved to `Recusados` with a reason in Portuguese. An unknown account waits for linking in the panel and is never lost (test in Task 2).
5. **webPosto rejects or times out on the import.** Expected: the approval becomes "falhou" with an explanation, nothing is marked imported, the line can be retried by a new approval, and the trust counter does not go up (test in Task 3).

---

### Task 1: Injection points in the OFX writer (existing module)

**Files:**
- Modify: `src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py`
- Test: `tests/unit/cash_reconciliation/test_webposto_escrita_ofx.py` (append)

**Interfaces:**
- `enviar_ofx_webposto(..., autorizacao: Callable[[], tuple[bool, str]] | None = None, ...)`:
  - With `None`: behaviour exactly as today (`.env` locks).
  - When given: it replaces `verificar_travas_ambiente`. A `(False, motivo)` result blocks the send with the same error path as today.
- The conta is still resolved by `resolver_cd_conta_unidade(unidade, banco, conta_sufixo, contas_cadastradas)` from `unidade.contas_extrato`. The app fills that list in Task 2, so no change is needed here.

- [ ] **Step 1:** Write failing tests:
  - `test_autorizacao_injetada_substitui_env`: with no `.env` file and `autorizacao=lambda: (True, "ok")`, a mocked `confirmar=True` send reaches the HTTP POST.
  - `test_autorizacao_injetada_bloqueia`: with `(False, "x")`, no POST and `ok=False`.
  - `test_sem_autorizacao_continua_exigindo_env`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement the change.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `refactor(ofx): autorização injetável no envio de OFX ao webPosto`.

### Task 2: Folder, recognition, deduplication and filing

**Files:**
- Create: `apps/match/extratos/__init__.py`, `apps/match/extratos/repositorio.py`, `apps/match/extratos/entrada.py`
- Modify:
  - `apps/match/banco.py` (migration 6)
  - `apps/match/caminhos.py` (`extratos(con) -> Path`, same pattern as `fiscal(con)`: `<pasta da rede>/Extratos`, else `raiz()/Extratos`)
  - `apps/match/unidades.py` (`montar` fills `Unidade.contas_extrato` from `conta_bancaria`)
  - `apps/match/agendador.py` (job `extratos` every 60 s plus once at start; same isolation and logging rules as the other jobs)
- Test: `tests/unit/match/test_extratos_entrada.py`

**Interfaces:**
- Migration 6 tables:
  - `conta_bancaria(id, posto_id NOT NULL REFERENCES posto(id), banco TEXT NOT NULL, agencia TEXT, conta_sufixo TEXT NOT NULL, cd_conta_webposto INTEGER NOT NULL, ativo INTEGER NOT NULL DEFAULT 1, UNIQUE(banco, conta_sufixo))`
  - `extrato_arquivo(id, sha256 TEXT UNIQUE NOT NULL, nome_original, recebido_em, banco, agencia, conta_sufixo, conta_bancaria_id NULL, inicio, fim, situacao CHECK IN ('aguardando_vinculo','lido','recusado'), motivo, caminho_arquivado)`
  - `extrato_linha(id, conta_bancaria_id NOT NULL, arquivo_id NOT NULL, chave TEXT NOT NULL, fitid, data, valor TEXT, tipo, descricao, documento, categoria, importada_webposto INTEGER NOT NULL DEFAULT 0, UNIQUE(conta_bancaria_id, chave))`
    - `chave` = FITID when present and not empty, else `"h:" + sha256(data|valor|descricao|documento)`.
- `entrada.processar_pasta(con, agora_: datetime) -> list[ResultadoArquivo]`:
  - Reads `<extratos>/Entrada/*.ofx` (case-insensitive) and handles each file under its own `try`.
  - **Invalid OFX** (`validar_cabecalho_ofx` / `ler_ofx` raise): move to `Recusados/<nome>`; situation `recusado`; motivo `"Arquivo não é um extrato OFX válido."`
  - **Same sha256 already seen:** move to `Duplicados/<nome>`; no new rows.
  - **Unknown account:** situation `aguardando_vinculo`; the file moves to `Aguardando/<nome>`.
  - **Known account:** lines are inserted with `INSERT ... ON CONFLICT DO NOTHING` (the count of new lines is returned); situation `lido`; the file is archived to `Extratos/<apelido_seguro>/<banco>-<conta_sufixo>/<aaaa-mm of fim>/<aaaammdd-hhmm>_<nome>`.
  - A file still being written (size changes between two reads 1 s apart, or `PermissionError`) is skipped this round.
- `entrada.vincular(con, arquivo_id, posto_id, cd_conta_webposto) -> int`: creates the `conta_bancaria`, then reprocesses every `aguardando_vinculo` file of that bank+account.
- `@dataclass ResultadoArquivo(nome: str, situacao: str, novas_linhas: int, mensagem: str)`
- `repositorio`: `contas(con)`, `conta_por_banco(con, banco, sufixo)`, `linhas_pendentes(con, conta_id) -> list[Row]` (where `importada_webposto=0`), `marcar_importadas(con, linha_ids)`, `arquivos(con, limite=50)`.
- `unidades.importar_units_json` also creates `conta_bancaria` rows from each unit's `contas_extrato`, when `cd_conta` is present.

- [ ] **Step 1:** Write failing tests using real tiny OFX fixtures. Write SGML strings for BB and PagBank (`TRNTYPE IN/OUT`) in the test file; each run uses `tmp_path` as `LOGOS_MATCH_DIR`.
  - `test_ofx_invalido_vai_para_recusados`
  - `test_mesmo_arquivo_duas_vezes_vai_para_duplicados`
  - `test_periodo_sobreposto_so_conta_linhas_novas` (Review Focus 1; the second file shares 3 lines with the first → `novas_linhas` = only the new ones)
  - `test_fitid_vazio_usa_hash`
  - `test_conta_desconhecida_aguarda_vinculo_e_vincular_processa`
  - `test_arquivado_na_pasta_do_posto_conta_mes`
  - `test_arquivo_em_escrita_fica_para_depois`
  - `test_montar_preenche_contas_extrato`
  - `test_importar_units_json_cria_contas_bancarias`
  - `test_migracao_6_de_banco_v5`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `feat(match): pasta de extratos OFX com reconhecimento, arquivo e sem duplicidade`.

### Task 3: Camada 1 — preview, approval and import into webPosto

**Files:**
- Create: `apps/match/extratos/aprovacoes.py`, `apps/match/extratos/camada1.py`
- Modify:
  - `apps/match/banco.py` (migration 7)
  - `apps/match/painel/rotas.py` + new templates `extratos.html`, `extrato_aprovacao.html`
  - menu in `base.html`
- Test: `tests/unit/match/test_extratos_camada1.py`, `tests/unit/match/test_painel.py`

**Interfaces:**
- Migration 7:
  - `aprovacao(id, tipo CHECK IN ('importar_extrato','lancamento'), conta_bancaria_id, posto_id, resumo_json, hash TEXT NOT NULL, situacao CHECK IN ('pendente','aprovada','recusada','executada','falhou','automatica'), criada_em, decidida_em, decidida_por TEXT, canal_decisao TEXT, resultado TEXT, ticket TEXT UNIQUE NOT NULL)`
  - `ALTER TABLE posto ADD COLUMN enviar_extratos_webposto INTEGER NOT NULL DEFAULT 0`
- `aprovacoes`:
  - `criar(con, tipo, posto_id, conta_id, resumo: dict) -> Row`. The ticket is `secrets.token_urlsafe(9)`; the hash is the SHA-256 of the canonical `resumo` JSON.
  - `decidir(con, ticket, aprovar: bool, quem: str, canal: str) -> tuple[bool, str]`. It is atomic (`BEGIN IMMEDIATE`) and works only while `pendente`; otherwise it returns `(False, "Já resolvido.")`.
  - `pendentes(con, postos: list[int] | None) -> list[Row]`
- `camada1.montar_previa(con, conta_id) -> dict | None`:
  - The days of pending lines are grouped into windows of ≤7 consecutive past days (today excluded).
  - Days that webPosto already has are found through `enviar_ofx_webposto(..., confirmar=False)` previews. Pass the same `autorizacao` as `executar`: previews must work even when no `.env` exists. If the writer checks the locks before building the preview, Task 1 must also apply the injected authorization to previews.
  - It returns `{"conta", "posto", "periodos": [{"de","ate","linhas","entradas","saidas","dias_existentes"}], "total_linhas"}`, or `None` when nothing is new.
  - It creates a `pendente` approval only when there is no other `pendente` for that account.
- `camada1.executar(con, aprovacao_id) -> tuple[bool, str]`:
  - For each period it calls `enviar_ofx_webposto(unidade, arquivo_temporario, data_inicial, data_final, confirmar=True, autorizacao=lambda: _autorizado(con, posto_id), diretorio_historico=raiz()/"importacoes_ofx")`.
  - `arquivo_temporario` is an OFX the app rebuilds from the stored lines of that account and period. Write it with `extrato_reader`-compatible SGML: header plus `STMTTRN` with `TRNTYPE`, `DTPOSTED`, `TRNAMT`, `FITID`, `MEMO`.
  - `_autorizado` returns `(True, "")` only when the posto has `enviar_extratos_webposto=1`. Otherwise it returns `(False, "Envio de extratos ao webPosto está desligado para este posto.")`.
  - On success it marks those lines `importada_webposto=1`, sets the approval to `executada` and sends a notification.
  - On failure or timeout the approval becomes `falhou`, using `explicar.erro_pt` text. Nothing is marked; the next preview proposes the lines again (Review Focus 5).
- Run order: after `processar_pasta`, the `extratos` job calls `montar_previa` for each account with new lines. Approved approvals are executed by the same job; approving in the panel also triggers an immediate run in a background thread.
- Panel:
  - `GET /extratos` (VER, scoped by posto): files, accounts, `aguardando_vinculo` files with a link form (admin), pending approvals with preview, the history of approvals, the folder path, and "Abrir pasta" for admin (`os.startfile` in a background thread, local only).
  - `POST /extratos/vincular` (CONFIGURAR)
  - `POST /extratos/aprovacoes/{ticket}` with `acao=aprovar|recusar` (COLETAR on that posto)
  - `POST /postos/{id}/extratos-webposto` (CONFIGURAR) to switch `enviar_extratos_webposto`
  - Labels: pendente → "Aguardando aprovação", executada → "Importado no webPosto", falhou → "Falhou", recusada → "Recusado", automatica → "Importado automaticamente".

- [ ] **Step 1:** Write failing tests:
  - `test_previa_so_dias_novos_e_janelas_de_7`
  - `test_sem_linhas_novas_nao_cria_aprovacao`
  - `test_uma_pendente_por_conta`
  - `test_aprovar_executa_e_marca_importadas` (`enviar_ofx_webposto` mocked)
  - `test_falha_webposto_fica_falhou_e_nao_marca` (Review Focus 5)
  - `test_trava_do_posto_desligada_bloqueia_envio`
  - `test_decidir_duas_vezes_ja_resolvido` (Review Focus 2; also two threads)
  - Panel: `test_extratos_tela_escopo_por_posto`, `test_vincular_admin_e_csrf`, `test_aprovar_pelo_painel`, `test_gerente_outro_posto_403`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `feat(match): importação de extratos no webPosto com prévia e aprovação`.

### Task 4: Approvals through Telegram

**Files:**
- Create: `apps/match/canais/telegram_aprovacoes.py`
- Modify:
  - `apps/match/canais/telegram.py` (`enviar` gains `botoes: list[tuple[str, str]] | None`, sent as an inline keyboard through `src.shared.notificacao.telegram.enviar_mensagem(reply_markup=...)`)
  - `apps/match/__main__.py` (start the poller thread)
  - `canais.html` (checkbox "Receber aprovações por este canal" plus the conflict message)
- Test: `tests/unit/match/test_telegram_aprovacoes.py`

**Interfaces:**
- Canal `config_json["aprovacoes"]: bool`, default False. `config_json["aprovadores"]: list[str]` holds Telegram user ids allowed to decide; empty means anyone in the canal's `chat_ids`.
- When an approval is created, every canal with `aprovacoes=True` that covers the posto gets the preview text plus buttons `[("Aprovar", f"lm:a:{ticket}"), ("Recusar", f"lm:r:{ticket}")]`. Callback data never contains values or ids.
- `telegram_aprovacoes.rodar(con_factory, parar: threading.Event) -> None`:
  - Long-polls `getUpdates` (timeout 25 s, offset kept in memory) for each canal with approvals on.
  - On `callback_query` from an allowed chat and user, it calls `aprovacoes.decidir(..., quem=f"telegram:{from.id}", canal="telegram")`, answers with `answerCallbackQuery` ("Aprovado." / "Recusado." / "Já resolvido.") and edits the message text.
  - When an action is approved, it starts `camada1.executar`.
  - HTTP 409 → stops that canal, stores `config_json["aprovacoes_erro"] = "conflito"` and logs the type only (Review Focus 3).
  - A network error → back off 30 s and continue.
- The token is read with `credenciais.ler(f"canal/{id}/token")` and is never logged.

- [ ] **Step 1:** Write failing tests with `httpx.MockTransport`:
  - `test_aprovacao_envia_botoes_sem_dados_sensiveis`
  - `test_callback_aprova_e_executa`
  - `test_callback_de_quem_nao_pode_e_ignorado`
  - `test_clique_repetido_ja_resolvido`
  - `test_409_desliga_e_avisa_no_canal` (and `/canais` shows the conflict text)
  - `test_erro_de_rede_nao_derruba`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `feat(match): aprovações pelo Telegram com botões`.

### Task 5: Camada 2 — list the missing financial entries (no write)

**Files:**
- Create: `apps/match/extratos/camada2.py`
- Modify: `apps/match/painel/rotas.py` + `extratos.html` (section "Faltando no financeiro")
- Test: `tests/unit/match/test_extratos_camada2.py`

**Interfaces:**
- `camada2.analisar(con, conta_id, de: date, ate: date) -> list[dict]`:
  - Calls `identificar_despesas_sem_lancamento(unidade, de, ate, extratos_mock=[<ExtratoBancario rebuilt from stored lines>])` with the live webPosto reads.
  - Each item: `{chave_linha, data, valor, descricao, tipo_sugerido, plano_conta, centro_custo, explicacao_pt}`.
  - It runs after a successful camada 1 for that period, and on demand from the panel.
- Each item creates an approval `tipo='lancamento'` with `resumo` = item, unless one already exists for that `chave_linha`.
- Decisions:
  - `aprovar` → `situacao='aprovada'` and the result "Aguardando liberação de lançamentos no webPosto (teste supervisionado pendente)." **No webPosto call.**
  - `corrigir` (panel only) → saves the corrected plano/centro in `resumo`, then counts as approved with correction.
  - `recusar` → done.
- Telegram buttons for camada 2: Aprovar and Recusar only. "Corrigir" is panel-only.

- [ ] **Step 1:** Write failing tests:
  - `test_linha_ja_lancada_nao_vira_proposta`
  - `test_proposta_unica_por_linha`
  - `test_aprovar_nao_chama_webposto`
  - `test_corrigir_guarda_classificacao`
  - Panel: `test_faltando_no_financeiro_escopo_e_csrf`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite and confirm it is green.
- [ ] **Step 5:** Commit `feat(match): lista do que falta no financeiro a partir do extrato`.

### Task 6: Gradual autonomy, notifications, docs and release 0.4.0

**Files:**
- Create: `apps/match/extratos/autonomia.py`
- Modify:
  - `camada1.py` (automatic path)
  - `banco.py` (migration 8)
  - panel (`/extratos/autonomia` screen, admin)
  - `canais/envio.py` (summary of extratos in the daily message)
  - `README.md`
  - `__init__.py` (`VERSAO = "0.4.0"`)
- Test: `tests/unit/match/test_extratos_autonomia.py`

**Interfaces:**
- Migration 8: `autonomia(id, chave_tipo TEXT UNIQUE NOT NULL, aprovacoes_seguidas INTEGER NOT NULL DEFAULT 0, automatico INTEGER NOT NULL DEFAULT 0, desligado_por_admin INTEGER NOT NULL DEFAULT 0, atualizado_em)`
- `chave_tipo`:
  - camada 1: `f"importar:{conta_id}"`
  - camada 2: `f"lanc:{conta_id}:{padrao_descricao}:{plano}:{centro}"`, where `padrao_descricao` is the normalized description with digits removed
- Constants: `APROVACOES_PARA_AUTOMATICO = 5`, `LIMITE_POR_LANCAMENTO = Decimal("500.00")`, `LIMITE_DIARIO_POR_CONTA = Decimal("2000.00")`.
- `registrar_decisao(con, chave_tipo, aprovada: bool, corrigida: bool) -> None`:
  - A clean approval adds 1. A correction, a rejection or a camada 1 failure resets the count to 0 and turns automatic off.
  - When the count reaches 5 and the admin has not switched the type off, the type becomes automatic.
- `pode_automatico(con, chave_tipo, valor: Decimal | None, conta_id) -> bool`:
  - Camada 1 needs only `automatico`.
  - Camada 2 also requires `valor <= 500`, the day total ≤ 2000 per account, a debit, and not a transfer between own accounts.
- Camada 1 automatic: `montar_previa` creates the approval as `automatica` and executes it at once, then notifies "Importado automaticamente".
- Camada 2 "automatic" only marks the type as eligible ("Pronto para lançar sozinho") because writes are not enabled. There is no webPosto call.
- Admin screen: list of types with counter, state and buttons "Desligar automático" / "Religar". Every change goes to `log_acesso`.
- Daily message: "Extratos: N importados, M aguardando aprovação, K faltando no financeiro."
- Rebuild the installer and run the packaged `--verificar` with a temp `LOGOS_MATCH_DIR`.

- [ ] **Step 1:** Write failing tests:
  - `test_cinco_aprovacoes_viram_automatico`
  - `test_correcao_zera`
  - `test_falha_camada1_zera`
  - `test_limites_valor_e_diario`
  - `test_transferencia_propria_nunca_automatica`
  - `test_admin_desliga`
  - `test_camada1_automatica_executa_e_avisa`
  - `test_camada2_automatico_nao_chama_webposto`
  - `test_resumo_diario_extratos`
- [ ] **Step 2:** Run the tests and confirm they FAIL.
- [ ] **Step 3:** Implement. In the README, document the extratos folder (path, how to download the OFX, linking accounts, the per-posto switch, approvals, autonomy rules).
- [ ] **Step 4:** Run the full suite and confirm it is green. Build `dist/LogosMatch-Setup-0.4.0.exe`, then run `LogosMatchCLI.exe --verificar` and confirm exit 0.
- [ ] **Step 5:** Commit `feat(match): autonomia gradual dos extratos; versão 0.4.0`.
