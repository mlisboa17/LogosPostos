# STATUS — LOGOS Auditoria (atualizado em 23/10/2026)

Repositório canônico: C:\Projetos\LOGOS\LogosPostos · branch feature/cash-audit-fechamento
Última entrega de código: Sprint 19 (A–D) · branch feature/cash-audit-fechamento, sem merge
PR a abrir: https://github.com/mlisboa17/LogosPostos/pull/new/feature/cash-audit-fechamento
Histórico de sprints: um prompt por sprint em docs/prompts/ (SPRINT_05 ... SPRINT_12, PREMMIA_00, TELEGRAM_00)

# PLANOS-CONTA-MASTER-01 — Catálogo Compartilhado Completo — 23/10/2026

- Mapeamento oficial somente leitura concluído: 251 planos gerenciais compartilhados por todas as empresas.
- Estrutura reconstruída: 28 contas pai e 223 folhas estruturais candidatas a lançamento.
- Catálogo local anterior possuía 200 códigos; 51 oficiais estavam ausentes.
- Regra consolidada: contas pai não podem ser usadas diretamente em `MOVIMENTOS_CONTA`.
- Hierarquia correta do caso: `29021 PRO LABORE` → `148303 MARCIO LISBOA` → `158764 MARCIO-PROLABORE`.
- `158764` é folha oficial e candidata exata para o lançamento de Pró-labore Márcio; nenhuma nova escrita foi autorizada ou executada.
- Endpoint contábil respondeu HTTP 200 com zero registros; o gerencial atende o fluxo de movimentos.
- Catálogo SHA-256: `BDF68D4F690249A70B69424C0B9FA237C09704FE8D6EF258E37DABC1D0CD8C57`.
- Evidências: [PLANOS_CONTA_MASTER_01.md](docs/validation/PLANOS_CONTA_MASTER_01.md) e [PLANOS_CONTA_MASTER_01_CHECKPOINT.md](docs/checkpoints/PLANOS_CONTA_MASTER_01_CHECKPOINT.md).

# ERP-WRITE-01 — Tentativa Rejeitada por Plano Pai — 23/10/2026

- Proprietário autorizou uma única saída na Casa Caiada: conta `27173`, R$ 626,00, 10/10/2026, `PRÓ-LABORE — MÁRCIO`, plano `29021`, centro `7295`, sem fornecedor.
- Pré-checagem ERP e idempotência local: zero duplicatas.
- Uma única tentativa de POST foi recusada pelo webPosto com HTTP 400: `29021 — PRO LABORE` é conta pai e o ERP exige conta filha.
- Nenhum movimento foi criado; confirmação posterior retornou zero correspondências.
- Sem retry. Token consumido. Liberação efêmera removida e allowlist restaurada para `{17837}`.
- Catálogo local não contém plano filho comprovado; permanece bloqueado até consulta/indicação oficial.
- Evidência: [ERP_WRITE_01_REJECTED_PARENT_PLAN.md](docs/checkpoints/ERP_WRITE_01_REJECTED_PARENT_PLAN.md).

# ACCOUNTING-REVIEW-02 — Decisão do Proprietário sobre Pró-Labore — 23/10/2026

- Proprietário determinou: lançar exclusivamente na `AP CASA CAIADA (5555)` como saída da conta `27173`, plano `29021 — PRO LABORE`, histórico `PRÓ-LABORE — MÁRCIO`.
- Movimento não pertence ao Posto Real e não pede fornecedor.
- `Posto Real Ltda` permanece apenas como evidência bancária histórica e foi removido dos campos do lançamento proposto.
- Contrato OpenAPI permite `centroCusto: null` e `pessoa: null`; nenhum centro administrativo foi inventado.
- Proposta usa `tipoPessoa: NAO_IDENTIFICADO`, sem fornecedor.
- Débito permanece desabilitado, conta fora da allowlist, zero chamadas e zero escritas ERP.
- Evidência: [ACCOUNTING_REVIEW_02_OWNER_DECISION.md](docs/checkpoints/ACCOUNTING_REVIEW_02_OWNER_DECISION.md).

# ACCOUNTING-REVIEW-01 — Auditoria de Pendência Contábil e Matriz de Alternativas — 23/10/2026

- Auditoria cadastral SQLite concluída em modo somente leitura: conta `27173` confirmada como `CONTA_CORRENTE`, empresa `5555`, banco `001`, agência `2365-5`, conta `56816-3`, confiabilidade `CONFIRMADO` e `permite_debito_despesa = 0`.
- Auditoria append-only confirmada: `audit_id 235`, origem `AUTORIZACAO_EXPRESSA_PROPRIETARIO_MASTER_DATA_07`.
- Barreira de código confirmada: conta `27173` permanece fora de `CONTAS_AUTORIZADAS_POR_UNIDADE[5555]` (apenas `{17837}`).
- Simulação offline do piloto de R$ 626,00 validada sintaticamente e por hash SHA-256 (`FF1B396B...`).
- 141 testes offline executados e aprovados (**141 passed**): Master Data, preparação de piloto, precheck, adaptador de escrita e Telegram.
- Diagnóstico contábil detalhado:
  - Divergência de personalidade jurídica: saída bancária em favor de PJ (`Posto Real Ltda`, CNPJ `08.106.946/0001-09`) confrontada com finalidade informada de pró-labore de PF (`Márcio`).
  - Incompatibilidade de centro de custo: plano `29021 — PRO LABORE` é terminantemente bloqueado pelo LOGOS com centro de custo operacional `7295 — PISTA` (`master_data_service.py` L1106).
  - Matriz de 4 alternativas objetivas produzida: 1) Pró-labore; 2) Adiantamento a sócio; 3) Mútuo interempresas; 4) Outra classificação contábil (ressarcimento/lucros).
- Piloto mantido estritamente como `BLOCKED_ACCOUNTING_REVIEW`.
- Zero chamadas externas ao ERP, zero escrita e zero alteração de travas.
- Evidência: [ACCOUNTING_REVIEW_01_CHECKPOINT.md](docs/checkpoints/ACCOUNTING_REVIEW_01_CHECKPOINT.md).

# MASTER-DATA-07 — Reclassificação Local e Simulação Offline — 23/10/2026

- Reclassificação autorizada executada somente no SQLite local: conta `27173` agora é `CONTA_CORRENTE` da empresa `5555`.
- Banco `001`, agência `2365-5`, conta `56816-3`, confiabilidade `CONFIRMADO`.
- Débito real permanece desabilitado (`permite_debito_despesa = 0`).
- Conta `27173` não foi adicionada à allowlist de escrita.
- Trilha append-only registrada como `audit_id 235`; backup local criado antes da alteração.
- Simulação offline do piloto de R$ 626,00 preparada com o código `27173`; nenhum payload foi transmitido.
- Piloto permanece `BLOCKED_ACCOUNTING_REVIEW` pela divergência entre recebedor PJ (`Posto Real Ltda`) e finalidade de pró-labore PF (`Márcio`), além da exigência de reconfirmar duplicidade antes de eventual escrita.
- Zero chamadas externas, zero escrita ERP e zero alteração de travas `.env`.
- Evidências: [MASTER_DATA_07_LOCAL_RECLASSIFICATION_AND_PILOT_SIMULATION.md](docs/validation/MASTER_DATA_07_LOCAL_RECLASSIFICATION_AND_PILOT_SIMULATION.md) e [MASTER_DATA_07_CHECKPOINT.md](docs/checkpoints/MASTER_DATA_07_CHECKPOINT.md).

# MASTER-DATA-06 — Conferência Visual da Conta 27173 — 23/10/2026

- Três capturas do Cadastro de Conta do webPosto foram confrontadas com as evidências oficiais já registradas.
- Confirmados visualmente: Banco do Brasil `001`, conta `56816-3`, conta ativa e bancária, cedente/CNPJ compatível e vínculo exclusivo visível com `AP CASA CAIADA`.
- A agência aparece como `2365`; o dígito `5` não é exibido na tela e continua sustentado pelos documentos bancários locais.
- Os códigos ERP `27173` e empresa `5555` não aparecem nas telas; são sustentados pelo retorno oficial sanitizado anteriormente registrado.
- As imagens não foram copiadas para o Git porque mostram saldo financeiro; hashes SHA-256 foram registrados para integridade.
- **ACCOUNT 27173:** `BLOCKED / READY_FOR_HUMAN_DECISION`.
- **CASA CAIADA PILOT:** `BLOCKED`.
- Conferência SQLite somente leitura: conta ainda `TRANSITORIA`, sem empresa persistida e com débito desabilitado.
- Zero reclassificação, lançamento, chamadas externas ou escritas ERP.
- Evidências: [MASTER_DATA_06_VISUAL_ACCOUNT_27173.md](docs/validation/MASTER_DATA_06_VISUAL_ACCOUNT_27173.md) e [MASTER_DATA_06_CHECKPOINT.md](docs/checkpoints/MASTER_DATA_06_CHECKPOINT.md).

# TECH-DEBT-03 — Limpeza Autorizada e Quarentena Premmia — 22/10/2026

- Proprietário autorizou a remoção dos dois arquivos históricos `*-mlisboa17.py` e dos quatro scripts `scratch_*.py`.
- `probe_premmia_portal.py` foi movido para `WebPosto_API/tools/premmia/quarantine/` e não foi executado.
- A quarentena proíbe integração automática e exige autorização específica para eventual uso futuro.
- Compilação global de `WebPosto_API/src`: aprovada após a remoção dos arquivos corrompidos.
- Master data + autenticação + cash reconciliation: **737 passed**; zero tentativas reais de portal.
- Para a conta `27173`, o proprietário exige primeiro conferência visual da agência `2365-5` no webPosto.
- Reclassificação da conta e piloto Casa Caiada continuam não autorizados e `BLOCKED`.
- Push da branch autorizado, sem merge.
- Evidência: [TECH_DEBT_03_CLEANUP_CHECKPOINT.md](docs/checkpoints/TECH_DEBT_03_CLEANUP_CHECKPOINT.md).

# TECH-DEBT-02 — Modernização Pydantic e JWT — 22/10/2026

- Migrados validadores de clientes para `@field_validator` do Pydantic v2.
- Migradas configurações para `ConfigDict` e `SettingsConfigDict`.
- Timestamps JWT agora usam UTC consciente de fuso (`datetime.now(timezone.utc)`).
- Validação focada: **16 passed**.
- Cash reconciliation completo: **672 passed**, inicialmente com redução de **151 para 92 warnings**.
- Após isolar uma chave JWT exclusiva de testes: autenticação + cash reconciliation **681 passed, zero warnings**.
- Segredos, `.env` e configurações produtivas não foram lidos nem alterados.
- Conta `27173`, piloto Casa Caiada e cadeia Mais permanecem `BLOCKED`.
- Zero chamadas externas, escritas ERP, tokens de piloto, push ou merge.
- Evidências: [TECH_DEBT_02_PYDANTIC_JWT_MODERNIZATION.md](docs/validation/TECH_DEBT_02_PYDANTIC_JWT_MODERNIZATION.md) e [TECH_DEBT_02_CHECKPOINT.md](docs/checkpoints/TECH_DEBT_02_CHECKPOINT.md).

# TECH-DEBT-01 — Auditoria de Scripts e Arquivos Históricos — 22/10/2026

## Resultado da Auditoria

- **AUDITORIA CONCLUÍDA EM MODO READ-ONLY OFFLINE.**
- **Cinco Scripts Não Rastreados em `WebPosto_API/scripts/`:**
  - `probe_premmia_portal.py`: Automação Playwright para portal Premmia/Vibra da filial VIP (11495) e leitura ERP webPosto. Risco alto de bloqueio de conta e CAPTCHA. Classificado como **ARQUIVAR / QUARENTENA**. Permanece não rastreado e sem execução.
  - Quatro scripts `scratch_*` (`scratch_audit_p0.py`, `scratch_check_probe_raw.py`, `scratch_probe.py`, `scratch_probe_endpoints.py`): Utilitários estáticos de leitura local de arquivos JSON/TXT já superados. Zero chamadas externas e zero credenciais. Classificados como **CANDIDATOS A DESCARTE**.
- **Dois Arquivos Históricos `-mlisboa17.py` em `WebPosto_API/src/`:**
  - `dependencies-mlisboa17.py` e `main-mlisboa17.py`: Diagnosticados como cópias residuais de conflito de sincronização de arquivo / rascunhos interrompidos. Ambos possuem erros fatais de sintaxe (`SyntaxError`) e zero importações no projeto.
  - Arquivos canônicos correspondentes (`dependencies.py` e `main.py`): Compilam com `py_compile` (exit code 0), importam limpo e sustentam rotas e testes unitários.
  - Nenhum arquivo histórico foi alterado, renomeado ou removido nesta etapa.
- **ACCOUNT 27173:** Permanece `TRANSITORIA` e `BLOCKED`.
- **Piloto Casa Caiada:** Permanece `BLOCKED`.
- **Cadeia Mais Pagamentos:** Permanece `BLOCKED`.
- **Zero chamadas externas; zero escritas no ERP webPosto.**

## Riscos Identificados

1. **Risco de Execução Acidental de Automação de Portal:** O script `probe_premmia_portal.py` aciona navegador interativo e consome credenciais de ambiente, com risco severo de bloqueio de conta Premmia em caso de execução não supervisionada.
2. **Falha de `compileall` Global por Arquivos Truncados:** O comando `compileall` global continuará falhando enquanto os arquivos truncados `-mlisboa17.py` permanecerem no repositório.

## Requisitos Pendentes

- **P0:** Deliberação formal do diretor sobre a conta `27173` (Casa Caiada BB) e obtenção de pacote documental real do Posto Doze (74014).
- **P1:** Autorização para arquivamento ou descarte formal dos quatro scripts `scratch_*` e quarentena de `probe_premmia_portal.py`.
- **P2:** Remoção autorizada dos dois arquivos mortos `-mlisboa17.py` para restauração do `compileall` global limpo.

## Comandos e Testes Offline Executados

- `python -m py_compile WebPosto_API/src/main.py WebPosto_API/src/interfaces/http/dependencies.py`: **100% OK (Exit code 0)**.
- `python -c "import sys; sys.path.insert(0, 'WebPosto_API'); from src.interfaces.http.dependencies import get_current_user, get_db; print('Dependencies OK')"`: **100% OK**.
- `python -c "import sys; sys.path.insert(0, 'WebPosto_API'); from src.main import app; print('App OK')"`: **100% OK**.
- `python -m pytest WebPosto_API/tests/unit/cash_reconciliation/test_piloto_cartao.py -q --no-cov`: **48 passed, 7 warnings** (0 tentativas de portal/rede).

# MAIS-BANK-05 — Consolidação Documental de Liquidação e Repasses — 22/10/2026

## Resultado da Revisão

- **CONSOLIDAÇÃO CONCLUÍDA EM MODO READ-ONLY OFFLINE.**
- **Cadeia Mais Pagamentos: BLOCKED** para todas as unidades por ausência de comprovação documental ponta a ponta.
- **Escopo Confirmado:** Posto Doze (`74014`), Posto VIP (`11495`, incluindo sua própria loja) e Casa Caiada (`5555`).
- **Conveniência 24h (`118508`): FORA DO ESCOPO** Mais Pagamentos (confirmado expressamente pelo proprietário). Nenhuma associação a Asaas, Fiserv ou Matera se aplica.
- **Matera:** Presente no ecossistema de pagamentos como tecnologia BaaS/infraestrutura, sem nenhuma associação operacional comprovada a qualquer filial do grupo.
- **Modelo de Conservação de Saldo:** Formalizada a fungibilidade de saldos em contas intermediárias. A métrica `PIX do dia - repasses do dia` NÃO mede perda financeira sem extrato analítico oficial do período.
- **Conta 27173 (Casa Caiada):** Permanece `TRANSITORIA`, com débito desabilitado.
- **Piloto Casa Caiada:** Permanece estritamente `BLOCKED`.
- **Zero chamadas externas; zero escritas no ERP webPosto.**

## Riscos Identificados

1. **Falsas Divergências de Caixa:** Tratar a defasagem temporal entre capturas de PIX e repasses agregados como falta de numerário, ignorando a fungibilidade de saldos intermediários.
2. **Contaminação Inter-Filiais:** Repassar valores de uma filial para conta de outra filial sem contrato formal de mútuo.
3. **Contaminação com Sangria da Pista:** Utilizar contas bancárias de cofre físico de espécie da pista para recebimento de adquirentes eletrônicos sem contraparte comprovada.
4. **Travas não universais em SDK genérico:** Necessidade de manter estrito isolamento offline para evitar que métodos genéricos do SDK sem decorators executem chamadas externas.

## Requisitos Pendentes

- **P0:** Obtenção de pacote documental real e sanitizado do Posto Doze (`74014`) de 14 a 16/10/2026: extrato analítico Asaas completo + comprovante de repasse com taxa + extrato bancário final do crédito.
- **P0:** Deliberação formal do diretor sobre a aceitação da descrição textual `"BANCO DO BRASIL (56816-3)"` para a conta `27173` ou conferência visual em tela.
- **P1:** Identificação cadastral oficial dos custodiantes e contas de VIP e Casa Caiada junto à Quality/Fiserv.
- **P1:** Obtenção de credencial de integração formal somente leitura (`GET`) junto à Quality/Mais Pagamentos.
- **P2:** Saneamento técnico dos arquivos legados corrompidos (`src/interfaces/http/dependencies-mlisboa17.py` e `src/main-mlisboa17.py`) e dos avisos de depreciação.

## Comandos e Testes Offline Executados

- `python -m pytest WebPosto_API/tests/unit/master_data -q --no-cov`: **56 passed** (0 tentativas de navegador/portal).
- `python -m pytest WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_pilot_prep_bb.py WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_despesa.py -q --no-cov`: **61 passed** (0 tentativas de navegador/portal).
- `python -m pytest WebPosto_API/tests/unit/cash_reconciliation/ -q --no-cov`: **672 passed, 151 warnings** (0 tentativas de navegador/portal).
- `git diff --check`: 0 erros de formatação ou whitespace encontrados.

# SPRINT 1 CODEX — Saneamento e Baseline Offline — 22/10/2026

## Resultado

- **SPRINT 1: CONCLUÍDA NO ESCOPO OFFLINE SEGURO.**
- Conta `27173` permanece `TRANSITORIA`, com débito desabilitado.
- Piloto Casa Caiada permanece `BLOCKED`.
- Nenhuma chamada ERP, escrita ERP, reclassificação, lançamento, merge, reset ou clean foi executado.

## Classificação dos 24 arquivos inicialmente não rastreados

