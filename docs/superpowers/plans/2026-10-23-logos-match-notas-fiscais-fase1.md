# Logos Match — Notas Fiscais, Fase 1 (NF-e via webPosto + pacote da contabilidade) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O Logos Match captura todo dia as NF-e recebidas por cada empresa pelo webPosto (XML completo), aceita NFS-e/NF-e por importação manual, e no dia de envio monta e manda a cada escritório de contabilidade o pacote do mês (XMLs, PDFs separados/unificados, planilha resumo).

**Architecture:** Núcleo reutilizável em `WebPosto_API/src/modules/fiscal_docs/` (parser, leitura webPosto, acervo, PDF), sem dependência do Match. O Match ganha `apps/match/fiscal/` (captura, planilha, pacote, conferência, envio mensal), migração v5 do SQLite, perfil Contabilidade e telas no painel. **Nenhuma consulta à SEFAZ ou ao ADN nesta fase**; só GET no webPosto.

**Tech Stack:** Python 3.11+ (venv do repo roda 3.14), stdlib `xml.etree.ElementTree` (sem lxml), Pydantic 2, httpx, openpyxl, `brazilfiscalreport` (DANFE, sobre fpdf2), `fpdf2` (DANFSe simples), `pypdf` (unir PDFs), FastAPI + Jinja2, APScheduler, keyring.

**Spec:** `docs/superpowers/specs/2026-10-23-logos-match-notas-fiscais-design.md` (e a base `2026-10-18-logos-match-design.md`).

**Fora desta fase (Fase 2, plano próprio):** registro de donos `donos.json` e checagem no LOGOS; CT-e pela SEFAZ; NFS-e pelo ADN; certificado A1 (DPAPI); reserva SEFAZ NF-e com ciência; detecção de cancelamento por evento SEFAZ; CT-e no parser.

## Global Constraints
- Diretório de trabalho: worktree `C:\Projetos\LOGOS\LogosPostos-match`, branch `feature/logos-match`; código Python em `WebPosto_API/`. Testes: `cd WebPosto_API && .venv/Scripts/python.exe -m pytest tests/unit/match tests/unit/fiscal_docs -q`.
- webPosto: **somente GET**. Rotas: `/INTEGRACAO/V1/NOTAS_MANIFESTACAO`, `/INTEGRACAO/V1/NOTAS_ENTRADA/XML/{chaveNfe}`, `/INTEGRACAO/V1/NOTAS_ENTRADA`. Paginação `ultimoCodigo`/`limite`; usar `src.modules.webposto_integration.http.paginar` para listas.
- A CHAVE webPosto nunca aparece em log, exceção, planilha ou tela (substituir por `***`).
- Fuso `America/Recife`; exibir `dd/mm/aaaa HH:mm`; competência = mês da emissão no fuso de Recife.
- Valores em `Decimal`, gravados como texto no SQLite.
- Arquivos fiscais nunca no repo; testes usam XMLs sintéticos/anonimizados em `tests/unit/fiscal_docs/dados/`.
- Pacote: `<CNPJ>_<AAAA-MM>.zip` com `xml/`, `pdf/` e `Resumo_<apelido>_<mm-aaaa>.xlsx`. E-mail: no máximo **20 MB** por mensagem.
- Envio padrão: dia **5**, **08:00**, competência = mês anterior. Captura diária **07:00**, retentativa de hora em hora só para notas `so_resumo`.
- Retenção de XML: 5 anos (não entra no `limpar_antigos` de 13 meses).
- Textos ao usuário em português simples (padrão `explicar.py`).
- Commits frequentes, testes verdes antes de cada commit; terminar mensagens com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus
1. **Nota listada no webPosto cuja rota de XML responde 404/vazio** → documento fica `so_resumo`, entra em Pendências e é tentado de novo; não pode derrubar a captura das outras notas (teste na Task 8).
2. **Erro HTTP do webPosto com a CHAVE no corpo/URL** → mensagem gravada e exibida sem a chave (teste na Task 3).
3. **NF-e emitida 31/10 23:30 -03:00** → competência outubro, não novembro (teste na Task 1 e na Task 10).
4. **Mesmo documento chegando duas vezes** (captura repetida, ou capturado e depois importado) → um registro só, sem duplicar no pacote (testes nas Tasks 8 e 13).
5. **PC desligado no dia 5, ou job mensal disparado duas vezes** → envia uma vez, no primeiro dia ≥ dia de envio em que o Match roda; nunca duas (teste na Task 11).

