# ARCH-MODULE-01 — Verificação da Organização Modular do Projeto

**Data:** 17/10/2026  
**Status:** Concluído — Read-Only Architecture Review  
**Branch:** `feature/cash-audit-fechamento`  
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`  
**Diretiva:** `REUSE > ADAPT > CREATE` (ADR-001 / ADR-002 / ADR-003)

---

## 1. Sumário Executivo

Esta auditoria avaliou a organização modular do repositório LOGOS com foco estrito no objetivo do produto:
> **Receber comprovante → reconhecer despesa → validar → aprovar → lançar efetivamente no webPosto.**

### Conclusão Principal
1. O LOGOS **não está modularizado de forma uniforme**. Coexistem três estratos históricos no repositório:
   - **Estrato 1 (Raiz legada):** scripts e módulos soltos na raiz (`servicos_auditoria.py`, `models_auditoria.py`, `api_webposto.py`, `webposto_client.py`, `src/`, `services/`).
   - **Estrato 2 (Camada horizontal de transição):** 42 serviços analíticos em `WebPosto_API/src/services/`, múltiplos clientes HTTP redundantes e schemas duplicados.
   - **Estrato 3 (Módulos verticais ativos):** `WebPosto_API/src/modules/` (`cash_reconciliation`, `commercial_performance`, `webposto_integration`), onde reside toda a evolução recente (Sprints 05 a 19, 611 testes automatizados).
2. O **Expense Hunter** já possui ~85% dos seus componentes implementados e testados, porém acomodados dentro do módulo vertical `cash_reconciliation` (especificamente em `application/despesas_sem_lancamento.py`, `processar_comprovante.py`, `fila_despesas.py`, `adapters/gemini_comprovantes.py` e `domain/comprovante.py`).
3. **Nenhum arquivo deve ser movido e nenhum módulo novo deve ser criado nesta etapa.**
   A movimentação prematura de arquivos quebraria imports e suítes de testes sem agregar valor funcional.
4. A **mudança mínima necessária** para completar o fluxo ponta a ponta é apenas criar um **adaptador isolado de escrita no webPosto** (`webposto_escrita_despesa.py`) com as guardas estritas do ADR-003, reutilizando a fila de revisão humana e a extração via IA existentes.

---

## 2. Mapa dos Módulos Reais

### 2.1. Estrutura em `WebPosto_API/src/`

| Diretório / Pacote | Natureza / Papel | Estado / Maturidade | Observações |
|---|---|---|---|
| `modules/cash_reconciliation/` | Módulo Vertical de Negócio | **Ativo / Canônico** (611 testes) | "God Module": concentra fechamento, sangrias, cartões, Premmia, Mais Pagamentos, conciliação OFX, e também o embrião completo de despesas avulsas e comprovantes. |
| `modules/webposto_integration/` | Integração Técnica com webPosto | **Ativo / Canônico** | Contém `http.py` (função `paginar` com cursor `ultimoCodigo` oficial V1, proteção anti-vazamento de chave `ARCH01`). Somente leitura (`GET`). |
| `modules/commercial_performance/` | Módulo Vertical de Negócio | Em consolidação | Vendas, abastecimento e performance comercial. |
| `jobs/` | CLI e Orquestrações de Tarefas | **Ativo / Canônico** | `receber_comprovantes.py` (listener Telegram), `despesas_avulsas.py`, `noturno.py`, `telegram.py`, `coleta.py`, etc. |
| `services/` (42 arquivos) | Camada Horizontal Analítica | Legado / Suporte | Contém serviços analíticos de despesas (`expenses_service.py`, 3 versões de classificadores, DRE, MDM fornecedores). Não é usado pelo robô noturno nem pela conciliação de caixa. |
| `gateway/` | Integração Legada com webPosto | Duplicação histórica | `WebPostoClient` alternativo com circuit breaker próprio, usando rotas genéricas. |
| `infrastructure/` | Infraestrutura Técnica | Misto | Subpastas `clients/`, `http/`, `webposto/`, `repositories/`, `cache/`. Múltiplos clientes HTTP concorrentes. |
| `domain/` | Domínio Horizontal Legado | Baixa coesão | Entidades genéricas e subpasta `adelaide/` (fiscal/combustíveis). |
| `application/` | Aplicação Horizontal Legada | Baixa coesão | Use cases antigos (`sync_all.py`, etc.). |
| `shared/` | Utilitários Transversais | Ativo | Notificações Telegram (`shared/notificacao/telegram.py`), helpers de data/tempo. |

### 2.2. A Duplicação Estrutural da Raiz (`C:\Projetos\LOGOS\LogosPostos`)

Além de `WebPosto_API/`, a raiz do repositório contém uma árvore paralela completa que gera confusão arquitetural:
- `main.py` e `app.py` na raiz (FastAPI paralelo).
- `src/` na raiz com `api/`, `application/`, `domain/`, `infrastructure/`.
- `services/financeiro_service.py` na raiz.
- `webposto/webposto.py` na raiz (24 KB).
- Scripts soltos: `servicos_auditoria.py`, `models_auditoria.py`, `models.py`, `webposto_client.py`, `api_webposto.py`.
- **Diagnóstico:** Esta árvore da raiz é remanescente de um estágio anterior do projeto ("NewWebLogos" / protótipo monolítico) e não é o alvo das sprints atuais (`WebPosto_API`).

---

## 3. Módulos Financeiros e Suas Responsabilidades

| Componente Financeiro | Localização | Responsabilidade Real |
|---|---|---|
| **Conciliação de Espécie e Caixa** | `WebPosto_API/src/modules/cash_reconciliation/application/auditar_fechamento.py`, `conciliar.py`, `relatorio_caixa_dia.py` | Auditoria de sangrias x depósitos em cofre/banco, faltas/sobras de frentistas, quebra de caixa. |
| **Conciliação de Cartões / Recebíveis** | `WebPosto_API/src/modules/cash_reconciliation/application/classificar_recebimentos.py`, `conciliar_cartoes.py`, `piloto_cartao.py`, `mais_pagamentos.py` | Cruzamento de vendas em cartão com extrato adquirente (PagBank EDI, Premmia Portal, Mais Pagamentos, TEF). |
| **Despesas Avulsas por Extrato** | `WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py` | Identificação de saídas bancárias (BB/PagBank) sem correspondência no ERP (`V1/TITULOS_PAGAR` e `V1/MOVIMENTOS_CONTA`), sugerindo plano de contas e centro de custo. |
| **Baixa de Títulos Quitados no Banco** | `WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py` | Identificação de títulos em aberto no ERP já debitados no extrato bancário (prevenção de duplicidade). |
| **Fila e Processamento de Comprovantes** | `WebPosto_API/src/modules/cash_reconciliation/application/processar_comprovante.py`, `fila_despesas.py` | Recepção de comprovantes/áudios, extração por IA, casamento com débitos OFX e fila de aprovação local. |
| **Centro Financeiro Corporativo (Analítico)** | `WebPosto_API/src/services/corporate_finance_center_service.py`, `corporate_cash_flow_service.py` | DRE consolidado, aging de títulos a pagar/receber, fluxo de caixa realizado/projetado. |
| **Classificadores de Despesas** | `WebPosto_API/src/services/logos_expense_classifier_v3.py` | Classificação heurística de despesas por palavras-chave em centros de custos e contas analíticas. |
| **Inteligência de Fornecedores** | `WebPosto_API/src/services/supplier_intelligence_service.py`, `supplier_mdm.py`, `supplier_segmentation.py` | Segmentação de gastos por fornecedor, matriz de custos e histórico cadastral. |

---

## 4. Componentes de Despesas: Localização e Responsabilidades

A busca pelo fluxo de despesas revelou que os componentes estão fragmentados entre a arquitetura ativa (`modules/cash_reconciliation`) e serviços soltos:

```
[ Telegram / Foto / PDF / Áudio ]
               │
               ▼
   receber_comprovantes.py (WebPosto_API/src/jobs/)
               │
               ▼
   processar_comprovante.py (WebPosto_API/src/modules/cash_reconciliation/application/)
       ├── gemini_comprovantes.py (WebPosto_API/src/modules/cash_reconciliation/adapters/) [IA / OCR]
       ├── extrato_reader.py (WebPosto_API/src/modules/cash_reconciliation/adapters/) [Leitura OFX]
       ├── despesas_sem_lancamento.py (WebPosto_API/src/modules/cash_reconciliation/application/) [Matching ERP/Extrato]
       └── fila_despesas.py (WebPosto_API/src/modules/cash_reconciliation/application/) [Persistência Local]
               │
               ▼
       fila.json (WebPosto_API/data/despesas_avulsas/)
               │
               ▼
       [ Revisão Humana / Aprovação Telegram / Painel ]  <─── (Ponto Atual)
               │
               ▼ (GAP DE ESCRITA)
       webPosto API (POST /V1/MOVIMENTOS_CONTA ou PATCH /V1/TITULOS_PAGAR/PAGAR)
