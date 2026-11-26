"""Diretor IA — orquestra Comprador, Tax, Precificador, Compras e Financeiro.

Não reimplementa as análises: só chama os métodos de relatório já existentes,
normaliza achados e ordena por impacto em R$. Não soma fontes distintas sem
origem. fonte_indisponivel vira pendência, nunca zero inventado.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ_RECIFE = ZoneInfo("America/Recife")

AREA_COMPRAS = "compras"
AREA_FISCAL = "fiscal"
AREA_PRECIFICACAO = "precificação"
AREA_VALIDACAO = "validação_compras"
AREA_FINANCEIRO = "financeiro"

STATUS_OK = "ok"
STATUS_INDISPONIVEL = "fonte_indisponivel"
STATUS_ERRO = "erro"
STATUS_VAZIO = "vazio"


def _agora_br() -> str:
    return datetime.now(TZ_RECIFE).strftime("%d/%m/%Y %H:%M")


# Milhar BR sem centavos: 1.000 | 12.345 | 1.234.567
_RE_MILHAR_BR = re.compile(r"^[-+]?\d{1,3}(?:\.\d{3})+$")
# Candidato numérico em texto (BR com/sem centavos, US decimal ou inteiro)
_RE_NUMERO_RS = re.compile(
    r"[-+]?(?:\d{1,3}(?:\.\d{3})+,\d+|\d{1,3}(?:\.\d{3})+|\d+,\d+|\d+\.\d+|\d+)"
)


def _parse_rs(valor: Any) -> float | None:
    """Extrai número de R$ a partir de float/Decimal/str; None se inválido/vazio.

    Regras (explicitas — não chutar):
    - Com vírgula → formato brasileiro: ponto é milhar, vírgula é decimal.
      Ex.: ``1.000,50`` → 1000.5; ``980,00`` → 980.0.
    - Sem vírgula e com grupos de três dígitos separados por ponto
      (``1.000``, ``1.234.567``) → ponto é milhar.
      Ex.: ``R$ 1.000`` → 1000.0.
    - Caso contrário → ponto é decimal.
      Ex.: ``1000.50`` → 1000.5; ``980.5`` → 980.5.
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float, Decimal)):
        try:
            return float(Decimal(str(valor)))
        except (InvalidOperation, ValueError):
            return None
    texto = str(valor).strip()
    if not texto:
        return None
    limpo = texto.replace("R$", "").replace("r$", "").replace(" ", "")
    match = _RE_NUMERO_RS.search(limpo)
    if not match:
        return None
    num = match.group(0)
    if "," in num:
        normalizado = num.replace(".", "").replace(",", ".")
    elif _RE_MILHAR_BR.fullmatch(num):
        normalizado = num.replace(".", "")
    else:
        normalizado = num
    try:
        return float(Decimal(normalizado))
    except (InvalidOperation, ValueError):
        return None


@dataclass
class AchadoDiretor:
    area: str
    achado: str
    impacto_rs: float | None
    urgencia: str
    acao_sugerida: str
    origem: str
    status_fonte: str = STATUS_OK

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StatusIA:
    ia: str
    status: str
    metodo: str
    motivo: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BriefDiretor:
    data_audit: str
    status_ias: list[StatusIA]
    achados: list[AchadoDiretor]
    impacto_total_rs: float
    achados_sem_valor: list[AchadoDiretor]
    mensagem: str
    pendencias: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_audit": self.data_audit,
            "status_ias": [s.to_dict() for s in self.status_ias],
            "achados": [a.to_dict() for a in self.achados],
            "impacto_total_rs": self.impacto_total_rs,
            "achados_sem_valor": [a.to_dict() for a in self.achados_sem_valor],
            "mensagem": self.mensagem,
            "pendencias": list(self.pendencias),
        }