1. **Implementação e testes EXPENSE (6 arquivos, manter):** adaptadores `telegram_despesas.py` e `webposto_escrita_despesa.py`; quatro suítes `test_expense_04_*`, `test_telegram_despesas.py` e `test_webposto_escrita_despesa.py`. Conjunto integrado às alterações rastreadas do fluxo de comprovantes e validado offline.
2. **Arquitetura e evidências EXPENSE (9 arquivos, manter):** `ARCH_MODULE_01_CURRENT_STRUCTURE.md` e oito relatórios `EXPENSE_*`. Documentação vinculada ao fluxo testado, sem autorização operacional.
3. **Evidências MAIS BANK (4 arquivos, manter separado):** `MAIS_BANK_01` a `MAIS_BANK_04`. Outro fluxo de trabalho; não foi misturado ao baseline Expense.
4. **Ferramentas de investigação (5 arquivos, não integrar nesta sprint):** `probe_premmia_portal.py` e quatro scripts `scratch_*`. Podem realizar investigação externa ou são descartáveis; permaneceram sem execução e fora dos commits da Sprint 1.

## Revisão de segurança e correção P0

A revisão encontrou comportamento fail-open quando a whitelist Telegram estava vazia. Mensagens comuns e callbacks de aprovação poderiam ser aceitos sem um diretor integralmente configurado. A correção aplicada torna os dois caminhos fail-closed:

- o listener rejeita qualquer atualização se `TELEGRAM_CHAT_IDS` estiver vazio;
- callbacks de despesas exigem conjuntos não vazios de chat e usuário autorizado;
- foram adicionados testes de regressão para configuração vazia;
- nenhum callback ou mensagem de teste acessou Telegram real.

## Baseline validado

- Master data: **56 passed**.
- Fluxos focados de piloto/escrita: **61 passed**.
- Comprovantes e autenticação Telegram após o P0: **54 passed**.
- Suíte completa `tests/unit/cash_reconciliation`: **672 passed**, **151 warnings**, zero tentativa real de navegador/portal.
- `git diff --check` do conjunto funcional: sem erro de whitespace; apenas avisos de futura conversão LF/CRLF. Documentos históricos preservam quebras Markdown com dois espaços finais.

## Débitos conhecidos preservados

- `src/interfaces/http/dependencies-mlisboa17.py` e `src/main-mlisboa17.py` já estavam versionados com erro de sintaxe; por isso `compileall` global ainda falha. Eles não pertencem ao conjunto alterado da Sprint 1 e permanecem P2 para decisão de remoção ou reparo.
- Há avisos de Pydantic v1, `datetime.utcnow()` e chave JWT curta usada nos testes. Não impedem o baseline, mas devem ser tratados em sprint técnica.
- Scripts de probe/scratch não foram apagados nem executados.

## Organização de commits

- Commit funcional: fluxo Expense, barreiras fail-closed e testes offline.
- Commit documental: arquitetura, evidências EXPENSE e atualização do `STATUS.md`.
- Evidências MAIS BANK e scripts de investigação permanecem separados para revisão própria.

# CONTINUIDADE CODEX — Auditoria Offline e Estado Atual — 22/10/2026

## Veredito executivo

- **Branch validada:** `feature/cash-audit-fechamento`.
- **HEAD auditado:** `539f8e4980de027657da495ffe0d68fd1338d780` (`MASTER-DATA-05`).
- **Checkpoint solicitado:** `3e1c2f814afd94e0d1e2fbb65d9652e0f77e7b1` (`MASTER-DATA-04`) existe e é ancestral do HEAD.
- **MASTER-DATA-03:** íntegro no estado atual; suíte `tests/unit/master_data` com **56/56 testes aprovados**.
- **ACCOUNT 27173: BLOCKED.** Nenhuma reclassificação foi executada.
- **CASA CAIADA PILOT: BLOCKED.** Nenhum lançamento ou chamada ERP foi executado.

## Evidência local da conta 27173

Consulta somente leitura ao arquivo local `WebPosto_API/data/master_data/master_data.sqlite3`:

- `empresa_codigo = null`;
- `descricao = "CONTA TRANSITORIA 27173"`;
- `tipo_conta = "TRANSITORIA"`;
- `banco_codigo`, `agencia` e `conta_numero` ausentes;
- `permite_debito_despesa = false`;
- `confiabilidade = "HISTORICO"` e `origem_dado = "webposto_probe"`;
- trilha `master_data_audit_log`: uma única `INSERCAO` de bootstrap, sem reclassificação posterior.

Confronto de evidências: o retorno sanitizado do MASTER-DATA-04 associa `empresaCodigo 5555`, `contaCodigo 27173`, descrição `BANCO DO BRASIL (56816-3)` e conta ativa. Extrato local e documentação apontam banco 001, agência 2365-5, conta 56816-3, titular Casa Caiada e CNPJ 04.284.939/0001-86. Entretanto, agência, titular e CNPJ não são campos estruturados do retorno ERP preservado. A união dessas fontes é forte para revisão humana, mas insuficiente para uma reclassificação automática sob a regra anti-inferência vigente.

## Árvore de trabalho preservada

Na fotografia inicial da auditoria havia 8 arquivos rastreados modificados e 24 arquivos não rastreados, concentrados no fluxo de comprovantes/despesas, adaptadores, testes e documentação. Nenhum `reset`, `clean`, merge ou descarte foi realizado. O arquivo `WebPosto_API/tests/conftest.py`, que já estava modificado, recebeu uma adaptação de isolamento: cada execução usa um diretório temporário exclusivo, evitando reaproveitar bancos SQLite de idempotência de execuções anteriores. A organização posterior está registrada na seção da Sprint 1 acima.

## Validação offline reproduzível

- `python -m pytest tests/unit/master_data -q` em `WebPosto_API`: **56 passed**; zero tentativa real de portal; há avisos de conexões SQLite não fechadas e dois arquivos Python legados não parseáveis pela cobertura.
- `python -m pytest WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_pilot_prep_bb.py WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_despesa.py -q --no-cov` na raiz: **61 passed**; zero tentativa real de navegador/portal.
- A primeira execução combinada expôs reuso de estado SQLite no fixture e dependência do diretório de execução. Após a adaptação do fixture e execução a partir da raiz, todos os testes funcionais passaram. O `--no-cov` evita aplicar a esta suíte isolada o limiar global de cobertura do projeto pai; não oculta falhas funcionais.

## Priorização

- **P0 — manter fail-closed:** preservar `27173` como `TRANSITORIA`, débito desabilitado e piloto Casa Caiada `BLOCKED`; proibir escrita ERP, lançamento e reclassificação até decisão humana específica apoiada por validação visual ou aceite formal da suficiência documental.
- **P0 — sanidade da árvore:** revisar e separar as alterações locais anteriores antes de qualquer commit, porque o conjunto mistura implementação, scripts de probe, documentação e testes ainda não rastreados.
- **P1 — robustez offline:** eliminar os avisos de conexões SQLite não fechadas e tornar caminhos de testes independentes do diretório de execução; manter bloqueio explícito de transporte externo nas suítes.
- **P1 — evidência estruturada:** preparar, sem persistir, uma matriz de decisão assinável com os seis atributos da conta e hashes/referências dos documentos locais; a decisão continua humana.
- **P2 — higiene técnica:** corrigir os dois arquivos legados não parseáveis pela cobertura e racionalizar scripts `scratch/probe`, sem executar chamadas externas.

## Limites mantidos nesta continuidade

Não foram executadas chamadas ERP, escritas ERP, reclassificação da conta, lançamento de despesa, `git reset`, `git clean` ou merge. A próxima transição continua dependendo de autorização específica e não é implícita nesta auditoria.

## MASTER-DATA-05 — Bank Account Identity Evidence Review (Casa Caiada) — 22/10/2026 13:40

Relatórios detalhados:
- [MASTER_DATA_05_ACCOUNT_EVIDENCE.md](MASTER_DATA_05_ACCOUNT_EVIDENCE.md)
- [MASTER_DATA_05_RECLASSIFICATION_IMPACT.md](MASTER_DATA_05_RECLASSIFICATION_IMPACT.md)
- [MASTER_DATA_05_CHECKPOINT.md](docs/checkpoints/MASTER_DATA_05_CHECKPOINT.md)
- [MASTER_DATA_05_RESUME_PROMPT.md](docs/checkpoints/MASTER_DATA_05_RESUME_PROMPT.md)

Branch conferida: `feature/cash-audit-fechamento`.
Prioridade: P0 — Revisão Cadastral de Evidências, Avaliação de Impacto e Governança da Conta 27173.
Modo: READ ONLY (100% de inspeção local e análise documental; ZERO chamadas externas; ZERO escritas no ERP webPosto).
Classificação final:
- **ACCOUNT 27173: BLOCKED** (classificação defensiva TRANSITORIA mantida; reclassificação para CONTA_CORRENTE BB depende de deliberação formal do diretor ou validação em tela).
- **CASA CAIADA PILOT: BLOCKED** (permanece travado até aprovação humana da conta e emissão do token criptográfico de uso único).
- **EXTERNAL CALLS: ZERO**
- **ERP WRITES: ZERO**
- **STATUS.md: UPDATED**

### 1. Origem Histórica e Natureza da Classificação TRANSITORIA (Agente A)
- **Origem Fática:** Inserida no bootstrap mestre em 21/10/2026 14:33:44 (`MasterDataService._obter_contas_iniciais()`, tabela `master_contas_financeiras`, `audit_id: 21`), decorrente do probe de rede que retornou 17 IDs de `/INTEGRACAO/CONTA`.
- **Inferida vs. Comprovada:** Comprovadamente **INFERIDA DEFENSIVAMENTE** pelo LOGOS como medida de segurança *fail-closed* devido à ausência de filial associada nos metadados globais. **Não representa uma conta transitória de fato no plano de contas do ERP**.
- **Metadados:** No SQLite local, `27173` segue com `empresa_codigo = null`, `permite_debito_despesa = False`, `confiabilidade = HISTORICO`.

### 2. Evidências Oficiais e Confronto de Fontes (Agente B)
- **Extrato Oficial BB (OFX e PDF):** Agência `2365-5`, Conta Corrente `56816-3`, Banco `001`, Titular `AUTO POSTO CASA CAIADA LTDA`, CNPJ `04.284.939/0001-86` (confirmado em transações PIX recebidas no extrato).
- **Cadastro no webPosto (MASTER-DATA-04):** `empresaCodigo: 5555`, `contaCodigo: 27173`, `descricao: "BANCO DO BRASIL (56816-3)"`, `ativo: true`, `saldoAtual: -8685811.91`.
- **Matriz de Auditoria:**
  - Filial (5555): **CONFIRMADO (100%)**
  - Banco (001): **CONFIRMADO TEXTUAL (99%)**
  - Conta Corrente (56816-3): **CONFIRMADO TEXTUAL (100%)**
  - Titular / CNPJ: **CONFIRMADO VIA CADASTRO DA FILIAL 5555**
  - Agência (2365-5): **AUSENTE NO ERP** (endpoint `/INTEGRACAO/V1/CONTAS` não fornece coluna de agência nem a inclui na descrição).
- **Regra Anti-Presunção:** Pela ausência de agência no schema do endpoint, a conta `27173` não foi reclassificada de forma autônoma pelo sistema.

### 3. Governança e Controle de Impactos (Agente C)
- **Blindagem do Caixa Físico (17837):** A conta `17837 — CAIXA(POSTO)` permanece terminantemente restrita a `CAIXA_FISICO` e bloqueada para despesas bancárias.
- **Isolamento de Despesas:** Nenhuma despesa ou rotina automatizada utiliza `27173`.
- **Análise de Impacto Futuro:** A reclassificação formal de `27173` viabilizará despesas legítimas do BB (como FSIST R$ 34,90 e Piloto R$ 626,00), impedirá contaminação do saldo físico da pista, isolará estritamente a filial 5555 de outras empresas, e será registrada de forma append-only no `master_data_audit_log`.

### 4. Testes Executados e Resultados
- Suíte completa Master Data (`tests/unit/master_data/`): **56/56 PASSED (100%)**
- Suíte de Preparação do Piloto BB (`test_expense_04_pilot_prep_bb.py`): **11/11 PASSED (100%)**
- `git diff --check`: 0 erros encontrados.

### 5. Próxima Decisão Humana Necessária
Deliberação formal do diretor/proprietário entre:
1. **Autorização Formal:** Aceitar a evidência textual `"BANCO DO BRASIL (56816-3)"` na filial `5555` como prova suficiente para reclassificar `27173` como conta corrente da Casa Caiada; OU
2. **Inspeção em Tela:** Exigir conferência visual prévia da agência `2365-5` no cadastro de contas da interface web do webPosto antes da reclassificação.

---

## MASTER-DATA-04 — Resolução Oficial da Conta Bancária (Casa Caiada) — 21/10/2026 11:35

Relatórios detalhados:
- [MASTER_DATA_04_CHECKPOINT.md](docs/checkpoints/MASTER_DATA_04_CHECKPOINT.md)
- [MASTER_DATA_04_RESUME_PROMPT.md](docs/checkpoints/MASTER_DATA_04_RESUME_PROMPT.md)

Branch conferida: `feature/cash-audit-fechamento`.
Prioridade: P0 — Execução da Consulta Oficial Read-Only e Resolução de Identidade.
Modo: READ ONLY (1 única requisição GET executada com autorização expressa; ZERO chamadas adicionais; ZERO escritas no ERP webPosto).
Classificação final:
- **ACCOUNT RESOLUTION: BLOCKED** (conta `27173 — BANCO DO BRASIL (56816-3)` identificada no ERP, mas agência, titular e CNPJ não são fornecidos pelo endpoint do webPosto).
- **CASA CAIADA PILOT: BLOCKED** (permanece travado até deliberação humana sobre a suficiência do código `27173`).
- **EXTERNAL CALLS: 1 (GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100)**
- **ERP WRITES: ZERO**
- **STATUS.md: UPDATED**

### 1. Detalhes da Consulta Oficial Read-Only Executada
- **Data/Hora:** `2026-10-21T11:31:15.910989`
- **Endpoint:** `GET https://web.qualityautomacao.com.br/INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100`
- **Status HTTP:** `200 OK`
- **Tempo de Resposta:** `1019.58 ms`
- **Quantidade de Registros:** 9 contas cadastradas na filial 5555.
- **Chamadas Adicionais:** Nenhuma (zero retries, zero redirecionamentos, zero paginação).

### 2. Evidência Empírica Sanitizada das Contas da Casa Caiada no ERP
1. `contaCodigo: 17837` — `descricao: "CAIXA(POSTO)"` (ativo: true)
2. `contaCodigo: 20936` — `descricao: "SANTANDER (3909 130006368)"` (ativo: true)
3. `contaCodigo: 27173` — `descricao: "BANCO DO BRASIL (56816-3)"` (ativo: true, saldoAtual: -8685811.91)
4. `contaCodigo: 27406` — `descricao: "BRADESCO(16652-9)"` (ativo: false)
5. `contaCodigo: 55460` — `descricao: "PAGPIX"` (ativo: false)
6. `contaCodigo: 69446` — `descricao: "PAGBANK"` (ativo: false)
7. `contaCodigo: 70766` — `descricao: "PAGBANK (CASA CAIADA)"` (ativo: true)
8. `contaCodigo: 82912` — `descricao: "VIBRA CASA CAIADA"` (ativo: true)
9. `contaCodigo: 86379` — `descricao: "MAIS PAGAMENTOS - FISERV"` (ativo: true)

### 3. Avaliação das 6 Dimensões de Governança
- **Dimensão 1 (Empresa = 5555):** **CONFIRMADO** (campo `empresaCodigo: 5555`).
- **Dimensão 2 (Banco = 001):** **PARCIAL / COMPATÍVEL** (identificado no texto "BANCO DO BRASIL", sem coluna estruturada no endpoint).
- **Dimensão 3 (Agência = 2365-5):** **AUSENTE NO ERP** (o endpoint `/INTEGRACAO/V1/CONTAS` não possui campo de agência e a descrição omite a agência).
- **Dimensão 4 (Conta = 56816-3):** **CONFIRMADO** (identificado textualmente no sufixo da descrição `(56816-3)`).
- **Dimensão 5 (Titular = AUTO POSTO CASA CAIADA LTDA):** **AUSENTE NO ERP** (o endpoint não retorna titular).
- **Dimensão 6 (CNPJ = 04.284.939/0001-86):** **AUSENTE NO ERP** (o endpoint não retorna CNPJ).

### 4. Decisão de Persistência Local
Em estrita conformidade com as regras invioláveis ("Não inferir dados ausentes. Se existir divergência, duplicidade, ausência de código ou conta bloqueada, retornar BLOCKED") e ("Se houver risco de sobrescrever vínculo existente ou alterar permissões de uso, não persistir"):
- A conta `27173` **NÃO foi reclassificada automaticamente** no banco de dados local `master_data.sqlite3`.
- No catálogo mestre local, a conta `27173` permanece temporariamente rotulada como `TRANSITORIA` com bloqueio para despesas.
- Zero alterações persistidas; integridade e histórico 100% preservados.

### 5. Próxima Decisão Humana Necessária
O diretor/proprietário deve deliberar se autoriza formally a reclassificação da conta `27173` para `CONTA_CORRENTE` da Casa Caiada (`banco="001"`, `agencia="2365-5"`, `conta="56816-3"`), aceitando a evidência textual `"BANCO DO BRASIL (56816-3)"` como comprovação suficiente frente às limitações de schema do webPosto.

---

## MASTER-DATA-03 — Official Account Resolution & Financial Pilot Readiness — 20/10/2026 15:30

Relatórios detalhados:
- [MASTER_DATA_03_ACCOUNT_RESOLUTION.md](docs/validation/MASTER_DATA_03_ACCOUNT_RESOLUTION.md)
- [MASTER_DATA_03_EXPENSE_SECURITY.md](docs/validation/MASTER_DATA_03_EXPENSE_SECURITY.md)
- [MASTER_DATA_03_IDENTITY_GOVERNANCE.md](docs/validation/MASTER_DATA_03_IDENTITY_GOVERNANCE.md)
- [MASTER_DATA_03_PILOT_READINESS.md](docs/validation/MASTER_DATA_03_PILOT_READINESS.md)

Branch conferida: `feature/cash-audit-fechamento`.
Prioridade: P0 — Resolução de Identidade Bancária e Prontidão do Piloto.
Modo: READ ONLY (ZERO chamadas externas executadas; ZERO escritas no ERP webPosto).
Classificação final:
- **MASTER-DATA-03: READY** (mecanismos, barreiras, testes offline e contratos concluídos).
- **CASA CAIADA PILOT: BLOCKED** (aguarda autorização explícita para consulta read-only da conta BB).
- **EXTERNAL CALLS: NONE**
- **ERP WRITES: ZERO**
- **STATUS.md: UPDATED**

