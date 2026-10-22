# LOGOS — EXPENSE-04-PILOT-GATE: Verificação Final de Isolamento e Integridade Antes do Primeiro Lançamento Real

> **SUPERADO / NÃO AUTORIZA ESCRITA:** este documento registra uma avaliação histórica de 18/10/2026. Os checkpoints posteriores MASTER-DATA-04 e MASTER-DATA-05 prevalecem: a conta 27173 continua `TRANSITORIA`, `ACCOUNT RESOLUTION: BLOCKED` e `CASA CAIADA PILOT: BLOCKED`. A expressão “READY FOR SINGLE CONTROLLED WRITE” abaixo não representa o estado atual e não deve ser usada como autorização operacional.

**Data:** 18/10/2026 16:30  
**Repositório Oficial:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Prioridade:** P0 — Segurança Financeira e Isolamento Operacional  
**Classificação do Gate:** **READY FOR SINGLE CONTROLLED WRITE**  
**Escrita Real no ERP:** NÃO EXECUTADA NESTA ETAPA (Parar antes de qualquer escrita real)

---

## 1. Sumário Executivo e Veredito do Gate

Esta verificação de segurança (PILOT GATE) estabelece as garantias formais, operacionais e técnicas de que o **Expense Hunter** está apto para realizar **uma única escrita real assistida e controlada** no ERP webPosto, sem qualquer risco de contaminação cruzada com os demais subsistemas do LOGOS, com o job noturno das 03:00 ou com contas e empresas não autorizadas.

```
+----------------------------------------------------------------------------------------------------+
|                                    EXPENSE-04-PILOT-GATE                                           |
|                                                                                                    |
|   CLASSIFICAÇÃO: READY FOR SINGLE CONTROLLED WRITE                                                 |
|                                                                                                    |
|   [x] Isolamento de Configuração: caminho_env isolado (.env.piloto), sem tocar no .env principal   |
|   [x] Isolamento do Job Noturno: WEBPOSTO_WRITES=0 e LOGOS_ERP_ESCRITA=0 mantidos no .env raiz     |
|   [x] Isolamento de Módulos: nenhum outro módulo ou processo recebeu novas permissões de escrita    |
|   [x] Autorização Fina Criptográfica: Token atômico de uso único (SHA-256) com match em 8 dimensões |
|   [x] Allowlist Imutável: Doze (74014), VIP (11495), Casa Caiada (5555), Conv 24h (118508)         |
|   [x] Posto Real Excluído: Códigos 5558 e 7 bloqueados sumariamente no adaptador                   |
|   [x] Bloqueio Cruzado: Conv 24h (118508) estritamente impedida de debitar conta 17837 (Casa Caiada)|
|   [x] Anti-Retry em Timeout: RESULTADO_DESCONHECIDO bloqueia reenvio até reconciliação manual       |
|   [x] Validação Offline: 102 testes focados de despesas e 659 de regressão global APROVADOS (100%) |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Verificação de Arquivos e Git

### 2.1. Inspeção de Status (`git status --short`)

A execução de `git status --short` no repositório `C:\Projetos\LOGOS\LogosPostos` confirma:

```
 M STATUS.md
 M WebPosto_API/src/jobs/receber_comprovantes.py
 M WebPosto_API/src/modules/cash_reconciliation/application/fila_despesas.py
 M WebPosto_API/src/modules/cash_reconciliation/application/processar_comprovante.py
 M WebPosto_API/src/modules/cash_reconciliation/domain/comprovante.py
 M WebPosto_API/src/shared/notificacao/telegram.py
 M WebPosto_API/tests/unit/cash_reconciliation/test_comprovantes_fila.py
