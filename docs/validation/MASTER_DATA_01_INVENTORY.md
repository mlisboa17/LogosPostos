# LOGOS — MASTER-DATA-01: Inventário de Fontes e Cadastros Mestres

**Data:** 19/10/2026 19:20
**Projeto:** `C:\Projetos\LOGOS\LogosPostos`
**Branch:** `feature/cash-audit-fechamento`
**Prioridade:** P0 — Fundação Operacional para Expense Hunter, Cash Hunter e Conciliação
**Diretriz Arquitetural:** **REUSE > ADAPT > CREATE**
**Modo ERP:** Somente Leitura (Nenhuma chamada externa ou escrita autorizada nesta etapa)

---

## 1. Objetivo do Inventário

Mapear exaustivamente todas as fontes de cadastros financeiros disponíveis no repositório LOGOS, classificando cada informação quanto à sua origem, granularidade, confiabilidade e cobertura pelas 4 empresas do escopo operacional (Posto Doze Filial II, Posto VIP, AP Casa Caiada, Conveniência 24 Horas) e pela empresa excluída (Posto Real — contraparte histórica).

### Níveis de Confiabilidade Adotados:
- **CONFIRMADO:** Informação atestada por contrato de API oficial (OpenAPI 2026-10-06) ou por arquivo de configuração canônico do LOGOS em uso produtivo.
- **HISTÓRICO:** Dados extraídos em auditorias e snapshots prévios (ex.: 06/10/2026). Válidos para referência, mas sujeitos a sincronização cadastral no ERP.
- **INFERIDO:** Correspondência heurística ou semântica derivada de descrições ou comprovantes. **Nunca autoriza escrita direta no ERP**.
- **PENDENTE:** Dado obrigatório ausente, ambíguo ou necessitando de consulta ao endpoint oficial do webPosto antes de liberar operação financeira.

---

## 2. Matriz Geral de Fontes de Dados Existentes

| Fonte / Arquivo | Tipo / Protocolo | Cadastros Contidos | Empresas Cobertas | Data Atualização | Confiabilidade | Capacidade Sincronização |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `units.json` | JSON Local (Config) | Empresas, Filiais, Cofres de Sangria | 74014, 11495, 5555, 118508, 5558 | Out/2026 | **CONFIRMADO** | Local / Estática |
| `account_category_mapping.json` | JSON Local (Catálogo) | 200 Planos de Contas webPosto | Grupo (Global) | Out/2026 | **CONFIRMADO** | Importável / Snapshot |
| `financial_origin_matrix.json` | JSON Local (Mapeamento) | Matriz de Endpoints, Origens e Cofres | 74014, 11495, 5555, 118508, 5558 | Out/2026 | **CONFIRMADO** | Referência técnica |
| `docs/external/webposto/openapi_integracao_2026-10-06.json` | OpenAPI 3.0.1 (Swagger) | Contratos de DTOs e Endpoints | Todas | 06/10/2026 | **CONFIRMADO** | Especificação Oficial |
| `webposto_network_probe_result.json` | Snapshot JSON | 17 Contas Financeiras do Grupo | Rede Logos | 06/10/2026 | **HISTÓRICO** | Read-Only Probe |
| `audit_p0_results.json` | Snapshot JSON | Títulos a Pagar, Movimentos, Baixas | 74014, 11495, 5555, 118508 | Out/2026 | **HISTÓRICO** | Auditoria |
| `src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py` | Código Python | Allowlist de Empresas, Mapeamento Cofres | 74014, 11495, 5555, 118508 | Out/2026 | **CONFIRMADO** | Regras de Negócio |

---

## 3. Inventário Detalhado por Cadastro P0

### 3.1 Empresas e Filiais (P0.1)