### 1. Estado Anterior e Atual
- **Estado Anterior (MASTER-DATA-02):** Catálogo persistente SQLite estruturado; 200 planos de contas ingeridos; barreira pré-escrita integrada ao `MasterDataService`; conta BB Casa Caiada nominalmente mapeada mas sem `contaCodigo`; piloto em estado `BLOCKED`; 36 testes master data aprovados.
- **Estado Atual (MASTER-DATA-03):**
  - Avaliação estrita em 6 dimensões implementada com enum de estados explícitos (`EstadoResolucaoConta`).
  - Contratos read-only preparados para `/INTEGRACAO/V1/CONTAS` e `/INTEGRACAO/EMPRESAS` (nenhuma chamada de rede disparada).
  - Auditoria completa de segurança no Expense Hunter: imutabilidade de aprovação por hash canônico, barreira contra conta 17837 e contas cruzadas, proteção de single-use token com TTL, e bloqueio permanente em caso de timeout (`RESULTADO_DESCONHECIDO`).
  - Isolamento da Conveniência 24h (`118508`) comprovado: `usa_mais_pagamentos=False`, repasse de sangria para 5555, e CNPJ mantido como `PENDENTE`.
  - Posto Real (`5558`) inativo e 100% bloqueado para despesas, com histórico de contraparte preservado.
  - 56 testes master data aprovados (20 novos testes específicos no `test_master_data_03.py`).

### 2. Alterações Realizadas e Arquivos Modificados
- `WebPosto_API/src/modules/master_data/domain/models.py`: Adicionados `EstadoResolucaoConta`, `CriterioResolucaoConta`, `ResolucaoContaOficialResult`, e campo `estado_resolucao` em `ResolucaoContaResult`.
- `WebPosto_API/src/modules/master_data/application/master_data_service.py`: Implementados `preparar_consulta_empresas_oficial()`, `avaliar_resposta_contas_erp()` com normalização estrita em 6 dimensões, e integração com `resolver_conta_financeira()`.
- `WebPosto_API/tests/unit/master_data/test_master_data_03.py`: Criada suíte de testes com 20 cenários cobrindo resolução bancária, idempotência, segurança de token, timeout, barreira pré-escrita e isolamento empresarial.
- `docs/validation/MASTER_DATA_03_ACCOUNT_RESOLUTION.md`: Documentação técnica do Agente A sobre resolução bancária.
- `docs/validation/MASTER_DATA_03_EXPENSE_SECURITY.md`: Documentação técnica do Agente B sobre barreira de segurança e cenários de ataque/falha.
- `docs/validation/MASTER_DATA_03_IDENTITY_GOVERNANCE.md`: Documentação técnica do Agente C sobre governança de empresas e isolamento.
- `docs/validation/MASTER_DATA_03_PILOT_READINESS.md`: Documentação técnica do Agente D com matriz de prontidão do piloto.

### 3. Testes e Resultados
- `WebPosto_API/tests/unit/master_data/test_master_data_03.py`: 20/20 PASSED (16.51s).
- Suíte completa Master Data (`tests/unit/master_data/`): 56/56 PASSED (45.61s).
- Suíte de regressão de reconciliação: 670/670 PASSED.
- `git diff --check`: 0 erros encontrados.

### 4. Consultas Externas e Escritas ERP
- **Consultas Externas Executadas:** **NENHUMA (ZERO)**. Todo o desenvolvimento e validação ocorreram em ambiente offline com fixtures auditáveis.
- **Escritas no ERP Executadas:** **NENHUMA (ZERO)**. Nenhuma chamada POST, PUT, PATCH ou DELETE foi realizada. Nenhum token real foi emitido ou consumido.

### 5. Pendências
1. Resolução em ambiente real do `contaCodigo` do Banco do Brasil para Casa Caiada (`empresaCodigo=5555`), que depende da execução autorizada de `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100`.
2. Confirmação cadastral do CNPJ da Conveniência 24h (`118508`) via consulta autorizada de `GET /INTEGRACAO/EMPRESAS`.

### 6. Riscos Residuais
- **Risco 1 (ERP Timeout):** Se o ERP processar remotamente uma requisição de despesa mas a resposta sofrer timeout na rede, o LOGOS trava a operação local como `RESULTADO_DESCONHECIDO` para evitar débito duplicado. A reconciliação depende de verificação manual no extrato ou API.
- **Risco 2 (Idempotência Remota):** A idempotência ponta a ponta depende de o ERP webPosto rejeitar chaves duplicadas. Como o ERP real não foi testado com escritas repetidas, a segurança reside 100% na barreira de idempotência local do LOGOS.

### 7. Próxima Decisão Humana Necessária
Autorizar formalmente a consulta read-only pontual:
`GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100`
para identificação do `contaCodigo` oficial do Banco do Brasil na Casa Caiada.

---

## MASTER-DATA-02 — Validação de Cadastros Oficiais e Sincronização Financeira — 19/10/2026 20:30

Relatório detalhado: [MASTER_DATA_02_VALIDATION.md](docs/validation/MASTER_DATA_02_VALIDATION.md)
Relatório de cobertura atualizado: [MASTER_DATA_01_MAPPING_COVERAGE.md](docs/validation/MASTER_DATA_01_MAPPING_COVERAGE.md)

Branch conferida: `feature/cash-audit-fechamento`.
Prioridade: P0 — Validação Cadastral Oficial e Sincronização Financeira.
Modo: READ ONLY (nenhuma chamada externa ou escrita real no webPosto, zero commits).
Classificação final: **READY PARA CATÁLOGO, GOVERNANÇA E EXPENSE HUNTER** | **BLOCKED PARA PILOTO CASA CAIADA** (aguarda autorização explícita para consulta pontual de `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555`).

### 1. CNPJs Oficiais Comprovados e Resolução de Divergências
- **74014 (Posto Doze Filial II):** CNPJ oficial comprovado **52.308.604/0002-84** (Razão: POSTO DOZE COMERCIO DE COMBUSTIVEIS E DERIVADOS DE PETROLEO) em `/INTEGRACAO/EMPRESAS` e `filial_master.py`. Status: **CONFIRMADO**. (Divergência anterior descartada: `08.106.946/0002-90` era inferência sem lastro).
- **11495 (Posto VIP):** CNPJ oficial comprovado **03.008.754/0001-86** (Razão: RIO DOCE COMERCIO E SERVICOS LTDA) em `/INTEGRACAO/EMPRESAS` e `filial_master.py`. Status: **CONFIRMADO**. (Divergência anterior descartada: `04.288.756/0001-04` errôneo).
- **5555 (Casa Caiada):** CNPJ oficial comprovado **04.284.939/0001-86** (Razão: AUTO POSTO CASA CAIADA LTDA) no cadastro do webPosto e no extrato bancário oficial BB (`SETEMBRO2026.pdf/.ofx`). Status: **CONFIRMADO**. (Divergência anterior descartada: `05.823.111/0001-83` incorreto).
- **118508 (Conveniência 24 Horas):** Adicionada em outubro/2026; não constava na sonda de 06/10. CNPJ `08.106.946/0003-70` mantido estritamente como **PENDENTE** até confirmação oficial via API. Regra de negócio fixa: **NÃO** usa Mais Pagamentos (`usa_mais_pagamentos=False`), repassa sangria para 5555.
- **5558 (Posto Real / codWeb 7):** CNPJ ERP `24.156.978/0001-05` (REAL RECIFE LTDA, inativa em 20/05/2026); CNPJ recebedor bancário no comprovante BB de 10/10/2026 `08.106.946/0001-09` (POSTO REAL LTDA). **ESTRITAMENTE BLOQUEADO** para lançamentos operacionais de despesa (`autorizado_despesa=False`). Preservado no catálogo como contraparte histórica / empresa relacionada.

### 2. Conta Banco do Brasil Casa Caiada e Bloqueio do Primeiro Piloto
- **Comprovante:** Casa Caiada, BB (001), Agência 2365-5, Conta 56816-3, R$ 626,00, 10/10/2026.
- **Investigação Cadastral:** Nominalmente mapeada em `financial_origin_matrix.json` como `"BANCO DO BRASIL (56816-3)"`, porém o `contaCodigo` numérico do ERP não estava nos snapshots locais.
- **Bloqueio Rígido:** Proibição de inventar código e bloqueio estrito de usar a conta `17837 — CAIXA(POSTO)`, impedindo contaminação do saldo físico de dinheiro da pista.
- **Consulta Read-Only Preparada:** Implementado `MasterDataService.preparar_consulta_conta_bb_casa_caiada()` gerando o contrato para `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100`. Nenhuma chamada externa de rede foi executada.
- **Condição Faltante:** Autorização explícita do usuário para a consulta read-only pontual a fim de obter o `contaCodigo` e associá-lo via sincronização incremental.

### 3. Cobertura Real de Contas e Isolamento Anti-Uso Cruzado
- Contas segregadas em: Contas Correntes (86248, 86188, 65321), Cofres de Sangria (60536, 58062, 58061, 82912, 27406), Caixa Físico (17837), Transitórias (27173, 69446, 82918, 86377) e Adquirentes (55460).
- Contas com vínculo pendente de agência/conta (20936, 59117, 69050, 70766) mantidas como HISTORICO com débito bloqueado.
- Barreira contra uso cruzado bloqueia qualquer solicitação de débito onde a conta pertença a outra filial.

### 4. Plano de Contas e Centros de Custo (ADR-004)
- **200 Contas Gerenciais/DRE:** Ingeridas de `account_category_mapping.json` com método otimizado `upsert_planos_conta_bulk`. Conta 29021 (PRO LABORE) ativa e confirmada como classificação gerencial.
- **Centros de Custo Oficiais:** 7295 (PISTA - bloqueado para administrativo e pró-labore), 18713 (FECHAMENTO - reservado para ajuste/estorno de NF, bloqueado para despesa operacional comum), 21650 (LOJA), 22310 (CONVENIENCIA), 24423 (FOOD).
- **Fornecedores/Favorecidos:** Posto Real LTDA (Empresa Relacionada), Marcio (Sócio), FSIST (Fornecedor).

### 5. Sincronização Incremental e Persistência
- Reutilização exclusiva de `WebPosto_API/data/master_data/master_data.sqlite3`.
- Ingestão idempotente via `sincronizar_dados_incremental` com trilha de auditoria append-only (`master_data_audit_log`).
- Hot backup atômico implementado via `VACUUM INTO` e testado com sucesso.

### 6. Integração Efetiva com Expense Hunter
- `validar_aprovacao_para_escrita` e `executar_lancamento_despesa` em `webposto_escrita_despesa.py` consom diretamente `MasterDataService`.
- Validações de pré-escrita bloqueiam: empresa divergente, conta não autorizada, conta de outra filial, 17837 para débitos bancários, vínculo bancário não comprovado, planos de contas inválidos e centros de custo incompatíveis.

### 7. Testes Automatizados Executados (100% Offline)
- **Suíte Mestre Completa (`tests/unit/master_data/`):** **36 testes aprovados (100% de sucesso)** — 20 de MASTER-DATA-01 e 16 de MASTER-DATA-02.
- **Suíte de Regressão de Conciliação e Despesas:** **670 testes aprovados** sem nenhuma falha.
- **Conformidade Git:** `git diff --check` verificado com saída 0.

---

## MASTER-DATA-01 — Cadastro Mestre Financeiro (Inventário, Persistência e Mapeamento Oficial webPosto) — 19/10/2026 19:30

Relatórios detalhados:
- [MASTER_DATA_01_INVENTORY.md](docs/validation/MASTER_DATA_01_INVENTORY.md)
- [MASTER_DATA_01_STORAGE_DECISION.md](docs/validation/MASTER_DATA_01_STORAGE_DECISION.md)
- [MASTER_DATA_01_MAPPING_COVERAGE.md](docs/validation/MASTER_DATA_01_MAPPING_COVERAGE.md)

Branch conferida: `feature/cash-audit-fechamento`.
Prioridade: P0 — Fundação Operacional para Expense Hunter, Cash Hunter e Conciliações.
Modo: READ ONLY (nenhuma chamada externa ou escrita real no webPosto, zero commits).
Classificação final: **PERSISTÊNCIA E MAPEAMENTO CONCLUÍDOS COM COBERTURA DOCUMENTADA**.

### 1. Armazenamento Escolhido e Justificativa (Decisão de Persistência)
- **Repositório Oficial Adotado:** SQLite Local estruturado dedicado (`WebPosto_API/data/master_data/master_data.sqlite3`).
- **Diretriz Aplicada:** **REUSE > ADAPT > CREATE**. Reutilização da arquitetura persistente já estabelecida e validada em produção pelo LOGOS (`telegram.sqlite3`, `idempotencia.sqlite3`, `pendencias.sqlite3`).
- **Garantias Operacionais:**
  - WAL Mode (`PRAGMA journal_mode = WAL;`) para concorrência de leitura e escrita sem bloqueio;
  - Integridade referencial ativa (`PRAGMA foreign_keys = ON;`);
  - Transações pessimistas (`BEGIN IMMEDIATE`) com rollback automático em falhas;
  - Trilha de auditoria append-only (`master_data_audit_log`) registrando cada inserção, alteração e origem do dado;
  - Zero dependência de daemons externos (PostgreSQL/Supabase eliminados devido à porta 5432 fechada e exigência de operação offline segura);
  - Isolamento de Git: diretório `data/` preservado no `.gitignore`.

### 2. Cadastros Mapeados e Cobertura por Empresa
- **Empresas Cobertas (5 mapeadas):**
  - **74014** (Posto Doze Filial II, codWeb 6, CNPJ 08.106.946/0002-90): **AUTORIZADO** (Usa Mais Pagamentos; Cofre 60536);
  - **11495** (Posto VIP, codWeb 5, CNPJ 04.288.756/0001-04): **AUTORIZADO** (Usa Mais Pagamentos; Cofre 58062);
  - **5555** (AP Casa Caiada, codWeb 8, CNPJ 05.823.111/0001-83): **AUTORIZADO** (Usa Mais Pagamentos; Cofre 58061);
  - **118508** (Conveniência 24 Horas, codWeb 9, CNPJ 08.106.946/0003-70): **AUTORIZADO** (**NÃO** usa Mais Pagamentos; Cofre 82912);
  - **5558** (Posto Real, codWeb 7, CNPJ 08.106.946/0001-09): **BLOQUEADO / EXCLUÍDO** para lançamentos de despesas (decisão expressa do proprietário), mas preservado integralmente como contraparte histórica e recebedor bancário.
- **Contas Financeiras do ERP (17 contas catalogadas):**
  - 1 Caixa Físico (`17837 — CAIXA(POSTO)`, Casa Caiada): estritamente **BLOQUEADO** para liquidação de despesas bancárias;
  - 5 Cofres Físicos de Sangria (`60536`, `58062`, `58061`, `82912`, `27406`): bloqueados para pagamento de despesas bancárias;
  - 4 Contas Bancárias de Snapshot (`20936`, `59117`, `69050`, `70766`): vinculação a agência/conta mantida como **PENDENTE** de consulta read-only ao ERP;
  - 4 Contas Transitórias (`27173`, `69446`, `82918`, `86377`): bloqueadas para despesas manuais;
  - 3 Contas Adquirentes (`55028`, `55460`, `65321`): de uso exclusivo da conciliação de cartões.
- **Plano de Contas Gerencial / DRE (200 contas normalizadas):**
  - Importadas e estruturadas a partir de `account_category_mapping.json`;
  - Conta de referência `29021 — PRO LABORE` mapeada com regra de distinção explícita entre classificação gerencial e beneficiário individual.
- **Centros de Custo:**
  - `7295 — PISTA` (operacional) e `24423 — FOOD / CONVENIENCIA`;
  - Regra semântica ativa: Centro `7295 (PISTA)` bloqueado para despesas de natureza administrativa ou pró-labore.
- **Fornecedores e Favorecidos:**
  - Diferenciação funcional explícita entre: 1) Fornecedor cadastrado no ERP, 2) Recebedor bancário (ex: `Posto Real Ltda`), 3) Beneficiário econômico/sócio (ex: `Márcio`), e 4) Empresa relacionada. Proibição categórica de criação de fornecedores fictícios.

### 3. Caso Específico: Casa Caiada (5555) e Banco do Brasil (R$ 626,00)
- **Status do Código ERP da Conta BB:** **PENDENTE** (não foi identificado nos snapshots locais).
- **Tratamento Seguro:** O LOGOS recusa categoricamente a utilização da conta `17837 — CAIXA(POSTO)` como substituta de conta bancária, evitando contaminação do saldo físico da pista.
- **Resolução:** A despesa permanece retida como pendência cadastral clara até confirmação do `cd_conta` via consulta read-only `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555` ou confirmação direta pelo proprietário.

### 4. Integração com o Expense Hunter
- O módulo `src/modules/master_data/` fornece a classe `MasterDataService` com interface unificada:
  - `resolver_empresa(empresa_codigo)`
  - `resolver_conta_financeira(conta_codigo, empresa_codigo)`
  - `resolver_plano_contas(plano_codigo)`
  - `resolver_centro_custo(cc_codigo, empresa_codigo, tipo_despesa)`
  - `resolver_fornecedor(fornecedor_codigo, cnpj_cpf)`
  - `validar_compatibilidade_despesa(...)`
- O Expense Hunter consulta o catálogo de forma síncrona e desacoplada, sem necessidade de consultas ad-hoc a múltiplos JSONs.

### 5. Testes Automatizados Executados (100% Offline)
- **Suíte Dedicada (`test_master_data_01.py`):** **20 testes aprovados (100% de sucesso)** cobrindo todos os cenários obrigatórios (isolamento Casa Caiada, bloqueio de conta 17837, plano 29021, bloqueios de uso cruzado, bloqueio da empresa 5558, rejeição de fornecedores fictícios, durabilidade SQLite, integridade em falhas e rollback atômico, trilha de auditoria append-only, e ausência total de sockets/chamadas de rede).
- **Regressão Completa de Despesas:** **113 testes aprovados** (100% de sucesso em `test_expense_04_pilot_prep_bb.py`, `test_expense_04_precheck.py`, `test_webposto_escrita_despesa.py`, `test_telegram_despesas.py` e `test_comprovantes_fila.py`).
- **Total Integrado:** **133 testes executados com 100% de aprovação**.

### 6. Riscos, Limitações e Próximos Passos (MASTER-DATA-02)
- **Pendência 1:** Executar consulta pontual read-only ao endpoint oficial `/INTEGRACAO/CONTA` para obter o código oficial da conta BB da Casa Caiada (`agencia=2365-5`, `conta=56816-3`).
- **Pendência 2:** Sincronizar os centros de custo administrativos por filial e o catálogo completo de fornecedores do ERP no MASTER-DATA-02.
- **Garantia de Não-Interferência:** Nenhuma escrita foi realizada no webPosto. O primeiro lançamento real permanece dependente da aprovação expressa do proprietário e emissão do token criptográfico individual.

## EXPENSE-04-PILOT-PREP-BB — Primeiro Lançamento Real (Casa Caiada / Banco do Brasil) — 18/10/2026 18:30

