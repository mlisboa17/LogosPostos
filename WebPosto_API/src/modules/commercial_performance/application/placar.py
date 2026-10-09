from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from src.modules.webposto_integration.http import WebPostoErro
from src.modules.webposto_integration.tempo import agora, hoje

from ..adapters.persistencia import carregar_placar
from ..adapters.webposto import PATHS, buscar
from ..config import POSTOS, ler_metas
from ..domain.models import Frentista, MetasPosto, Mix, Placar, Proveniencia
from ..rules.placar import VERSAO, _niveis, calcular, primeiro_dia, referencia

logger = logging.getLogger(__name__)
TIMEOUT = 180
ZERO = Decimal(0)


class FonteIndisponivel(RuntimeError):
    pass


def _proveniencia(metas: MetasPosto | None) -> Proveniencia:
    return Proveniencia(
        executado_em=agora(),
        execucao_id=uuid.uuid4().hex,
        versao_regra=VERSAO,
        fontes=tuple(PATHS.values()),
        metas_cadastradas=metas is not None,
    )


def _percentual_combinado(
    litros_antigos: Decimal,
    percentual_antigo: Decimal | None,
    litros_novos: Decimal,
    percentual_novo: Decimal | None,
) -> Decimal | None:
    total = litros_antigos + litros_novos
    if total == 0:
        return ZERO
    if (litros_antigos > 0 and percentual_antigo is None) or (
        litros_novos > 0 and percentual_novo is None
    ):
        return None
    aditivados = litros_antigos * (percentual_antigo or ZERO) + litros_novos * (
        percentual_novo or ZERO
    )
    return aditivados / total


def _combinar_frentistas(
    anteriores: tuple[Frentista, ...],
    do_dia: tuple[Frentista, ...],
    metas: MetasPosto | None,
    dia: date,
    dias_mes: int,
) -> tuple[Frentista, ...]:
    antigos = {item.codigo: item for item in anteriores}
    novos = {item.codigo: item for item in do_dia}
    linhas = []
    for codigo in antigos.keys() | novos.keys():
        anterior = antigos.get(codigo)
        hoje_item = novos.get(codigo)
        litros_antigos = anterior.litros if anterior else ZERO
        litros_hoje = hoje_item.litros if hoje_item else ZERO
        litros = litros_antigos + litros_hoje
        atendimentos = (anterior.atendimentos if anterior else 0) + (
            hoje_item.atendimentos if hoje_item else 0
        )
        ticket = litros / atendimentos if atendimentos else None
        individual = (
            metas.frentistas.get(codigo) if metas is not None and codigo is not None else None
        )
        meta_ticket = individual.meta_ticket if individual else None
        linhas.append(
            Frentista(
                codigo=codigo,
                nome=(hoje_item.nome if hoje_item else None)
                or (anterior.nome if anterior else None),
                litros=litros,
                atendimentos=atendimentos,
                abastecimentos=(anterior.abastecimentos if anterior else 0)
                + (hoje_item.abastecimentos if hoje_item else 0),
                ticket=ticket,
                meta_ticket=meta_ticket,
                ganho_bico=(
                    meta_ticket - ticket if meta_ticket is not None and ticket is not None else None
                ),
                abaixo_meta=(
                    ticket < meta_ticket if ticket is not None and meta_ticket is not None else None
                ),
                impacto_projetado=(
                    Decimal(atendimentos) / dia.day * dias_mes * meta_ticket
                    if meta_ticket is not None
                    else None
                ),
                percentual_aditivado=_percentual_combinado(
                    litros_antigos,
                    anterior.percentual_aditivado if anterior else None,
                    litros_hoje,
                    hoje_item.percentual_aditivado if hoje_item else None,
                ),
                ranking_ticket=0,
                ranking_volume=0,
            )
        )
    ordem = lambda item: item.codigo if item.codigo is not None else -1
    por_ticket = sorted(linhas, key=lambda item: (-(item.ticket or ZERO), ordem(item)))
    por_volume = sorted(linhas, key=lambda item: (-item.litros, ordem(item)))
    ranking_volume = {item.codigo: indice for indice, item in enumerate(por_volume, start=1)}
    return tuple(
        item.model_copy(
            update={
                "ranking_ticket": indice,
                "ranking_volume": ranking_volume[item.codigo],
            }
        )
        for indice, item in enumerate(por_ticket, start=1)
    )


def _combinar_mix(
    anteriores: tuple[Mix, ...], do_dia: tuple[Mix, ...], acumulado: Decimal
) -> tuple[Mix, ...]:
    antigos = {item.produto: item for item in anteriores}
    novos = {item.produto: item for item in do_dia}
    resultado = []
    for codigo in antigos.keys() | novos.keys():
        anterior = antigos.get(codigo)
        hoje_item = novos.get(codigo)
        litros = (anterior.litros if anterior else ZERO) + (hoje_item.litros if hoje_item else ZERO)
        resultado.append(
            Mix(
                produto=codigo,
                nome=(hoje_item.nome if hoje_item else None)
                or (anterior.nome if anterior else None),
                aditivado=(
                    hoje_item.aditivado
                    if hoje_item and hoje_item.aditivado is not None
                    else anterior.aditivado if anterior else None
                ),
                litros=litros,
                percentual=litros / acumulado * 100 if acumulado else ZERO,
            )
        )
    return tuple(sorted(resultado, key=lambda item: item.produto))


