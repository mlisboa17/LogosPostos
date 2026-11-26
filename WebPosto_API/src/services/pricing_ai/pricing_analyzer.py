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
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, Union
from zoneinfo import ZoneInfo

TZ_RECIFE = ZoneInfo("America/Recife")


def _agora_br() -> str:
    """Data/hora de auditoria no fuso America/Recife (dd/mm/aaaa HH:mm)."""
    return datetime.now(TZ_RECIFE).strftime("%d/%m/%Y %H:%M")


def _fonte_indisponivel(motivo: str) -> dict[str, str]:
    return {"status": "fonte_indisponivel", "motivo": motivo}


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

    def _extrair_preco_custo(self, row: dict[str, Any]) -> tuple[str, Decimal, Decimal, str]:
        """Normaliza linha PRODUTO_EMPRESA → (id, venda, custo, descricao)."""
        pid = str(
            row.get("produtoCodigo")
            or row.get("produto_id")
            or row.get("codigo")
            or ""
        )
        venda = Decimal(
            str(
                row.get("precoVenda")
                or row.get("preco_venda")
                or row.get("precoVendaA")
                or 0
            )
        )
        custo = Decimal(
            str(row.get("precoCusto") or row.get("custo") or row.get("custo_produto") or 0)
        )
        desc = str(row.get("descricao") or row.get("nome") or row.get("produtoNome") or "")
        return pid, venda, custo, desc

    async def _carregar_produtos_preco_custo(
        self,
    ) -> Union[list[dict[str, Any]], dict[str, str]]:
        """Lê preço/custo via cliente canônico de fábrica (`produtos.listar_empresa`).

        Lista vazia não significa "sem problema" — devolve fonte_indisponivel.
        """
        if self.webposto_client is None:
            return _fonte_indisponivel("webposto_client não injetado")

        produtos_api = getattr(self.webposto_client, "produtos", None)
        listar = getattr(produtos_api, "listar_empresa", None) if produtos_api else None
        if not callable(listar):
            return _fonte_indisponivel(
                "cliente WebPosto não expõe produtos.listar_empresa "
                "(GET /INTEGRACAO/PRODUTO_EMPRESA — preço/custo por empresa)"
            )

        try:
            rows = listar()
        except Exception as exc:  # noqa: BLE001 — diagnóstico honesto, sem inventar
            return _fonte_indisponivel(
                f"falha ao ler PRODUTO_EMPRESA: {type(exc).__name__}: {exc}"
            )

        if not isinstance(rows, list):
            return _fonte_indisponivel(
                "PRODUTO_EMPRESA não retornou lista (resposta inesperada)"
            )
        if len(rows) == 0:
            return _fonte_indisponivel(
                "PRODUTO_EMPRESA retornou zero registros; "
                "lista vazia não autoriza concluir ausência de problema de margem"
            )
        return rows

    async def _analisar_catalogo_margens(
        self,
        *,
        somente_negativas: bool = False,
        threshold_percentual: float = 15.0,
    ) -> Union[list[AnaliseMargem], dict[str, str]]:
        carregado = await self._carregar_produtos_preco_custo()
        if isinstance(carregado, dict) and carregado.get("status") == "fonte_indisponivel":
            return carregado

        resultados: list[AnaliseMargem] = []
        for row in carregado:
            if not isinstance(row, dict):
                continue
            pid, venda, custo, desc = self._extrair_preco_custo(row)
            if not pid or venda <= 0:
                continue
            analise = await self.analisar_margem_produto(
                pid,
                preco_venda=venda,
                custo_produto=custo,
                aliquota_icms=None,
            )
            analise.descricao = desc
            if somente_negativas:
                if analise.margem_status == "NEGATIVA":
                    resultados.append(analise)
            elif (
                analise.margem_status in {"BAIXA", "CRÍTICA"}
                and analise.margem_percentual < threshold_percentual
            ):
                resultados.append(analise)
        return resultados

    async def identificar_margens_negativas(
        self,
    ) -> Union[list[AnaliseMargem], dict[str, str]]:
        """Encontrar produtos com margem negativa a partir de PRODUTO_EMPRESA."""
        return await self._analisar_catalogo_margens(somente_negativas=True)

    async def identificar_produtos_baixa_margem(
        self, threshold_percentual: float = 15.0
    ) -> Union[list[AnaliseMargem], dict[str, str]]:
        """Encontrar produtos com margem abaixo do threshold (fonte real ou indisponível)."""
        return await self._analisar_catalogo_margens(
            somente_negativas=False,
            threshold_percentual=threshold_percentual,
        )

    async def gerar_sugestoes_reajuste(
        self,
        *,
        apenas_urgentes: bool = False,
    ) -> Union[list[SugestaoReajuste], dict[str, str]]:
        """Sugestões de reajuste a partir do catálogo real; sem inventar lista vazia."""
        baixas = await self.identificar_produtos_baixa_margem(20.0)
        if isinstance(baixas, dict) and baixas.get("status") == "fonte_indisponivel":
            return baixas
        negativas = await self.identificar_margens_negativas()
        if isinstance(negativas, dict) and negativas.get("status") == "fonte_indisponivel":
            return negativas

        candidatos = list(negativas) + [
            m for m in baixas if m.produto_id not in {n.produto_id for n in negativas}
        ]

        sugestoes: list[SugestaoReajuste] = []
        for m in candidatos:
            s = await self.recomendar_reajuste_preco(
                m.produto_id,
                preco_atual=m.preco_venda,
                margem_atual_percentual=m.margem_percentual,
            )
            s.descricao = m.descricao
            if apenas_urgentes and s.urgencia not in {"CRÍTICA", "ALTA"}:
                continue
            sugestoes.append(s)
        return sugestoes

    async def listar_perdas_ocultas(
        self,
    ) -> Union[list[PerdasOcultas], dict[str, str]]:
        """Perdas ocultas exigem histórico de vendas/estoque — não inventar."""
        if self.webposto_client is None:
            return _fonte_indisponivel("webposto_client não injetado")
        # Cliente de fábrica (src.webposto) não expõe série de dias sem venda por SKU.
        return _fonte_indisponivel(
            "cliente WebPosto (src.webposto) não expõe histórico de dias sem venda "
            "nem quantidade parada por produto para detectar perdas ocultas"
        )

    async def gerar_relatorio_precificacao(
        self,
    ) -> dict:
        """Gerar relatório consolidado de precificação (honesto se a fonte faltar)."""
        data_audit = _agora_br()

        margens_negativas_raw = await self.identificar_margens_negativas()
        margens_baixas_raw = await self.identificar_produtos_baixa_margem(15)

        # Só aborta o relatório inteiro se NENHUMA das fontes de margem respondeu.
        if (
            isinstance(margens_negativas_raw, dict)
            and margens_negativas_raw.get("status") == "fonte_indisponivel"
            and isinstance(margens_baixas_raw, dict)
            and margens_baixas_raw.get("status") == "fonte_indisponivel"
        ):
            return {
                **margens_negativas_raw,
                "data_audit": data_audit,
                "detalhe_baixa_margem": margens_baixas_raw,
            }

        margens_negativas: list[AnaliseMargem] = (
            []
            if isinstance(margens_negativas_raw, dict)
            else list(margens_negativas_raw)
        )
        margens_baixas: list[AnaliseMargem] = (
            []
            if isinstance(margens_baixas_raw, dict)
            else list(margens_baixas_raw)
        )

        perdas_ocultas = await self.listar_perdas_ocultas()
        perdas_lista: list[PerdasOcultas] = []
        perdas_meta: dict[str, str] | None = None
        if isinstance(perdas_ocultas, dict) and perdas_ocultas.get("status") == "fonte_indisponivel":
            perdas_meta = perdas_ocultas
        else:
            perdas_lista = list(perdas_ocultas)

        sugestoes_reajuste = await self.gerar_sugestoes_reajuste()
        sugestoes_lista: list[SugestaoReajuste] = []
        sugestoes_meta: dict[str, str] | None = None
        if isinstance(sugestoes_reajuste, dict) and sugestoes_reajuste.get("status") == "fonte_indisponivel":
            sugestoes_meta = sugestoes_reajuste
        else:
            sugestoes_lista = list(sugestoes_reajuste)

        impacto_margens_negativas = sum(
            (abs(m.margem_bruta) for m in margens_negativas),
            Decimal("0"),
        )
        impacto_reajustes = sum((s.impacto_mensal for s in sugestoes_lista), Decimal("0"))
        impacto_perdas_ocultas = sum(
            (p.perda_estimada_mensal for p in perdas_lista),
            Decimal("0"),
        )
        impacto_total = impacto_margens_negativas + impacto_reajustes + impacto_perdas_ocultas

        if len(margens_negativas) > 0:
            status = "CRÍTICO"
        elif len(margens_baixas) > 5:
            status = "ALERTA"
        else:
            status = "OK"

        out: dict[str, Any] = {
            "data_audit": data_audit,
            "estado": "PE",
            "margens_negativas": len(margens_negativas),
            "margens_baixas": len(margens_baixas),
            "oportunidades_reajuste": len(sugestoes_lista),
            "perdas_ocultas_detectadas": len(perdas_lista),
            "impacto_margens_negativas": float(impacto_margens_negativas),
            "impacto_reajustes": float(impacto_reajustes),
            "impacto_perdas_ocultas": float(impacto_perdas_ocultas),
            "impacto_total_mensal": float(impacto_total),
            "recomendacoes": [
                f"Corrigir {len(margens_negativas)} produtos com margem negativa",
                f"Aplicar reajustes em {len(sugestoes_lista)} produtos",
                f"Investigar {len(perdas_lista)} produtos com perdas ocultas",
            ],
            "status": status,
        }
        if isinstance(margens_negativas_raw, dict):
            out["margens_negativas_fonte"] = margens_negativas_raw
        if isinstance(margens_baixas_raw, dict):
            out["margens_baixas_fonte"] = margens_baixas_raw
        if perdas_meta:
            out["perdas_ocultas"] = perdas_meta
        if sugestoes_meta:
            out["sugestoes_reajuste"] = sugestoes_meta
        return out

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
