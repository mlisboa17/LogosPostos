# Logos Match Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App Windows **Logos Match** instalável (bandeja + painel local) que coleta Premmia e PagBank EDI por posto, compara com os caixas do webPosto e envia o resultado por Telegram/e-mail, reaproveitando `cash_reconciliation`.

**Architecture:** Pacote `WebPosto_API/apps/match/` importa os adapters e a conciliação existentes. O módulo existente ganha só dois pontos de injeção: um resolvedor de segredos (substitui `os.getenv` nas 3 leituras de credencial) e um provedor de unidades (substitui `units.json` quando o app está rodando). O app guarda postos/coletas em SQLite e segredos no Windows Credential Manager.

**Tech Stack:** Python (versão do `WebPosto_API/pyproject.toml`), FastAPI + Uvicorn + Jinja2, APScheduler 3.x, pystray + Pillow, keyring, openpyxl, httpx, Playwright (canal `msedge`), windows-toasts, PyInstaller, Inno Setup 6.

**Spec:** `docs/superpowers/specs/2026-10-18-logos-match-design.md`

## Global Constraints

- Nome do produto: **Logos Match**; pasta de dados `%LOCALAPPDATA%\LogosMatch\`; keyring service `LogosMatch`.
- Fuso `America/Recife` (usar `domain/tempo.py`: `FUSO`, `agora`, `ontem`); exibição `dd/mm/aaaa HH:mm`; ISO só em armazenamento/transporte.
- Valores em `Decimal`; no SQLite como TEXT.
- Segredo nunca em SQLite, xlsx, log, export JSON, mensagem ou exceção.
- Nenhuma escrita no webPosto a partir do app (só GET).
- Painel ouve apenas `127.0.0.1` e exige login; perfis `administrador`, `gerente`, `conferente` (matriz na seção 7A da spec).
- Toda divergência tem `explicacao_pt` + `correcao_pt` em português simples e `responsavel` (nome + código do frentista, via propriedade `.responsavel` já existente).
- Nada da rede do diretor fixo no código do app (import do `units.json` é ação manual).
- Rodar testes com `cd WebPosto_API && python -m pytest -o addopts="" <alvo>`; a suíte `tests/unit/cash_reconciliation` (635 testes) deve continuar verde.
- Trabalhar num worktree em branch `feature/logos-match` criada a partir de `feature/cash-audit-fechamento` (o checkout principal tem trabalho não commitado de outra sessão).

## Review Focus

1. Usuário clica "Coletar agora (visível)" depois que a coleta noturna do Premmia falhou → hoje as travas `logins/<emp>_<dia>.json` e `avisos/<emp>.json` bloqueiam; esperado: coleta manual visível libera as travas só daquele posto e tenta (teste na Task 2).
2. Máquina estava desligada/suspensa às 06:00 → esperado: ao abrir o app depois do horário, roda a coleta do dia uma vez (teste na Task 8).
3. Ao editar uma fonte, o usuário deixa o campo de senha em branco → esperado: manter a senha anterior, não apagar (teste na Task 10).
4. PagBank responde 401 ou o portal Premmia cai num posto → esperado: aquela coleta fica `erro` com texto legível e os demais postos/fontes seguem (teste na Task 5).
5. Gerente/conferente digita na barra do navegador a URL de um posto que não é dele (`/postos/7/fontes`, `POST /coletar?posto_id=7`) → esperado: 403, e nada vaza na tela (teste na Task 10).

---

### Task 1: Pontos de injeção no módulo existente (segredos e unidades)

**Files:**
- Create: `WebPosto_API/src/shared/segredos.py`
- Modify: `WebPosto_API/src/modules/webposto_integration/http.py:43` (leitura da chave)
- Modify: `WebPosto_API/src/modules/cash_reconciliation/adapters/pagbank_edi.py:69-70`
- Modify: `WebPosto_API/src/modules/cash_reconciliation/adapters/premmia_portal.py:449-450`
- Modify: `WebPosto_API/src/modules/cash_reconciliation/config/__init__.py` (`carregar_unidades`)
- Test: `WebPosto_API/tests/unit/test_segredos.py`

**Interfaces:**
- Produces: `obter_segredo(nome: str) -> str` (string vazia se ausente, já com `.strip()`); `definir_resolvedor(f: Callable[[str], str | None] | None) -> None` (None volta ao `os.getenv`).
- Produces: `config.definir_provedor_unidades(f: Callable[[], dict[int, Unidade]] | None) -> None`; `carregar_unidades(caminho=ARQUIVO)` usa o provedor quando definido **e** `caminho` é o padrão.

- [ ] **Step 1: Write the failing tests**

```python
def test_padrao_le_ambiente(monkeypatch):
    monkeypatch.setenv("X_TESTE", "  abc ")
    definir_resolvedor(None)
    assert obter_segredo("X_TESTE") == "abc"
    assert obter_segredo("NAO_EXISTE") == ""

