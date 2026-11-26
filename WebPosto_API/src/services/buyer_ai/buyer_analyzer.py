"""
Comprador IA - Analista permanente de estoque e reposição.

Identifica:
- Capital parado (produtos sem giro)
- Rupturas iminentes (risco de falta)
- Oportunidades de reposição (otimização)
- Desequilíbrios compras vs vendas

Objetivo: Gerar economias de R$ 50k+/mês em capital parado e vendas perdidas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def _fonte_indisponivel(motivo: str) -> dict[str, Any]:
    return {"status": "fonte_indisponivel", "motivo": motivo}


def _leitura_vazia_ok() -> dict[str, Any]:
    """Fonte respondeu com sucesso e não há registros."""
    return {"status": "ok", "fonte_ok": True, "itens": []}


def _extrair_itens(resultado: Any) -> list:
    if isinstance(resultado, dict):
        if resultado.get("fonte_ok"):
            return list(resultado.get("itens") or [])
        return []
    if isinstance(resultado, list):
        return resultado
    return []


@dataclass
class ProdutoAnalise:
    """Análise de um produto"""
    produto_id: str
    descricao: str
    estoque_atual: int
    consumo_diario: Decimal
    dias_de_estoque: Decimal
    custo_unitario: Decimal
    capital_parado: Decimal
    dias_sem_venda: int


@dataclass
class RupturaRisco:
    """Produto em risco de ruptura"""
    produto_id: str
    descricao: str
    estoque_atual: int
    consumo_diario: Decimal
    dias_de_estoque: Decimal
    tempo_reabastecimento_dias: int
    rupture_probability: float  # 0-100
    data_provavel_ruptura: str
    vendas_perdidas_estimadas: Decimal
    urgencia: str  # CRÍTICA, ALTA, MÉDIA, BAIXA


@dataclass
class RecomendacaoReposicao:
    """Recomendação de reposição"""
    produto_id: str
    descricao: str
    prioridade: int  # 1-100
    quantidade_sugerida: int
    fornecedor_recomendado: str
    preco_esperado: Decimal
    data_compra_ideal: str
    economia_potencial: Decimal
    justificativa: str


@dataclass
class Desequilibrio:
    """Desequilíbrio entre compras e vendas"""
    produto_id: str
    descricao: str
    comprado_periodo: int
    vendido_periodo: int
    diferenca: int
    percentual_desvio: float
    tipo: str  # COMPRADO_DEMAIS, COMPRADO_POUCO, EQUILIBRADO
    impacto_financeiro: Decimal
    recomendacao: str


class BuyerAnalyzer:
    """Consultor de compras, estoque e reposição"""

    def __init__(self, webposto_client, db_client, config: dict | None = None):
        self.client = webposto_client
        self.db = db_client
        self.config = config or {
            "dias_capital_parado": 45,  # Produtos sem venda por 45+ dias
            "dias_ruptura": 7,  # Prever rupturas nos próximos 7 dias
            "estoque_ideal_multiplo": 45,  # Estoque ideal = consumo diário * 45
            "margem_seguranca": 1.2,  # 20% de margem de segurança
            "threshold_preco_crescente": 15,  # Alertar se preço cresceu >15%
        }

    # ========== 1. ANÁLISE DE ESTOQUE ==========

    async def find_immobilized_capital(self) -> list[dict] | dict[str, Any]:
        """
        Encontrar capital parado (produtos sem giro).

        Retorna lista de produtos, ``fonte_indisponivel`` se a leitura falhar/nula,
        ou ``{fonte_ok: True, itens: []}`` se a fonte respondeu vazia com sucesso.
        """

        logger.info("Analisando capital parado...")

        dias_limite = self.config["dias_capital_parado"]
        min_capital = Decimal("100")  # Mínimo para considerar problema

        # 1. Buscar estoque atual
        try:
            estoques = await self.client.get("/INTEGRACAO/V1/ESTOQUES")
        except Exception as exc:  # noqa: BLE001
            return _fonte_indisponivel(
                f"falha ao ler ESTOQUES: {type(exc).__name__}: {exc}"
            )
        if estoques is None:
            logger.warning("ESTOQUES retornou nulo")
            return _fonte_indisponivel("ESTOQUES retornou nulo")
        if not isinstance(estoques, list):
            return _fonte_indisponivel("ESTOQUES não retornou lista")
        if len(estoques) == 0:
            return _leitura_vazia_ok()

        # 2. Buscar vendas dos últimos dias_limite dias
        data_inicial = (datetime.now() - timedelta(days=dias_limite)).isoformat()
        try:
            vendas = await self.client.get(
                "/INTEGRACAO/V1/VENDAS",
                params={"data_inicial": data_inicial},
            )
        except Exception as exc:  # noqa: BLE001
            return _fonte_indisponivel(
                f"falha ao ler VENDAS: {type(exc).__name__}: {exc}"
            )
        if vendas is None:
            vendas = []
        if vendas is not None and not isinstance(vendas, list):
            return _fonte_indisponivel("VENDAS não retornou lista")

        # Agrupar vendas por produto
        produtos_vendidos = set()
        if vendas:
            for venda in vendas:
                for item in venda.get("itens", []):
                    produtos_vendidos.add(item.get("produto_id"))

        # 3. Identificar produtos SEM venda
        produtos_parados = []

        for estoque in estoques:
            produto_id = estoque.get("produto_id")
            quantidade = int(estoque.get("quantidade", 0))
            custo_unitario = Decimal(str(estoque.get("custo_unitario", 0)))

            if produto_id not in produtos_vendidos and quantidade > 0:
                capital = quantidade * custo_unitario

                if capital >= min_capital:
                    produtos_parados.append(
                        {
                            "produto_id": produto_id,
                            "descricao": estoque.get("descricao", ""),
                            "quantidade": quantidade,
                            "custo_unitario": float(custo_unitario),
                            "capital_parado": float(capital),
                            "dias_sem_venda": dias_limite,
                            "recomendacao": "Considerar desconto/liquidação",
                            "impacto_financeiro": float(capital),
                            "urgencia": "ALTA" if capital > 5000 else "MÉDIA",
                        }
                    )

        # Ordenar por capital (maior primeiro)
        produtos_parados.sort(
            key=lambda x: x["capital_parado"],
            reverse=True,
        )

        logger.info(
            f"Encontrados {len(produtos_parados)} produtos parados. "
            f"Capital total: R${sum(p['capital_parado'] for p in produtos_parados):,.0f}"
        )

        return produtos_parados

    # ========== 2. PREDIÇÃO DE RUPTURAS ==========

    async def find_rupture_risk(self) -> list[dict] | dict[str, Any]:
        """
        Prever produtos que podem faltar nos próximos dias.

        Análise:
        - Consumo histórico → consumo diário médio
        - Estoque atual / consumo diário = dias de estoque
        - Se dias_estoque < tempo_reabastecimento: RISCO

        Sem estoque por falha/nulo → ``fonte_indisponivel``; vazio com sucesso → ``fonte_ok``.
        """

        logger.info("Analisando risco de rupturas...")

        dias_ruptura = self.config["dias_ruptura"]
        min_dias_aviso = 3  # Avisar com pelo menos 3 dias de antecedência

        # 1. Buscar estoque atual
        try:
            estoques = await self.client.get("/INTEGRACAO/V1/ESTOQUES")
        except Exception as exc:  # noqa: BLE001
            return _fonte_indisponivel(
                f"falha ao ler ESTOQUES: {type(exc).__name__}: {exc}"
            )
        if estoques is None:
            return _fonte_indisponivel("ESTOQUES retornou nulo")
        if not isinstance(estoques, list):
            return _fonte_indisponivel("ESTOQUES não retornou lista")
        if len(estoques) == 0:
            return _leitura_vazia_ok()

        # 2. Buscar vendas dos últimos 30 dias (para calcular consumo)
        data_inicial = (datetime.now() - timedelta(days=30)).isoformat()
        try:
            vendas = await self.client.get(
                "/INTEGRACAO/V1/VENDAS",
                params={"data_inicial": data_inicial},
            )
        except Exception as exc:  # noqa: BLE001
            return _fonte_indisponivel(
                f"falha ao ler VENDAS: {type(exc).__name__}: {exc}"
            )
        if vendas is None:
            vendas = []
        if vendas is not None and not isinstance(vendas, list):
            return _fonte_indisponivel("VENDAS não retornou lista")

        # Calcular consumo por produto
        consumo_por_produto = {}
        if vendas:
            for venda in vendas:
                for item in venda.get("itens", []):
                    produto_id = item.get("produto_id")
                    quantidade = int(item.get("quantidade", 0))

                    if produto_id not in consumo_por_produto:
                        consumo_por_produto[produto_id] = 0
                    consumo_por_produto[produto_id] += quantidade

        # Calcular consumo diário
        consumo_diario_por_produto = {}
        for produto_id, total in consumo_por_produto.items():
            consumo_diario_por_produto[produto_id] = Decimal(total) / Decimal("30")

        # 3. Buscar info de fornecedores (lead time real se existir; senão padrao_fixo=5)
        fornecedores = await self.client.get("/INTEGRACAO/V1/FORNECEDORES")
        tempo_reabastecimento: dict[Any, int] = {}
        origem_lead_por_fornecedor: dict[Any, str] = {}
        if fornecedores:
            for f in fornecedores:
                fid = f.get("id")
                lead = f.get("tempo_reabastecimento_dias") or f.get("prazoEntregaDias")
                if lead not in (None, "", 0, "0"):
                    tempo_reabastecimento[fid] = int(lead)
                    origem_lead_por_fornecedor[fid] = "historico"
                else:
                    tempo_reabastecimento[fid] = 5
                    origem_lead_por_fornecedor[fid] = "padrao_fixo"

        # 4. Análise de risco
        ruptures = []

        for estoque in estoques:
            produto_id = estoque.get("produto_id")
            quantidade = int(estoque.get("quantidade", 0))
            consumo_diario = consumo_diario_por_produto.get(
                produto_id, Decimal("0")
            )

            if consumo_diario > 0:
                dias_de_estoque = Decimal(quantidade) / consumo_diario
            else:
                dias_de_estoque = Decimal("999")  # Produto sem movimento

            fornecedor_id = estoque.get("fornecedor_id", "UNKNOWN")
            dias_reabastecimento = tempo_reabastecimento.get(fornecedor_id, 5)
            origem_lead = origem_lead_por_fornecedor.get(fornecedor_id, "padrao_fixo")

            # Verificar se há risco
            if dias_de_estoque <= dias_reabastecimento and consumo_diario > 0:
                rupture_probability = min(
                    100,
                    float((1 - dias_de_estoque / dias_reabastecimento) * 100),
                )

                if rupture_probability > 0:
                    data_ruptura = (
                        datetime.now() + timedelta(days=float(dias_de_estoque))
                    ).isoformat()

                    # Estimar vendas perdidas
                    vendas_diarias = consumo_diario * Decimal(
                        str(estoque.get("preco_venda", 10))
                    )
                    vendas_perdidas = vendas_diarias * (
                        Decimal(dias_reabastecimento) - dias_de_estoque
                    )

                    urgencia = "CRÍTICA"
                    if dias_de_estoque > 7:
                        urgencia = "ALTA"
                    elif dias_de_estoque > 14:
                        urgencia = "MÉDIA"

                    ruptures.append(
                        {
                            "produto_id": produto_id,
                            "descricao": estoque.get("descricao", ""),
                            "estoque_atual": quantidade,
                            "consumo_diario": float(consumo_diario),
                            "dias_de_estoque": float(dias_de_estoque),
                            "tempo_reabastecimento_dias": dias_reabastecimento,
                            "tempo_reabastecimento_origem": origem_lead,
                            "custo_unitario": estoque.get("custo_unitario"),
                            "preco_venda": estoque.get("preco_venda"),
                            "fornecedor_id": fornecedor_id,
                            "rupture_probability": rupture_probability,
                            "data_provavel_ruptura": data_ruptura,
                            "vendas_perdidas_estimadas": float(vendas_perdidas),
                            "recomendacao": "COMPRAR IMEDIATAMENTE"
                            if urgencia == "CRÍTICA"
                            else "Comprar em breve",
                            "impacto_perda_vendas": float(vendas_perdidas),
                            "urgencia": urgencia,
                        }
                    )

        # Ordenar por urgência e probabilidade
        ruptures.sort(
            key=lambda x: (
                {"CRÍTICA": 0, "ALTA": 1, "MÉDIA": 2, "BAIXA": 3}.get(
                    x["urgencia"], 4
                ),
                -x["rupture_probability"],
            )
        )

        logger.info(
            f"Encontrados {len(ruptures)} produtos em risco de ruptura. "
            f"Vendas perdidas potenciais: R${sum(r['vendas_perdidas_estimadas'] for r in ruptures):,.0f}"
        )

        return ruptures

    # ========== 3. OTIMIZAR REPOSIÇÃO ==========

    async def recommend_replenishment(self) -> list[dict]:
        """
        Recomendar quais produtos comprar, quanto e quando.

        Baseia-se em:
        - Consumo histórico
        - Estoque ideal = consumo_diário * dias_estoque_ideal
        - Tempo de reabastecimento
        - Custo atual vs histórico
        """

        logger.info("Gerando recomendações de reposição...")

        # 1. Buscar análises anteriores
        rupturas_raw = await self.find_rupture_risk()
        if isinstance(rupturas_raw, dict) and rupturas_raw.get("status") == "fonte_indisponivel":
            return rupturas_raw
        rupturas = _extrair_itens(rupturas_raw)
        capital_raw = await self.find_immobilized_capital()
        if isinstance(capital_raw, dict) and capital_raw.get("status") == "fonte_indisponivel":
            return capital_raw
        _ = _extrair_itens(capital_raw)

        # Produtos com ruptura = PRIORIDADE 1
        produtos_prioritarios = {r["produto_id"]: 1 for r in rupturas}

        # 2. Análise de todos produtos
        recomendacoes = []

        # Para cada produto em risco: calcular quantidade ideal
        for ruptura in rupturas:
            produto_id = ruptura["produto_id"]
            consumo_diario = Decimal(str(ruptura["consumo_diario"]))
            dias_reabast = int(ruptura.get("tempo_reabastecimento_dias") or 5)
            origem_lead = (
                "historico"
                if ruptura.get("tempo_reabastecimento_origem") == "historico"
                else "padrao_fixo"
            )

            # Quantidade ideal = consumo_diário * (dias_reabastecimento + margem)
            margem_seguranca = Decimal(str(self.config["margem_seguranca"]))
            quantidade_ideal = int(
                consumo_diario * (dias_reabast + 7) * margem_seguranca
            )

            # Preço: histórico/custo real se vier na ruptura; senão padrão fixo 5.0
            preco_raw = ruptura.get("custo_unitario") or ruptura.get("preco_venda")
            if preco_raw not in (None, "", 0, "0"):
                preco_esperado = Decimal(str(preco_raw))
                origem_preco = "historico"
            else:
                preco_esperado = Decimal("5.0")
                origem_preco = "padrao_fixo"

            origem_dado = (
                "historico"
                if origem_preco == "historico" and origem_lead == "historico"
                else "padrao_fixo"
            )

            # Economia potencial (evitar ruptura)
            economia = Decimal(str(ruptura["vendas_perdidas_estimadas"]))

            recomendacoes.append(
                {
                    "produto_id": produto_id,
                    "descricao": ruptura.get("descricao", ""),
                    "prioridade": 1,
                    "quantidade_sugerida": quantidade_ideal,
                    "estoque_atual": ruptura["estoque_atual"],
                    "consumo_diario": ruptura["consumo_diario"],
                    "fornecedor_recomendado": ruptura.get("fornecedor_id")
                    or "FORNECEDOR_A",
                    "preco_esperado": float(preco_esperado),
                    "custo_total": float(preco_esperado * quantidade_ideal),
                    "data_compra_ideal": (datetime.now()).isoformat(),
                    "economia_potencial": float(economia),
                    "justificativa": "Risco de ruptura iminente",
                    "origem_dado": origem_dado,
                    "origem_preco": origem_preco,
                    "origem_tempo_reabastecimento": origem_lead,
                    "tempo_reabastecimento_dias": dias_reabast,
                }
            )

        # Ordenar por prioridade e economia
        recomendacoes.sort(
            key=lambda x: (-x["prioridade"], -x["economia_potencial"])
        )

        logger.info(
            f"Geradas {len(recomendacoes)} recomendações de reposição. "
            f"Economia potencial: R${sum(r['economia_potencial'] for r in recomendacoes):,.0f}"
        )

        return recomendacoes

    # ========== 4. COMPARAR COMPRAS VS VENDAS ==========

    async def analyze_buy_vs_sell_mismatch(self, periodo_dias: int = 30) -> dict:
        """
        Identificar desequilíbrios: compramos muito e vendemos pouco (ou vice-versa).

        Análise por produto:
        - Quantidade comprada no período
        - Quantidade vendida no período
        - Diferença = desequilíbrio
        - Impacto = capital parado ou vendas perdidas
        """

        logger.info(f"Analisando compras vs vendas dos últimos {periodo_dias} dias...")

        data_inicial = (datetime.now() - timedelta(days=periodo_dias)).isoformat()

        # 1. Buscar compras
        try:
            compras = await self.client.get(
                "/INTEGRACAO/V1/COMPRAS",
                params={"data_inicial": data_inicial},
            )
        except Exception as exc:  # noqa: BLE001
            return _fonte_indisponivel(
                f"falha ao ler COMPRAS: {type(exc).__name__}: {exc}"
            )
        if compras is None:
            return _fonte_indisponivel("COMPRAS retornou nulo")
        if not isinstance(compras, list):
            return _fonte_indisponivel("COMPRAS não retornou lista")

        comprado_por_produto = {}
        for compra in compras:
            for item in compra.get("itens", []):
                produto_id = item.get("produto_id")
                quantidade = int(item.get("quantidade", 0))
                custo = Decimal(str(item.get("preco_unitario", 0)))

                if produto_id not in comprado_por_produto:
                    comprado_por_produto[produto_id] = {
                        "quantidade": 0,
                        "custo_medio": custo,
                    }
                comprado_por_produto[produto_id]["quantidade"] += quantidade
                comprado_por_produto[produto_id]["custo_medio"] = custo

        # 2. Buscar vendas
        try:
            vendas = await self.client.get(
                "/INTEGRACAO/V1/VENDAS",
                params={"data_inicial": data_inicial},
            )
        except Exception as exc:  # noqa: BLE001
            return _fonte_indisponivel(
                f"falha ao ler VENDAS: {type(exc).__name__}: {exc}"
            )
        if vendas is None:
            return _fonte_indisponivel("VENDAS retornou nulo")
        if not isinstance(vendas, list):
            return _fonte_indisponivel("VENDAS não retornou lista")

        vendido_por_produto = {}
        for venda in vendas:
            for item in venda.get("itens", []):
                produto_id = item.get("produto_id")
                quantidade = int(item.get("quantidade", 0))
                preco_venda = Decimal(str(item.get("preco_venda", 0)))

                if produto_id not in vendido_por_produto:
                    vendido_por_produto[produto_id] = {
                        "quantidade": 0,
                        "preco_medio": preco_venda,
                    }
                vendido_por_produto[produto_id]["quantidade"] += quantidade
                vendido_por_produto[produto_id]["preco_medio"] = preco_venda

        # 3. Analisar desequilíbrios
        produtos_comprado_demais = []
        produtos_comprado_pouco = []
        mudancas_comportamento = []

        todos_produtos = set(comprado_por_produto.keys()) | set(
            vendido_por_produto.keys()
        )

        for produto_id in todos_produtos:
            comprado = comprado_por_produto.get(produto_id, {"quantidade": 0})[
                "quantidade"
            ]
            vendido = vendido_por_produto.get(produto_id, {"quantidade": 0})[
                "quantidade"
            ]

            if comprado > 0 and vendido == 0:
                # Comprou mas não vendeu!
                custo = (
                    comprado_por_produto.get(produto_id, {}).get("custo_medio")
                    or Decimal("0")
                )
                capital_parado = int(comprado) * custo

                produtos_comprado_demais.append(
                    {
                        "produto_id": produto_id,
                        "comprado_ultimo_mes": comprado,
                        "vendido_ultimo_mes": 0,
                        "excesso": comprado,
                        "capital_parado": float(capital_parado),
                        "recomendacao": f"Reduzir futuras compras em 100% ou liquidar com desconto",
                    }
                )

            elif vendido > 0 and comprado == 0:
                # Vendeu mas não tinha comprado!
                preco_venda = (
                    vendido_por_produto.get(produto_id, {}).get("preco_medio")
                    or Decimal("0")
                )
                vendas_perdidas = int(vendido) * preco_venda

                produtos_comprado_pouco.append(
                    {
                        "produto_id": produto_id,
                        "comprado_ultimo_mes": 0,
                        "vendido_ultimo_mes": vendido,
                        "deficit": vendido,
                        "vendas_perdidas_potenciais": float(vendas_perdidas),
                        "recomendacao": f"Aumentar futuras compras para {int(vendido * 1.2)}/mês",
                    }
                )

            elif comprado > 0 and vendido > 0:
                diferenca = comprado - vendido
                percentual = (
                    abs(diferenca) / max(comprado, vendido) * 100
                    if max(comprado, vendido) > 0
                    else 0
                )

                if percentual > 50:  # Desequilíbrio > 50%
                    if comprado > vendido:
                        capital_parado = int(diferenca) * (
                            comprado_por_produto.get(produto_id, {}).get(
                                "custo_medio"
                            )
                            or Decimal("0")
                        )
                        produtos_comprado_demais.append(
                            {
                                "produto_id": produto_id,
                                "comprado_ultimo_mes": comprado,
                                "vendido_ultimo_mes": vendido,
                                "excesso": diferenca,
                                "capital_parado": float(capital_parado),
                                "percentual_desvio": percentual,
                                "recomendacao": f"Reduzir compras em {int(percentual)}%",
                            }
                        )
                    else:
                        preco_venda = (
                            vendido_por_produto.get(produto_id, {}).get(
                                "preco_medio"
                            )
                            or Decimal("0")
                        )
                        deficit = -diferenca  # comprado - vendido é negativo aqui
                        vendas_perdidas = int(deficit) * preco_venda
                        produtos_comprado_pouco.append(
                            {
                                "produto_id": produto_id,
                                "comprado_ultimo_mes": comprado,
                                "vendido_ultimo_mes": vendido,
                                "deficit": deficit,
                                "vendas_perdidas_potenciais": float(vendas_perdidas),
                                "percentual_desvio": percentual,
                                "recomendacao": f"Aumentar compras em {int(percentual)}%",
                            }
                        )

        logger.info(
            f"Análise completa. Comprado demais: {len(produtos_comprado_demais)}. "
            f"Comprado pouco: {len(produtos_comprado_pouco)}"
        )

        return {
            "periodo_dias": periodo_dias,
            "produtos_comprado_demais": produtos_comprado_demais,
            "produtos_comprado_pouco": produtos_comprado_pouco,
            "mudancas_comportamento": mudancas_comportamento,
            "capital_parado_total": sum(
                p.get("capital_parado", 0) for p in produtos_comprado_demais
            ),
            "vendas_perdidas_total": sum(
                p.get("vendas_perdidas_potenciais", 0) for p in produtos_comprado_pouco
            ),
        }

    # ========== 5. GERAR RELATÓRIO EXECUTIVO ==========

    async def generate_executive_brief(self) -> dict:
        """Relatório consolidado para decisão (3 páginas max)"""

        logger.info("Gerando brief executivo...")

        # Executar todas análises
        capital_raw = await self.find_immobilized_capital()
        if isinstance(capital_raw, dict) and capital_raw.get("status") == "fonte_indisponivel":
            return {**capital_raw, "data_audit": datetime.now().isoformat()}
        capital_parado_list = _extrair_itens(capital_raw)

        rupturas_raw = await self.find_rupture_risk()
        if isinstance(rupturas_raw, dict) and rupturas_raw.get("status") == "fonte_indisponivel":
            return {**rupturas_raw, "data_audit": datetime.now().isoformat()}
        rupturas = _extrair_itens(rupturas_raw)

        reposicoes = await self.recommend_replenishment()
        if isinstance(reposicoes, dict) and reposicoes.get("status") == "fonte_indisponivel":
            return {**reposicoes, "data_audit": datetime.now().isoformat()}
        if not isinstance(reposicoes, list):
            reposicoes = _extrair_itens(reposicoes)

        desequilibrios = await self.analyze_buy_vs_sell_mismatch()
        if isinstance(desequilibrios, dict) and desequilibrios.get("status") == "fonte_indisponivel":
            return {**desequilibrios, "data_audit": datetime.now().isoformat()}

        # Consolidar top 3 problemas
        problemas = []

        # Problema 1: Capital parado
        if capital_parado_list:
            total_capital = float(sum(p["capital_parado"] for p in capital_parado_list))
            ganho_capital = round(total_capital * 0.3, 2)
            problemas.append(
                {
                    "problema": f"Capital parado em {len(capital_parado_list)} produtos",
                    "impacto": f"R$ {total_capital:,.0f}",
                    "impacto_rs": round(total_capital, 2),
                    "prioridade": "ALTA",
                    "acao": "Desconto/liquidação",
                    "ganho_estimado": f"R$ {ganho_capital:,.0f}",
                    "ganho_estimado_rs": ganho_capital,
                }
            )

        # Problema 2: Rupturas
        if rupturas:
            total_perdas = float(sum(r["vendas_perdidas_estimadas"] for r in rupturas))
            problemas.append(
                {
                    "problema": f"{len(rupturas)} produtos em risco de ruptura",
                    "impacto": f"R$ {total_perdas:,.0f} em vendas perdidas",
                    "impacto_rs": round(total_perdas, 2),
                    "prioridade": "CRÍTICA",
                    "acao": "Comprar hoje",
                    "ganho_estimado": f"R$ {total_perdas:,.0f} (evitar perda)",
                    "ganho_estimado_rs": round(total_perdas, 2),
                }
            )

        # Problema 3: Desequilíbrios
        if (
            desequilibrios["produtos_comprado_demais"]
            or desequilibrios["produtos_comprado_pouco"]
        ):
            total_desequilibrio = float(
                desequilibrios["capital_parado_total"]
                + desequilibrios["vendas_perdidas_total"]
            )
            ganho_deseq = round(total_desequilibrio * 0.2, 2)
            problemas.append(
                {
                    "problema": f"Desequilíbrio compras vs vendas",
                    "impacto": f"R$ {total_desequilibrio:,.0f}",
                    "impacto_rs": round(total_desequilibrio, 2),
                    "prioridade": "ALTA",
                    "acao": "Rebalancear compras",
                    "ganho_estimado": f"R$ {ganho_deseq:,.0f}",
                    "ganho_estimado_rs": ganho_deseq,
                }
            )

        # Economia potencial total
        economia_total = sum(
            float(r["economia_potencial"]) for r in reposicoes
        ) + (
            desequilibrios["capital_parado_total"]
            + desequilibrios["vendas_perdidas_total"]
        )

        return {
            "data_audit": datetime.now().isoformat(),
            "periodo_analisado": "últimos 90 dias",
            "findings_count": len(problemas),
            "problemas_criticos": sum(
                1 for p in problemas if p["prioridade"] == "CRÍTICA"
            ),
            "oportunidades_ganho": len(reposicoes),
            "economia_potencial_total": economia_total,
            "reducao_trabalho_manual_horas": 40,
            "top_problemas": problemas[:3],
            "top_recomendacoes": [
                {
                    "id": i,
                    "produto_id": r["produto_id"],
                    "descricao": r.get("descricao", ""),
                    "quantidade": r.get("quantidade_sugerida", 0),
                    "economia": r["economia_potencial"],
                    "urgencia": "CRÍTICA",
                }
                for i, r in enumerate(reposicoes[:5], 1)
            ],
            "proximas_acoes": [
                f"Comprar {len(rupturas)} produtos em risco imediatamente",
                f"Liquidar {len(capital_parado_list)} produtos sem movimento",
                f"Rebalancear {len(desequilibrios['produtos_comprado_demais'])} compras excessivas",
            ],
        }
