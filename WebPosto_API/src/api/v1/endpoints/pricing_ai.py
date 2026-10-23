"""
Endpoints do Precificador IA.

Otimiza precificação, identifica margens inadequadas e recomenda reajustes:

GET /api/v1/pricing-ai/analise-margens
  └─ Análise consolidada de margens (negativas, baixas, saudáveis)

GET /api/v1/pricing-ai/margens-negativas
  └─ Produtos com margem negativa (lucro negativo)

GET /api/v1/pricing-ai/margens-baixas
  └─ Produtos com margem < 15%

POST /api/v1/pricing-ai/analisar-margem
  └─ Analisar margem de um produto específico

GET /api/v1/pricing-ai/sugestoes-reajuste
  └─ Produtos que deveriam ter reajuste de preço

GET /api/v1/pricing-ai/perdas-ocultas
  └─ Produtos com perdas por obsolescência/lentidão

GET /api/v1/pricing-ai/relatorio-precificacao
  └─ Relatório executivo consolidado
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.services.pricing_ai.pricing_analyzer import PricingAnalyzer
from src.api.v1.endpoints._webposto_factory import make_webposto_client

router = APIRouter(prefix="/pricing-ai", tags=["Pricing AI"])


class AnaliseMargemRequest(BaseModel):
    """Request para análise de margem"""
    produto_id: str
    preco_venda: float
    custo_produto: float
    aliquota_icms: Optional[float] = 12


# Instanciar cliente e analisador
_webposto_client: Optional[object] = None
_analyzer: Optional[PricingAnalyzer] = None


def get_analyzer() -> PricingAnalyzer:
    """Lazy initialization do analisador"""
    global _analyzer, _webposto_client
    if _analyzer is None:
        _webposto_client = make_webposto_client()
        _analyzer = PricingAnalyzer(_webposto_client, db_client=None)
    return _analyzer


@router.get(
    "/analise-margens",
    summary="Análise consolidada de margens",
    description="Resumo de produtos por categoria de margem",
)
async def get_analise_margens() -> dict:
    """
    Análise consolidada de margens de todos produtos.

    Categoriza produtos em:
    - Margem negativa (lucro negativo)
    - Margem crítica (0-10%)
    - Margem baixa (10-20%)
    - Margem saudável (>20%)

    Retorna: Contagem e exemplos de cada categoria.
    """

    analyzer = get_analyzer()

    try:
        margens_negativas = await analyzer.identificar_margens_negativas()
        margens_baixas = await analyzer.identificar_produtos_baixa_margem(15)

        return {
            "total_produtos": 0,  # Placeholder
            "margens_negativas": {
                "quantidade": len(margens_negativas),
                "impacto_mensal": 0,
                "produtos": [
                    {
                        "produto_id": m.produto_id,
                        "margem_percentual": m.margem_percentual,
                        "recomendacao": m.recomendacao,
                    }
                    for m in margens_negativas[:5]
                ],
            },
            "margens_baixas": {
                "quantidade": len(margens_baixas),
                "impacto_mensal": 0,
                "produtos": [
                    {
                        "produto_id": m.produto_id,
                        "margem_percentual": m.margem_percentual,
                        "recomendacao": m.recomendacao,
                    }
                    for m in margens_baixas[:5]
                ],
            },
            "status": "OK" if len(margens_negativas) == 0 else "CRÍTICO",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao analisar margens: {str(e)}",
        )


@router.get(
    "/margens-negativas",
    summary="Produtos com margem negativa",
    description="Produtos que estão perdendo dinheiro",
)
async def get_margens_negativas() -> list[dict]:
    """
    Encontrar todos produtos com margem negativa.

    Problema: Preço de venda < Custo total (produto + impostos + overhead)

    Risco: Cada venda reduz lucro.

    Retorna: Lista de produtos com margem negativa, ordenados por severidade.
    """

    analyzer = get_analyzer()

    try:
        margens_negativas = await analyzer.identificar_margens_negativas()

        return [
            {
                "produto_id": m.produto_id,
                "descricao": m.descricao,
                "preco_venda": float(m.preco_venda),
                "custo_total": float(m.custo_total),
                "margem_bruta": float(m.margem_bruta),
                "margem_percentual": m.margem_percentual,
                "markup": m.markup,
                "recomendacao": m.recomendacao,
                "problemas": m.problemas,
            }
            for m in margens_negativas
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar margens negativas: {str(e)}",
        )


@router.get(
    "/margens-baixas",
    summary="Produtos com margem baixa",
    description="Produtos com margem entre 10-20%",
)
async def get_margens_baixas(
    threshold_percentual: float = Query(
        default=15,
        ge=5,
        le=30,
        description="Threshold de margem em percentual",
    )
) -> list[dict]:
    """
    Encontrar produtos com margem abaixo do threshold.

    Padrão: Margem < 15% é considerada baixa (deveria ser >= 20%)

    Problema: Margem insuficiente para cobrir riscos operacionais.

    Retorna: Lista de produtos com margem baixa.
    """

    analyzer = get_analyzer()

    try:
        margens_baixas = await analyzer.identificar_produtos_baixa_margem(
            threshold_percentual
        )

        return [
            {
                "produto_id": m.produto_id,
                "descricao": m.descricao,
                "preco_venda": float(m.preco_venda),
                "custo_total": float(m.custo_total),
                "margem_percentual": m.margem_percentual,
                "margem_status": m.margem_status,
                "recomendacao": m.recomendacao,
            }
            for m in margens_baixas
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar margens baixas: {str(e)}",
        )


@router.post(
    "/analisar-margem",
    summary="Analisar margem de um produto",
    description="Análise detalhada de um produto específico",
)
async def analisar_margem(request: AnaliseMargemRequest) -> dict:
    """
    Analisar margem detalhada de um produto.

    Calcula:
    - Custo total (produto + impostos + overhead)
    - Margem bruta e percentual
    - Markup
    - Status (negativa, crítica, baixa, saudável)
    - Recomendações

    Retorna: Análise completa com recomendações.
    """

    analyzer = get_analyzer()

    try:
        resultado = await analyzer.analisar_margem_produto(
            request.produto_id,
            Decimal(str(request.preco_venda)),
            Decimal(str(request.custo_produto)),
            Decimal(str(request.aliquota_icms or 12)),
        )

        return {
            "produto_id": resultado.produto_id,
            "preco_venda": float(resultado.preco_venda),
            "custo_total": float(resultado.custo_total),
            "margem_bruta": float(resultado.margem_bruta),
            "margem_percentual": resultado.margem_percentual,
            "margem_status": resultado.margem_status,
            "markup": resultado.markup,
            "problemas": resultado.problemas,
            "recomendacao": resultado.recomendacao,
        }

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao analisar margem: {str(e)}",
        )


@router.get(
    "/sugestoes-reajuste",
    summary="Sugestões de reajuste de preço",
    description="Produtos que deveriam ter reajuste",
)
async def get_sugestoes_reajuste(
    apenas_urgentes: bool = Query(
        default=False,
        description="Apenas sugestões críticas/altas",
    )
) -> list[dict]:
    """
    Gerar sugestões de reajuste de preço.

    Baseado em:
    - Margem atual vs. margem alvo
    - Velocidade de venda
    - Impacto financeiro

    Retorna: Lista de sugestões priorizadas por urgência.
    """

    analyzer = get_analyzer()

    try:
        # Placeholder: em produção, analisar todos produtos
        sugestoes = []

        return [
            {
                "produto_id": s.produto_id,
                "descricao": s.descricao,
                "preco_atual": float(s.preco_atual),
                "preco_sugerido": float(s.preco_sugerido),
                "percentual_ajuste": s.percentual_ajuste,
                "margem_atual": float(s.margem_atual),
                "margem_sugerida": float(s.margem_sugerida),
                "impacto_mensal": float(s.impacto_mensal),
                "motivo": s.motivo,
                "urgencia": s.urgencia,
            }
            for s in sugestoes
            if not apenas_urgentes or s.urgencia in ["CRÍTICA", "ALTA"]
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar sugestões: {str(e)}",
        )


@router.get(
    "/perdas-ocultas",
    summary="Produtos com perdas ocultas",
    description="Obsoletos, lentidão, desperdício",
)
async def get_perdas_ocultas() -> list[dict]:
    """
    Detectar perdas ocultas por:
    - Obsolescência (>90 dias sem venda)
    - Baixa rotação (45-90 dias)
    - Possível erro de precificação
    - Desperdício/quebra estimada

    Risco: Perda de capital, oportunidade custo.

    Retorna: Lista de produtos com perdas ocultas.
    """

    analyzer = get_analyzer()

    try:
        # Placeholder: em produção, analisar histórico de vendas
        perdas = []

        return [
            {
                "tipo": p.tipo,
                "produto_id": p.produto_id,
                "descricao": p.descricao,
                "perda_estimada_mensal": float(p.perda_estimada_mensal),
                "dias_sem_venda": p.dias_sem_venda,
                "quantidade_parada": p.quantidade_parada,
                "recomendacao": p.recomendacao,
            }
            for p in perdas
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao detectar perdas ocultas: {str(e)}",
        )


@router.get(
    "/relatorio-precificacao",
    summary="Relatório executivo de precificação",
    description="Consolidado de margens, reajustes e impacto",
)
async def get_relatorio_precificacao() -> dict:
    """
    Gerar relatório executivo consolidado.

    Inclui:
    - Número de produtos por categoria de margem
    - Oportunidades de reajuste e impacto
    - Perdas ocultas identificadas
    - Impacto financeiro total
    - Recomendações prioritárias
    - Status geral (OK, ALERTA, CRÍTICO)

    Retorna: Relatório pronto para C-level.
    """

    analyzer = get_analyzer()

    try:
        relatorio = await analyzer.gerar_relatorio_precificacao()

        return relatorio

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar relatório: {str(e)}",
        )


@router.get(
    "/health",
    summary="Health check - Precificador IA operacional?",
    description="Verificação rápida se sistema está funcionando",
)
async def pricing_health() -> dict:
    """Health check rápido"""

    analyzer = get_analyzer()

    try:
        # Tentar operação leve
        await analyzer.gerar_relatorio_precificacao()

        return {
            "status": "OK",
            "sistema": "Precificador IA",
            "pronto": True,
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "sistema": "Precificador IA",
            "erro": str(e),
            "pronto": False,
        }


# Exportar router
__all__ = ["router"]