def test_resolvedor_substitui_ambiente(monkeypatch):
    monkeypatch.setenv("X_TESTE", "do_env")
    definir_resolvedor(lambda n: "do_cofre" if n == "X_TESTE" else None)
    try:
        assert obter_segredo("X_TESTE") == "do_cofre"
        assert obter_segredo("OUTRO") == ""
    finally:
        definir_resolvedor(None)

def test_provedor_de_unidades():
    u = Unidade(empresa_codigo=-1, nome="TESTE", chave_env="LC_1_WEBPOSTO_CHAVE", destinos=())
    definir_provedor_unidades(lambda: {-1: u})
    try:
        assert carregar_unidades()[-1] is u
    finally:
        definir_provedor_unidades(None)
    assert 74014 in carregar_unidades()

async def test_pagbank_usa_resolvedor():
    definir_resolvedor(lambda n: None)
    try:
        with pytest.raises(PagBankCredencialInvalida):
            await pagbank_edi.buscar_transacoes(74014, date(2026, 10, 5), client=httpx.AsyncClient())
    finally:
        definir_resolvedor(None)
```

- [ ] **Step 2: Run** `python -m pytest -o addopts="" tests/unit/test_segredos.py -v` → FAIL (`ModuleNotFoundError: src.shared.segredos`).
- [ ] **Step 3: Implement** `segredos.py` (resolvedor em variável de módulo) e troque as 3 leituras de credencial por `obter_segredo(...)`; em `config/__init__.py` adicione `_provedor` de módulo + `definir_provedor_unidades`.
- [ ] **Step 4: Run** `python -m pytest -o addopts="" tests/unit/test_segredos.py tests/unit/cash_reconciliation -q` → tudo PASS (635 + 4).
- [ ] **Step 5: Commit** `git commit -m "refactor(cash): resolvedor de segredos e provedor de unidades injetáveis"`

### Task 2: Premmia — canal do navegador e liberação para coleta manual

**Files:**
- Modify: `WebPosto_API/src/modules/cash_reconciliation/adapters/premmia_portal.py` (`abrir_login`, nova função)
- Test: `WebPosto_API/tests/unit/cash_reconciliation/test_premmia_portal.py` (acrescentar)

**Interfaces:**
- Produces: `liberar_nova_tentativa(unidade: Unidade, diretorio: Path) -> None` — apaga `diretorio/logins/<emp>_<hoje>.json` e `diretorio/avisos/<emp>.json` se existirem; nunca toca em outro posto.
- `abrir_login` passa `channel=os.getenv("LOGOS_NAVEGADOR_CANAL") or None` para `playwright.chromium.launch` (o app define `msedge`; robô atual inalterado).

- [ ] **Step 1: Write the failing test**

```python
def test_liberar_nova_tentativa_so_do_posto(tmp_path, unidade_doze, unidade_casa):
    hoje = agora().date().isoformat()
    for emp in (74014, 5555):
        (tmp_path / "logins").mkdir(exist_ok=True)
        (tmp_path / "logins" / f"{emp}_{hoje}.json").write_text("{}")
        (tmp_path / "avisos").mkdir(exist_ok=True)
        (tmp_path / "avisos" / f"{emp}.json").write_text('{"dia_alvo": "2026-10-17"}')
    liberar_nova_tentativa(unidade_doze, tmp_path)
    assert not (tmp_path / "logins" / f"74014_{hoje}.json").exists()
    assert not (tmp_path / "avisos" / "74014.json").exists()
    assert (tmp_path / "logins" / f"5555_{hoje}.json").exists()
    assert (tmp_path / "avisos" / "5555.json").exists()
```
(Use as unidades do `carregar_unidades()` ou fixtures existentes do arquivo.)

- [ ] **Step 2: Run** o teste → FAIL (`ImportError: liberar_nova_tentativa`).
- [ ] **Step 3: Implement** `liberar_nova_tentativa` e o `channel` em `abrir_login`.
- [ ] **Step 4: Run** `python -m pytest -o addopts="" tests/unit/cash_reconciliation/test_premmia_portal.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(premmia): canal do navegador configurável e liberação de nova tentativa manual"`

### Task 3: Base do app — caminhos e banco SQLite

**Files:**
- Create: `WebPosto_API/apps/__init__.py`, `WebPosto_API/apps/match/__init__.py` (`NOME = "Logos Match"`, `VERSAO = "0.1.0"`)
- Create: `WebPosto_API/apps/match/caminhos.py`
- Create: `WebPosto_API/apps/match/banco.py`
- Create: `WebPosto_API/requirements-match.txt` (fastapi, uvicorn, jinja2, apscheduler<4, pystray, pillow, keyring, windows-toasts, openpyxl, httpx, playwright==1.58.0, pydantic, pyinstaller)
- Test: `WebPosto_API/tests/unit/match/test_banco.py`

