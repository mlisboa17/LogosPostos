"""Regras de auditoria do fechamento — FECHAMENTO_V2.

  vermelho: quebra em qualquer modalidade acima do limite (padrao R$ 10)
            sangria sem conta de destino
  laranja:  caixa fechado e nao consolidado
            caixa aberto (em andamento: quebra nao e calculada ate o fechamento)
            sangria alterada depois de lancada
V2: caixa aberto nao gera quebra (antes mostrava todo o apurado como "falta").
Mudou alguma regra? Crie nova VERSAO.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from ..domain.fechamento import Alerta, AuditoriaCaixa, Caixa, LinhaModalidade, Severidade
from ..domain.models import Sangria

VERSAO = "FECHAMENTO_V2"
LIMITE_QUEBRA = Decimal("10")


def _brl(v: Decimal) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def auditar_caixa(
    caixa: Caixa,
    modalidades: Iterable[LinhaModalidade],
    sangrias: Iterable[Sangria],
    limite: Decimal = LIMITE_QUEBRA,
) -> AuditoriaCaixa:
    linhas = tuple(modalidades)
    do_caixa = tuple(s for s in sangrias if s.caixa_codigo == caixa.codigo)
    alertas: list[Alerta] = []

    for m in (linhas if caixa.fechado else ()):
        if abs(m.diferenca) > limite:
            tipo = "falta" if m.diferenca < 0 else "sobra"
            alertas.append(Alerta(codigo="QUEBRA", severidade=Severidade.VERMELHO, valor=m.diferenca,
                                  referencia=caixa.codigo, mensagem=f"{m.rotulo}: {tipo} de {_brl(abs(m.diferenca))}"))
    if not caixa.fechado:
        alertas.append(Alerta(codigo="CAIXA_ABERTO", severidade=Severidade.LARANJA, referencia=caixa.codigo,
                              mensagem="Caixa em andamento: quebra só após o fechamento"))
    elif not caixa.consolidado:
        alertas.append(Alerta(codigo="NAO_CONSOLIDADO", severidade=Severidade.LARANJA,
                              referencia=caixa.codigo, mensagem="Caixa fechado e não consolidado"))
    for s in do_caixa:
        if s.conta_codigo is None:
            alertas.append(Alerta(codigo="SANGRIA_SEM_DESTINO", severidade=Severidade.VERMELHO, valor=s.valor,
                                  referencia=s.codigo, mensagem=f"Sangria de {_brl(s.valor)} às {s.momento:%H:%M} sem conta de destino"))
        if s.alterada:
            alertas.append(Alerta(codigo="SANGRIA_ALTERADA", severidade=Severidade.LARANJA, valor=s.valor,
                                  referencia=s.codigo, mensagem=f"Sangria de {_brl(s.valor)} às {s.momento:%H:%M} alterada após o lançamento"))

    return AuditoriaCaixa(caixa=caixa, modalidades=linhas, sangrias=do_caixa, alertas=tuple(alertas))
