"""Adapter PagBank EDI v3.00 — movimento transacional do dia.

Portado de services/integrations/pagbank_edi_client.py (Codex, branch resgate/conciliacao-4-vias),
com duas correcoes validadas contra a resposta real (Doze 74014, 05/10/2026):
  - data/hora vem em data_inicial_transacao + hora_inicial_transacao (o cliente original perdia a hora);
  - paginacao vem em pagination.totalPages (o original so lia a 1a pagina).
Credenciais por unidade: PAGBANK_USER_<empresa> e PAGBANK_TOKEN_<empresa> (nunca logadas).
"""
from __future__ import annotations

import os
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from ..domain.cartoes import TransacaoAdquirente
from ..domain.tempo import ler_data_hora
from .webposto_http import WebPostoErro

BASE_URL = "https://edi.api.pagbank.com.br/movement/v3.00"
FONTE = f"PagBank EDI {BASE_URL}/transactional"
STATUS_APROVADO = {"1", "2", "00", "APROVADA", "APROVADO", "PAID", "APPROVED", "PAGO", "CONFIRMADO"}


class PagBankErro(WebPostoErro):
    pass


class PagBankCredencialInvalida(PagBankErro):
    pass


def _texto(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def para_transacao(r: dict[str, Any]) -> TransacaoAdquirente | None:
    if str(r.get("status_pagamento", "")).strip().upper() not in STATUS_APROVADO:
        return None
    if str(r.get("tipo_evento", "1")).strip() != "1":  # 1 = venda; demais sao ajustes/cancelamentos
        return None
    dia = r.get("data_inicial_transacao") or r.get("data_venda_ajuste")
    hora = r.get("hora_inicial_transacao") or r.get("hora_venda_ajuste") or "00:00:00"
    valor = Decimal(str(r.get("valor_total_transacao") or r.get("valor_original_transacao") or 0))
    return TransacaoAdquirente(
        adquirente="PAGBANK",
        identificador=_texto(r.get("tid")) or _texto(r.get("movimento_api_codigo")) or f"{dia}T{hora}:{valor}",
        nsu=_texto(r.get("nsu")),
        autorizacao=_texto(r.get("codigo_autorizacao")),
        valor=valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        momento=ler_data_hora(f"{dia}T{hora}"),
        bandeira=_texto(r.get("instituicao_financeira")),
        terminal=_texto(r.get("numero_serie_leitor")),
    )


async def buscar_transacoes(
    empresa_codigo: int, dia: date, *, client: httpx.AsyncClient | None = None, page_size: int = 1000
) -> list[TransacaoAdquirente]:
    user = (os.getenv(f"PAGBANK_USER_{empresa_codigo}") or "").strip()
    token = (os.getenv(f"PAGBANK_TOKEN_{empresa_codigo}") or "").strip()
    if not user or not token:
        raise PagBankCredencialInvalida(f"credenciais PagBank ausentes para {empresa_codigo}")
    proprio = client is None
    http = client or httpx.AsyncClient(base_url=BASE_URL, timeout=60.0)
    vistos: set[str] = set()
    saida: list[TransacaoAdquirente] = []
    pagina = 1
    try:
        while True:
            try:
                resp = await http.get(f"/transactional/{dia.isoformat()}",
                                      params={"pageNumber": pagina, "pageSize": page_size},
                                      auth=(user, token), headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                raise PagBankErro(type(exc).__name__) from None
            if resp.status_code == 404:
                return saida
            if resp.status_code in (401, 403):
                raise PagBankCredencialInvalida("credencial inválida")
            if resp.status_code != 200:
                raise PagBankErro(f"HTTP {resp.status_code}")
            payload = resp.json()
            for r in payload.get("detalhes") or []:
                t = para_transacao(r)
                if t and t.identificador not in vistos:
                    vistos.add(t.identificador)
                    saida.append(t)
            total = int((payload.get("pagination") or {}).get("totalPages") or 1)
            if pagina >= total or not payload.get("detalhes"):
                return saida
            pagina += 1
    finally:
        if proprio:
            await http.aclose()
