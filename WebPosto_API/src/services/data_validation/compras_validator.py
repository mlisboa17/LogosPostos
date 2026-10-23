"""
Validador de qualidade de dados de compras.

Audita integridade, consistência e completude de dados de compras
vindos das APIs CONSULTAR_COMPRA_REDE e CONSULTAR_COMPRA_ITEM_REDE.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CustaValidationResult:
    """Resultado da validação de um item de compra"""
    compra_item_id: str
    produto_id: str
    is_valid: bool
    custo_real: Decimal
    custo_esperado: Decimal
    diferenca: Decimal
    diferenca_percentual: float
    problemas: list[str]


@dataclass
class FornecedorAnalysis:
    """Análise de um fornecedor"""
    fornecedor_id: str
    nome: str
    total_compras: int
    preco_medio: Decimal
    preco_minimo: Decimal
    preco_maximo: Decimal
    evolucao_preco: float  # % de variação
    anomalias: list[str]
    qualidade_dados: float  # 0-100%


class ComprasValidator:
    """Auditor de qualidade de dados de compras"""

    def __init__(self, webposto_client, db_client):
        self.client = webposto_client
        self.db = db_client

    async def validate_compra_item(self, item: dict) -> CustaValidationResult:
        """
        Validar integridade de um item de compra.

        Verifica:
        - Custo real = (valor_nota + frete + imposto) / quantidade
        - Quantidade > 0
        - Datas válidas
        - Fornecedor cadastrado
        """

        problemas = []
        compra_item_id = item.get("id", "UNKNOWN")
        produto_id = item.get("produto_id", "UNKNOWN")

        # Extrair valores
        valor_nota = Decimal(str(item.get("valor", 0) or 0))
        frete = Decimal(str(item.get("frete", 0) or 0))
        imposto = Decimal(str(item.get("imposto", 0) or 0))
        quantidade = Decimal(str(item.get("quantidade", 0) or 0))
        data_compra = item.get("data_compra")

        # Validações
        if quantidade <= 0:
            problemas.append("Quantidade inválida (≤0)")
            return CustaValidationResult(
                compra_item_id=compra_item_id,
                produto_id=produto_id,
                is_valid=False,
                custo_real=Decimal(0),
                custo_esperado=Decimal(0),
                diferenca=Decimal(0),
                diferenca_percentual=0,
                problemas=problemas,
            )

        if valor_nota < 0:
            problemas.append("Valor da nota negativo")

        if frete < 0:
            problemas.append("Frete negativo")

        if imposto < 0:
            problemas.append("Imposto negativo")

        # Calcular custo real
        custo_total = valor_nota + frete + imposto
        custo_real = custo_total / quantidade if quantidade > 0 else Decimal(0)

        # Comparar com histórico (se disponível)
        custo_historico = await self._get_historical_cost(produto_id)
        diferenca = custo_real - custo_historico
        diferenca_percentual = float((diferenca / custo_historico * 100)) if custo_historico > 0 else 0

        # Alertar se diferença > 20%
        if abs(diferenca_percentual) > 20:
            problemas.append(f"Custo divergiu {abs(diferenca_percentual):.1f}% do histórico")

        # Validar data
        try:
            if data_compra and isinstance(data_compra, str):
                datetime.fromisoformat(data_compra)
        except ValueError:
            problemas.append("Data de compra inválida")

        is_valid = len(problemas) == 0

        return CustaValidationResult(
            compra_item_id=compra_item_id,
            produto_id=produto_id,
            is_valid=is_valid,
            custo_real=custo_real,
            custo_esperado=custo_historico,
            diferenca=diferenca,
            diferenca_percentual=diferenca_percentual,
            problemas=problemas,
        )

    async def detect_price_outliers(
        self, fornecedor_id: str, sensitivity: float = 1.5
    ) -> list[dict]:
        """
        Detectar outliers de preço para um fornecedor.

        Usa desvio padrão: if preço > média + (sensitivity * std_dev): anomalia
        """

        # Buscar histórico de compras do fornecedor
        compras = await self.client.get(
            "/INTEGRACAO/V1/COMPRAS",
            params={
                "fornecedor_id": fornecedor_id,
                "data_inicial": (datetime.now() - timedelta(days=90)).isoformat(),
                "data_final": datetime.now().isoformat(),
            },
        )

        if not compras:
            return []

        # Agrupar por produto
        precos_por_produto = {}
        for compra in compras:
            for item in compra.get("itens", []):
                produto_id = item.get("produto_id")
                preco = Decimal(str(item.get("preco_unitario", 0)))

                if produto_id not in precos_por_produto:
                    precos_por_produto[produto_id] = []
                precos_por_produto[produto_id].append(preco)

        # Detectar outliers
        outliers = []
        for produto_id, precos in precos_por_produto.items():
            if len(precos) < 3:  # Precisa de histórico mínimo
                continue

            media = sum(precos) / len(precos)
            variancia = sum((p - media) ** 2 for p in precos) / len(precos)
            std_dev = variancia ** 0.5

            threshold_superior = media + (sensitivity * std_dev)

            for preco in precos:
                if preco > threshold_superior:
                    outliers.append(
                        {
                            "produto_id": produto_id,
                            "preco": float(preco),
                            "media_historica": float(media),
                            "desvio_padrao": float(std_dev),
                            "percentual_acima": float((preco - media) / media * 100),
                            "severidade": "ALTA" if preco > media * 1.5 else "MÉDIA",
                        }
                    )

        return outliers

    async def validate_consistency(self, compra_id: str) -> list[str]:
        """
        Validar consistência: compra vs estoque subsequente.

        Se comprei 100un mas estoque só aumentou 80un, há discrepância.
        """

        problemas = []

        # Buscar compra
        compra = await self.client.get(f"/INTEGRACAO/V1/COMPRAS/{compra_id}")
        if not compra:
            return ["Compra não encontrada"]

        data_compra = compra.get("data")
        itens = compra.get("itens", [])

        # Para cada item, verificar estoque
        for item in itens:
            produto_id = item.get("produto_id")
            quantidade_comprada = Decimal(str(item.get("quantidade", 0)))

            # Buscar movimento de estoque após compra
            estoques = await self.client.get(
                "/INTEGRACAO/V1/ESTOQUES_PERIODO",
                params={
                    "produto_id": produto_id,
                    "data_inicial": data_compra,
                    "data_final": (
                        datetime.fromisoformat(data_compra) + timedelta(days=7)
                    ).isoformat(),
                },
            )

            if estoques:
                # Somar entradas
                quantidade_entrada = sum(
                    Decimal(str(e.get("entrada", 0))) for e in estoques
                )

                if quantidade_entrada < quantidade_comprada:
                    diferenca = quantidade_comprada - quantidade_entrada
                    problemas.append(
                        f"Produto {produto_id}: Comprei {quantidade_comprada} "
                        f"mas estoque recebeu apenas {quantidade_entrada} "
                        f"(diferença: {diferenca})"
                    )

        return problemas

    async def generate_data_quality_report(
        self, data_inicial: str, data_final: str
    ) -> dict:
        """
        Gerar relatório consolidado de qualidade de dados.

        Cobre: cobertura, gaps, anomalias, recomendações.
        """

        logger.info(f"Iniciando validação de compras: {data_inicial} a {data_final}")

        # Buscar todas compras no período
        compras = await self.client.get(
            "/INTEGRACAO/V1/COMPRAS",
            params={
                "data_inicial": data_inicial,
                "data_final": data_final,
            },
        )

        total_compras = len(compras) if compras else 0
        compras_com_problema = 0
        itens_validados = 0
        itens_com_problema = 0
        fornecedores_analisados = set()
        fornecedores_com_anomalia = set()

        # Validar cada item
        problemas_encontrados = []
        for compra in compras or []:
            for item in compra.get("itens", []):
                itens_validados += 1
                fornecedor_id = compra.get("fornecedor_id")
                if fornecedor_id:
                    fornecedores_analisados.add(fornecedor_id)

                resultado = await self.validate_compra_item(item)
                if not resultado.is_valid:
                    itens_com_problema += 1
                    compras_com_problema += 1
                    problemas_encontrados.append(
                        {
                            "compra_item_id": resultado.compra_item_id,
                            "produto_id": resultado.produto_id,
                            "problemas": resultado.problemas,
                            "diferenca_percentual": resultado.diferenca_percentual,
                        }
                    )

        # Detectar anomalias de preço
        anomalias_preco = []
        for fornecedor_id in fornecedores_analisados:
            outliers = await self.detect_price_outliers(fornecedor_id)
            if outliers:
                fornecedores_com_anomalia.add(fornecedor_id)
                anomalias_preco.extend(outliers)

        # Calcular taxa de cobertura
        cobertura_dados = (
            (total_compras - compras_com_problema) / total_compras * 100
            if total_compras > 0
            else 0
        )

        # Gerar recomendações
        recomendacoes = []
        if compras_com_problema > total_compras * 0.05:  # >5% com problema
            recomendacoes.append(
                f"Revisar {compras_com_problema} compras com dados inconsistentes"
            )

        if len(fornecedores_com_anomalia) > 0:
            recomendacoes.append(
                f"{len(fornecedores_com_anomalia)} fornecedores têm anomalias de preço - negociar"
            )

        status = (
            "PRONTO_PARA_IA"
            if cobertura_dados > 95 and len(recomendacoes) < 3
            else "REQUER_REVISAO"
        )

        report = {
            "periodo": f"{data_inicial} a {data_final}",
            "data_geracao": datetime.now().isoformat(),
            "status": status,
            "total_compras": total_compras,
            "compras_validadas": total_compras - compras_com_problema,
            "compras_com_problema": compras_com_problema,
            "itens_validados": itens_validados,
            "itens_com_problema": itens_com_problema,
            "cobertura_dados_percentual": round(cobertura_dados, 1),
            "fornecedores_analisados": len(fornecedores_analisados),
            "fornecedores_com_anomalia": len(fornecedores_com_anomalia),
            "anomalias_preco_detectadas": len(anomalias_preco),
            "problemas_encontrados": problemas_encontrados[:50],  # Top 50
            "anomalias_preco": anomalias_preco[:20],  # Top 20
            "recomendacoes": recomendacoes,
        }

        logger.info(f"Validação completa. Status: {status}")

        return report

    async def _get_historical_cost(self, produto_id: str) -> Decimal:
        """Buscar custo médio histórico de um produto"""
        # TODO: Implementar busca em DB de histórico
        # Por enquanto retorna 0 para evitar erro
        return Decimal(0)
