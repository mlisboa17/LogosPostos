"""Testes para BuyerAnalyzer - Comprador IA"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.services.buyer_ai.buyer_analyzer import BuyerAnalyzer


@pytest.fixture
def mock_webposto_client():
    """Mock do cliente WebPostos"""
    return AsyncMock()


@pytest.fixture
def mock_db_client():
    """Mock do cliente de banco de dados"""
    return MagicMock()


@pytest.fixture
def analyzer(mock_webposto_client, mock_db_client):
    """Instância do analisador"""
    return BuyerAnalyzer(mock_webposto_client, mock_db_client)


class TestCapitalPardoAnalysis:
    """Testes de análise de capital parado"""

    @pytest.mark.asyncio
    async def test_find_immobilized_capital(self, analyzer, mock_webposto_client):
        """Identificar produtos parados"""

        # Mock: 1 produto com 500un, sem venda há 45+ dias
        estoques = [
            {
                "produto_id": "SKU_123",
                "descricao": "Bebida Energética 250ml",
                "quantidade": 500,
                "custo_unitario": 2.5,
            }
        ]

        # Sem vendas no período
        vendas_vazias = []

        mock_webposto_client.get.side_effect = [estoques, vendas_vazias]

        resultado = await analyzer.find_immobilized_capital()

        assert len(resultado) == 1
        assert resultado[0]["produto_id"] == "SKU_123"
        assert resultado[0]["quantidade"] == 500
        assert resultado[0]["capital_parado"] == 1250.0
        assert resultado[0]["urgencia"] == "MÉDIA"

    @pytest.mark.asyncio
    async def test_capital_parado_alto_prioridade_critica(
        self, analyzer, mock_webposto_client
    ):
        """Capital parado > R$ 5000 = urgência ALTA"""

        estoques = [
            {
                "produto_id": "SKU_CARO",
                "descricao": "Produto Caro",
                "quantidade": 1000,
                "custo_unitario": 10.0,  # Capital = 10k
            }
        ]

        mock_webposto_client.get.side_effect = [estoques, []]

        resultado = await analyzer.find_immobilized_capital()

        assert len(resultado) == 1
        assert resultado[0]["capital_parado"] == 10000.0
        assert resultado[0]["urgencia"] == "ALTA"

    @pytest.mark.asyncio
    async def test_no_capital_parado_quando_tem_venda(
        self, analyzer, mock_webposto_client
    ):
        """Produto COM venda = não é problema"""

        estoques = [
            {
                "produto_id": "SKU_OK",
                "descricao": "Produto OK",
                "quantidade": 100,
                "custo_unitario": 5.0,
            }
        ]

        vendas = [
            {
                "itens": [
                    {
                        "produto_id": "SKU_OK",
                        "quantidade": 50,
                    }
                ]
            }
        ]

        mock_webposto_client.get.side_effect = [estoques, vendas]

        resultado = await analyzer.find_immobilized_capital()

        assert len(resultado) == 0


class TestRuptureRiskAnalysis:
    """Testes de previsão de rupturas"""

    @pytest.mark.asyncio
    async def test_find_rupture_risk_produto_em_risco(
        self, analyzer, mock_webposto_client
    ):
        """Detectar produto em risco de ruptura"""

        estoques = [
            {
                "produto_id": "SKU_CAFE",
                "descricao": "Café 500g",
                "quantidade": 50,  # Pouquinho
                "custo_unitario": 10.0,
                "preco_venda": 15.0,
                "fornecedor_id": "FOR_A",
            }
        ]

        # Consumo nos últimos 30 dias: 600 un = 20/dia
        vendas = [
            {
                "itens": [
                    {
                        "produto_id": "SKU_CAFE",
                        "quantidade": 600,  # 20/dia em média
                    }
                ]
            }
        ]

        fornecedores = [
            {
                "id": "FOR_A",
                "nome": "Fornecedor A",
            }
        ]

        mock_webposto_client.get.side_effect = [estoques, vendas, fornecedores]

        resultado = await analyzer.find_rupture_risk()

        assert len(resultado) > 0
        ruptura = resultado[0]
        assert ruptura["produto_id"] == "SKU_CAFE"
        assert ruptura["dias_de_estoque"] < 5  # 50 / 20 = 2.5 dias
        # Formula: (1 - dias_de_estoque / dias_reabastecimento) * 100 = (1 - 2.5/5) * 100
        assert ruptura["rupture_probability"] == pytest.approx(50.0)
        assert ruptura["urgencia"] == "CRÍTICA"

    @pytest.mark.asyncio
    async def test_no_rupture_quando_estoque_bom(
        self, analyzer, mock_webposto_client
    ):
        """Sem risco quando estoque é bom"""

        estoques = [
            {
                "produto_id": "SKU_OK",
                "descricao": "Produto OK",
                "quantidade": 500,  # Muito
                "custo_unitario": 5.0,
                "preco_venda": 10.0,
                "fornecedor_id": "FOR_A",
            }
        ]

        # Consumo baixo
        vendas = [
            {
                "itens": [
                    {
                        "produto_id": "SKU_OK",
                        "quantidade": 100,  # 3/dia
                    }
                ]
            }
        ]

        fornecedores = [
            {
                "id": "FOR_A",
                "nome": "Fornecedor A",
            }
        ]

        mock_webposto_client.get.side_effect = [estoques, vendas, fornecedores]

        resultado = await analyzer.find_rupture_risk()

        # 500 un / (~100/30) ~ 150 dias de estoque >> lead 5 -> sem ruptura
        assert resultado == []


class TestReplenishmentRecommendation:
    """Testes de recomendação de reposição"""

    @pytest.mark.asyncio
    async def test_recommend_replenishment_produto_em_risco(
        self, analyzer, mock_webposto_client
    ):
        """Recomendar reposição para produto em risco"""

        # Mock: find_rupture_risk retorna produto em risco
        analyzer.find_rupture_risk = AsyncMock(
            return_value=[
                {
                    "produto_id": "SKU_CAFE",
                    "descricao": "Café 500g",
                    "estoque_atual": 50,
                    "consumo_diario": 20.0,
                    "dias_de_estoque": 2.5,
                    "tempo_reabastecimento_dias": 5,
                    "rupture_probability": 95,
                    "data_provavel_ruptura": "2024-08-23",
                    "vendas_perdidas_estimadas": 5000,
                }
            ]
        )

        # Mock: find_immobilized_capital vazio
        analyzer.find_immobilized_capital = AsyncMock(return_value=[])

        resultado = await analyzer.recommend_replenishment()

        assert len(resultado) > 0
        recomendacao = resultado[0]
        assert recomendacao["produto_id"] == "SKU_CAFE"
        assert recomendacao["prioridade"] == 1
        assert recomendacao["quantidade_sugerida"] > 0
        assert recomendacao["economia_potencial"] > 0
        assert recomendacao["origem_dado"] == "padrao_fixo"
        assert recomendacao["origem_preco"] == "padrao_fixo"
        assert recomendacao["preco_esperado"] == 5.0


class TestBuyVsSellAnalysis:
    """Testes de análise compras vs vendas"""

    @pytest.mark.asyncio
    async def test_comprado_demais_nao_vendeu(
        self, analyzer, mock_webposto_client
    ):
        """Detectar produto comprado mas não vendido"""

        # Comprado 1000 un
        compras = [
            {
                "itens": [
                    {
                        "produto_id": "SKU_FAIL",
                        "quantidade": 1000,
                        "preco_unitario": 5.0,
                    }
                ]
            }
        ]

        # Não vendeu nada
        vendas = []

        mock_webposto_client.get.side_effect = [compras, vendas]

        resultado = await analyzer.analyze_buy_vs_sell_mismatch(periodo_dias=30)

        assert len(resultado["produtos_comprado_demais"]) == 1
        produto = resultado["produtos_comprado_demais"][0]
        assert produto["produto_id"] == "SKU_FAIL"
        assert produto["comprado_ultimo_mes"] == 1000
        assert produto["vendido_ultimo_mes"] == 0
        assert produto["capital_parado"] == 5000.0

    @pytest.mark.asyncio
    async def test_comprado_pouco_vendeu_muito(
        self, analyzer, mock_webposto_client
    ):
        """Detectar produto comprado pouco mas vendido muito"""

        # Comprado 100 un
        compras = [
            {
                "itens": [
                    {
                        "produto_id": "SKU_SUCCESS",
                        "quantidade": 100,
                        "preco_unitario": 5.0,
                    }
                ]
            }
        ]

        # Vendeu 500 un
        vendas = [
            {
                "itens": [
                    {
                        "produto_id": "SKU_SUCCESS",
                        "quantidade": 500,
                        "preco_venda": 10.0,
                    }
                ]
            }
        ]

        mock_webposto_client.get.side_effect = [compras, vendas]

        resultado = await analyzer.analyze_buy_vs_sell_mismatch(periodo_dias=30)

        assert len(resultado["produtos_comprado_pouco"]) == 1
        produto = resultado["produtos_comprado_pouco"][0]
        assert produto["produto_id"] == "SKU_SUCCESS"
        assert produto["comprado_ultimo_mes"] == 100
        assert produto["vendido_ultimo_mes"] == 500
        assert produto["deficit"] == 400
        assert produto["vendas_perdidas_potenciais"] == 4000.0


class TestExecutiveBrief:
    """Testes de relatório executivo"""

    @pytest.mark.asyncio
    async def test_generate_executive_brief(
        self, analyzer, mock_webposto_client
    ):
        """Gerar brief consolidado"""

        # Mock de todas análises
        analyzer.find_immobilized_capital = AsyncMock(
            return_value=[
                {
                    "produto_id": "SKU_PARADO",
                    "capital_parado": 5000,
                }
            ]
        )

        analyzer.find_rupture_risk = AsyncMock(
            return_value=[
                {
                    "produto_id": "SKU_RUPTURA",
                    "vendas_perdidas_estimadas": 10000,
                }
            ]
        )

        analyzer.recommend_replenishment = AsyncMock(
            return_value=[
                {
                    "produto_id": "SKU_COMPRAR",
                    "economia_potencial": 5000,
                }
            ]
        )

        analyzer.analyze_buy_vs_sell_mismatch = AsyncMock(
            return_value={
                "produtos_comprado_demais": [],
                "produtos_comprado_pouco": [],
                "capital_parado_total": 3000,
                "vendas_perdidas_total": 7000,
            }
        )

        brief = await analyzer.generate_executive_brief()

        assert brief["findings_count"] > 0
        assert brief["economia_potencial_total"] > 0
        assert len(brief["top_problemas"]) > 0
        assert len(brief["proximas_acoes"]) > 0
