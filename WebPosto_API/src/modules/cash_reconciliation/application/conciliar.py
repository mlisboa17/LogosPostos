"""Caso de uso: conciliar sangrias de uma unidade contra extratos bancarios.

Fluxo direto: sangria com destino deposito_direto x depositos Bco24h do banco/terminal.
Fluxo cofre:  saldo diario = sangrias para cofre - depositos restantes do banco do cofre
              (a conta "CAIXA(POSTO)" do webPosto NAO e usada — ADR-002 item 5).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from ..adapters.ofx_reader import Extrato, ler_arquivo
from ..adapters.webposto_sangrias import FONTE, buscar_sangrias
from ..config import carregar_contas_compartilhadas, carregar_unidades
from ..domain.models import (
    Canal,
    ContaCompartilhada,
    DepositoBancario,
    Destino,
    DiaCofre,
    FluxoCofre,
    FluxoDireto,
    Proveniencia,
    ResultadoConciliacao,
    ResultadoContaCompartilhada,
    Sangria,
    TipoDestino,
    Unidade,
)
from ..rules.matching import VERSAO, Parametros, casar
from ..domain.tempo import agora


def _do_destino(d: DepositoBancario, destino: Destino) -> bool:
    return d.banco == destino.banco and (not destino.conta_sufixo or d.conta.endswith(destino.conta_sufixo))


def _terminal_ok(d: DepositoBancario, destino: Destino) -> bool:
    return not destino.terminais or (d.terminal or "") in destino.terminais


def _dias(sangrias: Iterable[Sangria], depositos: Iterable[DepositoBancario], inicio: date, fim: date) -> tuple[DiaCofre, ...]:
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
    return tuple(dias)


def _sem_destino(unidade: Unidade, s: Sangria) -> bool:
    return s.conta_codigo is None or unidade.destino(s.conta_codigo) is None


def _proveniencia(extratos: dict[str, Extrato]) -> Proveniencia:
    return Proveniencia(
        execucao_id=uuid.uuid4().hex,
        executado_em=agora(),
        versao_regra=VERSAO,
        fonte_sangrias=FONTE,
        extratos=tuple(f"{nome}:{e.sha256}" for nome, e in extratos.items()),
    )


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
        FluxoCofre(destino=destino, dias=_dias(
            [s for s in periodo if unidade.conta_efetiva(s) == destino.conta_codigo],
            [d for d in livres if _do_destino(d, destino) and d.data <= fim],
            inicio,
            fim,
        ))
        for destino in unidade.destinos
        if destino.tipo is TipoDestino.COFRE
    ]

    return ResultadoConciliacao(
        empresa_codigo=unidade.empresa_codigo,
        inicio=inicio,
        fim=fim,
        fluxos_diretos=tuple(diretos),
        fluxos_cofre=tuple(cofres),
        sangrias_sem_destino=tuple(s for s in periodo if _sem_destino(unidade, s)),
        sangrias_alteradas=tuple(s for s in periodo if s.alterada),
        proveniencia=_proveniencia(extratos),
    )


def conciliar_conta(
    conta: ContaCompartilhada,
    unidades: dict[int, Unidade],
    sangrias: Iterable[Sangria],
    extratos: dict[str, Extrato],
    inicio: date,
    fim: date,
) -> ResultadoContaCompartilhada:
    """Conta que recebe especie de varias unidades: soma os cofres de todas antes de comparar."""
    membros = [unidades[c] for c in conta.membros]
    cofre: list[Sangria] = []
    periodo: list[Sangria] = []
    for u in membros:
        da_unidade = [s for s in sangrias if s.empresa_codigo == u.empresa_codigo and inicio <= s.momento.date() <= fim]
        periodo += da_unidade
        for s in da_unidade:
            destino = u.destino(u.conta_efetiva(s))
            if destino and destino.tipo is TipoDestino.COFRE and destino.banco == conta.banco:
                cofre.append(s)
    depositos = [d for e in extratos.values() for d in e.depositos if d.banco == conta.banco and inicio <= d.data <= fim]
    por_unidade: dict[int, Decimal] = defaultdict(Decimal)
    for s in cofre:
        por_unidade[s.empresa_codigo] += s.valor
    sem_destino = [s for s in periodo if _sem_destino(unidades[s.empresa_codigo], s)]
    return ResultadoContaCompartilhada(
        conta=conta,
        inicio=inicio,
        fim=fim,
        dias=_dias(cofre, depositos, inicio, fim),
        entradas_por_unidade=tuple(sorted(por_unidade.items())),
        sangrias_sem_destino=tuple(sem_destino),
        sangrias_alteradas=tuple(s for s in periodo if s.alterada),
        proveniencia=_proveniencia(extratos),
    )


async def conciliar_unidade(empresa_codigo: int, inicio: date, fim: date, arquivos_ofx: Iterable[Path]) -> ResultadoConciliacao:
    unidade = carregar_unidades()[empresa_codigo]
    sangrias = await buscar_sangrias(unidade, inicio, fim)
    extratos = {Path(a).name: ler_arquivo(Path(a)) for a in arquivos_ofx}
    return conciliar(unidade, sangrias, extratos, inicio, fim)


async def conciliar_conta_compartilhada(nome: str, inicio: date, fim: date, arquivos_ofx: Iterable[Path]) -> ResultadoContaCompartilhada:
    conta = carregar_contas_compartilhadas()[nome]
    unidades = carregar_unidades()
    sangrias = [s for c in conta.membros for s in await buscar_sangrias(unidades[c], inicio, fim)]
    extratos = {Path(a).name: ler_arquivo(Path(a)) for a in arquivos_ofx}
    return conciliar_conta(conta, unidades, sangrias, extratos, inicio, fim)
