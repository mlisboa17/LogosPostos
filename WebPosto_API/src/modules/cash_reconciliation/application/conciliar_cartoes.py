"""Caso de uso: conciliar o dia de uma unidade com uma adquirente e investigar as sobras."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
import logging
from typing import Iterable

from ..adapters import pagbank_edi, premmia_portal
from ..adapters.webposto_cartoes import buscar_abastecimentos, buscar_cartoes, buscar_contexto_vendas
from ..config import carregar_unidades
from ..domain.cartoes import (
    Abastecimento,
    AlertaCartao,
    CartaoErp,
    ParProvavel,
    ResultadoCartoes,
    TransacaoAdquirente,
)
from ..domain.models import Proveniencia
from ..domain.tempo import agora, formatar_data_hora
from ..rules.cartoes import (
    VERSAO,
    _chave,
    agrupar_sobras,
    casar,
    candidato_pos,
    grupos_nsu_repetido,
    investigar,
    parear_sobras,
)
from ...webposto_integration.funcionarios import buscar_nomes_funcionarios
from ...webposto_integration.http import WebPostoErro

logger = logging.getLogger(__name__)

# administradoras do webPosto liquidadas por cada adquirente (V1/ADMINISTRADORAS)
ADMINISTRADORAS = {"PAGBANK": ("PAGSEGURO", "PIX PAGBANK"), "PREMMIA": ("PREMMIA",)}
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
    transacoes, cartoes = list(transacoes), list(cartoes)
    cancelados = [t for t in transacoes if t.situacao is not None]
    casados, sobra_t, sobra_c = casar(transacoes, cartoes)
    codigos_casados = {c.cartao.codigo for c in casados}
    alertas = []
    motivos_repetidos = {}
    for grupo in grupos_nsu_repetido(cartoes, transacoes):
        excedentes = [
            c for c in grupo[1:] if c.momento.date() == dia and c.codigo not in codigos_casados
        ]
        if not excedentes:
            continue
        primeiro = grupo[0]
        mensagem = "NSU/autorização repetido: " + " · ".join(
            f"venda {c.venda_codigo}, {formatar_data_hora(c.momento)}, R$ {c.valor:.2f}, "
            f"{c.responsavel}, tipoInclusao={c.tipo_inclusao or 'não informado'}"
            for c in grupo
        )
        alertas.append(
            AlertaCartao(
                codigo="CARTAO_NSU_REPETIDO",
                severidade="vermelho",
                mensagem=mensagem,
                valor=sum((c.valor for c in excedentes), Decimal(0)),
                cartoes=tuple(grupo),
            )
        )
        for c in excedentes:
            motivos_repetidos[c.codigo] = f"NSU já usado na venda {primeiro.venda_codigo}"
    for cartao in cartoes:
        if (
            cartao.momento.date() == dia
            and cartao.tipo_inclusao == "Manualmente"
            and not cartao.venda_codigo
        ):
            alertas.append(
                AlertaCartao(
                    codigo="CARTAO_MANUAL_SEM_VENDA",
                    severidade="laranja",
                    valor=cartao.valor,
                    cartoes=(cartao,),
                    mensagem=(
                        f"Lançamento manual sem venda: R$ {cartao.valor:.2f}, "
                        f"{formatar_data_hora(cartao.momento)}, {cartao.administradora} — "
                        f"{cartao.responsavel}; tipoInclusao=Manualmente"
                    ),
                )
            )
    for casamento in casados:
        if not casamento.valor_divergente or casamento.transacao.momento.date() != dia:
            continue
        menor = casamento.diferenca > 0
        alertas.append(
            AlertaCartao(
                codigo="CARTAO_VALOR_A_MENOR" if menor else "CARTAO_VALOR_A_MAIOR",
                severidade="vermelho" if menor else "laranja",
                mensagem=(
                    f"Lançado R$ {casamento.cartao.valor:.2f}, recebido R$ {casamento.transacao.valor:.2f}"
                    f" — {'faltam' if menor else 'sobram'} R$ {abs(casamento.diferenca):.2f} — "
                    f"{casamento.cartao.responsavel}; tipoInclusao={casamento.cartao.tipo_inclusao or 'não informado'}"
                ),
                valor=abs(casamento.diferenca),
                cartoes=(casamento.cartao,),
            )
        )
    sobras = []
    for c in sobra_c:
        motivo = motivos_repetidos.get(c.codigo)
        chaves = {_chave(k) for k in (c.nsu, c.nsu_tef, c.autorizacao) if _chave(k)}
        cancelamento = next(
            (
                t
                for t in cancelados
                if chaves & {_chave(k) for k in (t.nsu, t.autorizacao) if _chave(k)}
            ),
            None,
        )
        if not motivo and cancelamento:
            nome_adquirente = "Premmia" if adquirente == "PREMMIA" else "PagBank"
            rotulo = (
                f"{cancelamento.situacao} no {nome_adquirente}"
                if cancelamento.situacao in {"cancelada", "estornada", "ajuste"}
                else f"evento não aprovado no {nome_adquirente} ({cancelamento.situacao})"
            )
            motivo = f"{rotulo} em {formatar_data_hora(cancelamento.momento)}"
        if not motivo and adquirente == "PREMMIA":
            motivo = "Lançado no webPosto e não encontrado no portal Premmia"
        sobras.append(c.model_copy(update={"motivo": motivo}))
    abastecimentos = list(abastecimentos)
    a_maior = [
        investigar(t, abastecimentos, itens_em_dinheiro) for t in sobra_t if t.momento.date() == dia
    ]
    a_menor = [
        c
        for c in sobras
        if c.momento.date() == dia
        and (da_adquirente(c, adquirente) or c.codigo in motivos_repetidos)
    ]
    pares, grupos = [], []
    if adquirente != "PREMMIA":
        a_maior, a_menor, pares = parear_sobras(a_maior, a_menor)
        a_maior, a_menor, grupos = agrupar_sobras(a_maior, a_menor)
    else:
        for inv in list(a_maior):
            candidatos = [c for c in a_menor if candidato_pos(inv.transacao, c) and c.codigo not in motivos_repetidos]
            if candidatos:
                pares.extend(ParProvavel(investigacao=inv, cartao=c) for c in candidatos)
                a_maior.remove(inv)
        candidatos_provaveis = {p.cartao.codigo for p in pares}
        a_menor = [c for c in a_menor if c.codigo not in candidatos_provaveis]
    return ResultadoCartoes(
        empresa_codigo=empresa_codigo,
        adquirente=adquirente,
        dia=dia,
        casados=tuple(c for c in casados if c.transacao.momento.date() == dia),
        a_maior=tuple(a_maior),
        a_menor=tuple(a_menor),
        pares_provaveis=tuple(pares),
        grupos_provaveis=tuple(grupos),
        cancelados=tuple(t for t in cancelados if t.momento.date() == dia),
        alertas=tuple(alertas),
        proveniencia=Proveniencia(
            execucao_id=uuid.uuid4().hex,
            executado_em=agora(),
            versao_regra=VERSAO,
            fonte_sangrias="",
            extratos=(),
            outras_fontes=(
                "Premmia/planilha mensal" if adquirente == "PREMMIA" else pagbank_edi.FONTE,
                "webPosto/INTEGRACAO/V1/CARTOES",
                "webPosto/INTEGRACAO/V1/ABASTECIMENTOS",
                "webPosto/INTEGRACAO/V1/VENDAS/ITENS",
                "webPosto/INTEGRACAO/V1/VENDAS_FORMA_PAGAMENTO",
                "webPosto/INTEGRACAO/V1/VENDAS",
            ),
        ),
    )


async def coletar_contexto_cartoes(
    empresa_codigo: int, dia: date
) -> tuple[list[CartaoErp], list[Abastecimento], set[int]]:
    unidade = carregar_unidades()[empresa_codigo]
    antes, depois = dia - timedelta(days=1), dia + timedelta(days=1)
    cartoes = await buscar_cartoes(unidade, antes, depois)
    abastecimentos = await buscar_abastecimentos(unidade, antes, depois)
    contexto: dict[int, dict] = {}
    itens, pix = await buscar_contexto_vendas(
        unidade,
        antes,
        depois,
        contexto=contexto,
        abastecimentos=abastecimentos,
    )
    codigos = {a.frentista for a in abastecimentos if a.frentista is not None}
    codigos.update(
        item["frentista"] for item in contexto.values() if item.get("frentista") is not None
    )
    try:
        nomes = await buscar_nomes_funcionarios(unidade, antes, depois) if codigos else {}
    except WebPostoErro as exc:
        logger.warning("Nomes indisponíveis unidade=%s tipo=%s", empresa_codigo, type(exc).__name__)
        nomes = {}
    abastecimentos = [
        a.model_copy(update={"nome_frentista": nomes.get(a.frentista)}) for a in abastecimentos
    ]
    cartoes = [
        c.model_copy(
            update={
                **contexto.get(c.venda_codigo, {}),
                "nome_frentista": nomes.get(contexto.get(c.venda_codigo, {}).get("frentista")),
            }
        )
        for c in cartoes + pix
    ]
    return cartoes, abastecimentos, itens


async def conciliar_pagbank(empresa_codigo: int, dia: date) -> ResultadoCartoes:
    antes, depois = dia - timedelta(days=1), dia + timedelta(days=1)
    transacoes = [
        t
        for d in (antes, dia, depois)
        for t in await pagbank_edi.buscar_transacoes(empresa_codigo, d)
    ]
    cartoes, abastecimentos, itens = await coletar_contexto_cartoes(empresa_codigo, dia)
    if carregar_unidades()[empresa_codigo].premmia_ativo:
        cartoes = [c for c in cartoes if "PREMMIA" not in c.administradora.upper()]
    return conciliar(empresa_codigo, "PAGBANK", dia, transacoes, cartoes, abastecimentos, itens)


async def conciliar_premmia(empresa_codigo: int, dia: date) -> ResultadoCartoes:
    unidade = carregar_unidades()[empresa_codigo]
    transacoes = premmia_portal.buscar_transacoes(unidade, dia)
    cartoes, abastecimentos, itens = await coletar_contexto_cartoes(empresa_codigo, dia)
    cartoes = [c for c in cartoes if da_adquirente(c, "PREMMIA")]
    return conciliar(empresa_codigo, "PREMMIA", dia, transacoes, cartoes, abastecimentos, itens)


async def verificar_repetidos_premmia(empresa_codigo: int, dia: date) -> ResultadoCartoes:
    cartoes, abastecimentos, itens = await coletar_contexto_cartoes(empresa_codigo, dia)
    cartoes = [c for c in cartoes if "PREMMIA" in c.administradora.upper()]
    resultado = conciliar(empresa_codigo, "PAGBANK", dia, [], cartoes, abastecimentos, itens)
    return resultado.model_copy(
        update={
            "adquirente": "PREMMIA",
            "proveniencia": resultado.proveniencia.model_copy(
                update={
                    "outras_fontes": tuple(
                        fonte
                        for fonte in resultado.proveniencia.outras_fontes
                        if fonte != pagbank_edi.FONTE
                    ),
                }
            ),
        }
    )
