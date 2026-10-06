"""Adapter GET /INTEGRACAO/V1/SANGRIAS_CAIXA (contrato validado em producao, ADR-002).

Chave por unidade lida da variavel de ambiente indicada em Unidade.chave_env.
A CHAVE nunca e logada nem propagada em mensagens de erro (ARCH01).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from ..domain.models import Sangria, Unidade

PATH = "/INTEGRACAO/V1/SANGRIAS_CAIXA"
BASE_URL_PADRAO = "https://web.qualityautomacao.com.br"
FONTE = f"webPosto{PATH}"


class WebPostoErro(RuntimeError):
    pass


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
    chave = (os.getenv(unidade.chave_env) or "").strip()
    if not chave:
        raise WebPostoErro(f"variavel {unidade.chave_env} ausente")
    base = base_url or os.getenv("WEBPOSTO_BASE_URL") or BASE_URL_PADRAO
    params: dict[str, Any] = {
        "dataInicial": inicio.isoformat(),
        "dataFinal": fim.isoformat(),
        "empresaCodigo": unidade.empresa_codigo,
        "limite": limite,
    }
    proprio = client is None
    http = client or httpx.AsyncClient(base_url=base, timeout=60.0)
    sangrias: list[Sangria] = []
    cursor = None
    try:
        while True:
            q = {"CHAVE": chave, **params, **({"ultimoCodigo": cursor} if cursor else {})}
            try:
                resp = await http.get(PATH, params=q)
            except httpx.HTTPError as exc:
                raise WebPostoErro(type(exc).__name__) from None
            if resp.status_code != 200:
                raise WebPostoErro(f"HTTP {resp.status_code}: {resp.text[:120].replace(chave, '***')}")
            payload = resp.json()
            lote = payload.get("resultados") or []
            sangrias += [para_sangria(r) for r in lote if r.get("empresaCodigo") == unidade.empresa_codigo]
            novo = payload.get("ultimoCodigo")
            if not lote or not novo or novo == cursor:
                return sangrias
            cursor = novo
    finally:
        if proprio:
            await http.aclose()