---

### Task 1: Modelos e parser de NF-e (`fiscal_docs`)

**Files:**
- Create: `WebPosto_API/src/modules/fiscal_docs/__init__.py`, `modelos.py`, `parser_nfe.py`
- Create: `WebPosto_API/tests/unit/fiscal_docs/__init__.py`, `dados/nfe_combustivel.xml` (nfeProc sintético: emitente distribuidora, 2 itens com `<comb><cProdANP>`, um com `ICMS61`/`vICMSMono`, `<transp>` modFrete=1 com transportadora, `<veicTransp>` placa/UF, `<vol>` qVol/pesoB, `protNFe` cStat 100, `dhEmi` `2026-10-31T23:30:00-03:00`), `dados/nfe_produto.xml` (sem comb, modFrete=9)
- Test: `WebPosto_API/tests/unit/fiscal_docs/test_parser_nfe.py`

**Interfaces:**
- Produces (`modelos.py`, Pydantic, `frozen=True`):
  - `TipoDoc = Literal["nfe", "nfse", "cte"]`; `Situacao = Literal["autorizada", "cancelada", "so_resumo"]`
  - `Item(n_item:int, codigo:str, descricao:str, ncm:str|None, cfop:str|None, cprod_anp:str|None, quantidade:Decimal, unidade:str, valor_unitario:Decimal, valor_total:Decimal, icms_mono:Decimal|None)`
  - `Transporte(mod_frete:str, mod_frete_texto:str, transportadora_cnpj:str|None, transportadora_nome:str|None, placa:str|None, uf_placa:str|None, volumes:Decimal|None, peso_bruto:Decimal|None)`
  - `Impostos(icms:Decimal, icms_st:Decimal, ipi:Decimal, iss:Decimal, retencoes:Decimal, frete:Decimal)` (zeros quando ausente)
  - `DocumentoFiscal(tipo:TipoDoc, chave:str, numero:str, serie:str|None, emissao_em:datetime (aware), competencia:str 'AAAA-MM', emitente_cnpj:str, emitente_nome:str, destinatario_cnpj:str|None, valor_total:Decimal, impostos:Impostos, situacao:Situacao, combustivel:bool, itens:tuple[Item,...]=(), transporte:Transporte|None=None, descricao_servico:str|None=None)`
  - `competencia_de(dt: datetime) -> str` (converte para America/Recife)
  - `class XmlInvalido(ValueError)`
- Produces (`parser_nfe.py`): `ler_nfe(xml: bytes) -> DocumentoFiscal`

- [ ] **Step 1: Write failing tests** — `test_combustivel_campos`: chave de 44 dígitos (de `infNFe/@Id` sem "NFe"), numero, serie, emitente, `valor_total == Decimal(vNF)`, `combustivel is True`, `itens[0].cprod_anp == "320102001"` (valor do XML), `itens[i].icms_mono` lido de `vICMSMono`; `transporte.mod_frete == "1"`, `mod_frete_texto == "FOB"` (mapa 0=CIF,1=FOB,2=Terceiros,3=Próprio rem.,4=Próprio dest.,9=Sem frete), placa/UF/volumes/peso. `test_competencia_fuso`: `competencia == "2026-10"`. `test_produto_sem_frete`: `combustivel is False`, `mod_frete_texto == "Sem frete"`. `test_xml_quebrado`: `pytest.raises(XmlInvalido)` para `b"<x>"` e para XML sem `infNFe`. `test_sem_protocolo`: XML `NFe` sem `nfeProc` → `situacao == "so_resumo"`.
- [ ] **Step 2: Run** `pytest tests/unit/fiscal_docs/test_parser_nfe.py -v` → FAIL (módulo inexistente).
- [ ] **Step 3: Implement** modelos e `ler_nfe` com `ElementTree` e namespace `http://www.portalfiscal.inf.br/nfe`; aceita raiz `nfeProc` ou `NFe`; `situacao="autorizada"` se `protNFe/infProt/cStat` ∈ {100, 150}.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(fiscal): modelos e parser de NF-e`.

### Task 2: Parser de NFS-e (padrão nacional)

**Files:**
- Create: `WebPosto_API/src/modules/fiscal_docs/parser_nfse.py`, `parser.py`
- Create: `tests/unit/fiscal_docs/dados/nfse_nacional.xml` (sintético, leiaute nacional `NFSe/infNFSe` com `DPS/infDPS`: prestador CNPJ/nome, tomador CNPJ, `xDescServ`, `vServ`, ISS `vISSQN`, retenções, `dhEmi`, chave em `infNFSe/@Id`)
- Test: `tests/unit/fiscal_docs/test_parser_nfse.py`

**Interfaces:**
- Produces: `ler_nfse(xml: bytes) -> DocumentoFiscal` (tipo `"nfse"`, `serie=None`, `combustivel=False`, `descricao_servico` preenchido, `impostos.iss`, `impostos.retencoes` = soma das retenções federais + ISS retido).
- Produces (`parser.py`): `ler(xml: bytes) -> DocumentoFiscal` — detecta pelo namespace/raiz (`nfeProc`/`NFe` → NF-e; `NFSe` nacional → NFS-e); outro leiaute → `XmlInvalido("Formato não reconhecido. Hoje o Logos Match lê NF-e e NFS-e do padrão nacional.")`.

- [ ] **Step 1: Failing tests** — `test_nfse_campos` (chave, emitente = prestador, `destinatario_cnpj` = tomador, `valor_total == vServ`, `impostos.iss`, `descricao_servico`); `test_detecta_tipo` (`ler` devolve tipo certo para os 3 XMLs de dados); `test_leiaute_municipal_recusado` (XML ABRASF `<CompNfse>` → `XmlInvalido` com a mensagem exata acima).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** com namespace `http://www.sped.fazenda.gov.br/nfse`; confira os caminhos do leiaute no manual vigente do gov.br/nfse antes de fixar.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(fiscal): parser de NFS-e nacional e detector de tipo`.

