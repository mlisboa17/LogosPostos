"""Consultas e gravações locais para contas e extratos."""
from __future__ import annotations

import sqlite3
import json
from datetime import timedelta

from src.modules.cash_reconciliation.domain.tempo import agora, ler_data_hora


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


def conta_por_id(con, conta_id: int) -> sqlite3.Row | None:
    return con.execute(
        """SELECT c.*, p.nome AS posto_nome, p.apelido AS posto_apelido
           FROM conta_bancaria c JOIN posto p ON p.id=c.posto_id
           WHERE c.id=? AND c.ativo=1""",
        (conta_id,),
    ).fetchone()


def linhas_pendentes(con, conta_id: int) -> list[sqlite3.Row]:
    linhas = con.execute(
        "SELECT * FROM extrato_linha WHERE conta_bancaria_id=? AND importada_webposto=0 ORDER BY data, id",
        (conta_id,),
    ).fetchall()
    bloqueadas = set()
    for aprovacao in con.execute(
        """SELECT * FROM aprovacao WHERE tipo='importar_extrato'
           AND conta_bancaria_id=? AND situacao IN ('recusada','falhou')
           AND reproposta_em IS NULL""",
        (conta_id,),
    ):
        if (aprovacao["situacao"] == "falhou"
                and agora() - ler_data_hora(
                    aprovacao["decidida_em"] or aprovacao["criada_em"]
                ) >= timedelta(hours=1)):
            continue
        for periodo in json.loads(aprovacao["resumo_json"]).get("periodos", []):
            bloqueadas.update(periodo.get("linha_ids") or [])
    # Não enviar só parte de um dia: o webPosto ignoraria o restante para sempre.
    dias_bloqueados = {linha["data"] for linha in linhas if linha["id"] in bloqueadas}
    return [linha for linha in linhas if linha["data"] not in dias_bloqueados]


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
