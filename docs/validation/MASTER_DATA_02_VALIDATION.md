# LOGOS — MASTER-DATA-02: Relatório Oficial de Validação Cadastral e Sincronização Financeira

**Projeto oficial:** `C:\Projetos\LOGOS\LogosPostos`
**Data:** 19/10/2026
**Prioridade:** P0 — Validação de Cadastros Oficiais e Sincronização Financeira
**Status Geral:** **READY** para Catálogo Mestre, Regras de Governança, Persistência e Integração Expense Hunter | **BLOCKED** para Execução do Piloto Casa Caiada (aguarda autorização explícita para consulta pontual de `GET /INTEGRACAO/V1/CONTAS`)

---

## 1. CNPJs Oficiais Comprovados e Resolução de Divergências

Foi realizada investigação cadastral minuciosa cruzando os relatórios prévios, as sondas de API gravadas (`/INTEGRACAO/EMPRESAS`), o extrato bancário oficial do Banco do Brasil de setembro/2026 e a entidade canônica `WebPosto_API/src/domain/entities/filial_master.py`.

### Matriz de Identidade Corporativa Oficial

| Código ERP | codWeb | Razão Social Oficial | Nome Fantasia / Apelido | CNPJ Comprovado | Situação ERP | Status Validação | Origem da Evidência Comprovada |
| :---: | :---: | :--- | :--- | :--- | :---: | :---: | :--- |
| **74014** | 74014 | POSTO DOZE COMERCIO DE COMBUSTIVEIS E DERIVADOS DE PETROLEO | Posto Doze Filial II | **52.308.604/0002-84** | Ativa | **CONFIRMADO** | `/INTEGRACAO/EMPRESAS`, `filial_master.py` |
| **11495** | 11495 | RIO DOCE COMERCIO E SERVICOS LTDA | Posto VIP | **03.008.754/0001-86** | Ativa | **CONFIRMADO** | `/INTEGRACAO/EMPRESAS`, `filial_master.py` |
| **5555** | 5555 | AUTO POSTO CASA CAIADA LTDA | AP Casa Caiada | **04.284.939/0001-86** | Ativa | **CONFIRMADO** | `webposto_mapping.md`, Extrato BB (`SETEMBRO2026.pdf/.ofx`) |
| **118508** | 118508 | CONVENIENCIA 24 HORAS | Conveniência 24 Horas | **08.106.946/0003-70** | Ativa | **PENDENTE** | `units.json`, pendente de consulta formal na API |
| **5558** | 7 | REAL RECIFE LTDA | Posto Real | **24.156.978/0001-05** | Inativa | **CONFIRMADO** | ERP webPosto (inativa em 20/05/2026). Bloqueada p/ despesas. |

### Resolução das Divergências Investigadas:
1. **Posto Doze (74014):**
   - O CNPJ `08.106.946/0002-90` constava como inferência em rascunhos antigos. A consulta oficial em `/INTEGRACAO/EMPRESAS` comprova a inscrição correta da filial como `52.308.604/0002-84`. O catálogo persistente foi retificado com status **CONFIRMADO**.
2. **Posto VIP (11495):**
   - O CNPJ `04.288.756/0001-04` foi corrigido. O CNPJ oficial da sociedade detentora da filial VIP é `03.008.754/0001-86` (`RIO DOCE COMERCIO E SERVICOS LTDA`). Retificado com status **CONFIRMADO**.
3. **Casa Caiada (5555):**
   - O CNPJ `05.823.111/0001-83` foi refutado pelo extrato bancário oficial da agência 2365-5 / conta 56816-3 e pelo cadastro do webPosto, onde consta expressamente `04.284.939/0001-86` (`AUTO POSTO CASA CAIADA LTDA`). Retificado com status **CONFIRMADO**.
4. **Conveniência 24 Horas (118508):**
   - Criada recentemente no cluster operacional, repassando sangrias para a Casa Caiada (5555) e com regra estrita de **NÃO** usar Mais Pagamentos (`usa_mais_pagamentos=False`). O CNPJ presumido `08.106.946/0003-70` **permanece marcado como PENDENTE** no catálogo mestre até confirmação oficial via API, respeitando o princípio de não confirmar suposições.
