"""Fontes reais (somente leitura) para o Financeiro IA.

Liga CorporateCashFlowService, CorporateFinanceCenterService e leitores
do cash_reconciliation (pagbank_edi, extrato_reader, webposto_cartoes,
webposto_detalhes). Não importa adaptadores de escrita.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from src.services.network_financial_overview_service import FinancialOverviewFilters

logger = logging.getLogger(__name__)

FonteResult = list[dict[str, Any]] | dict[str, Any]


def _indisponivel(motivo: str) -> dict[str, str]:
    return {"status": "fonte_indisponivel", "motivo": motivo}


async def carregar_movimentos_cash_flow(
    cash_flow_service: Any,
    *,
    empresa_codigo: int,
    ref: date,
    horizonte_dias: int,
) -> FonteResult:
    """Converte série diária do CorporateCashFlowService em movimentos do analisador."""
    if cash_flow_service is None:
        return _indisponivel(
            "CorporateCashFlowService não injetado; informe movimentos=... para projeção offline"
        )
    fim = ref + timedelta(days=horizonte_dias)
    filters = FinancialOverviewFilters(
        data_inicial=ref.isoformat(),
        data_final=fim.isoformat(),
        empresa_codigo=empresa_codigo,
    )
    try:
        resp = await cash_flow_service.build(filters, empresa_codigo)
    except Exception as exc:  # noqa: BLE001
        return _indisponivel(
            f"CorporateCashFlowService falhou: {type(exc).__name__}: {exc}"
        )
    if resp is None or not getattr(resp, "success", False):
        erro = getattr(resp, "error", None) if resp is not None else None
        return _indisponivel(
            f"CorporateCashFlowService sem sucesso"
            + (f": {erro}" if erro else "")
        )
    data = getattr(resp, "data", None) or {}
    if not isinstance(data, dict):
        return _indisponivel("CorporateCashFlowService retornou payload inválido")
    daily = data.get("daily")
    if daily is None:
        return _indisponivel("CorporateCashFlowService sem série daily")
    if not isinstance(daily, list):
        return _indisponivel("CorporateCashFlowService.daily não é lista")
    movimentos: list[dict[str, Any]] = []
    for row in daily:
        if not isinstance(row, dict):
            continue
        periodo = row.get("periodo")
        if not periodo:
            continue
        movimentos.append(
            {
                "dia": str(periodo)[:10],
                "entradas": row.get("entradasPrevistas") or 0,
                "saidas": row.get("saidasPrevistas") or 0,
            }
        )
    return movimentos


async def carregar_titulos_finance_center(
    finance_center_service: Any,
    *,
    empresa_codigo: int,
    ref: date,
    janela_dias: int = 90,
) -> FonteResult:
    """Títulos a receber em aberto via CorporateFinanceCenterService (_is_recebido)."""
    if finance_center_service is None:
        return _indisponivel(
            "CorporateFinanceCenterService não injetado; informe titulos=... para análise offline"
        )
    inicio = ref - timedelta(days=janela_dias)
    filters = FinancialOverviewFilters(
        data_inicial=inicio.isoformat(),
        data_final=ref.isoformat(),
        empresa_codigo=empresa_codigo,
    )
    fetch = getattr(finance_center_service, "_fetch_titulo_receber_all", None)
    classify = getattr(finance_center_service, "_classify_receivables", None)
    if callable(fetch) and callable(classify):
        try:
            rows, _ms = await fetch(filters)
            buckets = classify(rows, ref.isoformat())
        except Exception as exc:  # noqa: BLE001
            return _indisponivel(
                f"CorporateFinanceCenterService falhou: {type(exc).__name__}: {exc}"
            )
        if not isinstance(buckets, dict):
            return _indisponivel("classificação de recebíveis inválida")
        pendentes = buckets.get("pendente") or []
        if not isinstance(pendentes, list):
            return _indisponivel("bucket pendente de recebíveis inválido")
        saida: list[dict[str, Any]] = []
        for row in pendentes:
            if not isinstance(row, dict):
                continue
            saida.append(
                {
                    "tituloCodigo": row.get("tituloCodigo") or row.get("codigo") or "",
                    "nomeCliente": row.get("cliente") or row.get("nomeCliente") or "",
                    "valor": row.get("valor") or 0,
                    "dataVencimento": row.get("vencimento") or row.get("dataVencimento") or "",
                    "situacao": row.get("situacao") or "ABERTO",
                    "pendente": row.get("pendente", True),
                    "tipoCliente": row.get("tipoCliente") or row.get("tipo_cliente") or "",
                    "empresaCodigo": row.get("empresaCodigo") or empresa_codigo,
                }
            )
        return saida

    # Fallback: API pública get_receivables
    try:
        resp = await finance_center_service.get_receivables(
            filters, empresa_codigo, page=1, limit=500
        )
    except Exception as exc:  # noqa: BLE001
        return _indisponivel(
            f"CorporateFinanceCenterService falhou: {type(exc).__name__}: {exc}"
        )
    if resp is None or not getattr(resp, "success", False):
        erro = getattr(resp, "error", None) if resp is not None else None
        return _indisponivel(
            f"CorporateFinanceCenterService.get_receivables sem sucesso"
            + (f": {erro}" if erro else "")
        )
    data = getattr(resp, "data", None) or {}
    if not isinstance(data, dict):
        return _indisponivel("get_receivables retornou payload inválido")
    rows = data.get("data")
    if rows is None:
        return []
    if not isinstance(rows, list):
        return _indisponivel("get_receivables.data não é lista")
    saida = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("pendente") is False:
            continue
        situacao = str(row.get("situacao") or "").upper()
        if situacao in {"RECEBIDO", "PAGO", "BAIXADO", "QUITADO"}:
            continue
        saida.append(
            {
                "tituloCodigo": row.get("tituloCodigo") or row.get("codigo") or "",
                "nomeCliente": row.get("cliente") or row.get("nomeCliente") or "",
                "valor": row.get("valor") or 0,
                "dataVencimento": row.get("vencimento") or row.get("dataVencimento") or "",
                "situacao": row.get("situacao") or "ABERTO",
                "pendente": row.get("pendente"),
                "tipoCliente": row.get("tipoCliente") or row.get("tipo_cliente") or "",
                "empresaCodigo": row.get("empresaCodigo") or empresa_codigo,
            }
        )
    return saida


async def carregar_fontes_cartao_cash_reconciliation(
    *,
    empresa_codigo: int,
    dia: date,
    caminho_ofx: str | Path | None = None,
) -> FonteResult:
    """Leitura PagBank EDI + (opcional) OFX via extrato_reader; vendas via webposto_cartoes.

    Não chama adaptadores de escrita. Sem credencial PagBank → motivo exato.
    """
    from src.modules.cash_reconciliation.adapters import pagbank_edi
    from src.modules.cash_reconciliation.adapters.extrato_reader import ler_arquivo

    # Garante que extrato_reader está importável (leitura); uso só com caminho
    _ = ler_arquivo

    recebimentos: list[dict[str, Any]] = []
    try:
        txs = await pagbank_edi.buscar_transacoes(empresa_codigo, dia)
    except pagbank_edi.PagBankCredencialInvalida as exc:
        return _indisponivel(str(exc))
    except pagbank_edi.PagBankErro as exc:
        return _indisponivel(f"PagBank EDI: {exc}")
    except Exception as exc:  # noqa: BLE001
        return _indisponivel(f"PagBank EDI falhou: {type(exc).__name__}: {exc}")

    for t in txs:
        momento = getattr(t, "momento", None)
        dia_iso = dia.isoformat()
        if momento is not None:
            try:
                dia_iso = momento.date().isoformat() if hasattr(momento, "date") else str(momento)[:10]
            except Exception:  # noqa: BLE001
                dia_iso = dia.isoformat()
        recebimentos.append(
            {
                "dia": dia_iso,
                "bandeira": getattr(t, "bandeira", None) or "NÃO INFORMADA",
                "valor": getattr(t, "valor", 0),
                "adquirente": getattr(t, "adquirente", None) or "PagBank",
            }
        )

    ofx_path = caminho_ofx or os.getenv("FINANCEIRO_AI_EXTRATO_OFX") or ""
    if ofx_path:
        try:
            extrato = ler_arquivo(Path(ofx_path))
            for lan in extrato.lancamentos:
                if not lan.eh_credito:
                    continue
                if lan.data != dia:
                    continue
                if "cart" not in (lan.categoria or "").casefold() and "cart" not in (
                    lan.descricao or ""
                ).casefold():
                    continue
                recebimentos.append(
                    {
                        "dia": lan.data.isoformat(),
                        "bandeira": "EXTRATO",
                        "valor": abs(lan.valor),
                        "adquirente": extrato.banco or "EXTRATO_OFX",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            return _indisponivel(
                f"extrato_reader falhou: {type(exc).__name__}: {exc}"
            )

    vendas: list[dict[str, Any]] = []
    try:
        from src.modules.cash_reconciliation.config import carregar_unidades
        from src.modules.cash_reconciliation.adapters.webposto_cartoes import (
            buscar_cartoes,
        )

        unidades = carregar_unidades()
        unidade = unidades.get(empresa_codigo)
        if unidade is None:
            return _indisponivel(
                f"unidade {empresa_codigo} ausente em units.json do cash_reconciliation"
            )
        cartoes = await buscar_cartoes(unidade, dia, dia)
        for c in cartoes:
            momento = getattr(c, "momento", None)
            dia_iso = dia.isoformat()
            if momento is not None and hasattr(momento, "date"):
                try:
                    dia_iso = momento.date().isoformat()
                except Exception:  # noqa: BLE001
                    pass
            vendas.append(
                {
                    "dia": dia_iso,
                    "bandeira": getattr(c, "administradora", None) or "NÃO INFORMADA",
                    "valor": getattr(c, "valor", 0),
                }
            )
    except Exception as exc:  # noqa: BLE001
        return _indisponivel(
            f"leitura webPosto CARTOES falhou: {type(exc).__name__}: {exc}"
        )

    return {"vendas_cartao": vendas, "recebimentos": recebimentos}


async def carregar_despesas_cash_reconciliation(
    *,
    empresa_codigo: int,
    inicio: date,
    fim: date,
) -> FonteResult:
    """Despesas de caixa via webposto_detalhes.buscar_despesas (somente leitura)."""
    try:
        from src.modules.cash_reconciliation.config import carregar_unidades
        from src.modules.cash_reconciliation.adapters.webposto_caixas import (
            buscar_caixas,
        )
        from src.modules.cash_reconciliation.adapters.webposto_detalhes import (
            buscar_despesas,
        )
    except Exception as exc:  # noqa: BLE001
        return _indisponivel(
            f"adaptadores de leitura de despesas indisponíveis: {type(exc).__name__}: {exc}"
        )

    try:
        unidades = carregar_unidades()
        unidade = unidades.get(empresa_codigo)
        if unidade is None:
            return _indisponivel(
                f"unidade {empresa_codigo} ausente em units.json do cash_reconciliation"
            )
        caixas = await buscar_caixas(unidade, inicio, fim)
        if not caixas:
            return []
        codigos = {c.codigo for c in caixas}
        caixa_meta = {
            c.codigo: {
                "centro_custo": c.centro_custo,
                "data": c.data.isoformat() if c.data else None,
            }
            for c in caixas
        }
        despesas = await buscar_despesas(unidade, codigos)
    except Exception as exc:  # noqa: BLE001
        return _indisponivel(
            f"falha ao ler despesas de caixa: {type(exc).__name__}: {exc}"
        )

    saida: list[dict[str, Any]] = []
    for d in despesas:
        meta = caixa_meta.get(d.caixa_codigo) or {}
        saida.append(
            {
                "despesaCodigo": str(d.codigo),
                "posto": str(empresa_codigo),
                "nome_caixa": f"CAIXA_{d.caixa_codigo}",
                "setor": str(meta.get("centro_custo") or d.centro_custo or ""),
                "centro_custo": meta.get("centro_custo") or d.centro_custo,
                "valor": d.valor,
                "data": meta.get("data") or "",
                "planoContaCodigo": d.plano_conta_codigo,
                "planoConta": d.plano_conta_nome,
                # comprovante não vem deste endpoint — não inventa tem_comprovante
            }
        )
    return saida


def montar_servicos_corporativos() -> tuple[Any, Any]:
    """Instancia Finance Center + Cash Flow com o cliente gateway (somente leitura)."""
    from src.gateway.webposto_client import WebPostoClient
    from src.services.corporate_cash_flow_service import CorporateCashFlowService
    from src.services.corporate_finance_center_service import CorporateFinanceCenterService
    from src.services.network_financial_overview_service import (
        NetworkFinancialOverviewService,
    )

    client = WebPostoClient()
    overview = NetworkFinancialOverviewService(client)
    finance_center = CorporateFinanceCenterService(overview)
    cash_flow = CorporateCashFlowService(finance_center)
    return cash_flow, finance_center


__all__ = [
    "carregar_movimentos_cash_flow",
    "carregar_titulos_finance_center",
    "carregar_fontes_cartao_cash_reconciliation",
    "carregar_despesas_cash_reconciliation",
    "montar_servicos_corporativos",
]
