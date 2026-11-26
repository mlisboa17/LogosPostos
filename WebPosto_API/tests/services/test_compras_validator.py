"""Testes para ComprasValidator"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.services.data_validation.compras_validator import ComprasValidator


@pytest.fixture
def mock_webposto_client():
    """Mock do cliente WebPostos"""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_db_client():
    """Mock do cliente de banco de dados"""
    db = MagicMock()
    return db


@pytest.fixture
def validator(mock_webposto_client, mock_db_client):
    """Instância do validador"""
    return ComprasValidator(mock_webposto_client, mock_db_client)


class TestCompraItemValidation:
    """Testes de validação de itens de compra"""

    @pytest.mark.asyncio
    async def test_valid_compra_item(self, validator):
        """Validar item correto"""
        item = {
            "id": "ITEM_123",
            "produto_id": "SKU_456",
            "valor": 1000,
            "frete": 100,
            "imposto": 50,
            "quantidade": 10,
            "data_compra": datetime.now().isoformat(),
        }

        resultado = await validator.validate_compra_item(item)

        assert resultado.is_valid is True
        assert resultado.custo_real == Decimal("115")  # (1000+100+50)/10
        assert len(resultado.problemas) == 0

    @pytest.mark.asyncio
    async def test_invalid_quantidade_zero(self, validator):
        """Quantidade = 0 é inválida"""
        item = {
            "id": "ITEM_123",
            "produto_id": "SKU_456",
            "valor": 1000,
            "frete": 100,
            "imposto": 50,
            "quantidade": 0,
            "data_compra": datetime.now().isoformat(),
        }

        resultado = await validator.validate_compra_item(item)

        assert resultado.is_valid is False
        assert any("quantidade" in p.lower() for p in resultado.problemas)

    @pytest.mark.asyncio
    async def test_invalid_quantidade_negativa(self, validator):
        """Quantidade negativa é inválida"""
        item = {
            "id": "ITEM_123",
            "produto_id": "SKU_456",
            "valor": 1000,
            "frete": 100,
            "imposto": 50,
            "quantidade": -5,
            "data_compra": datetime.now().isoformat(),
        }

        resultado = await validator.validate_compra_item(item)

        assert resultado.is_valid is False

    @pytest.mark.asyncio
    async def test_negative_valor(self, validator):
        """Valor negativo não é permitido"""
        item = {
            "id": "ITEM_123",
            "produto_id": "SKU_456",
            "valor": -1000,  # Negativo!
            "frete": 100,
            "imposto": 50,
            "quantidade": 10,
            "data_compra": datetime.now().isoformat(),
        }

        resultado = await validator.validate_compra_item(item)

        assert resultado.is_valid is False
        assert any("valor" in p.lower() for p in resultado.problemas)

    @pytest.mark.asyncio
    async def test_invalid_data(self, validator):
        """Data inválida"""
        item = {
            "id": "ITEM_123",
            "produto_id": "SKU_456",
            "valor": 1000,
            "frete": 100,
            "imposto": 50,
            "quantidade": 10,
            "data_compra": "data_invalida",
        }

        resultado = await validator.validate_compra_item(item)

        assert resultado.is_valid is False
        assert any("data" in p.lower() for p in resultado.problemas)

    @pytest.mark.asyncio
    async def test_preco_outlier_deteccao(self, validator):
        """Detectar preço divergindo > 20% do histórico"""
        item = {
            "id": "ITEM_123",
            "produto_id": "SKU_456",
            "valor": 5000,  # Muito caro!
            "frete": 0,
            "imposto": 0,
            "quantidade": 10,
            "data_compra": datetime.now().isoformat(),
        }

        # Mock: custo histórico é 100, novo é 500 (+400%)
        validator._get_historical_cost = AsyncMock(return_value=Decimal("100"))

        resultado = await validator.validate_compra_item(item)

        # Custo real = 5000/10 = 500
        # Diferença = 500-100 = 400 (+400%)
        assert resultado.diferenca_percentual > 20
        assert any("custo divergiu" in p.lower() for p in resultado.problemas)


class TestPriceOutlierDetection:
    """Testes de detecção de outliers de preço"""

    @pytest.mark.asyncio
    async def test_no_outliers_preco_estavel(self, validator, mock_webposto_client):
        """Sem outliers se preço é estável"""
        compras = [
            {
                "fornecedor_id": "FOR_123",
                "itens": [
                    {"produto_id": "SKU_456", "preco_unitario": 100},
                    {"produto_id": "SKU_456", "preco_unitario": 102},
                    {"produto_id": "SKU_456", "preco_unitario": 101},
                ],
            }
        ]
        mock_webposto_client.get = AsyncMock(return_value=compras)

        outliers = await validator.detect_price_outliers("FOR_123")

        assert len(outliers) == 0

    @pytest.mark.asyncio
    async def test_detecta_preco_extremo(self, validator, mock_webposto_client):
        """Detectar preço extremo"""
        compras = [
            {
                "fornecedor_id": "FOR_123",
                "itens": [
                    {"produto_id": "SKU_456", "preco_unitario": 100},
                    {"produto_id": "SKU_456", "preco_unitario": 101},
                    {"produto_id": "SKU_456", "preco_unitario": 102},
                    {"produto_id": "SKU_456", "preco_unitario": 500},  # Outlier!
                ],
            }
        ]
        mock_webposto_client.get = AsyncMock(return_value=compras)

        outliers = await validator.detect_price_outliers("FOR_123", sensitivity=1.5)

        assert len(outliers) == 1
        assert outliers[0]["produto_id"] == "SKU_456"
        assert outliers[0]["preco"] == 500
        assert outliers[0]["severidade"] in ["ALTA", "MÉDIA"]


class TestDataQualityReport:
    """Testes de relatório de qualidade de dados"""

    @pytest.mark.asyncio
    async def test_relatorio_dados_perfeitos(
        self, validator, mock_webposto_client
    ):
        """Relatório quando todos os dados estão corretos"""
        data_inicial = (datetime.now() - timedelta(days=30)).isoformat()
        data_final = datetime.now().isoformat()

        compras = [
            {
                "fornecedor_id": "FOR_123",
                "data": data_inicial,
                "itens": [
                    {
                        "id": "ITEM_1",
                        "produto_id": "SKU_456",
                        "valor": 1000,
                        "frete": 100,
                        "imposto": 50,
                        "quantidade": 10,
                        "data_compra": data_inicial,
                    }
                ],
            }
        ]

        mock_webposto_client.get = AsyncMock(return_value=compras)
        validator._get_historical_cost = AsyncMock(return_value=Decimal("115"))
        validator.detect_price_outliers = AsyncMock(return_value=[])

        relatorio = await validator.generate_data_quality_report(
            data_inicial, data_final
        )

        assert relatorio["status"] == "PRONTO_PARA_IA"
        assert relatorio["cobertura_dados_percentual"] == 100.0
        assert relatorio["compras_com_problema"] == 0
        assert len(relatorio["recomendacoes"]) == 0

    @pytest.mark.asyncio
    async def test_relatorio_muitos_problemas(
        self, validator, mock_webposto_client
    ):
        """Relatório quando há muitos problemas"""
        data_inicial = (datetime.now() - timedelta(days=30)).isoformat()
        data_final = datetime.now().isoformat()

        # 10 compras, 8 com problema
        compras = []
        for i in range(10):
            compras.append(
                {
                    "fornecedor_id": f"FOR_{i}",
                    "data": data_inicial,
                    "itens": [
                        {
                            "id": f"ITEM_{i}",
                            "produto_id": f"SKU_{i}",
                            "valor": -1000 if i < 8 else 1000,  # 8 negativas
                            "frete": 100,
                            "imposto": 50,
                            "quantidade": 10,
                            "data_compra": data_inicial,
                        }
                    ],
                }
            )

        mock_webposto_client.get = AsyncMock(return_value=compras)
        validator._get_historical_cost = AsyncMock(return_value=Decimal("115"))
        validator.detect_price_outliers = AsyncMock(return_value=[])

        relatorio = await validator.generate_data_quality_report(
            data_inicial, data_final
        )

        assert relatorio["status"] == "REQUER_REVISAO"
        assert relatorio["compras_com_problema"] == 8
        assert len(relatorio["recomendacoes"]) > 0


class TestConsistencyValidation:
    """Testes de validação de consistência"""

    @pytest.mark.asyncio
    async def test_consistencia_ok_entrada_igual_compra(
        self, validator, mock_webposto_client
    ):
        """Consistência OK: comprei 100 e estoque recebeu 100"""
        data_compra = datetime.now().isoformat()

        compra = {
            "id": "COMPRA_123",
            "data": data_compra,
            "itens": [
                {
                    "produto_id": "SKU_456",
                    "quantidade": 100,
                }
            ],
        }

        estoques = [
            {
                "entrada": 100,
            }
        ]

        mock_webposto_client.get = AsyncMock(
            side_effect=[compra, estoques]  # Primeira chamada: compra, segunda: estoque
        )

        problemas = await validator.validate_consistency("COMPRA_123")

        assert len(problemas) == 0

    @pytest.mark.asyncio
    async def test_consistencia_falta_compra_em_estoque(
        self, validator, mock_webposto_client
    ):
        """Inconsistência: comprei 100 mas estoque recebeu 80"""
        data_compra = datetime.now().isoformat()

        compra = {
            "id": "COMPRA_123",
            "data": data_compra,
            "itens": [
                {
                    "produto_id": "SKU_456",
                    "quantidade": 100,
                }
            ],
        }

        estoques = [
            {
                "entrada": 80,  # Menos!
            }
        ]

        mock_webposto_client.get = AsyncMock(
            side_effect=[compra, estoques]
        )

        problemas = await validator.validate_consistency("COMPRA_123")

        assert len(problemas) > 0
        assert any("diferença" in p.lower() for p in problemas)
