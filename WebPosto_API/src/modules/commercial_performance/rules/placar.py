"""PLACAR_V1: calendario de Recife; hoje parcial ate a meia-noite."""
from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from ..domain.models import (
    Abastecimento, Dia, Frentista, MetasPosto, Mix, Nivel, Placar, Produto, Proveniencia,
)

VERSAO = "PLACAR_V1"
ZERO = Decimal(0)


def primeiro_dia(mes: str) -> date:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
        raise ValueError("Mes invalido. Use aaaa-mm.")
    try:
        return date.fromisoformat(f"{mes}-01")
    except ValueError:
        raise ValueError("Mes invalido. Use aaaa-mm.") from None


def referencia(mes: str, hoje: date, dia: date | None = None) -> date:
    inicio = primeiro_dia(mes)
    fim = inicio.replace(day=calendar.monthrange(inicio.year, inicio.month)[1])
    valor = dia if dia is not None else min(hoje, fim)
    if valor < inicio or valor > fim or valor > hoje:
        raise ValueError("Dia deve pertencer ao mes e nao pode estar no futuro.")
    return valor


def _litros(linhas: Iterable[Abastecimento]) -> Decimal:
    return sum((a.litros for a in linhas), ZERO)


def _atendimentos(linhas: Iterable[Abastecimento]) -> int:
    return len({("venda", a.venda) if a.venda is not None else ("abastecimento", a.codigo) for a in linhas})


def _percentual_aditivado(linhas: list[Abastecimento], produtos: dict[int, Produto]) -> Decimal | None:
    if any(a.produto not in produtos for a in linhas):
        return None
    total = _litros(linhas)
    return _litros(a for a in linhas if produtos[a.produto].aditivado) / total * 100 if total else ZERO


def _niveis(
    metas: MetasPosto | None, acumulado: Decimal, anterior: Decimal, realizado: Decimal,
    dias_mes: int, restantes: int, ativos: int,
) -> dict[str, Nivel]:
    if metas is None:
        return {}
    resultado = {}
    for nome in ("bronze", "prata", "ouro"):
        meta = getattr(metas, nome)
        media = meta / dias_mes
        viva = max(ZERO, meta - anterior) / restantes if restantes else None
        resultado[nome] = Nivel(
            meta=meta, percentual=acumulado / meta * 100,
            faltante=max(ZERO, meta - acumulado), media_exigida=media,
            meta_viva=viva, meta_viva_frentista=viva / ativos if viva is not None and ativos else None,
            status_media="acima" if realizado >= media else "abaixo",
            status_viva=("acima" if realizado >= viva else "abaixo") if viva is not None else None,
        )
    return resultado