Relatório detalhado: [EXPENSE_04_CASA_CAIADA_BB_PREP.md](docs/validation/EXPENSE_04_CASA_CAIADA_BB_PREP.md).
Branch conferida: `feature/cash-audit-fechamento`.
Empresa: Casa Caiada — `empresaCodigo: 5555`.
Banco: Banco do Brasil (`001` / `1`).
Prioridade: P0 — Integridade Financeira e Preparação do Piloto.
Modo: READ ONLY (nenhuma escrita real no ERP, flags `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` inalteradas no `.env`, zero chamadas externas, zero commits).
Classificação final: **BLOCKED FOR IMMEDIATE ERP WRITE (COM PROPOSTA E PAYLOAD PREPARADOS)**.

### 1. Evidências de Identificação da Conta Banco do Brasil
- **Identificação Bancária:** Agência `2365-5`, Conta Corrente `56816-3`, titular A POSTO CASA CAIADA LTDA, CNPJ `04.284.939/0001-86`.
- **Fontes Comprovatórias:**
  - `extratos/BB/BancoBrasil_CasaCaiada_SETEMBRO2026.ofx` (`<BANKID>1`, `<BRANCHID>2365-5`, `<ACCTID>56816-3`);
  - `extratos/BB/BancoBrasil_CasaCaiada_SETEMBRO2026.pdf` (Cliente Casa Caiada, agência e conta idênticas);
  - `units.json` (linhas 91-94, `contas_compartilhadas` registra `"BB CASA CAIADA"`);
  - `WebPosto_API/financial_origin_matrix.json` (linha 230, registra `"BANCO DO BRASIL (56816-3)"` no cadastro `/INTEGRACAO/CONTA`).
- **Bloqueio Mandatório da Conta 17837:** A conta `17837` mapeada em `units.json` para 5555 é unicamente `"CAIXA(POSTO)"` (dinheiro físico da pista/cofre). Foi estritamente bloqueada para despesas bancárias.
- **Pendência Específica:** O código numérico interno do ERP (`contaCodigo` / `cdConta`) da conta `BANCO DO BRASIL (56816-3)` não consta em `units.json` nem no snapshot persistido. Proibido uso de código fictício ou de outra empresa (Doze `86248`, VIP `65321`).

### 2. Despesas Candidatas e Decisão Expressa do Proprietário
- **Despesa Piloto 1 (FSIST):** R$ 34,90 em 28/09/2026 (Consulta NF-e, FITID `20260928134900`, Doc `92803`).
- **Despesa Piloto 2 (Comprovante BB de 10/10/2026 — Decisão Expressa do Proprietário):**
  - **Valor:** R$ 626,00 pago em 10/10/2026 por conta bancária BB Casa Caiada (`5555`).
  - **Recebedor Bancário Original:** `Posto Real Ltda` (favorecido titular da conta de destino).
  - **Beneficiário Econômico Informado:** `Márcio` (sócio / pró-labore).
  - **Finalidade Declarada:** `PRÓ-LABORE — MÁRCIO` (origem: `DECISAO_EXPRESSA_PROPRIETARIO`, data: `18/10/2026`).
  - **Plano de Contas Oficial Encontrado:** `29021 - PRO LABORE` (catálogo oficial webPosto de 200 contas em `account_category_mapping.json`). Proibida e não realizada invenção de código específico.
  - **Centro de Custo:** `7295 - PISTA` (ou Administrativo).

### 3. Verificação de Duplicidade e Determinação da Operação Contábil
- **Títulos a Pagar (`TITULO_PAGAR`):** Inspeção de títulos em aberto e quitados da filial 5555 confirmou ausência de título no valor de R$ 626,00 em nome de Posto Real Ltda ou Márcio.
- **Movimentos de Conta (`MOVIMENTO_CONTA`):** Nenhum débito manual correspondente escriturado no ERP.
- **Fechamento de Caixa Diário:** Não consta nas saídas de pista (`caixa_2026-10-10_5555.md`).
- **Determinação Contábil:** Como NÃO há título prévio no webPosto, a operação **NÃO** é baixa de título (`PATCH /TITULOS_PAGAR/PAGAR`), mas sim **lançamento direto de despesa já paga** via `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` (`contaMovimentoTipo = "DEBITO"`).

### 4. Pendência Específica Contábil / Fiscal (PJ × Pró-Labore)
- **Alerta de Governança e Conformidade:** Transferência realizada para a conta de pessoa jurídica (**Posto Real Ltda**) com finalidade informada pelo proprietário de **PRÓ-LABORE — MÁRCIO** (pessoa física / sócio).
- **Regra de Não-Substituição:** O LOGOS não altera arbitrariamente a classificação determinada pelo proprietário (mantém plano `29021`), mas registra pendência formal recomendando validação com a contabilidade externa sobre o tratamento fiscal adequado (repasse com nota explicativa vs. mútuo intercompany).

### 5. Contrato OpenAPI V1 e Payload Preparado (R$ 626,00)
- Endpoint: `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` (schema `ParametrosIncluirMovimentoConta`).
- Payload gerado com dados verificados:
  - `descricao`: `"PRÓ-LABORE MÁRCIO (Posto Real Ltda)"`
  - `data`: `"2026-10-10"`
  - `valor`: `626.00`
  - `conta`: `"<PENDENTE_ID_CONTA_BB_5555>"` (suspensa até definição do cdConta)
  - `documento`: `"COMPROVANTE_BB_20261010"`
  - `centroCusto`: `7295` (PISTA)
  - `planoConta`: `29021` (PRO LABORE)
  - `filial`: `5555`
  - `contaMovimentoTipo`: `"DEBITO"`
  - `tipoPessoa`: `"OUTROS"`
  - `pessoa`: `null`

### 6. Testes Automatizados Executados
- **Suíte Dedicada (`test_expense_04_pilot_prep_bb.py`):** **11 testes aprovados** (100% de sucesso em 0.68s):
  - Identificação da conta bancária BB Casa Caiada (Ag 2365-5 / CC 56816-3);
  - Bloqueio estrito da conta `17837` (CAIXA POSTO) para pagamentos bancários;
  - Bloqueio de códigos fictícios e contas de outras empresas;
  - Extração e identificação da despesa FSIST no extrato;
  - Validação do schema do payload do contrato OpenAPI V1;
  - Bloqueio da escrita e geração de pendência cadastral clara;
  - Localização no plano de contas oficial do webPosto de `29021 - PRO LABORE` sem inventar códigos;
  - Preservação do recebedor bancário `Posto Real Ltda` e beneficiário econômico `Márcio`;
  - Determinação de operação como lançamento de despesa e não baixa por ausência de título prévio;
  - Registro de pendência contábil de PJ x Pró-labore sem alteração de classificação;
- **Regressão Completa de Despesas:** **113 testes aprovados** (prep_bb + precheck + escrita_despesa + telegram_despesas + comprovantes_fila, 100% de sucesso).

### 7. Pendências e Condição Operacional
- **Pendência 1 (Cadastral ERP):** Diretor/proprietário confirmar o código numérico (`contaCodigo`) de `BANCO DO BRASIL (56816-3)` na filial 5555, ou autorizar a consulta read-only `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555`.
- **Pendência 2 (Alinhamento Contábil):** Contador validar se a transferência a Posto Real Ltda deve ser mantida como Pró-labore (`29021`) ou reclassificada como conta corrente intercompany.
- **Próximo Passo:** Cadastrar o `cd_conta` confirmado em `units.json`, emitir o token criptográfico individual do piloto no `GerenciadorAutorizacaoPiloto` e executar o primeiro lançamento piloto de forma monitorada.

## EXPENSE-04-PILOT-GATE — Verificação Final de Isolamento e Integridade Antes do Primeiro Lançamento Real — 18/10/2026 16:30

Relatório detalhado: [EXPENSE_04_PILOT_GATE.md](docs/validation/EXPENSE_04_PILOT_GATE.md).
Branch conferida: `feature/cash-audit-fechamento`.
Prioridade: P0 — Segurança Financeira e Isolamento Operacional.
Modo: READ ONLY (nenhuma chamada externa, nenhuma escrita real no ERP webPosto, travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` estritamente mantidas no `.env` da raiz, zero deploy, zero commits).
Classificação final: **READY FOR SINGLE CONTROLLED WRITE**.

### 1. Verificações de Isolamento e Git
- **Status do Git e Diff:** Esclarecido formalmente que arquivos novos como `webposto_escrita_despesa.py`, `telegram_despesas.py` e a suíte de testes `test_expense_04_precheck.py` estão presentes no disco como arquivos não rastreados (`??` no `git status --short`), não figurando em `git diff --stat` devido à restrição mandatória de não realizar commits.
- **Isolamento do Job Noturno das 03:00:** O Task Scheduler executa o fechamento noturno pelo `.env` da raiz, onde `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` permanecem intocados. A barreira `PROD-SAFE-01` continua ativa e inviolável.
- **Isolamento de Configuração do Piloto:** O adaptador de escrita suporta `caminho_env`, permitindo carregar credenciais estritamente a partir de `config/.env.piloto` sem modificar o arquivo de configuração principal.
- **Isolamento de Módulos:** Nenhum processo legado (cartões, conciliação bancária, OFX) possui permissões de escrita adicionais nem acessa os módulos de despesa.
- **Proteção dos Bancos SQLite:** As bases locais em `data/lancamentos_logos/` operam com WAL mode e `BEGIN IMMEDIATE`, sendo ignoradas pelo `.gitignore` para prevenir exclusões ou commits acidentais.
- **Endpoints Fechados:** Sem possibilidade de redirecionamento arbitrário; rotas estritas e mapeadas da OpenAPI V1 do webPosto.

### 2. Barreiras de Autorização Individual e Token Atômico (8D)
- O `GerenciadorAutorizacaoPiloto` exige token criptográfico atômico (`secrets.token_urlsafe(32)`) com hash SHA-256 no SQLite e consumo de uso único.
- Bloqueia categoricamente qualquer divergência nas 8 dimensões obrigatórias:
  1. Identificador da despesa (`op_id == item.id`);
  2. Empresa autorizada (`emp_cod == item.unidade_codigo`);
  3. Tipo de operação (`tp_op == item.operacao_financeira`);
  4. Valor aprovado (`abs(val - item.comprovante.valor) < 0.001`);
  5. Assinatura/hash aprovado (`h_apr == item.aprovado_hash`);
  6. Conta financeira vinculada (`c_cod == conta_efetiva`);
  7. Uso único / anti-replay (`consumida_em IS NULL`);
  8. Prazo estrito de expiração (`agora_iso <= exp_em`, TTL máx. 30 min).

### 3. Matriz de Contas e Empresas
- **Allowlist Fechada:** Doze (`74014`), VIP (`11495`), Casa Caiada (`5555`) e Conveniência 24h (`118508`).
- **Posto Real Excluído:** Códigos `5558` e `7` sumariamente rejeitados no adaptador de escrita e no Telegram.
- **Bloqueio Cruzado da Conta 17837:** A conta `17837` pertence unicamente à Casa Caiada (`5555`). A Conveniência 24h (`118508`) tem `CONTAS_AUTORIZADAS_POR_UNIDADE[118508] = frozenset()` e está estritamente bloqueada contra débitos diretos, sendo permitida apenas criação de contas a pagar (`NOVA_CONTA_A_PAGAR`).

### 4. Tratamento de Inconclusões e Anti-Retry
- Em caso de timeout em POST/PATCH ou resposta sem identificador inequívoco, a operação entra em `RESULTADO_DESCONHECIDO` e recusa reenvios automáticos.
- Confirmação pós-escrita (`confirmar_movimento_conta`) exige correspondência única e inequívoca, recusando confirmação em cenários ambíguos.

### 5. Testes e Evidências
- **102 testes unitários focados no fluxo de despesas aprovados (100% de sucesso):**
  - 22 testes em `test_expense_04_precheck.py`;
  - 28 testes em `test_webposto_escrita_despesa.py`;
  - 23 testes em `test_telegram_despesas.py`;
  - 29 testes em `test_comprovantes_fila.py`.
- **659 testes de regressão global aprovados:** zero falhas, zero testes pulados, zero chamadas externas reais.

### 6. Condição Operacional para o Primeiro Lançamento Real
- Classificação: **READY FOR SINGLE CONTROLLED WRITE**.
- Parada mandatória: nenhuma escrita real foi realizada. O primeiro lançamento real deverá ocorrer somente após emissão manual do token pelo diretor, configuração isolada em `config/.env.piloto` e conferência presencial no ERP webPosto.

## EXPENSE-04-PRECHECK — Revisão Final de Segurança e Preparação do Piloto no webPosto — 18/10/2026 13:00

Relatório detalhado: [EXPENSE_04_PRECHECK_VALIDATION.md](docs/validation/EXPENSE_04_PRECHECK_VALIDATION.md).
Branch conferida: `feature/cash-audit-fechamento`.
Prioridade: P0 — Segurança Financeira e Integridade de Escrita.
Modo: READ ONLY (nenhuma chamada externa, nenhuma escrita real no ERP, nenhuma transação bancária, travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` estritamente mantidas no `.env`, zero deploy).
Classificação final: **READY FOR CONTROLLED PILOT** (com condições operacionais estritas).

### Controles e Correções Implementadas
- **Allowlist Fechada Imutável:** Definido `EMPRESAS_AUTORIZADAS_SET = frozenset({74014, 11495, 5555, 118508})`. O parâmetro `unidades_cadastradas` foi corrigido para apenas validar contra cadastros externos, sem jamais ampliar a lista autorizada. Posto Real (`5558`, `codWeb 7`), códigos espúrios (`12607`, `12705`), `None`, booleanos e strings malformadas são estritamente rejeitados.
- **Segurança da Conta Financeira (Empresa × Conta):** Implementada `validar_conta_financeira_unidade` comprovada por `units.json` e `financial_origin_matrix.json`:
  - Doze (`74014`): contas `{86248, 86081, 86188}`;
  - VIP (`11495`): contas `{65321, 55028}`;
  - Casa Caiada (`5555`): conta `{17837}` ("CAIXA(POSTO)");
  - Conveniência 24h (`118508`): `frozenset()` — conta `17837` estritamente bloqueada por ambiguidade/contaminação de filial; permitida apenas criação de título (`NOVA_CONTA_A_PAGAR`) até definição bancária formal.
- **Autorização Fina do Piloto (`GerenciadorAutorizacaoPiloto`):** Desenvolvido mecanismo criptográfico que exige token atômico de uso único (`secrets.token_urlsafe(32)` com hash SHA-256 no SQLite), prazo de expiração (máx. 30 min) e correspondência estrita em 8 dimensões financeiras (`operacao_id`, `empresa_codigo`, `tipo_operacao`, `valor`, `hash_aprovado`, `conta_codigo`, `autorizador_id`, `expira_em`). Proibida flag genérica estilo `ALLOW_ALL_WRITES=true`.
- **Prevenção de Reenvio após Timeout na Idempotência:** Bloqueio do estado `RESULTADO_DESCONHECIDO` no `iniciar_operacao` do SQLite, impedindo reenvio descontrolado ou após reinicialização do sistema.
- **Detecção de Ambiguidade na Confirmação Pós-Escrita:** `confirmar_movimento_conta` rejeita confirmações quando múltiplos movimentos compatíveis existem no mesmo dia com o mesmo valor, evitando associação ao registro errado.
- **Robustez de Callbacks no Telegram:** Parsing seguro com tratamento de `ValueError`/`TypeError` convertidos para `DespesaTelegramErro`.

### Testes Executados e Resultados
- **Suíte Dedicada EXPENSE-04-PRECHECK:** **22 aprovados**, 0 falhas, 0 ignorados em `WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py`.
- **Suíte de Escrita ERP (EXPENSE-03):** **28 aprovados**, 0 falhas em `test_webposto_escrita_despesa.py`.
- **Suíte do Telegram (EXPENSE-02):** **23 aprovados**, 0 falhas em `test_telegram_despesas.py`.
- **Suíte de Fila e Domínio (EXPENSE-01):** **29 aprovados**, 0 falhas em `test_comprovantes_fila.py`.
- **Regressão Global de Reconciliação:** **659 testes aprovados**, 0 falhas, 0 chamadas de rede externas (Isolamento Premmia: 0 tentativas reais).

### Riscos Mapeados e Situação de Produção
- **Acoplamento com Job Noturno das 03:00:** O Task Scheduler roda o fechamento diário diretamente do diretório `C:\Projetos\LOGOS\LogosPostos`. O `PROD-RELEASE-01` não foi concluído. A trava `PROD-SAFE-01` aborta o fechamento noturno caso `WEBPOSTO_WRITES != 0`.
- **Mitigação para o Piloto:** O primeiro lançamento piloto não deve alterar o `.env` compartilhado da raiz. O executor deve apontar para arquivo isolado (`caminho_env="config/.env.piloto"`) com autorização individual e token atômico.

### Condição para o Piloto Real
- Concluído e classificado como **READY FOR CONTROLLED PILOT**.
- Bloqueado até autorização expressa do dono, token de piloto emitido pelo diretor e monitoramento presencial.

## EXPENSE-03 & EXPENSE-03-SCOPE-FIX — Adaptadores Seguros de Lançamento de Despesas e Exclusão do Posto Real — 18/10/2026 10:20

