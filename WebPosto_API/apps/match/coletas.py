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


class _AdquirenteSemVendasAinda(Exception):
    """Adquirente vazia no dia mas webPosto com cartões dela: arquivo provavelmente não publicado."""

    def __init__(self, nome: str, dia: date):
        super().__init__(
            f"O {nome} ainda não mostra vendas de {dia:%d/%m/%Y}, mas o webPosto tem cartões"
            " lançados. Nova tentativa na repescagem.")


def _exigir_vendas(transacoes_do_dia, cartoes, dia: date, nome: str) -> None:
    if not transacoes_do_dia and any(c.momento.date() == dia for c in cartoes):
        raise _AdquirenteSemVendasAinda(nome, dia)


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
    _exigir_vendas([t for t in transacoes if t.momento.date() == dia], cartoes, dia, "Premmia")
    return transacoes, conciliar_cartoes.conciliar(
        emp, "PREMMIA", dia, transacoes, cartoes, abastecimentos, itens)


async def _pagbank(unidade, dia: date, comparar: bool):
    emp = unidade.empresa_codigo
    do_dia = await pagbank_edi.buscar_transacoes(emp, dia)
    if not comparar:
        return do_dia, None
    cartoes, abastecimentos, itens = await conciliar_cartoes.coletar_contexto_cartoes(emp, dia)
    if unidade.premmia_ativo:
        cartoes = [c for c in cartoes if "PREMMIA" not in c.administradora.upper()]
    _exigir_vendas(
        [t for t in do_dia if t.momento.date() == dia],
        [c for c in cartoes if conciliar_cartoes.da_adquirente(c, "PAGBANK", unidade.administradoras)],
        dia, "PagBank")
    vizinhos = [t for d in (dia - timedelta(days=1), dia + timedelta(days=1))
                for t in await pagbank_edi.buscar_transacoes(emp, d)]
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
    except premmia_portal.PremmiaVerificacaoHumana as exc:
        situacao, mensagem = "verificacao_humana", explicar.erro_pt(exc)
    except _AdquirenteSemVendasAinda as exc:
        situacao, mensagem = "erro", str(exc)
    except Exception as exc:  # cada fonte isolada: falha numa não para as outras
        logger.warning("Coleta falhou posto=%s fonte=%s tipo=%s", posto_id, tipo, type(exc).__name__)
        situacao, mensagem = "erro", explicar.erro_pt(exc)
    con.rollback()
    banco.registrar_coleta(con, fonte["id"], dia, situacao, 0, Decimal(0), mensagem)
    banco.gravar_divergencias(con, posto_id, dia, tipo, [])  # sem divergência antiga ao lado do erro
    return ResultadoFonte(posto_id, tipo, dia, situacao, 0, Decimal(0), mensagem, [])


def _fontes_ativas(con, posto_id: int) -> dict:
    return {f["tipo"]: f for f in banco.fontes_do_posto(con, posto_id) if f["ativo"]}


async def coletar_posto(con, posto_id: int, dia: date, *, visivel: bool = False,
                        so_falhas: bool = False) -> list[ResultadoFonte]:
    posto = con.execute("SELECT * FROM posto WHERE id=?", (posto_id,)).fetchone()
    if posto is None or not posto["ativo"]:
        return []
    fontes = _fontes_ativas(con, posto_id)
    comparar = _tem_chave_webposto(posto, fontes)
    unidade = unidades.montar(con).get(unidades.codigo_empresa(posto))
    if unidade is None:
        return []
    resultados = []
    for tipo in _FONTES:
        fonte = fontes.get(tipo)
        if not fonte or (so_falhas and _ja_coletado(con, fonte["id"], dia)):
            continue
        resultados.append(await _coletar_fonte(con, posto, fonte, unidade, dia, visivel, comparar))
    return resultados


async def coletar_todos(con, dia: date, *, so_falhas: bool = False) -> list[ResultadoFonte]:
    resultados = []
    for posto in banco.listar_postos(con):
        try:
            resultados.extend(await coletar_posto(con, posto["id"], dia, so_falhas=so_falhas))
        except Exception as exc:  # um posto ruim não impede os outros
            logger.warning("Coleta do posto falhou posto=%s tipo=%s", posto["id"], type(exc).__name__)
            mensagem = explicar.erro_pt(exc)
            resultados.extend(
                ResultadoFonte(posto["id"], t, dia, "erro", 0, Decimal(0), mensagem, [])
                for t in _FONTES if t in _fontes_ativas(con, posto["id"]))
    return resultados


def resultados_salvos(con, posto_id: int, dia: date) -> list[ResultadoFonte]:
    """Remonta o resultado do dia a partir do banco (para "Reenviar", sem coletar de novo)."""
    posto = con.execute("SELECT * FROM posto WHERE id=?", (posto_id,)).fetchone()
    if posto is None:
        return []
    fontes = _fontes_ativas(con, posto_id)
    comparar = _tem_chave_webposto(posto, fontes)
    resultados = []
    for tipo in _FONTES:
        fonte = fontes.get(tipo)
        coleta = fonte and con.execute("SELECT * FROM coleta WHERE fonte_id=? AND dia=?",
                                       (fonte["id"], str(dia))).fetchone()
        if not coleta:
            continue
        itens = [dict(r) for r in con.execute(
            "SELECT * FROM divergencia WHERE posto_id=? AND dia=? AND fonte=? ORDER BY id",
            (posto_id, str(dia), tipo))]
        total = Decimal(coleta["total"])
        if coleta["situacao"] in ("erro", "verificacao_humana"):
            situacao, mensagem = coleta["situacao"], coleta["erro_texto"] or ""
        else:
            situacao = coleta["situacao"] if (comparar or not coleta["qtd"]) else "sem_comparacao"
            mensagem = _mensagem(_NOME[tipo], coleta["qtd"], total, comparar, len(itens))
        resultados.append(ResultadoFonte(posto_id, tipo, dia, situacao, coleta["qtd"], total,
                                         mensagem, itens))
    return resultados