def calcular(
    posto: int, mes: str, dia: date, hoje: date, abastecimentos: Iterable[Abastecimento],
    produtos: dict[int, Produto], funcionarios: dict[int, str], metas: MetasPosto | None,
    proveniencia: Proveniencia,
) -> Placar:
    referencia(mes, hoje, dia)
    inicio = primeiro_dia(mes)
    dias_mes = calendar.monthrange(dia.year, dia.month)[1]
    todos = [a for a in abastecimentos if a.empresa_codigo == posto and a.momento.date() <= dia]
    codigos = [a.codigo for a in todos]
    if len(codigos) != len(set(codigos)):
        raise ValueError("Abastecimentos duplicados na fonte.")
    mes_linhas = [a for a in todos if a.momento.date() >= inicio]
    ativos = len({a.frentista for a in todos if a.frentista is not None and a.momento.date() >= dia - timedelta(days=6)})
    por_dia: dict[date, list[Abastecimento]] = defaultdict(list)
    por_frentista: dict[int | None, list[Abastecimento]] = defaultdict(list)
    por_produto: dict[int, list[Abastecimento]] = defaultdict(list)
    for a in mes_linhas:
        por_dia[a.momento.date()].append(a)
        por_frentista[a.frentista].append(a)
        por_produto[a.produto].append(a)
    diario = []
    acumulado = ZERO
    for numero in range(1, dia.day + 1):
        data = inicio.replace(day=numero)
        realizado = _litros(por_dia[data])
        anterior = acumulado
        acumulado += realizado
        fechado = data < hoje
        restantes = dias_mes - numero + (0 if fechado else 1)
        ativos_dia = len({a.frentista for a in todos if a.frentista is not None and data - timedelta(days=6) <= a.momento.date() <= data})
        diario.append(Dia(
            dia=data, litros=realizado, acumulado=acumulado,
            atendimentos=_atendimentos(por_dia[data]), abastecimentos=len(por_dia[data]),
            fechado=fechado, niveis=_niveis(metas, acumulado, anterior, realizado, dias_mes, restantes, ativos_dia),
        ))
    restantes = dias_mes - dia.day + (1 if dia == hoje else 0)
    projecao = acumulado + acumulado / dia.day * restantes
    nivel_projetado = None
    if metas is not None:
        for nome in ("bronze", "prata", "ouro"):
            if projecao >= getattr(metas, nome):
                nivel_projetado = nome
        if nivel_projetado is None:
            nivel_projetado = "abaixo_bronze"
    frentistas = []
    for codigo, linhas in por_frentista.items():
        litros = _litros(linhas)
        atendimentos = _atendimentos(linhas)
        ticket = litros / atendimentos if atendimentos else None
        individual = metas.frentistas.get(codigo) if metas is not None and codigo is not None else None
        meta_ticket = individual.meta_ticket if individual else None
        frentistas.append(Frentista(
            codigo=codigo, nome=funcionarios.get(codigo) if codigo is not None else None,
            litros=litros, atendimentos=atendimentos, abastecimentos=len(linhas), ticket=ticket,
            meta_ticket=meta_ticket, ganho_bico=meta_ticket - ticket if meta_ticket is not None and ticket is not None else None,
            abaixo_meta=ticket < meta_ticket if ticket is not None and meta_ticket is not None else None,
            impacto_projetado=Decimal(atendimentos) / dia.day * dias_mes * meta_ticket if meta_ticket is not None else None,
            percentual_aditivado=_percentual_aditivado(linhas, produtos), ranking_ticket=0, ranking_volume=0,
        ))
    ordem = lambda f: f.codigo if f.codigo is not None else -1
    ticket_ordem = sorted(frentistas, key=lambda f: (-(f.ticket or ZERO), ordem(f)))
    volume_ordem = sorted(frentistas, key=lambda f: (-f.litros, ordem(f)))
    rankings_ticket = {f.codigo: i + 1 for i, f in enumerate(ticket_ordem)}
    rankings_volume = {f.codigo: i + 1 for i, f in enumerate(volume_ordem)}
    frentistas = [f.model_copy(update={
        "ranking_ticket": rankings_ticket[f.codigo], "ranking_volume": rankings_volume[f.codigo],
    }) for f in ticket_ordem]
    atendimentos = _atendimentos(mes_linhas)
    return Placar(
        posto=posto, mes=mes, dia=dia, parcial=dia == hoje, dias_mes=dias_mes, dias_restantes=restantes,
        frentistas_ativos=ativos, acumulado=acumulado, realizado_dia=diario[-1].litros,
        atendimentos=atendimentos, abastecimentos=len(mes_linhas),
        atendimentos_fallback=sum(a.venda is None for a in mes_linhas),
        ticket=acumulado / atendimentos if atendimentos else None,
        projecao=projecao, nivel_projetado=nivel_projetado,
        percentual_aditivado=_percentual_aditivado(mes_linhas, produtos),
        niveis=diario[-1].niveis, diario=tuple(diario), frentistas=tuple(frentistas),
        mix=tuple(Mix(
            produto=codigo, nome=produtos[codigo].nome if codigo in produtos else None,
            aditivado=produtos[codigo].aditivado if codigo in produtos else None,
            litros=_litros(linhas), percentual=_litros(linhas) / acumulado * 100 if acumulado else ZERO,
        ) for codigo, linhas in sorted(por_produto.items())),
        proveniencia=proveniencia,
    )
