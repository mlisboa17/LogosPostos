"""
Testes unitários para modelos e serviços de auditoria
pytest + pytest-asyncio
"""

from unittest.mock import AsyncMock, patch

import pytest
import webposto_client as wp_mod
from datetime import datetime
from pydantic import ValidationError
from models_auditoria import (
    CategoriaDesapesa,
    DespesaCaixa,
    EspecieFinanceira,
    FechamentoCaixa,
    MovimentacaoEspecie,
    StatusCaixa,
    StatusJustificativa,
    TipoCaixa,
)
from servicos_auditoria import AuditoriaService


# ============ TESTES DE MODELOS ============
class TestDespesaCaixa:
    """Testes para modelo DespesaCaixa"""

    def test_criar_despesa_valida(self):
        """✓ Criar despesa com valores válidos"""
        despesa = DespesaCaixa(
            id="exp_test_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario=datetime.now(),
            categoria=CategoriaDesapesa.GELO,
            valor=100.50,
            operador="João",
        )
        assert despesa.valor == 100.50
        assert despesa.status_justificativa == StatusJustificativa.PENDENTE

    def test_despesa_valor_negativo(self):
        """✗ Rejeitar valor negativo"""
        with pytest.raises(ValidationError) as exc_info:
            DespesaCaixa(
                id="exp_bad_001",
                unidade_id=1,
                caixa_tipo=TipoCaixa.PISTA,
                horario=datetime.now(),
                categoria=CategoriaDesapesa.LUZ,
                valor=-50.00,  # Inválido
                operador="João",
            )
        assert "greater than 0" in str(exc_info.value)

    def test_despesa_valor_arredondado(self):
        """✓ Valor arredondado para 2 casas decimais"""
        despesa = DespesaCaixa(
            id="exp_round_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario=datetime.now(),
            categoria=CategoriaDesapesa.LUZ,
            valor=99.999,
            operador="João",
        )
        assert despesa.valor == 100.00

    def test_despesa_categoria_obrigatoria(self):
        """✗ Categoria obrigatória"""
        with pytest.raises(ValidationError):
            DespesaCaixa(
                id="exp_no_cat_001",
                unidade_id=1,
                caixa_tipo=TipoCaixa.PISTA,
                horario=datetime.now(),
                categoria=None,  # Inválido
                valor=100.00,
                operador="João",
            )

    def test_despesa_enum_categoria(self):
        """✗ Categoria deve ser do enum"""
        with pytest.raises(ValidationError):
            DespesaCaixa(
                id="exp_bad_cat_001",
                unidade_id=1,
                caixa_tipo=TipoCaixa.PISTA,
                horario=datetime.now(),
                categoria="categoria_invalida",  # Não existe no enum
                valor=100.00,
                operador="João",
            )


class TestMovimentacaoEspecie:
    """Testes para MovimentacaoEspecie"""

    def test_movimento_calcula_diferenca(self):
        """✓ Diferença calculada automaticamente"""
        mov = MovimentacaoEspecie(
            especie=EspecieFinanceira.DINHEIRO,
            valor_esperado=1000.00,
            valor_informado=950.00,
        )
        assert mov.diferenca == 50.00

    def test_movimento_calcula_variacao_percentual(self):
        """✓ Variação % calculada automaticamente"""
        mov = MovimentacaoEspecie(
            especie=EspecieFinanceira.DINHEIRO,
            valor_esperado=1000.00,
            valor_informado=950.00,
        )
        assert mov.variacao_percentual == 5.00

    def test_movimento_sem_diferenca(self):
        """✓ Quando valores são iguais"""
        mov = MovimentacaoEspecie(
            especie=EspecieFinanceira.PIX, valor_esperado=500.00, valor_informado=500.00
        )
        assert mov.diferenca == 0.0
        assert mov.variacao_percentual == 0.0

    def test_movimento_variacao_zero_quando_esperado_zero(self):
        """✓ Proteção contra divisão por zero"""
        mov = MovimentacaoEspecie(
            especie=EspecieFinanceira.DINHEIRO,
            valor_esperado=0.0,
            valor_informado=100.00,
        )
        assert mov.variacao_percentual == 0.0  # Não quebra


class TestFechamentoCaixa:
    """Testes para FechamentoCaixa"""

    def test_fechamento_calcula_quebra(self):
        """✓ Quebra calculada automaticamente"""
        fechamento = FechamentoCaixa(
            id="fech_test_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario_abertura=datetime(2026, 4, 12, 7, 0),
            horario_fechamento=datetime(2026, 4, 12, 23, 0),
            faturamento_bruto=5000.00,
            despesas_caixa_total=200.00,
            saldo_esperado_dinheiro=2500.00,
            saldo_informado_dinheiro=2490.00,
            operador_fechamento="Maria",
            status=StatusCaixa.FECHADO,
        )
        assert fechamento.quebra_caixa == 10.00

    def test_fechamento_obrigatorio_operador(self):
        """✗ Operador obrigatório"""
        with pytest.raises(ValidationError):
            FechamentoCaixa(
                id="fech_no_op_001",
                unidade_id=1,
                caixa_tipo=TipoCaixa.PISTA,
                horario_abertura=datetime.now(),
                horario_fechamento=datetime.now(),
                operador_fechamento=None,  # Inválido
            )

    def test_fechamento_com_movimentacoes(self):
        """✓ Fechamento com múltiplas movimentações"""
        movs = [
            MovimentacaoEspecie(
                especie=EspecieFinanceira.DINHEIRO,
                valor_esperado=2000.00,
                valor_informado=1990.00,
            ),
            MovimentacaoEspecie(
                especie=EspecieFinanceira.PIX,
                valor_esperado=1500.00,
                valor_informado=1500.00,
            ),
        ]
        fechamento = FechamentoCaixa(
            id="fech_movs_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario_abertura=datetime.now(),
            horario_fechamento=datetime.now(),
            faturamento_bruto=3500.00,
            movimentacoes=movs,
            operador_fechamento="Maria",
            status=StatusCaixa.FECHADO,
        )
        assert len(fechamento.movimentacoes) == 2
        assert fechamento.movimentacoes[0].diferenca == 10.00


