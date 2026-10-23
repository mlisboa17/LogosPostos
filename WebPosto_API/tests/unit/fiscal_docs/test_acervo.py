from pathlib import Path

from src.modules.fiscal_docs import acervo
from src.modules.fiscal_docs.parser import ler

DADOS = Path(__file__).parent / "dados"
CNPJ = "52308604000284"


def _doc():
    xml = (DADOS / "nfe_combustivel.xml").read_bytes()
    return ler(xml), xml


def test_caminho_padrao(tmp_path):
    doc, _ = _doc()
    assert acervo.caminho_xml(tmp_path, CNPJ, doc) == (
        tmp_path / CNPJ / "2026-10" / "nfe" / f"{doc.chave}.xml")


def test_grava_e_le_indice(tmp_path):
    doc, xml = _doc()
    p = acervo.gravar(tmp_path, CNPJ, doc, xml, "webposto")
    assert p.read_bytes() == xml
    [linha] = acervo.ler_indice(tmp_path, CNPJ)
    assert linha["chave"] == doc.chave
    assert linha["origem"] == "webposto"
    assert linha["valor_total"] == "43617.28"
    assert len(linha["sha256"]) == 64


def test_regravar_igual_nao_duplica(tmp_path):
    doc, xml = _doc()
    acervo.gravar(tmp_path, CNPJ, doc, xml, "webposto")
    acervo.gravar(tmp_path, CNPJ, doc, xml, "importado")
    assert len(acervo.ler_indice(tmp_path, CNPJ)) == 1
    assert not list((tmp_path / CNPJ).rglob("*.tmp"))


def test_indice_vazio(tmp_path):
    assert acervo.ler_indice(tmp_path, CNPJ) == []
