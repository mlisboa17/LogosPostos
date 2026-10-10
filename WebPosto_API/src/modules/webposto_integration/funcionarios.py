"""Consulta compartilhada de nomes de funcionários no webPosto."""
from __future__ import annotations

from datetime import date

from .http import UnidadeIntegrada, paginar

PATH_FUNCIONARIOS = "/INTEGRACAO/V1/FUNCIONARIOS"


async def buscar_nomes_funcionarios(
    unidade: UnidadeIntegrada,
    inicio: date,
    fim: date,
) -> dict[int, str]:
    rows = await paginar(
        unidade,
        PATH_FUNCIONARIOS,
        {
            "empresaCodigo": unidade.empresa_codigo,
            "dataInicial": inicio.isoformat(),
            "dataFinal": fim.isoformat(),
        },
    )
    return {
        row["funcionarioCodigo"]: row["nome"]
        for row in rows
        if row.get("empresaCodigo") == unidade.empresa_codigo
        and row.get("funcionarioCodigo") is not None
        and row.get("nome")
    }
