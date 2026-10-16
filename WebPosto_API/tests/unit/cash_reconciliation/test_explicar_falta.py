from decimal import Decimal

from src.modules.cash_reconciliation.application.explicar_falta import explicar_falta, tabela_falta
from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente
from .test_resumo_diario import _registro, _unidade
from .test_piloto_cartao import caso


def registro(caso):
    r = _registro(alertas=())
    auditoria = r.fechamento.caixas[0]
    cx = auditoria.caixa
    inv = caso.inv.model_copy(update={
        "transacao": caso.inv.transacao.model_copy(update={"momento": cx.abertura.replace(
            year=r.dia.year, month=r.dia.month, day=r.dia.day, hour=11, minute=26)}),
        "candidatos": (caso.inv.candidatos[0].model_copy(update={
            "abastecimento": caso.inv.candidatos[0].abastecimento.model_copy(update={
                "empresa_codigo": r.empresa_codigo, "caixa_codigo": cx.codigo,
            }),
        }),),
    })
    auditoria = auditoria.model_copy(update={"modalidades": (
        auditoria.modalidades[0].model_copy(update={"modalidade": "dinheiro", "diferenca": Decimal("-686.71")}),
    )})
    return r.model_copy(update={
        "fechamento": r.fechamento.model_copy(update={"caixas": (auditoria,)}),
        "recebimentos": r.recebimentos.model_copy(update={"adquirentes": (
            RecebimentoAdquirente(adquirente="PAGBANK", situacao="ok", a_maior=(inv, inv)),
        )}),
    })


def test_decomposicao_sem_duplicar_pagamento_e_com_residual(caso):
    exp, = explicar_falta(registro(caso), _unidade("Doze"))
    assert exp.falta == Decimal("686.71")
    assert len(exp.partes) == 1 and exp.partes[0].valor == Decimal("34.75")
    assert exp.sem_explicacao == Decimal("651.96")
    texto = "\n".join(tabela_falta(exp))
    assert "Frentista Sintético (7)" in texto and "venda 101" in texto
    assert "Mastercard PagSeguro" in texto and "[Lançar]" in texto
    assert "caixa 10" not in texto
    assert sum((p.valor for p in exp.partes), exp.sem_explicacao) == exp.falta


def test_sem_caixa_ou_candidato_ambiguo_nao_inventa_responsabilidade(caso):
    r = registro(caso)
    adq = r.recebimentos.adquirentes[0]
    inv = adq.a_maior[0]
    inv = inv.model_copy(update={"candidatos": (*inv.candidatos, *inv.candidatos)})
    r = r.model_copy(update={"recebimentos": r.recebimentos.model_copy(update={
        "adquirentes": (adq.model_copy(update={"a_maior": (inv,)}),),
    })})
    exp, = explicar_falta(r, _unidade("Doze"))
    assert not exp.partes and exp.sem_explicacao == exp.falta


def test_sobra_e_evidencias_maiores_que_falta_nao_sao_truncadas(caso):
    r = registro(caso)
    a = r.fechamento.caixas[0]
    for diferenca in ("10", "-10"):
        r = r.model_copy(update={"fechamento": r.fechamento.model_copy(update={
            "caixas": (a.model_copy(update={"modalidades": (
                a.modalidades[0].model_copy(update={"diferenca": Decimal(diferenca)}),
            )}),),
        })})
        exp, = explicar_falta(r, _unidade("Doze"))
        assert exp.sem_explicacao == -Decimal(diferenca) - Decimal("34.75")


def test_caixa_aberto_nao_tem_falta(caso):
    r = registro(caso)
    a = r.fechamento.caixas[0]
    r = r.model_copy(update={"fechamento": r.fechamento.model_copy(update={
        "caixas": (a.model_copy(update={"caixa": a.caixa.model_copy(update={"fechado": False})}),),
    })})
    assert not explicar_falta(r, _unidade("Doze"))
