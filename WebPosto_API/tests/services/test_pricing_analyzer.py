"""Testes para PricingAnalyzer - Precificador IA"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.services.pricing_ai.pricing_analyzer import (
    PricingAnalyzer,
    AnaliseMargem,
    SugestaoReajuste,
    PerdasOcultas,
)


@pytest.fixture
def mock_webposto_client():
    return AsyncMock()


@pytest.fixture
def mock_db_client():
    return MagicMock()


@pytest.fixture
def analyzer(mock_webposto_client, mock_db_client):
    return PricingAnalyzer(mock_webposto_client, mock_db_client)


class TestAnaliseMargem:
    """Testes de análise de margem"""

    @pytest.mark.asyncio
    async def test_margem_saudavel(self, analyzer):
        """Produto com margem saudável (>20%)"""
        resultado = await analyzer.analisar_margem_produto(
            "SKU_123",
            preco_venda=Decimal("100"),
            custo_produto=Decimal("60"),  # Margem: 40% bruta
            aliquota_icms=Decimal("12"),
        )

        assert resultado.produto_id == "SKU_123"
        assert resultado.margem_status == "SAUDÁVEL"
        assert resultado.margem_percentual > 20
        assert resultado.markup > 1.25

    @pytest.mark.asyncio
    async def test_margem_baixa(self, analyzer):
        """Produto com margem baixa (10-20%)"""
        resultado = await analyzer.analisar_margem_produto(
            "SKU_BAIXA",
            preco_venda=Decimal("100"),
            custo_produto=Decimal("85"),  # Margem: 15%
            aliquota_icms=Decimal("12"),
        )

        assert resultado.margem_status == "BAIXA"
        assert 10 < resultado.margem_percentual < 20
        assert "aumento de preço" in resultado.recomendacao.lower()

    @pytest.mark.asyncio
    async def test_margem_negativa(self, analyzer):
        """Produto com margem negativa"""
        resultado = await analyzer.analisar_margem_produto(
            "SKU_PROBLEMA",
            preco_venda=Decimal("50"),
            custo_produto=Decimal("60"),  # Custo > Preço
            aliquota_icms=Decimal("12"),
        )

        assert resultado.margem_status == "NEGATIVA"
        assert resultado.margem_percentual < 0
        assert "imediatamente" in resultado.recomendacao.lower()
        assert len(resultado.problemas) > 0

    @pytest.mark.asyncio
    async def test_margem_critica(self, analyzer):
        """Produto com margem crítica (< 10%)"""
        resultado = await analyzer.analisar_margem_produto(
            "SKU_CRITICA",
            preco_venda=Decimal("100"),
            custo_produto=Decimal("92"),  # Margem: 8%
            aliquota_icms=Decimal("12"),
        )

        assert resultado.margem_status == "CRÍTICA"
        assert resultado.margem_percentual < 10
        assert "urgente" in resultado.recomendacao.lower()

    @pytest.mark.asyncio
    async def test_markup_calculo(self, analyzer):
        """Validar cálculo de markup"""
        resultado = await analyzer.analisar_margem_produto(
            "SKU_MARKUP",
            preco_venda=Decimal("100"),
            custo_produto=Decimal("50"),
            aliquota_icms=Decimal("0"),  # Sem impostos para teste puro
        )

        # Markup deve ser: (100 / custo_total - 1) * 100
        assert resultado.markup > 0
        assert isinstance(resultado.markup, float)

    @pytest.mark.asyncio
    async def test_margem_com_impostos_diversos(self, analyzer):
        """Testar cálculo com diferentes alíquotas de imposto"""
        # Com 12% ICMS
        resultado_12 = await analyzer.analisar_margem_produto(
            "SKU_ICMS12",
            preco_venda=Decimal("100"),
            custo_produto=Decimal("70"),
            aliquota_icms=Decimal("12"),
        )

        # Com 7% ICMS
        resultado_7 = await analyzer.analisar_margem_produto(
            "SKU_ICMS7",
            preco_venda=Decimal("100"),
            custo_produto=Decimal("70"),
            aliquota_icms=Decimal("7"),
        )

        # Com menos impostos, margem deve ser maior
        assert resultado_7.margem_percentual > resultado_12.margem_percentual


class TestSugestaoReajuste:
    """Testes de sugestão de reajuste de preço"""

    @pytest.mark.asyncio
    async def test_sugestao_margem_negativa(self, analyzer):
        """Sugestão urgente para margem negativa"""
        sugestao = await analyzer.recomendar_reajuste_preco(
            "SKU_NEGATIVA",
            preco_atual=Decimal("50"),
            margem_atual_percentual=-10,  # Negativa!
            margem_alvo_percentual=25,
            velocidade_venda_mensal=100,
        )

        assert sugestao.preco_sugerido > sugestao.preco_atual
        assert sugestao.percentual_ajuste > 0
        assert sugestao.urgencia == "CRÍTICA"
        assert "negativa" in sugestao.motivo.lower()

    @pytest.mark.asyncio
    async def test_sugestao_margem_baixa(self, analyzer):
        """Sugestão para margem abaixo do mínimo"""
        sugestao = await analyzer.recomendar_reajuste_preco(
            "SKU_BAIXA",
            preco_atual=Decimal("100"),
            margem_atual_percentual=10,  # Abaixo de 20%
            margem_alvo_percentual=25,
            velocidade_venda_mensal=200,
        )

        assert sugestao.preco_sugerido > sugestao.preco_atual
        assert sugestao.urgencia == "ALTA"

    @pytest.mark.asyncio
    async def test_impacto_mensal_reajuste(self, analyzer):
        """Validar cálculo de impacto mensal"""
        sugestao = await analyzer.recomendar_reajuste_preco(
            "SKU_IMPACTO",
            preco_atual=Decimal("100"),
            margem_atual_percentual=15,
            margem_alvo_percentual=25,
            velocidade_venda_mensal=300,  # 300 unidades/mês
        )

        # Impacto = (novo_preco - preco_atual) * volume
        diferenca = sugestao.preco_sugerido - sugestao.preco_atual
        impacto_esperado = diferenca * Decimal("300")

        # Deve estar próximo do calculado
        assert abs(sugestao.impacto_mensal - impacto_esperado) < Decimal("10")

    @pytest.mark.asyncio
    async def test_preco_psicologico(self, analyzer):
        """Preço deve ser arredondado para valor psicológico (X.90, X.99)"""
        sugestao = await analyzer.recomendar_reajuste_preco(
            "SKU_PSICO",
            preco_atual=Decimal("100"),
            margem_atual_percentual=20,
            margem_alvo_percentual=25,
            velocidade_venda_mensal=100,
        )

        # Verificar se preço termina em .90 ou .99
        decimal = sugestao.preco_sugerido - int(sugestao.preco_sugerido)
        psicologico = decimal == Decimal("0.90") or decimal == Decimal("0.99")
        assert psicologico, f"Preço {sugestao.preco_sugerido} não é psicológico"

    @pytest.mark.asyncio
    async def test_pequeno_reajuste_margem_ok(self, analyzer):
        """Pequeno reajuste quando margem já está ok"""
        sugestao = await analyzer.recomendar_reajuste_preco(
            "SKU_OK",
            preco_atual=Decimal("100"),
            margem_atual_percentual=30,  # Já saudável
            margem_alvo_percentual=25,
            velocidade_venda_mensal=150,
        )

        assert sugestao.urgencia == "BAIXA"


class TestPerdasOcultas:
    """Testes de detecção de perdas ocultas"""

    @pytest.mark.asyncio
    async def test_detectar_obsoleto(self, analyzer):
        """Detectar produto obsoleto (>90 dias sem venda)"""
        perda = await analyzer.detectar_perdas_ocultas(
            "SKU_OBSOLETO",
            dias_sem_venda=120,
            quantidade_parada=500,
            custo_unitario=Decimal("10"),
        )

        assert perda.tipo == "OBSOLETO"
        assert perda.perda_estimada_mensal > 0
        assert "remoção" in perda.recomendacao.lower()

    @pytest.mark.asyncio
    async def test_detectar_baixa_rotacao(self, analyzer):
        """Detectar produto com baixa rotação (45-90 dias)"""
        perda = await analyzer.detectar_perdas_ocultas(
            "SKU_LENTO",
            dias_sem_venda=60,
            quantidade_parada=300,
            custo_unitario=Decimal("20"),
        )

        assert perda.tipo == "BAIXA_ROTACAO"
        assert perda.perda_estimada_mensal > 0
        assert "desconto" in perda.recomendacao.lower()

    @pytest.mark.asyncio
    async def test_detectar_composto_errado(self, analyzer):
        """Detectar possível erro de precificação/classificação"""
        perda = await analyzer.detectar_perdas_ocultas(
            "SKU_ERRADO",
            dias_sem_venda=10,
            quantidade_parada=1000,  # Muito estoque parado
            custo_unitario=Decimal("5"),
        )

        assert perda.tipo == "COMPOSTO_ERRADO"
        assert "preço" in perda.recomendacao.lower()

    @pytest.mark.asyncio
    async def test_sem_perdas_detectadas(self, analyzer):
        """Sem perdas quando produto tem rotação normal"""
        perda = await analyzer.detectar_perdas_ocultas(
            "SKU_BOM",
            dias_sem_venda=10,
            quantidade_parada=100,
            custo_unitario=Decimal("15"),
        )

        assert perda.tipo == ""
        assert perda.perda_estimada_mensal == Decimal("0")


class TestRelatorioAudit:
    """Testes de geração de relatório"""

    @pytest.mark.asyncio
    async def test_gerar_relatorio_precificacao(self, analyzer):
        """Sem fonte real de preço/custo o relatório declara fonte_indisponivel."""
        relatorio = await analyzer.gerar_relatorio_precificacao()

        assert relatorio["status"] == "fonte_indisponivel"
        assert "motivo" in relatorio
        assert "data_audit" in relatorio

    @pytest.mark.asyncio
    async def test_relatorio_status_critico(self, analyzer):
        """Relatório deve marcar status CRÍTICO quando há margens negativas"""
        analyzer.identificar_margens_negativas = AsyncMock(
            return_value=[
                AnaliseMargem(
                    produto_id="SKU_BAD",
                    descricao="Produto ruim",
                    preco_venda=Decimal("50"),
                    custo_total=Decimal("60"),
                    margem_bruta=Decimal("-10"),
                    margem_percentual=-20,
                    margem_status="NEGATIVA",
                    markup=-20,
                    problemas=["Margem negativa"],
                    recomendacao="Aumentar preço",
                )
            ]
        )
        analyzer.identificar_produtos_baixa_margem = AsyncMock(return_value=[])
        analyzer.gerar_sugestoes_reajuste = AsyncMock(return_value=[])
        analyzer.listar_perdas_ocultas = AsyncMock(
            return_value={"status": "fonte_indisponivel", "motivo": "teste"}
        )

        relatorio = await analyzer.gerar_relatorio_precificacao()

        assert relatorio["margens_negativas"] == 1
        assert relatorio["status"] == "CRÍTICO"

    @pytest.mark.asyncio
    async def test_relatorio_status_alerta(self, analyzer):
        """Relatório deve marcar ALERTA quando há muitos produtos com baixa margem"""
        analyzer.identificar_margens_negativas = AsyncMock(return_value=[])
        analyzer.identificar_produtos_baixa_margem = AsyncMock(
            return_value=[
                AnaliseMargem(
                    produto_id=f"SKU_{i}",
                    descricao="",
                    preco_venda=Decimal("100"),
                    custo_total=Decimal("85"),
                    margem_bruta=Decimal("15"),
                    margem_percentual=15,
                    margem_status="BAIXA",
                    markup=1.18,
                )
                for i in range(6)
            ]
        )
        analyzer.gerar_sugestoes_reajuste = AsyncMock(return_value=[])
        analyzer.listar_perdas_ocultas = AsyncMock(
            return_value={"status": "fonte_indisponivel", "motivo": "teste"}
        )

        relatorio = await analyzer.gerar_relatorio_precificacao()

        assert relatorio["margens_baixas"] == 6
        assert relatorio["status"] == "ALERTA"


class TestArredondamentoPsicologico:
    """Testes de arredondamento psicológico de preço"""

    def test_arredondar_para_90(self, analyzer):
        """Preço entre 0.30 e 0.60 deve arredondar para X.90"""
        preco = Decimal("50.45")
        arredondado = analyzer._arredondar_preco_psicologico(preco)

        assert arredondado == Decimal("50.90")

    def test_arredondar_para_99(self, analyzer):
        """Preço >= 0.60 deve arredondar para X.99"""
        preco = Decimal("50.70")
        arredondado = analyzer._arredondar_preco_psicologico(preco)

        assert arredondado == Decimal("50.99")

    def test_arredondar_para_90_baixo(self, analyzer):
        """Preço < 0.30 deve arredondar para X.90"""
        preco = Decimal("50.15")
        arredondado = analyzer._arredondar_preco_psicologico(preco)

        assert arredondado == Decimal("50.90")

    def test_arredondar_aumenta_inteiro(self, analyzer):
        """Arredondar para X.99 pode aumentar inteiro"""
        preco = Decimal("49.80")
        arredondado = analyzer._arredondar_preco_psicologico(preco)

        # Deve virar 50.99
        assert arredondado >= Decimal("50")


class TestIntegracaoCompleta:
    """Testes de integração entre componentes"""

    @pytest.mark.asyncio
    async def test_fluxo_completo_margem_negativa(self, analyzer):
        """Fluxo: detectar margem negativa → recomendar reajuste"""

        # 1. Analisar margem
        analise = await analyzer.analisar_margem_produto(
            "SKU_PROBLEMA",
            preco_venda=Decimal("50"),
            custo_produto=Decimal("60"),
        )

        assert analise.margem_status == "NEGATIVA"

        # 2. Recomendar reajuste
        sugestao = await analyzer.recomendar_reajuste_preco(
            "SKU_PROBLEMA",
            preco_atual=analise.preco_venda,
            margem_atual_percentual=analise.margem_percentual,
            margem_alvo_percentual=25,
        )

        # Novo preço deve ser maior
        assert sugestao.preco_sugerido > sugestao.preco_atual
        assert sugestao.urgencia == "CRÍTICA"
        assert sugestao.impacto_mensal > 0

    @pytest.mark.asyncio
    async def test_cenario_produto_boom(self, analyzer):
        """Cenário: Produto em boom (margem ok, muita venda)"""

        analise = await analyzer.analisar_margem_produto(
            "SKU_BOOM",
            preco_venda=Decimal("100"),
            custo_produto=Decimal("60"),
            aliquota_icms=Decimal("0"),
        )

        assert analise.margem_status == "SAUDÁVEL"

        sugestao = await analyzer.recomendar_reajuste_preco(
            "SKU_BOOM",
            preco_atual=Decimal("100"),
            margem_atual_percentual=analise.margem_percentual,
            margem_alvo_percentual=25,
            velocidade_venda_mensal=1000,
        )

        # Margem já acima do alvo → urgência baixa; impacto = Δpreço * volume
        assert sugestao.urgencia == "BAIXA"
        impacto_esperado = (sugestao.preco_sugerido - sugestao.preco_atual) * Decimal(
            "1000"
        )
        assert sugestao.impacto_mensal == impacto_esperado