### Task 3: Leitura de notas no webPosto

**Files:**
- Create: `WebPosto_API/src/modules/fiscal_docs/webposto_notas.py`
- Test: `tests/unit/fiscal_docs/test_webposto_notas.py`

**Interfaces:**
- Consumes: `paginar(unidade, path, params, *, limite, client)` e `WebPostoErro` de `src.modules.webposto_integration.http`; `obter_segredo`.
- Produces:
  - `NotaListada(chave:str, emitente_cnpj:str, emitente_nome:str, emissao:date, valor:Decimal, tipo_produto:str|None, recebido:bool|None)` (Pydantic)
  - `EntradaWebposto(chave:str, tipo_frete:str|None, valor_frete:Decimal|None, placa:str|None, placa_reboque:str|None, cte_numero:str|None, cte_emissao:date|None)`
  - `async listar_notas(unidade, inicio: date, fim: date, *, client=None) -> list[NotaListada]` (GET `NOTAS_MANIFESTACAO` com `dataInicial/dataFinal/empresaCodigo`; descarta itens sem `chaveDocumento`)
  - `async baixar_xml(unidade, chave: str, *, client=None) -> bytes | None` (200 com `<` no início → bytes; 404, 204 ou corpo vazio → `None`; outro status → `WebPostoErro` sem a chave)
  - `async listar_entradas(unidade, inicio: date, fim: date, *, client=None) -> dict[str, EntradaWebposto]` (GET `NOTAS_ENTRADA`, `tipoData` omitido)

- [ ] **Step 1: Failing tests** com `httpx.MockTransport`: paginação em 2 páginas via `ultimoCodigo`; `baixar_xml` 200→bytes, 404→None, 500 com corpo contendo a chave → `WebPostoErro` cujo `str()` **não contém** a chave (Review Focus 2); `listar_entradas` mapeia `cteNumero` e `tipoFrete`. Unidade fake com `empresa_codigo=74014`, `chave_env="TESTE_CHAVE"` e `monkeypatch.setenv("TESTE_CHAVE","segredo123")`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(fiscal): leitura de NF-e no webPosto (somente GET)`.

### Task 4: Acervo de arquivos

**Files:**
- Create: `WebPosto_API/src/modules/fiscal_docs/acervo.py`
- Test: `tests/unit/fiscal_docs/test_acervo.py`

**Interfaces:**
- Produces:
  - `caminho_xml(base: Path, cnpj_empresa: str, doc: DocumentoFiscal) -> Path` = `base/<cnpj_empresa>/<AAAA-MM>/<tipo>/<chave>.xml` (CNPJ só dígitos da empresa que recebeu a nota)
  - `gravar(base: Path, cnpj_empresa: str, doc: DocumentoFiscal, xml: bytes, origem: str) -> Path` — escrita atômica (tmp + `os.replace`); se o arquivo já existe com o mesmo SHA-256, não regrava; acrescenta linha JSON em `base/<cnpj>/indice.jsonl` (`chave, tipo, emissao_em, emitente_cnpj, emitente_nome, valor_total, situacao, origem, sha256`) só quando gravou.
  - `ler_indice(base: Path, cnpj_empresa: str) -> list[dict]`

- [ ] **Step 1: Failing tests** — grava e lê; segunda gravação idêntica não duplica a linha do índice; caminho segue o padrão exato.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(fiscal): acervo de XML com índice`.

