"""Adapters somente leitura para vales e despesas associados ao fechamento."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from ..domain.fechamento import MovimentoDespesa, ValeFuncionario
from ..domain.models import Unidade
from .webposto_http import WebPostoErro, paginar

PATH_VALES = "/INTEGRACAO/V1/VALES_FUNCIONARIO"
PATH_MOVIMENTOS = "/INTEGRACAO/V1/MOVIMENTACOES_CAIXA"
PATH_PLANOS_CONTA = "/INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL"
logger = logging.getLogger(__name__)


def _texto(valor: Any) -> str | None:
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def _decimal(valor: Any) -> Decimal:
    return Decimal(str(valor or 0))


def _descricao(row: dict[str, Any]) -> str | None:
    for campo in ("descricaoHistorico", "descricaoDocumento", "descricaoCoo"):
        valor = _texto(row.get(campo))
        if valor and valor.casefold() not in {"-", "n/a", "sem descricao", "sem histórico"}:
            return valor
    return None


async def buscar_vales(
    unidade: Unidade,
    inicio: date,
    fim: date,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[ValeFuncionario]:
    linhas = await paginar(
        unidade,
        PATH_VALES,
        {
            "empresaCodigo": unidade.empresa_codigo,
            "dataInicial": inicio.isoformat(),
            "dataFinal": fim.isoformat(),
        },
        client=client,
    )
    return [
        ValeFuncionario(
            codigo=row["codigo"],
            empresa_codigo=row["empresaCodigo"],
            caixa_codigo=row["caixaCodigo"],
            funcionario_codigo=row.get("funcionarioCodigo"),
            origem=str(row.get("origem") or ""),
            valor=_decimal(row.get("valor")),
        )
        for row in linhas
        if row.get("empresaCodigo") == unidade.empresa_codigo
        and inicio.isoformat() <= str(row.get("data") or "") <= fim.isoformat()
    ]


async def buscar_despesas(
    unidade: Unidade,
    caixas: set[int],
    *,
    client: httpx.AsyncClient | None = None,
) -> list[MovimentoDespesa]:
    despesas: list[MovimentoDespesa] = []
    for caixa_codigo in sorted(caixas):
        linhas = await paginar(
            unidade,
            PATH_MOVIMENTOS,
            {"empresaCodigo": unidade.empresa_codigo, "caixaCodigo": caixa_codigo, "tipo": ["D"]},
            client=client,
        )
        despesas.extend(
            MovimentoDespesa(
                codigo=row["caixaMovimentoCodigo"],
                caixa_codigo=caixa_codigo,
                tipo=str(row.get("tipo") or ""),
                valor=_decimal(row.get("valorDinheiro")),
                plano_conta_codigo=_texto(row.get("planoContaCodigo")),
                descricao=_descricao(row),
                centro_custo=row.get("centroCusto"),
            )
            for row in linhas
            if row.get("empresaCodigo") == unidade.empresa_codigo
            and str(row.get("tipo") or "").upper() == "D"
            and _decimal(row.get("valorDinheiro")) > 0
        )
    nomes_planos: dict[str, str | None] = {}
    for codigo in sorted({d.plano_conta_codigo for d in despesas if d.plano_conta_codigo}):
        nomes_planos[codigo] = None
        if not codigo.isdecimal():
            continue
        try:
            linhas = await paginar(
                unidade,
                PATH_PLANOS_CONTA,
                {"planoContaCodigo": int(codigo)},
                client=client,
            )
        except WebPostoErro as exc:
            logger.warning(
                "Plano de contas nao enriquecido unidade=%s tipo=%s",
                unidade.empresa_codigo,
                type(exc).__name__,
            )
            continue
        for linha in linhas:
            if str(linha.get("planoContaCodigo")) == codigo:
                nomes_planos[codigo] = _texto(linha.get("descricao"))
                break
    return [
        despesa.model_copy(
            update={"plano_conta_nome": nomes_planos.get(despesa.plano_conta_codigo)}
        )
        for despesa in despesas
    ]
