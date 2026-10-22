# PROMPT DE RETOMADA — LOGOS MASTER-DATA-06 (Pós-Reinicialização)
## Decisão Executiva sobre Reclassificação da Conta 27173 e Prontidão do Piloto Casa Caiada

**Papel:** CTO + Principal Software Engineer + Solution Architect + Auditor Financeiro  
**Projeto:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch de trabalho:** `feature/cash-audit-fechamento`  
**Prioridade:** P0  
**Estratégia:** REUSE > ADAPT > CREATE  

---

### 1. CONTEXTO DO PROJETO E ESTADO ATUAL

No **MASTER-DATA-05**, realizou-se a revisão aprofundada de evidências cadastrais e de governança sobre a conta ERP **`27173`**:
1. Comprovou-se que a classificação anterior de `27173` como `TRANSITORIA` foi **inferida defensivamente** pelo LOGOS no bootstrap inicial como proteção contra IDs sem filial mapeada, e não reflete a natureza contábil da conta no webPosto.
2. Identificou-se que a conta `27173` é a **única conta cadastrada no ERP para a filial 5555** vinculada ao Banco do Brasil, com a descrição exata `"BANCO DO BRASIL (56816-3)"`.
3. O extrato oficial do Banco do Brasil confirma a titularidade de `AUTO POSTO CASA CAIADA LTDA` (CNPJ `04.284.939/0001-86`, Agência `2365-5`, Conta `56816-3`).
4. Por estrito cumprimento da governança e limitação de schema da API do webPosto (que omite campo estruturado de agência), a conta `27173` **permaneceu travada** (`ACCOUNT 27173: BLOCKED` / `CASA CAIADA PILOT: BLOCKED`).

**Documentos de referência essenciais:**
- Relatório de Evidências: `MASTER_DATA_05_ACCOUNT_EVIDENCE.md`
- Avaliação de Impacto: `MASTER_DATA_05_RECLASSIFICATION_IMPACT.md`
- Checkpoint atual: `docs/checkpoints/MASTER_DATA_05_CHECKPOINT.md`
- Status geral: `STATUS.md`

---

### 2. O QUE JÁ ESTÁ CONCLUÍDO (NÃO REPETIR)

- [x] Origem histórica da conta `27173` rastreada até o probe e bootstrap inicial (Audit ID 21).
- [x] Natureza inferida (não comprovada contabilisticamente) da classificação transitória demonstrada.
- [x] Evidências oficiais do Banco do Brasil (OFX e PDF) confrontadas com o retorno do ERP.
- [x] Análise de impacto nos módulos Expense Hunter, Reconciliação, Isolamento de Empresas e SQLite.
- [x] Preservação integral do bloqueio da conta `17837` (CAIXA POSTO).
- [x] 56 testes de Master Data e 11 testes de preparação do piloto BB aprovados (100% de sucesso).
- [x] Zero escritas no ERP e zero chamadas externas nesta sprint.

---

### 3. OBJETIVO DA PRÓXIMA SESSÃO (DECISÃO EXECUTIVA / PILOTO)

1. **Obter a deliberação formal do Diretor/Proprietário:**
   - **Opção 1:** Aprovar expressamente a reclassificação de `27173` para `CONTA_CORRENTE` da Casa Caiada (`banco="001"`, `agencia="2365-5"`, `conta="56816-3"`), aceitando a descrição oficial `"BANCO DO BRASIL (56816-3)"` como evidência suficiente; OU
   - **Opção 2:** Solicitar validação visual prévia na tela de contas do webPosto.
2. **Se formalmente aprovada a Opção 1:**
   - Ingerir incrementalmente no SQLite local a reclassificação auditada de `27173`.
   - Adicionar `27173` na allowlist da empresa 5555 (`CONTAS_AUTORIZADAS_POR_UNIDADE`).
   - Mapear a conta em `units.json` (`contas_extrato`).
   - Transicionar o piloto de Casa Caiada para `READY_FOR_SINGLE_CONTROLLED_WRITE`.
3. **Se mantida a restrição:**
   - Manter os bloqueios ativos.

---

### 4. REGRAS INVIOLÁVEIS

- ZERO chamadas de escrita no ERP sem autorização expressa e token criptográfico individual.
- Manter o bloqueio definitivo da conta `17837` contra saídas bancárias.
- Não executar chamadas externas não autorizadas.
- Preservar arquivos de auditoria e reconciliação não rastreados.

---

### 5. COMANDO DE PARTIDA

```bash
cd C:\Projetos\LOGOS\LogosPostos
git status
python -m pytest WebPosto_API/tests/unit/master_data/ -v --no-cov
```