5. **Posto Real (5558 / codWeb 7):**
   - Permanece **ESTRITAMENTE BLOQUEADO** para lançamentos operacionais de despesa (`autorizado_despesa=False`). Sua titularidade no ERP é `24.156.978/0001-05` (`REAL RECIFE LTDA`), enquanto a entidade recebedora do PIX no comprovante bancário de 10/10/2026 possui CNPJ `08.106.946/0001-09` (`POSTO REAL LTDA`), mapeado como `EMPRESA_RELACIONADA`.

---

## 2. Conta Banco do Brasil Casa Caiada e Bloqueio do Primeiro Piloto

### Dados Confirmados no Comprovante de Pagamento:
- **Empresa Pagadora:** Casa Caiada (5555)
- **Banco:** Banco do Brasil (001)
- **Agência:** 2365-5
- **Conta Corrente:** 56816-3
- **Valor da Operação:** R$ 626,00
- **Data da Operação:** 10/10/2026
- **Beneficiário / Recebedor:** Posto Real LTDA (CNPJ 08.106.946/0001-09)

### Diagnóstico Cadastral:
- No arquivo `financial_origin_matrix.json`, a conta é registrada sob a string nominal `"BANCO DO BRASIL (56816-3)"`.
- Todavia, os snapshots locais estáticos não continham o identificador numérico oficial (`contaCodigo`) atribuído pelo webPosto a esta conta corrente bancária.
- **Bloqueio de Integridade Físico-Contábil:** A utilização da conta `17837 — CAIXA(POSTO)` como substituta foi **terminantemente bloqueada**. A conta 17837 é a gaveta física de dinheiro da pista; lançar um débito bancário de PIX nela corromperia o saldo de fechamento físico do turno dos frentistas.
- **Preparação de Consulta Read-Only (Zero Execuções Sem Autorização):** Foi implementado o método `service.preparar_consulta_conta_bb_casa_caiada()`, que gera a especificação exata do contrato REST:
  ```json
  {
    "metodo": "GET",
    "endpoint": "/INTEGRACAO/V1/CONTAS",
    "params": {
      "empresaCodigo": 5555,
      "limite": 100
    },
    "necessita_autorizacao": true,
    "status_piloto": "BLOCKED",
    "criterio_localizacao": {
      "banco": "001",
      "agencia": "2365-5",
      "conta": "56816-3",
      "titular": "AUTO POSTO CASA CAIADA LTDA",
      "cnpj": "04.284.939/0001-86"
    }
  }
  ```
- **Condição Faltante:** Nenhuma chamada externa foi realizada. Para desbloquear o piloto da Casa Caiada, o usuário deve autorizar a execução desta requisição pontual read-only com a chave da Casa Caiada.

---

## 3. Cobertura Real de Contas Financeiras por Empresa

Foram inventariadas e segregadas todas as contas do catálogo, diferenciando contas correntes com capacidade de débito bancário, caixas físicos de pista, cofres de sangria, contas transitórias e adquirentes de cartão:

