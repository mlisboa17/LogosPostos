from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..adapters.persistencia import PersistenciaErro
from ..application.placar import FonteIndisponivel, obter_placar
from ..config import MetasErro, POSTOS
from ..domain.models import Placar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/commercial", tags=["commercial"])


@router.get("/placar", response_model=Placar)
async def consultar_placar(
    posto: int = Query(...),
    mes: str = Query(...),
    dia: date | None = Query(None),
) -> Placar:
    if posto not in POSTOS:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
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
def listar_postos() -> list[dict[str, int | str]]:
    return [
        {"empresa_codigo": posto.empresa_codigo, "nome": posto.nome} for posto in POSTOS.values()
    ]
