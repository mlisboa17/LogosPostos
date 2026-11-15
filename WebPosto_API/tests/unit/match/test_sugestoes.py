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


# ---------------------------------------------------------------- casos reais do Doze (novembro/2026)

def test_pagamento_dividido_no_premmia_e_um_lancamento_manual_e_a_mesma_venda():
    """01/11: Premmia 12,00 + 188,00 às 21:39; webPosto um Premmia manual de 200,00 às 20:00, sem venda."""
    partes = (_inv(_t("12.00", 21, 39, nsu="A"), Atribuicao.SEM_ABASTECIMENTO),
              _inv(_t("188.00", 21, 39, nsu="B"), Atribuicao.SEM_ABASTECIMENTO))
    manual = _c(214125021, "200.00", 20, 0, frentista=None, nome=None)
    oc = sugestoes.ocorrencias(_r(a_maior=partes, a_menor=(manual,)), [])
    assert [o.acao for o in oc] == ["vincular"]  # nunca "excluir" o lançamento que pagou a venda
    o = oc[0]
    assert o.valor == Decimal("200.00") and not o.nao_resolvida
    assert "R$ 12,00 + R$ 188,00" in o.explicacao and "20:00" in o.explicacao
    r = sugestoes.consolidar(oc, Decimal("200"), Decimal("200"))
    assert r.pendentes == 0 and r.excedentes == 0


def test_pagamento_dividido_com_abastecimento_da_soma_sugere_incluir():
    partes = (_inv(_t("5.00", 22, 27, nsu="A"), Atribuicao.SEM_ABASTECIMENTO),
              _inv(_t("95.00", 22, 27, nsu="B"), Atribuicao.SEM_ABASTECIMENTO))
    a = _a(555, "100.00", 22, 20, frentista=31, nome="CARLOS")
    [o] = sugestoes.ocorrencias(_r(a_maior=partes), [a])
    assert o.acao == "incluir" and o.valor == Decimal("100.00") and o.funcionario == "CARLOS (31)"
    assert "pagamento dividido em 2 partes" in " ".join(o.criterios) and "abastecimento 555" in o.abastecimento


def test_venda_em_dinheiro_e_lancamento_manual_do_mesmo_valor_sao_a_mesma_venda():
    """07/11: Premmia 179,46 às 11:12 lançado como dinheiro; à mão, Premmia 179,46 às 12:00 sem venda."""
    a = _a(413438288, "179.46", 11, 8, frentista=299244, nome="RONALDO")
    cand = Candidato(abastecimento=a, pontos=93, motivos=("valor igual", "venda lançada como dinheiro"),
                     venda_em_dinheiro=True)
    inv = _inv(_t("179.46", 11, 12), Atribuicao.ATRIBUIDO, [cand], frentista=299244, nome="RONALDO", troca=True)
    manual = _c(214803713, "179.46", 12, 0, frentista=None, nome=None)
    [o] = sugestoes.ocorrencias(_r(a_maior=(inv,), a_menor=(manual,)), [a])
    assert o.acao == "vincular" and "11:12" in o.explicacao and "12:00" in o.explicacao
    assert o.funcionario == "RONALDO (299244)"


def test_alerta_do_mesmo_cartao_nao_vira_outra_ocorrencia():
    from src.modules.cash_reconciliation.domain.cartoes import AlertaCartao
    c = _c(900, "40.00", 15, 0)
    alerta = AlertaCartao(codigo="CARTAO_MANUAL_SEM_VENDA", severidade="laranja", mensagem="Lançamento manual sem venda",
                          valor=Decimal("40.00"), cartoes=(c,))
    [o] = sugestoes.ocorrencias(_r(a_menor=(c,), alertas=(alerta,)), [])
    assert o.acao == "excluir" and "lançamento manual sem venda" in " ".join(o.criterios)


def test_cancelado_no_premmia_nao_e_ligado_a_venda_de_mesmo_valor():
    inv = _inv(_t("40.00", 9, 0), Atribuicao.SEM_ABASTECIMENTO)
    cancelado = _c(900, "40.00", 15, 0, motivo="cancelada no Premmia em 12/11/2026 15:10")
    acoes = sorted(o.acao for o in sugestoes.ocorrencias(_r(a_maior=(inv,), a_menor=(cancelado,)), []))
    assert acoes == ["analisar", "excluir"]