```

### 4.1. Inventário Detalhado dos Componentes de Despesas

1. **Recepção e Extração de Comprovantes (IA):**
   - `WebPosto_API/src/modules/cash_reconciliation/adapters/gemini_comprovantes.py` (`GeminiExtractor`): Extrai valor, data, favorecido, CPF/CNPJ, chave PIX, banco/conta e transcreve áudios do diretor via `gemini-2.5-flash` / `gemini-1.5-flash`.
   - `WebPosto_API/src/modules/cash_reconciliation/domain/comprovante.py` (`DadosComprovante`, `ItemFilaDespesa`): Modelos tipados com Pydantic para os dados extraídos.
   - `WebPosto_API/src/jobs/receber_comprovantes.py`: Listener do Telegram em polling contínuo com whitelist de chat_id do diretor.
2. **Matching, Regras Contábeis e Classificação:**
   - `WebPosto_API/src/modules/cash_reconciliation/application/processar_comprovante.py`: Orquestra extração, casamento com extratos bancários locais e sugestão de plano de contas (ex: "pedreiro" → 198595, "piso" → 194968, "DARF" → 29128, etc.).
   - `WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py`: Analisa saídas bancárias reais, cruza com `V1/TITULOS_PAGAR` e `V1/MOVIMENTOS_CONTA`, ignora transferências internas e tarifas, e identifica saídas "na rua".
   - `WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py`: Cruza extratos com títulos em aberto para evitar que pagamentos com boleto/NF sejam relançados como avulsos.
3. **Fila e Revisão Humana:**
   - `WebPosto_API/src/modules/cash_reconciliation/application/fila_despesas.py`: Persistência atômica da fila de revisão em `WebPosto_API/data/despesas_avulsas/fila.json`.
   - `WebPosto_API/src/modules/cash_reconciliation/adapters/telegram_cartoes.py`: Suporte a callbacks do Telegram (botões de confirmação/revisão).
   - `WebPosto_API/src/modules/cash_reconciliation/adapters/pendencias.py`: Motor de pendências e auditoria com registro de intervenção humana.
4. **Lançamento no webPosto (Status Atual):**
   - **Inexistente para despesas.**
   - Existem apenas adaptadores de escrita para cartões (`webposto_escrita_cartao.py`) e extratos OFX (`webposto_escrita_ofx.py`), ambos blindados pelas travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0`.