### Task 5: PDFs (DANFE, DANFSe, unir)

**Files:**
- Create: `WebPosto_API/src/modules/fiscal_docs/pdf.py`
- Modify: `WebPosto_API/requirements-match.txt` (+ `brazilfiscalreport`, `fpdf2`, `pypdf`, versões fixadas), `pyproject.toml` (mesmas deps)
- Test: `tests/unit/fiscal_docs/test_pdf.py`

**Interfaces:**
- Produces: `gerar_pdf(xml: bytes, doc: DocumentoFiscal) -> bytes` (NF-e → DANFE via `brazilfiscalreport`; NFS-e → DANFSe simples com fpdf2: cabeçalho "DANFSe — Documento auxiliar", prestador, tomador, número, emissão dd/mm/aaaa HH:mm, descrição, valor, ISS, retenções, chave); `unir(pdfs: list[bytes]) -> bytes` (pypdf).

- [ ] **Step 1: Failing tests** — `gerar_pdf` dos três XMLs de dados começa com `b"%PDF"`; `unir([a, b])` tem `len(PdfReader(...).pages) == pages(a)+pages(b)`.
- [ ] **Step 2:** instalar deps no `.venv` e rodar → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(fiscal): DANFE, DANFSe e união de PDFs`.

### Task 6: Migração v5 do banco do Match

**Files:**
- Modify: `WebPosto_API/apps/match/banco.py` (`_SCHEMA_V5`, `_MIGRACOES`)
- Create: `WebPosto_API/apps/match/fiscal/__init__.py`, `apps/match/fiscal/repositorio.py`
- Test: `tests/unit/match/test_fiscal_repositorio.py`, ajustar `tests/unit/match/test_banco.py` (versão 5)

**Interfaces:**
- `_SCHEMA_V5` cria (colunas da spec §5, só o necessário à Fase 1):
  - `empresa(id, cnpj UNIQUE, razao_social, apelido, municipio, uf, posto_id REFERENCES posto(id), ativo, criado_em)`
  - `escritorio(id, nome, emails_json, dia_envio INTEGER DEFAULT 5 CHECK 1..28, modo CHECK IN ('enviar','so_gerar'), pdf CHECK IN ('separados','unificado','ambos'), ativo)`; `escritorio_empresa(escritorio_id, empresa_id, PRIMARY KEY(...))`
  - `documento(id, empresa_id, tipo, chave UNIQUE, numero, serie, emissao_em, competencia, emitente_cnpj, emitente_nome, valor_total, impostos_json, situacao, origem CHECK IN ('webposto','sefaz','adn','importado'), combustivel, xml_path, xml_hash, capturado_em, cte_numero, frete_json)`; `documento_item(documento_id, n_item, ..., PRIMARY KEY(documento_id,n_item))`; `documento_transporte(documento_id PRIMARY KEY, ...)`
  - `captura(id, empresa_id, fonte, iniciada_em, terminada_em, situacao CHECK IN ('ok','erro'), qtd_novas, qtd_pendentes, erro_texto)`
  - `leitura_webposto(empresa_id PRIMARY KEY, ultima_data_lida TEXT)`
  - `pacote(id, empresa_id, competencia, complementar INTEGER DEFAULT 0, gerado_em, arquivos_json, situacao CHECK IN ('gerado','retido','aprovado','enviado','erro'), motivo_retencao, enviado_em, aprovado_por, UNIQUE(empresa_id, competencia, complementar, gerado_em))`
  - Recria `usuario` para aceitar perfil `'contabilidade'` (SQLite não altera CHECK: `PRAGMA foreign_keys=OFF` não vale dentro de `executescript` transacional — faça `CREATE TABLE usuario_novo ...; INSERT ... SELECT; DROP TABLE usuario; ALTER TABLE usuario_novo RENAME TO usuario;` e confirme que `usuario_posto`/`log_acesso` continuam íntegros com `PRAGMA foreign_key_check`).
- Produces (`repositorio.py`): `salvar_empresa(con, cnpj, razao_social, apelido, municipio, uf, posto_id) -> int`, `listar_empresas(con, ids: list[int] | None = None) -> list[Row]`, `salvar_escritorio(con, nome, emails: list[str], dia_envio, modo, pdf, empresas: list[int], escritorio_id: int | None = None) -> int`, `listar_escritorios(con) -> list[Row]`, `empresas_do_escritorio(con, escritorio_id) -> list[Row]`, `gravar_documento(con, empresa_id, doc: DocumentoFiscal, xml_path: Path, xml_hash: str, origem: str, entrada: EntradaWebposto | None = None) -> bool` (True se inseriu ou promoveu `so_resumo`→`autorizada`; False se já existia igual), `registrar_so_resumo(con, empresa_id, nota: NotaListada) -> bool`, `buscar_documentos(con, filtros: FiltroDocs) -> list[Row]` com `FiltroDocs(empresas:list[int], inicio:date|None, fim:date|None, fornecedor:str|None, tipo:str|None, situacao:str|None, combustivel:bool|None, valor_min:Decimal|None, valor_max:Decimal|None)` (fornecedor casa CNPJ só dígitos ou nome `LIKE`), `documentos_da_competencia(con, empresa_id, competencia) -> list[Row]`, `registrar_captura(...)`, `capturas_recentes(con, empresa_id, desde: datetime) -> list[Row]`, `salvar_pacote(...) -> int`, `pacotes(con, empresa_ids, competencia=None) -> list[Row]`, `atualizar_pacote(con, pacote_id, **campos)`.

- [ ] **Step 1: Failing tests** — banco novo chega à versão 5; banco v4 com 1 admin + `usuario_posto` migra preservando ambos e aceita criar usuário `contabilidade`; `gravar_documento` duas vezes com a mesma chave → segunda retorna False e há 1 linha (Review Focus 4); `so_resumo` seguido de documento completo → promove; `buscar_documentos` filtra por fornecedor "distrib" e por CNPJ com pontuação.
- [ ] **Step 2–4:** FAIL → implementar → PASS (`pytest tests/unit/match -q` inteiro verde).
- [ ] **Step 5: Commit** `feat(match): migração v5 do módulo fiscal e perfil contabilidade`.

### Task 7: Perfil Contabilidade e novas ações

**Files:**
- Modify: `WebPosto_API/apps/match/acesso.py`
- Test: `tests/unit/match/test_acesso.py`

**Interfaces:**
- `Perfil.CONTABILIDADE = "contabilidade"`; `Acao.VER_FISCAL`, `Acao.APROVAR_PACOTE`, `Acao.GERIR_FISCAL`.
- `_POR_POSTO`: gerente += `VER_FISCAL`; conferente sem fiscal; contabilidade = `{VER_FISCAL, APROVAR_PACOTE}`. `GERIR_FISCAL` (empresas, escritórios) só administrador. Escopo do contabilidade/gerente = empresas cujo `posto_id` ∈ postos do usuário. Produz `empresas_visiveis(con, usuario) -> list[int]`.
- Decisão minha (spec não fixou gerente/conferente): gerente vê notas dos seus postos; conferente não vê.

- [ ] **Step 1: Failing tests** — matriz: contabilidade não `COLETAR`/`CONFIGURAR`/`TROCAR_CREDENCIAL`; `VER_FISCAL` só nos seus postos; `empresas_visiveis` para admin = todas.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(match): perfil contabilidade`.