**Interfaces:**
- `caminhos.raiz() -> Path` — `Path(os.getenv("LOGOS_MATCH_DIR") or %LOCALAPPDATA%/LogosMatch)`, cria se faltar; `caminhos.premmia(posto_id: int) -> Path` = `raiz()/premmia/<posto_id>`; `caminhos.planilhas() -> Path`; `caminhos.logs() -> Path`.
- `banco.conectar(caminho: Path | None = None) -> sqlite3.Connection` — `row_factory=sqlite3.Row`, `foreign_keys=ON`, roda migrações (tabela `schema_version`).
- Tabelas e colunas exatamente as da seção 5 da spec. Restrições: `UNIQUE(posto_id, fonte, identificador)` em `transacao`; `UNIQUE(fonte_id, dia)` em `coleta` (nova coleta do mesmo dia faz UPDATE); `fonte.tipo CHECK IN ('premmia','pagbank_edi','webposto')`.
- Funções pequenas no mesmo arquivo (uma por operação usada nas tasks seguintes): `inserir_posto(con, nome, apelido, cnpj, empresa_codigo_webposto) -> int`, `listar_postos(con, so_ativos=True) -> list[Row]`, `salvar_fonte(con, posto_id, tipo, ativo, config: dict) -> int`, `fontes_do_posto(con, posto_id) -> list[Row]`, `registrar_coleta(con, fonte_id, dia, situacao, qtd, total, erro_texto) -> int`, `gravar_transacoes(con, coleta_id, posto_id, fonte, transacoes: list[TransacaoAdquirente]) -> int` (ignora repetidas), `gravar_divergencias(con, posto_id, dia, fonte, itens: list[dict]) -> None` (apaga as do mesmo posto/dia/fonte antes), `id_instalacao(con) -> str` (cria UUID na 1ª vez).

- [ ] **Step 1: Write failing tests** — `test_migracao_idempotente` (conectar 2× no mesmo arquivo, `schema_version` = 1), `test_transacao_repetida_ignorada` (gravar a mesma `TransacaoAdquirente` 2× → contagem 1), `test_coleta_mesmo_dia_atualiza` (registrar 2× → 1 linha, situação da 2ª), `test_valor_decimal_preservado` (`Decimal("10.10")` volta igual), `test_id_instalacao_estavel`.
- [ ] **Step 2: Run** `python -m pytest -o addopts="" tests/unit/match/test_banco.py -v` → FAIL.
- [ ] **Step 3: Implement** `caminhos.py` e `banco.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(match): base do app com caminhos locais e banco SQLite"`

### Task 4: Credenciais no Credential Manager e unidades vindas do banco

**Files:**
- Create: `WebPosto_API/apps/match/credenciais.py`
- Create: `WebPosto_API/apps/match/unidades.py`
- Test: `WebPosto_API/tests/unit/match/test_credenciais.py`, `test_unidades.py`

**Interfaces:**
- `credenciais.SERVICO = "LogosMatch"`; `salvar(chave: str, valor: str) -> None` (valor vazio → não faz nada); `ler(chave: str) -> str | None`; `apagar(chave: str) -> None`; `tem(chave: str) -> bool`. Chaves: `"<posto_id>/premmia/usuario"`, `"<posto_id>/premmia/senha"`, `"<posto_id>/pagbank/usuario"`, `"<posto_id>/pagbank/token"`, `"<posto_id>/webposto/chave"`, `"canal/<canal_id>/<campo>"`. (Formato decidido aqui; a spec dizia `LogosMatch/<posto_id>/<tipo>` — mesma ideia.)
- `unidades.codigo_empresa(posto: Row) -> int` = `empresa_codigo_webposto` ou `-posto.id`.
- `unidades.montar(con) -> dict[int, Unidade]` — para cada posto ativo: `Unidade(empresa_codigo=codigo_empresa(p), nome, apelido=apelido or f"P{id}", chave_env=f"LC_{id}_WEBPOSTO_CHAVE", premmia_ativo=<fonte premmia ativa>, premmia_usuario_env=f"LC_{id}_PREMMIA_USUARIO", premmia_senha_env=f"LC_{id}_PREMMIA_SENHA", destinos=(), administradoras=fonte_premmia_ou_pagbank.config.get("administradoras", {}))`.
- `unidades.resolvedor(con) -> Callable[[str], str | None]` — traduz `LC_<id>_<FONTE>_<CAMPO>` e `PAGBANK_(USER|TOKEN)_<empresa_codigo>` para `credenciais.ler(...)`; qualquer outro nome → `None`.
- `unidades.ativar(con) -> None` — chama `definir_resolvedor` e `definir_provedor_unidades` da Task 1.
- `unidades.importar_units_json(con, caminho: Path) -> int` — cria postos/fontes a partir do `units.json` (sem segredos; fontes criadas inativas até ter credencial); ignora `empresa_codigo` já cadastrado.
- `unidades.exportar_config(con) -> dict` / `importar_config(con, dados: dict) -> int` — postos, fontes (config não secreta), canais (config não secreta); nunca inclui valores do keyring.

