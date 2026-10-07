"""Adapters GET /INTEGRACAO/V1/CAIXAS e /CAIXAS_APRESENTADO (validados em producao 2026-10-06).

CAIXAS_APRESENTADO nao filtra por empresa: o filtro e feito pelos caixaCodigo da unidade.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from ..domain.fechamento import MODALIDADES, Caixa, LinhaModalidade
from ..domain.models import Unidade
from ..domain.tempo import ler_data_hora
from .webposto_http import paginar

PATH_CAIXAS = "/INTEGRACAO/V1/CAIXAS"
PATH_APRESENTADO = "/INTEGRACAO/V1/CAIXAS_APRESENTADO"


def _dec(v: Any) -> Decimal:
    return Decimal(str(v or 0))


def para_caixa(r: dict[str, Any]) -> Caixa:
    return Caixa(
        codigo=r["caixaCodigo"],
        empresa_codigo=r["empresaCodigo"],
        data=date.fromisoformat(r["dataMovimento"]),
        turno=r.get("turno") or str(r.get("turnoCodigo")),
        pdv_codigo=r["pdvCodigo"],
        centro_custo=r.get("centroCusto"),
        funcionario_codigo=r["funcionarioCodigo"],
        abertura=ler_data_hora(r["abertura"]),
        fechamento=ler_data_hora(r["fechamento"]) if r.get("fechamento") else None,
        fechado=bool(r.get("fechado")),
        consolidado=bool(r.get("consolidado")),
        bloqueado=bool(r.get("bloqueado")),
    )


def para_modalidades(r: dict[str, Any]) -> tuple[LinhaModalidade, ...]:
    linhas = []
    for prefixo, rotulo in MODALIDADES.items():
        ap, apu, dif = (_dec(r.get(f"{prefixo}{s}")) for s in ("Apresentado", "Apurado", "Diferenca"))
        if ap or apu or dif:
            linhas.append(LinhaModalidade(modalidade=prefixo, rotulo=rotulo, apresentado=ap, apurado=apu, diferenca=dif))
    return tuple(linhas)


async def buscar_caixas(unidade: Unidade, inicio: date, fim: date, *, client: httpx.AsyncClient | None = None) -> list[Caixa]:
    params = {"dataInicial": inicio.isoformat(), "dataFinal": fim.isoformat(), "empresaCodigo": unidade.empresa_codigo}
    linhas = await paginar(unidade, PATH_CAIXAS, params, client=client)
    return [para_caixa(r) for r in linhas if r.get("empresaCodigo") == unidade.empresa_codigo]


async def buscar_apresentados(
    unidade: Unidade, inicio: date, fim: date, caixas: set[int], *, client: httpx.AsyncClient | None = None
) -> dict[int, tuple[LinhaModalidade, ...]]:
    params = {"dataInicial": inicio.isoformat(), "dataFinal": fim.isoformat()}
    linhas = await paginar(unidade, PATH_APRESENTADO, params, client=client)
    return {r["caixaCodigo"]: para_modalidades(r) for r in linhas if r.get("caixaCodigo") in caixas}
