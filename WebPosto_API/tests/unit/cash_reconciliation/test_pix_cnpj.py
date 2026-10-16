from dataclasses import replace
from decimal import Decimal

import pytest

from src.modules.cash_reconciliation.adapters.extrato_reader import ler_ofx
from src.modules.cash_reconciliation.application.pix_cnpj import conferir_pix_cnpj
from src.modules.cash_reconciliation.domain.models import ContaExtratoConfig
from .test_piloto_cartao import caso
from .test_resumo_diario import _unidade


def extrato(nome="Cliente", fitid="1"):
    return ler_ofx(f"""OFXHEADER:100
<OFX><BANKID>290<ACCTID>1239048-8
<BANKTRANLIST><DTSTART>20261005<DTEND>20261005
<STMTTRN><TRNTYPE>IN<DTPOSTED>20261005112600<TRNAMT>34.75
<FITID>{fitid}<MEMO>Pix recebido {nome}</STMTTRN></BANKTRANLIST></OFX>""".encode())


def unidade():
    return _unidade("Doze").model_copy(update={"empresa_codigo": 74014, "contas_extrato": (
        ContaExtratoConfig(banco="PAGBANK", conta_sufixo="9048-8", cd_conta=1),
    )})


def conferir(caso, extratos, transferencias=()):
    a = caso.inv.candidatos[0].abastecimento.model_copy(update={"caixa_codigo": 10})
    return conferir_pix_cnpj(unidade(), caso.inv.transacao.momento.date(), extratos, list(transferencias), [a], {a.venda_item_codigo})


@pytest.mark.parametrize("nome", ["Posto Abreu e Lima", "Auto Posto Casa Caiada", "Posto Doze",
                                 "Posto VIP", "Loja de Conveniência", "Posto Real", "Vibra Energia"])
def test_exclui_grupo_fornecedor_e_deduplica_fitid(caso, nome):
    e = extrato(nome)
    conf, partes = conferir(caso, (e, e))
    assert conf.coberto and conf.ignorados == 1 and conf.clientes == 0
    assert not partes


def test_cliente_casado_por_valor_hora_nao_explica_dinheiro(caso):
    from src.modules.cash_reconciliation.domain.cartoes import CartaoErp
    t = caso.inv.transacao
    c = CartaoErp(codigo=1, empresa_codigo=74014, venda_codigo=101, valor=t.valor,
                  momento=t.momento, administradora="PIX CNPJ", nsu=None, nsu_tef=None, autorizacao=None)
    conf, partes = conferir(caso, (extrato(),), (c,))
    assert conf.casados == 1 and not partes and not conf.pendencias


def test_cliente_nao_lancado_encontra_venda_dinheiro(caso):
    conf, partes = conferir(caso, (extrato(),))
    assert conf.clientes == 1 and conf.casados == 0 and conf.pendencias
    assert partes[0].valor == Decimal("34.75")
    assert "Frentista Sintético (7)" in partes[0].correcao
    assert "Transferência Bancária / conta PAGBANK" in partes[0].correcao


def test_outra_conta_dia_sem_cobertura_e_fitid_conflitante(caso):
    e = extrato()
    conf, partes = conferir(caso, (replace(e, conta_sufixo="outra"),))
    assert not conf.coberto and not partes
    with pytest.raises(ValueError, match="FITID conflitante"):
        conferir(caso, (e, extrato("outro nome")))


def test_nao_casa_duas_entradas_com_mesma_transferencia(caso):
    from src.modules.cash_reconciliation.domain.cartoes import CartaoErp
    t = caso.inv.transacao
    c = CartaoErp(codigo=1, empresa_codigo=74014, venda_codigo=101, valor=t.valor,
                  momento=t.momento, administradora="PIX CNPJ", nsu=None, nsu_tef=None, autorizacao=None)
    conf, partes = conferir(caso, (extrato(), extrato(fitid="2")), (c,))
    assert conf.casados == 0 and not partes and len(conf.pendencias) == 3