| Código (`empresaCodigo`) | `codWeb` | Razão Social / Descrição | CNPJ | Status Expense Hunter | Regra de Negócio Específica | Confiabilidade |
| :---: | :---: | :--- | :--- | :---: | :--- | :---: |
| **74014** | 6 | Posto Doze Filial II | 08.106.946/0002-90 | **AUTORIZADO** | Utiliza Mais Pagamentos | **CONFIRMADO** |
| **11495** | 5 | Posto VIP | 04.288.756/0001-04 | **AUTORIZADO** | Utiliza Mais Pagamentos | **CONFIRMADO** |
| **5555** | 8 | AP Casa Caiada | 05.823.111/0001-83 | **AUTORIZADO** | Utiliza Mais Pagamentos | **CONFIRMADO** |
| **118508** | 9 | Conveniência 24 Horas | 08.106.946/0003-70 | **AUTORIZADO** | **NÃO** utiliza Mais Pagamentos | **CONFIRMADO** |
| **5558** | 7 | Posto Real | 08.106.946/0001-09 | **EXCLUÍDO (BLOQUEADO)** | Preservado como contraparte histórica | **CONFIRMADO** |

- **Campos Mapeados:** `empresa_codigo`, `cod_web`, `razao_social`, `nome_fantasia`, `cnpj`, `ativo`, `autorizado_despesa`, `usa_mais_pagamentos`.
- **Campos Ausentes na Fonte Local:** Inscrição Estadual, Regime Tributário (não impactam conciliação de despesas).
- **Relacionamentos:** Cada filial possui exatamente uma conta de cofre de sangria oficial mapeada.

---

### 3.2 Contas Financeiras do ERP (P0.2)

Foram identificadas 17 contas financeiras cadastradas no grupo econômico no webPosto (via snapshot de sonda 06/10/2026 e matriz operacional):

| Código webPosto | Empresa Proprietária | Descrição Cadastral | Tipo / Classificação | Finalidade Operacional | Confiabilidade | Uso no Expense Hunter |
| :---: | :---: | :--- | :--- | :--- | :---: | :--- |
| **17837** | 5555 / Geral | CAIXA(POSTO) | Caixa Físico | Frente de Caixa / Pista | **CONFIRMADO** | **BLOQUEADO para pagamentos bancários** |
| **20936** | Grupo | CONTA BANCO | Bancária | Movimentação Geral | **HISTÓRICO** | PENDENTE vínculo por filial |
| **27173** | Grupo | CONTA TRANSITORIA | Transitória | Compensação Interna | **HISTÓRICO** | Bloqueado para despesas |
| **27406** | 5558 | COFRE POSTO REAL | Cofre | Sangrias Posto Real | **CONFIRMADO** | Bloqueado (Empresa 5558 excluída) |
| **55028** | Grupo | ADQUIRENTE CARTAO | Adquirente | Liquidação de Cartões | **HISTÓRICO** | Bloqueado para despesas |
| **55460** | Grupo | ADQUIRENTE CARTAO | Adquirente | Liquidação de Cartões | **HISTÓRICO** | Bloqueado para despesas |
| **58061** | 5555 | COFRE CASA CAIADA | Cofre | Sangrias Casa Caiada | **CONFIRMADO** | Bloqueado para débito bancário |
| **58062** | 11495 | COFRE VIP | Cofre | Sangrias VIP | **CONFIRMADO** | Bloqueado para débito bancário |
| **59117** | Grupo | CONTA BANCO | Bancária | Movimentação Bancária | **HISTÓRICO** | PENDENTE confirmação de agência/conta |
| **60536** | 74014 | COFRE DOZE | Cofre | Sangrias Doze | **CONFIRMADO** | Bloqueado para débito bancário |
| **65321** | Grupo | ADQUIRENTE CARTAO | Adquirente | Liquidação de Cartões | **HISTÓRICO** | Bloqueado para despesas |
| **69050** | Grupo | CONTA BANCO | Bancária | Movimentação Bancária | **HISTÓRICO** | PENDENTE confirmação de agência/conta |
| **69446** | Grupo | CONTA TRANSITORIA | Transitória | Ajustes Contábeis | **HISTÓRICO** | Bloqueado para despesas |
| **70766** | Grupo | CONTA BANCO | Bancária | Movimentação Bancária | **HISTÓRICO** | PENDENTE confirmação de agência/conta |
| **82912** | 118508 | COFRE CONVENIENCIA | Cofre | Sangrias Conveniência 24h | **CONFIRMADO** | Bloqueado para débito bancário |
| **82918** | Grupo | CONTA TRANSITORIA | Transitória | Repasses | **HISTÓRICO** | Bloqueado para despesas |
| **86377** | Grupo | CONTA TRANSITORIA | Transitória | Ajustes de Fechamento | **HISTÓRICO** | Bloqueado para despesas |

