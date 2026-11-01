"""Consultas e gravações locais para contas e extratos."""
from __future__ import annotations

import sqlite3


def contas(con) -> list[sqlite3.Row]:
    return con.execute(
        """SELECT c.*, p.nome AS posto_nome, p.apelido AS posto_apelido
           FROM conta_bancaria c JOIN posto p ON p.id=c.posto_id
           WHERE c.ativo=1 ORDER BY p.nome, c.banco, c.conta_sufixo"""
    ).fetchall()


def conta_por_banco(con, banco: str, sufixo: str) -> sqlite3.Row | None:
    return con.execute(
        """SELECT c.*, p.nome AS posto_nome, p.apelido AS posto_apelido
           FROM conta_bancaria c JOIN posto p ON p.id=c.posto_id
           WHERE c.ativo=1 AND UPPER(c.banco)=UPPER(?) AND c.conta_sufixo=?""",
        (banco, sufixo),
    ).fetchone()


def linhas_pendentes(con, conta_id: int) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM extrato_linha WHERE conta_bancaria_id=? AND importada_webposto=0 ORDER BY data, id",
        (conta_id,),
    ).fetchall()


def marcar_importadas(con, linha_ids: list[int]) -> None:
    if not linha_ids:
        return
    marcadores = ",".join("?" for _ in linha_ids)
    con.execute(f"UPDATE extrato_linha SET importada_webposto=1 WHERE id IN ({marcadores})", linha_ids)


def arquivos(con, limite: int = 50) -> list[sqlite3.Row]:
    if limite < 1:
        return []
    return con.execute(
        "SELECT * FROM extrato_arquivo ORDER BY recebido_em DESC, id DESC LIMIT ?",
        (limite,),
    ).fetchall()