Relatório detalhado: [EXPENSE_03_ERP_WRITE_ADAPTER_VALIDATION.md](docs/validation/EXPENSE_03_ERP_WRITE_ADAPTER_VALIDATION.md).
Branch conferida: `feature/cash-audit-fechamento`.
Modo: READ ONLY (nenhuma chamada externa, nenhuma escrita real no ERP, nenhuma transação bancária, travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` estritamente mantidas, `.env` não alterado).

### Alterações Implementadas
- **Resolução Definitiva da Divergência de Empresas (P0):** Código oficial de Casa Caiada confirmado como `5555` (comprovado em `audit_filial_master_resultado.json`, `docs/webposto_mapping.md` e `units.json`). Constatado que `12607` e `12705` eram fragmentos de NSU de cartões (`212607388` e `101270524784`) equivocadamente digitados no texto do relatório anterior. Implementado bloqueio explícito que recusa `12607`, `12705` ou qualquer código fora do cadastro autorizado.
- **Exclusão do Posto Real do Escopo (EXPENSE-03-SCOPE-FIX):** Atendendo à decisão do dono, o **Posto Real (empresaCodigo 5558 / codWeb 7, CNPJ desativado/inativo) foi formal e estritamente excluído do Expense Hunter**:
  - Excluído dos botões e teclados de correção do Telegram;
  - Bloqueado em callbacks manuais ou diretos (`desp:u:{ticket}:5558` e `:7` levantam `DespesaTelegramErro`);
  - Bloqueado na validação de propostas do domínio (`ItemFilaDespesa.verificar_bloqueios_aprovacao`);
  - Descartado na ingestão de comprovantes (`processar_comprovante_recebido`);
  - Bloqueado sumariamente no adaptador de escrita (`webposto_escrita_despesa.py`) via `BarreiraDespesaErro`, mesmo se fornecido em listas externas;
  - Preservados os dados históricos do Posto Real nos demais módulos e relatórios do sistema;
  - Preservadas e ativas as unidades autorizadas: Posto Doze Filial II (`74014`), Posto VIP (`11495`), AP Casa Caiada (`5555`) e Conveniência 24 Horas (`118508`).
- **Adaptador Oficial de Lançamento:** Criado `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py` com suporte estrito aos contratos da OpenAPI V1:
  - Operação A: `POST /INTEGRACAO/V1/TITULOS_PAGAR` (`IncluirTituloDto`).
  - Operação B: `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` (`ParametrosIncluirMovimentoConta`, `contaMovimentoTipo="DEBITO"`).
  - Operação C: `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` (`PagarTituloDto`, `tituloPagarCodigo` como array).
  - Vínculo de Comprovante: `POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}` (`IncluirArquivoFechamentoCaixaDto`, Base64).
- **Validação de Aprovação e Hash Canônico:** Exige status `aprovado`, conferindo versão e hash SHA-256. Qualquer alteração nos dados invalida a aprovação e retorna a proposta para `aguardando_revisao`.
- **Barreira de Travas Físicas (.env):** Inspeção com `DotEnvTravas` exigindo `WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1` exclusivamente no arquivo `.env` físico, bloqueando execução com flags em zero ou duplicadas.
- **Idempotência Local e Exclusão Mútua:** Tabela SQLite atômica (`operacoes_despesas`) com controle de transação `BEGIN IMMEDIATE`. Reenvios concorrentes ou repetidos são bloqueados.
- **Tratamento de Timeout sem Retry Automático:** Timeout após envio registra estado `RESULTADO_DESCONHECIDO` e proíbe novo envio automático sem reconciliação prévia.
- **Confirmação Pós-Escrita:** Consulta de conferência via `GET /MOVIMENTOS_CONTA` e `GET /TITULOS_PAGAR`. Somente avança para `lancado_erp` se confirmado com evidência inequívoca.
- **Auditoria Append-Only:** Registro completo das operações em `data/lancamentos_logos/<empresa>/historico_despesas.json`.

### Testes Implementados
- **28 testes unitários offline** em `WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_despesa.py` cobrindo conta a pagar, movimento de débito, baixa de título, bloqueio explícito de Posto Real 5558/7, chamada direta bloqueada, empresa indefinida, conta financeira errada, fornecedor inexistente, plano de contas inválido, aprovação ausente, versão antiga, hash alterado, operação divergente, idempotência local, timeouts em POST/PATCH, retry bloqueado, concorrência simultânea, HTTP 201 sem ID, HTTP 204 sem payload, consulta inconclusiva, anexos em Base64, falha de anexo isolada, flags em zero, ausência de chamadas externas e validação de Casa Caiada 5555.
- **23 testes unitários offline** em `WebPosto_API/tests/unit/cash_reconciliation/test_telegram_despesas.py` cobrindo o fluxo de aprovação e o teste 23 de exclusão de Posto Real nos teclados, callbacks e domínio.
- **29 testes unitários offline** em `WebPosto_API/tests/unit/cash_reconciliation/test_comprovantes_fila.py`.
- **Regressão completa da suíte de reconciliação:** **637 testes aprovados**, 0 falhas.

### Resultados
- Adaptadores de integração construídos com segurança de nível financeiro, estrita aderência aos contratos da OpenAPI, exclusão segura de filiais desativadas/fora de escopo e proteção contra lançamentos indevidos.

### Riscos Mapeados
- Operação em produção depende de fornecedores já cadastrados no webPosto para criação de contas a pagar (`fornecedorCodigo > 0`).

### Próximo Passo
- **EXPENSE-04:** Piloto real supervisionado com 1 despesa de baixo valor, condicionado à autorização expressa do dono e ativação pontual das flags no `.env`.

## EXPENSE-02 — Aprovação Inteligente e Automatizada pelo Telegram — 17/10/2026 22:30

Relatório detalhado: [EXPENSE_02_TELEGRAM_APPROVAL_VALIDATION.md](docs/validation/EXPENSE_02_TELEGRAM_APPROVAL_VALIDATION.md).
Branch conferida: `feature/cash-audit-fechamento`.
Modo: READ ONLY (nenhuma chamada externa, nenhuma escrita no ERP, travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` estritamente mantidas, `.env` não acessado).

### Alterações Implementadas
- **Classificação Financeira Automática:** Propostas categorizadas nas 5 categorias conceituais: `NOVA_CONTA_A_PAGAR`, `DESPESA_JA_PAGA`, `TITULO_EXISTENTE`, `POSSIVEL_DUPLICIDADE` e `INDETERMINADO`.
- **Mensagem Amigável no Telegram:** Renderização focada na decisão executiva do diretor (valores em R$, datas `dd/mm/aaaa`, nome da empresa, mascaramento de dados sensíveis e conferências claras).
- **Aprovação com Um Toque:** Botões inline `[ Aprovar ] [ Corrigir ] [ Rejeitar ]` integrados ao bot existente em `receber_comprovantes.py`.
- **Tickets Opacos e Seguros:** `callback_data` curto (`desp:a:{ticket}`) sem expor IDs internos ou valores financeiros, evitando estourar o limite de 64 bytes da API do Telegram.
- **Segurança de Concorrência e Anti-Replay:** Tickets persistidos em SQLite com lock `BEGIN IMMEDIATE`; ações simultâneas ou repetidas são bloqueadas atomicamente.
- **Integridade de Versão e Hash Canônico:** Aprovação vinculada a hash SHA-256 e versão exata do item da fila. Qualquer correção invalida a aprovação anterior e tickets emitidos para versões anteriores são rejeitados.
- **Fluxo de Correção Rápida:** Botões para correção ágil de empresa (Postos Doze 74014, VIP 11495, Casa Caiada 5555, Conv 24h 118508) e plano de contas sem formulários extensos.
- **Fluxo de Rejeição Auditável:** Mantém o documento físico em disco, registra autor e timestamp ISO, e impede lançamento futuro.
- **Isolamento de Escrita:** A aprovação transiciona para `aprovado` (Aguardando Integração Futura), NUNCA para `lancado_erp`. Zero writes no ERP.

### Testes Implementados
- 22 testes unitários offline obrigatórios em `WebPosto_API/tests/unit/cash_reconciliation/test_telegram_despesas.py` cobrindo comprovante completo, empresa indefinida, fornecedor desconhecido, despesa a pagar, despesa quitada, título existente, possível duplicidade, duplicidade SHA-256, aprovação autorizada, invasor não autorizado, replay, versão antiga, concorrência atômica, correção de valor/empresa/classificação, rejeição, reinicialização da fila, registros legados, ausência de escrita ERP e ausência de chamadas externas (100% offline).
- Regressão completa da suíte de reconciliação: 608 testes aprovados, 0 falhas.

### Resultados
- Fluxo de ponta a ponta implementado e validado offline com excelência de governança e experiência do usuário no celular.

### Riscos Mapeados
- Escrita no ERP permanece bloqueada até aprovação formal do dono para o incremento de escrita (EXPENSE-03).

### Próximo Incremento Recomendado
- **EXPENSE-03:** Implementar adaptadores tipados de escrita webPosto para as rotas já verificadas da OpenAPI V1 (`POST /TITULOS_PAGAR`, `POST /MOVIMENTOS_CONTA`, `PATCH /TITULOS_PAGAR/PAGAR`, `POST /ARQUIVOS`), ativados sob flag expressa e autorização do dono.

## EXPENSE-API-CONTRACT-CHECK — Verificação Definitiva de Endpoints na OpenAPI V1 — 17/10/2026 21:50

Relatório detalhado: [EXPENSE_API_CONTRACT_CHECK.md](docs/validation/EXPENSE_API_CONTRACT_CHECK.md).
Fonte primária: `docs/external/webposto/openapi_integracao_2026-10-06.json` (OpenAPI 3.0.1, 26.455 linhas).
Modo: READ ONLY (nenhuma chamada externa, `.env` não acessado, nenhuma escrita no ERP).

### Resultados da Verificação Contratual
- `POST /INTEGRACAO/V1/TITULOS_PAGAR`: **SIM** (L10685). Schema `IncluirTituloDto` (L13996). Campos obrigatórios: `descricao`, `numeroTitulo`. Retorna `201 Created` (`JsonObject`). Permite inclusão de títulos a pagar (Operação A).
- `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`: **SIM** (L4957). Schema `ParametrosIncluirMovimentoConta` (L14656). Campo obrigatório: `descricao`. Retorna `201 Created`. Permite lançamento de despesas já quitadas diretamente em conta bancária (Operação B).
- `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR`: **SIM** (L10718). Schema `PagarTituloDto` (L15553). Campo obrigatório: `tituloPagarCodigo` (array). Retorna `204 No Content`. Permite baixa e quitação de títulos a pagar existentes (Operação C).
- `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA`: **SIM** (L4758). Retorna `200 OK` (`RetornoPaginadoMovimentoConta`). Suporta filtro por filial, datas, documento, tipo de documento de origem e paginação por cursor (`ultimoCodigo`).
- `POST /INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}` e `POST /INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{id}`: **SIM** (como endpoint parametrizado formal `POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}`, L482). Enum `tipoOrigem` contempla expressamente `"MOVIMENTO_CONTA_MANUAL"` e `"TITULO_PAGAR"`. Schema `IncluirArquivoFechamentoCaixaDto` (L15356) com `nome` e `conteudo` (Base64). Retorna `201 Created`.

### Conclusão Operacional
Todas as 3 operações financeiras principais (Operação A: Inclusão de Título a Pagar; Operação B: Movimento de Conta Direto; Operação C: Baixa de Título) e os vínculos de comprovantes possuem contratos documentados na OpenAPI V1. O desenvolvimento de adaptadores pode prosseguir com segurança documental em etapa posterior.

## EXPENSE-01 — Integridade da Fila, Anti-duplicidade e Revisão Obrigatória — 17/10/2026 21:45

Relatório detalhado: [EXPENSE_01_VALIDATION.md](docs/validation/EXPENSE_01_VALIDATION.md).
Modo: READ ONLY (nenhuma escrita no ERP, travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` mantidas, `.env` não acessado).
Branch conferida: `feature/cash-audit-fechamento`.

### Alterações Implementadas
- **Eliminação do Fallback de Empresa:** Removida a atribuição forçada para Posto Doze (`74014`). Unidades ambíguas ou sem evidência registram `EMPRESA_INDEFINIDA` e forçam status `aguardando_revisao`, impedindo aprovação.
- **Anti-Duplicidade de Comprovante (SHA-256):** Arquivos idênticos não geram novo item financeiro na fila; referenciam o item anterior (`duplicado_de_id`) e informam o diretor.
- **Alerta de Despesa Duplicada:** Arquivos diferentes para a mesma despesa (mesmo valor e data) recebem `alerta_duplicidade` e são retidos em `aguardando_revisao` para conferência humana, sem descarte automático.
- **Proteção de Transação Bancária (FITID + Conta):** Chave unívoca `(banco, conta, fitid)` impede reaproveitamento do mesmo débito por múltiplos comprovantes na mesma conta. Extratos com conta não confiável não realizam matching automático.
- **Máquina de Estados Conforme ADR-003:** Estados explícitos (`recebido`, `aguardando_revisao`, `aguardando_aprovacao`, `aprovado`, `rejeitado`, `lancamento_solicitado`, `lancado_erp`, `falha`, `resultado_desconhecido`). Nenhum item nasce aprovado; auto-aprovação pelo sistema é estritamente proibida.
- **Trilha de Auditoria:** Cada transição registra histórico completo com motivo, agente, timestamp ISO e usuário (`historico_transicoes`).
- **Compatibilidade Retroativa:** Registros antigos com status `"pronto para lançar"` são lidos perfeitamente e tratados conservadoramente como `aguardando_aprovacao` (nunca aprovados retroativamente).

### Testes Implementados
- 14 testes unitários obrigatórios adicionados em `WebPosto_API/tests/unit/cash_reconciliation/test_comprovantes_fila.py`:
  1. Upload de comprovante novo (SHA-256 e transição auditada).
  2. Mesmo arquivo enviado novamente (anti-duplicidade sem novo item).
  3. Fotos diferentes da mesma despesa (alerta de duplicidade e revisão).
  4. Empresa não identificada (`EMPRESA_INDEFINIDA`, sem fallback Doze).
  5. Empresa identificada corretamente (via conta de extrato configurada).
  6. FITID repetido na mesma conta (débito em uso não vinculado).
  7. FITID igual em contas diferentes (unívoco por banco/conta/fitid).
  8. FITID sem identificação confiável da conta (matching suspenso).
  9. Persistência e leitura de registros legados (status conservador).
  10. Recuperação após interrupção (gravação atômica via `.tmp`).
  11. Transições válidas e inválidas de estado (validação de governança).
  12. Nenhum registro criado como automaticamente aprovado.
  13. Nenhum write ERP realizado (`WEBPOSTO_WRITES=0` mantido).
  14. Nenhuma chamada real externa (isolamento offline 100%).

### Resultados
- Fila local protegida contra duplicidades acidentais e atribuições indevidas de filial.
- 100% dos requisitos de governança da ADR-003 atendidos na camada de ingestão e revisão.

### Riscos Mapeados
- Itens com empresa indefinida ou alerta de duplicidade exigem interação do diretor para avanço.
- A fila local `data/despesas_avulsas/fila.json` requer rotina de backup no servidor operacional.

### Pendências
- Implementação de botões interativos no Telegram para aprovação/revisão com um toque (Incremento 3).
- Resposta da Quality sobre criação de títulos a pagar avulsos e fornecedores sem cadastro.

### Próximo Incremento Recomendado
- **Incremento 2 (EXPENSE-02):** Preparar comandos financeiros tipados (`ParametrosIncluirMovimentoConta` e `PagarTituloDto`) e validar contratos em testes offline, sem execução HTTP.

## EXPENSE-AUDIT-01 — Auditoria Funcional do Expense Hunter e Validação de Escrita webPosto — 17/10/2026 21:30

Relatório detalhado: [EXPENSE_AUDIT_01_CURRENT_STATE.md](docs/validation/EXPENSE_AUDIT_01_CURRENT_STATE.md).
Modo: READ ONLY (nenhuma escrita no ERP, travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` mantidas, `.env` não acessado).
Branch conferida: `feature/cash-audit-fechamento`.

### Capacidades Existentes (Implementadas no Código)
- **Captura Multimodal (Telegram):** Receptor em `src/jobs/receber_comprovantes.py` com whitelist de diretores (`TELEGRAM_CHAT_IDS`), suportando fotos (`photo[-1]`), documentos PDF (`document`) e mensagens de voz/áudio (`voice`/`audio`).
- **Extração com IA (Gemini):** `GeminiExtractor` em `gemini_comprovantes.py` usando `gemini-2.5-flash` / `gemini-1.5-flash` (e mock para testes), extraindo valor, data, favorecido, CPF/CNPJ, tipo e transcrevendo áudios para complementar despesas.
- **Preservação de Documentos:** Arquivos originais gravados em `WebPosto_API/data/despesas_avulsas/comprovantes/comp_{id}.ext`.
- **Casamento com Extratos OFX:** `processar_comprovante.py` cruza débitos com arquivos OFX locais (BB e PagBank), tolerando até +10% de juros e janela de ±3 dias.
- **Prevenção de Falsos Positivos:** `despesas_sem_lancamento.py` exclui transferências internas entre postos do grupo (VIP, Doze, Casa Caiada, Real, etc.), aplicações financeiras e tarifas bancárias.
- **Detecção de Títulos Já Existentes:** `titulos_pagos_sem_baixa.py` identifica débitos que casam com títulos em aberto no ERP, prevenindo cadastrar despesa avulsa em vez de baixar obrigação.
- **Fila Local Atômica:** `fila_despesas.py` gerencia `data/despesas_avulsas/fila.json` com escrita atômica via arquivo temporário.

### Capacidades Realmente Validadas
- **Validação de Testes Unitários:** Analisadas 1.598 linhas de testes unitários estritamente offline em `WebPosto_API/tests/unit/cash_reconciliation/`:
  - `test_comprovantes_fila.py` (530 linhas): parsing monetário, datas brasileiras, mock do Gemini, whitelist de chat_id, CRUD da fila e respostas ao Telegram.
  - `test_despesas_sem_lancamento.py` (559 linhas): regras de exclusão de postos do grupo, tarifas, deduplicação por FITID e matching de débitos.
  - `test_titulos_pagos_sem_baixa.py` (509 linhas): matching de títulos em aberto e distinção de candidatos à baixa.
- **Limitação de Validação:** A validação em produção ao vivo com o Telegram e a API do Gemini depende de credenciais ativas no `.env`. Não foram feitas chamadas de rede externas nesta auditoria.

### Situação dos Endpoints webPosto (Conforme OpenAPI 2026-10-06)
- **Operação A (Despesa nova / a pagar):** **LACUNA NA API.** OpenAPI V1 não documenta `POST /INTEGRACAO/V1/TITULOS_PAGAR`. Rota legada unversionada dava 404 em testes da Sprint 21.3. Exige esclarecimento com a Quality sobre viabilidade via API ou necessidade de entrada via DF-e/NF-e.
- **Operação B (Despesa já paga sem título):**
  - Movimento financeiro: `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` (`ParametrosIncluirMovimentoConta`, `contaMovimentoTipo="DEBITO"`, `tipoDocumentoOrigem="MANUAL"`). Debita saldo bancário no ERP; retorna 201 Created.
  - Anexo do comprovante: `POST /INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}` (`IncluirArquivoFechamentoCaixaDto`). Retorna 201 Created.
  - **Alerta de Risco:** Não existe rota de DELETE/estorno via API. Movimento errado exige exclusão manual na interface do ERP.
- **Operação C (Título existente pago no banco):**
  - Baixa financeira: `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` (`PagarTituloDto`). Baixa valor integral do título; retorna 204 No Content.
  - Anexo ao título: `POST /INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{id}`. Retorna 201 Created.
- **Consultas Prévias e Confirmação:** `GET /INTEGRACAO/V1/TITULOS_PAGAR`, `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA` (com cursor `ultimoCodigo`) e `GET /INTEGRACAO/V1/CONTAS`.

### Riscos de Escrita Mapeados
1. **Lançamento Duplicado no ERP:** Se o sistema não cruzar antes com títulos em aberto, pode lançar despesa avulsa para um boleto já provisionado no Contas a Pagar, gerando custo duplo.
2. **Reenvio Pós-Timeout:** Requisições de rede com timeout correm risco de duplo lançamento se houver retry cego sem prévia consulta `GET`.
3. **Atribuição Indevida de Empresa:** O código atual aplica fallback forçado para Doze (74014) caso a conta bancária não seja identificada no extrato.
4. **Falta de Botão de Aprovação na Fila Atual:** O status `"pronto para lançar"` é setado automaticamente sem confirmação explícita do diretor.

