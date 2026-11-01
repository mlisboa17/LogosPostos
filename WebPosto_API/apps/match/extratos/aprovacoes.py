"""Persistência e decisão atômica de aprovações de extratos."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone


JA_RESOLVIDO = "Já resolvido."


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_canonico(resumo: dict) -> str:
    return json.dumps(resumo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def criar(con, tipo: str, posto_id: int, conta_id: int | None, resumo: dict):
    resumo_json = _json_canonico(resumo)
    digest = hashlib.sha256(resumo_json.encode("utf-8")).hexdigest()
    ticket = secrets.token_urlsafe(9)
    cur = con.execute(
        """INSERT INTO aprovacao
           (tipo, conta_bancaria_id, posto_id, resumo_json, hash, situacao, criada_em, ticket)
           VALUES (?,?,?,?,?,'pendente',?,?)""",
        (tipo, conta_id, posto_id, resumo_json, digest, _agora(), ticket),
    )
    con.commit()
    return con.execute("SELECT * FROM aprovacao WHERE id=?", (cur.lastrowid,)).fetchone()


def decidir(con, ticket: str, aprovar: bool, quem: str, canal: str) -> tuple[bool, str]:
    con.execute("BEGIN IMMEDIATE")
    try:
        row = con.execute(
            "SELECT id, situacao FROM aprovacao WHERE ticket=?", (ticket,)
        ).fetchone()
        if row is None or row["situacao"] != "pendente":
            con.rollback()
            return False, JA_RESOLVIDO
        situacao = "aprovada" if aprovar else "recusada"
        resultado = "Aprovação registrada." if aprovar else "Aprovação recusada."
        con.execute(
            """UPDATE aprovacao SET situacao=?, decidida_em=?, decidida_por=?,
               canal_decisao=?, resultado=? WHERE id=? AND situacao='pendente'""",
            (situacao, _agora(), quem, canal, resultado, row["id"]),
        )
        con.commit()
        return True, resultado
    except Exception:
        con.rollback()
        raise


def pendentes(con, postos: list[int] | None = None):
    sql = "SELECT * FROM aprovacao WHERE situacao='pendente'"
    parametros: tuple = ()
    if postos is not None:
        if not postos:
            return []
        sql += " AND posto_id IN (" + ",".join("?" for _ in postos) + ")"
        parametros = tuple(postos)
    return con.execute(sql + " ORDER BY criada_em, id", parametros).fetchall()
