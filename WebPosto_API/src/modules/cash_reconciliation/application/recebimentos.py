"""Seleciona apenas adquirentes ativas; falhas nao derrubam as demais etapas."""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from ..adapters.pagbank_edi import PagBankCredencialInvalida
from ..adapters.webposto_http import WebPostoErro
from ..config import carregar_unidades
from ..domain.models import AdquirenteConfigurada, SituacaoAdquirente
from ..domain.recebimentos import RecebimentoAdquirente, ResultadoRecebimentos
from .conciliar_cartoes import conciliar_pagbank

logger = logging.getLogger(__name__)
TIMEOUT_ETAPA = 180.0


async def conciliar_adquirente(
    empresa_codigo: int,
    dia: date,
    configurada: AdquirenteConfigurada,
    *,
    timeout: float = TIMEOUT_ETAPA,
) -> RecebimentoAdquirente:
    nome = configurada.nome
    if configurada.situacao is SituacaoAdquirente.PENDENTE:
        return RecebimentoAdquirente(adquirente=nome, situacao="pendente")
    if configurada.situacao is SituacaoAdquirente.CREDENCIAL_INVALIDA:
        return RecebimentoAdquirente(
            adquirente=nome, situacao="credencial inválida", erro="credencial inválida",
        )
    try:
        if nome != "PAGBANK":
            raise ValueError("Adquirente ativa sem adaptador.")
        resultado = await asyncio.wait_for(conciliar_pagbank(empresa_codigo, dia), timeout=timeout)
        if resultado.empresa_codigo != empresa_codigo or resultado.dia != dia or resultado.adquirente != nome:
            raise ValueError("Resultado fora do escopo solicitado.")
        return RecebimentoAdquirente.de_resultado(resultado)
    except PagBankCredencialInvalida:
        mensagem, situacao = "credencial inválida", "credencial inválida"
    except TimeoutError:
        mensagem, situacao = "tempo limite excedido", "erro"
    except WebPostoErro:
        mensagem, situacao = "falha ao consultar dados operacionais", "erro"
    except Exception as exc:
        # A etapa isola inclusive respostas malformadas; nunca registra corpo/URL da excecao.
        logger.warning(
            "Recebimentos unidade=%s adquirente=%s tipo=%s",
            empresa_codigo, nome, type(exc).__name__,
        )
        mensagem, situacao = "falha ao processar recebimentos", "erro"
    logger.warning("Recebimentos unidade=%s adquirente=%s situacao=%s", empresa_codigo, nome, situacao)
    return RecebimentoAdquirente(adquirente=nome, situacao=situacao, erro=mensagem)


async def conciliar_recebimentos(empresa_codigo: int, dia: date) -> ResultadoRecebimentos:
    unidade = carregar_unidades()[empresa_codigo]
    resultados = [
        await conciliar_adquirente(empresa_codigo, dia, adquirente)
        for adquirente in unidade.adquirentes
    ]
    return ResultadoRecebimentos(empresa_codigo=empresa_codigo, dia=dia, adquirentes=tuple(resultados))
