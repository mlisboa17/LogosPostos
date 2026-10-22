from datetime import date, datetime
from decimal import Decimal

from apps.match import explicar
from src.modules.cash_reconciliation.adapters.pagbank_edi import PagBankCredencialInvalida
from src.modules.cash_reconciliation.adapters.premmia_portal import PremmiaVerificacaoHumana
from src.modules.cash_reconciliation.adapters.webposto_http import WebPostoErro
from src.modules.cash_reconciliation.domain.cartoes import (
    AlertaCartao, Atribuicao, CartaoErp, Casamento, Investigacao, ResultadoCartoes,
    TransacaoAdquirente,
)
from src.modules.cash_reconciliation.domain.models import Proveniencia
from src.modules.cash_reconciliation.domain.tempo import FUSO

MOMENTO = datetime(2026, 10, 17, 14, 5, tzinfo=FUSO)


def _transacao(valor="150.00", nsu="123", adquirente="PAGBANK"):
    return TransacaoAdquirente(adquirente=adquirente, identificador=f"t{nsu}", nsu=nsu,
                               autorizacao=None, valor=Decimal(valor), momento=MOMENTO)


def _cartao(valor="80.00", nsu="999"):
    return CartaoErp(codigo=1, empresa_codigo=74014, venda_codigo=10, valor=Decimal(valor),
                     momento=MOMENTO, administradora="PAGSEGURO", nsu=nsu, nsu_tef=None,
                     autorizacao=None, caixa_codigo=7, frentista=42, nome_frentista="JOÃO")


def _resultado(adquirente="PAGBANK", **kw):
    prov = Proveniencia(execucao_id="x", executado_em=MOMENTO, versao_regra="v",
                        fonte_sangrias="", extratos=(), outras_fontes=())
    base = dict(empresa_codigo=74014, adquirente=adquirente, dia=date(2026, 10, 17),
                casados=(), a_maior=(), a_menor=(), proveniencia=prov)
    base.update(kw)
    return ResultadoCartoes(**base)


def test_dinheiro_formato_brasileiro():
    assert explicar.dinheiro(Decimal("1234.5")) == "R$ 1.234,50"
    assert explicar.dinheiro(Decimal("-0.3")) == "-R$ 0,30"


def test_explicacao_falta_no_webposto():
    inv = Investigacao(transacao=_transacao(), atribuicao=Atribuicao.ATRIBUIDO, frentista=42,
                       candidatos=(), troca_de_forma=False, nome_frentista="JOÃO")
    [item] = explicar.divergencias(_resultado(a_maior=(inv,)))
    assert item["tipo"] == "falta_no_webposto"
    assert item["explicacao_pt"] == (
        "Venda de R$ 150,00 às 14:05 (NSU 123) está no PagBank mas não foi lançada no webPosto."
        " Responsável provável: JOÃO (42).")
    assert item["correcao_pt"] == "Lançar o cartão NSU 123 no caixa correto do webPosto."
    assert item["nsu"] == "123" and item["responsavel"] == "JOÃO (42)"
    assert item["valor_esperado"] == Decimal("150.00")


def test_explicacao_sobra_no_webposto_premmia():
    [item] = explicar.divergencias(_resultado(adquirente="PREMMIA", a_menor=(_cartao(),)))
    assert item["tipo"] == "sobra_no_webposto"
    assert item["explicacao_pt"] == (
        "Cartão de R$ 80,00 às 14:05 lançado no webPosto (JOÃO (42)) não aparece no Premmia.")
    assert item["correcao_pt"].startswith("Conferir com o frentista")
    assert item["caixa_codigo"] == 7 and item["valor_encontrado"] == Decimal("80.00")


def test_explicacao_valor_diferente_e_sem_alerta_duplicado():
    cas = Casamento(transacao=_transacao("100.00", "555"), cartao=_cartao("90.00", "555"),
                    chave="nsu", valor_divergente=True, diferenca=Decimal("10.00"))
    alertas = (
        AlertaCartao(codigo="CARTAO_VALOR_A_MENOR", severidade="vermelho", mensagem="dup",
                     valor=Decimal("10")),
        AlertaCartao(codigo="CARTAO_NSU_REPETIDO", severidade="vermelho", mensagem="NSU repetido",
                     valor=Decimal("5"), cartoes=(_cartao(),)),
    )
    ok = Casamento(transacao=_transacao("20.00", "1"), cartao=_cartao("20.00", "1"), chave="nsu")
    itens = explicar.divergencias(_resultado(casados=(cas, ok), alertas=alertas))
    assert [i["tipo"] for i in itens] == ["valor_diferente", "CARTAO_NSU_REPETIDO"]
    diff = itens[0]
    assert "R$ 90,00" in diff["explicacao_pt"] and "R$ 100,00" in diff["explicacao_pt"]
    assert "R$ 10,00" in diff["explicacao_pt"]
    assert diff["correcao_pt"] == "Corrigir o valor do cartão NSU 555 no webPosto."
    assert itens[1]["explicacao_pt"] == "NSU repetido" and itens[1]["caixa_codigo"] == 7


def test_erro_pt_textos():
    assert explicar.erro_pt(PagBankCredencialInvalida("x")) == (
        "PagBank recusou o usuário/token. Confira em Fontes do posto.")
    assert explicar.erro_pt(PremmiaVerificacaoHumana()) == (
        "O Premmia pediu verificação humana. Clique em Coletar agora (visível).")
    assert explicar.erro_pt(WebPostoErro("x")) == "webPosto indisponível ou chave inválida."


def test_erro_pt_nao_vaza_mensagem():
    texto = explicar.erro_pt(RuntimeError("falhou token=abc"))
    assert "abc" not in texto
    assert texto == "Falha inesperada na coleta (RuntimeError)."


def test_erro_pt_premmia_por_etapa():
    from src.modules.cash_reconciliation.adapters.premmia_portal import (
        PremmiaDiaNaoColetado, PremmiaErro)
    sem_cred = PremmiaVerificacaoHumana()
    sem_cred.etapa = "validar credenciais"
    assert explicar.erro_pt(sem_cred) == "Falta usuário/senha do Premmia em Fontes do posto."
    assert explicar.erro_pt(PremmiaErro("x", etapa="login já tentado")) == (
        "O Premmia já foi tentado hoje. Clique em Coletar agora (visível) para tentar de novo.")
    assert explicar.erro_pt(PremmiaDiaNaoColetado("x")) == (
        "O Premmia não entregou as vendas do dia. Nova tentativa na repescagem.")
    assert explicar.erro_pt(PremmiaVerificacaoHumana()) == (
        "O Premmia pediu verificação humana. Clique em Coletar agora (visível).")
