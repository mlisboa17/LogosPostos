# CHECKPOINT — LOGOS PLANOS-CONTA-SYNC-01

## Sincronização do Catálogo Global de Planos de Conta e Pré-Validador de Despesas

**Data:** 23/10/2026  
**Branch:** `feature/cash-audit-fechamento`  
**Escopo:** Catálogo global compartilhado entre todas as empresas (`5555`, `11495`, `74014`, `118508`)  
**Modo Operacional:** Somente leitura contra ERP (`GET /INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL`)  
**ERP Writes:** **ZERO** (Ausência total de `POST`, `PUT`, `PATCH`, `DELETE`)  
**Status do Piloto:** Bloqueado (Conta `27173` permanece não autorizada para débito; lançamento de R$ 626,00 não executado)

---

### 1. Diagnóstico do Git

- **Sintoma:** Comandos de status ou diff podem apresentar `fatal: this operation must be run in a work tree` se executados sem especificar `--work-tree` a partir de diretórios internos `.git` ou após worktrees auxiliares órfãos.
- **Diagnóstico:** O repositório canônico está íntegro. O worktree auxiliar `LogosPostos-match` estava registrado em `.git/worktrees/` como prunável. O repositório canônico em `C:\Projetos\LOGOS\LogosPostos` responde perfeitamente na branch obrigatória `feature/cash-audit-fechamento`.
- **Condição da Branch:** `HEAD` local em `37ec46d3337a1c1ca8dbf356cbadf11dcb5bf16a`, 1 commit à frente do remoto `logos/feature/cash-audit-fechamento` (`a6bf1c8`).
- **Ação:** Nenhuma operação destrutiva (reset, clean, checkout forçado) foi executada.

---

### 2. Backup Verificável do SQLite

Antes da aplicação da sincronização na base local operacional, foi gerado backup verificado:
- **Origem:** `WebPosto_API/data/master_data/master_data.sqlite3`
- **Backup:** `WebPosto_API/data/master_data/master_data.pre_sync_01.20261023T203802Z.sqlite3.bak`
- **Tamanho:** 200.704 bytes
- **SHA-256:** `98BA4A02B4648BF0C84121FED7F2F91CB664B9BFF10996211EB01C6D799699D4`

---

### 3. Migração 001 Aplicada

- **Arquivo:** `WebPosto_API/src/modules/master_data/adapters/migrations/migration_001_planos_conta_hierarquia.py`
- **Tabela:** `master_planos_conta` enriquecida com:
  - `hierarquia TEXT`, `pai_codigo INTEGER`, `pai_hierarquia TEXT`, `nivel INTEGER`, `eh_folha INTEGER`, `candidato_lancavel INTEGER`, `observado_ultima_sincronizacao INTEGER`, `hash_origem TEXT`, `sincronizado_em TEXT`.
  - Índices hierárquicos e de busca: `idx_planos_hierarquia`, `idx_planos_pai`, `idx_planos_folha`, `idx_planos_lancavel`, `idx_planos_observado`.
- **Nova Tabela de Auditoria de Sincronizações:** `master_sincronizacao_log` registrando data/hora, modo, total oficial, total anterior, inseridos, atualizados, inalterados, não observados, hash e payload JSON sanitizado.
- **Reversibilidade:** Possui função `reverter(db_path)` documentada e testada.

---

### 4. Arquitetura da Sincronização

Implementado em `WebPosto_API/src/modules/master_data/application/plano_contas_sync_service.py`:
1. **Fonte Oficial:** `GET /INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL` com paginação estrita (`limite=2000`) e detecção de loop de cursor.
2. **Escopo Global Compartilhado:** Não duplica planos por empresa. O catálogo contábil gerencial do webPosto é único e global para o grupo.
3. **Modos:**
   - `dry-run`: simula a sincronização e calcula métricas sem alterar o SQLite.
   - `apply`: persiste em transação atômica única com rollback integral se houver falha.
   - `offline`: aceita injeção direta de fixtures (como `PLANOS_CONTA_MASTER_01.json`).
4. **Proteção de Ausência Oficial:** Planos locais que deixam de aparecer no retorno oficial recebem `observado_ultima_sincronizacao = 0` e `candidato_lancavel = 0`. **Nunca são deletados.**
5. **Idempotência Absoluta:** Repetições do mesmo catálogo geram 0 novos registros de auditoria em `master_data_audit_log` e marcam todos os planos como inalterados.
6. **Controle de Concorrência:** `threading.Lock` impede execuções simultâneas.

---

### 5. Pré-Validador Atualizado

Atualizado em `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py` e `MasterDataService`:
1. **Conta-Pai Bloqueada:** `29021 — PRO LABORE` e `148303 — MARCIO LISBOA` são rejeitadas categoricamente como contas-pai estruturais (`eh_folha = False`, `candidato_lancavel = False`).
2. **Folha Candidata:** `158764 — MARCIO-PROLABORE` é reconhecida como folha oficial candidata (`eh_folha = True`), emitindo aviso expresso de que **não constitui autorização para lançamento**.
3. **Plano Desconhecido Bloqueado:** Bloqueia qualquer plano ausente do catálogo.
4. **Plano Não Observado Bloqueado:** Bloqueia preventivamente planos com `observado_ultima_sincronizacao = False`.
5. **Catálogo Vencido Bloqueado:** Bloqueia operações se a última sincronização bem-sucedida tiver ocorrido há mais de `max_dias_desatualizado` (padrão 30 dias).
6. **Todas as barreiras mantidas:** Contas bancárias, travas `.env`, confirmação humana, duplicidade e idempotência estritamente preservadas.

---

### 6. Resultados dos Testes Offline

- `WebPosto_API/tests/unit/master_data/test_plano_contas_sync.py`: **17 passed** (100% dos cenários exigidos).
- `WebPosto_API/tests/unit/master_data/` (suíte completa): **73 passed** (56 existentes + 17 novos).
- `WebPosto_API/tests/unit/cash_reconciliation/` (pré-validação e escrita): **50 passed** (zero regressões).
- **Total:** 123 testes aprovados, 0 falhas.

---

### 7. Evidência de ERP Writes = Zero

- Nenhuma chamada `POST`, `PUT`, `PATCH`, `DELETE` contra endpoints do webPosto foi realizada.
- O teste `test_16_ausencia_total_post_put_patch_delete` valida via monkeypatch que qualquer tentativa de mutação HTTP dispara exceção de segurança imediata.
- A sincronização executou exclusivamente via fixture oficial offline sanitizada (`PLANOS_CONTA_MASTER_01.json`).