### Task 8: Captura diária de NF-e

**Files:**
- Create: `WebPosto_API/apps/match/fiscal/captura.py`
- Modify: `WebPosto_API/apps/match/caminhos.py` (+ `fiscal() -> Path`: `pasta_rede/fiscal` se configurada e acessível, senão `raiz()/fiscal`)
- Test: `tests/unit/match/test_fiscal_captura.py`

**Interfaces:**
- Consumes: Tasks 1–4, 6; `unidades.do_posto(con, posto)`, `coletas.tem_chave_webposto(con, posto)`, `registro_rede` (só capturar empresa cujo posto é desta máquina: mesmo critério que a coleta usa hoje).
- Produces:
  - `ResultadoCaptura(empresa_id:int, situacao:Literal["ok","erro","sem_chave"], novas:int, pendentes:int, mensagem:str)`
  - `async capturar_empresa(con, empresa_id: int, hoje: date, *, client=None) -> ResultadoCaptura` — janela: de `leitura_webposto.ultima_data_lida - 5 dias` (ou 1º dia do mês anterior na primeira vez) até `hoje`; `listar_notas` → para chave nova ou `so_resumo`: `baixar_xml`; `None` → `registrar_so_resumo`; bytes → `parser.ler` → `acervo.gravar(origem="webposto")` → `gravar_documento(..., entrada=entradas.get(chave))`; erro de uma nota não interrompe as outras; atualiza `leitura_webposto`; `registrar_captura`.
  - `capturar_todas(con_factory, hoje: date, *, so_pendentes: bool = False) -> list[ResultadoCaptura]` (síncrono; usa `asyncio.run`; trava com `rotina._TRAVA`-like lock próprio `_TRAVA_FISCAL`).

