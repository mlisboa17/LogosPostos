import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from src.modules.fiscal_docs import pdf
from src.modules.fiscal_docs.parser import ler

DADOS = Path(__file__).parent / "dados"


def _paginas(b: bytes) -> int:
    return len(PdfReader(io.BytesIO(b)).pages)


@pytest.mark.parametrize("arquivo", ["nfe_combustivel.xml", "nfe_produto.xml", "nfse_nacional.xml"])
def test_gerar_pdf(arquivo):
    xml = (DADOS / arquivo).read_bytes()
    saida = pdf.gerar_pdf(xml, ler(xml))
    assert saida.startswith(b"%PDF")
    assert _paginas(saida) >= 1


def test_danfse_simples_tem_dados_do_servico():
    xml = (DADOS / "nfse_nacional.xml").read_bytes()
    texto = PdfReader(io.BytesIO(pdf.danfse_simples(ler(xml)))).pages[0].extract_text()
    assert "DANFSe" in texto
    assert "MANUTENCAO DE BOMBAS TESTE LTDA" in texto
    assert "15/09/2026 10:00" in texto
    assert "1.500,00" in texto


def test_unir_soma_paginas():
    a = pdf.gerar_pdf(*(lambda x: (x, ler(x)))((DADOS / "nfe_combustivel.xml").read_bytes()))
    b = pdf.gerar_pdf(*(lambda x: (x, ler(x)))((DADOS / "nfse_nacional.xml").read_bytes()))
    assert _paginas(pdf.unir([a, b])) == _paginas(a) + _paginas(b)
