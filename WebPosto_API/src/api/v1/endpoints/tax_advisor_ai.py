"""
Endpoints do Tax Advisor IA.

Audita classificação tributária e detecta riscos fiscais:

GET /api/v1/tax-advisor/audit-report
  └─ Relatório consolidado de auditoria tributária

GET /api/v1/tax-advisor/divergencias
  └─ Produtos com divergências de classificação

GET /api/v1/tax-advisor/sem-classificacao
  └─ Produtos sem NCM/CEST adequado

POST /api/v1/tax-advisor/validar-ncm
  └─ Validar NCM específico

POST /api/v1/tax-advisor/validar-cest
  └─ Validar CEST específico

POST /api/v1/tax-advisor/calcular-impostos
  └─ Calcular ICMS/PIS/COFINS
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.services.tax_ai.tax_advisor_analyzer import TaxAdvisorAnalyzer
from src.api.v1.endpoints._webposto_factory import make_webposto_client
from src.interfaces.http.dependencies import get_current_user

router = APIRouter(
    prefix="/tax-advisor",
    tags=["Tax Advisor AI"],
    dependencies=[Depends(get_current_user)],
)


class NCMValidationRequest(BaseModel):
    """Request para validação de NCM"""
    produto_id: str
    ncm: str


class CESTValidationRequest(BaseModel):
    """Request para validação de CEST"""
    produto_id: str
    cest: str


class TaxCalculationRequest(BaseModel):
    """Request para cálculo de impostos"""
    produto_id: str
    ncm: str
    estado: str
    base_calculo: float


# Instanciar cliente e analisador
_webposto_client: Optional[object] = None
_analyzer: Optional[TaxAdvisorAnalyzer] = None


def get_analyzer() -> TaxAdvisorAnalyzer:
    """Lazy initialization do analisador"""
    global _analyzer
    if _analyzer is None:
        _webposto_client = make_webposto_client()
        _analyzer = TaxAdvisorAnalyzer(_webposto_client, db_client=None)
    return _analyzer


@router.get(
    "/audit-report",
    summary="Auditoria tributária consolidada",
    description="Relatório de risco fiscal e recomendações",
)
async def get_tax_audit_report() -> dict:
    """
    Gerar relatório consolidado de auditoria tributária.

    Analisa:
    - Divergências de classificação (NCM, CST)
    - Produtos sem classificação
    - Risco fiscal estimado
    - Recomendações de ação

    Retorna: Relatório executivo pronto para decisão.
    """

    analyzer = get_analyzer()

    try:
        report = await analyzer.generate_tax_audit_report()

        return report

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar auditoria tributária: {str(e)}",
        )


@router.get(
    "/divergencias",
    summary="Produtos com divergências tributárias",
    description="Mesmos produtos com classificações diferentes",
)
async def get_tax_divergences(
    periodo_dias: int = Query(
        default=30,
        ge=7,
        le=90,
        description="Quantos dias analisar",
    )
) -> list[dict]:
    """
    Detectar produtos com divergências de classificação.

    Problemas:
    - Mesmo produto com NCMs diferentes
    - Mesmo produto com CSTs diferentes
    - Inconsistências em substituição tributária

    Risco: Pode causar rejeição de notas ou multa fiscal.

    Retorna: Lista de divergências encontradas, ordenadas por severidade.
    """

    analyzer = get_analyzer()

    try:
        divergencias = await analyzer.detect_tax_divergences(periodo_dias=periodo_dias)

        return divergencias

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao detectar divergências: {str(e)}",
        )


@router.get(
    "/sem-classificacao",
    summary="Produtos sem classificação tributária",
    description="Produtos sem NCM/CEST preenchido",
)
async def get_unclassified_products() -> list[dict]:
    """
    Encontrar produtos sem classificação tributária adequada.

    Produtos que nunca tiveram:
    - NCM preenchido
    - CEST preenchido (quando aplicável)

    Risco: Não podem ser operacionalizados em notas fiscais.

    Retorna: Lista de produtos que precisam classificação.
    """

    analyzer = get_analyzer()

    try:
        sem_classificacao = await analyzer.find_unclassified_products()

        return sem_classificacao

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar produtos sem classificação: {str(e)}",
        )


@router.post(
    "/validar-ncm",
    summary="Validar NCM individual",
    description="Verifica se NCM é válido e vigente",
)
async def validate_ncm(request: NCMValidationRequest) -> dict:
    """
    Validar NCM de um produto específico.

    Verifica:
    - Formato (8 dígitos)
    - Dígito verificador
    - Vigência na tabela

    Retorna: Validação detalhada com categoria e problemas encontrados.
    """

    analyzer = get_analyzer()

    try:
        resultado = await analyzer.validate_ncm(
            request.produto_id,
            request.ncm,
        )

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao validar NCM: {str(e)}",
        )


@router.post(
    "/validar-cest",
    summary="Validar CEST individual",
    description="Verifica se CEST é válido e vigente",
)
async def validate_cest(request: CESTValidationRequest) -> dict:
    """
    Validar CEST de um produto específico.

    CEST = Código de Substituição Tributária (7 dígitos ou vazio)

    Verifica:
    - Formato
    - Vigência
    - Aplicabilidade

    Retorna: Validação com recomendações.
    """

    analyzer = get_analyzer()

    try:
        resultado = await analyzer.validate_cest(
            request.produto_id,
            request.cest,
        )

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao validar CEST: {str(e)}",
        )


@router.post(
    "/calcular-impostos",
    summary="Calcular ICMS/PIS/COFINS",
    description="Simula cálculo de impostos para um produto",
)
async def calculate_taxes(request: TaxCalculationRequest) -> dict:
    """
    Calcular impostos (ICMS, PIS, COFINS) para um produto.

    Baseado em:
    - NCM do produto
    - Estado
    - Base de cálculo

    Retorna:
    - Alíquotas aplicáveis
    - Cálculo dos impostos
    - Margem líquida

    Útil para:
    - Simular impacto de mudança de NCM
    - Validar cálculos em operações
    - Estimar precificação
    """

    analyzer = get_analyzer()

    try:
        resultado = await analyzer.validate_tax_calculation(
            request.produto_id,
            request.ncm,
            request.estado,
            Decimal(str(request.base_calculo)),
        )

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao calcular impostos: {str(e)}",
        )


@router.get(
    "/health",
    summary="Health check - Tax Advisor IA operacional?",
    description="Verificação rápida se sistema está funcionando",
)
async def tax_advisor_health() -> dict:
    """Health check rápido"""

    analyzer = get_analyzer()

    try:
        # Tentar chamar análise leve
        resultado = await analyzer.find_unclassified_products()

        return {
            "status": "OK",
            "sistema": "Tax Advisor IA",
            "produtos_analisados": len(resultado),
            "pronto": True,
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "sistema": "Tax Advisor IA",
            "erro": str(e),
            "pronto": False,
        }


# Exportar router
__all__ = ["router"]
