"""Caso de uso: conciliar o dia de uma unidade com uma adquirente e investigar as sobras."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Iterable

from ..adapters import pagbank_edi
from ..adapters.webposto_cartoes import buscar_abastecimentos, buscar_cartoes, buscar_contexto_vendas
from ..config import carregar_unidades
from ..domain.cartoes import Abastecimento, CartaoErp, ResultadoCartoes, TransacaoAdquirente
from ..domain.models import Proveniencia
from ..domain.tempo import agora
from ..rules.cartoes import VERSAO, casar, investigar, parear_sobras

# administradoras do webPosto liquidadas por cada adquirente (V1/ADMINISTRADORAS)
ADMINISTRADORAS = {"PAGBANK": ("PAGSEGURO", "PIX PAGBANK")}
# casamento usa TODOS os recebimentos do ERP (ex.: AMEX da maquininha PagBank cadastrado com outro nome);
# o filtro por administradora so define o que e cobrado como "a menor".


def da_adquirente(c: CartaoErp, adquirente: str) -> bool:
    nome = c.administradora.upper()
    return any(p in nome for p in ADMINISTRADORAS[adquirente])


def conciliar(
    empresa_codigo: int,
    adquirente: str,
    dia: date,
    transacoes: Iterable[TransacaoAdquirente],
    cartoes: Iterable[CartaoErp],
    abastecimentos: Iterable[Abastecimento],
    itens_em_dinheiro: set[int],
) -> ResultadoCartoes:
    """transacoes e cartoes podem cobrir D-1..D+1 (virada do dia); o relatorio e so do dia D."""
    casados, sobra_t, sobra_c = casar(transacoes, cartoes)
    abastecimentos = list(abastecimentos)
    a_maior, a_menor, pares = parear_sobras(
        (investigar(t, abastecimentos, itens_em_dinheiro) for t in sobra_t if t.momento.date() == dia),
        (c for c in sobra_c if c.momento.date() == dia and da_adquirente(c, adquirente)),
    )
    return ResultadoCartoes(
        empresa_codigo=empresa_codigo,
        adquirente=adquirente,
        dia=dia,
        casados=tuple(c for c in casados if c.transacao.momento.date() == dia),
        a_maior=tuple(a_maior),
        a_menor=tuple(a_menor),
        pares_provaveis=tuple(pares),
        proveniencia=Proveniencia(
            execucao_id=uuid.uuid4().hex,
            executado_em=agora(),
            versao_regra=VERSAO,
            fonte_sangrias="",
            extratos=(),
            outras_fontes=(pagbank_edi.FONTE, "webPosto/INTEGRACAO/V1/CARTOES",
                           "webPosto/INTEGRACAO/V1/ABASTECIMENTOS", "webPosto/INTEGRACAO/V1/VENDAS/ITENS",
                           "webPosto/INTEGRACAO/V1/VENDAS_FORMA_PAGAMENTO", "webPosto/INTEGRACAO/V1/VENDAS"),
        ),
    )


async def conciliar_pagbank(empresa_codigo: int, dia: date) -> ResultadoCartoes:
    unidade = carregar_unidades()[empresa_codigo]
    antes, depois = dia - timedelta(days=1), dia + timedelta(days=1)
    transacoes = [t for d in (antes, dia, depois) for t in await pagbank_edi.buscar_transacoes(empresa_codigo, d)]
    cartoes = await buscar_cartoes(unidade, antes, depois)
    abastecimentos = await buscar_abastecimentos(unidade, antes, dia)
    itens, pix = await buscar_contexto_vendas(unidade, antes, depois)
    return conciliar(empresa_codigo, "PAGBANK", dia, transacoes, cartoes + pix, abastecimentos, itens)