- [ ] **Step 1: Failing tests** (webPosto mockado): 3 notas listadas, uma com XML 404 → `novas==2`, `pendentes==1`, documento `so_resumo` existe (Review Focus 1); rodar de novo com o XML disponível → promove, `novas==1`; rodar de novo sem mudança → `novas==0` e acervo sem linha nova (Review Focus 4); empresa sem chave → `sem_chave` com mensagem "Cadastre a chave do webPosto do posto para capturar as notas."; erro 500 na listagem → `erro`, `captura.erro_texto` sem a chave.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(match): captura diária de NF-e pelo webPosto`.

### Task 9: Planilha resumo do mês

**Files:**
- Create: `WebPosto_API/apps/match/fiscal/planilha.py`
- Test: `tests/unit/match/test_fiscal_planilha.py`

**Interfaces:**
- Produces: `gerar_planilha(con, empresa_id: int, competencia: str, destino: Path) -> Path` com abas e colunas da spec §7:
  1. `Notas` (Data emissão, Tipo, Número, Série, Chave, Emitente CNPJ, Emitente, Valor total, ICMS, ICMS-ST, IPI, ISS, Retenções, Situação, Origem)
  2. `Combustível` (Data emissão, Nota, Distribuidora, Produto, Código ANP, Litros, Preço/litro, Valor, ICMS monofásico, Frete CIF/FOB, Transportadora CNPJ, Transportadora, Placa, UF placa, CT-e número, Valor frete) — CT-e número e valor vêm de `NOTAS_ENTRADA` (`cte_numero`, `frete_json`)
  3. `Fretes (CT-e)` — nesta fase lista os CT-e citados pelo webPosto (número, data, nota, valor do frete) com a observação "XML do CT-e chega na próxima versão"
  4. `Totais` (por fornecedor; por tipo; litros e valor por produto; frete total; canceladas)
  5. `Pendências` (só resumo; CT-e sem XML)
- Datas dd/mm/aaaa; valores numéricos com formato `#,##0.00`; litros `#,##0.000`.

- [ ] **Step 1: Failing tests** — gera a partir de 1 NF-e de combustível + 1 de produto + 1 NFS-e importada + 1 `so_resumo`; checa nomes das abas, cabeçalhos exatos, litros somados por produto e a linha na aba Pendências.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(match): planilha resumo fiscal do mês`.

### Task 10: Conferência e montagem do pacote

**Files:**
- Create: `WebPosto_API/apps/match/fiscal/conferencia.py`, `apps/match/fiscal/pacote.py`
- Test: `tests/unit/match/test_fiscal_pacote.py`

**Interfaces:**
- Produces (`conferencia.py`): `Achado(nivel:Literal["retem","aviso"], texto:str)`; `conferir(con, empresa_id, competencia, agora: datetime) -> list[Achado]`:
  - retém: captura com `erro` nos últimos 3 dias; documento `so_resumo` capturado há mais de 48 h; empresa sem chave webPosto;
  - aviso: CT-e citado sem XML; "NFS-e: nesta versão só entram as importadas manualmente".
- Produces (`pacote.py`): `montar(con, empresa_id, competencia, pdf_modo: Literal["separados","unificado","ambos"], destino: Path, *, complementar: bool = False, desde: datetime | None = None) -> list[Path]` — gera o zip `<CNPJ>_<AAAA-MM>.zip` (complementar: `<CNPJ>_<AAAA-MM>_complementar_<n>.zip` só com documentos capturados após `desde`); `xml/<chave>.xml`; `pdf/<chave>.pdf` e/ou `pdf/<CNPJ>_<AAAA-MM>_notas.pdf`; planilha da Task 9. Se o zip passar de 20 MB, divide em partes `_parte1..N` com no máximo 20 MB cada (a planilha vai na parte 1); retorna a lista de zips.

- [ ] **Step 1: Failing tests** — competência pela data em Recife (NF-e de 31/10 23:30 -03 entra em `2026-10`, Review Focus 3); `unificado` gera um único PDF dentro de `pdf/`; `ambos` gera os dois; conteúdo do zip lista exatamente os arquivos esperados; com limite monkeypatchado para 50 KB a saída vira várias partes ≤ limite; `conferir` retém com `so_resumo` de 3 dias e não retém com 1 dia.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(match): conferência e pacote mensal`.