?? WebPosto_API/scripts/probe_premmia_portal.py
?? WebPosto_API/src/modules/cash_reconciliation/adapters/telegram_despesas.py
?? WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py
?? WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py
?? WebPosto_API/tests/unit/cash_reconciliation/test_telegram_despesas.py
?? WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_despesa.py
?? docs/architecture/ARCH_MODULE_01_CURRENT_STRUCTURE.md
?? docs/validation/EXPENSE_01_VALIDATION.md
?? docs/validation/EXPENSE_02_TELEGRAM_APPROVAL_VALIDATION.md
?? docs/validation/EXPENSE_03_ERP_WRITE_ADAPTER_VALIDATION.md
?? docs/validation/EXPENSE_04_PRECHECK_VALIDATION.md
?? docs/validation/EXPENSE_API_CONTRACT_CHECK.md
?? docs/validation/EXPENSE_AUDIT_01_CURRENT_STATE.md
?? docs/validation/MAIS_BANK_01_SOURCE_GAP_MATRIX.md
?? docs/validation/MAIS_BANK_02_SETTLEMENT_SOURCES.md
?? docs/validation/MAIS_BANK_03_SOURCE_VALIDATION.md
?? docs/validation/MAIS_BANK_04_BALANCE_AND_PAYOUT_MODEL.md
```

### 2.2. Inspeção de Diff (`git diff --stat`)

```
 STATUS.md                                          | 428 ++++++++++++++-
 WebPosto_API/src/jobs/receber_comprovantes.py      |  36 +-
 .../application/fila_despesas.py                   | 185 ++++++-
 .../application/processar_comprovante.py           | 393 ++++++++++----
 .../cash_reconciliation/domain/comprovante.py      | 148 +++++-
 WebPosto_API/src/shared/notificacao/telegram.py    |  15 +-
 .../cash_reconciliation/test_comprovantes_fila.py  | 580 ++++++++++++++++++++-
 7 files changed, 1668 insertions(+), 117 deletions(-)
