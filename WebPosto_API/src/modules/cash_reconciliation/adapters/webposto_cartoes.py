"""Adapters webPosto V1 para a conciliacao de recebimentos eletronicos.

CARTOES (recebimentos lancados) · ABASTECIMENTOS (frentista via identfid) ·
VENDAS/ITENS + VENDAS_FORMA_PAGAMENTO (abastecimento -> venda -> forma de pagamento).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from ..domain.cartoes import Abastecimento, CartaoErp
from ..domain.models import Unidade
from ..domain.tempo import ler_data_hora
from .webposto_http import paginar

TIPO_DINHEIRO = "D"


def _dec(v: Any) -> Decimal:
    return Decimal(str(v or 0))


def _texto(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def para_cartao(r: dict[str, Any]) -> CartaoErp:
    return CartaoErp(
        codigo=r["cartaoCodigo"],
        empresa_codigo=r["empresaCodigo"],
        venda_codigo=r.get("vendaCodigo"),
        valor=_dec(r.get("valor")),
        momento=ler_data_hora(f"{r['dataMovimento']}T{r.get('horaMovimento') or '00:00:00'}"),
        administradora=str(r.get("adiministradoraDescricao") or ""),  # sic: grafia da API
        nsu=_texto(r.get("nsu")),
        nsu_tef=_texto(r.get("nsuTef")),
        autorizacao=_texto(r.get("autorizacao")),
    )


def para_abastecimento(r: dict[str, Any]) -> Abastecimento:
    momento = ler_data_hora(r["dataHoraAbastecimento"])
    return Abastecimento(
        codigo=r["abastecimentoCodigo"],
        empresa_codigo=r["empresaCodigo"],
        momento=momento,
        bico=r.get("codigoBico"),
        valor=_dec(r.get("valorTotal")),
        frentista=r.get("codigoFrentista"),
        venda_item_codigo=r.get("vendaItemCodigo"),
    )


def _periodo(unidade: Unidade, inicio: date, fim: date) -> dict[str, Any]:
    return {"dataInicial": inicio.isoformat(), "dataFinal": fim.isoformat(), "empresaCodigo": unidade.empresa_codigo}


async def buscar_cartoes(unidade: Unidade, inicio: date, fim: date, *, client: httpx.AsyncClient | None = None) -> list[CartaoErp]:
    linhas = await paginar(unidade, "/INTEGRACAO/V1/CARTOES", _periodo(unidade, inicio, fim), client=client)
    return [para_cartao(r) for r in linhas if r.get("empresaCodigo") == unidade.empresa_codigo]


async def buscar_abastecimentos(unidade: Unidade, inicio: date, fim: date, *, client: httpx.AsyncClient | None = None) -> list[Abastecimento]:
    linhas = await paginar(unidade, "/INTEGRACAO/V1/ABASTECIMENTOS", _periodo(unidade, inicio, fim), client=client)
    return [para_abastecimento(r) for r in linhas
            if r.get("empresaCodigo") == unidade.empresa_codigo and not r.get("afericao") and r.get("dataHoraAbastecimento")]


TIPO_PIX = "B"


def _cancelada(valor: Any) -> bool:
    if valor is None:
        return False
    marcador = str(valor).strip().upper()
    if marcador in {"N", "FALSE", "0"}:
        return False
    if marcador in {"S", "TRUE", "1"}:
        return True
    raise ValueError("Marcador de cancelamento de venda inválido.")


async def buscar_contexto_vendas(
    unidade: Unidade, inicio: date, fim: date, *, client: httpx.AsyncClient | None = None
) -> tuple[set[int], list[CartaoErp]]:
    """(vendaItemCodigo pagos em dinheiro, PIX lancados como forma de pagamento da venda).

    PIX nao entra em V1/CARTOES: vem de VENDAS_FORMA_PAGAMENTO (tipo B) com a hora de V1/VENDAS.
    """
    p = _periodo(unidade, inicio, fim)
    itens = await paginar(unidade, "/INTEGRACAO/V1/VENDAS/ITENS", p, client=client)
    formas = await paginar(unidade, "/INTEGRACAO/V1/VENDAS_FORMA_PAGAMENTO", p, client=client)
    vendas = await paginar(unidade, "/INTEGRACAO/V1/VENDAS", p, client=client)
    hora = {
        v["vendaCodigo"]: v.get("dataHora")
        for v in vendas
        if v.get("empresaCodigo") == unidade.empresa_codigo and not _cancelada(v.get("cancelada"))
    }
    vendas_dinheiro = {
        f["vendaCodigo"] for f in formas
        if f.get("empresaCodigo") == unidade.empresa_codigo
        and f.get("tipoFormaPagamento") == TIPO_DINHEIRO and f["vendaCodigo"] in hora
    }
    itens_dinheiro = {
        i["vendaItemCodigo"] for i in itens
        if i.get("empresaCodigo") == unidade.empresa_codigo and i.get("vendaCodigo") in vendas_dinheiro
    }
    pix = [
        CartaoErp(
            codigo=f.get("codigo") or f["vendaCodigo"],
            empresa_codigo=f["empresaCodigo"],
            venda_codigo=f["vendaCodigo"],
            valor=_dec(f.get("valorPagamento")),
            momento=ler_data_hora(hora[f["vendaCodigo"]]),
            administradora=f"PIX (venda) {f.get('nomeFormaPagamento') or ''}".strip(),
            nsu=None, nsu_tef=None, autorizacao=None,
        )
        for f in formas
        if f.get("tipoFormaPagamento") == TIPO_PIX and hora.get(f["vendaCodigo"]) and f.get("empresaCodigo") == unidade.empresa_codigo
    ]
    return itens_dinheiro, pix