class DiretorOrquestrador:
    """Recebe analisadores por injeção e monta o brief executivo."""

    def __init__(
        self,
        *,
        buyer_analyzer: Optional[object] = None,
        tax_analyzer: Optional[object] = None,
        pricing_analyzer: Optional[object] = None,
        compras_validator: Optional[object] = None,
        financeiro_analyzer: Optional[object] = None,
    ) -> None:
        self.buyer_analyzer = buyer_analyzer
        self.tax_analyzer = tax_analyzer
        self.pricing_analyzer = pricing_analyzer
        self.compras_validator = compras_validator
        self.financeiro_analyzer = financeiro_analyzer

    async def gerar_brief(self) -> dict[str, Any]:
        status_ias: list[StatusIA] = []
        achados: list[AchadoDiretor] = []
        pendencias: list[str] = []

        for nome, coletor in (
            ("Comprador IA", self._coletar_buyer),
            ("Tax Advisor IA", self._coletar_tax),
            ("Precificador IA", self._coletar_pricing),
            ("Validação de Compras", self._coletar_compras),
            ("Financeiro IA", self._coletar_financeiro),
        ):
            try:
                st, itens = await coletor()
            except Exception as exc:  # noqa: BLE001 — uma IA não derruba as outras
                logger.exception("Diretor IA: falha ao coletar %s", nome)
                st = StatusIA(
                    ia=nome,
                    status=STATUS_ERRO,
                    metodo="(exceção na coleta)",
                    motivo=f"{type(exc).__name__}: {exc}",
                )
                itens = []
            status_ias.append(st)
            if st.status == STATUS_INDISPONIVEL:
                pendencias.append(f"{nome}: {st.motivo or 'fonte indisponível'}")
            elif st.status == STATUS_ERRO:
                pendencias.append(f"{nome}: erro — {st.motivo or 'sem detalhe'}")
            achados.extend(itens)

        com_valor = [a for a in achados if a.impacto_rs is not None]
        sem_valor = [a for a in achados if a.impacto_rs is None]
        com_valor.sort(key=lambda a: abs(a.impacto_rs or 0.0), reverse=True)

        # Não funde achados: cada item permanece distinto mesmo com mesmo valor/origem
        total = float(
            sum((Decimal(str(a.impacto_rs)) for a in com_valor), Decimal("0")).quantize(
                Decimal("0.01")
            )
        )

        if not achados and not pendencias:
            mensagem = (
                "Não há achados no momento: as cinco IAs responderam sem "
                "problemas a reportar. Nada foi inventado."
            )
        elif not com_valor and pendencias:
            mensagem = (
                "Há pendências de fonte ou erro nas IAs; nenhum impacto em R$ "
                "foi somado a partir de fontes indisponíveis."
            )
        elif not com_valor:
            mensagem = (
                "Há achados sem valor em R$ calculado pela própria IA; "
                "nada foi inventado no total."
            )
        else:
            mensagem = (
                f"Há {len(com_valor)} achado(s) com impacto informado, "
                f"totalizando R$ {total:,.2f}. "
                f"{len(sem_valor)} sem valor calculado; "
                f"{len(pendencias)} pendência(s) de fonte/erro."
            ).replace(",", "X").replace(".", ",").replace("X", ".")

        brief = BriefDiretor(
            data_audit=_agora_br(),
            status_ias=status_ias,
            achados=com_valor,
            impacto_total_rs=total,
            achados_sem_valor=sem_valor,
            mensagem=mensagem,
            pendencias=pendencias,
        )
        return brief.to_dict()

    # ---------- coletores ----------

    async def _coletar_buyer(self) -> tuple[StatusIA, list[AchadoDiretor]]:
        metodo = "BuyerAnalyzer.generate_executive_brief"
        ia = "Comprador IA"
        if self.buyer_analyzer is None:
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_INDISPONIVEL,
                    metodo=metodo,
                    motivo="BuyerAnalyzer não injetado",
                ),
                [],
            )
        rel = await self.buyer_analyzer.generate_executive_brief()
        return self._normalizar_buyer(rel, metodo)

    async def _coletar_tax(self) -> tuple[StatusIA, list[AchadoDiretor]]:
        metodo = "TaxAdvisorAnalyzer.generate_tax_audit_report"
        ia = "Tax Advisor IA"
        if self.tax_analyzer is None:
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_INDISPONIVEL,
                    metodo=metodo,
                    motivo="TaxAdvisorAnalyzer não injetado",
                ),
                [],
            )
        rel = await self.tax_analyzer.generate_tax_audit_report()
        return self._normalizar_tax(rel, metodo)

    async def _coletar_pricing(self) -> tuple[StatusIA, list[AchadoDiretor]]:
        metodo = "PricingAnalyzer.gerar_relatorio_precificacao"
        ia = "Precificador IA"
        if self.pricing_analyzer is None:
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_INDISPONIVEL,
                    metodo=metodo,
                    motivo="PricingAnalyzer não injetado",
                ),
                [],
            )
        rel = await self.pricing_analyzer.gerar_relatorio_precificacao()
        return self._normalizar_pricing(rel, metodo)

    async def _coletar_compras(self) -> tuple[StatusIA, list[AchadoDiretor]]:
        metodo = "ComprasDataValidator.generate_data_quality_report"
        ia = "Validação de Compras"
        if self.compras_validator is None:
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_INDISPONIVEL,
                    metodo=metodo,
                    motivo="ComprasDataValidator não injetado",
                ),
                [],
            )
        hoje = datetime.now(TZ_RECIFE).date()
        inicio = (hoje - timedelta(days=30)).isoformat()
        fim = hoje.isoformat()
        rel = await self.compras_validator.generate_data_quality_report(inicio, fim)
        return self._normalizar_compras(rel, metodo)

    async def _coletar_financeiro(self) -> tuple[StatusIA, list[AchadoDiretor]]:
        metodo = "FinanceiroAnalyzer.gerar_relatorio_financeiro"
        ia = "Financeiro IA"
        if self.financeiro_analyzer is None:
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_INDISPONIVEL,
                    metodo=metodo,
                    motivo="FinanceiroAnalyzer não injetado",
                ),
                [],
            )
        rel = await self.financeiro_analyzer.gerar_relatorio_financeiro()
        return self._normalizar_financeiro(rel, metodo)

    # ---------- normalizadores ----------

    @staticmethod
    def _eh_indisponivel(rel: Any) -> tuple[bool, str | None]:
        if not isinstance(rel, dict):
            return False, None
        if rel.get("status") == STATUS_INDISPONIVEL:
            return True, str(rel.get("motivo") or "fonte_indisponivel")
        return False, None

    def _normalizar_buyer(
        self, rel: Any, metodo: str
    ) -> tuple[StatusIA, list[AchadoDiretor]]:
        ia = "Comprador IA"
        indisponivel, motivo = self._eh_indisponivel(rel)
        if indisponivel:
            return (
                StatusIA(ia=ia, status=STATUS_INDISPONIVEL, metodo=metodo, motivo=motivo),
                [],
            )
        if not isinstance(rel, dict):
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_ERRO,
                    metodo=metodo,
                    motivo="relatório do Comprador IA em formato inválido",
                ),
                [],
            )
        achados: list[AchadoDiretor] = []
        for item in rel.get("top_problemas") or []:
            if not isinstance(item, dict):
                continue
            impacto = _parse_rs(item.get("impacto"))
            if impacto is None:
                impacto = _parse_rs(item.get("ganho_estimado"))
            achados.append(
                AchadoDiretor(
                    area=AREA_COMPRAS,
                    achado=str(item.get("problema") or "problema de compras"),
                    impacto_rs=impacto,
                    urgencia=str(item.get("prioridade") or "MEDIA"),
                    acao_sugerida=str(item.get("acao") or "Revisar compras"),
                    origem=metodo,
                    status_fonte=STATUS_OK,
                )
            )
        economia = _parse_rs(rel.get("economia_potencial_total"))
        if economia is not None and economia > 0 and not achados:
            achados.append(
                AchadoDiretor(
                    area=AREA_COMPRAS,
                    achado="Economia potencial consolidada nas recomendações de reposição",
                    impacto_rs=economia,
                    urgencia="ALTA",
                    acao_sugerida="Priorizar reposições sugeridas pelo Comprador IA",
                    origem=metodo,
                    status_fonte=STATUS_OK,
                )
            )
        status = STATUS_VAZIO if not achados else STATUS_OK
        return StatusIA(ia=ia, status=status, metodo=metodo), achados

    def _normalizar_tax(
        self, rel: Any, metodo: str
    ) -> tuple[StatusIA, list[AchadoDiretor]]:
        ia = "Tax Advisor IA"
        indisponivel, motivo = self._eh_indisponivel(rel)
        if indisponivel:
            return (
                StatusIA(ia=ia, status=STATUS_INDISPONIVEL, metodo=metodo, motivo=motivo),
                [],
            )
        if not isinstance(rel, dict):
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_ERRO,
                    metodo=metodo,
                    motivo="relatório do Tax Advisor em formato inválido",
                ),
                [],
            )
        achados: list[AchadoDiretor] = []
        risco = _parse_rs(rel.get("risco_fiscal_estimado"))
        problemas = int(rel.get("problemas_encontrados") or 0)
        acoes = rel.get("recomendacoes") or []
        acao = acoes[0] if acoes else "Revisar classificação fiscal"
        if risco is not None and risco > 0:
            achados.append(
                AchadoDiretor(
                    area=AREA_FISCAL,
                    achado=(
                        f"{problemas} problema(s) tributário(s) "
                        f"({rel.get('problemas_criticos', 0)} crítico(s))"
                    ),
                    impacto_rs=risco,
                    urgencia="CRÍTICA" if (rel.get("problemas_criticos") or 0) > 0 else "ALTA",
                    acao_sugerida=str(acao),
                    origem=metodo,
                    status_fonte=STATUS_OK,
                )
            )
        elif problemas > 0:
            achados.append(
                AchadoDiretor(
                    area=AREA_FISCAL,
                    achado=f"{problemas} problema(s) tributário(s) sem risco monetário informado",
                    impacto_rs=None,
                    urgencia="ALTA",
                    acao_sugerida=str(acao),
                    origem=metodo,
                    status_fonte=STATUS_OK,
                )
            )
        status = STATUS_VAZIO if not achados else STATUS_OK
        return StatusIA(ia=ia, status=status, metodo=metodo), achados

    def _normalizar_pricing(
        self, rel: Any, metodo: str
    ) -> tuple[StatusIA, list[AchadoDiretor]]:
        ia = "Precificador IA"
        indisponivel, motivo = self._eh_indisponivel(rel)
        if indisponivel:
            return (
                StatusIA(ia=ia, status=STATUS_INDISPONIVEL, metodo=metodo, motivo=motivo),
                [],
            )
        if not isinstance(rel, dict):
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_ERRO,
                    metodo=metodo,
                    motivo="relatório do Precificador em formato inválido",
                ),
                [],
            )
        achados: list[AchadoDiretor] = []
        impacto = _parse_rs(rel.get("impacto_total_mensal"))
        recs = rel.get("recomendacoes") or []
        acao = recs[0] if recs else "Revisar margens e reajustes"
        neg = int(rel.get("margens_negativas") or 0)
        if impacto is not None and impacto > 0:
            achados.append(
                AchadoDiretor(
                    area=AREA_PRECIFICACAO,
                    achado=(
                        f"Impacto mensal de precificação "
                        f"({neg} margem(ns) negativa(s))"
                    ),
                    impacto_rs=impacto,
                    urgencia="CRÍTICA" if neg > 0 else "ALTA",
                    acao_sugerida=str(acao),
                    origem=metodo,
                    status_fonte=STATUS_OK,
                )
            )
        elif neg > 0:
            achados.append(
                AchadoDiretor(
                    area=AREA_PRECIFICACAO,
                    achado=f"{neg} produto(s) com margem negativa",
                    impacto_rs=_parse_rs(rel.get("impacto_margens_negativas")),
                    urgencia="CRÍTICA",
                    acao_sugerida=str(acao),
                    origem=metodo,
                    status_fonte=STATUS_OK,
                )
            )
        status = STATUS_VAZIO if not achados else STATUS_OK
        return StatusIA(ia=ia, status=status, metodo=metodo), achados

    def _normalizar_compras(
        self, rel: Any, metodo: str
    ) -> tuple[StatusIA, list[AchadoDiretor]]:
        ia = "Validação de Compras"
        indisponivel, motivo = self._eh_indisponivel(rel)
        if indisponivel:
            return (
                StatusIA(ia=ia, status=STATUS_INDISPONIVEL, metodo=metodo, motivo=motivo),
                [],
            )
        if not isinstance(rel, dict):
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_ERRO,
                    metodo=metodo,
                    motivo="relatório de Validação de Compras em formato inválido",
                ),
                [],
            )
        achados: list[AchadoDiretor] = []
        problemas = int(rel.get("compras_com_problema") or 0)
        anomalias = int(rel.get("anomalias_preco_detectadas") or 0)
        recs = rel.get("recomendacoes") or []
        if problemas > 0:
            achados.append(
                AchadoDiretor(
                    area=AREA_VALIDACAO,
                    achado=f"{problemas} compra(s) com dados inconsistentes",
                    impacto_rs=None,  # validador não informa R$
                    urgencia="ALTA",
                    acao_sugerida=str(recs[0] if recs else "Revisar compras inconsistentes"),
                    origem=metodo,
                    status_fonte=STATUS_OK,
                )
            )
        if anomalias > 0:
            achados.append(
                AchadoDiretor(
                    area=AREA_VALIDACAO,
                    achado=f"{anomalias} anomalia(s) de preço em fornecedores",
                    impacto_rs=None,
                    urgencia="MEDIA",
                    acao_sugerida=str(
                        recs[1] if len(recs) > 1 else (recs[0] if recs else "Negociar com fornecedores")
                    ),
                    origem=metodo,
                    status_fonte=STATUS_OK,
                )
            )
        status = STATUS_VAZIO if not achados else STATUS_OK
        return StatusIA(ia=ia, status=status, metodo=metodo), achados

    def _normalizar_financeiro(
        self, rel: Any, metodo: str
    ) -> tuple[StatusIA, list[AchadoDiretor]]:
        ia = "Financeiro IA"
        indisponivel, motivo = self._eh_indisponivel(rel)
        if indisponivel:
            return (
                StatusIA(ia=ia, status=STATUS_INDISPONIVEL, metodo=metodo, motivo=motivo),
                [],
            )
        if not isinstance(rel, dict):
            return (
                StatusIA(
                    ia=ia,
                    status=STATUS_ERRO,
                    metodo=metodo,
                    motivo="relatório do Financeiro IA em formato inválido",
                ),
                [],
            )
        achados: list[AchadoDiretor] = []
        blocos = rel.get("blocos") or {}
        if not isinstance(blocos, dict):
            blocos = {}

        inad = blocos.get("inadimplencia") or {}
        if isinstance(inad, dict) and inad.get("status") != STATUS_INDISPONIVEL:
            valor = _parse_rs(inad.get("valor_total_inadimplencia"))
            qtd = int(inad.get("quantidade") or 0)
            if qtd > 0 or (valor is not None and valor > 0):
                achados.append(
                    AchadoDiretor(
                        area=AREA_FINANCEIRO,
                        achado=f"Inadimplência: {qtd} título(s) vencido(s)",
                        impacto_rs=valor,
                        urgencia="ALTA",
                        acao_sugerida="Cobrar clientes ou negociar prazo",
                        origem=f"{metodo}/inadimplencia",
                        status_fonte=STATUS_OK,
                    )
                )

        cartoes = blocos.get("conferencia_cartoes") or {}
        if isinstance(cartoes, dict) and cartoes.get("status") != STATUS_INDISPONIVEL:
            dif = _parse_rs(cartoes.get("diferenca_total"))
            if dif is not None and abs(dif) > 0:
                achados.append(
                    AchadoDiretor(
                        area=AREA_FINANCEIRO,
                        achado=f"Diferença na conferência de cartões: R$ {abs(dif):.2f}",
                        impacto_rs=abs(dif),
                        urgencia="ALTA",
                        acao_sugerida="Conferir vendas webPosto × adquirentes",
                        origem=f"{metodo}/conferencia_cartoes",
                        status_fonte=STATUS_OK,
                    )
                )

        despesas = blocos.get("despesas_problematicas") or {}
        if isinstance(despesas, dict) and despesas.get("status") != STATUS_INDISPONIVEL:
            qtd = int(despesas.get("quantidade") or 0)
            valor = _parse_rs(despesas.get("valor_total"))
            if qtd > 0:
                achados.append(
                    AchadoDiretor(
                        area=AREA_FINANCEIRO,
                        achado=f"{qtd} despesa(s) sem categoria ou comprovante",
                        impacto_rs=valor,
                        urgencia="MEDIA",
                        acao_sugerida="Classificar no plano/conta e anexar comprovante",
                        origem=f"{metodo}/despesas_problematicas",
                        status_fonte=STATUS_OK,
                    )
                )

        fluxo = blocos.get("fluxo_caixa") or {}
        if isinstance(fluxo, dict) and fluxo.get("status") == "CRÍTICO":
            alertas = fluxo.get("alertas_saldo_negativo") or []
            primeiro = alertas[0] if alertas else {}
            saldo = _parse_rs(
                primeiro.get("saldo_projetado") if isinstance(primeiro, dict) else None
            )
            achados.append(
                AchadoDiretor(
                    area=AREA_FINANCEIRO,
                    achado="Saldo de caixa projetado negativo no horizonte",
                    impacto_rs=abs(saldo) if saldo is not None else None,
                    urgencia="CRÍTICA",
                    acao_sugerida=str(
                        (primeiro.get("correcao_sugerida") if isinstance(primeiro, dict) else None)
                        or "Antecipar recebíveis ou reduzir saídas"
                    ),
                    origem=f"{metodo}/fluxo_caixa",
                    status_fonte=STATUS_OK,
                )
            )

        for chave in rel.get("blocos_fonte_indisponivel") or []:
            bloco = blocos.get(chave) if isinstance(blocos, dict) else None
            motivo_bloco = None
            if isinstance(bloco, dict):
                motivo_bloco = bloco.get("motivo")
            # pendência parcial: não inventa zero; sinaliza via achado sem valor
            achados.append(
                AchadoDiretor(
                    area=AREA_FINANCEIRO,
                    achado=f"Bloco financeiro '{chave}' sem fonte",
                    impacto_rs=None,
                    urgencia="MEDIA",
                    acao_sugerida="Verificar credenciais/fonte do bloco",
                    origem=f"{metodo}/{chave}",
                    status_fonte=STATUS_INDISPONIVEL,
                )
            )
            if motivo_bloco:
                # motivo preservado no achado via acao se necessário — status board já OK/PARCIAL
                pass

        status = STATUS_VAZIO if not achados else STATUS_OK
        # Se o relatório veio PARCIAL mas só com indisponíveis sem achados monetários
        if rel.get("status") == "PARCIAL" and not any(a.impacto_rs for a in achados):
            status = STATUS_OK
        return StatusIA(ia=ia, status=status, metodo=metodo), achados


__all__ = [
    "DiretorOrquestrador",
    "AchadoDiretor",
    "StatusIA",
    "BriefDiretor",
]
