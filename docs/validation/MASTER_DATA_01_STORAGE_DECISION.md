# LOGOS — MASTER-DATA-01: Decisão de Armazenamento do Cadastro Mestre

**Data:** 19/10/2026 19:15
**Projeto:** `C:\Projetos\LOGOS\LogosPostos`
**Branch:** `feature/cash-audit-fechamento`
**Prioridade:** P0 — Fundação Operacional para Expense Hunter, Cash Hunter e Conciliação
**Diretriz Arquitetural:** **REUSE > ADAPT > CREATE**

---

## 1. Contexto e Problema

O LOGOS possui diversos componentes financeiros (Expense Hunter, Cash Hunter, Conciliação Bancária de Cartões, Auditoria Noturna de Fechamento de Caixa) que necessitam consultar e validar cadastros mestres:
- Empresas e filiais autorizadas (`empresaCodigo`, `codWeb`, CNPJ, situação);
- Contas financeiras do ERP e contas bancárias (distinguindo conta corrente, caixa físico da pista, cofre, adquirentes);
- Plano de contas gerencial e contábil oficial (classificações DRE, natureza débito/crédito);
- Centros de custo (pista, conveniência, administrativo);
- Fornecedores, favorecidos bancários e sócios.

Atualmente, essas informações encontram-se fragmentadas em múltiplos arquivos:
- `units.json` (configuração estrutural de unidades e destinos de sangria);
- `account_category_mapping.json` (catálogo de 200 planos de contas do webPosto);
- `financial_origin_matrix.json` (matriz de endpoints e amostras de dados);
- Snapshots JSON legados e relatórios Markdown.

A cada nova operação, o sistema precisava reinterpretar esses arquivos ou depender de heurísticas pontuais. Faz-se necessária uma base mestre unificada, consultável e durável, que sobreviva a reinicializações e atualizações de código.

---

## 2. Avaliação Comparativa das Alternativas de Armazenamento

Foram analisadas 4 alternativas sob os 10 critérios mandatórios do projeto:

| Critério Mandatório | 1. PostgreSQL Local / Remoto | 2. Supabase Cloud | 3. Arquivos JSON Versionados | 4. SQLite Local Dedicado (Recomendado) |
| :--- | :--- | :--- | :--- | :--- |
| **1. Persistência durável** | ✅ Sim, se daemon ativo | ✅ Sim | ⚠️ Sim, mas frágil em concorrência | ✅ Sim (ACID em disco local) |
| **2. Integridade transacional** | ✅ Sim | ✅ Sim | ❌ Não (regravação total de arquivo) | ✅ Sim (`BEGIN IMMEDIATE`, WAL mode) |
| **3. Chaves únicas e constraints** | ✅ Sim | ✅ Sim | ❌ Manual via código | ✅ Sim (PKs, UKs compostas, FKs) |
| **4. Relacionamentos explícitos** | ✅ Sim | ✅ Sim | ❌ Não relacional | ✅ Sim (`REFERENCES`, `PRAGMA foreign_keys=ON`) |
| **5. Consultas eficientes (<5ms)** | ⚠️ Latência TCP / pool | ❌ Latência WAN (>50ms) | ⚠️ Ineficiente para buscas relacionais | ✅ Altamente eficiente (<1ms in-process) |
| **6. Histórico de mudanças (Audit)** | ✅ Sim | ✅ Sim | ❌ Difícil controle append-only | ✅ Sim (Tabela `master_data_audit_log`) |
| **7. Rastreabilidade de origem** | ✅ Sim | ✅ Sim | ⚠️ Parcial | ✅ Sim (Metadados por registro) |
| **8. Sincronização incremental** | ✅ Sim | ✅ Sim | ❌ Reescreve arquivo todo | ✅ Sim (`INSERT ... ON CONFLICT DO UPDATE`) |
| **9. Backup e recuperação** | ⚠️ Requer pg_dump / scripts | ⚠️ Depende da nuvem | ⚠️ Backup manual | ✅ Simples (`VACUUM INTO`, cópia atômica) |
| **10. Independência de ambiente** | ❌ **REPROVADO**: Porta 5432 fechada | ❌ **REPROVADO**: Exige internet/secrets | ⚠️ Acoplado ao repositório | ✅ **APROVADO**: 100% autônomo, zero daemon |

### Justificativas de Eliminação:
1. **PostgreSQL / AsyncPG:**
   - Embora `src/infrastructure/config/settings.py` contenha parâmetros para `postgresql+asyncpg://`, a inspeção de portas em tempo real confirmou que a porta `5432` está **fechada** na máquina local. O serviço não está em execução. O LOGOS roda como processo agendado (Task Scheduler) em ambiente desktop/servidor sem garantia de daemon PostgreSQL local ativo. Forçar Postgres violaria o princípio de não introduzir dependências inexistentes.
2. **Supabase:**
   - Exige conectividade de rede externa, chaves de API remotas e expõe dados cadastrais à nuvem, violando as regras de isolamento e operação offline.