```

### 2.3. Esclarecimento Mandatório: Por que o `git diff` não lista todos os novos arquivos?

O comando `git diff` e `git diff --stat` compara exclusivamente as modificações realizadas em **arquivos rastreados (tracked files)** que já pertenciam ao histórico da branch `feature/cash-audit-fechamento`.

Os novos componentes desenvolvidos ao longo dos incrementos EXPENSE-02, EXPENSE-03 e EXPENSE-04:
- `WebPosto_API/src/modules/cash_reconciliation/adapters/telegram_despesas.py`
- `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py`
- `WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py`
- `WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_despesa.py`
- `WebPosto_API/tests/unit/cash_reconciliation/test_telegram_despesas.py`
- Documentos de arquitetura e validação em `docs/`

são **arquivos novos e não rastreados (untracked files, `??`)**. Em cumprimento estrito à restrição de segurança e governança de auditoria (*"Não fazer commit, push ou merge"*), nenhum `git add` ou `git commit` foi executado. Consequentemente, eles não constam no índice Git (`git diff`), mas estão **100% presentes no disco, localizados em seus diretórios canônicos e validados por todos os testes unitários**.

### 2.4. Arquivos Ignorados e Segurança do Repositório (`.gitignore`)

O arquivo `.gitignore` do projeto assegura isolamento permanente de dados e credenciais:
- `*.env`, `.env`, `.env.*`, `**/*.env`: impede qualquer commit de arquivos de credenciais e segredos (incluindo o futuro `.env.piloto`);
- `*.db`: impede o commit de bases SQLite locais;
- `data/`, `WebPosto_API/data/`, `data/lancamentos_logos/`: isola completamente os bancos operacionais de idempotência e auditoria de escrita de despesas;
- `WebPosto_API/snapshots/`: preserva relatórios operacionais sem expô-los ao Git.

### 2.5. Confirmação dos Componentes Essenciais

| Componente | Localização Física | Status de Presença |
| :--- | :--- | :--- |
| `GerenciadorAutorizacaoPiloto` | `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py:429` | **Confirmado** |
| `test_expense_04_precheck.py` | `WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py` | **Confirmado (22 testes)** |
| `webposto_escrita_despesa.py` | `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py` | **Confirmado (1305 linhas)** |
| Registros de Autorização | Tabela `autorizacoes_piloto` criada no SQLite via `GerenciadorAutorizacaoPiloto._inicializar` | **Confirmado** |
| Registros de Idempotência | Tabelas `idempotencia_despesas` e `tentativas_lancamento` via `IdempotenciaDespesas._inicializar` | **Confirmado** |

---

## 3. Isolamento Estrutural do Piloto

O mecanismo do piloto foi arquitetado para blindar completamente o ambiente de produção existente:

```
[ Job Noturno 03:00 ] ---> Lê .env (raiz) [WEBPOSTO_WRITES=0] ---> Bloqueio Total (PROD-SAFE-01)
[ Conciliação Cartões ] ---> Lê .env (raiz) [LOGOS_ERP_ESCRITA=0] ---> Somente Leitura
[ Conciliação OFX ]     ---> Lê .env (raiz) [WEBPOSTO_WRITES=0]   ---> Somente Leitura

[ Piloto Controlado ]   ---> Lê config/.env.piloto [caminho_env] ---> Valida Token Criptográfico (8D)
                             + Trava de Idempotência
                             + Allowlist Imutável (4 empresas)
                             + Validação Estrita Empresa x Conta
                             ===> 1 ÚNICA ESCRITA AUTORIZADA
```

### 3.1. Configuração Própria e Isolada (`caminho_env`)
O adaptador de escrita aceita o parâmetro opcional `caminho_env: Path | str | None`:
- Na chamada do piloto, o executor carregará explicitamente `caminho_env="config/.env.piloto"`.
- O arquivo `.env` principal na raiz do repositório **NÃO é alterado nem consultado** para habilitar escritas.

### 3.2. Bloqueio Garantido do Job Noturno das 03:00
O job das 03:00 (`run_noturno.bat` acionado pelo Windows Task Scheduler) é executado no diretório raiz do repositório. Ele carrega automaticamente as variáveis de ambiente do `.env` da raiz.
- No `.env` raiz: `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0`.
- A trava corporativa **PROD-SAFE-01** do job noturno verifica `WEBPOSTO_WRITES`. Se for diferente de `"0"`, o job aborta para evitar escritas descontroladas.
- Como o piloto não toca no `.env` da raiz, o job das 03:00 continuará rodando com escritas 100% bloqueadas.

### 3.3. Nenhum Processo Existente Recebe Novas Permissões
Nenhum módulo legado (cartões de crédito, OFX, conciliação de fechamento) possui importação ou dependência de `GerenciadorAutorizacaoPiloto` ou de `executar_lancamento_despesa`. Esses processos permanecem inalterados e restritos ao modo leitura.

### 3.4. Preservação dos Bancos SQLite do Piloto
A base de idempotência e de autorizações do piloto reside em:
`C:\Projetos\LOGOS\LogosPostos\data\lancamentos_logos\idempotencia_despesas.db`
- Opera com `PRAGMA journal_mode=WAL` (Write-Ahead Logging) e `PRAGMA busy_timeout=5000` para tolerância a falhas.
- Todas as validações e consumos de token utilizam transações estritas `BEGIN IMMEDIATE` com rollback garantido em caso de qualquer divergência ou erro.
- O diretório `data/lancamentos_logos/` é ignorado no Git, garantindo que o banco de dados não seja sobrescrito por operações de checkout ou merge.

### 3.5. Proibição de Redirecionamento Arbitrário de Empresas ou Endpoints
- **Endpoints Fechados:** O adaptador não aceita injeção dinâmica de URLs. Os endpoints são constantes literais e mapeadas diretamente da OpenAPI V1 do webPosto:
  - `POST /INTEGRACAO/V1/TITULOS_PAGAR`
  - `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`
  - `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR`
  - `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA`
  - `POST /INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}`
  - `POST /INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{id}`
- **Allowlist Fechada:** A função `validar_unidade_autorizada` valida o código da empresa contra o conjunto imutável `EMPRESAS_AUTORIZADAS_SET = frozenset({74014, 11495, 5555, 118508})`. Qualquer outro identificador levanta `BarreiraDespesaErro` antes de abrir conexão HTTP.

---

## 4. Autorização Individual e Token Atômico (8 Dimensões)

O `GerenciadorAutorizacaoPiloto` implementa uma barreira criptográfica intransponível. A escrita só é autorizada se o token fornecido casar perfeitamente em 8 dimensões verificadas atomicamente dentro de uma transação SQLite `BEGIN IMMEDIATE`:

| Dimensão Verificada | Regra de Bloqueio | Comprovação por Teste Unitário |
| :--- | :--- | :--- |
| **1. Identificador da Despesa** | `op_id != item.id` | `test_05_aprovacao_de_uma_despesa_nao_autoriza_outra` |
| **2. Empresa Autorizada** | `emp_cod != item.unidade_codigo` | `test_06_empresa_alterada_apos_aprovacao` |
| **3. Tipo de Operação** | `tp_op != item.operacao_financeira` | `test_09_operacao_alterada_apos_aprovacao` |
| **4. Valor Exato** | `abs(val - item.comprovante.valor) >= 0.001` | `test_08_valor_alterado_apos_aprovacao` |
| **5. Hash Aprovado** | `h_apr != item.aprovado_hash` | `test_webposto_escrita_despesa.py:test_11_hash_diferente` |
| **6. Conta Financeira** | `c_cod is not None and c_cod != conta_efetiva` | `test_07_conta_alterada_apos_aprovacao` |
| **7. Uso Único (Anti-Replay)** | `cons_em is not None` | `test_11_token_piloto_reutilizado` |
| **8. Prazo de Expiração (TTL)** | `agora_iso > exp_em` (máx. 30 minutos) | `test_10_token_piloto_vencido` |

Qualquer divergência em qualquer uma dessas dimensões gera `ROLLBACK` imediato e aborta a execução sem emitir nenhuma chamada externa de rede.

---

## 5. Matriz de Contas e Empresas

### 5.1. Mapeamento Oficial Comprovado

Baseado nas fontes canônicas do projeto (`units.json`, `financial_origin_matrix.json` e OpenAPI V1):

| Filial / Unidade | Código Oficial (`empresaCodigo`) | Contas Financeiras Autorizadas | Restrições Específicas |
| :--- | :---: | :--- | :--- |
| **Posto Doze Filial II** | `74014` | `{86248, 86081, 86188}` | Mapeadas no webPosto |
| **Posto VIP** | `11495` | `{65321, 55028}` | Mapeadas no webPosto |
| **AP Casa Caiada** | `5555` | `{17837}` | Conta "CAIXA(POSTO)" vinculada estritamente à filial 5555 |
| **Conveniência 24 Horas** | `118508` | `frozenset()` (nenhuma) | **Bloqueio total de débito direto.** Permitida apenas `NOVA_CONTA_A_PAGAR` |
| **Posto Real** | `5558` / `7` | **EXCLUÍDO** | Bloqueado sumariamente via `validar_unidade_autorizada` |

### 5.2. Regra Específica da Conta `17837` (Casa Caiada × Conveniência 24h)
- A consulta cadastral oficial (`GET /INTEGRACAO/V1/CONTAS`) demonstra que a conta `17837` pertence exclusivamente à empresa `5555` ("AP CASA CAIADA").
- A Conveniência 24 Horas (`118508`) tem `destinos.conta_codigo = null` e repassa o numerário fisicamente ao Posto Casa Caiada.
- **Decisão de Segurança:** Uma filial não pode lançar débito direto em conta contábil/financeira de outra filial. O código `CONTAS_AUTORIZADAS_POR_UNIDADE[118508] = frozenset()` garante que qualquer tentativa da Conveniência 24h de debitar a conta `17837` resulte em:
  `BarreiraDespesaErro: Empresa 118508 não possui conta financeira própria autorizada para movimentação direta.`

---

## 6. Condições de Bloqueio e Reconciliação (Anti-Duplicidade)

O adaptador trata rigorosamente qualquer anomalia operacional durante o ciclo de escrita:

1. **Timeout em Requisição HTTP (POST ou PATCH):**
   - Transita a chave de idempotência para `RESULTADO_DESCONHECIDO` no SQLite com log da tentativa.
   - O método `iniciar_operacao` passa a recusar novas tentativas para a mesma despesa com a mensagem:
     `Operação já executada com resultado inconclusivo. Exige verificação manual no webPosto antes de novo envio.`
2. **Resposta HTTP Inconclusiva ou 201 sem Identificador:**
   - Se o webPosto responder 201/200 sem retornar o ID gerado, a escrita entra em `RESULTADO_DESCONHECIDO`.
3. **Falha ou Ambiguidade na Confirmação Pós-Escrita:**
   - `confirmar_movimento_conta` realiza uma consulta `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA`.
   - Se encontrar zero registros compatíveis ou **mais de um registro compatível no mesmo dia com o mesmo valor**, a confirmação é recusada por ambiguidade, evitando vincular comprovantes ao lançamento errado.
4. **Falha no Upload de Anexos:**
   - O upload do comprovante é desacoplado do lançamento financeiro. Caso o anexo falhe, o lançamento financeiro já registrado no ERP é mantido, o anexo é marcado como pendente e a operação **não é reenviada**.

---

## 7. Evidências dos Testes Automatizados

A integridade de todas as barreiras foi comprovada por **102 testes unitários focados no módulo de despesas** e **659 testes de regressão global**:

```bash
# Execução dos 22 testes de segurança mandatória EXPENSE-04-PRECHECK:
pytest WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py -v
Resultado: 22 passed in 2.42s (100% sucesso)

# Execução dos 73 testes dos adaptadores de escrita e do Telegram:
pytest WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_despesa.py WebPosto_API/tests/unit/cash_reconciliation/test_telegram_despesas.py -v
Resultado: 73 passed in 20.53s (100% sucesso)

# Execução dos 29 testes da fila de despesas e anti-duplicidade:
pytest WebPosto_API/tests/unit/cash_reconciliation/test_comprovantes_fila.py -v
Resultado: 29 passed in 11.51s (100% sucesso)

# Regressão global de reconciliação:
pytest WebPosto_API/tests/unit/cash_reconciliation/ -v
Resultado: 659 passed, 0 failed, 0 skipped
Isolamento de Rede: 0 chamadas externas reais realizadas (Isolamento Premmia: 0 tentativas reais de navegador/portal).
```

---

## 8. Checklist Obrigatório para o Primeiro Lançamento Real

Para executar o primeiro lançamento piloto assistido, o operador deverá seguir estritamente o seguinte procedimento:

1. [ ] **Ambiente Isolado:** Criar `config/.env.piloto` contendo exclusivamente as credenciais necessárias da unidade do teste e `WEBPOSTO_WRITES=1`. O arquivo `.env` principal na raiz deve permanecer com `WEBPOSTO_WRITES=0`.
2. [ ] **Seleção da Despesa Piloto:** Selecionar um comprovante real de baixo valor (ex.: despesa de valor reduzido, R$ 10,00 a R$ 50,00) em uma das unidades homologadas (recomendado: Posto Doze `74014`).
3. [ ] **Aprovação Telegram:** O diretor aprova a proposta gerada pelo robô do Telegram, gerando o ticket e a assinatura `aprovado_hash`.
4. [ ] **Emissão do Token de Piloto:** Gerar o token no SQLite via `GerenciadorAutorizacaoPiloto.criar_autorizacao(...)` vinculando os 8 parâmetros exatos e TTL de 15 minutos.
5. [ ] **Execução Assistida:** Executar o script do piloto passando `caminho_env="config/.env.piloto"` e `autorizacao_piloto_token=token`.
6. [ ] **Conferência Presencial no webPosto:** Acessar a interface visual do ERP webPosto e conferir se o título/movimento foi registrado com exatidão (valor, plano de contas, histórico e anexo).
7. [ ] **Consumo do Token:** Confirmar que o token foi marcado como consumido no banco de dados SQLite e não pode ser reutilizado.

---

## 9. Veredito Final

O subsistema Expense Hunter cumpre todos os requisitos de segurança defensiva, isolamento de processos e integridade contábil.

**Classificação Oficial:** **READY FOR SINGLE CONTROLLED WRITE**  
*(Autorizado para execução de 1 única escrita piloto assistida, mediante autorização do diretor e observância do checklist acima).*
