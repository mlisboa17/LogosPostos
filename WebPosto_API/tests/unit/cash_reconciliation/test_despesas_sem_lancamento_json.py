import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import openpyxl
import pytest

from src.jobs import despesas_avulsas as job


@pytest.fixture
def amostra():
    referencia = datetime.now(timezone.utc).replace(microsecond=0)
    return (*job.criar_demo_sintetica(date(2026, 8, 1), date(2026, 8, 31), referencia), referencia)


@pytest.fixture(autouse=True)
def somente_local(monkeypatch):
    def proibido(*args, **kwargs):
        raise AssertionError("A demonstração tentou executar uma dependência operacional.")

    for nome in ("load_dotenv", "carregar_unidades", "identificar_despesas_sem_lancamento", "_executar"):
        monkeypatch.setattr(job, nome, proibido)


def test_exporta_decimal_proveniencia_e_marcadores_sem_dados_brutos(amostra, tmp_path):
    resumo, titulos, movimentos, referencia = amostra
    saida = job.gravar_relatorio_json(
        resumo, titulos, movimentos, caminho_saida=tmp_path / "demo.json",
        referencia_temporal=referencia, max_idade_horas=168,
    )
    report = json.loads(saida.read_text(encoding="utf-8"))
    assert set(report) == {
        "schema_version", "sintetico", "cnpj_sintetico", "referencia_temporal",
        "max_idade_horas", "snapshots", "resumo",
    }
    assert report["schema_version"] == 1
    assert report["sintetico"] is True
    assert report["cnpj_sintetico"] == "00.000.000/0000-00"
    assert report["resumo"]["despesas"][0]["valor"] == "125.600000000000000001"
    assert report["resumo"]["total_geral"] == "125.600000000000000001"
    assert report["snapshots"]["titulos"]["status_cobertura"] == "COBERTURA_NAO_VERIFICADA"
    assert report["snapshots"]["titulos"]["sha256"] == titulos.sha256
    assert report["snapshots"]["movimentos"]["origem_atualizada_em"] == movimentos.origem_atualizada_em.isoformat()
    assert report["resumo"]["fontes_nao_mapeadas"]
    assert report["resumo"]["movimentacoes_auditadas"][0]["status"] == "AMBIGUO"
    assert "registros" not in report["snapshots"]["titulos"]
    assert resumo.total_geral == Decimal("125.600000000000000001")
    completo = json.loads(job.serializar_relatorio_json(
        replace(resumo, triagem_completa=True, fontes_nao_mapeadas=(), fontes_cobertura_incompleta=()),
        titulos, movimentos, referencia_temporal=referencia, max_idade_horas=168,
    ))
    assert completo["resumo"]["triagem_completa"] is True
    assert completo["snapshots"]["titulos"]["status_cobertura"] == "COBERTURA_NAO_VERIFICADA"


def test_exportacao_rejeita_identidade_ou_metadados_incompativeis_sem_gravar(amostra, tmp_path):
    resumo, titulos, movimentos, referencia = amostra
    for r, t in (
        (replace(resumo, unidade_codigo=-1), titulos),
        (resumo, replace(titulos, empresa_codigo=-1)),
        (resumo, replace(titulos, status_cobertura="VERIFICADA")),
        (resumo, replace(titulos, capturado_em=referencia)),
        (replace(resumo, despesas=(replace(resumo.despesas[0], conta_sufixo="NAO-PERMITIDA"),)), titulos),
    ):
        with pytest.raises(ValueError):
            job.gravar_relatorio_json(
                r, t, movimentos, caminho_saida=tmp_path / "rejeitado.json",
                referencia_temporal=referencia, max_idade_horas=168,
            )
        assert not (tmp_path / "rejeitado.json").exists()


def test_cli_sintetico_e_xlsx_opcionalmente_acompanhado_de_json(amostra, tmp_path, monkeypatch):
    _, _, _, referencia = amostra
    xlsx = tmp_path / "demo.xlsx"
    saida = tmp_path / "demo.json"
    argumentos = [
        "despesas_avulsas", "--demo-sintetica", "--de", "01/08/2026", "--ate", "31/08/2026",
        "--referencia-temporal", referencia.isoformat(), "--xlsx-saida", str(xlsx),
    ]
    for extras in ([], ["--json-saida", str(saida)]):
        monkeypatch.setattr("sys.argv", argumentos + extras)
        with pytest.raises(SystemExit) as exc:
            job.main()
        assert exc.value.code == 0
        assert saida.exists() == bool(extras)
        wb = openpyxl.load_workbook(xlsx, read_only=True)
        try:
            assert wb.active["E4"].value == "125.600000000000000001"
            assert wb.active["E4"].data_type == "s"
            assert wb.active["B1"].value == "COBERTURA_NAO_VERIFICADA"
            assert "SINTÉTICOS" in wb.active["A1"].value
        finally:
            wb.close()
