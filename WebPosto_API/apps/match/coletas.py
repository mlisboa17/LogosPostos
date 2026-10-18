"""Coleta Premmia/PagBank por posto e comparação com o webPosto.

Quem chama deve ter rodado `unidades.ativar(con)` (resolvedor de segredos e provedor de unidades).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from apps.match import banco, caminhos, credenciais, explicar, unidades
from src.modules.cash_reconciliation.adapters import pagbank_edi, premmia_portal
from src.modules.cash_reconciliation.application import conciliar_cartoes

logger = logging.getLogger(__name__)

_FONTES = ("premmia", "pagbank_edi")
_NOME = {"premmia": "Premmia", "pagbank_edi": "PagBank"}
_JA_COLETADO = ("ok", "sem_movimento")


@dataclass
class ResultadoFonte:
    posto_id: int
    fonte: str
    dia: date
    situacao: str  # ok | sem_movimento | erro | verificacao_humana | sem_comparacao
    qtd: int
    total: Decimal
    mensagem: str
    divergencias: list[dict] = field(default_factory=list)


def _tem_chave_webposto(posto, fontes: dict) -> bool:
    wp = fontes.get("webposto")
    return bool(wp and wp["ativo"] and posto["empresa_codigo_webposto"] is not None
                and credenciais.tem(f"{posto['id']}/webposto/chave"))


def _ja_coletado(con, fonte_id: int, dia: date) -> bool:
    row = con.execute("SELECT situacao FROM coleta WHERE fonte_id=? AND dia=?",
                      (fonte_id, str(dia))).fetchone()
    return bool(row and row["situacao"] in _JA_COLETADO)


async def _premmia(unidade, posto_id: int, dia: date, visivel: bool, comparar: bool):
    diretorio = caminhos.premmia(posto_id)
    if visivel:
        premmia_portal.liberar_nova_tentativa(unidade, diretorio)
    await premmia_portal.coletar(unidade, ate=dia, visivel=visivel, diretorio=diretorio)
    transacoes = premmia_portal.buscar_transacoes(unidade, dia, diretorio)
    if not comparar:
        return transacoes, None
    emp = unidade.empresa_codigo
    cartoes, abastecimentos, itens = await conciliar_cartoes.coletar_contexto_cartoes(emp, dia)
    cartoes = [c for c in cartoes
               if conciliar_cartoes.da_adquirente(c, "PREMMIA", unidade.administradoras)]
    return transacoes, conciliar_cartoes.conciliar(
        emp, "PREMMIA", dia, transacoes, cartoes, abastecimentos, itens)


async def _pagbank(unidade, dia: date, comparar: bool):
    emp = unidade.empresa_codigo
    do_dia = await pagbank_edi.buscar_transacoes(emp, dia)
    if not comparar:
        return do_dia, None
    vizinhos = [t for d in (dia - timedelta(days=1), dia + timedelta(days=1))
                for t in await pagbank_edi.buscar_transacoes(emp, d)]
    cartoes, abastecimentos, itens = await conciliar_cartoes.coletar_contexto_cartoes(emp, dia)
    if unidade.premmia_ativo:
        cartoes = [c for c in cartoes if "PREMMIA" not in c.administradora.upper()]
    return do_dia, conciliar_cartoes.conciliar(
        emp, "PAGBANK", dia, do_dia + vizinhos, cartoes, abastecimentos, itens)


def _mensagem(nome: str, qtd: int, total: Decimal, comparou: bool, n_div: int) -> str:
    if qtd == 0:
        base = f"{nome}: dia sem vendas registradas."
    else:
        base = f"{nome}: {qtd} venda(s), {explicar.dinheiro(total)}."
    if not comparou:
        return base + " Sem comparação com o webPosto (cadastre a chave do webPosto em Fontes do posto)."
    if n_div == 0:
        return base + " Tudo confere com o webPosto."
    return base + f" {n_div} divergência(s) com o webPosto."


async def _coletar_fonte(con, posto, fonte, unidade, dia, visivel, comparar) -> ResultadoFonte:
    tipo, posto_id = fonte["tipo"], posto["id"]
    try:
        if tipo == "premmia":
            transacoes, resultado = await _premmia(unidade, posto_id, dia, visivel, comparar)
        else:
            transacoes, resultado = await _pagbank(unidade, dia, comparar)
    except premmia_portal.PremmiaVerificacaoHumana as exc:
        situacao, mensagem = "verificacao_humana", explicar.erro_pt(exc)
    except Exception as exc:  # cada fonte isolada: falha numa não para as outras
        logger.warning("Coleta falhou posto=%s fonte=%s tipo=%s", posto_id, tipo, type(exc).__name__)
        situacao, mensagem = "erro", explicar.erro_pt(exc)
    else:
        do_dia = [t for t in transacoes if t.momento.date() == dia]
        total = sum((t.valor for t in do_dia if t.situacao is None), Decimal(0))
        itens = explicar.divergencias(resultado) if resultado is not None else []
        situacao_coleta = "ok" if do_dia else "sem_movimento"
        coleta_id = banco.registrar_coleta(con, fonte["id"], dia, situacao_coleta, len(do_dia), total, None)
        banco.gravar_transacoes(con, coleta_id, posto_id, tipo, do_dia)
        if resultado is not None:
            banco.gravar_divergencias(con, posto_id, dia, tipo, itens)
        # coleta.situacao não aceita 'sem_comparacao': fica 'ok' no banco, só o resultado informa
        situacao = situacao_coleta if (resultado is not None or not do_dia) else "sem_comparacao"
        return ResultadoFonte(posto_id, tipo, dia, situacao, len(do_dia), total,
                              _mensagem(_NOME[tipo], len(do_dia), total, resultado is not None,
                                        len(itens)), itens)
    banco.registrar_coleta(con, fonte["id"], dia, situacao, 0, Decimal(0), mensagem)
    return ResultadoFonte(posto_id, tipo, dia, situacao, 0, Decimal(0), mensagem, [])


async def coletar_posto(con, posto_id: int, dia: date, *, visivel: bool = False,
                        so_falhas: bool = False) -> list[ResultadoFonte]:
    posto = con.execute("SELECT * FROM posto WHERE id=?", (posto_id,)).fetchone()
    fontes = {f["tipo"]: f for f in banco.fontes_do_posto(con, posto_id)}
    comparar = _tem_chave_webposto(posto, fontes)
    unidade = unidades.montar(con)[unidades.codigo_empresa(posto)]
    resultados = []
    for tipo in _FONTES:
        fonte = fontes.get(tipo)
        if not fonte or not fonte["ativo"]:
            continue
        if so_falhas and _ja_coletado(con, fonte["id"], dia):
            continue
        resultados.append(await _coletar_fonte(con, posto, fonte, unidade, dia, visivel, comparar))
    return resultados


async def coletar_todos(con, dia: date, *, so_falhas: bool = False) -> list[ResultadoFonte]:
    resultados = []
    for posto in banco.listar_postos(con):
        resultados.extend(await coletar_posto(con, posto["id"], dia, so_falhas=so_falhas))
    return resultados
