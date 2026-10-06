"""Casamento sangria x deposito bancario — SANGRIA_DEPOSITO_V1.

Passadas em ordem (cada sangria/deposito usado uma unica vez):
  1. exato      — mesmo valor, janela curta
  2. moedas     — deposito = sangria sem as moedas (terminal so aceita cedulas)
  3. soma       — 2..N sangrias depositadas de uma vez
  4. janela24h  — exato/moedas com janela ampliada
Evidencia: Doze Filial set/2026, deposito ocorre ~2 min antes do lancamento da sangria.
Mudou alguma regra? Crie nova VERSAO (ADR-002 item 4).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from itertools import combinations
from typing import Iterable

from ..domain.models import Casamento, DepositoBancario, Sangria

VERSAO = "SANGRIA_DEPOSITO_V1"


@dataclass(frozen=True)
class Parametros:
    janela_curta: timedelta = timedelta(hours=3)
    janela_ampla: timedelta = timedelta(hours=24)
    tolerancia_moedas: Decimal = Decimal("5")
    max_sangrias_soma: int = 3
    max_candidatos_soma: int = 20


def _na_janela(s: Sangria, d: DepositoBancario, janela: timedelta) -> bool:
    if d.momento is None:  # extrato sem hora: compara por dia (D ate D+janela)
        delta = (d.data - s.momento.date()).days
        return 0 <= delta <= max(1, janela.days)
    return abs(d.momento - s.momento) <= janela


def _distancia(s: Sangria, d: DepositoBancario) -> float:
    return abs((d.referencia - s.momento).total_seconds())


def _exato(valor_sangria: Decimal, d: DepositoBancario) -> bool:
    return abs(valor_sangria - d.valor) < Decimal("0.01")


def _moedas(valor_sangria: Decimal, d: DepositoBancario, p: Parametros) -> bool:
    return Decimal(0) <= valor_sangria - d.valor < p.tolerancia_moedas


def casar(
    sangrias: Iterable[Sangria],
    depositos: Iterable[DepositoBancario],
    p: Parametros = Parametros(),
) -> tuple[list[Casamento], list[Sangria], list[DepositoBancario]]:
    livres_s = sorted(sangrias, key=lambda s: (s.momento, s.codigo))
    livres_d = sorted(depositos, key=lambda d: (d.referencia, d.fitid))
    casamentos: list[Casamento] = []

    def um_para_um(regra: str, janela: timedelta, ok) -> None:
        for s in list(livres_s):
            cands = [d for d in livres_d if ok(s.valor, d) and _na_janela(s, d, janela)]
            if cands:
                d = min(cands, key=lambda d: _distancia(s, d))
                livres_s.remove(s)
                livres_d.remove(d)
                casamentos.append(Casamento(deposito=d, sangrias=(s,), regra=regra))

    um_para_um("exato", p.janela_curta, _exato)
    um_para_um("moedas", p.janela_curta, lambda v, d: _moedas(v, d, p))

    for d in list(livres_d):
        pool = sorted(
            (s for s in livres_s if _na_janela(s, d, p.janela_curta)),
            key=lambda s: _distancia(s, d),
        )[: p.max_candidatos_soma]
        achado = next(
            (
                comb
                for k in range(2, p.max_sangrias_soma + 1)
                for comb in combinations(pool, k)
                if _moedas(sum((s.valor for s in comb), Decimal(0)), d, p)
            ),
            None,
        )
        if achado:
            for s in achado:
                livres_s.remove(s)
            livres_d.remove(d)
            casamentos.append(Casamento(deposito=d, sangrias=tuple(achado), regra="soma"))

    um_para_um("janela24h", p.janela_ampla, lambda v, d: _moedas(v, d, p))
    return casamentos, livres_s, livres_d
