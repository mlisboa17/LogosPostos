"""Divergências e erros explicados em português simples (o Logos explica sozinho)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from src.modules.cash_reconciliation.adapters.pagbank_edi import PagBankCredencialInvalida, PagBankErro
from src.modules.cash_reconciliation.adapters.premmia_portal import (
    PremmiaDiaNaoColetado, PremmiaErro, PremmiaVerificacaoHumana)
from src.modules.cash_reconciliation.adapters.webposto_http import WebPostoErro
from src.modules.cash_reconciliation.domain.cartoes import ResultadoCartoes
from src.modules.cash_reconciliation.domain.tempo import formatar_hora

ETAPA_SEM_CREDENCIAIS = "validar credenciais"  # premmia_portal: usuário/senha ausentes
_NOME_FONTE = {"PREMMIA": "Premmia", "PAGBANK": "PagBank"}
# já cobertos pelo item "valor_diferente" gerado a partir do casamento
_ALERTAS_DE_VALOR = {"CARTAO_VALOR_A_MENOR", "CARTAO_VALOR_A_MAIOR"}


def dinheiro(valor: Decimal) -> str:
    q = Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    texto = f"{abs(q):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if q < 0 else ''}R$ {texto}"


def _item(tipo, esperado, encontrado, nsu, caixa, responsavel, explicacao, correcao) -> dict:
    return {"tipo": tipo, "valor_esperado": esperado, "valor_encontrado": encontrado, "nsu": nsu,
            "caixa_codigo": caixa, "responsavel": responsavel, "explicacao_pt": explicacao,
            "correcao_pt": correcao}


def divergencias(resultado: ResultadoCartoes) -> list[dict]:
    """valor_esperado = o que a adquirente registrou; valor_encontrado = o que está no webPosto."""
    fonte = _NOME_FONTE.get(resultado.adquirente, resultado.adquirente)
    itens = []
    for inv in resultado.a_maior:
        t = inv.transacao
        itens.append(_item(
            "falta_no_webposto", t.valor, Decimal(0), t.nsu, None, inv.responsavel,
            f"Venda de {dinheiro(t.valor)} às {formatar_hora(t.momento)} (NSU {t.nsu}) está no {fonte}"
            f" mas não foi lançada no webPosto. Responsável provável: {inv.responsavel}.",
            f"Lançar o cartão NSU {t.nsu} no caixa correto do webPosto."))
    for c in resultado.a_menor:
        itens.append(_item(
            "sobra_no_webposto", Decimal(0), c.valor, c.nsu, c.caixa_codigo, c.responsavel,
            f"Cartão de {dinheiro(c.valor)} às {formatar_hora(c.momento)} lançado no webPosto"
            f" ({c.responsavel}) não aparece no {fonte}.",
            "Conferir com o frentista se a venda foi em outra forma de pagamento e corrigir o lançamento."))
    for cas in resultado.casados:
        if not cas.valor_divergente:
            continue
        c, t = cas.cartao, cas.transacao
        nsu = c.nsu or t.nsu
        itens.append(_item(
            "valor_diferente", t.valor, c.valor, nsu, c.caixa_codigo, c.responsavel,
            f"Cartão NSU {nsu} às {formatar_hora(c.momento)} foi lançado no webPosto com"
            f" {dinheiro(c.valor)} ({c.responsavel}), mas o {fonte} registrou {dinheiro(t.valor)}."
            f" Diferença de {dinheiro(abs(t.valor - c.valor))}.",
            f"Corrigir o valor do cartão NSU {nsu} no webPosto."))
    for a in resultado.alertas:
        if a.codigo in _ALERTAS_DE_VALOR:
            continue
        cartao = a.cartoes[0] if a.cartoes else None
        itens.append(_item(
            a.codigo, None, a.valor, cartao.nsu if cartao else None,
            cartao.caixa_codigo if cartao else None, cartao.responsavel if cartao else None,
            a.mensagem, "Conferir o lançamento no webPosto e corrigir se necessário."))
    return itens


def erro_pt(exc: Exception) -> str:
    """Nunca usa str(exc): mensagens de adaptadores podem carregar segredo."""
    if isinstance(exc, PagBankCredencialInvalida):
        return "PagBank recusou o usuário/token. Confira em Fontes do posto."
    etapa = getattr(exc, "etapa", None)
    if isinstance(exc, PremmiaVerificacaoHumana) and etapa == ETAPA_SEM_CREDENCIAIS:
        return "Falta usuário/senha do Premmia em Fontes do posto."
    if isinstance(exc, PremmiaVerificacaoHumana):
        return "O Premmia pediu verificação humana. Clique em Coletar agora (visível)."
    if isinstance(exc, PremmiaDiaNaoColetado):
        return "O Premmia não entregou as vendas do dia. Nova tentativa na repescagem."
    if isinstance(exc, PremmiaErro) and etapa == "login já tentado":
        return "O Premmia já foi tentado hoje. Clique em Coletar agora (visível) para tentar de novo."
    if isinstance(exc, WebPostoErro) and not isinstance(exc, PagBankErro):
        return "webPosto indisponível ou chave inválida."
    return f"Falha inesperada na coleta ({type(exc).__name__})."