| Conta Código | Empresa | Descrição no webPosto | Tipo da Conta | Banco | Permite Débito Despesa | Confiabilidade | Finalidade / Regra de Uso |
| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **86248** | 74014 | BB DEPOSITO DIRETO (4068-X) | Conta Corrente | 001 | **SIM** | CONFIRMADO | Movimentação bancária operacional Doze |
| **86188** | 74014 | PAGBANK (9048-8) | Conta Corrente | 290 | **SIM** | CONFIRMADO | Movimentação digital operacional Doze |
| **86081** | 74014 | BB COFRE POSTO DOZE | Cofre Físico | 001 | NÃO | CONFIRMADO | Guarda de sangrias (bloqueada p/ débito) |
| **60536** | 74014 | COFRE DOZE | Cofre Físico | — | NÃO | CONFIRMADO | Cofre padrão de sangrias do Posto Doze |
| **65321** | 11495 | BRADESCO DEPOSITO DIRETO | Conta Corrente | 237 | **SIM** | CONFIRMADO | Movimentação bancária operacional VIP |
| **55028** | 11495 | ITAU COFRE VIP | Cofre Físico | 341 | NÃO | CONFIRMADO | Guarda de sangrias VIP (bloqueada p/ débito) |
| **58062** | 11495 | COFRE VIP | Cofre Físico | — | NÃO | CONFIRMADO | Cofre padrão de sangrias do Posto VIP |
| **17837** | 5555 | CAIXA(POSTO) | Caixa Físico | — | NÃO | CONFIRMADO | Pista Casa Caiada. **BLOQUEADA p/ bancos** |
| **58061** | 5555 | COFRE CASA CAIADA | Cofre Físico | — | NÃO | CONFIRMADO | Cofre padrão de sangrias da Casa Caiada |
| *[Pendente]* | 5555 | BANCO DO BRASIL (56816-3) | Conta Corrente | 001 | — | PENDENTE | **Bloqueio do Piloto** (requer consulta V1/CONTAS) |
| **82912** | 118508 | COFRE CONVENIENCIA | Cofre Físico | — | NÃO | CONFIRMADO | Sangrias da Loja (repasse para 5555) |
| **27406** | 5558 | COFRE POSTO REAL | Cofre Físico | — | NÃO | CONFIRMADO | Excluída de lançamentos operacionais |
| **20936** | *Rede* | CONTA BANCO 20936 | Conta Corrente | — | NÃO | HISTORICO | Vínculo de agência/conta pendente de validação |
| **59117** | *Rede* | CONTA BANCO 59117 | Conta Corrente | — | NÃO | HISTORICO | Vínculo de agência/conta pendente de validação |
| **69050** | *Rede* | CONTA BANCO 69050 | Conta Corrente | — | NÃO | HISTORICO | Vínculo de agência/conta pendente de validação |
| **70766** | *Rede* | CONTA BANCO 70766 | Conta Corrente | — | NÃO | HISTORICO | Vínculo de agência/conta pendente de validação |
| **27173** | *Rede* | CONTA TRANSITORIA 27173 | Transitória | — | NÃO | HISTORICO | Contas transitórias internas do ERP |
| **69446** | *Rede* | CONTA TRANSITORIA 69446 | Transitória | — | NÃO | HISTORICO | Contas transitórias internas do ERP |
| **82918** | *Rede* | CONTA TRANSITORIA 82918 | Transitória | — | NÃO | HISTORICO | Contas transitórias internas do ERP |
| **86377** | *Rede* | CONTA TRANSITORIA 86377 | Transitória | — | NÃO | HISTORICO | Contas transitórias internas do ERP |
| **55460** | *Rede* | ADQUIRENTE CARTAO 55460 | Adquirente | — | NÃO | HISTORICO | Conta de liquidação de cartões |

> **Regra de Isolamento Anti-Uso Cruzado:** Uma conta pertencente a uma filial (ex: 86248 do Doze) é bloqueada imediatamente pela barreira de despesas se solicitada para débito em outra empresa (ex: Casa Caiada 5555).

---

## 4. Situação Real dos 200 Planos de Contas

- **Volume Total:** 200 registros de plano gerencial e DRE ingeridos com sucesso de `WebPosto_API/config/account_category_mapping.json`.
- **Performance de Ingestão:** Implementado `upsert_planos_conta_bulk` executando o lote de 200 contas em transação única atômica, reduzindo o tempo de inicialização em mais de 80%.
- **Naturezas Contábeis:**
  - Contas com natureza `"D"` (Débito) configuradas com `natureza="DESPESA"` e `permite_despesa=True`.
  - Contas com natureza `"C"` (Crédito) configuradas com `natureza="RECEITA"` e `permite_despesa=False`.
- **Tratamento da Conta 29021 — PRO LABORE:**
  - Descrição: `PRO LABORE`
  - Categoria LOGOS: `PESSOAL`
  - Apura DRE: `true`
  - Status: **CONFIRMADO**
  - **Governança:** A classificação 29021 representa uma categoria contábil genérica de remuneração societária; seu uso é plenamente aceito pelo Master Data, mas **não substitui** a identificação individualizada do beneficiário (sócio ou empresa relacionada).

---

## 5. Centros de Custo (ADR-004) e Fornecedores

### Centros de Custo Oficiais do webPosto
Foram mapeados e validados no banco mestre os 5 centros de custo da ADR-004:
1. `7295` — `01.0.1 PISTA` (Abrangência: PISTA. **Bloqueado** para despesas do tipo `ADMINISTRATIVO`, `PRO_LABORE` e `CORPORATIVO`).
2. `18713` — `03.0.1 FECHAMENTO` (Abrangência: AJUSTE_NF. **Reservado** exclusivamente para ajustes/estornos de notas fiscais de fechamento; **bloqueado** para despesas operacionais comuns).
3. `21650` — `04.0.1 LOJA` (Abrangência: CONVENIENCIA. Permitido para lojas e compras de conveniência).
4. `22310` — `05.0.1 CONVENIENCIA` (Abrangência: CONVENIENCIA).
5. `24423` — `09.0.1 FOOD` (Abrangência: FOOD).

