"""
Endpoints para validação de qualidade de dados.

GET /api/v1/data-validation/compras
  └─ Gerar relatório de qualidade de dados de compras
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from src.services.data_validation.compras_validator import ComprasValidator
from src.api.v1.endpoints._webposto_factory import make_webposto_client
from src.interfaces.http.dependencies import get_current_user

router = APIRouter(
    prefix="/data-validation",
    tags=["Data Validation"],
    dependencies=[Depends(get_current_user)],
)


class ComprasValidationReport(BaseModel):
    """Relatório de validação de compras"""
    status: str
    periodo: str
    total_compras: int
    compras_com_problema: int
    cobertura_dados_percentual: float
    fornecedores_analisados: int
    fornecedores_com_anomalia: int
    problemas_encontrados: list[dict]
    recomendacoes: list[str]


# Instanciar cliente e validador
# TODO: Injetar via dependency injection em produção
_webposto_client: Optional[object] = None
_validator: Optional[ComprasValidator] = None


def get_validator() -> ComprasValidator:
    """Lazy initialization do validador"""
    global _validator
    if _validator is None:
        _webposto_client = make_webposto_client()
        _validator = ComprasValidator(_webposto_client, db_client=None)
    return _validator


@router.get(
    "/compras",
    response_model=ComprasValidationReport,
    summary="Validar qualidade de dados de compras",
    description="Analisa integridade, consistência e completude de dados de compras",
)
async def validate_compras_data(
    dias: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Quantos dias no passado analisar",
    ),
    sensibilidade_preco: float = Query(
        default=1.5,
        ge=0.5,
        le=3.0,
        description="Sensibilidade para detectar outliers de preço (desvios padrão)",
    ),
) -> ComprasValidationReport:
    """
    Validar qualidade de dados de compras.

    Verifica:
    - Integridade de valores (custo real vs informado)
    - Cobertura de dados (% de registros válidos)
    - Anomalias de preço por fornecedor
    - Consistência (compra vs estoque)

    Retorna:
    - Relatório completo de qualidade
    - Problemas encontrados (top 50)
    - Anomalias de preço (top 20)
    - Recomendações actionáveis
    """

    validator = get_validator()

    # Definir período
    data_final = datetime.now().isoformat()
    data_inicial = (datetime.now() - timedelta(days=dias)).isoformat()

    try:
        # Gerar relatório
        relatorio = await validator.generate_data_quality_report(
            data_inicial=data_inicial,
            data_final=data_final,
        )

        return ComprasValidationReport(**relatorio)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao validar dados de compras: {str(e)}",
        )


@router.get(
    "/compras/health",
    summary="Health check de dados de compras",
    description="Verificação rápida do status dos dados de compras",
)
async def compras_data_health() -> dict:
    """
    Health check rápido de dados de compras.

    Retorna:
    - Status geral (OK/WARNING/ERROR)
    - Últimas anomalias detectadas
    - Recomendações imediatas
    """

    validator = get_validator()

    # Checar últimas 7 dias
    data_final = datetime.now().isoformat()
    data_inicial = (datetime.now() - timedelta(days=7)).isoformat()

    try:
        relatorio = await validator.generate_data_quality_report(
            data_inicial=data_inicial,
            data_final=data_final,
        )

        status = "OK" if relatorio["status"] == "PRONTO_PARA_IA" else "WARNING"
        if relatorio["compras_com_problema"] > 0:
            status = "WARNING"
        if relatorio["cobertura_dados_percentual"] < 80:
            status = "ERROR"

        return {
            "status": status,
            "cobertura_dados_percentual": relatorio["cobertura_dados_percentual"],
            "compras_analisadas": relatorio["total_compras"],
            "problemas_criticos": len(
                [p for p in relatorio["problemas_encontrados"]
                 if abs(p.get("diferenca_percentual", 0)) > 50]
            ),
            "recomendacoes": relatorio["recomendacoes"][:3],  # Top 3
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "erro": str(e),
        }


@router.post(
    "/compras/validar-item",
    summary="Validar item de compra individual",
    description="Valida um item específico de compra",
)
async def validate_single_item(item: dict) -> dict:
    """
    Validar um item de compra individual.

    Entrada:
    ```json
    {
      "id": "ITEM_123",
      "produto_id": "SKU_456",
      "valor": 1000,
      "frete": 100,
      "imposto": 50,
      "quantidade": 10,
      "data_compra": "2024-08-17T10:00:00"
    }
    ```

    Retorna:
    - Validações executadas
    - Custo real calculado
    - Problemas encontrados
    """

    validator = get_validator()

    try:
        resultado = await validator.validate_compra_item(item)

        return {
            "compra_item_id": resultado.compra_item_id,
            "produto_id": resultado.produto_id,
            "is_valid": resultado.is_valid,
            "custo_real": float(resultado.custo_real),
            "custo_esperado": float(resultado.custo_esperado),
            "diferenca": float(resultado.diferenca),
            "diferenca_percentual": resultado.diferenca_percentual,
            "problemas": resultado.problemas,
        }

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao validar item: {str(e)}",
        )


# Exportar router
__all__ = ["router"]
