"""Acesso paginado (cursor ultimoCodigo) as rotas V1 do webPosto.

Chave por unidade lida da variavel de ambiente indicada em Unidade.chave_env.
A CHAVE nunca e logada nem propagada em mensagens de erro (ARCH01).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Protocol

import httpx

from src.shared.segredos import obter_segredo

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
    def __init__(self, mensagem: str, *, status_http: int | None = None):
        super().__init__(mensagem)
        self.status_http = status_http


async def paginar(
    unidade: UnidadeIntegrada,
    path: str,
    params: dict[str, Any],
    *,
    base_url: str | None = None,
    limite: int = 1000,  # validado no webPosto em 2026-10-07; metade das chamadas de 500
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    chave = obter_segredo(unidade.chave_env)
    if not chave:
        raise WebPostoErro(f"variavel {unidade.chave_env} ausente")
    base = base_url or os.getenv("WEBPOSTO_BASE_URL") or BASE_URL_PADRAO
    proprio = client is None
    http = client or httpx.AsyncClient(base_url=base, timeout=60.0)
    linhas: list[dict[str, Any]] = []
    cursor = None
    cursores = set()
    try:
        while True:
            q = {"CHAVE": chave, **params, "limite": limite, **({"ultimoCodigo": cursor} if cursor else {})}
            try:
                resp = await http.get(path, params=q)
            except httpx.HTTPError as exc:
                raise WebPostoErro(type(exc).__name__) from None
            if resp.status_code != 200:
                raise WebPostoErro(f"HTTP {resp.status_code}: {resp.text[:120].replace(chave, '***')}",
                                  status_http=resp.status_code)
            payload = resp.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("resultados"), list):
                raise WebPostoErro("Resposta paginada inválida: resultados ausentes ou inválidos.")
            lote = payload["resultados"]
            if any(not isinstance(item, dict) for item in lote):
                raise WebPostoErro("Resposta paginada inválida: registro sem estrutura.")
            linhas += lote
            novo = payload.get("ultimoCodigo")
            if not lote or not novo:
                return linhas
            if not isinstance(novo, (str, int)) or isinstance(novo, bool) or novo in cursores:
                raise WebPostoErro("Resposta paginada sem avanço de cursor.")
            cursores.add(novo)
            cursor = novo
    finally:
        if proprio:
            await http.aclose()