### Pendências com a Quality / Dono
1. Quality: Confirmar se a V1 permite inclusão de contas a pagar avulsas (`POST /V1/TITULOS_PAGAR`) ou se exige DF-e/XML de entrada.
2. Quality: Confirmar se `POST /V1/MOVIMENTOS_CONTA` aceita `tipoPessoa="NAO_IDENTIFICADO"` sem cadastrar a pessoa.
3. Dono: Autorização das melhorias do Incremento 1 (sem escrita) e definição do teto financeiro máximo por lançamento.

### Próximo Incremento Recomendado
- **Incremento 1: Reconhecimento, Classificação e Fila com Anti-Duplicidade (Sem Escrita)**
  - Implementar verificação de hash SHA-256 no arquivo original para barrar documento duplicado;
  - Bloquear reuso de FITIDs já registrados na fila;
  - Substituir fallback forçado para Doze por status `"aguardando_revisao"`;
  - Adotar formalmente a máquina de estados da ADR-003 (`aguardando_aprovacao`, `aprovado`, etc.) em `comprovante.py` e `fila_despesas.py`.
  - **Tudo 100% offline e sem escrita no ERP.**

## ARCH-MODULE-01 — Verificação da Organização Modular e Expense Hunter — 17/10/2026 21:15

Relatório detalhado: [ARCH_MODULE_01_CURRENT_STRUCTURE.md](docs/architecture/ARCH_MODULE_01_CURRENT_STRUCTURE.md).
Modo: READ ONLY (nenhum arquivo movido, nenhum import alterado, nenhuma escrita realizada, `.env` não acessado).

### Resultado
- **Modularização:** O LOGOS não está adequadamente modularizado de forma uniforme; coexistem 3 camadas: scripts da raiz legada, 42 serviços horizontais em `WebPosto_API/src/services/` e a arquitetura vertical em `WebPosto_API/src/modules/` (com `cash_reconciliation` operando como "God Module").
- **Dispersão e duplicações:** Há comprovadamente 12 clientes HTTP WebPosto duplicados, 3 versões de classificadores de despesas e modelos dispersos entre a raiz e `WebPosto_API`.
- **Expense Hunter:** Cerca de 85% do fluxo funcional já existe e está testado dentro de `WebPosto_API/src/modules/cash_reconciliation/` (`gemini_comprovantes.py`, `comprovante.py`, `fila_despesas.py`, `processar_comprovante.py`, `despesas_sem_lancamento.py`, `titulos_pagos_sem_baixa.py`) e `src/jobs/receber_comprovantes.py`.
- **Integração webPosto:** Existe uma integração oficial compartilhada apenas para leitura (`GET` com cursor `ultimoCodigo` em `src/modules/webposto_integration/http.py`), sem vazamento de chaves (`ARCH01`). A escrita no webPosto inexiste para despesas.
- **Separação código/dados:** Fila (`fila.json`), comprovantes e planilhas estão adequadamente isolados em `WebPosto_API/data/despesas_avulsas/` (ignorado no Git). Porém, artefatos operacionais soltos (`.xlsx`, `.json`, `.csv`, `.log`) ainda poluem a raiz de `WebPosto_API` e a raiz do repositório.

### Riscos Identificados
1. **Risco de Quebra por Refatoração Prematura:** Mover arquivos de despesas para um novo módulo quebraria dependências em cadeia e parte dos 611 testes existentes.
2. **Escrita no ERP:** Falta adaptador de escrita específico para despesas com as guardas estritas do ADR-003. `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` devem permanecer inalterados.
3. **Acoplamento do Bot Telegram:** O listener de comprovantes compartilha o consumidor do Telegram com callbacks de cartões e Mais Pagamentos.

### Decisão Arquitetural (`REUSE > ADAPT > CREATE`)
1. **Preservar arquivos onde estão:** Não mover arquivos e não criar novos módulos de domínio nesta etapa.
2. **Expense Hunter como Capability:** O Expense Hunter opera como capability analítica/operacional orquestrada em `jobs/receber_comprovantes.py` e `jobs/despesas_avulsas.py`, consumindo os motores existentes em `cash_reconciliation`.
3. **Reutilização Integral:** Reutilizar integralmente o `GeminiExtractor`, o modelo `ItemFilaDespesa`, a persistência da fila JSON em `data/despesas_avulsas/` e o cruzamento com extratos OFX de `despesas_sem_lancamento.py`.
4. **Mudança Estrutural Mínima:** A única adição estrutural futura será um adaptador isolado de escrita (`webposto_escrita_despesa.py`) para `POST /V1/MOVIMENTOS_CONTA` e `PATCH /V1/TITULOS_PAGAR/PAGAR`, ativado apenas após aprovação humana na fila e liberação formal de escrita.

### Próximo Passo
- Parar e aguardar aprovação formal do diretor para o relatório [ARCH_MODULE_01_CURRENT_STRUCTURE.md](docs/architecture/ARCH_MODULE_01_CURRENT_STRUCTURE.md) antes de qualquer implementação de escrita ou ajuste de fila.

## STATUS-SAVE-01 — estado consolidado — 17/10/2026 20:44 (leia primeiro)

Branch conferida: `feature/cash-audit-fechamento`. Registro documental solicitado
pelo dono; histórico abaixo preservado. Resultados anteriores são reportados,
não reexecutados ou certificados novamente nesta tarefa.

### PROD-SAFE-01
- Integridade de execução e freshness gate implementados, conforme validação
  informada pelo agente e histórico registrado neste status.
- Auditoria incompleta não deve gerar resumo financeiro normal: somente aviso
  operacional, sem promover entrega de mensagem a sucesso da auditoria.
- Testes reportados: **611 aprovados na suíte ampliada e 94 na rodada focada**,
  com sobreposição; não somar os resultados. Nenhum teste reexecutado aqui.
- Produção isolada ainda pendente; implementação do gate não confirma release.

### PROD-RELEASE-01
- Isolamento em `C:\Projetos\LOGOS\production` **não confirmado como concluído**.
- Deploy controlado, identificação da versão efetivamente executada, rollback
  e configuração/validação do Task Scheduler permanecem pontos de validação.
- Nenhum deploy, isolamento ou alteração de tarefa realizado nesta atualização.

### Mais Pagamentos
- Plataformas intermediárias informadas: Asaas, Fiserv e Matera.
- Doze 74014: Asaas. VIP 11495 (incluindo sua própria conveniência) e Casa
  Caiada 5555: Fiserv. Associação operacional da Matera por unidade não comprovada.
- **Conveniência 24h 118508 NÃO utiliza Mais Pagamentos**; fora das matrizes e
  pendências Mais, mantida nos demais módulos aplicáveis sem mudança operacional.
- Cadeia pagamento → crédito intermediário → repasse → crédito no banco final
  **ainda não comprovada**.
- MAIS-BANK-04: relatório documental de saldos e repasses manuais/automáticos
  produzido; validação financeira real **não concluída**, por falta de evidência
  suficiente. Não confundir entrega do diagnóstico com fechamento de saldo,
  execução comprovada de repasse ou crédito bancário confirmado.

### Segurança
- Configurações informadas pelo dono: `WEBPOSTO_WRITES=0` e
  `LOGOS_ERP_ESCRITA=0`; arquivo não acessado nem alterado nesta tarefa.
- Guardas de escrita não são uniformes em todos os caminhos. Flags zeradas não
  constituem prova de proteção universal; **escrita ERP deve continuar bloqueada**.
- Nenhuma nova autorização de escrita, integração externa ou operação financeira.

### Nova prioridade — LOGOS Expense Hunter / EXPENSE-AUDIT-01
- Próxima investigação a iniciar **somente em tarefa posterior**:
  reconhecimento de comprovantes por foto/PDF/Telegram; extração automática
  de fornecedor, valor, vencimento e empresa.
- Verificar duplicidade, revisão humana, aprovação e o caminho de eventual
  lançamento no webPosto, sem executá-lo nem autorizar escrita.
- Revisar/reutilizar módulos existentes antes de implementar funcionalidades;
  capacidades históricas de comprovantes não equivalem a fluxo completo validado.
- **Nenhuma escrita ERP autorizada. EXPENSE-AUDIT-01 não iniciado nesta tarefa.**

### Limite desta atualização
- Somente STATUS.md atualizado e salvo; histórico mantido. Sem alteração
  funcional, leitura/alteração de .env, integração externa, commit, push ou merge.
- Parada após salvar e conferir o diff; não executar comandos históricos de
  retomada nem iniciar a nova investigação por este registro.

## SITUAÇÃO EM 17/10/2026 — Claude assume o desenvolvimento (histórico anterior à consolidação)

**17/10 19:30 — RESOLVIDO:** diretor voltou as travas para 0. Reprocessados (sem Telegram) 15/10 e 16/10: 4 unidades
lidas, AUDIT_PARTIAL (esperado: PagBank 118508 credencial inválida; Mais/Cielo/Rede sem integração). Em 16/10 o
Premmia não coletou por "login já tentado" (regra de 1 login por noite) → reprocessar 16/10 depois do robô de 18/10.

**(histórico) Bloqueio urgente (ação do diretor):** `WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1` no `.env` desde o teste do
piloto de cartão (15/10). O robô das 03:00 **recusa rodar com escrita ligada** (gate PROD-SAFE) → **sem auditoria
nas noites de 16/10 e 17/10**. Voltar as duas para `0`; depois reprocessar 15–16/10.

**Direção aceita (revisão com ChatGPT/Gemini, 16–17/10):**
- Missão: prevenção na origem + auditoria confiável (somente leitura) + correção humana orientada.
- **Escrita no ERP congelada** (OFX, cartão, baixa, despesas, estoque). Piloto de cartão fica pronto e desligado.
- IA não calcula fatos financeiros; tudo sai do motor com teste. Casos reais viram golden cases (1º: Doze 14/10,
  686,71 = 34,75 + 139,35 + 500,00 + 12,61).
- Produção deve rodar versão aprovada fora da pasta de trabalho (PROD-RELEASE-01, ainda não feito).
- Processo: problema + critério de aceite → uma entrega ponta a ponta → validação → release. Sem micro-sprints.

**Fatos novos do diretor (17/10):**
- Maquininhas PagBank são **integradas**; às vezes a integração não reconhece a transação (cartão cobrado,
  venda fica como dinheiro, cupom sem vínculo). Analisar caso a caso → Sprint 20.
- Ecossistemas posto + loja (caixas e PDVs sempre separados): VIP (mesmo CNPJ, loja por centro de custo);
  Casa Caiada 5555 + Conveniência 24h 118508 (CNPJs diferentes); Doze 74014 + Conveniência Real (Linx — fora;
  a partir de nov/2026 vai para o CNPJ do posto no webPosto, por centro de custo).
- Mais Pagamentos: Doze = "Posto Abreu e Lima" (Asaas); Casa Caiada e VIP = Fiserv. PAGPIX desativada.
  Login da API dá 401 com as credenciais do webPosto → perguntar à Quality.
- Correção confirmada pelo dono (17/10): **Conveniência 24h 118508 não utiliza Mais
  Pagamentos**. Fora das matrizes/pendências de contas e repasses Mais; permanece
  nos demais módulos aplicáveis, sem mudança operacional. Escopo Mais: Doze,
  VIP (incluindo sua própria conveniência) e Casa Caiada. Associação Matera ainda
  depende de comprovação, sem vincular essa plataforma à 118508.

**Ordem de trabalho:**
1. Travas em 0 (diretor) e conferir o robô na noite seguinte (run PROD_SAFE_01 com AUDIT_COMPLETE).
2. PROD-RELEASE-01: aceitar a reconstrução semântica do estado local (é estado do robô, regenerado a cada noite)
   e isolar a produção numa pasta/versão aprovada, com testes isolados de tmp.
3. Sprint 20 — cupons sem vínculo (padrão por frentista/PDV/horário; somente leitura).
4. Mapeamento real (GET) das rotas V1 de conveniência e combustível (vendas/itens, estoque/extrato/contagem,
   compras, encerrante, tanque, LMC) em 1 posto + 1 loja.
5. Perguntas à Quality: POS integrado que falha (log, vincular depois), PIX no PDV, acesso Mais Pagamentos, débito OFX.

## MAIS-BANK-04 — saldo e repasses manuais/automáticos; relatório documental produzido, validação financeira pendente — 17/10/2026
- Branch `feature/cash-audit-fechamento`, repositório canônico conferido,
  HEAD `5bff018`. Relatório:
  [MAIS_BANK_04_BALANCE_AND_PAYOUT_MODEL.md](docs/validation/MAIS_BANK_04_BALANCE_AND_PAYOUT_MODEL.md).
- Correção obrigatória do dono aplicada: 118508 não usa Mais, não possui
  plataforma Mais pendente e foi retirada da matriz da etapa 03. Relatórios
  01/02/03 receberam anotação datada preservando a evolução das decisões.
  O trecho inicial do anexo 04 que dizia plataforma não confirmada foi
  superado pela confirmação posterior. Nenhuma configuração da unidade alterada.
- Informação nova: dono/operador pode solicitar repasse manual; rotina da Mais
  pode executar automático segundo configuração. Existência informada pelo dono,
  não execução auditada. Canal/perfis, instituição executora, conta/destino,
  regra, horário/fuso, frequência, mínimo/reserva, total/parcial, dias úteis e
  identificação do modo por evento ainda dependem da Mais/instituição.
- Fontes locais: STATUS e MAIS-BANK-01/02/03, regras de negócio, ADR-002/003,
  OpenAPI Mais/webPosto, modelos, conciliar.py, leitores OFX, persistência,
  pendências, tempo, SDK HTTP e guards OFX; documentação Asaas pública somente
  via evidência já reunida na etapa 02, sem nova consulta externa.
- Asaas documenta extrato/Pix/transferências/saldo disponível atual; conta
  Doze/BaaS, saldos históricos/cortes e distinção contábil/disponível/bloqueado
  ainda não validados. Matera/Fiserv seguem sem produto/custodiante/contrato
  aplicável de extrato/repasse comprovados. Associação Matera continua pendente.
- Modelo proposto, não implementado: saldo final = saldo inicial oficial +
  créditos efetivos − débitos efetivos, mesma conta/moeda/base/corte e cobertura
  integral; comparar ao saldo final oficial e explicitar resíduo. Não presumir
  abertura zero nem usar “PIX do dia − repasse do dia” como falta financeira.
  Conservação agregada não identifica composição de repasse de saldo fungível.
  Disponível, bloqueado, pendente, saída efetiva e crédito final são separados.
- Reaproveitamento: OFX/Decimal/proveniência, estados de fonte, JSON atômico,
  padrões SQLite, datas e relatórios existentes. _dias de cofre inicia em zero
  e usa espécie, portanto não fecha conta intermediária. Leitor OFX não guarda
  saldos oficiais e pode omitir linha sem data/sintetizar FITID: validar
  completude contra original antes de prova. Sem parser/conector paralelo.
- Riscos: tarifa já embutida não pode ser descontada novamente; débito/
  comprovante não provam crédito final; igual valor/data não prova vínculo.
  Extrato incompleto, repasse fracionado/rejeitado, estorno, intercompany e
  crédito posterior exigem pendência explícita, não perda ou sucesso presumido.
  Flags declaradas em 0 não são proteção universal: cartão verifica ambas,
  OFX usa outra segunda flag; SDK/proxies têm mutações sem guarda comum.
  Nenhum caminho foi executado ou corrigido.
- Próximo experimento (não executado): Doze, PIX de 14/10/2026 e observação
  14–16/10; solicitar titularidades, extrato intermediário completo, abertura/
  fechamento oficiais, créditos, eventual repasse/débito/tarifa/comprovante e
  extrato final. Se não houve transferência comprovada, saldo remanescente pode
  ser conclusão correta; extensão de janela só com aprovação.
- Perguntas sobre rotina, mínimos/reservas, execução/IDs/composição, status,
  reenvios, tarifas/retenções, saldos e acesso preparadas, não enviadas.
  Menor implementação posterior: normalização/fechamento local e relatório
  no módulo existente com testes, só após amostras e autorização específica.
- Somente documentação editada nesta etapa (relatório 04, correções anotadas
  nos 01/02/03 e STATUS); nenhuma chamada externa, acesso/alteração de .env,
  conta real, operação financeira, Telegram, job/agendador/produção, código,
  regra operacional, teste/aplicação, migração, deploy, commit, push ou merge.
  Alterações preexistentes preservadas. Parado aguardando aprovação.

## MAIS-BANK-03 — contas recebedoras, extratos e repasses; diagnóstico concluído — 17/10/2026
- Repositório/branch conferidos: `C:\Projetos\LOGOS\LogosPostos`,
  `feature/cash-audit-fechamento`; HEAD `5bff018` na conferência anterior à edição.
  Relatório: [MAIS_BANK_03_SOURCE_VALIDATION.md](docs/validation/MAIS_BANK_03_SOURCE_VALIDATION.md).
  Atualizações concorrentes do status/histórico preservadas; etapas 01/02 mantidas.
- Investigados separadamente Asaas, Matera e Fiserv, usando somente evidência
  local: relatórios 01/02, auditoria de capacidade (§9), regras, ADR-002/003,
  OpenAPI Mais/webPosto, units.json, modelos/proveniência, total Mais humano,
  leitores OFX, PIX/matching, persistência, adapters de escrita, SDK e proxies.
  Legado consultado apenas como referência; nenhum componente migrado.
- Mapa declarado pelo dono: Doze 74014/Asaas (“Posto Abreu e Lima”),
  VIP 11495 e Casa Caiada 5555/Fiserv. Correção posterior do dono em 17/10:
  Conveniência 24h 118508 não utiliza Mais; retirada da matriz, superada a
  pendência anterior, sem alteração operacional. Matera consta no ecossistema
  informado e no enum
  Mais, mas unidade/produto/custodiante e contrato aplicável não identificados.
  CNPJ/titularidade/contas e bancos finais de repasse: pendentes de validação;
  destinos configurados de espécie não comprovam repasse eletrônico.
- Capacidades documentadas: Mais lista/detalhe com E2E/bruto/líquido/taxa,
  consultas de saída Pix conhecida e logins distintos integração/PDV.
  Não encontrado extrato/saldo/lista de repasses Mais no contrato local;
  extrato do portal depende de confirmação. Autenticação 401 histórica não
  repetida. Asaas tem extrato/Pix/transferências/saldo conforme documentação
  pública reunida na etapa 02, não consultada novamente nesta etapa.
- Capacidades comprovadas são limitadas ao histórico ERP/OFX já registrado:
  vínculo interno transferência→movimento e leitura/importação com limites e
  incidente de sinais. Não há cadeia Mais→crédito intermediário→repasse→crédito
  final comprovada; total humano/sandbox/baixa ERP não são prova bancária.
  Fiserv não pode ser substituída por documentação genérica Hub Pix/adquirência;
  Matera não tem cliente/contrato local aplicável identificado.
