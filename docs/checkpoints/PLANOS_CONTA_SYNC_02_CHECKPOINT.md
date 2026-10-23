# CHECKPOINT — LOGOS PLANOS-CONTA-SYNC-02

## Sincronização da Nova Conta Oficial: 198966 — SAÍDAS PENDENTES DE CLASSIFICAÇÃO

**Data:** 23/10/2026  
**Fonte:** `GET /INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL` (webPosto)  
**Modo:** Somente leitura contra ERP  
**ERP Writes:** **ZERO** (sem `POST`, `PUT`, `PATCH`, `DELETE`)  
**Status do Piloto:** Bloqueado (Conta `27173` não liberada; lançamento de R$ 626,00 não executado)

---

### 1. Correspondência Única Oficial Confirmada

- **planoContaCodigo:** `198966`
- **Hierarquia:** `2.04.10`
- **Descrição:** `SAÍDAS PENDENTES DE CLASSIFICAÇÃO`
- **Pai Estrutural:** `29031 — OUTRAS MOVIMENTACOES DE SAIDA` (`2.04`)
- **Natureza:** `DESPESA` (`D`)
- **Ativa:** `True`
- **eh_folha:** `True` (zero subcontas existentes sob 2.04.10)
- **candidato_lancavel:** `False` (**Estritamente bloqueado para uso real até a implementação da fila de revisão**)
- **permite_despesa:** `False`
- **observado_ultima_sincronizacao:** `True`

---

### 2. Métricas da Sincronização e Idempotência

- **Total Oficial:** 251 -> **252** (+1 novo plano oficial cadastrado no webPosto)
- **Total Local Anterior:** 251
- **Dry-Run:** 252 oficiais, 1 a inserir (`198966`), 0 a atualizar, 251 inalterados, 0 não observados.
- **Apply Local:** 1 inserido (`198966`), 0 atualizados, 251 inalterados. Total final local: **252 planos**.
- **Re-Apply (Idempotência):** 0 inseridos, 0 atualizados, 252 inalterados, 0 falsos logs.
- **Hash do Catálogo (SHA-256):** `C3674C5BD6C21DB31A649CA4D0C92B12830DC247C6DF32CF75926A6C41A06CC1`

---

### 3. Backup Verificável do SQLite

- **Arquivo:** `WebPosto_API/data/master_data/master_data.pre_sync_198966.20261023T214500Z.sqlite3.bak`
- **Tamanho:** 618.496 bytes
- **SHA-256:** `DF19DB7A2B4D9FFA3FA35784CEDEFC035DAF458C1811C95E0497ACEEA9096D10`

---

### 4. Testes e Regressão

- `WebPosto_API/tests/unit/master_data/test_plano_contas_sync.py`: **18 passed** (incluindo `test_18` cobrindo o bloqueio de lançamento da conta 198966).
