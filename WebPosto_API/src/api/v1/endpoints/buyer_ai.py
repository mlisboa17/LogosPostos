"""
Endpoints do Comprador IA.

GET /api/v1/buyer-ai/capital-parado
  └─ Produtos imobilizando capital

GET /api/v1/buyer-ai/ruptures-risk
  └─ Produtos em risco de ruptura

GET /api/v1/buyer-ai/recomendacoes-reposicao
  └─ O que comprar e quanto

GET /api/v1/buyer-ai/desequilibrios
  └─ Compras vs Vendas desbalanceadas

GET /api/v1/buyer-ai/brief-executivo
  └─ Relatório consolidado para decisão
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from src.services.buyer_ai.buyer_analyzer import BuyerAnalyzer
from src.api.v1.endpoints._webposto_factory import make_webposto_client

router = APIRouter(prefix="/buyer-ai", tags=["Buyer AI"])


class ProdutoParado(BaseModel):
    """Produto com capital parado"""
    produto_id: str
    descricao: str
    quantidade: int
    capital_parado: float
    dias_sem_venda: int
    urgencia: str


class RupturaRiscoResponse(BaseModel):
    """Produto em risco de ruptura"""
    produto_id: str
    descricao: str
    estoque_atual: int
    consumo_diario: float
    dias_de_estoque: float
    rupture_probability: float
    vendas_perdidas_estimadas: float
    urgencia: str


class RecomendacaoReposicaoResponse(BaseModel):
    """Recomendação de reposição"""
    produto_id: str
    descricao: str
    prioridade: int
    quantidade_sugerida: int
    economia_potencial: float
    urgencia: str


class ExecutiveBriefResponse(BaseModel):
    """Brief executivo"""
    economia_potencial_total: float
    problemas_criticos: int
    top_problemas: list[dict]
    proximas_acoes: list[str]


# Instanciar cliente e analisador
_webposto_client: Optional[object] = None
_analyzer: Optional[BuyerAnalyzer] = None


def get_analyzer() -> BuyerAnalyzer:
    """Lazy initialization do analisador"""
    global _analyzer
    if _analyzer is None:
        _webposto_client = make_webposto_client()
        _analyzer = BuyerAnalyzer(_webposto_client, db_client=None)
    return _analyzer


@router.get(
    "/capital-parado",
    response_model=list[dict],
    summary="Produtos imobilizando capital",
    description="Encontra produtos sem giro que estão ocupando espaço e capital",
)
async def get_immobilized_capital() -> list[dict]:
    """
    Identificar capital parado.

    Produtos que não foram vendidos nos últimos 45+ dias.
    Cada produto imobiliza capital que poderia ser investido em reposição.

    Retorna: Lista de produtos ordenados por capital parado (maior primeiro).
    """

    analyzer = get_analyzer()

    try:
        resultado = await analyzer.find_immobilized_capital()

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao analisar capital parado: {str(e)}",
        )


@router.get(
    "/ruptures-risk",
    response_model=list[dict],
    summary="Produtos em risco de ruptura",
    description="Produtos que podem faltar nos próximos dias",
)
async def get_rupture_risk(
    dias_ahead: int = Query(
        default=7,
        ge=1,
        le=30,
        description="Quantos dias no futuro prever",
    )
) -> list[dict]:
    """
    Prever rupturas iminentes.

    Baseado em:
    - Consumo histórico (últimos 30 dias)
    - Estoque atual
    - Tempo de reabastecimento do fornecedor

    Se dias_estoque < dias_reabastecimento: RISCO

    Retorna: Lista de produtos em risco, ordenados por urgência.
    """

    analyzer = get_analyzer()

    try:
        resultado = await analyzer.find_rupture_risk()

        # Filtrar por dias_ahead
        resultado = [
            r for r in resultado
            if r["dias_de_estoque"] < dias_ahead
        ]

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao prever rupturas: {str(e)}",
        )


@router.get(
    "/recomendacoes-reposicao",
    response_model=list[dict],
    summary="Recomendações de reposição",
    description="O que comprar, quanto e quando",
)
async def get_replenishment_recommendations() -> list[dict]:
    """
    Obter recomendações de reposição.

    Baseado em:
    - Produtos em risco de ruptura (prioridade 1)
    - Consumo histórico
    - Estoque ideal = consumo_diário * 45 dias
    - Preço atual vs histórico

    Retorna: Lista ordenada por prioridade e economia potencial.
    """

    analyzer = get_analyzer()

    try:
        resultado = await analyzer.recommend_replenishment()

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar recomendações: {str(e)}",
        )


@router.get(
    "/desequilibrios",
    response_model=dict,
    summary="Compras vs Vendas desbalanceadas",
    description="Produtos onde compramos demais ou pouco",
)
async def get_buy_sell_mismatch(
    periodo_dias: int = Query(
        default=30,
        ge=7,
        le=90,
        description="Quantos dias analisar",
    )
) -> dict:
    """
    Identificar desequilíbrios entre compras e vendas.

    Análise:
    - Comprado demais, vendido pouco → capital parado
    - Comprado pouco, vendido muito → vendas perdidas

    Retorna: Análise consolidada com desequilíbrios e impacto financeiro.
    """

    analyzer = get_analyzer()

    try:
        resultado = await analyzer.analyze_buy_vs_sell_mismatch(
            periodo_dias=periodo_dias
        )

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao analisar desequilíbrios: {str(e)}",
        )


@router.get(
    "/brief-executivo",
    response_model=dict,
    summary="Brief executivo consolidado",
    description="Relatório de 3 páginas com problemas e recomendações",
)
async def get_executive_brief() -> dict:
    """
    Obter brief executivo consolidado.

    Inclui:
    - Top 3 problemas (impacto e ação)
    - Top 5 recomendações (economia)
    - Próximas ações imediatas
    - Economia potencial total

    Formato: Pronto para decisão executiva.
    """

    analyzer = get_analyzer()

    try:
        brief = await analyzer.generate_executive_brief()

        return brief

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar brief executivo: {str(e)}",
        )


@router.get(
    "/health",
    summary="Health check - Comprador IA operacional?",
    description="Verificação rápida se sistema está funcionando",
)
async def buyer_ai_health() -> dict:
    """Health check rápido"""

    analyzer = get_analyzer()

    try:
        # Tentar chamar análise leve
        resultado = await analyzer.find_immobilized_capital()

        return {
            "status": "OK",
            "sistema": "Comprador IA",
            "produtos_analisados": len(resultado),
            "pronto": True,
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "sistema": "Comprador IA",
            "erro": str(e),
            "pronto": False,
        }


# Exportar router
__all__ = ["router"]
