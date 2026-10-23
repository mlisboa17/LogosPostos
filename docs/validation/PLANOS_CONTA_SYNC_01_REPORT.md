# RELATÓRIO DE SINCRONIZAÇÃO — PLANOS-CONTA-SYNC-01

## Sincronização do Catálogo Global de Planos de Conta (webPosto -> LOGOS)

**Ambiente:** LOGOS Master Data  
**Data da Execução:** 23/10/2026  
**Branch:** `feature/cash-audit-fechamento`  
**Escopo:** Catálogo global compartilhado para todas as empresas (`5555`, `11495`, `74014`, `118508`)  
**ERP Writes:** **ZERO** (Ausência total de mutações HTTP `POST`, `PUT`, `PATCH`, `DELETE`)

---

### 1. Métricas da Sincronização

| Métrica | Execução 1 (Dry-Run) | Execução 2 (Apply Local) | Execução 3 (Idempotência / Re-Apply) |
| :--- | :--- | :--- | :--- |
| **Horário UTC** | `2026-10-23T21:13:31Z` | `2026-10-23T21:14:09Z` | `2026-10-23T21:15:40Z` |
| **Origem** | `PLANOS_CONTA_MASTER_01.json` | `PLANOS_CONTA_MASTER_01.json` | `PLANOS_CONTA_MASTER_01.json` |
| **Modo** | `DRY_RUN` | `APPLY` | `APPLY` |
| **Sucesso** | `true` | `true` | `true` |
| **Quantidade Oficial Recebida** | 251 | 251 | 251 |
| **Quantidade Anterior na Base** | 200 | 200 | 251 |
| **Novos Planos Inseridos** | 51 | 51 | 0 |
| **Planos Atualizados** | 200 | 200 | 0 |
| **Planos Inalterados** | 0 | 0 | 251 |
| **Planos Não Observados** | 0 | 0 | 0 |
| **Erros** | `null` | `null` | `null` |
| **Hash SHA-256 do Catálogo** | `35D766AF0C0E5A6238437D8BCADA3D6C48BB8277E9BEF862A49EED0392DA0D96` | `35D766AF0C0E5A6238437D8BCADA3D6C48BB8277E9BEF862A49EED0392DA0D96` | `35D766AF0C0E5A6238437D8BCADA3D6C48BB8277E9BEF862A49EED0392DA0D96` |
| **Tempo de Execução** | ~28 ms | ~73 ms | ~45 ms |
| **Total Final de Planos Locais** | 200 (não alterado) | **251** | **251** |

---

### 2. Backup Verificável do SQLite

Antes da execução em modo `APPLY`, foi gerada cópia de segurança física:
- **Arquivo de Backup:** `WebPosto_API/data/master_data/master_data.pre_sync_01.20261023T203802Z.sqlite3.bak`
- **Tamanho:** 200.704 bytes
- **Hash SHA-256:** `98BA4A02B4648BF0C84121FED7F2F91CB664B9BFF10996211EB01C6D799699D4`

---

### 3. Detalhamento dos Planos Inseridos e Atualizados

1. **51 Planos Inseridos:**
   - Inclui a folha candidata de pró-labore `158764 — MARCIO-PROLABORE` (`2.02.05.005`).
   - Inclui a conta-pai `148303 — MARCIO LISBOA` (`2.02.05`).
   - Inclui as subcontas irmãs: `148304` (MARCIO CARRO), `148305` (BOLETO PAGO CC EMPRESA), `148306` (TRANSFERENCIAS P CONTA PF), `148307` (CARTAO EMPRESA).
   - Inclui demais contas operacionais oficiais ausentes no bootstrap legado (ex: `198595 — PEDREIRO`).
2. **200 Planos Atualizados:**
   - Enriquecidos com hierarquia formal oficial (ex: `2.02`), código e hierarquia do pai estrutural (`pai_codigo`, `pai_hierarquia`), profundidade (`nivel`), flag determinística de folha (`eh_folha`), e flag de candidato (`candidato_lancavel`).
   - Contas-pai históricas como `29021 — PRO LABORE` atualizadas para `eh_folha = 0`, `candidato_lancavel = 0`, `permite_despesa = 0`.
3. **Zero Planos Não Observados:**
   - Todos os 200 códigos preexistentes na base local foram reconhecidos no catálogo oficial de 251 contas do webPosto.

---

### 4. Governança e Regras do Pré-Validador

O módulo `MasterDataService` e o adaptador `validar_aprovacao_para_escrita` agora aplicam:
1. **Bloqueio de Contas-Pai:**
   - `29021 — PRO LABORE` é rejeitada por ser conta-pai (`2.02`).
   - `148303 — MARCIO LISBOA` é rejeitada por ser conta-pai (`2.02.05`).
2. **Reconhecimento de Folha Candidata:**
   - `158764 — MARCIO-PROLABORE` é reconhecida como folha candidata válida (`2.02.05.005`), mas **não constitui autorização para lançamento**.
3. **Plano Desconhecido Bloqueado:**
   - Qualquer código inexistente no catálogo local é rejeitado na pré-validação antes de qualquer montagem de payload ERP.
4. **Plano Não Observado Bloqueado:**
   - Se um plano local deixar de ser retornado pelo webPosto em sincronizações futuras, ele é marcado com `observado_ultima_sincronizacao = 0` e seu uso em novos lançamentos é preventivamente bloqueado. Nenhuma exclusão silenciosa é feita.
5. **Catálogo Vencido Bloqueado:**
   - Se a sincronização mais recente tiver idade superior a 30 dias (configurável via `max_dias_desatualizado`), operações contábeis são bloqueadas exigindo sincronização prévia.

---

### 5. Procedimento Operacional: Como Sincronizar Manualmente ou Antes de Operações

O script CLI `WebPosto_API/scripts/sincronizar_planos_conta.py` disponibiliza interface completa:

#### A. Consulta do Status da Última Sincronização
```powershell
python WebPosto_API/scripts/sincronizar_planos_conta.py --status
```

#### B. Simulação Prévia (Dry-Run Seguro)
```powershell
python WebPosto_API/scripts/sincronizar_planos_conta.py --dry-run
```
Ou com fixture offline:
```powershell
python WebPosto_API/scripts/sincronizar_planos_conta.py --dry-run --offline-file docs/validation/PLANOS_CONTA_MASTER_01.json
```

#### C. Aplicação Local da Sincronização
```powershell
python WebPosto_API/scripts/sincronizar_planos_conta.py --apply
```
Ou com fixture offline:
```powershell
python WebPosto_API/scripts/sincronizar_planos_conta.py --apply --offline-file docs/validation/PLANOS_CONTA_MASTER_01.json
```

#### D. Preparação para Execução Periódica Futura
O serviço `PlanoContasSyncService` foi projetado para chamada programável:
- Pode ser invocado no início de cada rotina de conciliação diária.
- Pode ser acionado sob demanda pelo operador contábil.
- Em caso de falha de rede ou resposta vazia inesperada do ERP, a transação atômica aborta sem corromper a base local.

---

### 6. Evidência de Barreiras Preservadas

- **Conta 27173 (BB Casa Caiada):** Permanece como `CONTA_CORRENTE LOCAL` com `permite_debito_despesa = False`. Fora da allowlist de escrita.
- **Despesa de R$ 626,00:** Permanece **não lançada**.
- **ERP Writes:** Zero chamadas mutacionais efetuadas.
