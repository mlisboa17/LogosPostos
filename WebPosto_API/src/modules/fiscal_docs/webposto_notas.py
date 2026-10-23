"""NF-e recebidas lidas do webPosto (somente GET).

O webPosto consulta a SEFAZ e manifesta por conta própria; aqui só lemos a lista
(`NOTAS_MANIFESTACAO`), o XML completo por chave e os dados de frete das notas lançadas.
A CHAVE nunca aparece em log nem em mensagem de erro.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from src.modules.webposto_integration.http import BASE_URL_PADRAO, UnidadeIntegrada, WebPostoErro, paginar
from src.shared.segredos import obter_segredo

logger = logging.getLogger(__name__)
ROTA_LISTA = "/INTEGRACAO/V1/NOTAS_MANIFESTACAO"
ROTA_XML = "/INTEGRACAO/V1/NOTAS_ENTRADA/XML/{chave}"
ROTA_ENTRADAS = "/INTEGRACAO/V1/NOTAS_ENTRADA"


class NotaListada(BaseModel):
    model_config = ConfigDict(frozen=True)
    chave: str
    emitente_cnpj: str
    emitente_nome: str
    emissao: date
    valor: Decimal
    tipo_produto: str | None = None
    recebido: bool | None = None


class EntradaWebposto(BaseModel):
    model_config = ConfigDict(frozen=True)
    chave: str
    tipo_frete: str | None = None
    valor_frete: Decimal | None = None
    placa: str | None = None
    placa_reboque: str | None = None
    cte_numero: str | None = None
    cte_emissao: date | None = None


def _texto(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def _dec(v: Any) -> Decimal | None:
    return None if v is None or v == "" else Decimal(str(v))


def _data(v: Any) -> date | None:
    s = _texto(v)
    return date.fromisoformat(s[:10]) if s else None


def _periodo(unidade: UnidadeIntegrada, inicio: date, fim: date) -> dict[str, Any]:
    return {"dataInicial": inicio.isoformat(), "dataFinal": fim.isoformat(),
            "empresaCodigo": unidade.empresa_codigo}


async def listar_notas(unidade: UnidadeIntegrada, inicio: date, fim: date, *,
                       client: httpx.AsyncClient | None = None) -> list[NotaListada]:
    linhas = await paginar(unidade, ROTA_LISTA, _periodo(unidade, inicio, fim), client=client)
    notas = []
    for r in linhas:
        if not _texto(r.get("chaveDocumento")):
            continue
        try:  # uma linha estranha não derruba a lista
            notas.append(NotaListada(
                chave=_texto(r.get("chaveDocumento")),
                emitente_cnpj=_texto(r.get("cnpjFornecedor")) or "",
                emitente_nome=_texto(r.get("razaoSocialFornecedor")) or "",
                emissao=_data(r.get("dataEmissao")),
                valor=_dec(r.get("valor")) or Decimal("0"),
                tipo_produto=_texto(r.get("tipoProduto")),
                recebido=r.get("recebido"),
            ))
        except (ValidationError, ValueError, TypeError, InvalidOperation):
            logger.warning("Linha de NOTAS_MANIFESTACAO ignorada (formato inesperado)")
    return notas


async def baixar_xml(unidade: UnidadeIntegrada, chave: str, *,
                     client: httpx.AsyncClient | None = None) -> bytes | None:
    """XML completo da NF-e; `None` se o webPosto ainda não tem o XML (404/vazio)."""
    segredo = obter_segredo(unidade.chave_env)
    if not segredo:
        raise WebPostoErro(f"variavel {unidade.chave_env} ausente")
    base = os.getenv("WEBPOSTO_BASE_URL") or BASE_URL_PADRAO
    proprio = client is None
    http = client or httpx.AsyncClient(base_url=base, timeout=60.0)
    try:
        try:
            resp = await http.get(ROTA_XML.format(chave=chave), params={"CHAVE": segredo})
        except httpx.HTTPError as exc:
            raise WebPostoErro(type(exc).__name__) from None
    finally:
        if proprio:
            await http.aclose()
    if resp.status_code in (204, 404):
        return None
    if resp.status_code != 200:
        raise WebPostoErro(f"HTTP {resp.status_code}: {resp.text[:120].replace(segredo, '***')}",
                           status_http=resp.status_code)
    corpo = resp.content.strip()
    return corpo if corpo.startswith(b"<") else None


async def listar_entradas(unidade: UnidadeIntegrada, inicio: date, fim: date, *,
                          client: httpx.AsyncClient | None = None) -> dict[str, EntradaWebposto]:
    linhas = await paginar(unidade, ROTA_ENTRADAS, _periodo(unidade, inicio, fim), client=client)
    saida: dict[str, EntradaWebposto] = {}
    for r in linhas:
        chave = _texto(r.get("chaveDocumento"))
        if not chave:
            continue
        saida[chave] = EntradaWebposto(
            chave=chave,
            tipo_frete=_texto(r.get("tipoFrete")),
            valor_frete=_dec(r.get("valorFrete")),
            placa=_texto(r.get("placaVeiculo")),
            placa_reboque=_texto(r.get("placaReboque")),
            cte_numero=_texto(r.get("cteNumero")),
            cte_emissao=_data(r.get("cteDataEmissao")),
        )
    return saida
