# LOGOS — EXPENSE-03: Relatório de Validação dos Adaptadores de Lançamento no webPosto

**Data:** 18/10/2026 10:15  
**Branch:** `feature/cash-audit-fechamento`  
**Status:** CONCLUÍDO COM SUCESSO (28 testes de escrita + 23 testes Telegram + 29 testes fila = 80 testes do módulo aprovados; 637/637 na regressão completa)  
**Modo:** READ ONLY — Nenhuma chamada externa, nenhuma escrita ERP real, nenhuma transação bancária, `.env` não alterado, travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` estritamente mantidas.

---

## 1. Missão e Resumo da Entrega

A missão do **EXPENSE-03** é implementar o adaptador técnico de integração para lançamento seguro de despesas no webPosto após aprovação humana:
**Comprovante → reconhecimento automático → conferência → aprovação Telegram → preparação da operação → lançamento webPosto → confirmação → evidência.**

### Princípios Rigorosamente Aplicados:
1. **REUSE > ADAPT > CREATE:** Reutilizou o padrão de barreira física de `.env` (`DotEnvTravas`), mascaramento de credenciais (`mensagem_segura`), persistência append-only e contratos da OpenAPI V1 já verificados.
2. **Nenhuma Escrita Prematura ou Irrestrita:** O adaptador opera com travas estritas no `.env` físico. Toda execução sem as duas flags em `1` levanta `BarreiraDespesaErro`.
3. **Validação da Empresa e Resolução da Divergência (P0):** Código oficial de Casa Caiada confirmado como `5555`. Bloqueio estrito de códigos espúrios (`12607` e `12705`).
4. **Exclusão Estrita do Posto Real do Escopo (EXPENSE-03-SCOPE-FIX):** Posto Real (`empresaCodigo 5558 / codWeb 7`) possui CNPJ desativado/inativo e foi substituído operacionalmente pelo Posto Doze Filial II (`74014`). O dono determinou que o Posto Real **NÃO faz parte do escopo atual do Expense Hunter**. Implementado bloqueio ponta a ponta: excluído de botões de correção do Telegram, bloqueado em callbacks diretos, rejeitado na verificação de aprovação do domínio, descartado na ingestão e sumariamente recusado no adaptador de escrita (mesmo se presente em cadastros externos).
5. **Idempotência Local e Exclusão Mútua:** Bloqueio atômico em SQLite (`IdempotenciaDespesas`) para impedir envios simultâneos ou duplicados.
6. **Tratamento de Timeout sem Retry Automático:** Timeout após envio registra `RESULTADO_DESCONHECIDO` e proíbe reenvio automático sem reconciliação.
7. **Confirmação Pós-Escrita:** Validação de retorno (201 para título e confirmação via consulta `GET /MOVIMENTOS_CONTA` e `GET /TITULOS_PAGAR` para movimentos e baixas).
8. **Isolamento de Anexos:** Falha no upload de anexo digital não reverte nem repete o lançamento financeiro original.

---

## 2. Bloqueio P0 — Identificação de Empresas e Escopo Autorizado

### Investigação e Descoberta:
- **Origem dos números `12607` e `12705`:** A investigação minuciosa no repositório comprovou que `12607` e `12705` eram fragmentos de NSU de cartões de crédito em transações auditadas (`212607388` e `101270524784` em arquivos de fechamento de caixa). Esses números foram erroneamente digitados como exemplos no texto descritivo do relatório EXPENSE-02, mas **nunca** existiram como códigos de empresa no webPosto.
- **Cadastro Canônico do webPosto:** Confirmado nas fontes primárias (`audit_filial_master_resultado.json`, `docs/webposto_mapping.md` e `units.json`):
  - `5555`: **AP CASA CAIADA** (`empresaCodigo: 5555`, CNPJ `04.284.939/0001-86`) — **AUTORIZADA**
  - `11495`: **POSTO VIP** (`empresaCodigo: 11495`, CNPJ `03.008.754/0001-86`) — **AUTORIZADA**
  - `74014`: **POSTO DOZE FILIAL II** (`empresaCodigo: 74014`, CNPJ `52.308.604/0002-84`) — **AUTORIZADA**
  - `118508`: **CONVENIENCIA 24 HORAS** (`empresaCodigo: 118508`, repasse sangria para 5555) — **AUTORIZADA**
  - `5558` (ou codWeb 7): **POSTO REAL** (`empresaCodigo: 5558`) — **FORA DE ESCOPO / BLOQUEADO** (CNPJ desativado/inativo)
- **Regras de Bloqueio Implementadas:**
  1. **Posto Real (5558 / codWeb 7):** Bloqueio estrito implementado em todas as camadas do Expense Hunter:
     - Teclados de correção do Telegram não exibem opção para Posto Real.
     - Callbacks `desp:u:{ticket}:5558` ou `desp:u:{ticket}:7` levantam `DespesaTelegramErro`.
     - Ingestão descarta resolução para 5558/7 mantendo empresa a definir.
     - Validação de proposta (`ItemFilaDespesa.verificar_bloqueios_aprovacao`) impede aprovação com erro explícito.
     - Adaptador de escrita (`validar_unidade_autorizada`) levanta `BarreiraDespesaErro` com mensagem clara: *"Posto Real (empresaCodigo 5558 / codWeb 7) não faz parte do escopo do Expense Hunter (CNPJ desativado/inativo)."* Mesmo se uma lista externa de unidades for passada contendo 5558, a exclusão é soberana.
  2. **Códigos Espúrios (12607 e 12705):** A função `validar_unidade_autorizada` e os callbacks Telegram rejeitam expressamente com mensagem explicativa: *"Empresa 12607 não existe no webPosto. O código oficial de Casa Caiada é 5555."*
  3. **Empresa não autorizada ou indefinida:** Lançamento é terminantemente bloqueado com `BarreiraDespesaErro` e sem fallback para o Doze.

---

## 3. Arquivos Alterados e Criados

| Arquivo | Status | Responsabilidade |
|---|---|---|
| `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py` | **Criado** | Adaptador oficial de integração com webPosto para as 3 operações de despesas (`POST /TITULOS_PAGAR`, `POST /MOVIMENTOS_CONTA`, `PATCH /TITULOS_PAGAR/PAGAR`, `POST /ARQUIVOS`), validação de travas físicas `.env`, bloqueio estrito de Posto Real (`5558`/`7`), idempotência SQLite, confirmação pós-escrita e auditoria append-only. |
| `WebPosto_API/src/modules/cash_reconciliation/domain/comprovante.py` | **Modificado** | Adicionados campos `titulo_casado_codigo`, `resultado_erp_id`, `resultado_erp_detalhes` em `ItemFilaDespesa`. Inclusão de `sugestao_fornecedor_codigo` e `titulo_casado_codigo` na fórmula de hash canônico `calcular_hash_conteudo`. Bloqueio de aprovação para `unidade_codigo in (5558, 7)` em `verificar_bloqueios_aprovacao`. |
| `WebPosto_API/src/modules/cash_reconciliation/adapters/telegram_despesas.py` | **Modificado** | Adicionada proteção explícita contra Posto Real (`5558`/`7`) e códigos de empresa inválidos (`12607` e `12705`) no callback de correção rápida. Teclado de correção restrito exclusivamente às 4 unidades autorizadas. |
| `WebPosto_API/src/modules/cash_reconciliation/application/processar_comprovante.py` | **Modificado** | Descarta qualquer atribuição automática ou textual para Posto Real (`5558`/`7`), preservando a regra de empresa a definir sem fallback cego. |
| `WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_despesa.py` | **Criado** | Suíte completa com 28 testes unitários offline cobrindo todas as operações, barreiras, exclusão do Posto Real (5558/7), idempotência, timeouts, consultas e anexos. |
| `WebPosto_API/tests/unit/cash_reconciliation/test_telegram_despesas.py` | **Modificado** | Suíte com 23 testes unitários offline, incluindo teste 23 de bloqueio de Posto Real e unidades inválidas. |
| `docs/validation/EXPENSE_02_TELEGRAM_APPROVAL_VALIDATION.md` | **Modificado** | Correção textual na descrição de botões para referenciar os códigos canônicos (`5555` e `118508`). |
| `STATUS.md` | **Modificado** | Atualização com o registro formal de entrega do EXPENSE-03 e EXPENSE-03-SCOPE-FIX. |

---

## 4. Contratos da OpenAPI V1 Implementados

### Operação A: Criar Conta a Pagar
- **Endpoint:** `POST /INTEGRACAO/V1/TITULOS_PAGAR` (`incluirTituloPagar`)
- **Schema:** `IncluirTituloDto`
- **Campos estritos:** `descricao`, `numeroTitulo`, `fornecedorCodigo`, `valorParcela`, `numeroParcelas`, `dataMovimento`, `vencimento`, `planoContaCodigo`, `centroCustoCodigo`, `empresaCodigo`, `observacao`, `dataValida`.
- **Governança:** `empresaCodigo` é obrigatório (impede fallback do ERP); `fornecedorCodigo` deve ser cadastrado e > 0; `valorParcela` > 0. Retorna `201 Created` com `tituloPagarCodigo`.

### Operação B: Despesa Já Paga (Lançamento Direto em Conta)
- **Endpoint:** `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` (`incluirMovimentoConta`)
- **Schema:** `ParametrosIncluirMovimentoConta`
- **Campos estritos:** `descricao`, `data`, `valor`, `conta`, `documento`, `centroCusto`, `planoConta`, `filial`, `contaMovimentoTipo="DEBITO"`, `tipoPessoa`, `pessoa`.
- **Governança:** `conta` financeira obrigatória e autorizada na unidade; quitação prévia comprovada por evidência bancária (ex: FITID no extrato OFX). Retorna `201 Created` e é conferido via `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA`.

### Operação C: Baixar Título Existente
- **Endpoint:** `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` (`pagarTituloPagar`)
- **Schema:** `PagarTituloDto`
- **Campos estritos:** `tituloPagarCodigo` (array de `int32`), `contaCodigo`, `dataPagamento`, `dataValida`, `pagamentoDataPosterior`.
- **Governança:** Título correspondente localizado no ERP; conta de liquidação válida; evidência de pagamento. Retorna `204 No Content` e é conferido via `GET /INTEGRACAO/V1/TITULOS_PAGAR`.

### Vínculo de Comprovante Digital
- **Endpoint:** `POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}` (`incluirArquivoFechamentoCaixa`)
- **Schema:** `IncluirArquivoFechamentoCaixaDto`
- **Campos estritos:** `nome` (string), `conteudo` (Base64).
- **Tipos de Origem:** `"MOVIMENTO_CONTA_MANUAL"` e `"TITULO_PAGAR"`.

---

## 5. Arquitetura de Guardas, Idempotência e Tratamento de Timeout

```
[ Proposta Aprovada ]
         │
         ▼