- [ ] **Step 1: Write failing tests** (keyring em memória: `keyring.set_keyring(...)` com backend falso de teste): `test_salvar_vazio_nao_apaga`, `test_resolvedor_pagbank_por_empresa` (posto 74014 com token salvo → `obter_segredo("PAGBANK_TOKEN_74014")` retorna o token), `test_posto_sem_webposto_tem_codigo_negativo`, `test_resolvedor_ignora_nome_desconhecido`, `test_exportar_nao_tem_segredo` (salvar senha "S3gr3d0!" e garantir que `"S3gr3d0!"` não aparece em `json.dumps(exportar_config(con))`), `test_importar_units_json_idempotente`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python -m pytest -o addopts="" tests/unit/match -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(match): credenciais no Credential Manager e unidades a partir do banco"`

### Task 5: Coleta e comparação por posto

**Files:**
- Create: `WebPosto_API/apps/match/coletas.py`
- Create: `WebPosto_API/apps/match/explicar.py`
- Test: `WebPosto_API/tests/unit/match/test_coletas.py`, `test_explicar.py`

**Interfaces:**
- Consumes: `premmia_portal.coletar(unidade, ate=dia, visivel=..., diretorio=caminhos.premmia(id))`, `premmia_portal.buscar_transacoes(unidade, dia, diretorio)`, `premmia_portal.liberar_nova_tentativa`, `pagbank_edi.buscar_transacoes(emp, dia)`, `conciliar_cartoes.coletar_contexto_cartoes(emp, dia)`, `conciliar_cartoes.conciliar(...)`, `conciliar_cartoes.da_adquirente`.
- `@dataclass ResultadoFonte(posto_id: int, fonte: str, dia: date, situacao: str, qtd: int, total: Decimal, mensagem: str, divergencias: list[dict])` — `situacao ∈ {"ok","sem_movimento","erro","verificacao_humana","sem_comparacao"}`.
- `async coletar_posto(con, posto_id: int, dia: date, *, visivel: bool = False, so_falhas: bool = False) -> list[ResultadoFonte]` — para cada fonte ativa: coleta → grava `coleta` + `transacao`; se o posto tem chave webPosto, roda a comparação (Premmia: transações da planilha + contexto filtrado por `da_adquirente(c, "PREMMIA", ...)`; PagBank: D-1..D+1 como em `conciliar_pagbank`, removendo cartões PREMMIA quando o Premmia está ativo) e grava divergências; sem chave → `sem_comparacao`. Cada fonte em `try/except` próprio: exceção vira `erro` com mensagem de `explicar.erro_pt(exc)`; `PremmiaVerificacaoHumana` vira `verificacao_humana`. `visivel=True` chama `liberar_nova_tentativa` antes. `so_falhas=True` pula fontes cuja coleta do dia já está `ok`/`sem_movimento`.
- `async coletar_todos(con, dia, *, so_falhas=False) -> list[ResultadoFonte]` — percorre postos ativos, um de cada vez.
- `explicar.divergencias(resultado: ResultadoCartoes) -> list[dict]` com chaves `tipo, valor_esperado, valor_encontrado, nsu, caixa_codigo, responsavel, explicacao_pt, correcao_pt`:
  - `a_maior` (Investigacao): tipo `"falta_no_webposto"`; explicação `"Venda de R$ {valor} às {HH:MM} (NSU {nsu}) está no {fonte} mas não foi lançada no webPosto. Responsável provável: {responsavel}."`; correção `"Lançar o cartão NSU {nsu} no caixa correto do webPosto."`
  - `a_menor` (CartaoErp): tipo `"sobra_no_webposto"`; explicação `"Cartão de R$ {valor} às {HH:MM} lançado no webPosto ({responsavel}) não aparece no {fonte}."`; correção `"Conferir com o frentista se a venda foi em outra forma de pagamento e corrigir o lançamento."`
  - `Casamento` com `valor_divergente`: tipo `"valor_diferente"`; explicação com os dois valores e a diferença; correção `"Corrigir o valor do cartão NSU {nsu} no webPosto."`
  - `alertas`: tipo = `alerta.codigo`, explicação = `alerta.mensagem`.
  Valores formatados `R$ 1.234,56`; hora em America/Recife.
- `explicar.erro_pt(exc: Exception) -> str` — `PagBankCredencialInvalida` → `"PagBank recusou o usuário/token. Confira em Fontes do posto."`; `PremmiaVerificacaoHumana` → `"O Premmia pediu verificação humana. Clique em Coletar agora (visível)."`; `WebPostoErro` → `"webPosto indisponível ou chave inválida."`; outros → `"Falha inesperada na coleta ({TipoDaExcecao})."` (nunca `str(exc)` cru, para não vazar segredo).

