"""Migração 002: Fila local auditável de revisão e aprendizagem para classificações incertas.

Tabelas criadas:
- fila_revisao_classificacao: Fila com ciclo de vida (PENDENTE_REVISAO, CLASSIFICADO, BLOQUEADO, CANCELADO)
- fila_revisao_historico: Trilha imutável e append-only de mudanças e auditoria
- classificacao_exemplos_confirmados: Casos revisados por humanos que servem como exemplos confirmados de aprendizado
- classificacao_regras_candidatas: Regras extraídas que exigem múltiplos casos (mínimo 3) e aprovação explícita antes de promoção
"""

from __future__ import annotations

import sqlite3
from typing import Any

MIGRATION_ID = "002_fila_revisao_classificacao"

TABELAS = [
    """
    CREATE TABLE IF NOT EXISTS fila_revisao_classificacao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hash_idempotencia TEXT UNIQUE NOT NULL,
        empresa_codigo INTEGER NOT NULL,
        conta_financeira_codigo INTEGER NOT NULL,
        data_movimento TEXT NOT NULL,
        valor TEXT NOT NULL,
        descricao TEXT NOT NULL,
        referencia_evidencias TEXT,
        sugestao_plano_codigo INTEGER,
        sugestao_plano_descricao TEXT,
        confianca_ia REAL DEFAULT 0.0,
        justificativa_ia TEXT,
        travas_encontradas TEXT,
        status TEXT NOT NULL DEFAULT 'PENDENTE_REVISAO' CHECK(status IN ('PENDENTE_REVISAO', 'CLASSIFICADO', 'BLOQUEADO', 'CANCELADO')),
        decisao_humana TEXT,
        plano_definitivo_codigo INTEGER,
        plano_definitivo_descricao TEXT,
        centro_custo_definitivo_codigo INTEGER,
        revisor TEXT,
        revisado_em TEXT,
        versao INTEGER NOT NULL DEFAULT 1,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fila_revisao_historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pendencia_id INTEGER NOT NULL,
        acao TEXT NOT NULL,
        status_anterior TEXT,
        status_novo TEXT NOT NULL,
        usuario_ou_sistema TEXT NOT NULL,
        justificativa TEXT,
        detalhes_json TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (pendencia_id) REFERENCES fila_revisao_classificacao(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS classificacao_exemplos_confirmados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pendencia_id INTEGER,
        empresa_codigo INTEGER NOT NULL,
        descricao_padronizada TEXT NOT NULL,
        valor TEXT,
        plano_conta_codigo INTEGER NOT NULL,
        plano_conta_descricao TEXT NOT NULL,
        revisor TEXT NOT NULL,
        confirmado_em TEXT NOT NULL,
        hash_exemplo TEXT UNIQUE NOT NULL,
        FOREIGN KEY (pendencia_id) REFERENCES fila_revisao_classificacao(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS classificacao_regras_candidatas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        padrao_descricao TEXT NOT NULL,
        empresa_codigo INTEGER,
        plano_conta_sugerido INTEGER NOT NULL,
        total_casos_confirmados INTEGER NOT NULL DEFAULT 1,
        casos_minimos_promocao INTEGER NOT NULL DEFAULT 3,
        status_regra TEXT NOT NULL DEFAULT 'CANDIDATA' CHECK(status_regra IN ('CANDIDATA', 'PROMOVIDA', 'REJEITADA')),
        aprovado_por TEXT,
        aprovado_em TEXT,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL
    );
    """,
]

INDICES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_fila_rev_hash ON fila_revisao_classificacao(hash_idempotencia);",
    "CREATE INDEX IF NOT EXISTS idx_fila_rev_status ON fila_revisao_classificacao(status);",
    "CREATE INDEX IF NOT EXISTS idx_fila_rev_empresa ON fila_revisao_classificacao(empresa_codigo, data_movimento);",
    "CREATE INDEX IF NOT EXISTS idx_fila_hist_pend ON fila_revisao_historico(pendencia_id);",
    "CREATE INDEX IF NOT EXISTS idx_exemp_desc ON classificacao_exemplos_confirmados(empresa_codigo, descricao_padronizada);",
    "CREATE INDEX IF NOT EXISTS idx_regras_padrao ON classificacao_regras_candidatas(padrao_descricao, status_regra);",
]


def migrar(conn: sqlite3.Connection) -> dict[str, Any]:
    """Aplica a migração 002 de forma idempotente."""
    for ddl in TABELAS:
        conn.execute(ddl)

    for idx_sql in INDICES:
        conn.execute(idx_sql)

    return {
        "migration_id": MIGRATION_ID,
        "status": "APLICADA",
        "tabelas_criadas": [
            "fila_revisao_classificacao",
            "fila_revisao_historico",
            "classificacao_exemplos_confirmados",
            "classificacao_regras_candidatas",
        ],
    }


def reverter(conn: sqlite3.Connection) -> dict[str, Any]:
    """Reverte a migração 002 de forma segura."""
    conn.execute("DROP TABLE IF EXISTS fila_revisao_historico;")
    conn.execute("DROP TABLE IF EXISTS classificacao_exemplos_confirmados;")
    conn.execute("DROP TABLE IF EXISTS classificacao_regras_candidatas;")
    conn.execute("DROP TABLE IF EXISTS fila_revisao_classificacao;")

    return {
        "migration_id": MIGRATION_ID,
        "status": "REVERTIDA",
        "tabelas_removidas": [
            "fila_revisao_historico",
            "classificacao_exemplos_confirmados",
            "classificacao_regras_candidatas",
            "fila_revisao_classificacao",
        ],
    }
