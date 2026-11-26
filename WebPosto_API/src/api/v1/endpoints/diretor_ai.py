"""
Endpoints do Diretor IA.

GET /api/v1/diretor-ai/brief
  └─ Relatório executivo consolidado das cinco IAs
GET /api/v1/diretor-ai/health
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.v1.endpoints._webposto_factory import make_webposto_client
from src.services.diretor_ai.diretor_orquestrador import DiretorOrquestrador

router = APIRouter(prefix="/diretor-ai", tags=["Diretor AI"])

_orquestrador: Optional[DiretorOrquestrador] = None


class AchadoOut(BaseModel):
    area: str
    achado: str
    impacto_rs: Optional[float] = None
    urgencia: str
    acao_sugerida: str
    origem: str
    status_fonte: str = "ok"


class StatusIAOut(BaseModel):
    ia: str
    status: str
    metodo: str
    motivo: Optional[str] = None


class BriefDiretorResponse(BaseModel):
    data_audit: str
    status_ias: list[StatusIAOut]
    achados: list[AchadoOut]
    impacto_total_rs: float = Field(
        ...,
        description="Soma apenas dos achados com impacto_rs informado pela própria IA",
    )
    achados_sem_valor: list[AchadoOut]
    mensagem: str
    pendencias: list[str] = Field(default_factory=list)


def get_orquestrador() -> DiretorOrquestrador:
    """Monta analisadores reais por injeção (somente leitura)."""
    global _orquestrador
    if _orquestrador is not None:
        return _orquestrador

    buyer = tax = pricing = compras = financeiro = None
    client = None
    try:
        client = make_webposto_client()
    except Exception:  # noqa: BLE001
        client = None

    try:
        from src.services.buyer_ai.buyer_analyzer import BuyerAnalyzer

        buyer = BuyerAnalyzer(client, None)
    except Exception:  # noqa: BLE001
        buyer = None

    try:
        from src.services.tax_ai.tax_advisor_analyzer import TaxAdvisorAnalyzer

        tax = TaxAdvisorAnalyzer(client, None)
    except Exception:  # noqa: BLE001
        tax = None

    try:
        from src.services.pricing_ai.pricing_analyzer import PricingAnalyzer

        pricing = PricingAnalyzer(client)
    except Exception:  # noqa: BLE001
        pricing = None

    try:
        from src.services.data_validation.compras_validator import ComprasDataValidator

        compras = ComprasDataValidator(client, None)
    except Exception:  # noqa: BLE001
        compras = None

    try:
        from src.api.v1.endpoints.financeiro_ai import get_analyzer as get_financeiro

        financeiro = get_financeiro()
    except Exception:  # noqa: BLE001
        financeiro = None

    _orquestrador = DiretorOrquestrador(
        buyer_analyzer=buyer,
        tax_analyzer=tax,
        pricing_analyzer=pricing,
        compras_validator=compras,
        financeiro_analyzer=financeiro,
    )
    return _orquestrador


@router.get(
    "/brief",
    response_model=BriefDiretorResponse,
    summary="Brief executivo das cinco IAs",
)
async def get_brief() -> dict[str, Any]:
    orq = get_orquestrador()
    try:
        return await orq.gerar_brief()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health", summary="Health check Diretor IA")
async def health() -> dict[str, Any]:
    orq = get_orquestrador()
    return {
        "status": "OK",
        "sistema": "Diretor IA",
        "webposto_writes": "0",
        "analisadores": {
            "buyer": orq.buyer_analyzer is not None,
            "tax": orq.tax_analyzer is not None,
            "pricing": orq.pricing_analyzer is not None,
            "compras": orq.compras_validator is not None,
            "financeiro": orq.financeiro_analyzer is not None,
        },
    }


__all__ = ["router"]
