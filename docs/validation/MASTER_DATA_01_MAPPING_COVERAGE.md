# LOGOS — MASTER-DATA-01: Relatório de Cobertura do Cadastro Mestre

**Data:** 19/10/2026 19:25
**Projeto:** `C:\Projetos\LOGOS\LogosPostos`
**Branch:** `feature/cash-audit-fechamento`
**Prioridade:** P0 — Fundação Operacional para Expense Hunter, Cash Hunter e Fechamento
**Diretriz Arquitetural:** **REUSE > ADAPT > CREATE**
**ERP:** Somente leitura; nenhuma escrita autorizada

---

## 1. Resumo Executivo

O **MASTER-DATA-01** estabelece a capacidade durável de **Master Data Financeiro do LOGOS**, eliminando a necessidade de buscas ad-hoc ou investigações manuais de códigos de contas, planos de contas, centros de custo e empresas a cada nova operação de conciliação ou auditoria.

### Indicadores Gerais de Cobertura:
- **Armazenamento:** SQLite Local dedicado (`WebPosto_API/data/master_data/master_data.sqlite3`) com WAL mode, transações pessimistas (`BEGIN IMMEDIATE`), constraints relacionais (`PRAGMA foreign_keys=ON`) e trilha de auditoria append-only (`master_data_audit_log`).
- **Empresas Cobertas:** 5 empresas (4 autorizadas para o Expense Hunter e 1 excluída por decisão do proprietário e mantida como contraparte histórica).
- **Contas Financeiras:** 17 contas financeiras mapeadas e categorizadas (com bloqueio rígido da conta 17837 para débitos bancários).
- **Plano de Contas:** 200 contas gerenciais/DRE normalizadas a partir de `account_category_mapping.json`.
- **Centros de Custo:** 2 centros de custo base operacionais (7295 PISTA e 24423 FOOD/CONVENIÊNCIA) com bloqueios semânticos contra uso indevido.
- **Fornecedores / Entidades:** Diferenciação funcional explícita entre fornecedor cadastrado, recebedor bancário, beneficiário econômico (sócio) e empresa relacionada.
- **Testes Automatizados:** 20 casos de teste obrigatórios executados 100% offline com isolamento em diretórios temporários.

---

## 2. Cobertura Cadastral por Empresa (Atualizado em MASTER-DATA-02)

| Empresa | `empresaCodigo` | `codWeb` | CNPJ Comprovado | Status Expense Hunter | Regras e Particularidades |
| :--- | :---: | :---: | :--- | :---: | :--- |
| **Posto Doze Filial II** | 74014 | 74014 | **52.308.604/0002-84** | **AUTORIZADO** | Utiliza Mais Pagamentos. Cofre oficial: 60536. Contas autorizadas: 86248, 86188. |
| **Posto VIP** | 11495 | 11495 | **03.008.754/0001-86** | **AUTORIZADO** | Utiliza Mais Pagamentos. Cofre oficial: 58062. Conta autorizada: 65321. |
| **AP Casa Caiada** | 5555 | 5555 | **04.284.939/0001-86** | **AUTORIZADO** | Utiliza Mais Pagamentos. Cofre oficial: 58061. Conta 17837 CAIXA(POSTO) bloqueada para pagamentos bancários. |
| **Conveniência 24 Horas**| 118508 | 118508 | 08.106.946/0003-70 *(Pendente)* | **AUTORIZADO** | **NÃO** utiliza Mais Pagamentos. Cofre oficial: 82912. Repassa sangria para 5555. |
| **Posto Real** | 5558 | 7 | 24.156.978/0001-05 | **BLOQUEADO (EXCLUÍDO)** | Excluído de despesas pelo proprietário. Preservado como contraparte histórica. Cofre: 27406. |

---

## 3. Cobertura de Contas Financeiras e Isolamento

As 17 contas identificadas na rede foram divididas rigorosamente em suas naturezas operacionais:

1. **Caixas Físicos de Pista:**
   - `17837 — CAIXA(POSTO)`: Pertencente à operação de pista da Casa Caiada. **Bloqueada para débitos bancários de despesas**. Não pode substituir contas correntes.
2. **Cofres de Sangria:**
   - `60536 — COFRE DOZE` (74014)
   - `58062 — COFRE VIP` (11495)
   - `58061 — COFRE CASA CAIADA` (5555)
   - `82912 — COFRE CONVENIENCIA` (118508)
   - `27406 — COFRE POSTO REAL` (5558)
   - *Regra:* Nenhum cofre é autorizado como conta de pagamento bancário direto no Expense Hunter.
3. **Contas Bancárias de Snapshot (Pendentes de Vínculo Específico):**
   - `20936`, `59117`, `69050`, `70766`.
   - *Status:* Marcadas com `permite_debito_despesa=False` até que uma consulta read-only ao webPosto retorne agência e conta corrente vinculadas a cada CNPJ.
4. **Contas Transitórias e Adquirentes:**
   - Transitórias: `27173`, `69446`, `82918`, `86377`.
   - Adquirentes de Cartão: `55028`, `55460`, `65321`.
   - *Status:* Uso exclusivo de compensação contábil interna e adquirentes; bloqueadas para lançamentos manuais de despesas avulsas.

---

## 4. Análise do Caso Específico: Casa Caiada (5555) e Banco do Brasil