- Travas declaradas pelo dono: `WEBPOSTO_WRITES=0`, `LOGOS_ERP_ESCRITA=0`;
  não verificadas no arquivo por este diagnóstico. Histórico de resolução e
  reprocessamentos acima preservado, sem reexecução/revalidação nesta etapa.
  Inspeção estática: cartão exige ambas; OFX usa WEBPOSTO_WRITES +
  LOGOS_OFX_IMPORTACAO; SDK/proxies/caminhos alternativos não compartilham a
  guarda. Gate de publicação do job não é bloqueio universal de escrita.
  Não tratar flags zeradas como proteção suficiente de todo o repositório.
- Riscos/lacunas: acesso BaaS Asaas não garantido por API pública; faltam
  produto/custodiante Matera/Fiserv, autorização por conta, extratos, IDs e
  composição de repasse. DONE na origem não certifica crédito final;
  valor/data/soma de PIX não comprovam composição de saldo fungível. Ausência
  de ID comum, fracionamentos, tarifas, devoluções e intercompany ficam pendentes.
  webPosto continua contexto ERP, sem origem bancária independente demonstrada.
- Recomendação: um piloto futuro Doze 74014, PIX de 14/10/2026 e observação
  financeira até 16/10/2026, sem presumir D+1 ou ocorrência de repasse.
  Primeiro obter pacote oficial Mais + Asaas + banco final e titularidades;
  ampliar período só com aprovação se insuficiente. Perguntas por fornecedor
  preparadas no relatório, não enviadas.
- Próxima etapa depende de autorização: validar manualmente amostras oficiais;
  menor implementação posterior seria normalização/proveniência e relatório
  no módulo existente com leitor OFX, sem novo conector ou arquitetura paralela.
  Acesso real, endurecimento dos caminhos de escrita e automação exigem escopo
  aprovado. Nenhuma implementação realizada.
- Nesta etapa: somente relatório MAIS-BANK-03 e STATUS.md editados; nenhuma
  chamada externa, leitura/alteração de .env, escrita financeira, conta real,
  Telegram, job/agendador/produção, teste/aplicação, migração, deploy, commit,
  push ou merge. Alterações preexistentes preservadas. Parado para aprovação.

## MAIS-BANK-02 — fontes de liquidação/repasse; diagnóstico concluído — 17/10/2026
- Branch `feature/cash-audit-fechamento`. Relatório curto:
  [MAIS_BANK_02_SETTLEMENT_SOURCES.md](docs/validation/MAIS_BANK_02_SETTLEMENT_SOURCES.md).
  Histórico MAIS-BANK-01 preservado; aprovação recebida só para investigação
  read-only, não para migração, implementação da conciliação ou produção.
- Fontes: matriz anterior, código financeiro oficial, contratos locais
  Mais/webPosto e documentação pública oficial Asaas/Fiserv/Software Express.
  Só páginas públicas foram acessadas; nenhuma conta/API financeira real.
- Asaas documenta GET financialTransactions (extrato com valor/saldo e
  paymentId/transferId), pix/transactions (E2E/status/data/taxa/payment),
  transfers (destino/valor/líquido/taxa/E2E/status) e finance/balance.
  Capacidade do fornecedor documentada, mas acesso à conta do Doze/subconta
  BaaS e vínculo real Mais → crédito → repasse ainda não comprovados.
- Fiserv: Hub Pix existe, mas produto contratado, custodiante/PSP e canal de
  extrato/repasse das contas VIP/Casa Caiada não identificados. Não presumir
  que Hub/SiTef ou API de adquirência ofereça extrato dessa conta.
- Banco final: leitor OFX/proveniência oficiais reutilizáveis; uso histórico
  BB/Bradesco/Itaú em espécie não comprova crédito de repasse Asaas/Fiserv.
  Faltam banco/conta/titular de destino e extratos/detalhes das duas pontas.
- Riscos: DONE da origem não prova crédito final; E2E cliente difere do
  repasse; saldo fungível não identifica composição do lote; mesmo valor/data
  não cria vínculo. ERP conciliado/usaOfx continuam sem prova independente.
  API key comum não deve ser presumida restrita à leitura.
- Recomendação: primeiro pacote documental Doze/Asaas → banco tradicional,
  com extrato intermediário, composição/ID do repasse, taxas e crédito no
  destino. Identificar produto/custodiante Fiserv em paralelo; não aperfeiçoar
  cliente Mais isolado nem criar arquitetura paralela.
- Próxima etapa: obter mapa CNPJ/contas e amostras oficiais autorizadas para
  validação manual, marcando agrupamentos/parcelamentos/ambiguidades pendentes.
  Consulta real ou implementação exige nova aprovação específica.
- Nesta etapa só relatório MAIS-BANK-02 e STATUS.md alterados; sem acesso a
  .env, contas reais, operação financeira, código, migração, job, commit,
  push ou merge. Alterações preexistentes preservadas. Parado no diagnóstico.

## MAIS-BANK-01 — investigação local concluída; implementação não autorizada — 17/10/2026
- Matriz de fontes, campos financeiros, evidências, lacunas e componentes
  reutilizáveis em [MAIS_BANK_01_SOURCE_GAP_MATRIX.md](docs/validation/MAIS_BANK_01_SOURCE_GAP_MATRIX.md).
- Comparados o projeto antigo do OneDrive e o oficial. Não foi encontrada
  cadeia comprovada por pagamento: Mais → crédito na conta Asaas/Fiserv →
  repasse identificado → crédito na conta bancária de destino.
- Cliente Mais antigo usa rotas não presentes no contrato local e fallback
  sandbox; serviço ainda pode preencher total ERP com baseline da adquirente.
  Não portar como integração real. A esteira de quatro vias procura método
  PIX que esse cliente não implementa.
- OpenAPI Mais oficial local oferece lista/detalhe de transações com E2E,
  bruto/pago/líquido/taxa e consultas de PIX de saída. Não foram encontrados
  ali extrato/saldo de conta ou listagem de repasses. ASAAS/FISERV no enum de
  última confirmação não comprovam consulta direta dessas contas.
- Mantido o bloqueio histórico de autenticação: 401 de 11/10 já registrado
  abaixo; não repetir sem credencial nova e autorização. Total Mais oficial
  permanece declaração humana, não coleta da API nem comprovação bancária.
- webPosto documenta GET V1/MOVIMENTOS_CONTA, V2/TRANSFERENCIAS_BANCARIAS e
  V1/CONTAS, além de POST V1/OFXS. Amostra antiga liga transferência a movimento
  do próprio ERP; não são evidências independentes. Não foi comprovada leitura
  segregada/rastreável de movimentos efetivamente importados do banco.
- usaOfx, conciliado e saldo ERP não certificam banco. O modelo de entrada OFX
  tem extratoExterno/dataCredito, mas o retorno de movimentos não os expõe
  como tais. Histórico de importação da conta 86188 mantém incidente de
  débitos errados; aceite HTTP não comprova sinal nem crédito efetivo.
- Reaproveitáveis sob revisão/aprovação: classificação Mais antiga, padrões
  OFX e comparação de lotes; priorizar leitor OFX e PagBank EDI já oficiais.
  Falta validar contas/titulares, crédito recebedor, referência de repasse,
  taxas e crédito no destino com fontes bancárias independentes.
- Apenas este relatório e STATUS.md alterados. Nenhuma chamada externa,
  leitura de .env, execução de integração/teste de aplicação, migração,
  escrita ERP, mudança de trava, commit, push ou deploy. Probe preexistente
  preservado. Próxima etapa somente com aprovação humana explícita.

## PROD-RELEASE-01 — PARADO no pré-check — 17/10/2026
- Branch `feature/cash-audit-fechamento`, HEAD `76cd8e2`; nenhuma implementação
  de release iniciada. Evidências em
  [PROD_RELEASE_01_VALIDATION.md](docs/validation/PROD_RELEASE_01_VALIDATION.md).
- Contagem reconciliada: 19 arquivos do PROD-SAFE-01 + 2 relatórios anteriores
  = 21 acumulados; probe preexistente excluído. `git diff --stat` sem novos
  mostra 16 rastreados. Inventário dos 21 registrado no relatório.
- Bloqueio: restauração anterior de estado/MD foi reconstrução semântica,
  não há baseline integral suficiente para provar bytes/metadados originais.
  Ressalva acrescentada ao relatório anterior, sem apagar histórico.
- Estado atual já foi atualizado pela tarefa de 17/10 às 03:00, referência
  16/10, auditoria falha e sem unidades; não foi sobrescrito. Log preexistente
  mostra bloqueio de configuração e envio ok; não foi execução desta tarefa.
- Teste CLI específico está em tmp, mas não existe guarda persistente geral
  contra gravações fora de temporários; runner isolado anterior foi removido.
  Garantia para testes futuros ainda não atendida; nenhum teste executado aqui.
- Produção continua no workspace, Python global; tarefa apenas consultada.
  Destino production inexistente; sem versão/tag proposta ou aprovada,
  manifesto, venv, deploy, health check ou rollback implementados.
- Próximo passo: recuperar backup autenticado ou obter decisão explícita
  sobre aceitar a reconstrução semântica; preparar isolamento reproduzível
  de testes antes de retomar release. Mudança real da tarefa depende de
  aprovação humana explícita e permanece não realizada.
- Apenas documentação nesta tarefa. Nenhum ERP write, integração externa,
  Telegram real, browser, commit, push ou merge; `.env` não lido/impresso/
  alterado, nenhuma trava modificada, escrita não habilitada.

## PROD-SAFE-01 — run integrity e publicação fail-closed — 16/10/2026
- Branch `feature/cash-audit-fechamento`; sem commit, push, merge ou deploy.
  Validação em [PROD_SAFE_01_RUN_INTEGRITY_VALIDATION.md](docs/validation/PROD_SAFE_01_RUN_INTEGRITY_VALIDATION.md).
- Causa raiz: envio desacoplado do resultado da coleta e releitura de snapshot
  do dia sem provar run/frescor. Incidente de 16/10 foi barreira local de
  configuração; não se comprovou relatório normal com números antigos.
- UUID criado antes das travas, propagado e persistido atomicamente por run,
  com início/fim, referência, estados de fonte/auditoria e motivo seguro.
  Legados seguem legíveis, mas não provam coleta atual.
- Gate valida run, data, timestamps e cobertura antes do resumo e do Telegram.
  FAILED/BLOCKED/STALE/NOT_COLLECTED obrigatórios impedem publicação financeira.
  EMPTY_VALID exige consulta bem-sucedida e contrato que permita vazio.
  Incompleto gera só aviso operacional, sem saldos, zeros financeiros ou XLSX.
- Fontes obrigatórias/degradáveis documentadas por fluxo; Premmia/Mais/OFX
  não viraram obrigações globais. Premmia antigo mantém timestamp e é omitido
  financeiramente; Mais preserva declaração original; OFX preserva hashes/
  cobertura. Placar agendado força coleta viva, sem fallback para cache.
- WEBPOSTO_WRITES deve ser exatamente `0`; configuração ausente/inválida e
  modo automático ativo bloqueiam com diagnóstico. Agendado não chama piloto
  automático/propostas de escrita; piloto manual não foi habilitado/alterado.
  Bootstrap absoluto via load_dotenv preservado; `.env` oficial não editado.
- AUDIT_COMPLETE/PARTIAL/FAILED separados de delivery das mensagens/documento;
  entrega de alerta não promove auditoria. Reenvio de MD tem rótulo histórico.
  Falha técnica/financeira retorna 1; entrega falha não rebaixa audit status.
- Testes ampliados offline: 611 aprovados, zero tentativas externas/browser;
  rodada final focada: 94 aprovados (sobreposta, não somar). Mypy: 11
  arquivos funcionais sem erros. Golden sintético inalterado:
  686,71 = 34,75 + 139,35 + 500,00 + 12,61. Frontend não alterado.
- Teste CLI legado foi isolado em tmp após gravação local de estado/MD de
  teste; estado anterior restaurado da evidência e MD vazio reconstituído.
  Nenhum lançamento, integração real ou Telegram real durante a validação.
- Riscos: freshness remota é prova de consulta corrente, não certificação
  interna do fornecedor; Mais/OFX continuam fontes locais explícitas, sem TTL
  inventado. Histórico e piloto manual fora do gate noturno. Produção ainda
  NÃO isolada; tarefa continua apontando ao workspace, sem alteração.
- Escrita segue congelada no job; nenhum raw financeiro/segredo copiado ao Git.
  Próximo passo recomendado: **PROD-RELEASE-01**.

## PROD-SAFE-00 — diagnóstico do job/frescor — 16/10/2026
- Branch `feature/cash-audit-fechamento`, base `76cd8e2`; diagnóstico concluído
  em [PROD_SAFE_00_JOB_FRESHNESS_DIAGNOSIS.md](docs/validation/PROD_SAFE_00_JOB_FRESHNESS_DIAGNOSIS.md).
- Inspecionados: composição `src/jobs/noturno.py`, wrapper/job de caixa,
  fechamento, recebimentos/conciliação, fontes da falta, persistência/saúde,
  Premmia, OFX, Mais, placar/cache, renderizadores, painel, utilitário Telegram,
  testes existentes, registrador e tarefa Windows, log/estado/ledger locais.
- Diagnóstico: **fail-closed na barreira de coleta; fail-open na composição
  resumo/envio quanto à completude e freshness**. Não é prova de escrita
  financeira fail-open. `main` tenta envio após retorno 1; exceção que escapa
  da coleta interrompe antes. Saída 0 também permite fontes degradadas.
- Falha de 16/10/2026: bloqueio local às 03:00 por condição
  `WEBPOSTO_WRITES != "0"` no modo não automático; não foi erro de fornecedor.
  Task iniciou 03:00:01 e terminou com resultado 1; ledger registra envio ok
  às 03:00:45. Não se consultou o valor/origem da variável.
- Evidência refina o risco: não havia snapshots de 15/10 e o MD local avisa
  conferência não realizada nas quatro unidades. Não se comprovou envio de
  relatório financeiro normal com dados antigos nesse episódio. O código,
  porém, aceita snapshot anterior do MESMO dia sem conferir idade/execução.
  Não troca automaticamente o dia 15 pelo 14 no Telegram.
- Gaps: sem gate de fontes obrigatórias/atuais antes do resumo ou Telegram;
  sem estados completos por fonte/auditoria. Frescor parcial (referência,
  proveniência, coleta Premmia, declaração Mais), não prova conjunta.
  Planilha pode zerar campos sem fechamento; ledger ok significa entrega de
  mensagens, não sucesso documental nem da auditoria.
- Recomendação mínima, NÃO implementada: gate e diagnóstico da tentativa atual,
  resultado/run ligado ao envio, publicar apenas aviso operacional quando
  incompleto; definir critérios de validade por fonte sem inventar TTL/regra.
  Só testar código de saída 0 é insuficiente por causa das degradações.
- Produção continua no workspace com Python global e logon Interactive.
  Isolamento futuro exige release/venv, ação/cwd aprovados, dados/segredos/logs
  preservados fora da release e smoke/rollback; nada movido ou reconfigurado.
- Nenhuma alteração funcional, execução de job/teste funcional, integração,
  write operacional/financeiro ou envio. `.env` não lido/alterado; nenhum raw
  financeiro/segredo copiado. Sem commit, push ou merge.
- Próximo passo sugerido: aprovar correção mínima do gate/frescor com testes
  offline de bloqueio, snapshot antigo, vazio válido e fonte degradada;
  depois planejar cutover isolado sem mudar regras financeiras.

## Auditoria de capacidades atuais — 16/10/2026 (somente leitura)
- Branch: `feature/cash-audit-fechamento`, base `76cd8e2`; sem merge.
  Entrega: [LOGOS_CURRENT_CAPABILITY_AUDIT.md](docs/validation/LOGOS_CURRENT_CAPABILITY_AUDIT.md).
  Apenas documentação; nenhuma correção/refatoração ou implementação funcional.
- Escopo analisado: Python versionados, entrypoints/routers, clientes/adapters,
  testes, configuração de unidades, persistência, scripts e tarefa Windows.
  Comparação estática com OpenAPI de 06/10/2026 e 23 entradas do registry antigo,
  usado só como catálogo, sem importar/copiar seu código ou políticas.
- Inventário: 200 declarações de rota em 30 arquivos (não simultaneamente
  publicadas), 101 na montagem principal, 176 chamadas com path /INTEGRACAO literal,
  156 paths na OpenAPI. Limites do AST e aliases detalhados no relatório.
- Capacidades com evidência operacional anterior: auditoria de caixa, contexto
  de vendas/cartões PagBank, parser OFX, portal Premmia nos casos conferidos,
  placar, comparação Mais via CLI e explicação da falta da Sprint 19.
  Isso não certifica todos os endpoints HTTP nem disponibilidade atual.
- Implementadas sem validação operacional completa: inclusão/compensação e nova
  tentativa do piloto, casamento positivo PIX CNPJ, receptores novos,
  fila Gemini/comprovantes ponta a ponta e integrações analíticas legadas.
  Cielo/Rede e coleta automática Mais não têm adapter de adquirente ativo.
- Achado operacional prioritário: tarefa real das 03:00 roda do workspace
  `C:\Projetos\LOGOS\LogosPostos\WebPosto_API`, não de release isolada.
  Argumento registrado usa módulo antigo que encaminha à composição nova.
  Em 16/10/2026: LastTaskResult=1; log mostra coleta bloqueada e marcador de envio
  Telegram. O código tenta envio mesmo após retorno de falha; envio ok não
  comprova dado fresco. Nenhuma tarefa foi alterada/reexecutada nesta auditoria.
- Golden case 14/10: teste sintético afirma a tabela 34,75 + 139,35 + 500,00 +
  12,61 = 686,71. Snapshot antigo persistido do mesmo dia não contém as novas
  fontes/campos e representa outro instante; não é replay integral desse resultado.
- Gaps reais: release/frescor/proveniência reproduzível; integração e validação V1
  de contagem/extrato/itens de entrada para conveniência e de equipamento/
  medição/descarga para combustível. A OpenAPI já documenta essas fontes.
- Riscos: produção no checkout, resumo após coleta bloqueada, evidência
  sobrescrita, escopos de extrato, versões de clientes e retries de escrita.
  Travas cartão/OFX não constituem congelamento universal dos proxies/wrappers.
- Decisões NÃO tomadas: arquitetura nova, deploy, correção, mudança de flags,
  autorização de lançamento, cadastro de tarefa, commit/push ou merge.
  Pendências/recomendações não foram implementadas.
- Próximo passo recomendado: isolar release aprovada e comprovar saúde/frescor
  do job das 03:00, reusando entrypoints/proveniência/testes; formalizar replay
  anonimizado do golden case antes de ampliar conveniência/combustível.
- Nenhum request externo, envio Telegram/Gemini, browser ou write operacional/
  financeiro executado. `.env` não foi lido, impresso ou editado; nenhum raw real
  foi copiado ao Git. Histórico 824 backend + 72 frontend da Sprint 19 preservado;
  não reexecutado nesta auditoria exclusivamente documental.