- [ ] **Step 1: Write failing tests** (adapters substituídos por `monkeypatch`): `test_erro_numa_fonte_nao_para_as_outras` (PagBank levanta `PagBankCredencialInvalida`, Premmia ok → 2 resultados, `erro` e `ok`), `test_dia_sem_movimento` (PagBank retorna `[]` → `sem_movimento`, mensagem contém `"sem vendas registradas"`), `test_posto_sem_chave_webposto_nao_compara` (→ `sem_comparacao`, `coletar_contexto_cartoes` não chamado), `test_verificacao_humana`, `test_visivel_libera_travas` (verifica chamada de `liberar_nova_tentativa`), `test_so_falhas_pula_ok`, `test_explicacao_falta_no_webposto` (valor `Decimal("150.00")`, momento 17/10/2026 14:05 Recife, NSU `"123"` → texto exato `"Venda de R$ 150,00 às 14:05 (NSU 123) está no PagBank mas não foi lançada no webPosto. Responsável provável: JOÃO (42)."`), `test_erro_pt_nao_vaza_mensagem` (exceção genérica com `"token=abc"` → texto não contém `"abc"`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Rodar o Premmia síncrono via o próprio `coletar` (já usa `asyncio.to_thread`).
- [ ] **Step 4: Run** `python -m pytest -o addopts="" tests/unit/match -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(match): coleta Premmia/PagBank por posto e comparação com webPosto"`

### Task 6: Planilha do dia

**Files:**
- Create: `WebPosto_API/apps/match/relatorio_xlsx.py`
- Test: `WebPosto_API/tests/unit/match/test_relatorio_xlsx.py`

**Interfaces:**
- `gerar(con, posto_id: int, dia: date, destino: Path | None = None) -> Path` → `caminhos.planilhas()/Logos_<apelido>_<dd-mm-aaaa>.xlsx`, abas `Resumo` (fonte, situação, quantidade, total, mensagem), `Premmia`, `PagBank` (transações: data/hora dd/mm/aaaa HH:mm, NSU, autorização, valor, bandeira/forma, situação), `Divergências` (tipo, valor esperado, valor encontrado, NSU, caixa, responsável, o que houve, o que fazer). Valores como número com formato `R$ #,##0.00`.

- [ ] **Step 1: Write failing tests** — `test_abas_e_nome_do_arquivo`, `test_data_no_formato_brasil` (célula de data = `"17/10/2026 14:05"`), `test_valor_numerico_formatado`, `test_sem_segredo_na_planilha` (salvar senha no keyring falso e varrer todas as células).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(match): planilha diária por posto"`

### Task 7: Canais de envio (Telegram, e-mail, notificação Windows)

**Files:**
- Create: `WebPosto_API/apps/match/canais/__init__.py`, `telegram.py`, `email_smtp.py`, `toast.py`, `envio.py`
- Test: `WebPosto_API/tests/unit/match/test_canais.py`

**Interfaces:**
- Consumes: `src.shared.notificacao.telegram.enviar_mensagem(texto, token=, chat_ids=, cliente=)` e `enviar_documento(caminho, legenda, token=, chat_ids=, cliente=)`.
- `telegram.enviar(canal: Row, texto: str, anexo: Path | None) -> None` — token em `canal/<id>/token`, chats em `config_json["chat_ids"]`.
- `email_smtp.enviar(canal: Row, assunto: str, texto: str, anexo: Path | None) -> None` — `smtplib.SMTP` + `starttls()` (porta 587) ou `SMTP_SSL` (465); `config_json`: `servidor, porta, usuario, destinatarios`; senha em `canal/<id>/senha`.
- `toast.avisar(titulo: str, texto: str) -> None` — `windows-toasts`; em falha só loga.
- `envio.texto_resumo(resultados: list[ResultadoFonte], posto: Row, dia: date) -> str` — 1 linha por fonte com ✅ (ok), ⚠️ (sem_movimento/sem_comparacao), ❌ (erro/verificacao_humana) + até 10 divergências (`explicacao_pt`), e "e mais N na planilha".
- `envio.enviar_dia(con, resultados, dia) -> None` — por posto: gera planilha (Task 6), envia em cada canal ativo cujo `config_json["postos"]` está vazio ou contém o posto, grava `envio` (situação `ok`/`erro` + `explicar.erro_pt`). Falha num canal não impede os outros.
- `envio.testar_canal(con, canal_id: int) -> str` — manda "Teste do Logos Match" e devolve "ok" ou o erro em português.

- [ ] **Step 1: Write failing tests** (Telegram com `httpx.MockTransport`; SMTP com classe falsa via monkeypatch): `test_resumo_icones`, `test_resumo_limita_dez_divergencias`, `test_canal_limitado_a_posto` (canal com `postos=[2]` não recebe o posto 1), `test_falha_telegram_nao_impede_email`, `test_envio_registrado`, `test_email_anexa_planilha`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(match): envio por Telegram, e-mail e notificação do Windows"`

### Task 8: Agendador, rotina diária e retenção

**Files:**
- Create: `WebPosto_API/apps/match/agendador.py`, `WebPosto_API/apps/match/rotina.py`
- Test: `WebPosto_API/tests/unit/match/test_rotina.py`

**Interfaces:**
- Config na tabela `instalacao` (colunas extras `hora_coleta TEXT DEFAULT '06:00'`, `hora_repescagem TEXT DEFAULT '10:00'`) — migração 2 em `banco.py`.
- `rotina.executar(con, *, dia: date | None = None, so_falhas: bool = False, visivel: bool = False, posto_id: int | None = None) -> list[ResultadoFonte]` — `dia` padrão `ontem()`; chama `unidades.ativar(con)`, coleta, envia (Task 7); `verificacao_humana` ou `erro` → também `toast.avisar`. Na repescagem, se ainda faltar, a mensagem diz `"O dia {dd/mm/aaaa} ficou sem coleta de {fonte} no {posto}."`
- `rotina.precisa_recuperar(con, agora_: datetime) -> bool` — True se já passou de `hora_coleta` hoje e não há `coleta` com `dia = ontem()` iniciada hoje.
- `rotina.limpar_antigos(con, hoje: date) -> None` — apaga `transacao/coleta/divergencia/envio` e planilhas com dia < hoje − 13 meses.
- `agendador.iniciar(con_factory) -> BackgroundScheduler` — jobs cron `hora_coleta` (executar + limpar_antigos) e `hora_repescagem` (executar so_falhas=True), `timezone=FUSO`, `coalesce=True`, `max_instances=1`; no início, se `precisa_recuperar`, agenda execução imediata. `agendador.reagendar(sched, con)` após mudar horários. Cada job roda `asyncio.run(...)` com conexão própria.

- [ ] **Step 1: Write failing tests** — `test_recupera_quando_maquina_estava_desligada` (agora 08:30, nenhuma coleta hoje → True; com coleta iniciada hoje → False; agora 05:00 → False), `test_repescagem_avisa_dia_sem_coleta`, `test_limpar_antigos_13_meses`, `test_erro_dispara_toast`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(match): agendamento diário, repescagem, recuperação e retenção"`

### Task 9: Usuários e níveis de acesso

**Files:**
- Create: `WebPosto_API/apps/match/acesso.py`
- Test: `WebPosto_API/tests/unit/match/test_acesso.py`

**Interfaces:**
- Consumes: tabelas `usuario`, `usuario_posto`, `log_acesso` (Task 3, seção 5 da spec).
- `class Perfil(str, Enum)`: `ADMINISTRADOR="administrador"`, `GERENTE="gerente"`, `CONFERENTE="conferente"`.
- `class Acao(str, Enum)`: `VER`, `COLETAR`, `TROCAR_CREDENCIAL`, `CADASTRAR_POSTO`, `CONFIGURAR` (canais, agenda, import/export), `GERIR_USUARIOS`.
- `pode(usuario: Row, acao: Acao, posto_id: int | None = None) -> bool` — matriz da seção 7A: administrador tudo; gerente `VER`/`COLETAR`/`TROCAR_CREDENCIAL` só em postos de `usuario_posto`; conferente `VER`/`COLETAR` só nos seus postos; demais → False; usuário inativo → False.
- `postos_visiveis(con, usuario: Row) -> list[int]`.
- `criar_usuario(con, nome, login, senha, perfil: Perfil, postos: list[int]) -> int` — senha com menos de 8 caracteres → `ValueError("A senha precisa ter pelo menos 8 caracteres.")`; hash `hashlib.scrypt(n=2**14, r=8, p=1)` com sal de 16 bytes, guardado como `scrypt$<sal_hex>$<hash_hex>`.
- `autenticar(con, login, senha, agora_: datetime) -> Row | None` — 5 falhas seguidas → `bloqueado_ate = agora_ + 15 min`; enquanto bloqueado retorna None mesmo com senha certa; sucesso zera `tentativas_falhas` e grava `ultimo_acesso_em`.
- `precisa_primeiro_uso(con) -> bool` (nenhum administrador ativo).
- `redefinir_admin(con, senha_nova: str) -> str` — cria/reativa o login `admin` como administrador; devolve o login.
- `registrar(con, usuario_id: int | None, acao: str, detalhe: str = "") -> None` — append em `log_acesso`; `detalhe` nunca recebe segredo.

- [ ] **Step 1: Write failing tests** — `test_matriz_de_acesso` (parametrizado com cada linha da tabela 7A, incluindo gerente no posto alheio → False), `test_senha_curta_recusa`, `test_hash_nao_e_a_senha` (`senha_hash` não contém a senha e começa com `"scrypt$"`), `test_bloqueio_apos_5_falhas` (6ª tentativa com senha certa → None; 16 min depois → Row), `test_usuario_inativo_nao_pode`, `test_primeiro_uso`, `test_redefinir_admin`.
- [ ] **Step 2: Run** `python -m pytest -o addopts="" tests/unit/match/test_acesso.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(match): usuários e níveis de acesso"`

### Task 10: Painel local

**Files:**
- Create: `WebPosto_API/apps/match/painel/__init__.py` (`criar_app(con_factory) -> FastAPI`), `rotas.py`, `templates/base.html`, `entrar.html`, `primeiro_uso.html`, `usuarios.html`, `hoje.html`, `postos.html`, `posto_fontes.html`, `canais.html`, `agenda.html`, `historico.html`, `static/estilo.css`
- Test: `WebPosto_API/tests/unit/match/test_painel.py`

**Interfaces:**
- Consumes: `acesso.*` (Task 9).
- Segurança: `/entrar` (login) e `/primeiro-uso` (cria administrador quando `precisa_primeiro_uso`) são as únicas rotas sem sessão; as demais redirecionam para `/entrar`. Sessão = cookie `lm_sessao` (aleatório, HttpOnly, SameSite=Strict) mapeado em memória para `usuario_id`, expira após 12 h sem uso; `/sair` encerra. Todo POST exige campo `csrf` igual ao da sessão. Cada rota checa `acesso.pode(usuario, acao, posto_id)` → 403 com a página "Você não tem acesso a isto."; listas usam `postos_visiveis`. Ações sensíveis chamam `acesso.registrar`.
- Rotas (GET mostra, POST grava e redireciona):
  - `/` Hoje — por posto: ícone por fonte, total, divergências (`explicacao_pt`, `correcao_pt`, `responsavel`); botões `POST /coletar?posto_id=&visivel=0|1` (roda `rotina.executar` em thread; devolve a página com "Coleta iniciada") e `POST /reenviar?posto_id=`.
  - `/postos`, `POST /postos` (novo/editar/desativar), `POST /postos/importar-logos` (Task 4, caminho do `units.json` do repo se existir), `GET /config/exportar` (download JSON), `POST /config/importar`.
  - `/postos/{id}/fontes`, `POST /postos/{id}/fontes/{tipo}` — campo secreto em branco = manter o atual; mostra `••••` quando `credenciais.tem(...)`; `POST /postos/{id}/fontes/{tipo}/testar` → PagBank: `buscar_transacoes(emp, ontem())`; webPosto: `buscar_caixas(unidade, ontem(), ontem())`; Premmia: só confirma que usuário/senha existem (login real só na coleta, por causa da trava de 1 tentativa/noite).
  - Ao cadastrar posto: aviso fixo `"Cadastre cada posto em uma só máquina para evitar coleta duplicada."`
  - `/canais`, `POST /canais`, `POST /canais/{id}/testar` (Task 7).
  - `/agenda`, `POST /agenda` (valida `HH:MM`, chama `agendador.reagendar`).
  - `/historico` — últimas 30 coletas e envios, datas `dd/mm/aaaa HH:mm`.
  - `/usuarios`, `POST /usuarios` (criar/editar perfil e postos/desativar/redefinir senha), `/usuarios/log` — só `GERIR_USUARIOS`.
  - O menu mostra só o que o perfil pode usar.

- [ ] **Step 1: Write failing tests** (`fastapi.testclient.TestClient`, keyring falso, banco em `tmp_path`): `test_sem_login_redireciona`, `test_primeiro_uso_cria_admin`, `test_login_errado_nao_entra`, `test_post_sem_csrf_recusa`, `test_gerente_posto_alheio_403` (GET `/postos/7/fontes` e POST `/coletar?posto_id=7`), `test_conferente_nao_troca_credencial`, `test_hoje_lista_so_postos_visiveis`, `test_log_registra_troca_de_credencial`, `test_senha_em_branco_mantem_anterior`, `test_tela_nao_mostra_segredo` (HTML de `/postos/{id}/fontes` não contém o valor salvo), `test_exportar_sem_segredo`, `test_agenda_hora_invalida_recusa`, `test_hoje_mostra_responsavel` (divergência com `"JOÃO (42)"` aparece na página).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Visual: HTML limpo, tema escuro opcional por `prefers-color-scheme`, sem framework JS.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(match): painel local de postos, fontes, canais e agenda"`

### Task 11: Bandeja, início e instância única

**Files:**
- Create: `WebPosto_API/apps/match/__main__.py`, `WebPosto_API/apps/match/bandeja.py`, `WebPosto_API/apps/match/assets/icone.ico`
- Test: `WebPosto_API/tests/unit/match/test_main.py`

**Interfaces:**
- `__main__.main() -> int`: define `os.environ.setdefault("LOGOS_NAVEGADOR_CANAL", "msedge")`; configura log rotativo em `caminhos.logs()/match.log` (5 × 1 MB, sem segredos); trava de instância única (mutex nomeado `Global\LogosMatch` via `ctypes`; se já existe, abre o painel da instância viva lendo `raiz()/porta.txt` e sai); escolhe porta livre em `127.0.0.1`, grava `porta.txt` (só a porta); sobe Uvicorn em thread; `agendador.iniciar`; `bandeja.rodar(url_painel, ao_coletar, ao_coletar_visivel, ao_sair)` no thread principal.
- Menu da bandeja: "Abrir painel" (`webbrowser.open(url_painel(porta))`, cai na tela de login), "Coletar agora", "Coletar agora (visível)", "Sair". Dica do ícone: `"Logos Match — última coleta dd/mm/aaaa HH:mm"`.
- `__main__.url_painel(porta: int) -> str` = `f"http://127.0.0.1:{porta}/"`.
- "Coletar agora" na bandeja vale como ação do usuário Windows da máquina (registrada em `log_acesso` com `usuario_id=None`, `acao="coleta_bandeja"`).

- [ ] **Step 1: Write failing tests** — `test_url_painel`, `test_porta_txt_so_tem_a_porta`, `test_segunda_instancia_nao_sobe_servidor` (mutex simulado).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Smoke manual:** `cd WebPosto_API && python -m apps.match` → ícone aparece, "Abrir painel" abre o navegador, criar o administrador no primeiro uso, cadastrar um posto de teste, "Coletar agora" registra coleta (erro legível sem credencial).
- [ ] **Step 6: Commit** `git commit -m "feat(match): bandeja do Windows e inicialização"`

### Task 12: Instalador

**Files:**
- Create: `WebPosto_API/apps/match/build/match.spec` (PyInstaller onedir, nome `LogosMatch`, ícone, inclui `painel/templates`, `painel/static`, `assets`; `console=False`)
- Create: `WebPosto_API/apps/match/build/instalador.iss` (Inno Setup: `PrivilegesRequired=lowest`, `DefaultDirName={localappdata}\Programs\LogosMatch`, atalho no Menu Iniciar, tarefa do Agendador "ao fazer logon" do usuário atual via `schtasks /Create /SC ONLOGON /TN "Logos Match" /TR "<exe>" /RL LIMITED /F`, removida no desinstalar; caixa "Apagar também os dados" no desinstalar → remove `{localappdata}\LogosMatch` e as entradas `LogosMatch` do Credential Manager via `<exe> --apagar-credenciais`)
- Create: `WebPosto_API/apps/match/build/build.ps1` (venv limpo, `pip install -r requirements-match.txt`, `pyinstaller`, `iscc`, saída `dist/LogosMatch-Setup-<VERSAO>.exe`)
- Modify: `WebPosto_API/apps/match/__main__.py` (flags `--apagar-credenciais`: apaga todas as chaves conhecidas do banco no keyring e sai; `--redefinir-admin`: pede a nova senha no console com `getpass` e chama `acesso.redefinir_admin`)
- Create: `WebPosto_API/apps/match/README.md` (instalar, primeiro acesso, perfis, cadastrar posto, onde ficam dados/segredos, como redefinir a senha do administrador, como gerar o instalador)

- [ ] **Step 1: Write failing tests** `test_redefinir_admin_pela_linha_de_comando` (getpass simulado) e `test_apagar_credenciais_remove_todas` (keyring falso com chaves de 2 postos e 1 canal → todas removidas).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** flag + arquivos de build. **Step 4: Run** → PASS.
- [ ] **Step 5: Build:** `powershell -File apps/match/build/build.ps1` → gera `dist/LogosMatch-Setup-0.1.0.exe` sem erros.
- [ ] **Step 6: Verificação em máquina limpa (ou outro usuário Windows):** instalar sem admin; app sobe no logon; Premmia abre com Edge; desinstalar com "apagar dados" limpa pasta e Credential Manager. Registrar resultado no README.
- [ ] **Step 7: Commit** `git commit -m "build(match): PyInstaller + Inno Setup"` e atualizar o topo do `STATUS.md` com a entrega.

---

## Fora deste plano (v2, ver seção 10 da spec)
EDI Cielo e Rede, Mais Pagamentos via OFX, coleta de extratos bancários (APIs dos bancos, e-mail IMAP, pasta/upload de OFX/CSV, Open Finance se houver opção sem custo). Cada um vira um plano próprio, como novo tipo de fonte do posto, sem mudar as Tasks 1–12.