- **Fato Contábil Real:** Saída de R$ 626,00 em 10/10/2026, via Banco do Brasil, agência `3234-4`, conta corrente `56816-3`.
- **Favorecido Bancário Original:** `POSTO REAL LTDA` (CNPJ `08.106.946/0001-09`).
- **Beneficiário Econômico Declarado:** `MÁRCIO` (Pró-labore).
- **Código do Plano de Contas:** `29021 — PRO LABORE` (confirmado no catálogo).
- **Situação Cadastral no webPosto:**
  - O código numérico da conta BB da Casa Caiada no webPosto permanece **PENDENTE** de confirmação direta via endpoint `/INTEGRACAO/CONTA`.
  - A tentativa de associar a conta `17837 — CAIXA(POSTO)` como paliativo foi **definitivamente rejeitada e bloqueada**, pois contaminaria o saldo físico de dinheiro dos frentistas da pista.
  - O LOGOS mantém essa pendência documentada de forma transparente, sem inventar identificadores aleatórios.

---

## 5. Matriz de Relacionamentos e Integridade Relacional

```
[ master_empresas ]
       │
       ├──< (1:N) [ master_contas_financeiras ] (FK empresa_codigo)
       │
       ├──< (1:N) [ master_centros_custo ] (FK empresa_codigo)
       │
       └──< (1:N) [ master_fornecedores ] (FK empresa_codigo)

[ master_planos_conta ] (Catálogo global de 200 contas)

[ master_data_audit_log ] (Trilha append-only de todas as operações)
```

- **Integridade Referencial Ativa:** `PRAGMA foreign_keys = ON;`
- **Validação Anti-Uso Cruzado:** Uma conta associada à filial A não pode ser debitada por uma operação iniciada na filial B.

---

## 6. Cobertura da Suíte de Testes (100% Offline)

A suíte `WebPosto_API/tests/unit/master_data/test_master_data_01.py` valida 20 cenários fundamentais:

| # | Cenário Validado | Componente Testado | Resultado |
| :-: | :--- | :--- | :---: |
| 1 | Casa Caiada e conta Banco do Brasil pendente | `resolver_conta_financeira` | ✅ APROVADO |
| 2 | Casa Caiada e conta 17837 CAIXA(POSTO) bloqueada | `resolver_conta_financeira` | ✅ APROVADO |
| 3 | Plano 29021 PRO LABORE (não identifica favorecido) | `resolver_plano_contas` | ✅ APROVADO |
| 4 | Empresa 5555 usando conta de outra empresa (bloqueio cruzado) | `resolver_conta_financeira` | ✅ APROVADO |
| 5 | Conveniência 24h usando conta 17837 (bloqueio cruzado) | `resolver_conta_financeira` | ✅ APROVADO |
| 6 | Posto Real (5558) bloqueado como empresa de lançamento | `resolver_empresa` | ✅ APROVADO |
| 7 | Posto Real preservado como contraparte histórica | `obter_fornecedor_por_documento` | ✅ APROVADO |
| 8 | Código financeiro inexistente rejeitado | `resolver_conta_financeira` | ✅ APROVADO |
| 9 | Conta bancária com vínculo não comprovado bloqueada | `resolver_conta_financeira` | ✅ APROVADO |
| 10 | Plano de contas desconhecido rejeitado | `resolver_plano_contas` | ✅ APROVADO |
| 11 | Centro de custo PISTA incompatível com despesa administrativa | `resolver_centro_custo` | ✅ APROVADO |
| 12 | Fornecedor inexistente rejeitado sem criação fictícia | `resolver_fornecedor` | ✅ APROVADO |
| 13 | Cadastro inativo bloqueado para operações | `resolver_empresa` | ✅ APROVADO |
| 14 | Divergência cadastral registrada na trilha de auditoria | `listar_auditoria` | ✅ APROVADO |
| 15 | Sincronização/bootstrap repetido sem duplicação (idempotência) | `bootstrap_catalogo` | ✅ APROVADO |
| 16 | Falha durante transação com rollback atômico | `_transacao` | ✅ APROVADO |
| 17 | Persistência após reinício de conexão (disco) | `SqliteMasterDataRepository` | ✅ APROVADO |
| 18 | Preservação cronológica do histórico de alterações | `listar_auditoria` | ✅ APROVADO |
| 19 | Nenhuma escrita real executada no webPosto | `validar_compatibilidade_despesa` | ✅ APROVADO |
| 20 | Nenhuma chamada externa ou abertura de socket nos testes | `monkeypatch socket` | ✅ APROVADO |

---

## 7. Evolução e Conclusão em MASTER-DATA-02

As limitações identificadas no MASTER-DATA-01 foram tratadas no **MASTER-DATA-02** ([MASTER_DATA_02_VALIDATION.md](file:///c:/Projetos/LOGOS/LogosPostos/docs/validation/MASTER_DATA_02_VALIDATION.md)):
1. **Identidades Oficiais e CNPJs:** Retificados com evidências comprovadas em `/INTEGRACAO/EMPRESAS` e extratos oficiais.
2. **Conta BB da Casa Caiada:** Isolada com bloqueio rigoroso da conta 17837. Contrato de consulta read-only `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555` devidamente preparado sem execução não autorizada.
3. **Plano de Contas:** Catálogo de 200 contas validado integralmente com ingestão em batch de alta performance.
4. **Centros de Custo (ADR-004):** Mapeamento dos 5 centros (7295, 18713, 21650, 22310, 24423) com regras estritas de isolamento semântico.
5. **Integração com Expense Hunter:** Implementada a barreira pré-escrita consumindo `MasterDataService`, validada com 36 testes unitários offline.