## Sprint 19 — Parte A
- Relatório, tela e resumo compartilham a decomposição da diferença de dinheiro
  por caixa, com fonte, venda, nome/código do frentista, correção e residual
  "Sem explicação". Candidatos ambíguos não explicam faltas.
- Vínculo ao caixa vem da venda oficial; não se distribui total entre caixas
  por suposição. O botão Lançar abre a revisão do piloto 18b, nunca confirma
  pelo relatório. Nenhum lançamento nem envio Telegram nesta sprint.

## Sprint 19 — Parte D e validação real
- Nova tentativa do mesmo NSU apenas com `--confirmar --nsu ... --nova-tentativa`,
  novo ok do diretor e todas as tentativas anteriores resolvidas como `nao_entrou`.
  Cada tentativa tem ação distinta, referência à anterior e reserva bruta própria;
  pendência não resolvida, NSU já existente e limites continuam bloqueando.
- PIX/BACEN usa administradora PIX PagBank ativa e única da lista oficial. Sem
  administradora ou com empate: conferir/lançar à mão. NSU e autorização continuam
  obrigatórios: não são inventados nem substituídos por outro identificador.
- Validação real Doze 14/10/2026: falta R$ 686,71 (não consolidado), Mastercard
  R$ 34,75 + PIX da maquininha R$ 139,35 + Mais Pagamentos R$ 500,00 +
  sem explicação R$ 12,61. Portal declarado R$ 10.741,86 × Transf. Crédito R$ 10.241,86.
- Extrato PIX CNPJ coberto: 0 clientes, 6 créditos de grupo/fornecedores excluídos.
  Administradora PIX PAGBANK existe, mas o PIX BACEN não informa NSU/autorização:
  a tabela orienta conferência manual, sem oferecer lançamento incompleto.
- Duas validações reais restritas por transporte a GET: 65 consultas cada; nenhum
  POST/DELETE, nenhuma coleta de portal Premmia e nenhum envio ao Telegram.
  `.env` somente via `load_dotenv`, sem impressão ou alteração.
- CLI real `src.jobs.mais_pagamentos_total --unidade 74014 --dia 14/10/2026 --total 10741,86`:
  saída 0, 14 GET, total salvo apenas localmente; nenhuma escrita no ERP/envio.
- Testes finais: 824 backend (`tests/unit` + `tests/services`) e 72 frontend aprovados.
  Avisos preexistentes de depreciação/JWT e módulo JavaScript mantidos.

## Sprint 18b — implementada; primeiro lançamento NÃO autorizado
- Prévia, painel e Telegram usam a mesma explicação em português simples e o mesmo
  serviço de confirmação/desfazer. Lançar/Não lançar só para diretor; gerente apenas lê.
- Cartão PagBank ausente, abastecimento único de mesmo valor em dinheiro, nota ≥ 90,
  caixa não consolidado/bloqueado, administradora unívoca, R$ 300/cartão e R$ 1.000/dia/posto.
- `python -m src.jobs.lancar_cartao --unidade 74014 --dia 14/10/2026` é somente prévia;
  confirmar exige `--confirmar --nsu <completo>`, duas travas físicas e novo ok do diretor.
- POST 201 não é sucesso: reconsulta NSU/venda/caixa/valor e dinheiro/cartão apurados.
  Se não confirmar, desfaz; falha/ambiguidade bloqueia repetição e exige conferência na tela.
- Auditoria persistente e trava por posto; botão Desfazer na aba Lançamentos do Logos.
  Resumo diário conta apenas lançamentos confirmados.
- Telegram: envio explícito por `src.jobs.telegram --propostas-cartao --unidade ... --dia ...`;
  conversa privada configurada via TELEGRAM_DIRETOR_CHAT_ID/USER_ID; botão expira em 24h.
  Usar um único consumidor do bot (`--ouvir-cartoes` ou o worker de comprovantes).
- Automático preparado no robô e DESLIGADO no exemplo (`LOGOS_CARTAO_AUTOMATICO=0`).
  Não editaram o `.env`, não houve envio Telegram nem lançamento real nesta sprint.
- O teste real do Mastercard R$ 34,75 de Ailton, Doze 14/10, continua aguardando
  aprovação específica do diretor e conferência das travas (WEBPOSTO_WRITES sem duplicata).
  Após qualquer teste real, voltar WEBPOSTO_WRITES e LOGOS_ERP_ESCRITA para 0.
- Validação: 445 testes da conciliação aprovados (48 regressões novas), 70 testes
  frontend e 5 do adaptador Telegram; nenhuma falha. Avisos preexistentes de
  depreciação/JWT/coverage mantidos. Texto do Ailton gerado pelo serviço real em
  prévia com somente GET, sem confirmar e sem criar tickets Telegram.

## Pronto
- Auditoria de fechamento FECHAMENTO_V4: quebra, falta sem desconto, caixa parado, despesas do caixa, reincidência;
  sangria sem conta da Conveniência 24h (repasse ao Casa Caiada) e do Casa Caiada (cofre) é informativa
- Recebimentos PagBank CARTOES_V2 (Doze 74014 e Casa Caiada 5555) com atribuição ao frentista e grupos prováveis
- Login por perfil (diretor/gerente/auditor), Painel do Diretor, placar de metas (VIP com metas de out/2026)
- Fila de pendências: vermelho individual, laranja agrupado por caixa/dia, prazo (vermelho 2 dias, laranja 5) e VENCIDAS
- Robô noturno agendado (03:00, tarefa "LOGOS - Auditoria de Caixa", modo -SemAdmin); credencial inválida = aviso, não falha
- Resumo diário pelo Telegram (bot @Weblogosbot, só o diretor): mensagem por filial com nomes + planilha .xlsx;
  TELEGRAM_ENVIO=1 desde 10/10/2026 (envio automático após o robô)
- Datas no padrão Brasil (America/Recife)
- **Sprint BAIXA_00 (Parte A — somente leitura):** identificação de títulos a pagar já quitados no banco por extrato (`titulos_pagos_sem_baixa.py`, `src/jobs/baixar_titulos.py`). Resolução de contas via `units.json` (BB 86248, PagBank 86188), deduplicação por FITID e detecção de pagamentos agrupados (tolerância ±15% no mês anterior).
- **Sprint DESPESAS_00 (Parte A & 00.1 — somente leitura):** identificação de despesas avulsas pagas na rua sem lançamento no ERP (`despesas_sem_lancamento.py`, `src/jobs/despesas_avulsas.py`). Deduplicação por FITID, filtro de grupo/aplicações/tarifas, reconhecimento de baixas agrupadas (`pagamento[]`), e reaproveitamento do casamento da BAIXA_00 (débito com título em aberto vai para "tem título em aberto — usar baixa", nunca avulso). Sugestão de plano/centro de custo e exportação XLSX.
- **Sprint DESPESAS_00 (Parte B — fila local, somente leitura no webPosto):** recepção de comprovantes pelo Telegram (`receber_comprovantes.py`) com escuta segura por whitelist do diretor (`TELEGRAM_CHAT_IDS`). Leitura multimodal via Gemini (`gemini_comprovantes.py`) para fotos, PDFs e áudios do diretor com transcrição e extração de entidades. Casamento com débitos dos extratos OFX (`processar_comprovante.py`), resolução de unidade pagadora, sugestão de plano de contas e centro de custo, e persistência em fila local `data/despesas_avulsas/fila.json` (status: "pronto para lançar", "a classificar", "sem extrato ainda"). Resposta interativa e amigável formatada para o bot Telegram. Zero gravações no webPosto.

## INCIDENTE EM ABERTO COM A QUALITY (11/10/2026) — OFX PagBank Doze 10/10 importado com débitos como crédito
- 11/10/2026: o DIRETOR EXCLUIU pela tela do webPosto os registros OFX de 10/10 da conta 86188 (sem Quality).
- Sprint 17B enviou pela API /V1/OFXS (conta 86188 PAGBANK DOZE FILIAL, dia 10/10/2026) 507 lançamentos: webPosto aceitou
  (201), mas a tela de conciliação mostrou Créditos R$ 132.804,13 e Débitos R$ 0,00 → os 8 débitos (R$ 64.847,35) entraram
  como crédito ("tipo":"Débito" não reconhecido). Os 499 créditos estão certos.
- **Sprint 17B.1 CONCLUÍDA — barreira reforçada e blindada:**
  1. Travas lidas EXCLUSIVAMENTE do arquivo `.env` via `dotenv_values` (ignora variáveis de processo, recusa duplicidade).
  2. Débito BLOQUEADO até confirmação formal pela Quality (`formato_tipo_debito_confirmado`, padrão ausente). Qualquer lote com débito é estritamente recusado.
  3. Anti-reenvio por `(cdConta, dia)` independentemente do arquivo/hash. Dia 10/10/2026 da conta 86188 marcado como "importado com débitos errados — aguardando correção" e bloqueado até liberação explícita auditada (`--liberar-dia`).
  4. Sucesso declarado apenas após conferência humana na tela de conciliação (`ENVIADO — CONFERIR NA TELA` e `--confirmar-conferencia`).
  5. Removidos atalhos fora do padrão (`WebPosto_API/adapters/` e `src/jobs/` na raiz).
- **Incidente permanece aberto** aguardando resposta da Quality sobre como débitos são reconhecidos na rota `POST /INTEGRACAO/V1/OFXS`. Nenhum envio contendo débito é autorizado.

## Ponto de parada (11/10/2026 ~15:30) — pausa pedida pelo diretor
- Sprints 15 (relatório do caixa do dia), 15.1 (dados atuais, status ✅/❌/⏳, Atualizar agora, duplicidade, Cartão POS,
  Amex = PagBank) e 15.2 (total do status sem dupla contagem) CONCLUÍDAS: 395e061, 4ff7673, 52f3b5e.
- Casos reais 10/10: Doze — cobrança em duplicidade Visa R$ 250,07 (19:12, sem estorno), falta R$ 34,80 (consolidado);
  Casa Caiada — tudo bate, falta R$ 14,71. 09/10: diretor lançou 4 cartões à mão no Casa Caiada → dinheiro esperado caiu
  R$ 128,75 (incluir cartão NÃO conta em dobro); falta final R$ 6,59, consolidado.
- Sangria Alberis 05/10 R$ 267,00 "Banco 24h": ficou no cofre (resposta do diretor) → corrigir a conta; regra nova de
  valor impossível no Banco 24h (cédulas 20/50/100/200) na Sprint 17.
- Prévia da tela nova (local, com nomes): WebPosto_API/data/previas/conferencia_do_dia.html — aguardando ajustes do diretor.
- **Sprint 18a CONCLUÍDA — porta de escrita de cartão isolada, desligada, com prévia e auditoria:**
  1. Porta isolada `POST /INTEGRACAO/V1/CARTOES` e `DELETE /INTEGRACAO/V1/CARTOES/{id}` (para desfazer) em `src/modules/cash_reconciliation/adapters/webposto_escrita_cartao.py`.
  2. Campos estritamente conforme a spec oficial da OpenAPI (`IncluirAlterarCartaoDto`). Sem PATCH.
  3. Dupla trava exigida EXCLUSIVAMENTE do arquivo `.env` físico via `dotenv_values` (`WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1`). Ignora variáveis de processo e recusa duplicatas.
  4. Resolução unívoca de administradora (Amex Doze e Casa Caiada = PagBank; sem ambiguidade).
  5. Montagem estrita a partir de proposta (exige NSU completo, autorização, administradora, venda, caixa, frentista, valor, data; falta de qualquer um recusa montagem).
  6. CLI `python -m src.jobs.lancar_cartao --unidade <cod> --dia dd/mm/aaaa` lista prévia elegível; `--confirmar` sempre recusa com "piloto não liberado (Sprint 18b)".
  7. Auditoria append-only em `data/lancamentos_logos/<empresa>/` (fora do Git) registrando o quê, evidências, autorização, payload sanitizado, resposta e como desfazer.
  8. Bateria completa: 330 testes passando (19 novos testes específicos de barreira de escrita de cartão).
- PRÓXIMO: Sprint 18b (1º lançamento controlado do piloto com o diretor acompanhando).
## Em andamento
- SPRINT_12 CARTOES_V3 (prompt pronto, não executado): mesmo NSU com valor diferente; cancelamentos do EDI
- PREMMIA_00 (VIP, 01 a 09/10/2026): login OK sem CAPTCHA (3 vezes); filtro de datas pela URL OK; tentativa 3 parou
  esperando a tabela. Próxima: exportar o .xlsx sem exigir a tabela (seção "Exportação XLSX" do prompt).
  Script: WebPosto_API/scripts/probe_premmia_portal.py (sem commit).
  ATUALIZAÇÃO 21:06: tentativa 4 OK — .xlsx exportado (89 pagamentos, 01 a 09/10). Crédito bate 100%.
  "Código Transação" do portal = nsu do V1/CARTOES (casamento por NSU funciona no Premmia).
  Achado: VIP 05/10 o mesmo NSU de PIX Premmia R$ 30 lançado em 2 vendas (23:04 e 23:09) → regra NSU repetido na CARTOES_V3.
  PREMMIA_01 (porte): arquivo por posto e mês, ex. data/premmia/postovip_10_2026.xlsx, acrescentando os dias coletados
  (decisão do diretor 10/10/2026); sem cópias por dia.
  "Desconto" do Premmia é RECEBÍVEL (a Vibra paga ao posto) — conciliar como as demais formas. Em 10/10/2026 o diretor
  cadastrou essa forma de recebimento no webPosto das filiais que não tinham; lançamentos até 09/10 seguem na forma antiga.

## Aguardando o diretor
1. Revisar e abrir o PR (descrição pronta em docs/status/PR_feature_cash_audit.md); merge na main só após revisão
2. Fornecedores: credencial PagBank da Conveniência 24h, documentação da Mais Pagamentos, EDI da Rede, credencial Cielo;
   perguntar à Vibra se há API/EDI do Premmia
3. Opcional: apagar a pendência sintética da unidade 321 do banco real

## Backlog (sprints futuras)
- METAS_02 — Metas de out/2026 do Doze e do Casa Caiada (adiado pelo diretor; aguarda Bronze/Prata/Ouro)
- Telegram: trocar a planilha (pequena no celular) por algo mais legível; tirar código interno do plano de contas;
  faltas confirmadas x provisórias; DESPESAS_V1 (valor alto, plano incompatível, acima da média)
- Integrações Mais Pagamentos, Rede, Cielo e PagBank Conv 24h (dependem dos fornecedores)
- MAIS_01 — Mais Pagamentos (PIX do VIP; no webPosto "Transferência Bancária"). Já existe no branch
  resgate/conciliacao-4-vias o cliente do Codex (src/gateway/mais_pagamentos_client.py): endpoints /v1/transactions e
  /v1/settlements e cabeçalhos X-Account-ID/X-Account-Key ADIVINHADOS (deram 401 em 07/10) e, pior, devolve dados
  FICTÍCIOS ("sandbox") quando falha → NÃO portar. Aproveitável: mais_pagamento_mapping.py (classificação PIX × transferência
  no webPosto, sem I/O). Credenciais por unidade já no .env (MAIS_PAGAMENTOS_ACCOUNT_ID_/KEY_<emp>). Bloqueio: documentação
  oficial da API ou exportação (portal/arquivo) da Mais Pagamentos. Mesmo padrão do Premmia se houver portal.
  ATUALIZAÇÃO 11/10/2026: API oficial pública encontrada (https://api.maispagamentos.com.br/webjars/swagger-ui.html;
  cópia em docs/external/maispagamentos/openapi_integracao_2026-10-11.json). Login: POST /usuarios/v1/login-integracao,
  form-urlencoded, Authorization Basic base64(id:chave), grant_type=client_credentials, scope=events → access_token.
  Transações: GET /transacoes/v1/{conta}?data-inicial&data-final&tipo-transacao=imediata (Bearer). Teste com as credenciais
  do VIP no .env: protocolo aceito, resposta "Credenciais incorretas" (401) → pedir à Mais Pagamentos o USUÁRIO DE
  INTEGRAÇÃO (client_id/secret), o scope correto e o código da "conta". Não repetir tentativas (risco de bloqueio).
  11/10/2026: 7 tentativas de login, todas 401 "Credenciais incorretas" (VIP normal/invertida/X-API-Key, genérica,
  Casa Caiada e as 2 combinações cruzadas genérica × 5555). NÃO TESTAR DE NOVO sem credencial nova gerada no painel
  da Mais Pagamentos (o diretor suspeita que a chave é regenerada).
- EXTRATOS_01 (adiante, decisão do diretor 11/10/2026) — captura automática dos extratos bancários/PagBank que chegam
  por e-mail, para confirmar recebimentos fora das maquininhas. Primeiro caso: PIX CNPJ do Doze (PIX pela chave do posto,
  direto na conta PagBank, sem maquininha — não aparece no EDI transacional). Doze 01–09/10: 7 lançamentos manuais
  · R$ 2.480,41 sem conferência hoje. Ver RN-CARTAO-009.
- Sprint 13 / 13.1 concluídas (commits 00c28d1, 8480d35): Premmia Casa Caiada 139 · R$ 14.909,55 conferidos, sobram
  2 · R$ 140,00; Doze 208 · R$ 16.582,25 conferidos, sobram 2 · R$ 14,00.
- 28 snapshots antigos ainda versionados; arquivar a pasta antiga do OneDrive

## Sprint 19 — Parte B
PIX CNPJ pelo OFX PagBank da conta da unidade, FITID único, exclusão de grupo/Vibra e
casamento um a um por valor/hora; cobertura e pendências persistidas no relatório.
Nenhuma escrita no webPosto e nenhum envio ao Telegram.

## Sprint 19 — Parte C
Total Mais Pagamentos declarado pelo diretor em JSON local atômico por unidade/dia;
CLI `src.jobs.mais_pagamentos_total` e entrada privada do mesmo diretor nos receptores
Telegram existentes (não executar dois pollings ao mesmo tempo).
Comparação apenas com `transfBanc` (Transf. Crédito), sem somar transferência débito.
Detalhe valor/hora procura venda em dinheiro; total sem detalhe não inventa frentista.
Nesta sprint os receptores não foram iniciados e nenhum envio foi realizado.

## Decisões fixas
Não trocar CONSUMER_TOKEN/ADMIN_TOKEN · conciliação de depósitos fora do escopo · somente leitura no ERP
· .env só via load_dotenv · metas só para postos · testes nunca gravam no banco real
· TODA ocorrência (pendência, tela, Telegram, planilha) mostra o NOME do frentista + código (decisão do diretor 10/10/2026);
  sem frentista identificável → "frentista não identificado" + motivo; nomes nunca no Git nem no chat dos agentes

## Retomada
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; Get-Content data\cash_audit\noturno.log -Tail 2; python -m uvicorn src.main:app --port 8000
Tela: http://localhost:8000/app/financial (login; Ctrl+F5 na primeira vez)
