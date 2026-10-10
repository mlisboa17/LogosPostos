from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from ..adapters.persistencia import PersistenciaErro, carregar_placar
from ..application.placar import FonteIndisponivel, obter_placar
from ..config import MetasErro, POSTOS
from ..domain.models import Placar
from src.interfaces.http.dependencies import get_commercial_user, require_unit_access
from src.modules.webposto_integration.tempo import agora

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


@router.get("/painel-resumo")
def obter_resumo_painel(current_user: dict = Depends(get_commercial_user)) -> dict[str, object]:
    if current_user.get("role") not in {"diretor", "gerente"}:
        raise HTTPException(status_code=403, detail="Perfil sem acesso ao painel.")
    mes = agora().strftime("%Y-%m")
    postos = [
        posto for posto in POSTOS.values()
        if current_user["role"] == "diretor"
        or current_user.get("company_id") == posto.empresa_codigo
    ]
    try:
        placares = [
            carregar_placar(posto.empresa_codigo, mes)
            for posto in postos
        ]
    except PersistenciaErro:
        logger.error("Snapshot comercial indisponível para resumo do painel mes=%s", mes)
        raise HTTPException(status_code=500, detail="Placar persistido indisponível.") from None
    disponiveis = [placar for placar in placares if placar is not None]
    contagens = {
        nivel: sum(placar.nivel_projetado == nivel for placar in disponiveis)
        for nivel in ("bronze", "prata", "ouro")
    }
    com_nivel = sum(contagens.values())
    percentuais = {
        nivel: round(contagem * 100 / com_nivel, 1) if com_nivel else None
        for nivel, contagem in contagens.items()
    }
    return {
        "mes": mes,
        "total_postos": len(postos),
        "postos_com_snapshot": len(disponiveis),
        "postos_com_projecao": sum(placar.projecao is not None for placar in disponiveis),
        "postos_com_nivel": com_nivel,
        "contagens": contagens,
        "percentuais": percentuais,
        "postos": [
            {
                "empresa_codigo": posto.empresa_codigo,
                "nome": posto.nome,
                "com_snapshot": placar is not None,
                "dia_snapshot": placar.dia if placar is not None else None,
                "projecao": placar.projecao if placar is not None else None,
                "nivel_projetado": placar.nivel_projetado if placar is not None else None,
            }
            for posto, placar in zip(postos, placares)
        ],
    }
