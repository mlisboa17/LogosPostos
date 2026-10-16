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


def test_tabela_completa_mesmo_calculo_no_relatorio_e_resumo(caso):
    from src.modules.cash_reconciliation.application.relatorio_caixa_dia import gerar_relatorio_caixa_dia
    from src.modules.cash_reconciliation.application.resumo_diario import gerar_resumo_diretor
    from src.modules.cash_reconciliation.domain.explicacao import ParteFalta
    r = registro(caso)
    adq = r.recebimentos.adquirentes[0]
    inv = adq.a_maior[0]
    ab = inv.candidatos[0].abastecimento.model_copy(update={"valor": Decimal("139.35"), "venda_codigo": 102})
    pix = inv.model_copy(update={
        "transacao": inv.transacao.model_copy(update={"identificador": "pix", "bandeira": "BACEN",
                                                      "valor": ab.valor, "nsu": None}),
        "candidatos": (inv.candidatos[0].model_copy(update={"abastecimento": ab}),),
    })
    r = r.model_copy(update={
        "recebimentos": r.recebimentos.model_copy(update={"adquirentes": (
            adq.model_copy(update={"a_maior": (inv, pix)}),
        )}),
        "administradora_pix_pagbank": "PIX PAGBANK",
        "partes_falta": (ParteFalta(referencia="mais:total", caixa_codigo=10,
                                  descricao="Mais Pagamentos — frentista não identificado",
                                  valor=Decimal("500"), fonte="total informado pelo diretor",
                                  correcao="Conferir na tela."),),
    })
    cfg = _unidade("Doze")
    exp, = explicar_falta(r, cfg)
    assert [p.valor for p in exp.partes] == [Decimal("34.75"), Decimal("139.35"), Decimal("500")]
    assert exp.sem_explicacao == Decimal("12.61") and exp.falta == Decimal("686.71")
    assert not exp.partes[1].lancavel
    assert "faltam NSU/autorização" in exp.partes[1].correcao
    assert "NSU final )" not in "\n".join(tabela_falta(exp))
    relatorio = gerar_relatorio_caixa_dia(r, cfg)
    resumo = gerar_resumo_diretor(r.dia, [r], [r.empresa_codigo], set(), {},
                                 unidades_config={r.empresa_codigo: cfg})
    for texto in (relatorio, resumo):
        assert "De onde vem a falta" in texto and "R$ 12,61" in texto
        assert "R$ 686,71" in texto and "frentista não identificado" in texto
