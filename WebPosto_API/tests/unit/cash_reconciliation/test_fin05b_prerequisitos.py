from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from src.modules.cash_reconciliation.application.despesas_sem_lancamento import (
    DebitoComTituloAberto,
    DespesaAvulsa,
    ResumoDespesasAvulsas,
    formatar_resumo_terminal,
    gerar_planilha_despesas_xlsx,
)


def test_construtores_legados_e_xlsx_continuam_compativeis(tmp_path):
    despesa = DespesaAvulsa(
        date(2026, 8, 15), "BANCO-FICTICIO", "CONTA-SINTETICA", Decimal("12.50"),
        "FITID-SINTETICO-001", "FAVORECIDO FICTICIO", "DESCRICAO SINTETICA", "PIX pessoa",
        None, "", None, "", None, "", "",
    )
    debito = DebitoComTituloAberto(
        date(2026, 8, 15), "BANCO-FICTICIO", "CONTA-SINTETICA", Decimal("1.00"),
        "FITID-SINTETICO-002", "DESCRICAO SINTETICA", "ambiguo", (), "", "",
    )
    resumo = ResumoDespesasAvulsas(
        0, "EMPRESA-SINTETICA-001", date(2026, 8, 1), date(2026, 8, 31), (despesa,),
        Decimal("12.50"), {"PIX pessoa": (1, Decimal("12.50"))}, 0, Decimal("0"), 0, Decimal("0"),
    )
    assert despesa.empresa_codigo is None
    assert debito.status_baixa == "ambiguo"
    assert resumo.triagem_completa is False
    assert resumo.movimentacoes_auditadas == ()
    assert "EMPRESA-SINTETICA-001" in formatar_resumo_terminal(resumo)
    caminho = gerar_planilha_despesas_xlsx(resumo, tmp_path / "legado.xlsx")
    wb = openpyxl.load_workbook(caminho, read_only=True)
    try:
        assert wb.active.title == "Despesas Avulsas"
        assert wb.active["D4"].value == 12.5
    finally:
        wb.close()


@pytest.mark.parametrize("opcoes", [
    ["--json-saida", "nao-gravar.json"],
    ["--json-saida", ""],
    ["--max-idade-horas", "168"],
    ["--demo-sintetica", "--xlsx-saida", ""],
    ["--demo-sintetica", "--unidade=0"],
    ["--demo-sintetica", "--unid=0"],
    ["--demo-sintetica", "--extrato", "nao-ler.ofx"],
    ["--demo-sintetica", "--referencia-temporal", "2026-08-01T00:00:00"],
    ["--demo-sintetica", "--max-idade-horas", "0"],
    ["--demo-sintetica", "--xlsx-saida", "nao-gravar.json"],
])
def test_cli_rejeita_mistura_operacional_e_opcoes_invalidas(monkeypatch, opcoes):
    from src.jobs import despesas_avulsas as job

    def proibido(*args, **kwargs):
        raise AssertionError("Nenhuma dependência operacional ou escrita deve ser executada.")

    for nome in ("_executar", "load_dotenv", "gerar_planilha_despesas_xlsx", "gravar_relatorio_json"):
        monkeypatch.setattr(job, nome, proibido)
    monkeypatch.setattr("sys.argv", [
        "despesas_avulsas", "--de", "01/08/2026", "--ate", "31/08/2026", *opcoes,
    ])
    with pytest.raises(SystemExit) as exc:
        job.main()
    assert exc.value.code == 2
