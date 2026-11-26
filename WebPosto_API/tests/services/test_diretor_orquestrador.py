"""Testes do DiretorOrquestrador — brief executivo das cinco IAs."""

from __future__ import annotations

import pytest

from src.services.diretor_ai.diretor_orquestrador import DiretorOrquestrador, _parse_rs


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("R$ 1.000", 1000.0),
        ("R$ 1.000,50", 1000.5),
        ("1.000,50", 1000.5),
        ("1.234.567", 1234567.0),
        ("1000.50", 1000.5),
        ("980.5", 980.5),
        ("R$ 980,00", 980.0),
        ("-400", -400.0),
        ("R$ 1,000", None),
        ("1,000.50", None),
        ("R$ 120,000 em vendas perdidas", None),
        ("", None),
        ("abc", None),
        (None, None),
    ],
)
def test_parse_rs_formatos(entrada, esperado):
    assert _parse_rs(entrada) == esperado


class _BuyerComAchados:
    async def generate_executive_brief(self):
        return {
            "status": "OK",
            "economia_potencial_total": 1500.0,
            "top_problemas": [
                {
                    "problema": "Capital parado em 3 produtos",
                    "impacto": "R$ 1,000",
                    "impacto_rs": 1000.0,
                    "prioridade": "ALTA",
                    "acao": "Desconto/liquidação",
                    "ganho_estimado": "R$ 300",
                    "ganho_estimado_rs": 300.0,
                },
                {
                    "problema": "2 produtos em risco de ruptura",
                    "impacto": "R$ 500 em vendas perdidas",
                    "impacto_rs": 500.0,
                    "prioridade": "CRÍTICA",
                    "acao": "Comprar hoje",
                    "ganho_estimado": "R$ 500",
                    "ganho_estimado_rs": 500.0,
                },
            ],
        }


class _BuyerSoTextoAmbiguo:
    """Simula brief antigo só com texto US — sem campos numéricos."""

    async def generate_executive_brief(self):
        return {
            "status": "OK",
            "economia_potencial_total": 0,
            "top_problemas": [
                {
                    "problema": "Ruptura formatada à americana",
                    "impacto": "R$ 120,000 em vendas perdidas",
                    "prioridade": "CRÍTICA",
                    "acao": "Comprar hoje",
                    "ganho_estimado": "R$ 1,000",
                }
            ],
        }


class _BuyerIndisponivel:
    async def generate_executive_brief(self):
        return {
            "status": "fonte_indisponivel",
            "motivo": "estoque webPosto offline",
        }


class _BuyerErro:
    async def generate_executive_brief(self):
        raise RuntimeError("buyer_explodiu")


class _BuyerVazio:
    async def generate_executive_brief(self):
        return {
            "status": "OK",
            "economia_potencial_total": 0,
            "top_problemas": [],
        }


class _TaxVazio:
    async def generate_tax_audit_report(self):
        return {
            "status": "OK",
            "problemas_encontrados": 0,
            "problemas_criticos": 0,
            "risco_fiscal": {
                "status": "nao_estimado",
                "motivo": "sem base de multa auditada",
            },
            "recomendacoes": [],
        }


class _TaxComCriticosSemValor:
    async def generate_tax_audit_report(self):
        return {
            "status": "CRÍTICO",
            "problemas_encontrados": 1,
            "problemas_criticos": 1,
            "risco_fiscal": {
                "status": "nao_estimado",
                "motivo": "sem base de multa auditada",
            },
            "recomendacoes": ["Corrigir NCM"],
        }


class _PricingVazio:
    async def gerar_relatorio_precificacao(self):
        return {
            "status": "OK",
            "margens_negativas": 0,
            "impacto_total_mensal": 0,
            "recomendacoes": [],
        }


class _PricingComValor:
    async def gerar_relatorio_precificacao(self):
        return {
            "status": "CRÍTICO",
            "margens_negativas": 1,
            "impacto_total_mensal": 1000.0,
            "recomendacoes": ["Corrigir margem"],
        }


