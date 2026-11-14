"""Cenários da conciliação Premmia x webPosto (especificação do diretor, 13/11/2026)."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from apps.match import sugestoes
from src.modules.cash_reconciliation.domain.cartoes import (
    Abastecimento, Atribuicao, Candidato, CartaoErp, Casamento, Investigacao, ParProvavel, ResultadoCartoes,
    TransacaoAdquirente,
)
from src.modules.cash_reconciliation.domain.models import Proveniencia
from src.modules.cash_reconciliation.domain.tempo import FUSO

DIA = date(2026, 11, 12)


def _h(hh, mm):
    return datetime(2026, 11, 12, hh, mm, tzinfo=FUSO)


def _t(valor, hh, mm, nsu="111"):
    return TransacaoAdquirente(adquirente="PREMMIA", identificador=f"t{nsu}", nsu=nsu, autorizacao=None,
                               valor=Decimal(valor), momento=_h(hh, mm))


def _a(codigo, valor, hh, mm, frentista=7, nome="JOSÉ", venda=None, bico=4):
    return Abastecimento(codigo=codigo, empresa_codigo=1, momento=_h(hh, mm), bico=bico, valor=Decimal(valor),
                         frentista=frentista, venda_item_codigo=None, nome_frentista=nome, venda_codigo=venda)


def _c(codigo, valor, hh, mm, frentista=9, nome="MARIA", venda=None, motivo=None):
    return CartaoErp(codigo=codigo, empresa_codigo=1, venda_codigo=venda, valor=Decimal(valor), momento=_h(hh, mm),
                     administradora="PREMMIA", nsu=None, nsu_tef=None, autorizacao=None, frentista=frentista,
                     nome_frentista=nome, motivo=motivo, caixa_codigo=55)


def _r(**kw):
    return ResultadoCartoes(empresa_codigo=1, adquirente="PREMMIA", dia=DIA, casados=kw.pop("casados", ()),
                            a_maior=kw.pop("a_maior", ()), a_menor=kw.pop("a_menor", ()),
                            proveniencia=Proveniencia(execucao_id="x", executado_em=_h(23, 0), versao_regra="v",
                                                      fonte_sangrias="", extratos=(), outras_fontes=()), **kw)


def _inv(t, atribuicao, candidatos=(), frentista=None, nome=None, troca=False):
    return Investigacao(transacao=t, atribuicao=atribuicao, frentista=frentista, nome_frentista=nome,
                        candidatos=tuple(candidatos), troca_de_forma=troca)


# ---------------------------------------------------------------- Cenário 1: Premmia maior

def test_premmia_sem_lancamento_com_frentista_certo_sugere_incluir():
    a = _a(123, "57.30", 10, 2)
    cand = Candidato(abastecimento=a, pontos=88, motivos=("valor igual", "abastecido 3 min antes"), venda_em_dinheiro=False)
    inv = _inv(_t("57.30", 10, 5), Atribuicao.ATRIBUIDO, [cand], frentista=7, nome="JOSÉ")
    [o] = sugestoes.ocorrencias(_r(a_maior=(inv,)), [a])
    assert o.acao == "incluir" and o.valor == Decimal("57.30") and o.funcionario == "JOSÉ (7)"
    assert "abastecimento 123" in o.abastecimento and "bico 4" in o.abastecimento and "10:02" in o.abastecimento
    assert "valor igual" in o.criterios and "abastecido 3 min antes" in o.criterios
    assert "NSU 111" in o.referencia


def test_premmia_sem_lancamento_e_venda_em_dinheiro_sugere_corrigir_forma():
    a = _a(123, "57.30", 10, 2)
    cand = Candidato(abastecimento=a, pontos=95, motivos=("valor igual", "venda lançada como dinheiro"), venda_em_dinheiro=True)
    inv = _inv(_t("57.30", 10, 5), Atribuicao.ATRIBUIDO, [cand], frentista=7, nome="JOSÉ", troca=True)
    [o] = sugestoes.ocorrencias(_r(a_maior=(inv,)), [a])
    assert o.acao == "corrigir_forma" and "dinheiro" in o.correcao.lower()


def test_premmia_com_dois_abastecimentos_possiveis_fica_nao_resolvida():
    a1, a2 = _a(1, "50.00", 10, 1, frentista=7), _a(2, "50.00", 10, 3, frentista=8, nome="ANA")
    cands = [Candidato(abastecimento=x, pontos=70, motivos=("valor igual",), venda_em_dinheiro=False) for x in (a1, a2)]
    inv = _inv(_t("50.00", 10, 5), Atribuicao.SUGESTAO, cands)
    [o] = sugestoes.ocorrencias(_r(a_maior=(inv,)), [a1, a2])
    assert o.acao == "analisar" and o.nao_resolvida
    assert "2 abastecimentos possíveis" in " ".join(o.criterios)


def test_premmia_sem_abastecimento_compativel_fica_nao_resolvida():
    inv = _inv(_t("80.00", 10, 5), Atribuicao.SEM_ABASTECIMENTO)
    [o] = sugestoes.ocorrencias(_r(a_maior=(inv,)), [])
    assert o.acao == "analisar" and o.nao_resolvida and "sem abastecimento" in " ".join(o.criterios)


# ---------------------------------------------------------------- Cenário 2: webPosto maior

def test_webposto_sem_premmia_e_sem_abastecimento_sugere_excluir():
    [o] = sugestoes.ocorrencias(_r(a_menor=(_c(900, "40.00", 15, 0, venda=777),)), [])
    assert o.acao == "excluir" and o.funcionario == "MARIA (9)" and o.valor == Decimal("40.00")
    assert "possível divergência de caixa" in o.explicacao and "venda 777" in o.referencia


def test_webposto_sem_premmia_mas_com_abastecimento_sugere_corrigir_forma():
    a = _a(321, "40.00", 14, 55, venda=777)
    [o] = sugestoes.ocorrencias(_r(a_menor=(_c(900, "40.00", 15, 0, venda=777),)), [a])
    assert o.acao == "corrigir_forma" and "abastecimento 321" in o.abastecimento
    assert "mesma venda" in " ".join(o.criterios)


def test_webposto_abastecimento_fora_da_tolerancia_nao_conta():
    a = _a(321, "40.00", 14, 30)  # 30 min antes, sem a mesma venda
    [o] = sugestoes.ocorrencias(_r(a_menor=(_c(900, "40.00", 15, 0),)), [a])
    assert o.acao == "excluir"
    [o2] = sugestoes.ocorrencias(_r(a_menor=(_c(900, "40.00", 15, 0),)), [a], janela=timedelta(minutes=40))
    assert o2.acao == "corrigir_forma"


def test_webposto_cancelado_no_premmia_sugere_excluir_com_justificativa():
    c = _c(900, "40.00", 15, 0, motivo="cancelada no Premmia em 12/11/2026 15:10")
    [o] = sugestoes.ocorrencias(_r(a_menor=(c,)), [])
    assert o.acao == "excluir" and "cancelada no Premmia" in o.explicacao


def test_webposto_com_dois_abastecimentos_possiveis_fica_nao_resolvida():
    a1, a2 = _a(1, "40.00", 14, 55), _a(2, "40.00", 14, 57, frentista=8)
    [o] = sugestoes.ocorrencias(_r(a_menor=(_c(900, "40.00", 15, 0),)), [a1, a2])
    assert o.acao == "analisar" and o.nao_resolvida


# ---------------------------------------------------------------- pares, valores e consolidado

def test_par_provavel_vira_analisar_com_os_dois_lados():
    inv = _inv(_t("60.00", 9, 0), Atribuicao.SEM_ABASTECIMENTO)
    par = ParProvavel(investigacao=inv, cartao=_c(901, "60.00", 11, 40))
    [o] = sugestoes.ocorrencias(_r(pares_provaveis=(par,)), [])
    assert o.acao == "analisar" and "09:00" in o.explicacao and "11:40" in o.explicacao


def test_valor_diferente_sugere_corrigir_valor():
    cas = Casamento(transacao=_t("50.00", 9, 0), cartao=_c(902, "55.00", 9, 0), chave="nsu",
                    valor_divergente=True, diferenca=Decimal("-5.00"))
    [o] = sugestoes.ocorrencias(_r(casados=(cas,)), [])
    assert o.acao == "corrigir_valor" and o.valor == Decimal("5.00")


def test_consolidado_por_funcionario_e_totais():
    a = _a(123, "57.30", 10, 2)
    cand = Candidato(abastecimento=a, pontos=88, motivos=("valor igual",), venda_em_dinheiro=False)
    oc = sugestoes.ocorrencias(_r(
        a_maior=(_inv(_t("57.30", 10, 5), Atribuicao.ATRIBUIDO, [cand], frentista=7, nome="JOSÉ"),
                 _inv(_t("80.00", 11, 0, nsu="2"), Atribuicao.SEM_ABASTECIMENTO)),
        a_menor=(_c(900, "40.00", 15, 0),)), [a])
    r = sugestoes.consolidar(oc, total_premmia=Decimal("1000"), total_webposto=Decimal("922.70"))
    assert r.diferenca == Decimal("77.30")
    assert r.pendentes == Decimal("137.30") and r.excedentes == Decimal("40.00") and r.nao_resolvidas == 1
    por = {f.funcionario: f for f in r.por_funcionario}
    assert por["JOSÉ (7)"].a_lancar == Decimal("57.30") and por["MARIA (9)"].lancado_a_mais == Decimal("40.00")
    assert por["funcionário não identificado"].a_lancar == Decimal("80.00")
