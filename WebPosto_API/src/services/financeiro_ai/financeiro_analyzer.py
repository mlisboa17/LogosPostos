"""Financeiro IA — análise honesta de caixa, cartões, inadimplência e saídas.

Reutiliza normalização monetária de ``financial_reconciliation_engine``.
Não concilia depósito × extrato bancário (fora do escopo).
Não identifica caixa por frentista — só posto + setor/centro ou nome do caixa.
Empresa canônica de conveniência: Doze Filial (74014), não "Real".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from src.services.financial_reconciliation_engine import to_decimal

TZ_RECIFE = ZoneInfo("America/Recife")

# Posto Doze Filial II — substitui a antiga unidade "Real"
EMPRESA_DOZE_FILIAL = 74014
EMPRESA_DOZE_FILIAL_NOME = "POSTO DOZE FILIAL II"

ADQUIRENTES_ESPERADAS = ("PagBank", "Cielo", "Premmia", "Mais Pagamentos")


def _agora_br() -> str:
    return datetime.now(TZ_RECIFE).strftime("%d/%m/%Y %H:%M")


def _fonte_indisponivel(motivo: str) -> dict[str, str]:
    return {"status": "fonte_indisponivel", "motivo": motivo}


def _fmt_dia(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _parse_dia(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    s = str(v).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


@dataclass
class MovimentoDia:
    dia: str  # dd/mm/aaaa
    entradas: Decimal
    saidas: Decimal
    saldo_dia: Decimal
    saldo_projetado: Decimal


@dataclass
class AlertaSaldoNegativo:
    dia: str
    saldo_projetado: Decimal
    mensagem: str
    correcao_sugerida: str


@dataclass
class DiferencaCartao:
    dia: str
    bandeira: str
    adquirente: str
    venda_webposto: Decimal
    recebido_adquirente: Decimal
    diferenca: Decimal
    causa: str
    mensagem: str
    correcao_sugerida: str


@dataclass
class TituloInadimplente:
    titulo_codigo: str
    cliente: str
    tipo_cliente: str  # FROTA | PRAZO | OUTRO
    valor: Decimal
    vencimento: str
    dias_atraso: int
    impacto: str
    mensagem: str
    correcao_sugerida: str


@dataclass
class DespesaProblema:
    despesa_id: str
    posto: str
    caixa_id: str  # posto+setor/centro ou nome do caixa — nunca frentista
    valor: Decimal
    data: str
    problemas: list[str] = field(default_factory=list)
    mensagem: str = ""
    correcao_sugerida: str = ""


@dataclass
class AporteAviso:
    """Aporte de outra origem — não entra na conciliação de cartões/caixa."""

    origem: str
    valor: Decimal
    dia: str
    mensagem: str


class FinanceiroAnalyzer:
    """Analisador financeiro (somente leitura / diagnóstico)."""

    def __init__(
        self,
        webposto_client: Optional[object] = None,
        *,
        empresa_codigo: int = EMPRESA_DOZE_FILIAL,
        horizonte_dias_padrao: int = 7,
    ) -> None:
        self.webposto_client = webposto_client
        self.empresa_codigo = empresa_codigo
        self.horizonte_dias_padrao = horizonte_dias_padrao

    # ---------- 1. Fluxo de caixa projetado ----------

    async def projetar_fluxo_caixa(
        self,
        *,
        movimentos: list[dict[str, Any]] | None = None,
        saldo_inicial: Decimal | float | str | None = None,
        horizonte_dias: int | None = None,
        data_referencia: date | None = None,
    ) -> dict[str, Any]:
        """Projeta entradas/saídas por dia e alerta saldo negativo em N dias.

        ``movimentos`` espera itens com ``dia`` (ISO ou date), ``entradas``, ``saidas``.
        Sem movimentos e sem cliente capaz de fornecê-los → fonte_indisponivel.
        """
        n = horizonte_dias if horizonte_dias is not None else self.horizonte_dias_padrao
        ref = data_referencia or datetime.now(TZ_RECIFE).date()

        if movimentos is None:
            carregado = await self._carregar_movimentos_fluxo(ref, n)
            if isinstance(carregado, dict) and carregado.get("status") == "fonte_indisponivel":
                return {**carregado, "data_audit": _agora_br()}
            movimentos = carregado

        if not isinstance(movimentos, list) or len(movimentos) == 0:
            return _fonte_indisponivel(
                "sem movimentos de entrada/saída para projetar o fluxo; "
                "lista vazia não autoriza concluir que o caixa está saudável"
            )

        saldo = to_decimal(saldo_inicial if saldo_inicial is not None else 0)
        por_dia: dict[date, dict[str, Decimal]] = defaultdict(
            lambda: {"entradas": Decimal("0.00"), "saidas": Decimal("0.00")}
        )
        for row in movimentos:
            if not isinstance(row, dict):
                continue
            dia = _parse_dia(row.get("dia") or row.get("data") or row.get("periodo"))
            if dia is None:
                continue
            por_dia[dia]["entradas"] += to_decimal(
                row.get("entradas") or row.get("entradasPrevistas") or 0
            )
            por_dia[dia]["saidas"] += to_decimal(
                row.get("saidas") or row.get("saidasPrevistas") or 0
            )

        limite = ref + timedelta(days=max(n, 0))
        dias_ordenados = sorted(d for d in por_dia if ref <= d <= limite)
        if not dias_ordenados:
            # usa os dias informados mesmo fora da janela se a janela estiver vazia
            dias_ordenados = sorted(por_dia.keys())
        if not dias_ordenados:
            return _fonte_indisponivel(
                "movimentos sem datas válidas; não é possível projetar o saldo"
            )

        serie: list[dict[str, Any]] = []
        alertas: list[dict[str, Any]] = []
        for dia in dias_ordenados:
            ent = por_dia[dia]["entradas"]
            sai = por_dia[dia]["saidas"]
            saldo_dia = (ent - sai).quantize(Decimal("0.01"))
            saldo = (saldo + saldo_dia).quantize(Decimal("0.01"))
            item = MovimentoDia(
                dia=_fmt_dia(dia),
                entradas=ent,
                saidas=sai,
                saldo_dia=saldo_dia,
                saldo_projetado=saldo,
            )
            serie.append(
                {
                    "dia": item.dia,
                    "entradas": float(item.entradas),
                    "saidas": float(item.saidas),
                    "saldo_dia": float(item.saldo_dia),
                    "saldo_projetado": float(item.saldo_projetado),
                }
            )
            if saldo < 0 and dia <= ref + timedelta(days=n):
                alertas.append(
                    {
                        "dia": item.dia,
                        "saldo_projetado": float(saldo),
                        "mensagem": (
                            f"No dia {item.dia} o saldo projetado fica negativo "
                            f"(R$ {saldo})."
                        ),
                        "correcao_sugerida": (
                            "Antecipe recebíveis, reduza saídas neste dia ou "
                            "programe um aporte identificado (aporte não entra na conciliação)."
                        ),
                    }
                )

        status = "CRÍTICO" if alertas else "OK"
        return {
            "status": status,
            "data_audit": _agora_br(),
            "empresa_codigo": self.empresa_codigo,
            "empresa_nome": EMPRESA_DOZE_FILIAL_NOME
            if self.empresa_codigo == EMPRESA_DOZE_FILIAL
            else str(self.empresa_codigo),
            "horizonte_dias": n,
            "saldo_inicial": float(to_decimal(saldo_inicial if saldo_inicial is not None else 0)),
            "serie_diaria": serie,
            "alertas_saldo_negativo": alertas,
            "observacao": (
                "Caixa identificado por posto + setor/centro de custo ou nome do caixa; "
                "nunca por frentista. Aportes de outra origem geram aviso próprio."
            ),
        }

    async def _carregar_movimentos_fluxo(
        self, ref: date, n: int
    ) -> list[dict[str, Any]] | dict[str, str]:
        if self.webposto_client is None:
            return _fonte_indisponivel(
                "webposto_client não injetado; informe movimentos=... para projeção offline"
            )
        # Cliente de fábrica (src.webposto) não expõe série diária consolidada de fluxo.
        # CorporateCashFlowService depende de gateway async + finance center — fora desta fachada.
        return _fonte_indisponivel(
            "cliente WebPosto injetado não fornece série diária de entradas/saídas "
            "para projeção; use CorporateCashFlowService/cash_flow_snapshot ou "
            "passe movimentos explicitamente"
        )

    # ---------- 2. Conferência de cartões ----------

    async def conferir_cartoes(
        self,
        *,
        vendas_cartao: list[dict[str, Any]] | None = None,
        recebimentos_adquirentes: list[dict[str, Any]] | None = None,
        aportes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Compara vendas cartão (webPosto) × recebidos (PagBank/Cielo/Premmia/Mais Pagamentos).

        Diferença por dia e bandeira, em R$. Aportes não entram na conciliação.
        """
        if vendas_cartao is None or recebimentos_adquirentes is None:
            carregado = await self._carregar_fontes_cartao()
            if isinstance(carregado, dict) and carregado.get("status") == "fonte_indisponivel":
                return {**carregado, "data_audit": _agora_br()}
            vendas_cartao = carregado.get("vendas_cartao")  # type: ignore[assignment]
            recebimentos_adquirentes = carregado.get("recebimentos")  # type: ignore[assignment]

        if not isinstance(vendas_cartao, list) or not isinstance(recebimentos_adquirentes, list):
            return _fonte_indisponivel(
                "fontes de venda cartão e/ou recebimento de adquirente ausentes ou inválidas"
            )
        if len(vendas_cartao) == 0 and len(recebimentos_adquirentes) == 0:
            return _fonte_indisponivel(
                "nenhuma venda em cartão nem recebimento de adquirente informado; "
                "lista vazia não significa conferência ok"
            )

        # Agrega venda webPosto por (dia, bandeira)
        vendas_agg: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
        for row in vendas_cartao:
            if not isinstance(row, dict):
                continue
            dia = _parse_dia(row.get("dia") or row.get("data"))
            if dia is None:
                continue
            bandeira = str(row.get("bandeira") or row.get("forma") or "NÃO INFORMADA").strip()
            vendas_agg[(dia.isoformat(), bandeira)] += to_decimal(
                row.get("valor") or row.get("total") or 0
            )

        # Agrega recebidos por (dia, bandeira, adquirente)
        rec_agg: dict[tuple[str, str, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
        for row in recebimentos_adquirentes:
            if not isinstance(row, dict):
                continue
            dia = _parse_dia(row.get("dia") or row.get("data"))
            if dia is None:
                continue
            bandeira = str(row.get("bandeira") or row.get("forma") or "NÃO INFORMADA").strip()
            adquirente = str(row.get("adquirente") or row.get("plataforma") or "NÃO INFORMADA")
            rec_agg[(dia.isoformat(), bandeira, adquirente)] += to_decimal(
                row.get("valor") or row.get("recebido") or 0
            )

        # Totais por (dia, bandeira) nos recebimentos (soma adquirentes)
        rec_por_chave: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
        adquirente_por_chave: dict[tuple[str, str], str] = {}
        for (dia_s, bandeira, adq), valor in rec_agg.items():
            key = (dia_s, bandeira)
            rec_por_chave[key] += valor
            # se várias adquirentes, marca "várias"
            if key in adquirente_por_chave and adquirente_por_chave[key] != adq:
                adquirente_por_chave[key] = "várias"
            else:
                adquirente_por_chave[key] = adq

        chaves = set(vendas_agg.keys()) | set(rec_por_chave.keys())
        diferencas: list[dict[str, Any]] = []
        for dia_s, bandeira in sorted(chaves):
            venda = vendas_agg.get((dia_s, bandeira), Decimal("0.00"))
            recebido = rec_por_chave.get((dia_s, bandeira), Decimal("0.00"))
            diff = (venda - recebido).quantize(Decimal("0.01"))
            if diff == 0:
                continue
            dia_fmt = _fmt_dia(date.fromisoformat(dia_s))
            adquirente = adquirente_por_chave.get((dia_s, bandeira), "não informado")
            if diff > 0:
                causa = "webposto_maior_que_adquirente"
                mensagem = (
                    f"No dia {dia_fmt}, bandeira {bandeira}: venda no webPosto "
                    f"R$ {venda} e recebido R$ {recebido} ({adquirente}). "
                    f"Falta R$ {diff} no recebimento."
                )
                correcao = (
                    "Confira NSU/autorização na adquirente, taxas não lançadas "
                    "ou venda sem liquidação no dia."
                )
            else:
                causa = "adquirente_maior_que_webposto"
                mensagem = (
                    f"No dia {dia_fmt}, bandeira {bandeira}: recebido R$ {recebido} "
                    f"({adquirente}) maior que a venda no webPosto R$ {venda}. "
                    f"Excesso de R$ {abs(diff)}."
                )
                correcao = (
                    "Verifique lançamento duplicado na adquirente ou venda "
                    "não registrada no webPosto."
                )
            diferencas.append(
                {
                    "dia": dia_fmt,
                    "bandeira": bandeira,
                    "adquirente": adquirente,
                    "venda_webposto": float(venda),
                    "recebido_adquirente": float(recebido),
                    "diferenca": float(diff),
                    "causa": causa,
                    "mensagem": mensagem,
                    "correcao_sugerida": correcao,
                }
            )

        avisos_aporte: list[dict[str, Any]] = []
        for ap in aportes or []:
            if not isinstance(ap, dict):
                continue
            dia = _parse_dia(ap.get("dia") or ap.get("data"))
            valor = to_decimal(ap.get("valor"))
            avisos_aporte.append(
                {
                    "origem": str(ap.get("origem") or "outra origem"),
                    "valor": float(valor),
                    "dia": _fmt_dia(dia) if dia else "",
                    "mensagem": (
                        f"Aporte de {ap.get('origem') or 'outra origem'} "
                        f"(R$ {valor}) não entra na conciliação de cartões."
                    ),
                }
            )

        total_venda = sum(vendas_agg.values(), Decimal("0.00"))
        total_rec = sum(rec_por_chave.values(), Decimal("0.00"))
        return {
            "status": "DIVERGENTE" if diferencas else "OK",
            "data_audit": _agora_br(),
            "empresa_codigo": self.empresa_codigo,
            "adquirentes_esperadas": list(ADQUIRENTES_ESPERADAS),
            "total_venda_cartao_webposto": float(total_venda),
            "total_recebido_adquirentes": float(total_rec),
            "diferenca_total": float((total_venda - total_rec).quantize(Decimal("0.01"))),
            "diferencas": diferencas,
            "avisos_aporte": avisos_aporte,
            "escopo_excluido": "conciliação depósito × extrato bancário (fora do escopo)",
        }

    async def _carregar_fontes_cartao(self) -> dict[str, Any]:
        if self.webposto_client is None:
            return _fonte_indisponivel(
                "webposto_client não injetado e listas vendas_cartao/"
                "recebimentos_adquirentes não foram informadas"
            )
        # A conciliação operacional vive em cash_reconciliation (PagBank/Cielo/Premmia).
        # Esta fachada não baixa portal/adquirente sozinha para não inventar totais.
        return _fonte_indisponivel(
            "fonte de adquirentes (PagBank/Cielo/Premmia/Mais Pagamentos) não disponível "
            "nesta fachada; use o módulo cash_reconciliation ou informe "
            "vendas_cartao e recebimentos_adquirentes"
        )

    # ---------- 3. Recebimentos / inadimplência ----------

    async def listar_inadimplencia(
        self,
        *,
        titulos: list[dict[str, Any]] | None = None,
        data_referencia: date | None = None,
    ) -> dict[str, Any]:
        """Títulos vencidos e clientes frota/prazo em atraso."""
        ref = data_referencia or datetime.now(TZ_RECIFE).date()
        if titulos is None:
            carregado = await self._carregar_titulos_receber()
            if isinstance(carregado, dict) and carregado.get("status") == "fonte_indisponivel":
                return {**carregado, "data_audit": _agora_br()}
            titulos = carregado

        if not isinstance(titulos, list) or len(titulos) == 0:
            return _fonte_indisponivel(
                "nenhum título a receber informado; lista vazia não prova ausência de inadimplência"
            )

        itens: list[dict[str, Any]] = []
        total = Decimal("0.00")
        for row in titulos:
            if not isinstance(row, dict):
                continue
            # ignora já recebidos
            situacao = str(row.get("situacao") or row.get("status") or "").upper()
            if situacao in {"RECEBIDO", "PAGO", "BAIXADO", "QUITADO"}:
                continue
            venc = _parse_dia(
                row.get("dataVencimento") or row.get("vencimento") or row.get("vencimentoEm")
            )
            if venc is None or venc >= ref:
                continue
            valor = to_decimal(row.get("valor") or row.get("saldo") or 0)
            if valor <= 0:
                continue
            tipo = self._classificar_cliente(row)
            dias = (ref - venc).days
            codigo = str(
                row.get("tituloCodigo")
                or row.get("codigo")
                or row.get("tituloReceberCodigo")
                or ""
            )
            cliente = str(
                row.get("nomeCliente") or row.get("cliente") or row.get("fantasia") or ""
            )
            total += valor
            itens.append(
                {
                    "titulo_codigo": codigo,
                    "cliente": cliente,
                    "tipo_cliente": tipo,
                    "valor": float(valor),
                    "vencimento": _fmt_dia(venc),
                    "dias_atraso": dias,
                    "impacto": f"R$ {valor} parado há {dias} dia(s)",
                    "mensagem": (
                        f"Cliente {cliente or '(sem nome)'} ({tipo}) com título {codigo} "
                        f"vencido em {_fmt_dia(venc)} — atraso de {dias} dia(s), R$ {valor}."
                    ),
                    "correcao_sugerida": (
                        "Cobrar o cliente, negociar prazo ou baixar o título se já houve "
                        "recebimento não lançado."
                    ),
                }
            )

        if not itens:
            # Fonte existiu e foi analisada: zero vencidos é resultado legítimo.
            return {
                "status": "OK",
                "data_audit": _agora_br(),
                "empresa_codigo": self.empresa_codigo,
                "data_referencia": _fmt_dia(ref),
                "quantidade": 0,
                "valor_total_inadimplencia": 0.0,
                "titulos": [],
                "observacao": "fonte analisada; nenhum título vencido em aberto no recorte",
            }

        return {
            "status": "ALERTA",
            "data_audit": _agora_br(),
            "empresa_codigo": self.empresa_codigo,
            "data_referencia": _fmt_dia(ref),
            "quantidade": len(itens),
            "valor_total_inadimplencia": float(total.quantize(Decimal("0.01"))),
            "titulos": itens,
        }

    @staticmethod
    def _classificar_cliente(row: dict[str, Any]) -> str:
        texto = " ".join(
            str(row.get(k) or "")
            for k in (
                "tipoCliente",
                "clienteTipo",
                "grupoCliente",
                "nomeCliente",
                "observacao",
                "centroCusto",
                "centro_custo",
            )
        ).upper()
        if "FROTA" in texto:
            return "FROTA"
        if "PRAZO" in texto or "A PRAZO" in texto:
            return "PRAZO"
        return "OUTRO"

    async def _carregar_titulos_receber(self) -> list[dict[str, Any]] | dict[str, str]:
        if self.webposto_client is None:
            return _fonte_indisponivel(
                "webposto_client não injetado; informe titulos=... para análise offline"
            )
        fin = getattr(self.webposto_client, "financeiro", None)
        listar = getattr(fin, "listar_titulos_receber", None) if fin else None
        if not callable(listar):
            return _fonte_indisponivel(
                "cliente WebPosto não expõe financeiro.listar_titulos_receber"
            )
        try:
            rows = listar(empresa_codigo=self.empresa_codigo)
        except TypeError:
            try:
                rows = listar()
            except Exception as exc:  # noqa: BLE001
                return _fonte_indisponivel(
                    f"falha ao ler títulos a receber: {type(exc).__name__}: {exc}"
                )
        except Exception as exc:  # noqa: BLE001
            return _fonte_indisponivel(
                f"falha ao ler títulos a receber: {type(exc).__name__}: {exc}"
            )
        if not isinstance(rows, list):
            return _fonte_indisponivel("listar_titulos_receber não retornou lista")
        if len(rows) == 0:
            return _fonte_indisponivel(
                "listar_titulos_receber retornou zero registros; "
                "não dá para afirmar ausência de inadimplência"
            )
        return rows

    # ---------- 4. Saídas / despesas sem categoria ou comprovante ----------

    async def listar_despesas_problematicas(
        self,
        *,
        despesas: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Despesas de caixa sem categoria (plano/conta) ou sem comprovante.

        Mesma ideia do dashboard de auditoria (despesasSemConta + sem comprovante).
        Identifica o caixa por posto + setor/centro ou nome_caixa — nunca frentista.
        """
        if despesas is None:
            carregado = await self._carregar_despesas_caixa()
            if isinstance(carregado, dict) and carregado.get("status") == "fonte_indisponivel":
                return {**carregado, "data_audit": _agora_br()}
            despesas = carregado

        if not isinstance(despesas, list) or len(despesas) == 0:
            return _fonte_indisponivel(
                "nenhuma despesa de caixa informada; lista vazia não prova que não há "
                "despesa sem categoria/comprovante"
            )

        problemas: list[dict[str, Any]] = []
        for row in despesas:
            if not isinstance(row, dict):
                continue
            faltas: list[str] = []
            if self._sem_categoria(row):
                faltas.append("sem_categoria")
            if self._sem_comprovante(row):
                faltas.append("sem_comprovante")
            if not faltas:
                continue
            posto = str(
                row.get("posto")
                or row.get("filial")
                or row.get("empresaNome")
                or self.empresa_codigo
            )
            caixa_id = self._identidade_caixa(row, posto)
            # nunca usar frentista
            if "frentista" in caixa_id.lower():
                caixa_id = f"{posto}|CAIXA_NAO_IDENTIFICADO"
            valor = to_decimal(row.get("valor") or row.get("valorDespesa") or 0)
            dia = _parse_dia(row.get("data") or row.get("dataMovimento") or row.get("dia"))
            despesa_id = str(
                row.get("despesaCodigo")
                or row.get("codigo")
                or row.get("lancamentoCodigo")
                or ""
            )
            msg_faltas = " e ".join(
                "categoria (plano/conta)" if f == "sem_categoria" else "comprovante"
                for f in faltas
            )
            problemas.append(
                {
                    "despesa_id": despesa_id,
                    "posto": posto,
                    "caixa_id": caixa_id,
                    "valor": float(valor),
                    "data": _fmt_dia(dia) if dia else "",
                    "problemas": faltas,
                    "mensagem": (
                        f"Despesa {despesa_id or '(sem código)'} no caixa {caixa_id} "
                        f"está sem {msg_faltas} (R$ {valor})."
                    ),
                    "correcao_sugerida": (
                        "Classifique no plano/centro correto e anexe o comprovante "
                        "antes de fechar o caixa do dia."
                    ),
                }
            )

        if not problemas:
            return {
                "status": "OK",
                "data_audit": _agora_br(),
                "empresa_codigo": self.empresa_codigo,
                "quantidade": 0,
                "valor_total": 0.0,
                "despesas": [],
                "observacao": "fonte analisada; nenhuma despesa sem categoria/comprovante no recorte",
            }

        total = sum((to_decimal(p["valor"]) for p in problemas), Decimal("0.00"))
        return {
            "status": "ALERTA",
            "data_audit": _agora_br(),
            "empresa_codigo": self.empresa_codigo,
            "quantidade": len(problemas),
            "valor_total": float(total.quantize(Decimal("0.01"))),
            "despesas": problemas,
            "regra_caixa": (
                "Identificação por posto + setor/centro de custo ou nome do caixa; "
                "nunca por frentista (VIP tem 2 caixas/dia)."
            ),
        }

    @staticmethod
    def _sem_categoria(row: dict[str, Any]) -> bool:
        campos = (
            row.get("contaCodigo"),
            row.get("planoContaCodigo"),
            row.get("planoConta"),
            row.get("categoria"),
            row.get("plano_conta"),
        )
        return all(v in (None, "", 0, "0") for v in campos)

    @staticmethod
    def _sem_comprovante(row: dict[str, Any]) -> bool:
        if "tem_comprovante" in row:
            return not bool(row.get("tem_comprovante"))
        if "comprovante" in row:
            return row.get("comprovante") in (None, "", False, 0)
        if "arquivo_comprovante" in row:
            return row.get("arquivo_comprovante") in (None, "")
        # sem campo explícito: não inventa problema de comprovante
        return False

    @staticmethod
    def _identidade_caixa(row: dict[str, Any], posto: str) -> str:
        nome = str(
            row.get("nome_caixa")
            or row.get("caixaNome")
            or row.get("caixa")
            or ""
        ).strip()
        setor = str(
            row.get("setor")
            or row.get("centro_custo")
            or row.get("centroCusto")
            or row.get("centroCustoNome")
            or ""
        ).strip()
        if nome and setor:
            return f"{posto}|{setor}|{nome}"
        if nome:
            return f"{posto}|{nome}"
        if setor:
            return f"{posto}|{setor}"
        return f"{posto}|CAIXA_NAO_IDENTIFICADO"

    async def _carregar_despesas_caixa(self) -> list[dict[str, Any]] | dict[str, str]:
        if self.webposto_client is None:
            return _fonte_indisponivel(
                "webposto_client não injetado; informe despesas=... para análise offline"
            )
        return _fonte_indisponivel(
            "cliente WebPosto injetado não expõe despesas de caixa com categoria/"
            "comprovante nesta fachada; use cash_reconciliation/data_quality ou "
            "passe despesas explicitamente"
        )

    # ---------- Relatório consolidado ----------

    async def gerar_relatorio_financeiro(
        self,
        *,
        movimentos: list[dict[str, Any]] | None = None,
        vendas_cartao: list[dict[str, Any]] | None = None,
        recebimentos_adquirentes: list[dict[str, Any]] | None = None,
        titulos: list[dict[str, Any]] | None = None,
        despesas: list[dict[str, Any]] | None = None,
        saldo_inicial: Decimal | float | str | None = None,
        horizonte_dias: int | None = None,
    ) -> dict[str, Any]:
        """Consolida as quatro frentes; propaga fonte_indisponivel por bloco."""
        fluxo = await self.projetar_fluxo_caixa(
            movimentos=movimentos,
            saldo_inicial=saldo_inicial,
            horizonte_dias=horizonte_dias,
        )
        cartoes = await self.conferir_cartoes(
            vendas_cartao=vendas_cartao,
            recebimentos_adquirentes=recebimentos_adquirentes,
        )
        inad = await self.listar_inadimplencia(titulos=titulos)
        saidas = await self.listar_despesas_problematicas(despesas=despesas)

        blocos = {
            "fluxo_caixa": fluxo,
            "conferencia_cartoes": cartoes,
            "inadimplencia": inad,
            "despesas_problematicas": saidas,
        }
        indisponiveis = [
            k
            for k, v in blocos.items()
            if isinstance(v, dict) and v.get("status") == "fonte_indisponivel"
        ]
        criticos = [
            k
            for k, v in blocos.items()
            if isinstance(v, dict) and v.get("status") in {"CRÍTICO", "DIVERGENTE", "ALERTA"}
        ]
        if len(indisponiveis) == len(blocos):
            return {
                "status": "fonte_indisponivel",
                "motivo": "todas as frentes financeiras sem fonte utilizável",
                "data_audit": _agora_br(),
                "blocos": blocos,
            }
        status = "CRÍTICO" if criticos else ("PARCIAL" if indisponiveis else "OK")
        return {
            "status": status,
            "data_audit": _agora_br(),
            "empresa_codigo": self.empresa_codigo,
            "empresa_nome": EMPRESA_DOZE_FILIAL_NOME
            if self.empresa_codigo == EMPRESA_DOZE_FILIAL
            else str(self.empresa_codigo),
            "blocos_criticos": criticos,
            "blocos_fonte_indisponivel": indisponiveis,
            "blocos": blocos,
            "escopo_excluido": [
                "conciliação depósito × extrato bancário",
            ],
        }


__all__ = [
    "FinanceiroAnalyzer",
    "EMPRESA_DOZE_FILIAL",
    "EMPRESA_DOZE_FILIAL_NOME",
    "MovimentoDia",
    "AlertaSaldoNegativo",
    "DiferencaCartao",
    "TituloInadimplente",
    "DespesaProblema",
    "AporteAviso",
]
