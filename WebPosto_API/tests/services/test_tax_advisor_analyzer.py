"""Testes para TaxAdvisorAnalyzer - Tax Advisor IA"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.services.tax_ai.tax_advisor_analyzer import TaxAdvisorAnalyzer


@pytest.fixture
def mock_webposto_client():
    return AsyncMock()


@pytest.fixture
def mock_db_client():
    return MagicMock()


@pytest.fixture
def analyzer(mock_webposto_client, mock_db_client):
    return TaxAdvisorAnalyzer(mock_webposto_client, mock_db_client)


class TestNCMValidation:
    """Testes de validação de NCM"""

    @pytest.mark.asyncio
    async def test_valid_ncm(self, analyzer):
        """NCM válido"""
        resultado = await analyzer.validate_ncm("SKU_123", "27160000")

        # Nota: 27160000 está na tabela de exemplo
        assert resultado["ncm"] == "27160000"
        assert resultado["is_valid"] is True
        assert resultado["fonte_tabela"] == "exemplo_local"
        assert len(resultado["problemas"]) == 0
        assert resultado["avisos"] == []

    @pytest.mark.asyncio
    async def test_ncm_formato_invalido_poucos_digitos(self, analyzer):
        """NCM com menos de 8 dígitos"""
        resultado = await analyzer.validate_ncm("SKU_123", "2716000")  # Faltam 1 dígito

        assert resultado["is_valid"] is False
        assert any("8 dígitos" in p for p in resultado["problemas"])

    @pytest.mark.asyncio
    async def test_ncm_formato_invalido_nao_numerico(self, analyzer):
        """NCM com caracteres não numéricos"""
        resultado = await analyzer.validate_ncm("SKU_123", "2716000A")

        assert resultado["is_valid"] is False
        assert any("dígitos" in p for p in resultado["problemas"])

    @pytest.mark.asyncio
    async def test_ncm_vazio(self, analyzer):
        """NCM vazio"""
        resultado = await analyzer.validate_ncm("SKU_123", "")

        assert resultado["is_valid"] is False
        assert len(resultado["problemas"]) > 0

    @pytest.mark.asyncio
    async def test_ncm_ausente_na_tabela_exemplo_nao_e_erro_definitivo(self, analyzer):
        """NCM com formato ok fora da amostra local: aviso, não erro fiscal definitivo."""
        resultado = await analyzer.validate_ncm("SKU_123", "12345678")

        assert resultado["is_valid"] is True
        assert resultado["fonte_tabela"] == "exemplo_local"
        assert len(resultado["problemas"]) == 0
        assert any("exemplo_local" in a for a in resultado["avisos"])


class TestCESTValidation:
    """Testes de validação de CEST"""

    @pytest.mark.asyncio
    async def test_cest_vazio_valido(self, analyzer):
        """CEST vazio é válido (produto sem substituição)"""
        resultado = await analyzer.validate_cest("SKU_123", "")

        assert resultado["is_valid"] is True
        assert resultado["tipo"] == "SEM_CEST"

    @pytest.mark.asyncio
    async def test_cest_valido(self, analyzer):
        """CEST válido"""
        resultado = await analyzer.validate_cest("SKU_123", "0100100")

        assert resultado["is_valid"] is True
        assert resultado["tipo"] == "COM_CEST"

    @pytest.mark.asyncio
    async def test_cest_formato_invalido(self, analyzer):
        """CEST com formato errado"""
        resultado = await analyzer.validate_cest("SKU_123", "010010")  # Faltam 1 dígito

        assert resultado["is_valid"] is False
        assert any("7 dígitos" in p for p in resultado["problemas"])

    @pytest.mark.asyncio
    async def test_cest_nao_numerico(self, analyzer):
        """CEST com caracteres não numéricos"""
        resultado = await analyzer.validate_cest("SKU_123", "010010A")

        assert resultado["is_valid"] is False


class TestCSTICMSValidation:
    """Testes de validação de CST ICMS"""

    @pytest.mark.asyncio
    async def test_cst_valido_simples(self, analyzer):
        """CST válido para regime Simples"""
        resultado = await analyzer.validate_cst_icms(
            "SKU_123", "00", regime="SIMPLES"
        )

        assert resultado["is_valid"] is True
        assert resultado["cst_icms"] == "00"

    @pytest.mark.asyncio
    async def test_cst_invalido_para_regime(self, analyzer):
        """CST inválido para regime (00 não existe em Lucro Real)"""
        resultado = await analyzer.validate_cst_icms(
            "SKU_123", "99", regime="SIMPLES"  # 99 não existe em Simples
        )

        assert resultado["is_valid"] is False
        assert any("regime" in p.lower() for p in resultado["problemas"])

    @pytest.mark.asyncio
    async def test_cst_formato_invalido(self, analyzer):
        """CST com formato errado"""
        resultado = await analyzer.validate_cst_icms("SKU_123", "0", regime="SIMPLES")

        assert resultado["is_valid"] is False
        assert any("2 dígitos" in p for p in resultado["problemas"])


class TestTaxDivergenceDetection:
    """Testes de detecção de divergências tributárias"""

    @pytest.mark.asyncio
    async def test_detect_ncm_inconsistente(
        self, analyzer, mock_webposto_client
    ):
        """Detectar mesmo produto com NCMs diferentes"""

        # Mock: mesmo produto com NCMs diferentes
        notas = [
            {
                "itens": [
                    {
                        "produto_id": "SKU_PROBLEMA",
                        "ncm": "27160000",
                        "cst_icms": "00",
                    },
                    {
                        "produto_id": "SKU_PROBLEMA",
                        "ncm": "27160001",  # NCM DIFERENTE!
                        "cst_icms": "00",
                    },
                ]
            }
        ]

        mock_webposto_client.get.return_value = notas

        divergencias = await analyzer.detect_tax_divergences()

        # Deve detectar a inconsistência
        assert len(divergencias) > 0
        ncm_issues = [d for d in divergencias if "NCM" in d["tipo"]]
        assert len(ncm_issues) > 0

    @pytest.mark.asyncio
    async def test_no_divergencias_quando_consistente(
        self, analyzer, mock_webposto_client
    ):
        """Sem divergências quando classificação é consistente"""

        # Mock: mesmo produto sempre com mesmo NCM
        notas = [
            {
                "itens": [
                    {
                        "produto_id": "SKU_OK",
                        "ncm": "27160000",
                        "cst_icms": "00",
                    },
                    {
                        "produto_id": "SKU_OK",
                        "ncm": "27160000",  # Mesmo NCM
                        "cst_icms": "00",
                    },
                ]
            }
        ]

        mock_webposto_client.get.return_value = notas

        divergencias = await analyzer.detect_tax_divergences()

        # Não deve haver divergências
        assert len(divergencias) == 0


class TestTaxCalculation:
    """Testes de cálculo de impostos"""

    @pytest.mark.asyncio
    async def test_validate_tax_calculation(self, analyzer):
        """Validar cálculo de ICMS/PIS/COFINS"""

        base = Decimal("1000")  # R$ 1000
        resultado = await analyzer.validate_tax_calculation(
            "SKU_123", "27160000", "PE", base
        )

        assert resultado["base_calculo"] == 1000.0
        assert resultado["icms"] > 0  # Deve ter ICMS
        assert resultado["pis"] > 0  # Deve ter PIS
        assert resultado["cofins"] > 0  # Deve ter COFINS
        assert resultado["total_impostos"] > 0
        assert resultado["percentual_impostos"] > 0

    @pytest.mark.asyncio
    async def test_tax_calculation_exemplo_concreto(self, analyzer):
        """Teste com números conhecidos"""

        # Base: R$ 1000
        # ICMS: 12%
        # PIS: 1.65%
        # COFINS: 7.6%
        # Total: 21.25%

        base = Decimal("1000")
        resultado = await analyzer.validate_tax_calculation(
            "SKU_COMBUSTIVEL", "27160000", "PE", base
        )

        # Esperado: R$ 212.50 de impostos
        assert resultado["total_impostos"] == pytest.approx(212.5, rel=1)


class TestUnclassifiedProducts:
    """Testes de detecção de produtos sem classificação"""

    @pytest.mark.asyncio
    async def test_find_produtos_sem_ncm(self, analyzer, mock_webposto_client):
        """Encontrar produtos sem NCM"""

        produtos = [
            {
                "produto_id": "SKU_OK",
                "descricao": "Produto OK",
                "ncm": "27160000",
                "cest": "0100100",
            },
            {
                "produto_id": "SKU_SEM_NCM",
                "descricao": "Produto sem NCM",
                "ncm": "",  # Sem NCM!
                "cest": "",
            },
        ]

        mock_webposto_client.get.return_value = produtos

        sem_classificacao = await analyzer.find_unclassified_products()

        # Deve encontrar 1 produto
        assert len(sem_classificacao) == 1
        assert sem_classificacao[0]["produto_id"] == "SKU_SEM_NCM"


class TestTaxAuditReport:
    """Testes de geração de relatório"""

    @pytest.mark.asyncio
    async def test_generate_tax_audit_report(self, analyzer, mock_webposto_client):
        """Gerar relatório consolidado"""

        # Mock: sem problemas
        mock_webposto_client.get.side_effect = [[], []]

        report = await analyzer.generate_tax_audit_report()

        assert "data_audit" in report
        assert "estado" in report
        assert "regime" in report
        assert "problemas_encontrados" in report
        assert "recomendacoes" in report
        assert "status" in report
        assert report["risco_fiscal"]["status"] == "nao_estimado"
        assert "multa" in report["risco_fiscal"]["motivo"]

    @pytest.mark.asyncio
    async def test_report_status_critico_quando_ha_problemas(
        self, analyzer, mock_webposto_client
    ):
        """Relatório deve indicar CRÍTICO quando há problemas"""

        # Mock com divergências
        divergencias = [
            {
                "tipo": "NCM_INCONSISTENTE",
                "severidade": "ALTA",
                "produto_id": "SKU_BAD",
            }
        ]

        mock_webposto_client.get.side_effect = [[], []]
        analyzer.detect_tax_divergences = AsyncMock(return_value=divergencias)

        report = await analyzer.generate_tax_audit_report()

        assert report["problemas_encontrados"] > 0
        assert report["problemas_criticos"] > 0
        assert report["status"] == "CRÍTICO"
        assert report["risco_fiscal"]["status"] == "nao_estimado"
        assert "risco_fiscal_estimado" not in report
