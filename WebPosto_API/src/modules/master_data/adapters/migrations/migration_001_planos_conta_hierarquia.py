"""Migração 001: Adição de estrutura hierárquica e controle de sincronização aos planos de conta.

Campos adicionados em master_planos_conta:
- hierarquia: código hierárquico estruturado (ex: '2.02.05.005')
- pai_codigo: identificador numérico da conta pai direta (ex: 148303)
- pai_hierarquia: hierarquia da conta pai direta (ex: '2.02.05')
- nivel: profundidade estrutural na árvore (ex: 4)
- eh_folha: 1 se for nó folha (lançável), 0 se for conta pai
- candidato_lancavel: 1 se elegível a lançamento, 0 se bloqueado/pai
- observado_ultima_sincronizacao: 1 se presente no último retorno oficial, 0 se ausente
- hash_origem: SHA-256 do lote ou payload de origem
- sincronizado_em: timestamp UTC da última sincronização bem-sucedida

Tabela criada:
- master_sincronizacao_log: histórico append-only de execuções de sincronização.
"""

from __future__ import annotations

import sqlite3
from typing import Any

MIGRATION_ID = "001_planos_conta_hierarquia"

COLUNAS_NOVAS: list[tuple[str, str]] = [
    ("hierarquia", "TEXT"),
    ("pai_codigo", "INTEGER"),
    ("pai_hierarquia", "TEXT"),
    ("nivel", "INTEGER NOT NULL DEFAULT 0"),
    ("eh_folha", "INTEGER NOT NULL DEFAULT 1"),
    ("candidato_lancavel", "INTEGER NOT NULL DEFAULT 1"),
    ("observado_ultima_sincronizacao", "INTEGER NOT NULL DEFAULT 1"),
    ("hash_origem", "TEXT"),
    ("sincronizado_em", "TEXT"),
]

INDICES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_planos_hierarquia ON master_planos_conta(hierarquia);",
    "CREATE INDEX IF NOT EXISTS idx_planos_pai ON master_planos_conta(pai_codigo);",
    "CREATE INDEX IF NOT EXISTS idx_planos_folha ON master_planos_conta(eh_folha);",
    "CREATE INDEX IF NOT EXISTS idx_planos_lancavel ON master_planos_conta(candidato_lancavel);",
    "CREATE INDEX IF NOT EXISTS idx_planos_observado ON master_planos_conta(observado_ultima_sincronizacao);",
]

DDL_SINCRONIZACAO_LOG = """
CREATE TABLE IF NOT EXISTS master_sincronizacao_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_entidade TEXT NOT NULL,
    iniciado_em TEXT NOT NULL,
    finalizado_em TEXT,
    sucesso INTEGER NOT NULL,
    modo TEXT NOT NULL,
    origem TEXT NOT NULL,
    total_oficial INTEGER NOT NULL DEFAULT 0,
    total_anterior INTEGER NOT NULL DEFAULT 0,
    total_inseridos INTEGER NOT NULL DEFAULT 0,
    total_atualizados INTEGER NOT NULL DEFAULT 0,
    total_inalterados INTEGER NOT NULL DEFAULT 0,
    total_nao_observados INTEGER NOT NULL DEFAULT 0,
    hash_catalogo TEXT,
    detalhes_json TEXT,
    erro TEXT
);
"""


def _colunas_existentes(conn: sqlite3.Connection, tabela: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({tabela})").fetchall()
    return {row[1] for row in rows}


def migrar(conn: sqlite3.Connection) -> dict[str, Any]:
    """Aplica a migração 001 de forma idempotente."""
    existentes = _colunas_existentes(conn, "master_planos_conta")
    adicionadas: list[str] = []

    for nome_coluna, definicao in COLUNAS_NOVAS:
        if nome_coluna not in existentes:
            conn.execute(f"ALTER TABLE master_planos_conta ADD COLUMN {nome_coluna} {definicao};")
            adicionadas.append(nome_coluna)

    for idx_sql in INDICES:
        conn.execute(idx_sql)

    conn.execute(DDL_SINCRONIZACAO_LOG)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_log_tipo ON master_sincronizacao_log(tipo_entidade, iniciado_em);")

    return {
        "migration_id": MIGRATION_ID,
        "status": "APLICADA",
        "colunas_adicionadas": adicionadas,
        "tabelas_criadas": ["master_sincronizacao_log"],
    }


def reverter(conn: sqlite3.Connection) -> dict[str, Any]:
    """Reverte a migração 001 de forma segura."""
    existentes = _colunas_existentes(conn, "master_planos_conta")
    removidas: list[str] = []

    for nome_coluna, _ in reversed(COLUNAS_NOVAS):
        if nome_coluna in existentes:
            conn.execute(f"ALTER TABLE master_planos_conta DROP COLUMN {nome_coluna};")
            removidas.append(nome_coluna)

    conn.execute("DROP TABLE IF EXISTS master_sincronizacao_log;")

    return {
        "migration_id": MIGRATION_ID,
        "status": "REVERTIDA",
        "colunas_removidas": removidas,
        "tabelas_removidas": ["master_sincronizacao_log"],
    }
