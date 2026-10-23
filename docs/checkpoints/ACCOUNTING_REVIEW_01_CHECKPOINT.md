# CHECKPOINT — LOGOS ACCOUNTING-REVIEW-01

## Análise de Pendência Contábil e Matriz de Alternativas (Piloto R$ 626,00)

**Data:** 23/10/2026  
**Conta:** `27173`  
**Empresa:** `5555 — AP CASA CAIADA`  
**Estado cadastral:** `CONTA_CORRENTE / CONFIRMADO` (`permite_debito_despesa = 0`)  
**Allowlist escrita:** Fora de `CONTAS_AUTORIZADAS_POR_UNIDADE[5555]`  
**Piloto:** `BLOCKED_ACCOUNTING_REVIEW`  
**ERP Writes:** `0` (Zero chamadas externas, zero escritas)

---

## 1. Auditoria do Estado Cadastral e Simulação

- **SQLite Local (`master_data.sqlite3`):**
  - `conta_codigo = 27173`
  - `empresa_codigo = 5555`
  - `tipo_conta = CONTA_CORRENTE`
  - `banco_codigo = 001`
  - `agencia = 2365-5`
  - `conta_numero = 56816-3`
  - `permite_debito_despesa = 0`
  - `confiabilidade = CONFIRMADO`
- **Auditoria Append-Only:**
  - `audit_id = 235`
  - `acao = ATUALIZACAO`
  - `origem = AUTORIZACAO_EXPRESSA_PROPRIETARIO_MASTER_DATA_07`
- **Allowlist de Escrita:**
  - `CONTAS_AUTORIZADAS_POR_UNIDADE[5555]` contém exclusivamente `{17837}`. Conta `27173` permanece fora.
- **Simulação Offline (`MASTER_DATA_07_PILOT_SIMULATION.json`):**
  - SHA-256 verificado: `FF1B396B5C08AB6E1CD192CE7FDA08B371E7897C60384D762736D1822425B8B3`
  - `send = false`, `erp_request_executed = false`, `erp_write_authorized = false`.
- **Validação Offline:**
  - 141 testes executados e aprovados (**141 passed**): Master Data, preparação de piloto, precheck, adaptador de escrita e Telegram.

---

## 2. Diagnóstico da Pendência Contábil

1. **Divergência de Personalidade (PJ × PF):**
   - Recebedor bancário incontestável do comprovante BB de 10/10/2026: **Posto Real Ltda** (pessoa jurídica, CNPJ `08.106.946/0001-09`).
   - Finalidade informada pelo proprietário: **Pró-labore — Márcio** (pessoa física / sócio).
2. **Incompatibilidade Semântica de Centro de Custo:**
   - Plano de contas provisório: `29021 — PRO LABORE` (categoria `PESSOAL`).
   - Centro de custo provisório informado: `7295 — PISTA`.
   - **Trava de Segurança do LOGOS:** O código em `master_data_service.py` (linha 1106) e o teste de regressão `test_16_expense_hunter_bloqueio_centro_custo_incompativel` bloqueiam a combinação de `7295 (PISTA)` com despesas do tipo `PRO_LABORE` ou `ADMINISTRATIVO`. Portanto, caso mantido como pró-labore, o centro de custo precisa ser corrigido antes de qualquer escrita.

---

## 3. Matriz Objetiva de Alternativas Contábeis

| Alternativa | Natureza Contábil | Plano Sugerido | Centro de Custo | Tratamento da Divergência PJ | Documentos / Confirmações Necessários | Principais Riscos |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Pró-labore (Márcio)** | Despesa Operacional / Pessoal (DRE) | `29021 - PRO LABORE` | Administrativo / Diretoria (rejeita 7295 PISTA) | Exige justificativa formal de recebimento via conta PJ do Posto Real para repasse à PF | Recibo de pró-labore assinado por Márcio; comprovante de repasse da PJ para PF; informe eSocial/DIRF/Reinf | Inconsistência bancária vs folha; retenção de INSS e IRRF; questionamento de confusão patrimonial |
| **2. Adiantamento a Sócio** | Ativo Circulante (Balanço Patrimonial) | Conta de Ativo (Adiantamento a Sócios / Créditos com Sócios) | Não transita em CC operacional/PISTA | Débito registrado em nome do sócio para acerto em fechamento posterior | Autorização de adiantamento assinada pelo sócio; previsão contratual ou encontro de contas futuro | Se não quitado/compensado, risco de caracterização de mútuo tributável por IOF ou distribuição disfarçada de lucros |
| **3. Mútuo entre Empresas** | Operação de Crédito Interempresas (Balanço) | Ativo Realizável (Mútuo a Receber - Posto Real Ltda) | Não transita em CC operacional/PISTA | Alinha 100% com o comprovante (saída da Casa Caiada para crédito do Posto Real) | Contrato formal de mútuo entre Casa Caiada e Posto Real com taxas de mercado e apuração/recolhimento de IOF | Necessidade de formalização jurídica e incidência tributária de IOF |
| **4. Outra Classificação (Ressarcimento / Lucros)** | Conforme definição contábil (ex: Ressarcimento de Despesas da Pista ou Distribuição de Lucros) | Conforme plano aprovado pelo contador | Conforme a natureza do fato comprovado | Posto Real teria pago despesa da Casa Caiada e foi reembolsado; ou distribuição ao sócio | Notas fiscais originais que originaram o reembolso ou ata de distribuição de lucros | Dependência total de documentação comprobatória e validação do contador externo |

---

## 4. Estado das Travas e Não Executado

- Zero reclassificações adicionais;
- Zero alterações no SQLite;
- Débito permanece desabilitado (`permite_debito_despesa = 0`);
- Conta `27173` permanece fora da allowlist;
- Zero chamadas externas ao ERP;
- Zero escritas no ERP;
- Zero tokens de piloto emitidos;
- Piloto permanece estritamente `BLOCKED_ACCOUNTING_REVIEW`.
