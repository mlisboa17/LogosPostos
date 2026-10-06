"""Caso de uso: conciliar sangrias de uma unidade contra extratos bancarios.

Fluxo direto: sangria com destino deposito_direto x depositos Bco24h do banco/terminal.
Fluxo cofre:  saldo diario = sangrias para cofre - depositos restantes do banco do cofre
              (a conta "CAIXA(POSTO)" do webPosto NAO e usada — ADR-002 item 5).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from ..adapters.ofx_reader import Extrato, ler_arquivo
from ..adapters.webposto_sangrias import FONTE, buscar_sangrias
from ..config import carregar_unidades
from ..domain.models import (
    Canal,
    DepositoBancario,
    Destino,
    DiaCofre,
    FluxoCofre,
    FluxoDireto,
    Proveniencia,
    ResultadoConciliacao,
    Sangria,
    TipoDestino,
    Unidade,
)
from ..rules.matching import VERSAO, Parametros, casar


def _do_destino(d: DepositoBancario, destino: Destino) -> bool:
    return d.banco == destino.banco and (not destino.conta_sufixo or d.conta.endswith(destino.conta_sufixo))


def _terminal_ok(d: DepositoBancario, destino: Destino) -> bool:
    return not destino.terminais or (d.terminal or "") in destino.terminais


def _fluxo_cofre(destino: Destino, sangrias: list[Sangria], depositos: list[DepositoBancario], inicio: date, fim: date) -> FluxoCofre:
    entradas: dict[date, Decimal] = defaultdict(Decimal)
    saidas: dict[date, Decimal] = defaultdict(Decimal)
    for s in sangrias:
        entradas[s.momento.date()] += s.valor
    for d in depositos:
        saidas[d.data] += d.valor
    dias, saldo, dia = [], Decimal(0), inicio
    while dia <= fim:
        saldo += entradas[dia] - saidas[dia]
        dias.append(DiaCofre(dia=dia, entradas=entradas[dia], depositos=saidas[dia], saldo=saldo))
        dia += timedelta(days=1)
    return FluxoCofre(destino=destino, dias=tuple(dias))


def conciliar(
    unidade: Unidade,
    sangrias: Iterable[Sangria],
    extratos: dict[str, Extrato],
    inicio: date,
    fim: date,
    parametros: Parametros = Parametros(),
) -> ResultadoConciliacao:
    periodo = [
        s for s in sangrias
        if s.empresa_codigo == unidade.empresa_codigo and inicio <= s.momento.date() <= fim
    ]
    livres = [
        d for e in extratos.values() for d in e.depositos if inicio <= d.data <= fim + timedelta(days=1)
    ]

    diretos = []
    for destino in (d for d in unidade.destinos if d.tipo is TipoDestino.DEPOSITO_DIRETO):
        cands = [d for d in livres if _do_destino(d, destino) and d.canal is Canal.BCO24H and _terminal_ok(d, destino)]
        casados, sem_dep, sem_sang = casar([s for s in periodo if unidade.conta_efetiva(s) == destino.conta_codigo], cands, parametros)
        usados = {c.deposito.fitid for c in casados}
        livres = [d for d in livres if d.fitid not in usados]
        diretos.append(FluxoDireto(destino=destino, casamentos=tuple(casados),
                                   sangrias_sem_deposito=tuple(sem_dep), depositos_sem_sangria=tuple(sem_sang)))

    cofres = [
        _fluxo_cofre(
            destino,
            [s for s in periodo if unidade.conta_efetiva(s) == destino.conta_codigo],
            [d for d in livres if _do_destino(d, destino) and d.data <= fim],
            inicio,
            fim,
        )
        for destino in unidade.destinos
        if destino.tipo is TipoDestino.COFRE
    ]

    return ResultadoConciliacao(
        empresa_codigo=unidade.empresa_codigo,
        inicio=inicio,
        fim=fim,
        fluxos_diretos=tuple(diretos),
        fluxos_cofre=tuple(cofres),
        sangrias_sem_destino=tuple(s for s in periodo if unidade.destino(s.conta_codigo) is None),
        sangrias_alteradas=tuple(s for s in periodo if s.alterada),
        proveniencia=Proveniencia(
            execucao_id=uuid.uuid4().hex,
            executado_em=datetime.now(),
            versao_regra=VERSAO,
            fonte_sangrias=FONTE,
            extratos=tuple(f"{nome}:{e.sha256}" for nome, e in extratos.items()),
        ),
    )


async def conciliar_unidade(empresa_codigo: int, inicio: date, fim: date, arquivos_ofx: Iterable[Path]) -> ResultadoConciliacao:
    unidade = carregar_unidades()[empresa_codigo]
    sangrias = await buscar_sangrias(unidade, inicio, fim)
    extratos = {Path(a).name: ler_arquivo(Path(a)) for a in arquivos_ofx}
    return conciliar(unidade, sangrias, extratos, inicio, fim)
