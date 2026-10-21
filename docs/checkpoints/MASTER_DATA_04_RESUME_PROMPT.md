# PROMPT DE RETOMADA — LOGOS MASTER-DATA-05 (Pós-Reinicialização)
## Decisão Humana sobre Conta 27173 e Prontidão do Piloto Casa Caiada

**Papel:** CTO + Principal Software Engineer + Solution Architect + Auditor Financeiro
**Projeto:** `C:\Projetos\LOGOS\LogosPostos`
**Branch de trabalho:** `feature/cash-audit-fechamento`
**Prioridade:** P0
**Estratégia:** REUSE > ADAPT > CREATE

---

### 1. CONTEXTO DO PROJETO E ESTADO ATUAL

No **MASTER-DATA-04**, executou-se com sucesso a única chamada autorizada ao ERP webPosto:
`GET https://web.qualityautomacao.com.br/INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100`

**Descoberta Factual:**
O ERP webPosto retornou 9 contas para a Casa Caiada. Entre elas:
- `contaCodigo`: `27173`
- `descricao`: `"BANCO DO BRASIL (56816-3)"`
- `empresaCodigo`: `5555`
- `ativo`: `true`

**Fronteira de Governança:**
O endpoint `/INTEGRACAO/V1/CONTAS` comprovadamente **não fornece** colunas estruturadas para agência, titular ou CNPJ, e o texto da descrição não contém a agência `2365-5`. Em cumprimento estrito à regra *"Não inferir dados ausentes"*, a conta `27173` **NÃO** foi persistida como conta bancária automaticamente, mantendo o status `ACCOUNT RESOLUTION: BLOCKED` e `CASA CAIADA PILOT: BLOCKED`.

**Documentos de referência essenciais:**
- Checkpoint atual: `docs/checkpoints/MASTER_DATA_04_CHECKPOINT.md`
- Status geral: `STATUS.md`

---

### 2. O QUE JÁ ESTÁ CONCLUÍDO (NÃO REPETIR)

- [x] Consulta oficial read-only executada com sucesso (HTTP 200 em 1019ms).
- [x] Evidência do cadastro oficial de contas da filial 5555 obtida e sanitizada.
- [x] Identificação inequívoca do código ERP `27173` correspondente a `"BANCO DO BRASIL (56816-3)"`.
- [x] Avaliação estrita em 6 dimensões rejeitando presunções automáticas.
- [x] Preservação integral do catálogo local `master_data.sqlite3`.
- [x] 56 testes Master Data passando 100%.

---

### 3. OBJETIVO DESTA SESSÃO (MASTER-DATA-05)

1. **Apresentar a decisão executiva ao proprietário:**
   - Informar que a conta `27173` é a única no ERP vinculada ao Banco do Brasil / 56816-3 da Casa Caiada.
   - Solicitar a aprovação humana formal para associar `contaCodigo=27173` à agência `2365-5` no catálogo mestre local.
2. **Se aprovado formalmente:**
   - Executar a ingestão incremental auditada de `27173` como `CONTA_CORRENTE` da Casa Caiada.
   - Atualizar `units.json` ou matriz de contas de origem conforme padrão de arquitetura.
   - Transicionar o piloto para `READY_FOR_AUTHORIZATION`.
3. **Se rejeitado ou exigida nova checagem:**
   - Manter os bloqueios ativos.

---

### 4. REGRAS INVIOLÁVEIS

- ZERO chamadas de escrita (POST, PUT, PATCH, DELETE) no ERP.
- Não executar o piloto financeiro sem nova autorização expressa.
- Não usar a conta `17837` para despesas.
- Preservar histórico e arquivos não rastreados de reconciliação de caixa.

---

### 5. COMANDO DE PARTIDA

```bash
cd C:\Projetos\LOGOS\LogosPostos
git status
python -m pytest WebPosto_API/tests/unit/master_data/ --no-cov -v
```
