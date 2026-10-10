"""Regras de auditoria do fechamento — FECHAMENTO_V3.

  vermelho: quebra em qualquer modalidade acima do limite (padrao R$ 10)
            falta em dinheiro sem vale de desconto; caixa parado fora da tolerancia
            sangria sem conta de destino
  laranja:  caixa fechado e nao consolidado dentro da tolerancia
            caixa aberto (em andamento: quebra nao e calculada ate o fechamento)
            sangria alterada depois de lancada
            vale divergente; despesa sem plano de contas/descricao util
V2: caixa aberto nao gera quebra (antes mostrava todo o apurado como "falta").
V3: verifica vales, tempo sem consolidar e despesas pagas no caixa.
Mudou alguma regra? Crie nova VERSAO.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from ..domain.fechamento import (
    Alerta,
    AuditoriaCaixa,
    Caixa,
    DescontoFalta,
    LinhaModalidade,
    MovimentoDespesa,
    Severidade,
    ValeFuncionario,
)
from ..domain.models import Sangria
from ..domain.tempo import agora

VERSAO = "FECHAMENTO_V3"
LIMITE_QUEBRA = Decimal("10")
ORIGEM_VALE_FALTA = "D"
TIPO_MOVIMENTO_DESPESA = "D"


def _brl(v: Decimal) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def auditar_caixa(
    caixa: Caixa,
    modalidades: Iterable[LinhaModalidade],
    sangrias: Iterable[Sangria],
    limite: Decimal = LIMITE_QUEBRA,
    *,
    vales: Iterable[ValeFuncionario] = (),
    despesas: Iterable[MovimentoDespesa] = (),
    dias_tolerancia_consolidacao: int = 2,
    hoje: date | None = None,
) -> AuditoriaCaixa:
    linhas = tuple(modalidades)
    do_caixa = tuple(s for s in sangrias if s.caixa_codigo == caixa.codigo)
    vales_do_caixa = tuple(
        vale for vale in vales
        if vale.caixa_codigo == caixa.codigo
        and vale.funcionario_codigo == caixa.funcionario_codigo
        and vale.origem.upper() == ORIGEM_VALE_FALTA
    )
    despesas_do_caixa = tuple(
        movimento for movimento in despesas
        if movimento.caixa_codigo == caixa.codigo and movimento.tipo.upper() == TIPO_MOVIMENTO_DESPESA
    )
    alertas: list[Alerta] = []
    desconto_falta = None

    for m in (linhas if caixa.fechado else ()):
        if abs(m.diferenca) > limite:
            tipo = "falta" if m.diferenca < 0 else "sobra"
            alertas.append(Alerta(codigo="QUEBRA", severidade=Severidade.VERMELHO, valor=m.diferenca,
                                  referencia=caixa.codigo, mensagem=f"{m.rotulo}: {tipo} de {_brl(abs(m.diferenca))}"))
    if not caixa.fechado:
        alertas.append(Alerta(codigo="CAIXA_ABERTO", severidade=Severidade.LARANJA, referencia=caixa.codigo,
                              mensagem="Caixa em andamento: quebra só após o fechamento"))
    elif not caixa.consolidado:
        data_fechamento = caixa.fechamento.date() if caixa.fechamento else caixa.data
        dias_parado = max(((hoje or agora().date()) - data_fechamento).days, 0)
        severidade = (
            Severidade.VERMELHO if dias_parado > dias_tolerancia_consolidacao else Severidade.LARANJA
        )
        alertas.append(Alerta(
            codigo="NAO_CONSOLIDADO",
            severidade=severidade,
            referencia=caixa.codigo,
            mensagem=f"Fechado há {dias_parado} dias sem consolidar",
            valor=Decimal(dias_parado),
        ))

    falta_dinheiro = sum(
        (-linha.diferenca for linha in linhas if linha.modalidade == "dinheiro" and linha.diferenca < 0),
        Decimal(0),
    )
    if caixa.fechado and falta_dinheiro > limite:
        total_vale = sum((vale.valor for vale in vales_do_caixa), Decimal(0))
        if not vales_do_caixa:
            situacao = "sem_desconto"
            alertas.append(Alerta(
                codigo="FALTA_SEM_DESCONTO",
                severidade=Severidade.VERMELHO,
                valor=falta_dinheiro,
                referencia=caixa.codigo,
                mensagem=f"Falta de {_brl(falta_dinheiro)} sem desconto lançado",
            ))
        elif total_vale == falta_dinheiro:
            situacao = "descontado"
        else:
            situacao = "divergente"
            diferenca = abs(falta_dinheiro - total_vale)
            alertas.append(Alerta(
                codigo="VALE_DIVERGENTE",
                severidade=Severidade.LARANJA,
                valor=diferenca,
                referencia=caixa.codigo,
                mensagem=(
                    f"Falta de {_brl(falta_dinheiro)} e vale de {_brl(total_vale)} "
                    f"(diferença de {_brl(diferenca)})"
                ),
            ))
        desconto_falta = DescontoFalta(
            situacao=situacao,
            falta=falta_dinheiro,
            total_vale=total_vale,
            diferenca=abs(falta_dinheiro - total_vale),
        )

    for s in do_caixa:
        if s.conta_codigo is None:
            alertas.append(Alerta(codigo="SANGRIA_SEM_DESTINO", severidade=Severidade.VERMELHO, valor=s.valor,
                                  referencia=s.codigo, mensagem=f"Sangria de {_brl(s.valor)} às {s.momento:%H:%M} sem conta de destino"))
        if s.alterada:
            alertas.append(Alerta(codigo="SANGRIA_ALTERADA", severidade=Severidade.LARANJA, valor=s.valor,
                                  referencia=s.codigo, mensagem=f"Sangria de {_brl(s.valor)} às {s.momento:%H:%M} alterada após o lançamento"))

    for despesa in despesas_do_caixa:
        if not despesa.plano_conta_codigo:
            alertas.append(Alerta(
                codigo="DESPESA_SEM_PLANO",
                severidade=Severidade.LARANJA,
                valor=despesa.valor,
                referencia=despesa.codigo,
                mensagem=f"Despesa de {_brl(despesa.valor)} sem plano de contas",
            ))
        if not despesa.descricao:
            alertas.append(Alerta(
                codigo="DESPESA_SEM_DESCRICAO",
                severidade=Severidade.LARANJA,
                valor=despesa.valor,
                referencia=despesa.codigo,
                mensagem=f"Despesa de {_brl(despesa.valor)} sem descrição útil",
            ))

    return AuditoriaCaixa(
        caixa=caixa,
        modalidades=linhas,
        sangrias=do_caixa,
        alertas=tuple(alertas),
        vales_falta=vales_do_caixa,
        desconto_falta=desconto_falta,
        despesas=despesas_do_caixa,
    )
