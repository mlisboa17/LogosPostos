"""Adapter PagBank EDI v3.00 — movimento transacional do dia.

Portado de services/integrations/pagbank_edi_client.py (Codex, branch resgate/conciliacao-4-vias),
com duas correcoes validadas contra a resposta real (Doze 74014, 05/10/2026):
  - data/hora vem em data_inicial_transacao + hora_inicial_transacao (o cliente original perdia a hora);
  - paginacao vem em pagination.totalPages (o original so lia a 1a pagina).
Credenciais por unidade: PAGBANK_USER_<empresa> e PAGBANK_TOKEN_<empresa> (nunca logadas).
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from src.shared.segredos import obter_segredo

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


def para_transacao(r: dict[str, Any]) -> TransacaoAdquirente:
    status = str(r.get("status_pagamento", "")).strip().upper()
    evento = str(r.get("tipo_evento", "1")).strip()
    situacao = None
    if evento != "1" or status not in STATUS_APROVADO:
        situacao = f"tipo_evento={evento};status_pagamento={status}"
    dia = r.get("data_inicial_transacao") or r.get("data_venda_ajuste")
    hora = r.get("hora_inicial_transacao") or r.get("hora_venda_ajuste") or "00:00:00"
    valor = Decimal(str(r.get("valor_total_transacao") or r.get("valor_original_transacao") or 0))
    return TransacaoAdquirente(
        adquirente="PAGBANK",
        identificador=_texto(r.get("tid"))
        or _texto(r.get("movimento_api_codigo"))
        or f"{dia}T{hora}:{valor}",
        nsu=_texto(r.get("nsu")),
        autorizacao=_texto(r.get("codigo_autorizacao")),
        valor=valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        momento=ler_data_hora(f"{dia}T{hora}"),
        bandeira=_texto(r.get("instituicao_financeira")),
        terminal=_texto(r.get("numero_serie_leitor")),
        situacao=situacao,
        tipo_evento=evento,
        status_pagamento=status,
    )


async def buscar_transacoes(
    empresa_codigo: int, dia: date, *, client: httpx.AsyncClient | None = None, page_size: int = 1000
) -> list[TransacaoAdquirente]:
    user = obter_segredo(f"PAGBANK_USER_{empresa_codigo}")
    token = obter_segredo(f"PAGBANK_TOKEN_{empresa_codigo}")
    if not user or not token:
        raise PagBankCredencialInvalida(f"credenciais PagBank ausentes para {empresa_codigo}")
    proprio = client is None
    http = client or httpx.AsyncClient(base_url=BASE_URL, timeout=60.0)
    vistos: set[str] = set()
    saida: list[TransacaoAdquirente] = []
    pagina = 1
    total_paginas: int | None = None
    try:
        while True:
            try:
                resp = await http.get(f"/transactional/{dia.isoformat()}",
                                      params={"pageNumber": pagina, "pageSize": page_size},
                                      auth=(user, token), headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                raise PagBankErro(type(exc).__name__) from None
            if resp.status_code == 404:
                if pagina > 1:
                    raise PagBankErro("Resposta EDI incompleta: página declarada indisponível.")
                return saida
            if resp.status_code in (401, 403):
                raise PagBankCredencialInvalida("credencial inválida")
            if resp.status_code != 200:
                raise PagBankErro(f"HTTP {resp.status_code}")
            payload = resp.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("detalhes"), list):
                raise PagBankErro("Resposta EDI inválida: detalhes ausentes ou inválidos.")
            paginacao = payload.get("pagination")
            total = paginacao.get("totalPages") if isinstance(paginacao, dict) else None
            if total is None and not payload["detalhes"] and pagina == 1:
                return []
            if isinstance(total, str) and total.isdecimal():
                total = int(total)
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise PagBankErro("Resposta EDI inválida: paginação ausente ou inválida.")
            if total_paginas is not None and total != total_paginas:
                raise PagBankErro("Resposta EDI inconsistente: quantidade de páginas alterada.")
            total_paginas = total
            if (not payload["detalhes"] and pagina < total) or (payload["detalhes"] and total < pagina):
                raise PagBankErro("Resposta EDI incompleta: cobertura de páginas inválida.")
            for r in payload["detalhes"]:
                if not isinstance(r, dict):
                    raise PagBankErro("Resposta EDI inválida: registro sem estrutura.")
                t = para_transacao(r)
                identidade = f"{t.identificador}|{t.tipo_evento}|{t.status_pagamento}"
                if t and identidade not in vistos:
                    vistos.add(identidade)
                    saida.append(t)
            if pagina >= total or not payload.get("detalhes"):
                return saida
            pagina += 1
    finally:
        if proprio:
            await http.aclose()