#### ⚠️ Caso Obrigatório: Casa Caiada (5555) e Banco do Brasil (Comprovante R$ 626,00)
- **Identificação Física:** O comprovante bancário de 10/10/2026 aponta saída via Banco do Brasil (Agência `3234-4`, Conta Corrente `56816-3`, Favorecido Posto Real Ltda, Motivo Pró-labore Márcio).
- **Situação no webPosto:**
  - A matriz `financial_origin_matrix.json` lista o nome literal `"BANCO DO BRASIL (56816-3)"`.
  - No entanto, o `contaCodigo` numérico correspondente a essa conta corrente bancária específica no webPosto **NÃO está presente nos snapshots locais**.
  - As contas bancárias genéricas disponíveis no snapshot são `20936`, `59117`, `69050`, `70766`.
  - **DECISÃO DE SEGURANÇA:** O vínculo da conta BB da Casa Caiada é classificado estritamente como **PENDENTE**.
  - **A conta `17837 — CAIXA(POSTO)` JAMAIS pode ser usada como substituta da conta Banco do Brasil**, pois causaria desbalanceamento grave no saldo físico da pista da Casa Caiada.
  - O LOGOS registrará a associação como pendente até que uma sincronização read-only do endpoint `/INTEGRACAO/CONTA` retorne os campos `banco_codigo`, `agencia` e `conta_numero` exatos.

---

### 3.3 Plano de Contas (P0.3)

- **Total de Contas Catalogadas:** 200 planos de contas extraídos de `account_category_mapping.json`.
- **Status Geral:** **CONFIRMADO** (utilizado ativamente na categorização contábil/DRE).
- **Classificação DRE e Operacional:**
  - `29021`: `PRO LABORE` (Natureza: Despesa / Pró-labore de Sócios).
  - `29001`: `ENERGIA ELETRICA`.
  - `29002`: `AGUA E ESGOTO`.
  - `29003`: `TELEFONE E INTERNET`.
  - `29005`: `HONORARIOS CONTABEIS`.
  - `700`: `COMBUSTIVEIS` (Custo de Mercadorias).
  - `705`: `LUBRIFICANTES`.
  - `1001`: `SALARIOS E ORDENADOS`.
- **Caso de Referência `29021 — PRO LABORE`:**
  - **Regra:** O plano `29021` classifica a natureza contábil da despesa gerencial.
  - **Diferenciação Obrigatória:** O plano `29021` NÃO identifica o beneficiário financeiro (Márcio). O beneficiário econômico é mantido no campo `beneficiario_economico` do DTO e o recebedor bancário no campo `fornecedor_id` / `favorecido_bancario`.

---

### 3.4 Centros de Custo (P0.4)

| Código Centro Custo | Descrição | Abrangência | Finalidade | Restrições | Confiabilidade |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **7295** | PISTA | Posto (Combustíveis) | Operações de pista e frentistas | Não usar para administrativo ou loja | **CONFIRMADO** |
| **24423** | FOOD / CONVENIÊNCIA | Lojas de Conveniência | Produtos de loja e conveniência | Exclusivo para operações de food/loja | **CONFIRMADO** |
| *Pendente* | ADMINISTRATIVO | Geral | Despesas gerais, pro-labore, taxas | Requer sincronização cadastral do webPosto | **PENDENTE** |

