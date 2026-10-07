"""Adapter GET /INTEGRACAO/V1/SANGRIAS_CAIXA (contrato validado em producao, ADR-002)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from ..domain.models import Sangria, Unidade
from .webposto_http import WebPostoErro, paginar  # noqa: F401  (WebPostoErro reexportado)

PATH = "/INTEGRACAO/V1/SANGRIAS_CAIXA"
FONTE = f"webPosto{PATH}"


def para_sangria(r: dict[str, Any]) -> Sangria:
    hora = r.get("horaSangria") or "00:00:00"
    return Sangria(
        codigo=r["sangriaCodigo"],
        empresa_codigo=r["empresaCodigo"],
        caixa_codigo=r["caixaCodigo"],
        conta_codigo=r.get("contaCodigo"),
        funcionario_codigo=r["funcionarioCodigo"],
        valor=Decimal(str(r.get("dinheiro") or 0)),
        momento=datetime.fromisoformat(f"{r['dataSangria']}T{hora}"),
        alterada=bool(r.get("alterada")),
    )


async def buscar_sangrias(
    unidade: Unidade,
    inicio: date,
    fim: date,
    *,
    base_url: str | None = None,
    limite: int = 500,
    client: httpx.AsyncClient | None = None,
) -> list[Sangria]:
    params = {"dataInicial": inicio.isoformat(), "dataFinal": fim.isoformat(), "empresaCodigo": unidade.empresa_codigo}
    linhas = await paginar(unidade, PATH, params, base_url=base_url, limite=limite, client=client)
    return [para_sangria(r) for r in linhas if r.get("empresaCodigo") == unidade.empresa_codigo]