---

## 5. Duplicações Comprovadas

A auditoria identificou três tipos de duplicação severa no repositório:

### 5.1. Clientes HTTP WebPosto (12 implementações concorrentes)
1. `WebPosto_API/src/modules/webposto_integration/http.py` (Oficial, seguro, paginação por cursor `ultimoCodigo`, utilizado por `cash_reconciliation`).
2. `WebPosto_API/src/gateway/webposto_client.py` (`class WebPostoClient`, com circuit breaker e permissions cache).
3. `WebPosto_API/src/infrastructure/webposto/client.py` (`class WebPostoClient`).
4. `WebPosto_API/src/webposto/client.py` e `WebPosto_API/src/webposto/http.py`.
5. `WebPosto_API/src/infrastructure/clients/webposto_client.py`.
6. `WebPosto_API/src/infrastructure/clients/gateway_webposto_client.py`.
7. `WebPosto_API/src/infrastructure/clients/posto_client_v1.py`.
8. `WebPosto_API/logos-webposto-gateway/src/infrastructure/webposto_client.py`.
9. `c:\Projetos\LOGOS\LogosPostos\webposto_client.py` (na raiz).
10. `c:\Projetos\LOGOS\LogosPostos\src\infrastructure\webposto\client.py` (na raiz).
11. `c:\Projetos\LOGOS\LogosPostos\webposto\webposto.py` (na raiz).
12. `c:\Projetos\LOGOS\LogosPostos\api_webposto.py` (na raiz).

### 5.2. Classificadores e Serviços de Despesas
1. `WebPosto_API/src/services/expenses_service.py` vs `despesas_sem_lancamento.py`.
2. `WebPosto_API/src/services/logos_expense_classifier.py` vs `logos_expense_classifier_v2.py` vs `logos_expense_classifier_v3.py` vs `processar_comprovante.py:sugerir_classificacao()`.
3. `WebPosto_API/src/services/financeiro_service.py` vs `c:\Projetos\LOGOS\LogosPostos\services\financeiro_service.py` vs `servicos_auditoria.py`.

### 5.3. Modelos de Entidades
1. Modelos de Unidade: `modules/cash_reconciliation/domain/models.py` (Unidade canônica) vs `domain/entities/` vs `models.py` da raiz vs `models_auditoria.py`.
2. Modelos de Despesas: `modules/cash_reconciliation/domain/comprovante.py` (`ItemFilaDespesa`, `DadosComprovante`) vs `models.py` da raiz (`Despesa`) vs `models_auditoria.py`.

