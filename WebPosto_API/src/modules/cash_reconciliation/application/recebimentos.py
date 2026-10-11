"""Seleciona apenas adquirentes ativas; falhas nao derrubam as demais etapas."""
from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import date

from ..adapters.pagbank_edi import PagBankCredencialInvalida
from ..adapters.premmia_portal import PremmiaDiaNaoColetado, PremmiaVerificacaoHumana
from ..adapters.webposto_http import WebPostoErro
from ..config import carregar_unidades
from ..domain.models import AdquirenteConfigurada, SituacaoAdquirente
from ..domain.recebimentos import RecebimentoAdquirente, ResultadoRecebimentos
from ..domain.acoes_recebimentos import ConferenciaRecebimentos
from .conciliar_cartoes import conciliar_pagbank, conciliar_premmia, verificar_repetidos_premmia

logger = logging.getLogger(__name__)
TIMEOUT_ETAPA = 180.0


async def conciliar_adquirente(
    empresa_codigo: int,
    dia: date,
    configurada: AdquirenteConfigurada,
    *,
    timeout: float = TIMEOUT_ETAPA,
    aviso_premmia: str | None = None,
) -> RecebimentoAdquirente:
    nome = configurada.nome
    if nome == "PREMMIA" and aviso_premmia:
        return RecebimentoAdquirente(adquirente=nome, situacao="pendente", erro=aviso_premmia)
    if nome == "PREMMIA" and configurada.situacao is SituacaoAdquirente.PENDENTE:
        unidade = carregar_unidades().get(empresa_codigo)
        if unidade and any(
            a.nome == "PAGBANK" and a.situacao is SituacaoAdquirente.ATIVO
            for a in unidade.adquirentes
        ):
            return RecebimentoAdquirente(adquirente=nome, situacao="pendente")
    if configurada.situacao is SituacaoAdquirente.PENDENTE and nome != "PREMMIA":
        return RecebimentoAdquirente(adquirente=nome, situacao="pendente")
    if configurada.situacao is SituacaoAdquirente.CREDENCIAL_INVALIDA:
        return RecebimentoAdquirente(
            adquirente=nome, situacao="credencial inválida", erro="credencial inválida",
        )
    try:
        if nome == "PREMMIA" and configurada.situacao is SituacaoAdquirente.PENDENTE:
            resultado = await asyncio.wait_for(
                verificar_repetidos_premmia(empresa_codigo, dia),
                timeout=timeout,
            )
            return RecebimentoAdquirente(
                adquirente=nome,
                situacao="pendente",
                alertas=resultado.alertas,
                a_menor=resultado.a_menor,
                proveniencia=resultado.proveniencia,
            )
        if nome == "PREMMIA":
            if not carregar_unidades()[empresa_codigo].premmia_ativo:
                return RecebimentoAdquirente(adquirente=nome, situacao="pendente")
            executar = conciliar_premmia
        elif nome == "PAGBANK":
            executar = conciliar_pagbank
        else:
            raise ValueError("Adquirente ativa sem adaptador.")
        resultado = await asyncio.wait_for(executar(empresa_codigo, dia), timeout=timeout)
        if resultado.empresa_codigo != empresa_codigo or resultado.dia != dia or resultado.adquirente != nome:
            raise ValueError("Resultado fora do escopo solicitado.")
        return RecebimentoAdquirente.de_resultado(resultado)
    except PagBankCredencialInvalida:
        mensagem, situacao = "credencial inválida", "credencial inválida"
    except PremmiaVerificacaoHumana as exc:
        mensagem, situacao = str(exc), "pendente"
    except PremmiaDiaNaoColetado as exc:
        mensagem, situacao = str(exc), "pendente"
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


def conferencia_gravada(empresa_codigo: int, inicio: date, fim: date) -> ConferenciaRecebimentos:
    """Le o mes para reincidencia; nao consulta fontes nem grava decisoes."""
    from datetime import timedelta
    from ..adapters.persistencia import carregar_dia
    from ..adapters.pendencias import eventos_recebimentos
    from ..adapters.webposto_cartoes import ler_pix_cnpj_gravado
    from .classificar_recebimentos import montar_conferencia

    if fim < inicio or (fim - inicio).days > 30:
        raise ValueError("O período deve conter no máximo 31 dias.")
    primeiro = inicio.replace(day=1)
    ultimo = fim.replace(day=calendar.monthrange(fim.year, fim.month)[1])
    registros = [
        r for indice in range((ultimo - primeiro).days + 1)
        if (r := carregar_dia(empresa_codigo, primeiro + timedelta(days=indice))) is not None
    ]
    registros = [
        r.model_copy(update={"recebimentos": r.recebimentos.model_copy(update={"adquirentes": tuple(
            a.model_copy(update={"sem_fonte": tuple({
                c.codigo: c for c in (*a.sem_fonte, *ler_pix_cnpj_gravado(empresa_codigo, r.dia))
            }.values())}) if a.adquirente == "PAGBANK" else a
            for a in r.recebimentos.adquirentes
        )})}) for r in registros
    ]
    return montar_conferencia(empresa_codigo, inicio, fim, registros, eventos_recebimentos(empresa_codigo))
