from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from apps.match import banco
from apps.match.fiscal import planilha, repositorio as repo
from src.modules.fiscal_docs.parser import ler
from src.modules.fiscal_docs.webposto_notas import EntradaWebposto, NotaListada

DADOS = Path(__file__).resolve().parents[1] / "fiscal_docs" / "dados"


@pytest.fixture
def con(tmp_path):
    c = banco.conectar(tmp_path / "p.db")
    yield c
    c.close()


def _preparar(con):
    pid = banco.inserir_posto(con, "Doze", "doze", "52308604000284", 74014)
    eid = repo.salvar_empresa(con, "52308604000284", "POSTO DOZE", "doze", "Abreu e Lima", "PE", pid)
    comb = ler((DADOS / "nfe_combustivel.xml").read_bytes())
    entrada = EntradaWebposto(chave=comb.chave, tipo_frete="F", valor_frete=Decimal("350.00"),
                              cte_numero="998", cte_emissao=date(2026, 10, 31))
    repo.gravar_documento(con, eid, comb, Path("a"), "a", "webposto", entrada)
    prod = ler((DADOS / "nfe_produto.xml").read_bytes())
    repo.gravar_documento(con, eid, prod, Path("b"), "b", "webposto")
    repo.registrar_so_resumo(con, eid, NotaListada(chave="9" * 44, emitente_cnpj="55555555000191",
                                                   emitente_nome="PENDENTE LTDA", emissao=date(2026, 10, 5),
                                                   valor=Decimal("10")))
    return eid


def test_abas_e_cabecalhos(con, tmp_path):
    eid = _preparar(con)
    wb = load_workbook(planilha.gerar_planilha(con, eid, "2026-10", tmp_path / "r.xlsx"))
    assert wb.sheetnames == ["Notas", "Combustível", "Fretes (CT-e)", "Totais", "Pendências"]
    assert [c.value for c in wb["Notas"][1]] == planilha.CAB_NOTAS
    assert planilha.CAB_NOTAS == ["Data emissão", "Tipo", "Número", "Série", "Chave", "Emitente CNPJ",
                                  "Emitente", "Valor total", "ICMS", "ICMS-ST", "IPI", "ISS", "Retenções",
                                  "Situação", "Origem"]
    assert [c.value for c in wb["Combustível"][1]] == planilha.CAB_COMBUSTIVEL
    assert planilha.CAB_COMBUSTIVEL == ["Data emissão", "Nota", "Distribuidora", "Produto", "Código ANP",
                                        "Litros", "Preço/litro", "Valor", "ICMS monofásico", "Frete CIF/FOB",
                                        "Transportadora CNPJ", "Transportadora", "Placa", "UF placa",
                                        "CT-e número", "Valor frete"]


def test_conteudo(con, tmp_path):
    eid = _preparar(con)
    wb = load_workbook(planilha.gerar_planilha(con, eid, "2026-10", tmp_path / "r.xlsx"))
    notas = list(wb["Notas"].iter_rows(min_row=2, values_only=True))
    assert len(notas) == 3
    assert notas[0][0] == "05/10/2026"
    comb = list(wb["Combustível"].iter_rows(min_row=2, values_only=True))
    assert [r[3] for r in comb] == ["GASOLINA C COMUM", "OLEO DIESEL B S10"]
    assert comb[0][5] == pytest.approx(5000.0)
    assert comb[0][9] == "FOB" and comb[0][14] == "998" and comb[0][15] == pytest.approx(350.0)
    fretes = list(wb["Fretes (CT-e)"].iter_rows(min_row=2, values_only=True))
    assert fretes[0][:2] == ("998", "31/10/2026")
    totais = [r for r in wb["Totais"].iter_rows(values_only=True) if r and r[0]]
    litros = {r[0]: r[2] for r in totais if r[0] in ("GASOLINA C COMUM", "OLEO DIESEL B S10")}
    assert litros == {"GASOLINA C COMUM": pytest.approx(5000.0), "OLEO DIESEL B S10": pytest.approx(3000.0)}
    pend = list(wb["Pendências"].iter_rows(min_row=2, values_only=True))
    assert any("PENDENTE LTDA" in str(r) for r in pend)
    assert any("998" in str(r) for r in pend)  # CT-e citado sem XML nesta fase
