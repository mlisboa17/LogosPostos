"""Compara lançamentos armazenados com o financeiro do webPosto, sem escrever lá."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import date
from decimal import Decimal

from apps.match import banco, unidades
from apps.match.extratos import aprovacoes, repositorio
from src.modules.cash_reconciliation.adapters.extrato_reader import (
    ExtratoBancario,
    LancamentoBancario,
)
from src.modules.cash_reconciliation.application.despesas_sem_lancamento import (
    identificar_despesas_sem_lancamento,
)

logger = logging.getLogger(__name__)
RESULTADO_APROVACAO = (
    "Aguardando liberação de lançamentos no webPosto (teste supervisionado pendente)."
)


def _extrato(conta, linhas: list[sqlite3.Row]) -> ExtratoBancario:
    lancamentos = tuple(
        LancamentoBancario(
            fitid=linha["fitid"] or linha["chave"],
            data=date.fromisoformat(linha["data"]),
            momento=None,
            valor=Decimal(linha["valor"]),
            tipo=linha["tipo"] or ("CREDIT" if Decimal(linha["valor"]) >= 0 else "DEBIT"),
            tipo_original=linha["tipo"] or "",
            descricao=linha["descricao"] or "",
            documento=linha["documento"],
            categoria=linha["categoria"] or "outros",
        )
        for linha in linhas
    )
    return ExtratoBancario(
        banco=conta["banco"],
        agencia=conta["agencia"],
        conta_sufixo=conta["conta_sufixo"],
        inicio=min((l.data for l in lancamentos), default=None),
        fim=max((l.data for l in lancamentos), default=None),
        sha256="",
        lancamentos=lancamentos,
    )


def _json_item(despesa, linha) -> dict:
    plano = None
    if despesa.sugestao_plano_codigo is not None or despesa.sugestao_plano_nome:
        plano = {
            "codigo": despesa.sugestao_plano_codigo,
            "nome": despesa.sugestao_plano_nome,
        }
    centro = None
    if despesa.sugestao_centro_codigo is not None or despesa.sugestao_centro_nome:
        centro = {
            "codigo": despesa.sugestao_centro_codigo,
            "nome": despesa.sugestao_centro_nome,
        }
    explicacao = (
        f"Débito de R$ {despesa.valor:.2f} em {despesa.data:%d/%m/%Y} "
        f"({despesa.descricao_extrato}) não foi encontrado nos movimentos ou títulos "
        "do webPosto."
    )
    return {
        "chave_linha": linha["chave"],
        "data": despesa.data.isoformat(),
        "valor": format(despesa.valor, "f"),
        "descricao": despesa.descricao_extrato,
        "tipo_sugerido": despesa.tipo,
        "plano_conta": plano,
        "centro_custo": centro,
        "explicacao_pt": explicacao,
    }


def analisar(con, conta_id: int, de: date, ate: date) -> list[dict]:
    """Cria propostas únicas para os débitos não encontrados no financeiro."""
    if de > ate:
        raise ValueError("O início do período deve ser anterior ao fim.")
    conta = repositorio.conta_por_id(con, conta_id)
    if conta is None:
        raise ValueError("Conta bancária não encontrada.")
    linhas = con.execute(
        """SELECT * FROM extrato_linha
           WHERE conta_bancaria_id=? AND data>=? AND data<=?
           ORDER BY data, id""",
        (conta_id, de.isoformat(), ate.isoformat()),
    ).fetchall()
    if not linhas:
        return []

    posto = banco.obter_posto(con, conta["posto_id"])
    if posto is None:
        raise ValueError("Posto da conta não encontrado.")
    unidades.ativar(con)
    unidade = unidades.do_posto(con, posto)
    resultado = asyncio.run(identificar_despesas_sem_lancamento(
        unidade,
        de,
        ate,
        extratos_mock=[_extrato(conta, linhas)],
        falhar_em_erro_leitura=True,
    ))

    por_fitid = {l["fitid"] or l["chave"]: l for l in linhas}
    itens: dict[str, dict] = {}
    for despesa in resultado.despesas:
        linha = por_fitid.get(despesa.fitid)
        if linha is None:
            linha = next(
                (l for l in linhas if l["data"] == despesa.data.isoformat()
                 and Decimal(l["valor"]).copy_abs() == despesa.valor
                 and (l["descricao"] or "") == despesa.descricao_extrato),
                None,
            )
        if linha is None:
            logger.warning(
                "Resultado financeiro sem linha de extrato correspondente tipo=ValueError"
            )
            continue
        item = _json_item(despesa, linha)
        itens.setdefault(linha["chave"], item)

    from apps.match.canais import telegram_aprovacoes

    criadas = []
    propostas = []
    con.execute("BEGIN IMMEDIATE")
    try:
        existentes = {
            json.loads(row["resumo_json"]).get("chave_linha")
            for row in con.execute(
                "SELECT resumo_json FROM aprovacao WHERE tipo='lancamento' AND conta_bancaria_id=?",
                (conta_id,),
            )
        }
        for chave, item in itens.items():
            if chave in existentes:
                continue
            criada = aprovacoes.criar(
                con, "lancamento", conta["posto_id"], conta_id, item, commit=False
            )
            criadas.append((item, criada["ticket"]))
            propostas.append(item)
        con.commit()
    except Exception:
        con.rollback()
        raise

    for item, ticket in criadas:
        telegram_aprovacoes.notificar_aprovacao(
            con, item, ticket, tipo="lancamento"
        )
    return propostas


def decidir(con, ticket: str, acao: str, *, plano_conta: str = "",
            centro_custo: str = "", quem: str = "painel",
            canal: str = "painel") -> tuple[bool, str]:
    """Registra aprovação, recusa ou classificação corrigida; nunca chama o webPosto."""
    if acao not in ("aprovar", "recusar", "corrigir"):
        raise ValueError("Ação de aprovação inválida.")
    con.execute("BEGIN IMMEDIATE")
    try:
        row = con.execute(
            "SELECT * FROM aprovacao WHERE ticket=? AND tipo='lancamento'", (ticket,)
        ).fetchone()
        if row is None or row["situacao"] != "pendente":
            con.rollback()
            return False, aprovacoes.JA_RESOLVIDO
        resumo = json.loads(row["resumo_json"])
        if acao == "corrigir":
            plano_conta = plano_conta.strip()
            centro_custo = centro_custo.strip()
            if not plano_conta or not centro_custo:
                con.rollback()
                raise ValueError("Informe o plano de conta e o centro de custo.")
            resumo["plano_conta"] = {"codigo": None, "nome": plano_conta}
            resumo["centro_custo"] = {"codigo": None, "nome": centro_custo}
            situacao, resultado = "aprovada", "Corrigido."
        elif acao == "aprovar":
            situacao, resultado = "aprovada", RESULTADO_APROVACAO
        else:
            situacao, resultado = "recusada", "Recusado."
        resumo_json = json.dumps(resumo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(resumo_json.encode("utf-8")).hexdigest()
        cur = con.execute(
            """UPDATE aprovacao SET situacao=?, resumo_json=?, hash=?, decidida_em=?,
               decidida_por=?, canal_decisao=?, resultado=?
               WHERE id=? AND situacao='pendente'""",
            (
                situacao, resumo_json, digest, aprovacoes._agora(), quem, canal, resultado,
                row["id"],
            ),
        )
        if cur.rowcount != 1:
            con.rollback()
            return False, aprovacoes.JA_RESOLVIDO
        con.commit()
        return True, resultado
    except Exception:
        con.rollback()
        raise