### Task 11: Envio mensal aos escritórios

**Files:**
- Modify: `WebPosto_API/apps/match/canais/email_smtp.py` (+ `enviar_arquivos`)
- Create: `WebPosto_API/apps/match/fiscal/envio_mensal.py`
- Test: `tests/unit/match/test_fiscal_envio.py`

**Interfaces:**
- `email_smtp.enviar_arquivos(canal, destinatarios: list[str], assunto: str, texto: str, anexos: list[Path]) -> None` (anexo genérico `application/zip` / mimetype pelo sufixo; reaproveita a conexão SMTP já existente — extraia a parte comum de `enviar` sem mudar seu comportamento).
- `envio_mensal.rodar(con, hoje: date) -> list[dict]`: para cada escritório ativo com `hoje.day >= dia_envio`, para cada empresa: competência = mês anterior a `hoje`; se já existe pacote dessa competência com situação `enviado`/`gerado`(modo só gerar) → pula (Review Focus 5); senão `conferir` → se houver `retem` salva pacote `retido` com `motivo_retencao` (textos unidos) e avisa o administrador pelos canais; senão monta e (modo `enviar`) manda **uma mensagem por parte** com assunto `Notas fiscais <apelido> — <mm/aaaa> (parte i/N)` usando o primeiro canal de e-mail ativo; marca `enviado`. Sem canal de e-mail ativo → situação `erro`, motivo "Cadastre um canal de e-mail em Canais para enviar à contabilidade.".
- `aprovar_e_enviar(con, pacote_id, usuario_id) -> None` (ignora retenção, grava `aprovado_por`, registra em `log_acesso`).
- `reenviar(con, pacote_id, usuario_id) -> None`.
- `enviar_complementares(con, agora) -> list[dict]`: documentos de competência já enviada e capturados depois do `enviado_em` → pacote complementar enviado (modo enviar).

- [ ] **Step 1: Failing tests** (SMTP mockado com `monkeypatch` em `smtplib.SMTP`): dia 4 não envia; dia 5 envia uma vez; segunda chamada no dia 5 e chamada no dia 6 não reenviam; PC "desligado" no dia 5 → chamada no dia 7 envia (Review Focus 5); retido não envia e grava motivo; `aprovar_e_enviar` envia o retido; nota capturada depois do envio vira complementar.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(match): envio mensal à contabilidade`.

### Task 12: Agendamento

**Files:**
- Modify: `WebPosto_API/apps/match/agendador.py`
- Test: `tests/unit/match/test_rotina.py` (ou novo `test_fiscal_agenda.py`)

**Interfaces:**
- Jobs novos com `_OPCOES`: `fiscal_captura` cron 07:00 → `captura.capturar_todas(con_factory, hoje)`; `fiscal_pendentes` a cada hora (minuto 30, das 08:00 às 20:00) → `capturar_todas(..., so_pendentes=True)` + `envio_mensal.enviar_complementares`; `fiscal_mensal` cron 08:00 → `envio_mensal.rodar`. Na inicialização, se o Match subir depois das 08:00, rodar `envio_mensal.rodar` uma vez em segundo plano (mesma ideia da recuperação existente).
- Erros nos jobs fiscais nunca derrubam os jobs de coleta (try/except com log e aviso).

- [ ] **Step 1: Failing test** — `reagendar` registra os 3 ids; exceção dentro do job fiscal é capturada.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(match): agenda do módulo fiscal`.

### Task 13: Telas do painel

**Files:**
- Modify: `WebPosto_API/apps/match/painel/rotas.py` (rotas novas e `_menu`)
- Create: `apps/match/painel/templates/fiscal_notas.html`, `fiscal_empresas.html`, `fiscal_escritorios.html`, `fiscal_pacotes.html`, `fiscal_importar.html`
- Test: `tests/unit/match/test_painel_fiscal.py`

