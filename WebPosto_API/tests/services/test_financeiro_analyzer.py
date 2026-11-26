"""Testes do FinanceiroAnalyzer — Fase 5 (valores fixos conhecidos)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.services.financeiro_ai.financeiro_analyzer import (
    EMPRESA_DOZE_FILIAL,
    FinanceiroAnalyzer,
)


@pytest.fixture
def analyzer() -> FinanceiroAnalyzer:
    return FinanceiroAnalyzer(webposto_client=None, empresa_codigo=EMPRESA_DOZE_FILIAL)


class TestFluxoCaixa:
    @pytest.mark.asyncio
    async def test_alerta_saldo_negativo_em_horizonte(self, analyzer: FinanceiroAnalyzer):
        rel = await analyzer.projetar_fluxo_caixa(
            movimentos=[
                {"dia": "2026-11-26", "entradas": 100, "saidas": 50},
                {"dia": "2026-11-27", "entradas": 0, "saidas": 200},
            ],
            saldo_inicial=Decimal("0"),
            horizonte_dias=7,
            data_referencia=date(2026, 11, 26),
        )

        assert rel["status"] == "CRÍTICO"
        assert rel["empresa_codigo"] == 74014
        assert len(rel["alertas_saldo_negativo"]) == 1
        assert rel["alertas_saldo_negativo"][0]["dia"] == "27/11/2026"
        assert rel["alertas_saldo_negativo"][0]["saldo_projetado"] == -150.0

    @pytest.mark.asyncio
    async def test_fluxo_sem_fonte_retorna_fonte_indisponivel(
        self, analyzer: FinanceiroAnalyzer
    ):
        rel = await analyzer.projetar_fluxo_caixa()

        assert rel["status"] == "fonte_indisponivel"
        assert "motivo" in rel

    @pytest.mark.asyncio
    async def test_fluxo_lista_vazia_nao_e_ok(self, analyzer: FinanceiroAnalyzer):
        rel = await analyzer.projetar_fluxo_caixa(movimentos=[])

        assert rel["status"] == "fonte_indisponivel"


class TestConferenciaCartoes:
    @pytest.mark.asyncio
    async def test_diferenca_20_reais_venda_1000_recebido_980(
        self, analyzer: FinanceiroAnalyzer
    ):
        """Exemplo de aceite: venda R$ 1.000 × recebido R$ 980 → diferença R$ 20."""
        rel = await analyzer.conferir_cartoes(
            vendas_cartao=[
                {"dia": "2026-11-25", "bandeira": "VISA", "valor": 1000.0},
            ],
            recebimentos_adquirentes=[
                {
                    "dia": "2026-11-25",
                    "bandeira": "VISA",
                    "valor": 980.0,
                    "adquirente": "PagBank",
                },
            ],
        )

        assert rel["status"] == "DIVERGENTE"
        assert rel["diferenca_total"] == 20.0
        assert len(rel["diferencas"]) == 1
        diff = rel["diferencas"][0]
        assert diff["venda_webposto"] == 1000.0
        assert diff["recebido_adquirente"] == 980.0
        assert diff["diferenca"] == 20.0
        assert diff["bandeira"] == "VISA"
        assert diff["adquirente"] == "PagBank"
        assert diff["causa"] == "webposto_maior_que_adquirente"
        assert "R$ 20.00" in diff["mensagem"] or "R$ 20" in diff["mensagem"]

    @pytest.mark.asyncio
    async def test_aporte_nao_entra_na_conciliacao(self, analyzer: FinanceiroAnalyzer):
        rel = await analyzer.conferir_cartoes(
            vendas_cartao=[
                {"dia": "2026-11-25", "bandeira": "MASTER", "valor": 100.0},
            ],
            recebimentos_adquirentes=[
                {
                    "dia": "2026-11-25",
                    "bandeira": "MASTER",
                    "valor": 100.0,
                    "adquirente": "Cielo",
                },
            ],
            aportes=[
                {"dia": "2026-11-25", "valor": 500.0, "origem": "transferencia matriz"},
            ],
        )

        assert rel["status"] == "OK"
        assert rel["diferenca_total"] == 0.0
        assert len(rel["avisos_aporte"]) == 1
        assert rel["avisos_aporte"][0]["valor"] == 500.0
        assert "não entra na conciliação" in rel["avisos_aporte"][0]["mensagem"]

    @pytest.mark.asyncio
    async def test_cartoes_sem_fonte(self, analyzer: FinanceiroAnalyzer):
        rel = await analyzer.conferir_cartoes()

        assert rel["status"] == "fonte_indisponivel"
        assert "motivo" in rel


class TestInadimplencia:
    @pytest.mark.asyncio
    async def test_titulo_frota_vencido(self, analyzer: FinanceiroAnalyzer):
        rel = await analyzer.listar_inadimplencia(
            titulos=[
                {
                    "tituloCodigo": "T1",
                    "nomeCliente": "Transportadora X",
                    "tipoCliente": "FROTA",
                    "valor": 350.50,
                    "dataVencimento": "2026-11-01",
                    "situacao": "ABERTO",
                }
            ],
            data_referencia=date(2026, 11, 26),
        )

        assert rel["status"] == "ALERTA"
        assert rel["quantidade"] == 1
        assert rel["valor_total_inadimplencia"] == 350.50
        assert rel["titulos"][0]["tipo_cliente"] == "FROTA"
        assert rel["titulos"][0]["dias_atraso"] == 25

    @pytest.mark.asyncio
    async def test_inadimplencia_sem_fonte(self, analyzer: FinanceiroAnalyzer):
        rel = await analyzer.listar_inadimplencia()

        assert rel["status"] == "fonte_indisponivel"


class TestDespesasProblematicas:
    @pytest.mark.asyncio
    async def test_despesa_sem_categoria_e_comprovante(
        self, analyzer: FinanceiroAnalyzer
    ):
        rel = await analyzer.listar_despesas_problematicas(
            despesas=[
                {
                    "despesaCodigo": "D9",
                    "posto": "74014",
                    "nome_caixa": "CAIXA CONVENIENCIA 1",
                    "setor": "22310",
                    "valor": 85.0,
                    "data": "2026-11-25",
                    "tem_comprovante": False,
                    "frentista": "João",  # deve ser ignorado na identidade
                }
            ]
        )

        assert rel["status"] == "ALERTA"
        assert rel["quantidade"] == 1
        desp = rel["despesas"][0]
        assert "sem_categoria" in desp["problemas"]
        assert "sem_comprovante" in desp["problemas"]
        assert "frentista" not in desp["caixa_id"].lower()
        assert "João" not in desp["caixa_id"]
        assert "22310" in desp["caixa_id"] or "CAIXA CONVENIENCIA" in desp["caixa_id"]

    @pytest.mark.asyncio
    async def test_despesas_sem_fonte(self, analyzer: FinanceiroAnalyzer):
        rel = await analyzer.listar_despesas_problematicas()

        assert rel["status"] == "fonte_indisponivel"


class TestRelatorio:
    @pytest.mark.asyncio
    async def test_relatorio_parcial_com_dados_de_cartao(
        self, analyzer: FinanceiroAnalyzer
    ):
        rel = await analyzer.gerar_relatorio_financeiro(
            vendas_cartao=[
                {"dia": "2026-11-25", "bandeira": "ELO", "valor": 200.0},
            ],
            recebimentos_adquirentes=[
                {
                    "dia": "2026-11-25",
                    "bandeira": "ELO",
                    "valor": 200.0,
                    "adquirente": "Premmia",
                },
            ],
        )

        assert rel["status"] in {"PARCIAL", "OK", "CRÍTICO"}
        assert "conferencia_cartoes" in rel["blocos"]
        assert rel["blocos"]["conferencia_cartoes"]["status"] == "OK"
        assert "fluxo_caixa" in rel["blocos_fonte_indisponivel"]

    @pytest.mark.asyncio
    async def test_empresa_doze_filial_nao_real(self, analyzer: FinanceiroAnalyzer):
        assert analyzer.empresa_codigo == 74014
        rel = await analyzer.projetar_fluxo_caixa(
            movimentos=[{"dia": "2026-11-26", "entradas": 10, "saidas": 0}],
            saldo_inicial=0,
            data_referencia=date(2026, 11, 26),
        )
        assert rel["empresa_nome"] == "POSTO DOZE FILIAL II"


# ---------- Fontes injetadas (sucesso / falha / vazio) ----------


class _Resp:
    def __init__(self, success: bool, data=None, error=None):
        self.success = success
        self.data = data
        self.error = error


class _FakeCashFlowOk:
    async def build(self, filters, empresa_codigo):
        return _Resp(
            True,
            {
                "daily": [
                    {
                        "periodo": "2026-11-26",
                        "entradasPrevistas": "100.00",
                        "saidasPrevistas": "40.00",
                    },
                    {
                        "periodo": "2026-11-27",
                        "entradasPrevistas": "0.00",
                        "saidasPrevistas": "200.00",
                    },
                ]
            },
        )


class _FakeCashFlowFail:
    async def build(self, filters, empresa_codigo):
        raise RuntimeError("cash_flow_offline")


class _FakeCashFlowEmpty:
    async def build(self, filters, empresa_codigo):
        return _Resp(True, {"daily": []})


class _FakeFinanceCenterOk:
    async def _fetch_titulo_receber_all(self, filters):
        return (
            [
                {
                    "tituloCodigo": "R1",
                    "nomeCliente": "Frota Alfa",
                    "tipoCliente": "FROTA",
                    "valor": "500.00",
                    "dataVencimento": "2026-11-01",
                    "pendente": True,
                }
            ],
            1.0,
        )

    def _classify_receivables(self, rows, reference_date):
        pendente = [
            {
                "tituloCodigo": r.get("tituloCodigo"),
                "cliente": r.get("nomeCliente"),
                "tipoCliente": r.get("tipoCliente"),
                "valor": r.get("valor"),
                "vencimento": r.get("dataVencimento"),
                "pendente": True,
            }
            for r in rows
        ]
        return {
            "pendente": pendente,
            "recebido": [],
            "vencido": [],
            "aVencer": [],
        }


class _FakeFinanceCenterFail:
    async def _fetch_titulo_receber_all(self, filters):
        raise RuntimeError("titulos_offline")

    def _classify_receivables(self, rows, reference_date):
        return {"pendente": []}


class _FakeFinanceCenterEmpty:
    async def _fetch_titulo_receber_all(self, filters):
        return ([], 0.5)

    def _classify_receivables(self, rows, reference_date):
        return {
            "pendente": [],
            "recebido": [],
            "vencido": [],
            "aVencer": [],
        }


class TestFonteFluxoCaixa:
    @pytest.mark.asyncio
    async def test_fluxo_fonte_sucesso(self):
        analyzer = FinanceiroAnalyzer(
            cash_flow_service=_FakeCashFlowOk(),
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.projetar_fluxo_caixa(
            horizonte_dias=7,
            data_referencia=date(2026, 11, 26),
            saldo_inicial=Decimal("0"),
        )

        assert rel["status"] == "CRÍTICO"
        assert len(rel["alertas_saldo_negativo"]) == 1
        assert rel["alertas_saldo_negativo"][0]["saldo_projetado"] == -140.0

    @pytest.mark.asyncio
    async def test_fluxo_fonte_falha(self):
        analyzer = FinanceiroAnalyzer(
            cash_flow_service=_FakeCashFlowFail(),
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.projetar_fluxo_caixa(
            data_referencia=date(2026, 11, 26),
        )

        assert rel["status"] == "fonte_indisponivel"
        assert "cash_flow_offline" in rel["motivo"]

    @pytest.mark.asyncio
    async def test_fluxo_fonte_vazia_sucesso(self):
        analyzer = FinanceiroAnalyzer(
            cash_flow_service=_FakeCashFlowEmpty(),
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.projetar_fluxo_caixa(
            data_referencia=date(2026, 11, 26),
        )

        assert rel["status"] == "OK"
        assert rel["serie_diaria"] == []
        assert rel["alertas_saldo_negativo"] == []


class TestFonteInadimplencia:
    @pytest.mark.asyncio
    async def test_titulos_fonte_sucesso(self):
        analyzer = FinanceiroAnalyzer(
            finance_center_service=_FakeFinanceCenterOk(),
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.listar_inadimplencia(
            data_referencia=date(2026, 11, 26),
        )

        assert rel["status"] == "ALERTA"
        assert rel["quantidade"] == 1
        assert rel["valor_total_inadimplencia"] == 500.0
        assert rel["titulos"][0]["tipo_cliente"] == "FROTA"

    @pytest.mark.asyncio
    async def test_titulos_fonte_falha(self):
        analyzer = FinanceiroAnalyzer(
            finance_center_service=_FakeFinanceCenterFail(),
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.listar_inadimplencia(
            data_referencia=date(2026, 11, 26),
        )

        assert rel["status"] == "fonte_indisponivel"
        assert "titulos_offline" in rel["motivo"]

    @pytest.mark.asyncio
    async def test_titulos_fonte_vazia_sucesso(self):
        analyzer = FinanceiroAnalyzer(
            finance_center_service=_FakeFinanceCenterEmpty(),
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.listar_inadimplencia(
            data_referencia=date(2026, 11, 26),
        )

        assert rel["status"] == "OK"
        assert rel["quantidade"] == 0
        assert rel["titulos"] == []


class TestFonteCartoes:
    @pytest.mark.asyncio
    async def test_cartoes_fonte_sucesso(self):
        async def fonte_ok():
            return {
                "vendas_cartao": [
                    {"dia": "2026-11-25", "bandeira": "VISA", "valor": 1000.0},
                ],
                "recebimentos": [
                    {
                        "dia": "2026-11-25",
                        "bandeira": "VISA",
                        "valor": 980.0,
                        "adquirente": "PagBank",
                    },
                ],
            }

        analyzer = FinanceiroAnalyzer(
            cartoes_fonte=fonte_ok,
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.conferir_cartoes()

        assert rel["status"] == "DIVERGENTE"
        assert rel["diferenca_total"] == 20.0

    @pytest.mark.asyncio
    async def test_cartoes_fonte_falha(self):
        async def fonte_falha():
            return {
                "status": "fonte_indisponivel",
                "motivo": "credenciais PagBank ausentes para 74014",
            }

        analyzer = FinanceiroAnalyzer(
            cartoes_fonte=fonte_falha,
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.conferir_cartoes()

        assert rel["status"] == "fonte_indisponivel"
        assert rel["motivo"] == "credenciais PagBank ausentes para 74014"

    @pytest.mark.asyncio
    async def test_cartoes_fonte_vazia_sucesso(self):
        async def fonte_vazia():
            return {"vendas_cartao": [], "recebimentos": []}

        analyzer = FinanceiroAnalyzer(
            cartoes_fonte=fonte_vazia,
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.conferir_cartoes()

        assert rel["status"] == "OK"
        assert rel["diferencas"] == []
        assert rel["diferenca_total"] == 0.0


class TestFonteDespesas:
    @pytest.mark.asyncio
    async def test_despesas_fonte_sucesso(self):
        async def fonte_ok():
            return [
                {
                    "despesaCodigo": "D1",
                    "posto": "74014",
                    "nome_caixa": "CAIXA PISTA",
                    "setor": "22310",
                    "valor": 50.0,
                    "data": "2026-11-25",
                    "tem_comprovante": False,
                }
            ]

        analyzer = FinanceiroAnalyzer(
            despesas_fonte=fonte_ok,
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.listar_despesas_problematicas()

        assert rel["status"] == "ALERTA"
        assert rel["quantidade"] == 1
        assert "sem_categoria" in rel["despesas"][0]["problemas"]

    @pytest.mark.asyncio
    async def test_despesas_fonte_falha(self):
        async def fonte_falha():
            return {
                "status": "fonte_indisponivel",
                "motivo": "falha ao ler despesas de caixa: TimeoutError",
            }

        analyzer = FinanceiroAnalyzer(
            despesas_fonte=fonte_falha,
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.listar_despesas_problematicas()

        assert rel["status"] == "fonte_indisponivel"
        assert "TimeoutError" in rel["motivo"]

    @pytest.mark.asyncio
    async def test_despesas_fonte_vazia_sucesso(self):
        async def fonte_vazia():
            return []

        analyzer = FinanceiroAnalyzer(
            despesas_fonte=fonte_vazia,
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
        rel = await analyzer.listar_despesas_problematicas()

        assert rel["status"] == "OK"
        assert rel["quantidade"] == 0
        assert rel["despesas"] == []
