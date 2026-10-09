from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, timedelta

from src.modules.webposto_integration.http import WebPostoErro
from src.modules.webposto_integration.tempo import agora, hoje

from ..adapters.webposto import PATHS, buscar
from ..config import POSTOS, ler_metas
from ..domain.models import Placar, Proveniencia
from ..rules.placar import VERSAO, calcular, primeiro_dia, referencia

logger = logging.getLogger(__name__)
TIMEOUT = 180


class FonteIndisponivel(RuntimeError):
    pass


async def obter_placar(posto: int, mes: str, dia: date | None = None) -> Placar:
    unidade = POSTOS[posto]
    atual = hoje()
    ref = referencia(mes, atual, dia)
    inicio = primeiro_dia(mes)
    metas_mes = ler_metas(mes)
    metas = metas_mes.postos.get(posto) if metas_mes else None
    try:
        linhas, produtos, nomes = await asyncio.wait_for(buscar(unidade, inicio - timedelta(days=6), ref), TIMEOUT)
    except (TimeoutError, WebPostoErro, ValueError, KeyError, TypeError) as exc:
        logger.warning("Fonte comercial indisponivel posto=%s tipo=%s", posto, type(exc).__name__)
        raise FonteIndisponivel("Fonte indisponivel. Tente novamente.") from None
    proveniencia = Proveniencia(
        executado_em=agora(), execucao_id=uuid.uuid4().hex, versao_regra=VERSAO,
        fontes=tuple(PATHS.values()), metas_cadastradas=metas is not None,
    )
    return calcular(posto, mes, ref, atual, linhas, produtos, nomes, metas, proveniencia)