def test_pagamento_dividido_sem_certeza_vira_uma_ocorrencia_so():
    """13/11 22:27: Premmia 5,00 + 95,00 e nenhum abastecimento de 100,00 certo."""
    partes = (_inv(_t("5.00", 22, 27, nsu="A"), Atribuicao.SEM_ABASTECIMENTO),
              _inv(_t("95.00", 22, 27, nsu="B"), Atribuicao.SEM_ABASTECIMENTO))
    [o] = sugestoes.ocorrencias(_r(a_maior=partes), [_a(1, "100.00", 22, 20), _a(2, "100.00", 22, 22, frentista=8)])
    assert o.acao == "analisar" and o.valor == Decimal("100.00") and o.nao_resolvida
    assert "R$ 5,00 + R$ 95,00" in o.explicacao and "2 abastecimentos de R$ 100,00 possíveis" in " ".join(o.criterios)


# ---------------------------------------------------------------- PagBank

def _rp(**kw):
    r = _r(**kw)
    return r.model_copy(update={"adquirente": "PAGBANK"})


def test_pagbank_usa_a_mesma_regra_com_o_nome_certo():
    [o] = sugestoes.ocorrencias(_rp(a_menor=(_c(900, "40.00", 15, 0, venda=777),)), [])
    assert o.acao == "excluir" and "PagBank" in o.explicacao and "Premmia" not in o.explicacao
    assert "não está no PagBank" in o.criterios


def test_pagbank_varias_transacoes_somando_um_lancamento_viram_mesma_venda():
    from src.modules.cash_reconciliation.domain.cartoes import GrupoProvavel
    invs = (_inv(_t("30.00", 10, 0, nsu="1"), Atribuicao.SEM_ABASTECIMENTO),
            _inv(_t("20.00", 10, 1, nsu="2"), Atribuicao.SEM_ABASTECIMENTO))
    grupo = GrupoProvavel(investigacoes=invs, cartao=_c(901, "50.00", 10, 3))
    [o] = sugestoes.ocorrencias(_rp(grupos_provaveis=(grupo,)), [])
    assert o.acao == "vincular" and o.valor == Decimal("50.00") and "R$ 30,00 + R$ 20,00" in o.explicacao
    assert "PagBank" in o.explicacao


# ---------------------------------------------------------------- casos reais do PagBank (novembro/2026)

def test_lancamento_manual_em_lote_soma_as_vendas_soltas():
    """Casa Caiada 11/11: vendas PagBank da manhã lançadas como dinheiro; acerto com um cartão manual em lote."""
    a = _a(1, "100.00", 6, 10, frentista=83139, nome="DAVI")
    cand = Candidato(abastecimento=a, pontos=84, motivos=("valor igual",), venda_em_dinheiro=True)
    invs = (_inv(_t("100.00", 6, 11, nsu="1"), Atribuicao.ATRIBUIDO, [cand], frentista=83139, nome="DAVI", troca=True),
            _inv(_t("190.08", 6, 35, nsu="2"), Atribuicao.ATRIBUIDO, [cand], frentista=83139, nome="DAVI", troca=True),
            _inv(_t("30.00", 7, 47, nsu="3"), Atribuicao.ATRIBUIDO, [cand], frentista=63048, nome="HENRIQUE", troca=True),
            _inv(_t("104.87", 9, 23, nsu="4"), Atribuicao.SEM_ABASTECIMENTO),
            _inv(_t("50.00", 9, 30, nsu="5"), Atribuicao.SEM_ABASTECIMENTO))
    lote = _c(215102552, "424.95", 0, 32, frentista=None, nome=None)  # 100 + 190,08 + 30 + 104,87
    oc = sugestoes.ocorrencias(_rp(a_maior=invs, a_menor=(lote,)), [a])
    acoes = sorted(o.acao for o in oc)
    assert acoes == ["analisar", "vincular"]  # sobra só a venda de 50,00
    o = next(o for o in oc if o.acao == "vincular")
    assert o.valor == Decimal("424.95") and "4 vendas" in o.explicacao and "em lote" in o.explicacao
    assert any("DAVI (83139)" in c and "R$ 290,08" in c for c in o.criterios)
    r = sugestoes.consolidar(oc, Decimal("474.95"), Decimal("424.95"))
    assert r.excedentes == 0