def _combinar_com_hoje(
    anterior: Placar,
    placar_hoje: Placar,
    frentistas_ativos: int,
    metas: MetasPosto | None,
) -> Placar:
    dia = placar_hoje.dia
    dia_resultado = placar_hoje.diario[-1]
    acumulado_anterior = anterior.acumulado
    acumulado = acumulado_anterior + dia_resultado.litros
    niveis = _niveis(
        metas,
        acumulado,
        acumulado_anterior,
        dia_resultado.litros,
        placar_hoje.dias_mes,
        placar_hoje.dias_restantes,
        frentistas_ativos,
    )
    dia_resultado = dia_resultado.model_copy(
        update={
            "acumulado": acumulado,
            "niveis": niveis,
        }
    )
    dias = (*anterior.diario, dia_resultado)
    atendimentos = anterior.atendimentos + placar_hoje.atendimentos
    projecao = acumulado + acumulado / dia.day * placar_hoje.dias_restantes
    nivel_projetado = None
    if metas is not None:
        nivel_projetado = "abaixo_bronze"
        for nome in ("bronze", "prata", "ouro"):
            if projecao >= getattr(metas, nome):
                nivel_projetado = nome
    return Placar(
        posto=placar_hoje.posto,
        mes=placar_hoje.mes,
        dia=dia,
        parcial=placar_hoje.parcial,
        dias_mes=placar_hoje.dias_mes,
        dias_restantes=placar_hoje.dias_restantes,
        frentistas_ativos=frentistas_ativos,
        acumulado=acumulado,
        realizado_dia=dia_resultado.litros,
        atendimentos=atendimentos,
        abastecimentos=anterior.abastecimentos + placar_hoje.abastecimentos,
        atendimentos_fallback=anterior.atendimentos_fallback + placar_hoje.atendimentos_fallback,
        ticket=acumulado / atendimentos if atendimentos else None,
        projecao=projecao,
        nivel_projetado=nivel_projetado,
        percentual_aditivado=_percentual_combinado(
            anterior.acumulado,
            anterior.percentual_aditivado,
            dia_resultado.litros,
            placar_hoje.percentual_aditivado,
        ),
        niveis=niveis,
        diario=dias,
        frentistas=_combinar_frentistas(
            anterior.frentistas,
            placar_hoje.frentistas,
            metas,
            dia,
            placar_hoje.dias_mes,
        ),
        mix=_combinar_mix(anterior.mix, placar_hoje.mix, acumulado),
        proveniencia=placar_hoje.proveniencia,
    )


async def _placar_vivo(
    posto: int,
    mes: str,
    ref: date,
    atual: date,
    metas: MetasPosto | None,
) -> Placar:
    inicio = primeiro_dia(mes)
    try:
        linhas, produtos, nomes = await asyncio.wait_for(
            buscar(POSTOS[posto], inicio - timedelta(days=6), ref),
            TIMEOUT,
        )
    except (TimeoutError, WebPostoErro, ValueError, KeyError, TypeError) as exc:
        logger.warning("Fonte comercial indisponivel posto=%s tipo=%s", posto, type(exc).__name__)
        raise FonteIndisponivel("Fonte indisponivel. Tente novamente.") from None
    return calcular(posto, mes, ref, atual, linhas, produtos, nomes, metas, _proveniencia(metas))


async def obter_placar(posto: int, mes: str, dia: date | None = None) -> Placar:
    atual = hoje()
    ref = referencia(mes, atual, dia)
    metas_mes = ler_metas(mes)
    metas = metas_mes.postos.get(posto) if metas_mes else None

    if ref == atual:
        anterior = carregar_placar(posto, mes)
        if anterior is not None and anterior.dia == ref - timedelta(days=1):
            try:
                linhas, produtos, nomes = await asyncio.wait_for(
                    buscar(POSTOS[posto], ref - timedelta(days=6), ref),
                    TIMEOUT,
                )
                ultimos_dias = [
                    linha
                    for linha in linhas
                    if ref - timedelta(days=6) <= linha.momento.date() <= ref
                ]
                linhas_hoje = [linha for linha in ultimos_dias if linha.momento.date() == ref]
                placar_hoje = calcular(
                    posto,
                    mes,
                    ref,
                    atual,
                    linhas_hoje,
                    produtos,
                    nomes,
                    metas,
                    _proveniencia(metas),
                )
                ativos = len(
                    {linha.frentista for linha in ultimos_dias if linha.frentista is not None}
                )
                return _combinar_com_hoje(anterior, placar_hoje, ativos, metas)
            except (TimeoutError, WebPostoErro, ValueError, KeyError, TypeError) as exc:
                logger.warning(
                    "Fonte comercial indisponivel posto=%s tipo=%s", posto, type(exc).__name__
                )
                raise FonteIndisponivel("Fonte indisponivel. Tente novamente.") from None
    elif ref < atual:
        anterior = carregar_placar(posto, mes)
        if anterior is not None and anterior.dia == ref:
            return anterior

    return await _placar_vivo(posto, mes, ref, atual, metas)
