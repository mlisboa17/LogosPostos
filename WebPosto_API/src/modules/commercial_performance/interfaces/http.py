from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from ..adapters.persistencia import PersistenciaErro
from ..application.placar import FonteIndisponivel, obter_placar
from ..config import MetasErro, POSTOS
from ..domain.models import Placar
from src.interfaces.http.dependencies import get_commercial_user, require_unit_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/commercial", tags=["commercial"])


@router.get("/placar", response_model=Placar)
async def consultar_placar(
    posto: int = Query(...),
    mes: str = Query(...),
    dia: date | None = Query(None),
    current_user: dict = Depends(get_commercial_user),
) -> Placar:
    if posto not in POSTOS:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
    require_unit_access(current_user, posto)
    try:
        return await obter_placar(posto, mes, dia)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except FonteIndisponivel:
        raise HTTPException(
            status_code=502, detail="Fonte indisponível. Tente novamente."
        ) from None
    except MetasErro:
        logger.error("Metas comerciais indisponíveis posto=%s mes=%s", posto, mes)
        raise HTTPException(status_code=500, detail="Metas do posto indisponíveis.") from None
    except PersistenciaErro:
        logger.error("Snapshot comercial indisponível posto=%s mes=%s", posto, mes)
        raise HTTPException(status_code=500, detail="Placar persistido indisponível.") from None


@router.get("/postos")
def listar_postos(current_user: dict = Depends(get_commercial_user)) -> list[dict[str, int | str]]:
    return [
        {"empresa_codigo": posto.empresa_codigo, "nome": posto.nome} for posto in POSTOS.values()
        if current_user["role"] in {"diretor", "auditor"}
        or current_user.get("company_id") == posto.empresa_codigo
    ]