**Interfaces / rotas** (todas com `_ctx`/`_ctx_post`, CSRF e `ctx.exigir`):
- `GET /notas` (VER_FISCAL): filtros da spec (período, empresa, fornecedor, tipo, situação, combustível, valor), tabela com totais; `GET /notas/xml?ids=` (zip de XMLs), `GET /notas/pdf?ids=&modo=separados|unificado` (zip ou PDF único), `GET /notas/planilha?empresa_id=&competencia=`.
- `GET|POST /empresas` (GERIR_FISCAL): cadastro com posto vinculado (escolha entre postos do Match; CNPJ pré-preenchido do posto), última captura e erro; botão "Capturar agora" (em segundo plano, padrão `_em_segundo_plano`).
- `GET|POST /escritorios` (GERIR_FISCAL): nome, e-mails (separados por vírgula, validados), empresas, dia (1–28), modo, PDFs.
- `GET /pacotes` (VER_FISCAL): por competência/empresa com situação e motivo; `POST /pacotes/{id}/aprovar` (APROVAR_PACOTE), `POST /pacotes/{id}/reenviar` (APROVAR_PACOTE), `GET /pacotes/{id}/baixar`.
- `GET|POST /importar` (VER_FISCAL na empresa escolhida): upload de `.xml` ou `.zip` (máx. 50 MB, no máx. 2.000 arquivos, ignora caminhos com `..`), `parser.ler` → acervo (origem `importado`) → `gravar_documento`; resposta: "X notas importadas, Y já existiam, Z não reconhecidas" com o nome dos arquivos recusados. O CNPJ destinatário/tomador precisa ser o da empresa escolhida; senão recusa o arquivo com explicação.
- `_menu`: "Notas fiscais" e "Pacotes" para quem tem VER_FISCAL; "Empresas" e "Escritórios" para GERIR_FISCAL; perfil contabilidade vê **só** Notas fiscais e Pacotes (sem Hoje/Coleta/Histórico).
- Datas exibidas com os filtros `_data`/`_data_hora` existentes.

- [ ] **Step 1: Failing tests** (TestClient, padrão de `test_painel.py`): contabilidade recebe 403 em `/postos` e vê só as empresas do seu escopo em `/notas`; filtro por fornecedor funciona; importar o mesmo XML duas vezes → segunda resposta "0 notas importadas, 1 já existia" (Review Focus 4); zip com `../x.xml` é ignorado; XML de outro CNPJ é recusado.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(match): telas de notas fiscais, empresas, escritórios, pacotes e importação`.

### Task 14: Empacotamento, versão e documentação

**Files:**
- Modify: `WebPosto_API/apps/match/__init__.py` (`VERSAO = "0.3.0"`), `apps/match/build/instalador.iss` (`#define Versao "0.3.0"`), `apps/match/build/match.spec` (hiddenimports `src.modules.fiscal_docs`, `brazilfiscalreport`, `fpdf`, `pypdf`; datas de fontes/recursos que o `brazilfiscalreport` usar), `apps/match/README.md` (seção "Notas fiscais"), `STATUS.md` (topo: Fase 1 entregue e o que fica para a Fase 2)

- [ ] **Step 1:** Rodar a suíte inteira: `.venv/Scripts/python.exe -m pytest tests/unit/match tests/unit/fiscal_docs tests/unit/cash_reconciliation -q` → tudo verde.
- [ ] **Step 2:** Gerar o build: `powershell -File apps/match/build/build.ps1` → `dist/LogosMatch-Setup-0.3.0.exe` criado; abrir o exe da pasta `dist` e gerar um DANFE pelo painel (importar `tests/unit/fiscal_docs/dados/nfe_combustivel.xml` numa empresa de teste) para provar que o PDF funciona empacotado.
- [ ] **Step 3: Smoke real (somente GET, com o diretor):** cadastrar a empresa Doze Filial II (posto 74014) e um escritório de teste com o e-mail do próprio diretor, modo `enviar`; "Capturar agora"; conferir em `/notas` as NF-e de setembro/2026 e baixar o pacote de setembro; comparar a contagem com `NOTAS_MANIFESTACAO` do mesmo período (validação pedida na spec §3).
- [ ] **Step 4: Commit** `chore(match): versão 0.3.0 com módulo de notas fiscais`.