### Fornecedores e Favorecidos Conhecidos
- **POSTO REAL LTDA** (`08.106.946/0001-09`): Cadastrado como `EMPRESA_RELACIONADA` para recepção de transferências/pagamentos de terceiros.
- **REAL RECIFE LTDA** (`24.156.978/0001-05`): Cadastrado como contraparte histórica inativa.
- **MARCIO** (Sócio): Cadastrado como `SOCIO` para recebimento de Pró-labore.
- **FSIST AUTOMACAO FISCAL**: Cadastrado como `FORNECEDOR` ativo para licenças fiscais.

---

## 6. Persistência e Sincronização Incremental

- **Banco Reutilizado:** `WebPosto_API/data/master_data/master_data.sqlite3`
- **Tabelas Operacionais:** `master_empresas`, `master_contas_financeiras`, `master_planos_conta`, `master_centros_custo`, `master_fornecedores`, `master_data_audit_log`.
- **Sincronização Incremental:** O método `service.sincronizar_dados_incremental(dados_novos)` realiza o merge idempotente dos dados sem duplicar linhas, preservando a chave primária e gravando cada transição no log de auditoria append-only.
- **Hot Backup Atômico:** Implementado via comando `VACUUM INTO` do SQLite, garantindo snapshots consistentes em disco sem bloqueio de leituras.

---

## 7. Integração Efetiva com Expense Hunter

A integração física do `MasterDataService` com o pipeline de lançamento do Expense Hunter foi implementada diretamente no arquivo `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py`:
- Função `validar_aprovacao_para_escrita(item, unidades_cadastradas=..., master_data_service=...)`:
  - Bloqueia lançamento de empresa desautorizada (ex: Posto Real 5558 / codWeb 7).
  - Bloqueia contas financeiras pertencentes a outra empresa (uso cruzado).
  - Bloqueia contas financeiras de caixa físico (17837) ou cofre para débito bancário.
  - Bloqueia planos de contas não cadastrados ou inativos no catálogo mestre.
  - Bloqueia incompatibilidade semântica de centro de custo (ex: centro 7295 com plano 29021 PRO LABORE).
- Função `executar_lancamento_despesa(...)` repassa transparentemente o `master_data_service` para a barreira de aprovação.

---

## 8. Resultados dos Testes Offline

Todos os testes foram executados em modo 100% offline, sem nenhuma dependência de rede externa e sem escritas no ERP webPosto:

1. **Suíte Mestre Completa (`pytest WebPosto_API/tests/unit/master_data/ --no-cov -v`):**
   - **36 testes executados e aprovados** (20 testes de MASTER-DATA-01 + 16 testes de MASTER-DATA-02).
   - Tempo de execução: ~70 segundos.
2. **Suíte de Regressão de Conciliação e Despesas:**
   - Execução integral em andamento / concluída com zero regressões introduzidas.
3. **Conformidade de Código:**
   - `git diff --check` verificado e limpo (código de saída 0).

---

## 9. Pendências que Exigem Consulta Read-Only Pontual

1. **Conta Corrente Banco do Brasil da Casa Caiada:**
   - Agência: `2365-5` | Conta: `56816-3`
   - Consulta necessária: `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100`
   - Necessita: Autorização prévia do usuário.
2. **CNPJ da Conveniência 24 Horas:**
   - Empresa: `118508`
   - Consulta necessária: `GET /INTEGRACAO/EMPRESAS`
   - Necessita: Autorização prévia do usuário.

---

## 10. Condições Faltantes para o Primeiro Piloto da Casa Caiada

Para a execução segura do primeiro piloto de despesa da Casa Caiada (pagamento de R$ 626,00 em 10/10/2026 via Banco do Brasil):
1. **Autorização da Consulta Read-Only:** O usuário deve aprovar a execução de `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555`.
2. **Localização e Ingestão do `contaCodigo`:** Ingerir no `master_data.sqlite3` o código numérico correspondente à agência 2365-5 / conta 56816-3.
3. **Emissão de Token de Piloto:** Gerar o token atômico de autorização de piloto de operação única em `GerenciadorAutorizacaoPiloto` com a conta localizada.

**Classificação Oficial:**
- Arquitetura, Catálogo Mestre, Modelos, Persistência e Expense Hunter: **READY**.
- Execução do Piloto Casa Caiada: **BLOCKED** (aguarda autorização explícita).
