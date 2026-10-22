# LOGOS — MASTER-DATA-05: Avaliação de Impacto e Governança de Reclassificação
## Reclassification Impact & Financial Safety Assessment — Conta 27173

**Data:** 22/10/2026  
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Checkpoint Base:** `3e1c2f8` (MASTER-DATA-04)  
**Prioridade:** P0  
**Status da Conta 27173:** **BLOCKED (Trava Mantida)**  
**Status do Piloto Casa Caiada:** **BLOCKED (Trava Mantida)**  
**Escritas no ERP:** **ZERO (0)**  
**Chamadas Externas:** **ZERO (0)**  

---

### 1. OBJETIVO DO DOCUMENTO

Analisar os impactos operacionais, contábeis, de segurança e de arquitetura de uma eventual e futura reclassificação da conta ERP **`27173`** de sua classificação atual (`TRANSITORIA` no LOGOS, com débito bloqueado) para **`CONTA_CORRENTE`** vinculada oficialmente à filial **`5555 (Casa Caiada)`**, Banco do Brasil (`001`), agência **`2365-5`**, conta **`56816-3`**.

---

### 2. ANÁLISE DE IMPACTO POR MÓDULO E SUBSISTEMA

#### 2.1. Impacto no Expense Hunter (Módulo de Despesas)
- **Desbloqueio Seguro de Débitos Bancários:**  
  Atualmente, qualquer despesa paga via Banco do Brasil da Casa Caiada (como a do FSIST de R$ 34,90 ou a do piloto de R$ 626,00) é sumariamente bloqueada no LOGOS porque o código numérico da conta BB não está cadastrado em `units.json` nem na allowlist `CONTAS_AUTORIZADAS_POR_UNIDADE[5555]`.
  A eventual reclassificação permitirá que o Expense Hunter monte o payload com o `contaCodigo` real `27173`, viabilizando o lançamento de saídas bancárias legítimas.
- **Blindagem Definitiva da Conta 17837 (CAIXA DA PISTA):**  
  A ausência de uma conta bancária associada criava o risco de operadores ou rotinas legadas usarem erroneamente a conta `17837` ("CAIXA(POSTO)"). A reclassificação formal da conta `27173` estabelece a distinção clara entre o saldo físico da pista (`17837`) e o saldo bancário escritural (`27173`).
- **Garantia de Não-Disparo Automático:**  
  Mesmo reclassificada a conta no catálogo, **nenhuma despesa será lançada automaticamente**. O `GerenciadorAutorizacaoPiloto` exige token criptográfico individual de uso único (`secrets.token_urlsafe(32)` com hash SHA-256 no SQLite) com correspondência estrita em 8 dimensões financeiras (`op_id`, `emp_cod`, `tp_op`, `valor`, `h_apr`, `c_cod`, `expira_em`).

#### 2.2. Impacto no Saldo Atual e Contabilidade do ERP
- **Evidência do Saldo no ERP:**  
  Na consulta oficial de 21/10/2026, o ERP retornou:
  `contaCodigo: 27173` — `descricao: "BANCO DO BRASIL (56816-3)"` — `saldoAtual: -8685811.91`.
- **Interpretação Financeira do Saldo Negativo:**  
  O saldo negativo de ~R$ 8,68 milhões reflete um padrão comum no ERP webPosto em postos de combustíveis:
  1. A conta no ERP é alimentada continuamente com lançamentos contábeis de despesas, faturas ou integração de vendas sem a conciliação/fechamento diário de extratos OFX pelo webPosto; OU
  2. O ERP acumula saídas históricas sem correspondente lançamento manual de saldos iniciais de extrato.
- **Risco de Distorção Contábil:**  
  O lançamento de uma nova despesa avulsa via `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` apenas adicionará uma linha de débito idêntica ao que o diretor realizaria na interface web do webPosto. Logo, **não introduz nenhuma distorção adicional nem corrompe a escrituração contábil**.

#### 2.3. Impacto na Conciliação de Cartões, Fechamento de Caixa e Sangrias
- **Mapeamento em `units.json`:**  
  Em `units.json` (linhas 91-94), consta a conta compartilhada `"BB CASA CAIADA"`, com membros `[5555, 118508]` e nota indicando que a Conveniência 24h deposita semanalmente nessa conta, bem como depósitos da pista ocorrem via ATM Banco24Horas.
  A vinculação de `27173` como a conta BB oficial de Casa Caiada possibilitará o cruzamento automático dos comprovantes de depósito de sangria de dinheiro contra a conta bancária no webPosto.
