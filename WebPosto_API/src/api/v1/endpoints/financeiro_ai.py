"""
Endpoints do Financeiro IA (Fase 5).

GET  /api/v1/financeiro-ai/fluxo-caixa
GET  /api/v1/financeiro-ai/conferencia-cartoes
GET  /api/v1/financeiro-ai/inadimplencia
GET  /api/v1/financeiro-ai/despesas-problematicas
GET  /api/v1/financeiro-ai/relatorio
GET  /api/v1/financeiro-ai/health
POST /api/v1/financeiro-ai/fluxo-caixa/analisar
POST /api/v1/financeiro-ai/conferencia-cartoes/analisar
POST /api/v1/financeiro-ai/inadimplencia/analisar
POST /api/v1/financeiro-ai/despesas-problematicas/analisar
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.v1.endpoints._webposto_factory import make_webposto_client
from src.services.financeiro_ai.financeiro_analyzer import (
    EMPRESA_DOZE_FILIAL,
    FinanceiroAnalyzer,
)

router = APIRouter(prefix="/financeiro-ai", tags=["Financeiro AI"])

_webposto_client: Optional[object] = None
_analyzer: Optional[FinanceiroAnalyzer] = None


def get_analyzer() -> FinanceiroAnalyzer:
    global _analyzer, _webposto_client
    if _analyzer is None:
        try:
            _webposto_client = make_webposto_client()
        except Exception:  # noqa: BLE001 — análise offline ainda funciona
            _webposto_client = None
        _analyzer = FinanceiroAnalyzer(
            _webposto_client,
            empresa_codigo=EMPRESA_DOZE_FILIAL,
        )
    return _analyzer


# ---------- modelos Pydantic ----------


class MovimentoDiaIn(BaseModel):
    dia: str = Field(..., description="Data ISO aaaa-mm-dd")
    entradas: float = 0
    saidas: float = 0


class FluxoCaixaRequest(BaseModel):
    movimentos: list[MovimentoDiaIn]
    saldo_inicial: float = 0
    horizonte_dias: int = Field(default=7, ge=1, le=90)


class VendaCartaoIn(BaseModel):
    dia: str
    bandeira: str
    valor: float


class RecebimentoAdquirenteIn(BaseModel):
    dia: str
    bandeira: str
    valor: float
    adquirente: str = Field(..., description="PagBank, Cielo, Premmia ou Mais Pagamentos")


class AporteIn(BaseModel):
    dia: str
    valor: float
    origem: str = "outra origem"


class ConferenciaCartoesRequest(BaseModel):
    vendas_cartao: list[VendaCartaoIn]
    recebimentos_adquirentes: list[RecebimentoAdquirenteIn]
    aportes: list[AporteIn] = Field(default_factory=list)


class TituloIn(BaseModel):
    titulo_codigo: str = ""
    cliente: str = ""
    valor: float
    vencimento: str
    situacao: str = "ABERTO"
    tipo_cliente: str = ""


class InadimplenciaRequest(BaseModel):
    titulos: list[TituloIn]
    data_referencia: Optional[str] = None


class DespesaIn(BaseModel):
    despesa_id: str = ""
    posto: str = "74014"
    nome_caixa: str = ""
    setor: str = ""
    centro_custo: str = ""
    valor: float
    data: str = ""
    planoContaCodigo: Optional[int] = None
    planoConta: Optional[str] = None
    tem_comprovante: Optional[bool] = None
    frentista: Optional[str] = Field(
        default=None,
        description="Ignorado — caixa nunca é identificado por frentista",
    )


class DespesasRequest(BaseModel):
    despesas: list[DespesaIn]


# ---------- GET (tenta fonte real; senão fonte_indisponivel) ----------


@router.get("/fluxo-caixa", summary="Projeção de fluxo de caixa")
async def get_fluxo_caixa(
    horizonte_dias: int = Query(default=7, ge=1, le=90),
) -> dict[str, Any]:
    analyzer = get_analyzer()
    try:
        return await analyzer.projetar_fluxo_caixa(horizonte_dias=horizonte_dias)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/conferencia-cartoes", summary="Conferência webPosto × adquirentes")
async def get_conferencia_cartoes() -> dict[str, Any]:
    analyzer = get_analyzer()
    try:
        return await analyzer.conferir_cartoes()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/inadimplencia", summary="Títulos vencidos / frota-prazo")
async def get_inadimplencia() -> dict[str, Any]:
    analyzer = get_analyzer()
    try:
        return await analyzer.listar_inadimplencia()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/despesas-problematicas", summary="Despesas sem categoria/comprovante")
async def get_despesas_problematicas() -> dict[str, Any]:
    analyzer = get_analyzer()
    try:
        return await analyzer.listar_despesas_problematicas()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/relatorio", summary="Relatório consolidado Financeiro IA")
async def get_relatorio() -> dict[str, Any]:
    analyzer = get_analyzer()
    try:
        return await analyzer.gerar_relatorio_financeiro()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health", summary="Health check Financeiro IA")
async def health() -> dict[str, Any]:
    analyzer = get_analyzer()
    return {
        "status": "OK",
        "sistema": "Financeiro IA",
        "empresa_padrao": EMPRESA_DOZE_FILIAL,
        "pronto": analyzer is not None,
        "webposto_writes": "0",
    }


# ---------- POST (análise com payload explícito — ideal para testes/diagnóstico) ----------


@router.post("/fluxo-caixa/analisar", summary="Projetar fluxo com movimentos informados")
async def post_fluxo_caixa(body: FluxoCaixaRequest) -> dict[str, Any]:
    analyzer = get_analyzer()
    movimentos = [m.model_dump() for m in body.movimentos]
    return await analyzer.projetar_fluxo_caixa(
        movimentos=movimentos,
        saldo_inicial=Decimal(str(body.saldo_inicial)),
        horizonte_dias=body.horizonte_dias,
    )


@router.post(
    "/conferencia-cartoes/analisar",
    summary="Conferir cartões com vendas e recebimentos informados",
)
async def post_conferencia_cartoes(body: ConferenciaCartoesRequest) -> dict[str, Any]:
    analyzer = get_analyzer()
    return await analyzer.conferir_cartoes(
        vendas_cartao=[v.model_dump() for v in body.vendas_cartao],
        recebimentos_adquirentes=[r.model_dump() for r in body.recebimentos_adquirentes],
        aportes=[a.model_dump() for a in body.aportes],
    )


@router.post("/inadimplencia/analisar", summary="Analisar inadimplência com títulos informados")
async def post_inadimplencia(body: InadimplenciaRequest) -> dict[str, Any]:
    analyzer = get_analyzer()
    titulos = []
    for t in body.titulos:
        row = t.model_dump()
        row["tituloCodigo"] = row.pop("titulo_codigo", "")
        row["nomeCliente"] = row.pop("cliente", "")
        row["dataVencimento"] = row.pop("vencimento", "")
        if t.tipo_cliente:
            row["tipoCliente"] = t.tipo_cliente
        titulos.append(row)
    data_ref = None
    if body.data_referencia:
        from datetime import date as _date

        data_ref = _date.fromisoformat(body.data_referencia[:10])
    return await analyzer.listar_inadimplencia(titulos=titulos, data_referencia=data_ref)


@router.post(
    "/despesas-problematicas/analisar",
    summary="Analisar despesas sem categoria/comprovante",
)
async def post_despesas(body: DespesasRequest) -> dict[str, Any]:
    analyzer = get_analyzer()
    despesas = []
    for d in body.despesas:
        row = d.model_dump()
        row["despesaCodigo"] = row.pop("despesa_id", "")
        # frentista propositalmente descartado da identidade do caixa
        row.pop("frentista", None)
        despesas.append(row)
    return await analyzer.listar_despesas_problematicas(despesas=despesas)


__all__ = ["router"]
