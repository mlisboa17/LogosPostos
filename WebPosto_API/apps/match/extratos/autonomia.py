"""Autonomia gradual, limitada e revogável para decisões de extratos."""
from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from src.modules.cash_reconciliation.domain.tempo import hoje

APROVACOES_PARA_AUTOMATICO = 5
LIMITE_POR_LANCAMENTO = Decimal("500.00")
LIMITE_DIARIO_POR_CONTA = Decimal("2000.00")

_TRANSFERENCIAS_PROPRIAS = (
    "entre contas",
    "conta propria",
    "contas proprias",
    "minhas contas",
    "mesma titularidade",
    "transferencia interna",
    "transferencia propria",
)


def normalizar(texto: str) -> str:
    ascii_texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    sem_digitos = "".join(" " if char.isdigit() else char.lower() for char in ascii_texto)
    return " ".join(sem_digitos.split())


def _classificacao(valor) -> str:
    if isinstance(valor, dict):
        codigo = valor.get("codigo")
        if codigo is not None:
            return str(codigo)
        valor = valor.get("nome") or ""
    texto = str(valor or "").strip()
    return texto if texto.isdigit() else normalizar(texto)


def chave_lancamento(conta_id: int, descricao: str, plano, centro) -> str:
    padrao = normalizar(descricao)
    return f"lanc:{conta_id}:{padrao}:{_classificacao(plano)}:{_classificacao(centro)}"


def chave_importacao(conta_id: int) -> str:
    return f"importar:{conta_id}"


def registrar_decisao(con, chave_tipo: str, aprovada: bool, corrigida: bool) -> None:
    con.execute("BEGIN IMMEDIATE")
    try:
        row = con.execute(
            "SELECT aprovacoes_seguidas, desligado_por_admin FROM autonomia WHERE chave_tipo=?",
            (chave_tipo,),
        ).fetchone()
        contador = row["aprovacoes_seguidas"] if row else 0
        desligado = row["desligado_por_admin"] if row else 0
        if aprovada and not corrigida:
            contador += 1
            automatico = int(contador >= APROVACOES_PARA_AUTOMATICO and not desligado)
        else:
            contador = 0
            automatico = 0
        con.execute(
            """INSERT INTO autonomia
               (chave_tipo, aprovacoes_seguidas, automatico, desligado_por_admin, atualizado_em)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(chave_tipo) DO UPDATE SET
               aprovacoes_seguidas=excluded.aprovacoes_seguidas,
               automatico=excluded.automatico,
               atualizado_em=excluded.atualizado_em""",
            (chave_tipo, contador, automatico, desligado,
             datetime.now(timezone.utc).isoformat()),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise


def pode_automatico(con, chave_tipo: str, valor: Decimal | None, conta_id: int) -> bool:
    row = con.execute(
        "SELECT automatico, desligado_por_admin FROM autonomia WHERE chave_tipo=?",
        (chave_tipo,),
    ).fetchone()
    if row is None or not row["automatico"] or row["desligado_por_admin"]:
        return False
    if chave_tipo.startswith("importar:"):
        return True
    if not chave_tipo.startswith(f"lanc:{conta_id}:") or valor is None:
        return False
    valor = Decimal(valor)
    if valor >= 0 or abs(valor) > LIMITE_POR_LANCAMENTO:
        return False
    prefixo = f"lanc:{conta_id}:"
    descricao_plano_centro = chave_tipo[len(prefixo):]
    padrao = descricao_plano_centro.rsplit(":", 2)[0]
    if any(palavra in padrao for palavra in _TRANSFERENCIAS_PROPRIAS):
        return False

    hoje_iso = hoje().isoformat()
    total = Decimal("0")
    for aprovado in con.execute(
        """SELECT resumo_json FROM aprovacao
           WHERE tipo='lancamento' AND conta_bancaria_id=? AND situacao='automatica'""",
        (conta_id,),
    ):
        resumo = json.loads(aprovado["resumo_json"])
        if resumo.get("data") == hoje_iso:
            total += abs(Decimal(str(resumo.get("valor") or 0)))
    return total + abs(valor) <= LIMITE_DIARIO_POR_CONTA


def definir_automatico(con, chave_tipo: str, ligado: bool) -> None:
    row = con.execute(
        "SELECT aprovacoes_seguidas FROM autonomia WHERE chave_tipo=?", (chave_tipo,)
    ).fetchone()
    if row is None:
        contador = 0
        con.execute(
            """INSERT INTO autonomia
               (chave_tipo, aprovacoes_seguidas, automatico, desligado_por_admin, atualizado_em)
               VALUES (?, 0, 0, ?, ?)""",
            (chave_tipo, int(not ligado), datetime.now(timezone.utc).isoformat()),
        )
    else:
        contador = row["aprovacoes_seguidas"]
        con.execute(
            """UPDATE autonomia SET automatico=?, desligado_por_admin=?, atualizado_em=?
               WHERE chave_tipo=?""",
            (
                int(ligado and contador >= APROVACOES_PARA_AUTOMATICO),
                int(not ligado),
                datetime.now(timezone.utc).isoformat(),
                chave_tipo,
            ),
        )
    con.commit()