class _ComprasVazio:
    async def generate_data_quality_report(self, data_inicial, data_final):
        return {
            "status": "PRONTO_PARA_IA",
            "compras_com_problema": 0,
            "anomalias_preco_detectadas": 0,
            "recomendacoes": [],
        }


class _FinanceiroVazio:
    async def gerar_relatorio_financeiro(self):
        return {
            "status": "OK",
            "blocos": {
                "fluxo_caixa": {"status": "OK", "alertas_saldo_negativo": []},
                "conferencia_cartoes": {"status": "OK", "diferenca_total": 0},
                "inadimplencia": {"status": "OK", "quantidade": 0, "valor_total_inadimplencia": 0},
                "despesas_problematicas": {"status": "OK", "quantidade": 0},
            },
            "blocos_fonte_indisponivel": [],
        }


def _quadro_por_nome(brief: dict) -> dict:
    return {s["ia"]: s for s in brief["status_ias"]}


class TestDiretorOrquestrador:
    @pytest.mark.asyncio
    async def test_achados_ordenados_por_impacto_e_somados(self):
        orq = DiretorOrquestrador(
            buyer_analyzer=_BuyerComAchados(),
            tax_analyzer=_TaxVazio(),
            pricing_analyzer=_PricingVazio(),
            compras_validator=_ComprasVazio(),
            financeiro_analyzer=_FinanceiroVazio(),
        )
        brief = await orq.gerar_brief()

        assert len(brief["status_ias"]) == 5
        assert brief["impacto_total_rs"] == 1500.0
        assert len(brief["achados"]) == 2
        assert brief["achados"][0]["impacto_rs"] == 1000.0
        assert brief["achados"][1]["impacto_rs"] == 500.0
        assert brief["achados"][0]["origem"] == "BuyerAnalyzer.generate_executive_brief"
        assert brief["pendencias"] == []

    @pytest.mark.asyncio
    async def test_buyer_soma_campos_numericos_ignora_texto_ambiguo(self):
        """Totais vêm de impacto_rs; texto 'R$ 1,000' / frase longa não entram no cálculo."""
        orq = DiretorOrquestrador(
            buyer_analyzer=_BuyerComAchados(),
            tax_analyzer=_TaxVazio(),
            pricing_analyzer=_PricingVazio(),
            compras_validator=_ComprasVazio(),
            financeiro_analyzer=_FinanceiroVazio(),
        )
        brief = await orq.gerar_brief()
        soma_campos = 1000.0 + 500.0

        assert brief["impacto_total_rs"] == soma_campos
        assert [a["impacto_rs"] for a in brief["achados"]] == [1000.0, 500.0]

    @pytest.mark.asyncio
    async def test_buyer_texto_ambiguo_sem_numero_vira_sem_valor(self):
        orq = DiretorOrquestrador(
            buyer_analyzer=_BuyerSoTextoAmbiguo(),
            tax_analyzer=_TaxVazio(),
            pricing_analyzer=_PricingVazio(),
            compras_validator=_ComprasVazio(),
            financeiro_analyzer=_FinanceiroVazio(),
        )
        brief = await orq.gerar_brief()

        assert brief["impacto_total_rs"] == 0.0
        assert brief["achados"] == []
        assert len(brief["achados_sem_valor"]) == 1
        assert brief["achados_sem_valor"][0]["impacto_rs"] is None

    @pytest.mark.asyncio
    async def test_fonte_indisponivel_vira_pendencia_nao_zero(self):
        orq = DiretorOrquestrador(
            buyer_analyzer=_BuyerIndisponivel(),
            tax_analyzer=_TaxVazio(),
            pricing_analyzer=_PricingVazio(),
            compras_validator=_ComprasVazio(),
            financeiro_analyzer=_FinanceiroVazio(),
        )
        brief = await orq.gerar_brief()
        quadro = _quadro_por_nome(brief)

        assert quadro["Comprador IA"]["status"] == "fonte_indisponivel"
        assert quadro["Comprador IA"]["motivo"] == "estoque webPosto offline"
        assert "estoque webPosto offline" in brief["pendencias"][0]
        assert brief["impacto_total_rs"] == 0.0
        assert all(a["origem"] != "BuyerAnalyzer.generate_executive_brief" for a in brief["achados"])

    @pytest.mark.asyncio
    async def test_excecao_vira_erro_sem_derrubar_outras(self):
        orq = DiretorOrquestrador(
            buyer_analyzer=_BuyerErro(),
            tax_analyzer=_TaxVazio(),
            pricing_analyzer=_PricingComValor(),
            compras_validator=_ComprasVazio(),
            financeiro_analyzer=_FinanceiroVazio(),
        )
        brief = await orq.gerar_brief()
        quadro = _quadro_por_nome(brief)

        assert quadro["Comprador IA"]["status"] == "erro"
        assert "buyer_explodiu" in (quadro["Comprador IA"]["motivo"] or "")
        assert quadro["Precificador IA"]["status"] in {"ok", "vazio"}
        assert brief["impacto_total_rs"] == 1000.0
        assert len(brief["status_ias"]) == 5

    @pytest.mark.asyncio
    async def test_mesmo_valor_origens_diferentes_nao_fundem(self):
        orq = DiretorOrquestrador(
            buyer_analyzer=_BuyerComAchados(),
            tax_analyzer=_TaxVazio(),
            pricing_analyzer=_PricingComValor(),
            compras_validator=_ComprasVazio(),
            financeiro_analyzer=_FinanceiroVazio(),
        )
        brief = await orq.gerar_brief()

        # Buyer tem R$ 1000 e Pricing tem R$ 1000 — permanecem dois achados distintos
        mil = [a for a in brief["achados"] if a["impacto_rs"] == 1000.0]
        assert len(mil) == 2
        origens = {a["origem"] for a in mil}
        assert "BuyerAnalyzer.generate_executive_brief" in origens
        assert "PricingAnalyzer.gerar_relatorio_precificacao" in origens
        assert brief["impacto_total_rs"] == 2500.0

    @pytest.mark.asyncio
    async def test_tax_critico_nao_entra_no_total_sem_multa_auditada(self):
        orq = DiretorOrquestrador(
            buyer_analyzer=_BuyerVazio(),
            tax_analyzer=_TaxComCriticosSemValor(),
            pricing_analyzer=_PricingVazio(),
            compras_validator=_ComprasVazio(),
            financeiro_analyzer=_FinanceiroVazio(),
        )
        brief = await orq.gerar_brief()

        assert brief["impacto_total_rs"] == 0.0
        assert brief["achados"] == []
        assert len(brief["achados_sem_valor"]) == 1
        assert brief["achados_sem_valor"][0]["impacto_rs"] is None
        assert "multa" in brief["achados_sem_valor"][0]["achado"]

    @pytest.mark.asyncio
    async def test_todos_vazios_com_fonte_ok_sem_inventar(self):
        orq = DiretorOrquestrador(
            buyer_analyzer=_BuyerVazio(),
            tax_analyzer=_TaxVazio(),
            pricing_analyzer=_PricingVazio(),
            compras_validator=_ComprasVazio(),
            financeiro_analyzer=_FinanceiroVazio(),
        )
        brief = await orq.gerar_brief()

        assert len(brief["status_ias"]) == 5
        assert brief["achados"] == []
        assert brief["achados_sem_valor"] == []
        assert brief["impacto_total_rs"] == 0.0
        assert brief["pendencias"] == []
        assert "não há achados" in brief["mensagem"].lower() or "Nada foi inventado" in brief["mensagem"]
        for st in brief["status_ias"]:
            assert st["status"] in {"ok", "vazio"}
