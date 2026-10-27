"""Adapter para consulta e agrupamento de vendas por caixa e operador no webPosto."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from ..domain.models import Unidade
from .webposto_http import WebPostoErro, paginar

PATH_VENDAS = "/INTEGRACAO/VENDA"
logger = logging.getLogger(__name__)


def _decimal(v: Any) -> Decimal:
    return Decimal(str(v or 0))


async def buscar_vendas_por_caixa(
    unidade: Unidade,
    inicio: date,
    fim: date,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[int, dict[int, Decimal]]:
    """Retorna {caixa_codigo: {funcionario_codigo: total_vendas}}."""
    resultado: dict[int, dict[int, Decimal]] = {}
    try:
        linhas = await paginar(
            unidade,
            PATH_VENDAS,
            {
                "empresaCodigo": unidade.empresa_codigo,
                "dataInicial": inicio.isoformat(),
                "dataFinal": fim.isoformat(),
            },
            limite=2000,
            client=client,
        )
        for row in linhas:
            if row.get("cancelada") == "S":
                continue
            cx = row.get("caixaCodigo")
            f = row.get("funcionarioCodigo")
            tot = _decimal(row.get("totalVenda"))
            if cx and f:
                if cx not in resultado:
                    resultado[cx] = {}
                resultado[cx][f] = resultado[cx].get(f, Decimal(0)) + tot
    except Exception as exc:
        logger.warning("Falha ao buscar vendas por caixa unidade=%s: %s", unidade.empresa_codigo, exc)
    return resultado
