# PROMPT DE RETOMADA — LOGOS MASTER-DATA-04 (Pós-Reinicialização)
## Execução Read-Only Autorizada e Desbloqueio do Piloto Casa Caiada

**Papel:** CTO + Principal Software Engineer + Solution Architect + Product Owner
**Projeto:** `C:\Projetos\LOGOS\LogosPostos`
**Branch de trabalho:** `feature/cash-audit-fechamento`
**Prioridade:** P0
**Estratégia:** REUSE > ADAPT > CREATE

---

### 1. CONTEXTO DO PROJETO E ESTADO ATUAL

O trabalho do **MASTER-DATA-03** foi integralmente concluído, testado (56/56 testes aprovados) e consolidado no commit de checkpoint.
Todas as regras de governança, o avaliador de contas em 6 dimensões, a máquina de estados explícitos (`EstadoResolucaoConta`), a barreira pré-escrita do Expense Hunter e a governança das empresas foram formalizados e validados offline.

**Documentos de referência essenciais:**
- Checkpoint: `docs/checkpoints/MASTER_DATA_03_CHECKPOINT.md`
- Status geral: `STATUS.md`
- Resolução bancária: `docs/validation/MASTER_DATA_03_ACCOUNT_RESOLUTION.md`
- Segurança financeira: `docs/validation/MASTER_DATA_03_EXPENSE_SECURITY.md`
- Governança de empresas: `docs/validation/MASTER_DATA_03_IDENTITY_GOVERNANCE.md`
- Matriz de prontidão: `docs/validation/MASTER_DATA_03_PILOT_READINESS.md`

---

### 2. O QUE JÁ ESTÁ CONCLUÍDO (NÃO REPETIR)

- [x] Criação e persistência do banco `master_data.sqlite3` com WAL mode e tabela de auditoria `master_data_audit_log`.
- [x] Ingestão em lote dos 200 planos de contas e centros de custo oficiais.
- [x] Implementação da máquina de estados `EstadoResolucaoConta`.
- [x] Implementação de `avaliar_resposta_contas_erp()` no `MasterDataService`.
- [x] Contratos read-only preparados para `/INTEGRACAO/V1/CONTAS` e `/INTEGRACAO/EMPRESAS`.
- [x] Bloqueio estrito da conta `17837 — CAIXA(POSTO)` e do Posto Real (`5558`).
- [x] Isolamento da Conveniência 24h (`118508`) dos fluxos da Mais Pagamentos.
- [x] Testes unitários 01, 02 e 03 (56 testes passando 100%).

---

### 3. OBJETIVO DESTA SESSÃO (MASTER-DATA-04)

Executar com segurança e governança os passos pendentes que necessitam de confirmação operacional:

1. **Validação do Ambiente Pós-Reinício:**
   - Verificar `git status` e `git log -n 1`.
   - Executar os testes: `python -m pytest WebPosto_API/tests/unit/master_data/ --no-cov -v`.
2. **Execução da Consulta Read-Only Autorizada:**
   - Executar a consulta oficial:
     `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100`
   - **Nota:** Nenhuma escrita ou token de lançamento financeiro é permitido nesta etapa.
3. **Avaliação da Resposta:**
   - Passar o retorno JSON pelo avaliador de 6 dimensões `avaliar_resposta_contas_erp(criterio, contas_erp)`.
   - Obter o código oficial `contaCodigo` associado à agência `2365-5` e conta `56816-3`.
4. **Atualização Incremental do Catálogo:**
   - Ingerir a conta confirmada no catálogo `master_data.sqlite3` via `sincronizar_dados_incremental()`.
5. **Transição de Estado do Piloto:**
   - Se e somente se o estado for `ACCOUNT_CONFIRMED`, transicionar o piloto da Casa Caiada de `BLOCKED` para `READY_FOR_AUTHORIZATION`.
6. **Consulta de Confirmação do CNPJ da Conveniência 24h (Opcional se autorizada):**
   - Executar `GET /INTEGRACAO/EMPRESAS` e atualizar o status do CNPJ `08.106.946/0003-70`.
7. **Atualizar `STATUS.md` e gerar relatório de evidências.**

---

### 4. REGRAS INVIOLÁVEIS

- ZERO chamadas de POST, PUT, PATCH ou DELETE no ERP sem nova autorização expressa.
- Não usar a conta `17837` para despesas.
- Não executar o piloto real de R$ 626,00 nesta etapa; apenas atualizar o catálogo e deixar o piloto pronto para decisão humana.
- Manter integridade total de auditoria e persistência.

---

### 5. COMANDOS DE PARTIDA

```bash
cd C:\Projetos\LOGOS\LogosPostos
python -m pytest WebPosto_API/tests/unit/master_data/ --no-cov -v
```