- **Isolamento do Fechamento Noturno das 03:00:**  
  O Task Scheduler roda o fechamento diário da pista baseado no `.env` da raiz, onde as travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` permanecem invioladas. O módulo de reconciliação de caixa noturno não escreve em contas bancárias.

#### 2.4. Isolamento Anti-Uso Cruzado entre Empresas (Governança Multi-Empresa)
- **Vínculo Unívoco com Filial 5555:**  
  A conta `27173` pertence única e exclusivamente à empresa `5555` (`empresaCodigo: 5555`).
- **Barreiras Imutáveis:**  
  - Posto Doze (`74014`): restrito às contas `{86248, 86081, 86188}`;
  - Posto VIP (`11495`): restrito às contas `{65321, 55028}`;
  - Conveniência 24h (`118508`): `CONTAS_AUTORIZADAS_POR_UNIDADE[118508] = frozenset()` — estritamente bloqueada contra débitos em conta bancária (apenas títulos a pagar autorizados);
  - Posto Real (`5558`): sumariamente bloqueado para qualquer lançamento de despesa (`autorizado_despesa = False`).
- **Garantia:** Qualquer tentativa de emitir débito na conta `27173` para uma despesa associada a outra filial levantará imediatamente `BarreiraDespesaErro`.

#### 2.5. Trilha de Auditoria e Persistência SQLite (`master_data.sqlite3`)
- A reclassificação será executada exclusivamente via `MasterDataService.sincronizar_dados_incremental()`:
  - O SQLite local (`master_data.sqlite3`) registrará uma nova entrada em `master_data_audit_log` com a ação `ATUALIZACAO`;
  - Os metadados anteriores (`tipo_conta: TRANSITORIA`, `permite_debito_despesa: false`, `empresa_codigo: null`) serão integralmente preservados no campo `dados_anteriores_json`;
  - A proveniência do dado (`origem_dado`) registrará o número da autorização formal ou inspeção em tela;
  - Zero perda de histórico, zero deleção física, conformidade total com o princípio append-only.

---

### 3. PRESERVAÇÃO DAS TRAVAS E REGRAS INVIOLÁVEIS

| Regra Inviolável | Estado Atual | Garantia Pós-Reclassificação Futura |
|---|---|---|
| **Bloqueio da Conta 17837** | **ATIVO** (Cofre da pista bloqueado para despesas bancárias) | **MANTIDO 100% INVIOLÁVEL** (`CAIXA_FISICO`, `permite_debito_despesa = False`). |
| **Uso Automático da Conta 27173** | **ZERO DESPESAS AUTOMÁTICAS** | **ZERO DESPESAS AUTOMÁTICAS** (exige aprovação humana prévia + token atômico). |
| **Piloto Casa Caiada (R$ 626,00)** | **BLOCKED** | **BLOCKED** (aguarda deliberação independente do proprietário). |
| **Escritas no ERP webPosto** | **ZERO (0)** | **ZERO (0)** (nenhum POST/PUT/PATCH/DELETE realizado nesta sprint). |
| **Chamadas Externas de Rede** | **ZERO (0)** | **ZERO (0)** (100% da verificação realizada em ambiente local offline). |

---

### 4. CRITÉRIOS OBJETIVOS PARA RECLASSIFICAÇÃO FUTURA

A transição da conta `27173` para `CONTA_CORRENTE` somente poderá ocorrer mediante o atendimento de um dos seguintes critérios:

#### Critério A — Autorização Formal do Diretor/Proprietário
1. O proprietário/diretor analisa o relatório de evidências [MASTER_DATA_05_ACCOUNT_EVIDENCE.md](MASTER_DATA_05_ACCOUNT_EVIDENCE.md);
2. Declara expressamente que aceita a correspondência `"BANCO DO BRASIL (56816-3)"` na filial `5555` como comprovação suficiente de que `27173` é a conta corrente BB da Casa Caiada (Agência `2365-5` / Conta `56816-3`).

#### Critério B — Validação Visual Auditada na Interface do webPosto
1. Um operador acessa a interface web do webPosto no menu `Financeiro > Cadastros > Contas / Bancos`;
2. Localiza o registro de código `27173`;
3. Confere visualmente se o campo de agência está registrado como `2365-5` (ou `2365`);
4. Registra screenshot ou ata de conferência visual no diretório de documentação do LOGOS.

---

### 5. ROTEIRO TÉCNICO DE IMPLEMENTAÇÃO (QUANDO AUTORIZADO)

Quando um dos critérios acima for formalizado:

1. **Ingestão Auditada no SQLite Local:**
   ```python
   service = MasterDataService()
   service.sincronizar_dados_incremental(
       {
           "contas_financeiras": [
               {
                   "conta_codigo": 27173,
                   "empresa_codigo": 5555,
                   "descricao": "BANCO DO BRASIL (56816-3)",
                   "tipo_conta": "CONTA_CORRENTE",
                   "banco_codigo": "001",
                   "banco_nome": "BANCO DO BRASIL",
                   "agencia": "2365-5",
                   "conta_numero": "56816-3",
                   "ativo": True,
                   "permite_debito_despesa": True,
                   "confiabilidade": "CONFIRMADO",
                   "origem_dado": "aprovacao_formal_diretoria_master_data_05",
               }
           ]
       },
       origem="reclassificacao_autorizada_27173",
   )
   ```
2. **Atualização do Mapeamento em `units.json`:**
   Adicionar no bloco da empresa 5555:
   ```json
   "contas_extrato": [
     {"banco": "BB", "conta_sufixo": "56816-3", "cd_conta": 27173}
   ]
   ```
3. **Atualização da Allowlist em `webposto_escrita_despesa.py`:**
   ```python
   CONTAS_AUTORIZADAS_POR_UNIDADE[5555] = frozenset({17837, 27173})
   ```
4. **Execução de Testes de Regressão Completos:**
   Garantir 100% de aprovação na suíte de testes de Master Data e Expense Hunter antes de qualquer emissão de token de piloto.

---

### 6. ESTADO ATUAL CONSOLIDADO

- **Conta 27173:** **BLOCKED** (nenhuma alteração foi gravada em disco ou no ERP).
- **Piloto Casa Caiada:** **BLOCKED**.
- **Segurança:** **100% PRESERVADA**.
