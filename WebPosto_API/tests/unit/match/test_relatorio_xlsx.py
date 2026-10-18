from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import openpyxl
import pytest

from apps.match import banco, credenciais, relatorio_xlsx
from src.modules.cash_reconciliation.domain.tempo import FUSO

DIA = date(2026, 10, 17)


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "t.db")
    yield c
    c.close()


def _t(ident, nsu, valor):
    return SimpleNamespace(identificador=ident, nsu=nsu, autorizacao="A1", valor=Decimal(valor),
                           momento=datetime(2026, 10, 17, 14, 5, tzinfo=FUSO), bandeira="VISA",
                           terminal="T1", situacao="aprovada")


@pytest.fixture
def posto(con):
    pid = banco.inserir_posto(con, "Posto Doze", "Doze", None, 74014)
    fp = banco.salvar_fonte(con, pid, "premmia", True, {})
    fb = banco.salvar_fonte(con, pid, "pagbank_edi", True, {})
    cp = banco.registrar_coleta(con, fp, DIA, "ok", 1, Decimal("100.50"), None)
    banco.registrar_coleta(con, fb, DIA, "erro", 0, Decimal("0"), "Falha ao entrar")
    banco.gravar_transacoes(con, cp, pid, "premmia", [_t("p1", "111", "100.50")])
    banco.gravar_divergencias(con, pid, DIA, "premmia", [{
        "tipo": "nsu_ausente", "valor_esperado": Decimal("100.50"), "valor_encontrado": None,
        "nsu": "111", "caixa_codigo": 7, "responsavel": "JOÃO (42)",
        "explicacao_pt": "Venda sem par", "correcao_pt": "Conferir no portal"}])
    return pid


def test_abas_e_nome_do_arquivo(con, posto, tmp_path):
    p = relatorio_xlsx.gerar(con, posto, DIA)
    assert p.name == "Logos_Doze_17-10-2026.xlsx"
    assert p.parent == tmp_path / "dados" / "planilhas"
    wb = openpyxl.load_workbook(p)
    assert wb.sheetnames == ["Resumo", "Premmia", "PagBank", "Divergências"]
    resumo = [[c.value for c in r] for r in wb["Resumo"].iter_rows()]
    assert ["Premmia", "ok", 1, 100.5, "Coleta concluída"] in resumo
    assert ["PagBank", "erro", 0, 0, "Falha ao entrar"] in resumo


def test_data_no_formato_brasil(con, posto):
    wb = openpyxl.load_workbook(relatorio_xlsx.gerar(con, posto, DIA))
    assert wb["Premmia"]["A2"].value == "17/10/2026 14:05"
    assert wb["Premmia"]["B2"].value == "111"


def test_valor_numerico_formatado(con, posto):
    wb = openpyxl.load_workbook(relatorio_xlsx.gerar(con, posto, DIA))
    c = wb["Premmia"]["D2"]
    assert c.value == 100.5 and c.number_format == "R$ #,##0.00"
    d = wb["Divergências"]["B2"]
    assert d.value == 100.5 and d.number_format == "R$ #,##0.00"
    assert wb["Divergências"]["F2"].value == "JOÃO (42)"


def test_sem_segredo_na_planilha(con, posto, tmp_path):
    credenciais.salvar("premmia-1", "S3nh@-Ultra-Secreta")
    wb = openpyxl.load_workbook(relatorio_xlsx.gerar(con, posto, DIA, tmp_path / "x.xlsx"))
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                assert "S3nh@-Ultra-Secreta" not in str(c.value)
