from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.fiscal_docs.modelos import XmlInvalido
from src.modules.fiscal_docs.parser_nfe import ler_nfe

DADOS = Path(__file__).parent / "dados"


def _ler(nome: str):
    return ler_nfe((DADOS / nome).read_bytes())


def test_combustivel_campos():
    d = _ler("nfe_combustivel.xml")
    assert d.tipo == "nfe"
    assert d.chave == "26261011111111000191550010000123451000012345"
    assert (d.numero, d.serie) == ("12345", "1")
    assert (d.emitente_cnpj, d.emitente_nome) == ("11111111000191", "DISTRIBUIDORA TESTE LTDA")
    assert d.destinatario_cnpj == "52308604000284"
    assert d.valor_total == Decimal("43617.28")
    assert d.situacao == "autorizada"
    assert d.combustivel is True
    assert [i.cprod_anp for i in d.itens] == ["320102001", "820101034"]
    assert d.itens[0].quantidade == Decimal("5000.0000")
    assert d.itens[0].icms_mono == Decimal("7350.00")
    assert d.itens[1].icms_mono == Decimal("3360.00")
    t = d.transporte
    assert (t.mod_frete, t.mod_frete_texto) == ("1", "FOB")
    assert (t.transportadora_cnpj, t.transportadora_nome) == ("22222222000191", "TRANSPORTES TESTE LTDA")
    assert (t.placa, t.uf_placa) == ("ABC1D23", "PE")
    assert (t.volumes, t.peso_bruto) == (Decimal("2"), Decimal("6200.000"))


def test_competencia_fuso():
    assert _ler("nfe_combustivel.xml").competencia == "2026-10"


def test_produto_sem_frete():
    d = _ler("nfe_produto.xml")
    assert d.combustivel is False
    assert d.transporte.mod_frete_texto == "Sem frete"
    assert d.impostos.icms_st == Decimal("5.10")
    assert d.impostos.ipi == Decimal("1.20")


@pytest.mark.parametrize("xml", [b"<x>", b"<?xml version='1.0'?><outro/>"])
def test_xml_quebrado(xml):
    with pytest.raises(XmlInvalido):
        ler_nfe(xml)


def test_sem_protocolo():
    bruto = (DADOS / "nfe_produto.xml").read_text(encoding="utf-8")
    inicio = bruto.index("<NFe>")
    fim = bruto.index("</NFe>") + len("</NFe>")
    so_nfe = bruto[inicio:fim].replace("<NFe>", '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">', 1)
    assert ler_nfe(so_nfe.encode()).situacao == "so_resumo"


def test_recusa_doctype():
    xml = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><nfeProc>&a;</nfeProc>'
    with pytest.raises(XmlInvalido):
        ler_nfe(xml)