---

## 6. Integração Oficial Compartilhada para o webPosto

### Diagnóstico da Integração
- **Existe integração oficial compartilhada para leitura (`GET`)?**
  **SIM.** O módulo `WebPosto_API/src/modules/webposto_integration/http.py` implementa a função `paginar(unidade, path, params, ...)`.
  - Ela é a única que atende à diretiva `ARCH01_SECRET_AUDIT_RUNBOOK.md` (suprime logs de chave pelo `httpx`, mascara parâmetros confidenciais).
  - Implementa o cursor `ultimoCodigo` da API V1 validado em produção.
  - É consumida por toda a suíte de conciliação de caixa e despesas (`cash_reconciliation/adapters/webposto_*.py`, `titulos_pagos_sem_baixa.py`, `despesas_sem_lancamento.py`).
- **Existe integração compartilhada para escrita (`POST`/`PATCH`/`DELETE`)?**
  **NÃO.**
  - A escrita foi implementada pontualmente por adaptadores isolados no módulo de reconciliação (`webposto_escrita_cartao.py` e `webposto_escrita_ofx.py`), seguindo a RN-ERP-002 e ADR-003.
  - Não existe conector de escrita para despesas (`POST /V1/MOVIMENTOS_CONTA` ou `PATCH /V1/TITULOS_PAGAR/PAGAR`).

---

## 7. Armazenamento de Dados, Snapshots e Logs: Separação de Código e Dados

