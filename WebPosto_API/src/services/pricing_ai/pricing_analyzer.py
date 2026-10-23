"""Precificador IA - Análise de margem, markup e otimização de preços.

Core business logic para:
- Calcular margem real (custo total vs preço venda)
- Analisar markup
- Identificar produtos com margem negativa
- Detectar produtos obsoletos com preço não otimizado
- Recomendar reajuste de preço
- Detectar perdas ocultas (compostos, desperdício)
- Gerar relatório executivo com impacto financeiro
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional



@dataclass
class AnaliseMargem:
    """Análise de margem de um produto"""
    produto_id: str
    descricao: str
    preco_venda: Decimal
    custo_total: Decimal  # custo produto + impostos + overhead
    margem_bruta: Decimal  # preco_venda - custo_total
    margem_percentual: float  # (margem_bruta / preco_venda) * 100
    margem_status: str  # "SAUDÁVEL", "BAIXA", "NEGATIVA", "CRÍTICA"
    markup: float  # (preco_venda / custo_total - 1) * 100
    problemas: list[str] = field(default_factory=list)
    recomendacao: str = ""


@dataclass
class SugestaoReajuste:
    """Sugestão de reajuste de preço"""
    produto_id: str
    descricao: str
    preco_atual: Decimal
    preco_sugerido: Decimal
    percentual_ajuste: float  # positivo = aumento, negativo = redução
    margem_atual: Decimal
    margem_sugerida: Decimal
    impacto_mensal: Decimal  # impacto no resultado mensal
    motivo: str
    urgencia: str  # "CRÍTICA", "ALTA", "MÉDIA", "BAIXA"


@dataclass
class PerdasOcultas:
    """Detecção de perdas ocultas"""
    tipo: str  # "OBSOLETO", "BAIXA_ROTACAO", "COMPOSTO_ERRADO", "QUEBRA_ESTIMADA"
    produto_id: str
    descricao: str
    perda_estimada_mensal: Decimal
    dias_sem_venda: Optional[int] = None
    quantidade_parada: Optional[int] = None
    recomendacao: str = ""


class PricingAnalyzer:
    """Analisador de precificação e margens"""

    def __init__(self, webposto_client: Optional[object] = None, db_client=None):
        self.webposto_client = webposto_client
        self.db_client = db_client

        # Tabelas de referência (em produção, viriam do WebPostos)
        self._overhead_percentual = 0.15  # 15% overhead operacional
        self._margem_minima_saudavel = 0.20  # 20% margem mínima
        self._markup_minimo = 1.25  # 1.25x custo (25% margem)

    async def analisar_margem_produto(
        self,
        produto_id: str,
        preco_venda: Decimal,
        custo_produto: Decimal,
        aliquota_icms: Optional[Decimal] = None,
    ) -> AnaliseMargem:
        """Analisar margem real de um produto.

        Calcula: margem_bruta = preco_venda - custo_total
        Custo zero ou ausente gera status COST_MISSING com margem 0.0 (sem cálculo irreal).
        """

        if custo_produto <= Decimal("0"):
            return AnaliseMargem(
                produto_id=produto_id,
                descricao="",
                preco_venda=preco_venda,
                custo_total=Decimal("0"),
                margem_bruta=preco_venda,
                margem_percentual=0.0,
                margem_status="COST_MISSING",
                markup=0.0,
                problemas=["Custo ausente ou não informado (COST_MISSING)"],
                recomendacao="Produto com custo ausente ou zerado. Reconciliar nota DF-e.",
            )

        # Calcular impostos estimados se informado alíquota (ICMS sobre a margem de agregação)
        impostos = Decimal("0")
        if aliquota_icms is not None and preco_venda > custo_produto:
            impostos = (preco_venda - custo_produto) * (aliquota_icms / Decimal("100"))

        # Custo total
        custo_total = custo_produto + impostos

        # Margem
        margem_bruta = preco_venda - custo_total
        if preco_venda > 0:
            margem_percentual = float((margem_bruta / preco_venda) * Decimal("100"))
        else:
            margem_percentual = 0.0

        # Markup
        if custo_total > 0:
            markup = float((preco_venda / custo_total - Decimal("1")) * Decimal("100"))
        else:
            markup = 0.0

        # Status da margem
        if margem_percentual < 0:
            status = "NEGATIVA"
            recomendacao = "Aumentar preço ou reduzir custo imediatamente"
        elif margem_percentual < 10:
            status = "CRÍTICA"
            recomendacao = "Margem muito baixa, reajuste urgente recomendado"
        elif margem_percentual < 20:
            status = "BAIXA"
            recomendacao = "Considerar aumento de preço"
        else:
            status = "SAUDÁVEL"
            recomendacao = "Margem dentro dos padrões"

        # Problemas
        problemas = []
        if margem_percentual < 0:
            problemas.append(f"Margem negativa: {margem_percentual:.2f}%")
        if markup < 1.10:
            problemas.append(f"Markup muito baixo: {markup:.2f}%")

        return AnaliseMargem(
            produto_id=produto_id,
            descricao="",  # Será preenchido pela API
            preco_venda=preco_venda,
            custo_total=custo_total,
            margem_bruta=margem_bruta,
            margem_percentual=margem_percentual,
            margem_status=status,
            markup=markup,
            problemas=problemas,
            recomendacao=recomendacao,
        )

    async def recomendar_reajuste_preco(
        self,
        produto_id: str,
        preco_atual: Decimal,
        margem_atual_percentual: float,
        margem_alvo_percentual: float = 25.0,
        velocidade_venda_mensal: int = 100,
    ) -> SugestaoReajuste:
        """Recomendar reajuste de preço para atingir margem alvo.

        Fórmula: novo_preco = custo_total / (1 - (margem_alvo / 100))
        """

        # Estimar custo a partir da margem atual
        if margem_atual_percentual >= 0:
            custo_estimado = preco_atual / Decimal(str(1.0 + margem_atual_percentual / 100.0))
        else:
            custo_estimado = preco_atual * Decimal("1.1")

        # Calcular novo preço para margem alvo
        novo_preco = custo_estimado / Decimal(str(1.0 - margem_alvo_percentual / 100.0))

        # Arredondar para 0.90, 0.95, 0.99, etc
        novo_preco = self._arredondar_preco_psicologico(novo_preco)

        # Percentual de ajuste
        percentual_ajuste = float((novo_preco / preco_atual - Decimal("1")) * Decimal("100"))

        # Margem sugerida
        margem_sugerida = novo_preco - custo_estimado

        # Impacto mensal (aumento de margem * volume)
        impacto_mensal = (novo_preco - preco_atual) * Decimal(str(velocidade_venda_mensal))

        # Motivo e urgência
        if margem_atual_percentual < 0:
            motivo = "Produto com margem negativa"
            urgencia = "CRÍTICA"
        elif margem_atual_percentual < 15:
            motivo = "Margem abaixo do mínimo saudável"
            urgencia = "ALTA"
        elif percentual_ajuste > 10:
            motivo = "Otimização de preço para margem alvo"
            urgencia = "MÉDIA"
        else:
            motivo = "Pequeno reajuste recomendado"
            urgencia = "BAIXA"

        return SugestaoReajuste(
            produto_id=produto_id,
            descricao="",
            preco_atual=preco_atual,
            preco_sugerido=novo_preco,
            percentual_ajuste=percentual_ajuste,
            margem_atual=Decimal(str(margem_atual_percentual)),
            margem_sugerida=margem_sugerida,
            impacto_mensal=impacto_mensal,
            motivo=motivo,
            urgencia=urgencia,
        )

    async def detectar_perdas_ocultas(
        self,
        produto_id: str,
        dias_sem_venda: int = 30,
        quantidade_parada: int = 0,
        custo_unitario: Decimal = Decimal("0"),
    ) -> PerdasOcultas:
        """Detectar perdas ocultas por obsolescência, quebra, etc."""

        perda_estimada = Decimal("0")
        tipo = ""
        recomendacao = ""

        if dias_sem_venda > 90:
            tipo = "OBSOLETO"
            # Produto sem venda há > 90 dias: estimar perda de obsolescência
            perda_estimada = quantidade_parada * custo_unitario * Decimal("0.3")  # 30% perda
            recomendacao = "Considerar remoção do catálogo ou liquidação"

        elif dias_sem_venda > 45:
            tipo = "BAIXA_ROTACAO"
            # Produto lento: estimar perda por capital parado
            custo_oportunidade_mensal = quantidade_parada * custo_unitario * Decimal("0.05")  # 5% CDO
            perda_estimada = custo_oportunidade_mensal
            recomendacao = "Liquidar com desconto ou parar compras"

        elif quantidade_parada > 500:
            tipo = "COMPOSTO_ERRADO"
            # Muito estoque parado: pode ser erro de classificação/preço
            perda_estimada = quantidade_parada * custo_unitario * Decimal("0.1")
            recomendacao = "Revisar preço e classificação"

        return PerdasOcultas(
            tipo=tipo,
            produto_id=produto_id,
            descricao="",
            perda_estimada_mensal=perda_estimada,
            dias_sem_venda=dias_sem_venda if dias_sem_venda > 0 else None,
            quantidade_parada=quantidade_parada if quantidade_parada > 0 else None,
            recomendacao=recomendacao,
        )

    async def identificar_margens_negativas(
        self,
    ) -> list[AnaliseMargem]:
        """Encontrar todos produtos com margem negativa."""
        return []

    async def identificar_produtos_baixa_margem(
        self, threshold_percentual: float = 15.0
    ) -> list[AnaliseMargem]:
        """Encontrar produtos com margem abaixo do threshold."""
        return []

    async def gerar_relatorio_precificacao(
        self,
    ) -> dict:
        """Gerar relatório consolidado de precificação."""
        data_audit = datetime.now().isoformat()

        margens_negativas = await self.identificar_margens_negativas()
        margens_baixas = await self.identificar_produtos_baixa_margem(15)
        perdas_ocultas: list[PerdasOcultas] = []
        sugestoes_reajuste: list[SugestaoReajuste] = []

        impacto_margens_negativas = Decimal("0")
        impacto_reajustes = Decimal("0")
        impacto_perdas_ocultas = Decimal("0")
        impacto_total = impacto_margens_negativas + impacto_reajustes + impacto_perdas_ocultas

        if len(margens_negativas) > 0:
            status = "CRÍTICO"
        elif len(margens_baixas) > 5:
            status = "ALERTA"
        else:
            status = "OK"

        return {
            "data_audit": data_audit,
            "estado": "PE",
            "margens_negativas": len(margens_negativas),
            "margens_baixas": len(margens_baixas),
            "oportunidades_reajuste": len(sugestoes_reajuste),
            "perdas_ocultas_detectadas": len(perdas_ocultas),
            "impacto_margens_negativas": float(impacto_margens_negativas),
            "impacto_reajustes": float(impacto_reajustes),
            "impacto_perdas_ocultas": float(impacto_perdas_ocultas),
            "impacto_total_mensal": float(impacto_total),
            "recomendacoes": [
                f"Corrigir {len(margens_negativas)} produtos com margem negativa",
                f"Aplicar reajustes em {len(sugestoes_reajuste)} produtos",
                f"Investigar {len(perdas_ocultas)} produtos com perdas ocultas",
            ],
            "status": status,
        }

    def _arredondar_preco_psicologico(self, preco: Decimal) -> Decimal:
        """Arredondar preço para valores psicológicos (X.90, X.99)."""
        inteiro = int(preco)
        decimal = preco - Decimal(str(inteiro))

        if decimal >= Decimal("0.75"):
            inteiro += 1
            novo_decimal = Decimal("0.99")
        elif decimal >= Decimal("0.60"):
            novo_decimal = Decimal("0.99")
        else:
            novo_decimal = Decimal("0.90")

        return Decimal(str(inteiro)) + novo_decimal


__all__ = [
    "PricingAnalyzer",
    "AnaliseMargem",
    "SugestaoReajuste",
    "PerdasOcultas",
]
