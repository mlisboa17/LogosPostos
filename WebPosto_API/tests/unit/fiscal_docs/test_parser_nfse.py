from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.fiscal_docs.modelos import XmlInvalido
from src.modules.fiscal_docs.parser import MSG_FORMATO, ler
from src.modules.fiscal_docs.parser_nfse import ler_nfse

DADOS = Path(__file__).parent / "dados"


def test_nfse_campos():
    d = ler_nfse((DADOS / "nfse_nacional.xml").read_bytes())
    assert d.tipo == "nfse"
    assert d.chave == "26116062244444444000191000000000000126090000000001"
    assert d.numero == "1"
    assert d.serie is None
    assert (d.emitente_cnpj, d.emitente_nome) == ("44444444000191", "MANUTENCAO DE BOMBAS TESTE LTDA")
    assert d.destinatario_cnpj == "52308604000284"
    assert d.valor_total == Decimal("1500.00")
    assert d.impostos.iss == Decimal("75.00")
    assert d.impostos.retencoes == Decimal("97.50")
    assert d.descricao_servico == "Manutencao preventiva de bombas de combustivel"
    assert d.competencia == "2026-09"
    assert d.situacao == "autorizada"
    assert d.combustivel is False


@pytest.mark.parametrize("arquivo,tipo", [
    ("nfe_combustivel.xml", "nfe"), ("nfe_produto.xml", "nfe"), ("nfse_nacional.xml", "nfse")])
def test_detecta_tipo(arquivo, tipo):
    assert ler((DADOS / arquivo).read_bytes()).tipo == tipo


def test_leiaute_municipal_recusado():
    abrasf = b'<?xml version="1.0"?><CompNfse xmlns="http://www.abrasf.org.br/nfse.xsd"><Nfse/></CompNfse>'
    with pytest.raises(XmlInvalido) as exc:
        ler(abrasf)
    assert str(exc.value) == MSG_FORMATO
    assert MSG_FORMATO == ("Formato não reconhecido. Hoje o Logos Match lê NF-e e NFS-e "
                           "do padrão nacional.")
