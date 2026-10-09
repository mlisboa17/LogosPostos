"""Acesso paginado (cursor ultimoCodigo) as rotas V1 do webPosto.

Chave por unidade lida da variavel de ambiente indicada em Unidade.chave_env.
A CHAVE nunca e logada nem propagada em mensagens de erro (ARCH01).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Protocol

import httpx

class UnidadeIntegrada(Protocol):
    @property
    def empresa_codigo(self) -> int: ...

    @property
    def chave_env(self) -> str: ...

# A CHAVE vai na query string: o httpx registraria a URL completa em INFO. Vale para API, robo e scripts.
for _nome in ("httpx", "httpcore"):
    logging.getLogger(_nome).setLevel(logging.WARNING)

BASE_URL_PADRAO = "https://web.qualityautomacao.com.br"


class WebPostoErro(RuntimeError):
    pass


async def paginar(
    unidade: UnidadeIntegrada,
    path: str,
    params: dict[str, Any],
    *,
    base_url: str | None = None,
    limite: int = 1000,  # validado no webPosto em 2026-10-07; metade das chamadas de 500
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    chave = (os.getenv(unidade.chave_env) or "").strip()
    if not chave:
        raise WebPostoErro(f"variavel {unidade.chave_env} ausente")
    base = base_url or os.getenv("WEBPOSTO_BASE_URL") or BASE_URL_PADRAO
    proprio = client is None
    http = client or httpx.AsyncClient(base_url=base, timeout=60.0)
    linhas: list[dict[str, Any]] = []
    cursor = None
    try:
        while True:
            q = {"CHAVE": chave, **params, "limite": limite, **({"ultimoCodigo": cursor} if cursor else {})}
            try:
                resp = await http.get(path, params=q)
            except httpx.HTTPError as exc:
                raise WebPostoErro(type(exc).__name__) from None
            if resp.status_code != 200:
                raise WebPostoErro(f"HTTP {resp.status_code}: {resp.text[:120].replace(chave, '***')}")
            payload = resp.json()
            lote = payload.get("resultados") or []
            linhas += lote
            novo = payload.get("ultimoCodigo")
            if not lote or not novo or novo == cursor:
                return linhas
            cursor = novo
    finally:
        if proprio:
            await http.aclose()