- **Regra de Segurança:** Despesas corporativas ou de pró-labore NÃO podem ser lançadas compulsoriamente no centro de custo `7295 — PISTA`. Caso o centro de custo administrativo não esteja catalogado para a empresa, a associação permanece PENDENTE de validação humana.

---

### 3.5 Fornecedores e Favorecidos (P0.5)

O inventário mapeia as 4 categorias funcionais exigidas pelo domínio financeiro:

1. **Fornecedor Cadastrado no ERP:** Entidade jurídica/física com `fornecedor_id` válido no webPosto, necessária para emissão e baixa de títulos.
2. **Recebedor Bancário Original:** Titular da conta de destino informada no comprovante PIX/TED (ex.: `Posto Real Ltda`, CNPJ `08.106.946/0001-09`).
3. **Beneficiário Econômico / Sócio:** Pessoa física ou jurídica que realmente usufruiu do recurso (ex.: `Márcio`, no comprovante de Pró-labore de 10/10/2026).
4. **Empresa Relacionada:** Empresas do mesmo grupo que figuram em transações de repasse mútuo (ex.: Posto Real figurando como recebedor transitório de despesas da Casa Caiada).

- **Regra Anti-Ficção:** É terminantemente proibido criar fornecedores ou códigos fictícios para contornar validações. Se o fornecedor não constar no catálogo persistente, a proposta de despesa deve ser retida com status `pendente_fornecedor`.

---

### 3.6 Tipos de Movimentos e Operações webPosto (P0.6)

Extraídos rigorosamente dos DTOs da OpenAPI oficial (`openapi_integracao_2026-10-06.json`):

1. **Título a Pagar (`/INTEGRACAO/TITULO_PAGAR`):**
   - Criação de provisão para despesas ainda não liquidadas ou agendadas.
   - Campos obrigatórios: `empresa_id`, `fornecedor_id`, `plano_conta_id`, `centro_custo_id`, `valor`, `data_emissao`, `data_vencimento`, `numero_documento`.
2. **Baixa de Título (`/INTEGRACAO/BAIXA_TITULO_PAGAR`):**
   - Liquidação de título pré-existente via débito em conta financeira.
   - Campos obrigatórios: `baixa_id`, `titulo_id`, `conta_id`, `data_baixa`, `valor_pago`.
3. **Movimento Manual de Conta (`/INTEGRACAO/MOVIMENTO_CONTA`):**
   - Registro de despesa avulsa já paga diretamente pela conta bancária (sem título prévio).
   - Campos obrigatórios: `empresa_id`, `conta_id`, `plano_conta_id`, `centro_custo_id`, `tipo_movimento` (`'D'`), `valor`, `data_movimento`, `historico`.
4. **Anexação de Comprovante (`/INTEGRACAO/ANEXO`):**
   - Upload de PDF/JPEG do comprovante vinculado ao movimento ou título.
   - Campos obrigatórios: `tipo_origem`, `origem_id`, `nome_arquivo`, `conteudo_base64`, `mime_type`.

---

## 4. Conclusão e Próximos Passos do Inventário

O inventário comprova que:
1. As 5 empresas e suas filiais estão 100% catalogadas e delimitadas em escopo.
2. O plano de contas possui 200 contas catalogadas com alta fidelidade (`account_category_mapping.json`).
3. As 17 contas financeiras da rede foram identificadas, com papéis de cofre 100% delimitados.
4. Permanece uma lacuna estrita: o código numérico no webPosto da conta bancária Banco do Brasil da Casa Caiada (`56816-3`), que não deve ser inferido nem preenchido com a conta de caixa `17837`.
5. Todos os dados confirmados serão normalizados e carregados na nova tabela SQLite de Master Data.