class TestAuditoriaService:
    """Testes para lógica de auditoria (cliente WebPosto mockado)."""

    @pytest.mark.asyncio
    async def test_extrair_despesas_unidade(self):
        """✓ Extrair despesas de unidade"""
        mock_row = DespesaCaixa(
            id="exp_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario=datetime.now(),
            categoria=CategoriaDesapesa.GELO,
            valor=85.50,
            operador="João Silva",
        )
        with patch.object(
            wp_mod.webposto_client, "get_despesas", new_callable=AsyncMock
        ) as m:
            m.return_value = [mock_row]
            despesas = await AuditoriaService.extrair_despesas_por_unidade(1)
        assert len(despesas) == 1
        assert all(d.unidade_id == 1 for d in despesas)

    @pytest.mark.asyncio
    async def test_extrair_fechamentos_unidade(self):
        """✓ Extrair fechamentos de unidade"""
        fech = FechamentoCaixa(
            id="fech_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario_abertura=datetime(2026, 4, 12, 7, 0),
            horario_fechamento=datetime(2026, 4, 12, 23, 0),
            faturamento_bruto=5420.50,
            despesas_caixa_total=130.50,
            saldo_esperado_dinheiro=2500.00,
            saldo_informado_dinheiro=2495.30,
            status=StatusCaixa.FECHADO,
            operador_fechamento="Maria Santos",
        )
        with patch.object(
            wp_mod.webposto_client, "get_fechamentos", new_callable=AsyncMock
        ) as m:
            m.return_value = [fech]
            fechamentos = await AuditoriaService.extrair_fechamentos(1)
        assert len(fechamentos) == 1
        assert all(f.unidade_id == 1 for f in fechamentos)

    @pytest.mark.asyncio
    async def test_calcular_resumo(self):
        """✓ Calcular resumo consolidado"""
        fech = FechamentoCaixa(
            id="fech_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario_abertura=datetime(2026, 4, 12, 7, 0),
            horario_fechamento=datetime(2026, 4, 12, 23, 0),
            faturamento_bruto=5420.50,
            despesas_caixa_total=130.50,
            saldo_esperado_dinheiro=2500.00,
            saldo_informado_dinheiro=2495.30,
            status=StatusCaixa.FECHADO,
            operador_fechamento="Maria Santos",
        )
        desp = DespesaCaixa(
            id="exp_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario=datetime.now(),
            categoria=CategoriaDesapesa.GELO,
            valor=10.0,
            operador="x",
        )
        resumo = AuditoriaService.calcular_resumo_unidade([fech], [desp], 1)

        assert resumo.faturamento_total > 0
        assert resumo.unidade_id == 1
        assert resumo.caixas_fechados > 0

    def test_resumo_identifica_outlier(self):
        """✓ Identify unidades outlier (desvio > 10%)"""
        fechamento = FechamentoCaixa(
            id="fech_outlier_001",
            unidade_id=99,
            caixa_tipo=TipoCaixa.CONVENIENCIA,
            horario_abertura=datetime.now(),
            horario_fechamento=datetime.now(),
            faturamento_bruto=1000.00,
            despesas_caixa_total=300.00,  # 30% (outlier!)
            operador_fechamento="Test",
        )

        resumo = AuditoriaService.calcular_resumo_unidade([fechamento], [], 99)

        assert resumo.outlier_unidade == True
        assert resumo.desvio_percentual_media_despesas > 10


# ============ TESTES DE INTEGRAÇÃO ============
class TestIntegracao:
    """Testes e2e básicos"""

    @pytest.mark.asyncio
    async def test_flow_completo(self):
        """✓ Flow completo: extrair → consolidar → identificar outliers"""

        fech = FechamentoCaixa(
            id="fech_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario_abertura=datetime(2026, 4, 12, 7, 0),
            horario_fechamento=datetime(2026, 4, 12, 23, 0),
            faturamento_bruto=5420.50,
            despesas_caixa_total=130.50,
            saldo_esperado_dinheiro=2500.00,
            saldo_informado_dinheiro=2495.30,
            status=StatusCaixa.FECHADO,
            operador_fechamento="Maria Santos",
        )
        desp = DespesaCaixa(
            id="exp_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario=datetime.now(),
            categoria=CategoriaDesapesa.GELO,
            valor=10.0,
            operador="x",
        )

        with patch.object(
            wp_mod.webposto_client, "get_despesas", new_callable=AsyncMock
        ) as md:
            md.return_value = [desp]
            with patch.object(
                wp_mod.webposto_client, "get_fechamentos", new_callable=AsyncMock
            ) as mf:
                mf.return_value = [fech]
                despesas = await AuditoriaService.extrair_despesas_por_unidade(1)
                fechamentos = await AuditoriaService.extrair_fechamentos(1)

        resumo = AuditoriaService.calcular_resumo_unidade(fechamentos, despesas, 1)

        assert resumo.faturamento_total > 0
        assert resumo.caixas_fechados >= 0
        assert resumo.desvio_percentual_media_despesas is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