| Tipo de Dado | Onde Está Armazenado | Avaliação de Risco e Separação |
|---|---|---|
| **Comprovantes (Fotos/PDFs/Áudios)** | `WebPosto_API/data/despesas_avulsas/comprovantes/` | **Correto:** pasta ignorada no Git (`WebPosto_API/data/`). |
| **Fila de Despesas JSON** | `WebPosto_API/data/despesas_avulsas/fila.json` | **Correto:** persistência append-only local fora do versionamento. |
| **Planilhas Geradas (XLSX)** | `WebPosto_API/data/despesas_avulsas/*.xlsx` | **Correto:** fora do Git. |
| **Extratos Bancários OFX** | `C:\Projetos\LOGOS\extratos\` | **Correto:** mantidos fora da pasta do repositório (ADR-002). |
| **Snapshots de Dados Reais** | `WebPosto_API/snapshots/` | **Atenção:** 28 snapshots históricos foram versionados no Git no passado. Novos snapshots estão bloqueados pelo `.gitignore`. |
| **Bancos SQLite e Arquivos Locais** | `WebPosto_API/logos_gateway.db`, `cache/` | **Risco:** `logos_gateway.db` está versionado na raiz de `WebPosto_API/`. |
| **Relatórios e Resultados Soltos** | Raiz de `WebPosto_API/` e raiz do repo (`.xlsx`, `.csv`, `.json`, `.log`) | **Inadequado:** arquivos como `VENDAS_DESPESAS_09_04_2026.xlsx`, `audit_expenses_webposto_result.json`, `reflex_run_debug.log` e `api.log` estão misturados com código-fonte. |

---

## 8. Riscos Reais de Dependências Circulares e Acoplamento

1. **Hipertrofia de `cash_reconciliation` (God Module):**
   - O módulo vertical `cash_reconciliation` acumula conciliação de espécie, auditoria de caixa, cartões, Premmia, Mais Pagamentos, baixa de títulos a pagar, despesas sem lançamento, recepção de comprovantes com Gemini, orquestração de fila e bot do Telegram.
   - *Risco:* Qualquer refatoração arriscada em dependências transversais pode desestabilizar os 611 testes existentes.
2. **Dependência do Bot Telegram:**
   - `WebPosto_API/src/jobs/receber_comprovantes.py` importa adaptadores de dentro de `cash_reconciliation` (`adapters/telegram_cartoes.py`), misturando fluxos de cartões e comprovantes na mesma escuta do bot.
3. **Ausência de Contrato Unificado de Escrita:**
   - Cada tipo de lançamento no webPosto reinventa seu mecanismo de segurança e retry em vez de consumir uma barreira de escrita compartilhada com governança de tenant e audit trail.

---

## 9. Matriz Arquitetural: Existente / Reutilizar / Adaptar / Criar

Aplicando estritamente **`REUSE > ADAPT > CREATE`**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CLASSIFICAÇÃO ARQUITETURAL                      │
├────────────────────────────────────────────────────────────────────────┤
│ 1. EXISTENTE & PRESERVAR (NÃO TOCAR, NÃO MOVER)                       │
│    - WebPosto_API/src/modules/cash_reconciliation/*                    │
│    - WebPosto_API/src/modules/webposto_integration/http.py             │
│    - WebPosto_API/src/jobs/receber_comprovantes.py                     │
│    - WebPosto_API/src/jobs/despesas_avulsas.py                         │
│    - WebPosto_API/data/despesas_avulsas/*                              │
│    - Testes unitários em WebPosto_API/tests/unit/cash_reconciliation/* │
│                                                                        │
│ 2. REUTILIZAR INTEGRALMENTE NO EXPENSE HUNTER                          │
│    - adapters/gemini_comprovantes.py (GeminiExtractor)                 │
│    - domain/comprovante.py (DadosComprovante, ItemFilaDespesa)         │
│    - application/fila_despesas.py (CRUD da fila JSON)                  │
│    - application/processar_comprovante.py (Orquestrador e Regras)      │
│    - application/despesas_sem_lancamento.py (Matching Extrato x ERP)   │
│    - application/titulos_pagos_sem_baixa.py (Prevenção de Duplicidade) │
│    - modules/webposto_integration/http.py (paginar GET)                │
│    - adapters/pendencias.py e propostas_lancamento.py (Revisão Humana) │
│                                                                        │
│ 3. ADAPTAR                                                             │
│    - application/fila_despesas.py / processar_comprovante.py:          │
│      Adicionar campos de controle de aprovação humana explícita        │
│      (status: "aguardando_aprovacao", "aprovado", "rejeitado",         │
│       "lancado_erp").                                                  │
│                                                                        │
│ 4. CRIAR SOMENTE SE NECESSÁRIO (EM FASE POSTERIOR DE ESCRITA)          │
│    - adapters/webposto_escrita_despesa.py:                             │
│      Adaptador isolado para POST /V1/MOVIMENTOS_CONTA (despesa avulsa) │
│      e PATCH /V1/TITULOS_PAGAR/PAGAR (baixa de títulos), com travas    │
│      WEBPOSTO_WRITES=1 e LOGOS_ERP_ESCRITA=1, limites de valor,        │
│      auditoria append-only e idempotência.                             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Organização Recomendada para o Expense Hunter

Conforme a diretiva arquitetural (`LOGOS_ARCHITECTURE_DIRECTIVE.md` § 5.3):
> *"Cash Hunter, Expense Hunter e outros Hunters são capabilities analíticas e operacionais que usam os bounded contexts relevantes. Não formam módulos de domínio independentes por padrão."*

### Onde deve residir o Expense Hunter?
1. **Fase Atual (Operação Imediata / Sprints Correntes):**
   - **Manter os arquivos onde já estão:** dentro de `WebPosto_API/src/modules/cash_reconciliation/` e `WebPosto_API/src/jobs/`.
   - **Justificativa:** Todos os 611 testes existentes passam nesses caminhos. Mover arquivos agora causaria quebra em cadeia de imports sem ganho para a entrega funcional.
2. **Entrada Operacional (CLI / Job):**
   - `WebPosto_API/src/jobs/receber_comprovantes.py` (para recepção contínua e interativa via Telegram).
   - `WebPosto_API/src/jobs/despesas_avulsas.py` (para conferência em lote por período e unidade).
3. **Evolução Futura (Somente quando formalmente aprovado o ADR de separação):**
   - Quando o monólito atingir maturidade e o ARCH-02 for retomado, a capability de despesas poderá ser agrupada sob `WebPosto_API/src/modules/financial_operations/` (ou `expense_management/`), extraindo-a de `cash_reconciliation`.
   - **Regra:** Essa movimentação só ocorrerá com script de migração de imports e validação total dos testes.

---

## 11. Mudança Estrutural Mínima para Lançar no webPosto

Para viabilizar a entrega final:
> **Receber comprovante → reconhecer despesa → validar → aprovar → lançar efetivamente no webPosto.**

A menor alteração física no repositório consiste em:

1. **Mover 0 arquivos.**
2. **Alterar 0 imports existentes.**
3. **Reutilizar 100% dos motores de reconhecimento, fila e matching já existentes.**
4. **Implementar 1 único adaptador de escrita isolado:**
   - Criar `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py`.
   - Implementar com dupla trava de segurança (`WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1`).
   - Somente permitir execução com aprovação humana explícita registrada na fila local (`data/despesas_avulsas/fila.json`).
   - Gravar registro append-only de auditoria em `WebPosto_API/data/lancamentos_logos/` com payload completo para possibilitar estorno manual na tela do webPosto em caso de divergência.