def test_mesmo_valor_no_mesmo_minuto_e_mesma_venda():
    inv = _inv(_t("100.00", 11, 22), Atribuicao.SEM_ABASTECIMENTO)
    par = ParProvavel(investigacao=inv, cartao=_c(214093973, "100.00", 11, 22, frentista=None, nome=None))
    [o] = sugestoes.ocorrencias(_rp(pares_provaveis=(par,)), [])
    assert o.acao == "vincular" and not o.nao_resolvida
    longe = ParProvavel(investigacao=inv, cartao=_c(1, "100.00", 15, 7, venda=555))
    [o2] = sugestoes.ocorrencias(_rp(pares_provaveis=(longe,)), [])
    assert o2.acao == "analisar"



def test_lancamento_manual_com_hora_redonda_e_mesma_venda():
    """Doze 02/11: PagBank 371,23 às 08:16; lançamento manual de 371,23 às 01:00 (hora padrão)."""
    inv = _inv(_t("371.23", 8, 16), Atribuicao.SEM_ABASTECIMENTO)
    par = ParProvavel(investigacao=inv, cartao=_c(214221200, "371.23", 1, 0, frentista=None, nome=None))
    [o] = sugestoes.ocorrencias(_rp(pares_provaveis=(par,)), [])
    assert o.acao == "vincular" and "hora redonda (01:00)" in o.criterios[0]


# ---------------------------------------------------------------- dados para lançar/corrigir

def test_incluir_traz_os_dados_da_maquininha_para_lancar():
    t = TransacaoAdquirente(adquirente="PAGBANK", identificador="x", nsu="630713422704", autorizacao="A1B2C3",
                            valor=Decimal("57.30"), momento=_h(10, 5), bandeira="ELO CREDITO")
    a = _a(123, "57.30", 10, 2)
    cand = Candidato(abastecimento=a, pontos=88, motivos=("valor igual",), venda_em_dinheiro=False)
    [o] = sugestoes.ocorrencias(_rp(a_maior=(_inv(t, Atribuicao.ATRIBUIDO, [cand], frentista=7, nome="JOSÉ"),)), [a])
    assert o.dados == [{"lado": "PagBank", "administradora": "PagBank ELO CREDITO", "autorizacao": "A1B2C3",
                        "nsu": "630713422704", "valor": "R$ 57,30", "hora": "10:05", "funcionario": "JOSÉ (7)"}]


def test_excluir_e_corrigir_valor_trazem_o_lancamento_do_webposto():
    c = CartaoErp(codigo=900, empresa_codigo=1, venda_codigo=None, valor=Decimal("69.99"), momento=_h(1, 0),
                  administradora="ELO CREDITO PAGSEGURO", nsu="555", nsu_tef=None, autorizacao="XYZ", frentista=9,
                  nome_frentista="MARIA")
    [o] = sugestoes.ocorrencias(_rp(a_menor=(c,)), [])
    assert o.acao == "excluir" and o.dados[0]["administradora"] == "ELO CREDITO PAGSEGURO"
    assert (o.dados[0]["autorizacao"], o.dados[0]["nsu"], o.dados[0]["funcionario"]) == ("XYZ", "555", "MARIA (9)")
    cas = Casamento(transacao=_t("143.92", 10, 44), cartao=_c(902, "120.03", 10, 44), chave="nsu",
                    valor_divergente=True, diferenca=Decimal("23.89"))
    [v] = sugestoes.ocorrencias(_rp(casados=(cas,)), [])
    assert [d["lado"] for d in v.dados] == ["Premmia", "webPosto"]  # o lado vem da transação (_t cria Premmia)
    assert [d["valor"] for d in v.dados] == ["R$ 143,92", "R$ 120,03"]


def test_lote_lista_cada_venda_e_o_lancamento():
    invs = (_inv(_t("100.00", 6, 11, nsu="1"), Atribuicao.SEM_ABASTECIMENTO),
            _inv(_t("40.00", 6, 35, nsu="2"), Atribuicao.SEM_ABASTECIMENTO))
    [o] = sugestoes.ocorrencias(_rp(a_menor=(_c(1, "140.00", 0, 32, frentista=None, nome=None),), a_maior=invs), [])
    assert o.acao == "vincular" and [d["lado"] for d in o.dados] == ["Premmia", "Premmia", "webPosto"]



def test_pix_do_pagbank_aparece_como_pix():
    t = TransacaoAdquirente(adquirente="PAGBANK", identificador="p", nsu=None, autorizacao=None,
                            valor=Decimal("100.00"), momento=_h(5, 26), bandeira="BACEN")
    [o] = sugestoes.ocorrencias(_rp(a_maior=(_inv(t, Atribuicao.SEM_ABASTECIMENTO),)), [])
    assert o.dados[0]["administradora"] == "PagBank PIX"