[ 1. Verificar Travas .env Físico ] ──(Travas != 1)──► [ BarreiraDespesaErro ] (Bloqueia)
         │
         ▼
[ 2. Validar Aprovação & Hash ] ──────(Divergência)──► [ Invalida Aprovação -> aguardando_revisao ]
         │
         ▼
[ 3. Lock Atômico de Idempotência ] ──(Já executado)─► [ BarreiraDespesaErro ] (Anti-Duplicidade)
         │
         ▼
[ 4. Envio HTTP (POST / PATCH) ]
         ├──► (Timeout de Rede) ─────────────────────► [ Marca RESULTADO_DESCONHECIDO ] (Sem Retry!)
         ├──► (Erro HTTP 4xx/5xx) ───────────────────► [ Marca FALHOU_SEM_ENVIO ]
         │
         ▼ (HTTP 201 / 204)
[ 5. Confirmação via Consulta GET ] ──(Não localizado)► [ Marca RESULTADO_DESCONHECIDO ] (Reconciliação)
         │
         ▼ (Confirmado)
[ 6. Anexar Arquivo Digital ] ────────(Falha anexo)──► [ Loga Falha de Anexo sem reverter lançamento ]
         │
         ▼
[ 7. Marca LANCADO_ERP & Auditoria Append-Only ]
```

---

## 6. Matriz de Testes Obrigatórios (100% Offline)

### Suíte do Adaptador de Escrita (`test_webposto_escrita_despesa.py` — 28 testes)

| # | Cenário Testado | Resultado | Detalhe |
|---|---|---|---|
| 01 | Conta a pagar válida | **PASSED** | POST `/TITULOS_PAGAR` retorna 201 com `tituloPagarCodigo`, avança para `lancado_erp`. |
| 02 | Movimento de débito válido | **PASSED** | POST `/MOVIMENTOS_CONTA` retorna 201, confirma via GET e registra `movimentoContaCodigo`. |
| 03 | Baixa de título válida | **PASSED** | PATCH `/TITULOS_PAGAR/PAGAR` retorna 204, confirma situação via GET. |
| 04 | Empresa errada / Bloqueio Posto Real | **PASSED** | Rejeita Posto Real (`5558` e `7`), códigos espúrios (`12607`, `12705`) e desconhecidas (`99999`). Aceita autorizadas (74014, 11495, 5555, 118508). |
| 04b| Bloqueio direto escrita Posto Real | **PASSED** | Chamadas diretas ao executor e montadores de payload com Posto Real (5558) são bloqueadas antes de qualquer requisição HTTP. |
| 05 | Empresa indefinida | **PASSED** | Rejeita lançamento se empresa for None ou `EMPRESA_INDEFINIDA`. |
| 06 | Conta financeira errada | **PASSED** | Rejeita operações de débito/baixa sem conta financeira informada. |
| 07 | Fornecedor inexistente | **PASSED** | Rejeita criação de título se `fornecedorCodigo` for nulo ou <= 0. |
| 08 | Plano de contas inválido | **PASSED** | Rejeita criação de título se `planoContaCodigo` for nulo ou <= 0. |
| 09 | Aprovação ausente | **PASSED** | Rejeita lançamento se status não for `aprovado`. |
| 10 | Aprovação de versão antiga | **PASSED** | Rejeita e invalida aprovação se versão atual > aprovada. |
| 11 | Hash diferente | **PASSED** | Rejeita e invalida se dados foram alterados pós-aprovação. |
| 12 | Operação diferente da aprovada | **PASSED** | Rejeita se operação pretendida diverge da aprovada. |
| 13 | Registro já existente no ERP | **PASSED** | Bloqueia reenvio de operação já confirmada na idempotência local. |
| 14 | Timeout em POST | **PASSED** | Registra `RESULTADO_DESCONHECIDO` e não executa retry automático. |
| 15 | Timeout em PATCH | **PASSED** | Registra `RESULTADO_DESCONHECIDO` e não executa retry automático. |
| 16 | Retry bloqueado | **PASSED** | Tentativa subsequente após timeout é sumariamente bloqueada. |
| 17 | Duas tentativas simultâneas | **PASSED** | Lock `BEGIN IMMEDIATE` no SQLite impede concorrência. |
| 18 | HTTP 201 sem identificador | **PASSED** | Resposta 201 sem ID no corpo transiciona para `RESULTADO_DESCONHECIDO`. |
| 19 | HTTP 204 sem payload | **PASSED** | Trata 204 No Content confirmando a liquidação via consulta GET. |
| 20 | Consulta posterior inconclusiva | **PASSED** | Se GET não encontra o movimento lançado, mantém pendência de reconciliação. |
| 21 | Anexo preparado corretamente | **PASSED** | Converte arquivo para Base64 e monta payload conforme spec. |
| 22 | Falha de anexo sem repetir lançamento | **PASSED** | Erro 500 no anexo não desfaz nem repete o lançamento financeiro. |
| 23 | Flags em zero bloqueiam escrita | **PASSED** | Com flags em zero, execução levanta `BarreiraDespesaErro`. |
| 24 | Ausência de chamadas externas | **PASSED** | MockTransport intercepta tudo; `AsyncHTTPTransport` bloqueado. |
| 25 | Nenhuma operação financeira real | **PASSED** | `.env` real do repositório verificado com travas em 0. |
| 26 | Compatibilidade com EXPENSE-01 e EXPENSE-02 | **PASSED** | Itens gerados pelas sprints anteriores são aceitos e validados perfeitamente. |
| 27 | Casa Caiada oficial é 5555 | **PASSED** | Execução de teste com Casa Caiada (`5555`) aprovada com sucesso. |

### Suíte de Aprovação e Correção Telegram (`test_telegram_despesas.py` — 23 testes)
- Cobre fluxo completo de aprovação, concorrência, idempotência e o teste 23 de bloqueio do Posto Real (`5558`/`7`) nos botões, callbacks e domínio.

---

## 7. Regressão Completa da Suíte de Testes

- **Testes de Escrita (`test_webposto_escrita_despesa.py`):** 28/28 aprovados.
- **Testes de Aprovação Telegram (`test_telegram_despesas.py`):** 23/23 aprovados.
- **Testes de Ingestão e Fila (`test_comprovantes_fila.py`):** 29/29 aprovados.
- **Total do Módulo Expense Hunter:** 80/80 testes aprovados.
- **Suíte Completa `tests/unit/cash_reconciliation/`:** **637 testes aprovados**, 0 falhas, 0 chamadas reais a portais ou ERP.
- **Git Check:** `git diff --check` aprovado com código 0.

---

## 8. Limitações, Riscos e Requisitos para o Piloto Real

1. **Requisitos para o Primeiro Lançamento Real (Piloto EXPENSE-04):**
   - Autorização expressa e por escrito do dono do LOGOS.
   - Habilitação das travas físicas no `.env`: `WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1`.
   - Limitação inicial para 1 único comprovante de baixo valor (ex: até R$ 50,00) na unidade Posto Doze (`74014`) ou Casa Caiada (`5555`).
   - Conferência imediata no painel webPosto da filial.
2. **Fornecedores sem Cadastro Prévio:**
   - A criação de títulos a pagar (`POST /TITULOS_PAGAR`) exige `fornecedorCodigo` válido no ERP.
   - Se o fornecedor não existir no cadastro do webPosto, a despesa deve ser retida em pendência ou lançada via débito em conta (`POST /MOVIMENTOS_CONTA` com `tipoPessoa="NAO_IDENTIFICADO"`), se aplicável e aprovado pelo diretor.
3. **Backup Operacional:**
   - As tabelas de idempotência `data/lancamentos_logos/despesas.sqlite3` e as auditorias em `data/lancamentos_logos/<empresa>/historico_despesas.json` devem ser incluídas na rotina de backup local do servidor.