3. **JSONs Isolados:**
   - Manter JSONs como armazenamento definitivo impede concorrência segura, não possui integridade referencial nativa e gera risco de sobrescrita acidental em sincronizações dinâmicas.

---

## 3. Decisão Formal de Armazenamento: SQLite Local Dedicado

A infraestrutura persistente oficial do LOGOS adota **SQLite local estruturado** para todos os seus subsistemas operacionais e de governança (`telegram.sqlite3`, `idempotencia.sqlite3`, `pendencias.sqlite3`), conforme validado nos épicos EXPENSE-01 a EXPENSE-04 e Fechamento Noturno.

Adota-se como repositório persistente oficial do Master Data:
```
WebPosto_API/data/master_data/master_data.sqlite3
```

### 3.1. Configuração de Robustez e Concorrência:
- **Journal Mode:** `PRAGMA journal_mode = WAL;` (Write-Ahead Logging permite leituras simultâneas sem bloqueio durante sincronizações).
- **Sincronismo:** `PRAGMA synchronous = NORMAL;` (segurança durável contra travamentos do SO).
- **Integridade Referencial:** `PRAGMA foreign_keys = ON;`.
- **Transações Concorrentes:** Transações de escrita usam `BEGIN IMMEDIATE` para prevenir race conditions.
- **Isolamento de Git:** O diretório `data/` encontra-se protegido no `.gitignore`, garantindo que cadastros dinâmicos e históricos persistam intactos entre alternâncias de branch ou deploys de código.

---

## 4. Estrutura do Esquema Relacional

O banco implementa 6 tabelas canônicas:

1. **`master_empresas`**: Cadastro mestre de unidades da rede (`empresa_codigo` PK, `cod_web`, `razao_social`, `nome_fantasia`, `apelido`, `cnpj`, `situacao`, `autorizado_escrita_despesa`).
2. **`master_contas_financeiras`**: Contas financeiras oficiais do webPosto e contas bancárias vinculadas (`id` PK, `empresa_codigo` FK, `conta_codigo_erp`, `descricao_erp`, `tipo_conta`, `banco_nome`, `agencia`, `conta_numero`, `permite_debito_despesa`, `status_vinculo`).
3. **`master_planos_conta`**: Catálogo oficial do plano de contas gerencial (`plano_conta_codigo` PK, `descricao_gerencial`, `natureza`, `hierarquia`, `apura_dre`, `categoria_logos`).
4. **`master_centros_custo`**: Centros de custo operacionais e administrativos (`centro_custo_codigo` PK, `descricao`, `empresa_codigo`, `tipo_centro_custo`).
5. **`master_fornecedores`**: Fornecedores cadastrados no ERP, recebedores bancários e beneficiários econômicos (`id` PK, `fornecedor_codigo_erp`, `cnpj_cpf`, `razao_social`, `nome_fantasia`, `empresa_codigo`, `tipo_relacao`).
6. **`master_data_audit_log`**: Trilha de auditoria append-only para todas as inserções, atualizações e resolução de pendências cadastrais (`id` PK, `tabela`, `registro_id`, `acao`, `dados_anteriores`, `dados_novos`, `motivo`, `autor`, `timestamp`).

---

## 5. Estratégia de Carga (Seed) e Sincronização Incremental

O catálogo opera em 2 camadas:
1. **Camada de Inicialização Determinística (Offline):**
   - Na ausência do banco ou na primeira carga, o serviço lê os artefatos locais consolidados (`units.json`, `account_category_mapping.json`, `financial_origin_matrix.json`) e popula o banco com status devidamente marcado (`CONFIRMADO` para cadastros oficiais, `PENDENTE` para vínculos não resolvidos como o Banco do Brasil da Casa Caiada).
2. **Camada de Sincronização Incremental (Futura - Read Only):**
   - Quando autorizada a sincronização online via OpenAPI (`/INTEGRACAO/V1/EMPRESAS`, `/CONTAS`, `/CENTROS_CUSTO`, `/PLANOS_CONTA_GERENCIAL`), o serviço executa `UPSERT` idempotente, comparando hashes de conteúdo e gravando em `master_data_audit_log` qualquer alteração detectada.

---

## 6. Procedimento de Backup e Recuperação

1. **Backup Quente Online:**
   ```python
   # Execução via SQLite Online Backup API (zero travamento de leituras)
   con.execute("VACUUM INTO 'data/master_data/backups/master_data_backup.sqlite3'")
   ```
2. **Recuperação:**
   - Restauração atômica do arquivo único `.sqlite3` para o diretório de dados, com reconstrução imediata dos índices.

---

## 7. Conclusão da Decisão

A escolha de `WebPosto_API/data/master_data/master_data.sqlite3`:
- Respeita integralmente **REUSE > ADAPT > CREATE**;
- Não cria dependências externas (Postgres / Redis / Supabase);
- Garante integridade referencial, consultas <1ms e trilha de auditoria append-only;
- Mantém o sistema 100% operacional no modo offline e isolado.
