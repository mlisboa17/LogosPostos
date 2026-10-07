"""Financial Health Score — F01.3."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from src.models.response_model import WebPostoResponse
from src.services.corporate_finance_center_service import CorporateFinanceCenterService
from src.services.corporate_cash_flow_service import CorporateCashFlowService
from src.services.financial_intelligence_service import FinancialIntelligenceService
from src.services.multiselect_utils import empresa_snapshot_suffix
from src.services.network_financial_overview_service import FinancialOverviewFilters

LOGGER = logging.getLogger(__name__)


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _q2(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


class FinancialHealthScoreService:
    def __init__(
        self,
        finance_center: CorporateFinanceCenterService,
        cash_flow: CorporateCashFlowService,
        intelligence: FinancialIntelligenceService,
    ) -> None:
        self._fc = finance_center
        self._flow = cash_flow
        self._intel = intelligence

    @staticmethod
    def snapshot_key(data_inicial: str, data_final: str, empresa_codigo: str | int | None) -> str:
        suffix = empresa_snapshot_suffix(empresa_codigo)
        return f"finance:health-score:{data_inicial}:{data_final}:{suffix}"

    def _score_branch(
        self,
        empresa: str,
        expense_total: Decimal,
        outros_pct: float,
        outros_v3_pct: float,
        plano_source_pct: float,
        saldo_acumulado: Decimal,
        rec_vencido: Decimal,
        pay_vencido: Decimal,
        tarifas: Decimal,
        cash_diffs: int,
    ) -> dict[str, Any]:
        components: dict[str, float] = {}
        components["classificacao"] = min(20, (100 - outros_v3_pct) * 0.2)
        components["planoConta"] = min(10, plano_source_pct * 0.1)
        components["fluxoCaixa"] = 20.0 if saldo_acumulado >= 0 else max(0, 20 + float(saldo_acumulado / max(expense_total, Decimal("1")) * 10))
        rec_ratio = float(rec_vencido / max(expense_total, Decimal("1"))) if expense_total else 0
        components["recebiveis"] = max(0, 15 - rec_ratio * 100)
        pay_ratio = float(pay_vencido / max(expense_total, Decimal("1"))) if expense_total else 0
        components["pagaveis"] = max(0, 15 - min(pay_ratio * 30, 15))
        fee_ratio = float(tarifas / max(expense_total, Decimal("1"))) if expense_total else 0
        components["tarifas"] = max(0, 10 - fee_ratio * 200)
        components["caixa"] = max(0, 10 - cash_diffs)
        components["concentracao"] = 10.0
        total_score = _clamp_score(sum(components.values()))
        return {
            "empresaCodigo": empresa,
            "score": total_score,
            "nivel": "saudavel" if total_score >= 70 else "atencao" if total_score >= 50 else "critico",
            "components": {k: round(v, 1) for k, v in components.items()},
            "expenseTotal": _q2(expense_total),
        }

    async def build(
        self,
        filters: FinancialOverviewFilters,
        empresa_codigo_raw: str | int | None,
    ) -> WebPostoResponse:
        intel_resp = await self._intel.build(filters, empresa_codigo_raw)
        if not intel_resp.success:
            return intel_resp
        intel = intel_resp.data or {}
        cls = intel.get("classification") or {}

        flow_resp = await self._flow.build(filters, empresa_codigo_raw)
        flow = flow_resp.data if flow_resp.success else {}
        cards = flow.get("cards") or {}
        saldo = _dec(cards.get("saldoAcumulado"))
        rec_venc = _dec((flow.get("receivablesAging") or {}).get("vencido", {}).get("valor"))
        pay_venc = _dec((flow.get("payablesAging") or {}).get("vencido", {}).get("valor"))
        tarifas = _dec((flow.get("treasury") or {}).get("tarifas", {}).get("valor"))

        caixa_resp = await self._fc.get_cash(filters, empresa_codigo_raw)
        cash_diffs = 0
        if caixa_resp.success and caixa_resp.data:
            cash_diffs = int((caixa_resp.data.get("diferencas") or {}).get("count") or 0)

        por_empresa = cls.get("porCategoriaLogos") or {}
        branch_scores: list[dict[str, Any]] = []
        branch_compare = intel.get("branchComparison") or []
        outros_pct = float(cls.get("outrosPercent") or 0)
        outros_v3_pct = float(cls.get("outrosV3Percent") or outros_pct)
        plano_source_pct = float(cls.get("planoContaSourcePercent") or 0)
        if branch_compare:
            for branch in branch_compare:
                emp = str(branch.get("empresaCodigo"))
                exp_total = _dec(branch.get("valor"))
                branch_scores.append(
                    self._score_branch(
                        emp, exp_total, outros_pct, outros_v3_pct, plano_source_pct,
                        saldo, rec_venc, pay_venc, tarifas, cash_diffs,
                    )
                )
        else:
            branch_scores.append(
                self._score_branch(
                    str(empresa_codigo_raw or "rede"),
                    _dec(cls.get("totalValor")),
                    outros_pct, outros_v3_pct, plano_source_pct,
                    saldo, rec_venc, pay_venc, tarifas, cash_diffs,
                )
            )

        branch_scores.sort(key=lambda x: x["score"], reverse=True)
        network_score = _clamp_score(
            sum(b["score"] for b in branch_scores) / len(branch_scores) if branch_scores else 0
        )

        payload = {
            "networkScore": network_score,
            "networkLevel": "saudavel" if network_score >= 70 else "atencao" if network_score >= 50 else "critico",
            "branches": branch_scores,
            "ranking": [{"empresaCodigo": b["empresaCodigo"], "score": b["score"], "nivel": b["nivel"]} for b in branch_scores],
            "healthiest": branch_scores[0] if branch_scores else None,
            "critical": branch_scores[-1] if branch_scores else None,
            "variables": {
                "outrosPercent": cls.get("outrosPercent"),
                "outrosV3Percent": cls.get("outrosV3Percent"),
                "planoContaSourcePercent": cls.get("planoContaSourcePercent"),
                "saldoAcumulado": _q2(saldo),
                "receivablesVencido": _q2(rec_venc),
                "payablesVencido": _q2(pay_venc),
                "tarifasBancarias": _q2(tarifas),
                "diferencasCaixa": cash_diffs,
            },
            "snapshotKey": self.snapshot_key(filters.data_inicial, filters.data_final, empresa_codigo_raw),
        }
        return WebPostoResponse.ok(payload)
