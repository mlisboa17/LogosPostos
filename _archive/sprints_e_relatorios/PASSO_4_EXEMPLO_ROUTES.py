"""
EXEMPLO - PASSO 4: Unified FastAPI Routes para Auditoria
Demonstra como integrar AuditoriaRepository com FastAPI
Pronto para ser adaptado e expandido

Localização desejada: /WebPosto_API/src/interfaces/http/routes/auditoria.py
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, date
from typing import List, Optional
import logging

from src.domain.models.auditoria_models import (
    DespesaCaixa,
    FechamentoCaixa,
    ResumoAuditoriaUnidade,
    ListaFechamentos,
    StatusJustificativa,
)
from src.infrastructure.repositories.auditoria_repository import AuditoriaRepository

logger = logging.getLogger(__name__)

# ============ ROUTER CONFIGURATION ============

router = APIRouter(
    prefix="/auditoria",
    tags=["audit"],
    responses={404: {"description": "Not found"}},
)


# ============ DEPENDENCY INJECTION ============


async def get_auditoria_repo() -> AuditoriaRepository:
    """
    Dependency for injecting AuditoriaRepository
    In production, get db from FastAPI context/container

    Example with Dependency Injection container:
    from src.infrastructure.container import get_db_instance

    db = await get_db_instance()
    return AuditoriaRepository(db)
    """
    # TODO: Implement proper dependency injection from FastAPI container
    # This is a placeholder showing the interface
    raise NotImplementedError(
        "Implement database dependency injection in your FastAPI app startup"
    )


# ============ DESPESAS ENDPOINTS ============


@router.get(
    "/despesas/{unidade_id}",
    response_model=List[DespesaCaixa],
    summary="Get expenses for a unit",
    responses={
        200: {"description": "List of expenses"},
        404: {"description": "Unit not found or no expenses"},
        422: {"description": "Invalid parameters"},
    },
)
async def get_despesas_unidade(
    unidade_id: str,
    data_inicio: date = Query(..., description="Start date (YYYY-MM-DD)"),
    data_fim: date = Query(..., description="End date (YYYY-MM-DD)"),
    status: Optional[StatusJustificativa] = Query(
        None, description="Filter by justification status"
    ),
    repo: AuditoriaRepository = Depends(get_auditoria_repo),
):
    """
    Retrieve all expenses for a unit within a date range

    Optional filter by justification status (pendente, justificada, rejeitada, em_analise)

    Example:
    GET /auditoria/despesas/real_01?data_inicio=2026-04-12&data_fim=2026-04-13
    GET /auditoria/despesas/real_01?data_inicio=2026-04-12&data_fim=2026-04-13&status=pendente
    """
    try:
        # Convert date to datetime
        data_inicio_dt = datetime.combine(data_inicio, datetime.min.time())
        data_fim_dt = datetime.combine(data_fim, datetime.max.time())

        despesas = await repo.get_despesas_by_unidade(
            unidade_id=unidade_id,
            data_inicio=data_inicio_dt,
            data_fim=data_fim_dt,
            status_justificativa=status,
        )

        if not despesas:
            raise HTTPException(
                status_code=404,
                detail=f"No expenses found for unit {unidade_id} in date range",
            )

        return despesas

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving despesas: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while retrieving expenses",
        )


@router.post(
    "/despesas",
    response_model=DespesaCaixa,
    status_code=201,
    summary="Create a new expense",
)
async def create_despesa(
    despesa: DespesaCaixa,
    repo: AuditoriaRepository = Depends(get_auditoria_repo),
):
    """
    Register a new expense in the system

    Automatically validates:
    - Valor must be positive
    - Categoria must be one of: luz, gelo, vale_operador, vale_cliente,
      manutencao, combustivel, limpeza, insumos, outros
    - Status defaults to 'pendente'

    Example POST body:
    {
        "id": "exp_001",
        "unidade_id": "real_01",
        "caixa_tipo": "pista",
        "horario": "2026-04-13T14:30:00",
        "categoria": "gelo",
        "valor": 85.50,
        "operador": "João Silva",
        "status_justificativa": "justificada",
        "tem_documento": true
    }
    """
    try:
        created = await repo.create_despesa(despesa)
        return created
    except Exception as e:
        logger.error(f"Error creating despesa: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error creating expense record",
        )


@router.patch(
    "/despesas/{despesa_id}/status",
    response_model=dict,
    summary="Update expense justification status",
)
async def update_despesa_status(
    despesa_id: str,
    novo_status: StatusJustificativa = Query(..., description="New status"),
    motivo: Optional[str] = Query(None, description="Reason for status change"),
    repo: AuditoriaRepository = Depends(get_auditoria_repo),
):
    """
    Update the justification status of an expense

    Valid statuses:
    - pendente: Waiting for justification
    - justificada: Has been justified
    - rejeitada: Justification rejected
    - em_analise: Under review

    Example:
    PATCH /auditoria/despesas/exp_001/status?novo_status=justificada&motivo=NF%20anexada
    """
    try:
        success = await repo.update_despesa_status(
            despesa_id=despesa_id,
            novo_status=novo_status,
            motivo=motivo,
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Expense {despesa_id} not found",
            )

        return {
            "message": "Status updated successfully",
            "despesa_id": despesa_id,
            "novo_status": novo_status.value,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating despesa status: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error updating expense status",
        )


# ============ FECHAMENTOS ENDPOINTS ============


@router.get(
    "/fechamentos/{unidade_id}",
    response_model=ListaFechamentos,
    summary="Get consolidated closures for a date",
)
async def get_fechamentos_unidade(
    unidade_id: str,
    data: date = Query(..., description="Date to retrieve closures for (YYYY-MM-DD)"),
    repo: AuditoriaRepository = Depends(get_auditoria_repo),
):
    """
    Retrieve all cash closures for a unit on a specific date

    Returns detailed information about each closure including:
    - Gross revenue
    - Cash breaks per currency type
    - Payment method breakdown
    - Audit flags if applicable

    Example:
    GET /auditoria/fechamentos/real_01?data=2026-04-13
    """
    try:
        data_dt = datetime.combine(data, datetime.min.time())

        fechamentos = await repo.get_fechamentos_consolidated(
            unidade_id=unidade_id,
            data=data_dt,
        )

        if not fechamentos:
            raise HTTPException(
                status_code=404,
                detail=f"No closures found for unit {unidade_id} on {data}",
            )

        return ListaFechamentos(
            unidade_id=unidade_id,
            data=data_dt,
            fechamentos=fechamentos,
            total_caixas=len(fechamentos),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving fechamentos: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving closures",
        )


@router.post(
    "/fechamentos",
    response_model=FechamentoCaixa,
    status_code=201,
    summary="Create a new cash closure",
)
async def create_fechamento(
    fechamento: FechamentoCaixa,
    repo: AuditoriaRepository = Depends(get_auditoria_repo),
):
    """
    Register a new daily cash closure

    This endpoint is typically called at end-of-day when:
    1. All transactions for the day are finalized
    2. Cash is counted and reconciled
    3. Payment methods are totaled

    The system automatically calculates:
    - Cash breaks (saldo_esperado vs saldo_informado)
    - Break percentage relative to revenue
    - Flags for audit if breaks > R$10
    """
    try:
        created = await repo.create_fechamento(fechamento)
        return created
    except Exception as e:
        logger.error(f"Error creating fechamento: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error creating closure record",
        )


@router.patch(
    "/fechamentos/{fechamento_id}/flag-auditoria",
    response_model=dict,
    summary="Flag closure for audit review",
)
async def flag_closure_for_audit(
    fechamento_id: str,
    motivo: str = Query(..., description="Reason for audit flag"),
    repo: AuditoriaRepository = Depends(get_auditoria_repo),
):
    """
    Manually flag a closure for audit review

    Common reasons:
    - "Quebra acima de R$50"
    - "Despesas sem categoria"
    - "Padrão anômalo de vendas"

    Example:
    PATCH /auditoria/fechamentos/fech_001/flag-auditoria?motivo=Quebra%20acima%20de%20R%2450
    """
    try:
        success = await repo.flag_fechamento_for_audit(
            fechamento_id=fechamento_id,
            motivo=motivo,
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Closure {fechamento_id} not found",
            )

        return {
            "message": "Closure flagged for audit",
            "fechamento_id": fechamento_id,
            "motivo": motivo,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error flagging closure: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error flagging closure for audit",
        )


# ============ AUDIT INSIGHTS ENDPOINTS ============


@router.get(
    "/resumo/{unidade_id}",
    response_model=ResumoAuditoriaUnidade,
    summary="Get executive audit summary",
)
async def get_resumo_auditoria(
    unidade_id: str,
    data: date = Query(..., description="Date to summarize (YYYY-MM-DD)"),
    repo: AuditoriaRepository = Depends(get_auditoria_repo),
):
    """
    Get consolidated audit summary with KPIs for a unit

    Includes:
    - Total revenue and expenses
    - Cash breaks and break percentage
    - Count of closures by status
    - Expenses without documentation/category
    - Outlier detection (deviation > 10% from 5% standard)

    Example:
    GET /auditoria/resumo/real_01?data=2026-04-13
    """
    try:
        data_dt = datetime.combine(data, datetime.min.time())

        resumo = await repo.get_auditoria_resumo_unidade(
            unidade_id=unidade_id,
            data=data_dt,
        )

        if not resumo:
            raise HTTPException(
                status_code=404,
                detail=f"No audit data found for unit {unidade_id} on {data}",
            )

        return resumo

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating audit summary: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error generating audit summary",
        )


@router.get(
    "/insights",
    response_model=List[dict],
    summary="Get detected anomalies and insights",
)
async def get_auditoria_insights(
    data_inicio: date = Query(..., description="Start date (YYYY-MM-DD)"),
    data_fim: date = Query(..., description="End date (YYYY-MM-DD)"),
    unidade_id: Optional[str] = Query(None, description="Optional filter by unit"),
    repo: AuditoriaRepository = Depends(get_auditoria_repo),
):
    """
    Get automatic anomaly detection and audit insights

    Detects:
    - Cash breaks > R$10 (critical if > R$50)
    - Expense ratio > 10% (standard is ~5%)
    - Expenses without documentation
    - Patterns with deviation > 10%

    Insights are ranked by severity: crítico > warning > info

    Example:
    GET /auditoria/insights?data_inicio=2026-04-12&data_fim=2026-04-13
    GET /auditoria/insights?data_inicio=2026-04-12&data_fim=2026-04-13&unidade_id=real_01
    """
    try:
        data_inicio_dt = datetime.combine(data_inicio, datetime.min.time())
        data_fim_dt = datetime.combine(data_fim, datetime.max.time())

        insights = await repo.calculate_auditoria_insights(
            data_inicio=data_inicio_dt,
            data_fim=data_fim_dt,
            unidade_id=unidade_id,
        )

        return insights

    except Exception as e:
        logger.error(f"Error calculating insights: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error calculating audit insights",
        )


# ============ HEALTH CHECK ============


@router.get("/health", summary="Audit service health check")
async def health_check():
    """
    Simple health check for audit endpoints

    Returns:
    - status: ok/error
    - timestamp: current timestamp
    """
    return {
        "status": "ok",
        "service": "Auditoria",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============ INTEGRATION POINT ============

"""
Para integrar estas rotas na aplicação FastAPI principal:

1. No seu main.py ou app initialization:

from src.interfaces.http.routes.auditoria import router as auditoria_router

app = FastAPI(title="WebPosto_API", version="2.0")
app.include_router(auditoria_router)

2. Endpoints estarão disponíveis em:
- GET  /auditoria/despesas/{unidade_id}
- POST /auditoria/despesas
- PATCH /auditoria/despesas/{despesa_id}/status
- GET  /auditoria/fechamentos/{unidade_id}
- POST /auditoria/fechamentos
- PATCH /auditoria/fechamentos/{fechamento_id}/flag-auditoria
- GET  /auditoria/resumo/{unidade_id}
- GET  /auditoria/insights
- GET  /auditoria/health

3. Documentação Swagger automática em: /docs
"""
