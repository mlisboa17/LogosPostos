"""Rotas da Fila Local de Revisão e Aprendizagem para o Cockpit LOGOS.

Segurança:
- Reutiliza autenticação JWT / Cookies e RBAC existentes (`get_current_user`, `require_unit_access`).
- Zero mutações no ERP webPosto (0 POST, 0 PUT, 0 PATCH, 0 DELETE).
- Sem geração de tokens de lançamento.
- Proteção estrita contra concorrência e conflitos de versão (HTTP 409).
- Rejeição categórica do plano 198966 como plano definitivo (HTTP 422).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ....modules.classification_review import (
    CONTA_TEMPORARIA_CLASSIFICACAO,
    ClassificationReviewService,
    EstadoRevisao,
    ItemFilaRevisao,
    RevisaoConcorrenteErro,
    StatusRegraCandidata,
    TransicaoInvalidaErro,
)
from ..dependencies import get_current_user, require_unit_access

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/classification-review",
    tags=["Classification Review"],
)

_service_instance: Optional[ClassificationReviewService] = None


def get_classification_review_service() -> ClassificationReviewService:
    global _service_instance
    if _service_instance is None:
        _service_instance = ClassificationReviewService()
    return _service_instance


# -------------------------------------------------------------
# DTOs
# -------------------------------------------------------------

class ClassificarPayload(BaseModel):
    versao: int = Field(..., description="Versão atual para controle otimista de concorrência")
    plano_definitivo_codigo: int = Field(..., description="Código oficial do plano de contas folha")
    plano_definitivo_descricao: Optional[str] = Field(None, description="Descrição do plano selecionado")
    centro_custo_definitivo_codigo: Optional[int] = Field(None, description="Código do centro de custo")
    justificativa: Optional[str] = Field(None, description="Justificativa da classificação humana")


class BloquearPayload(BaseModel):
    versao: int
    motivo: str
    travas: Optional[List[str]] = Field(default_factory=list)


class CancelarPayload(BaseModel):
    versao: int
    motivo: str


def _serializar_item(item: ItemFilaRevisao) -> dict[str, Any]:
    return {
        "id": item.id,
        "hash_idempotencia": item.hash_idempotencia,
        "empresa_codigo": item.empresa_codigo,
        "conta_financeira_codigo": item.conta_financeira_codigo,
        "data_movimento": item.data_movimento,
        "valor": float(item.valor),
        "valor_formatado": f"R$ {item.valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "descricao": item.descricao,
        "referencia_evidencias": item.referencia_evidencias,
        "sugestao_plano_codigo": item.sugestao_plano_codigo,
        "sugestao_plano_descricao": item.sugestao_plano_descricao,
        "confianca_ia": item.confianca_ia,
        "justificativa_ia": item.justificativa_ia,
        "travas_encontradas": item.travas_encontradas,
        "status": item.status.value,
        "decisao_humana": item.decisao_humana,
        "plano_definitivo_codigo": item.plano_definitivo_codigo,
        "plano_definitivo_descricao": item.plano_definitivo_descricao,
        "centro_custo_definitivo_codigo": item.centro_custo_definitivo_codigo,
        "revisor": item.revisor,
        "revisado_em": item.revisado_em,
        "versao": item.versao,
        "criado_em": item.criado_em,
        "atualizado_em": item.atualizado_em,
    }


# -------------------------------------------------------------
# ENDPOINTS
# -------------------------------------------------------------

@router.get("/pendencias")
async def listar_pendencias(
    status_filtro: Optional[str] = Query(None, alias="status"),
    empresa_codigo: Optional[int] = Query(None),
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Lista pendências da fila com filtros opcionais de status e empresa."""
    if empresa_codigo is not None:
        require_unit_access(current_user, empresa_codigo)

    estado_enum = None
    if status_filtro:
        try:
            estado_enum = EstadoRevisao(status_filtro.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Status '{status_filtro}' inválido. Opções: {[e.value for e in EstadoRevisao]}",
            )

    # Gerentes só veem a sua própria empresa
    if current_user.get("role") == "gerente":
        user_company = current_user.get("company_id")
        if empresa_codigo and empresa_codigo != user_company:
            raise HTTPException(status_code=403, detail="Acesso negado para esta unidade.")
        empresa_codigo = user_company

    itens = service.listar_pendencias(status=estado_enum, empresa_codigo=empresa_codigo)
    return {
        "total": len(itens),
        "itens": [_serializar_item(it) for it in itens],
    }


@router.get("/pendencias/{pendencia_id}")
async def obter_detalhes_pendencia(
    pendencia_id: int,
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Consulta detalhes completos e sanitizados de uma pendência."""
    item = service.obter_pendencia(pendencia_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")

    require_unit_access(current_user, item.empresa_codigo)
    return _serializar_item(item)


@router.get("/pendencias/{pendencia_id}/historico")
async def consultar_historico_pendencia(
    pendencia_id: int,
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Consulta a trilha imutável e append-only de alterações da pendência."""
    item = service.obter_pendencia(pendencia_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")

    require_unit_access(current_user, item.empresa_codigo)
    historico = service.consultar_historico(pendencia_id)
    return {
        "pendencia_id": pendencia_id,
        "total": len(historico),
        "eventos": [
            {
                "id": h.id,
                "acao": h.acao,
                "status_anterior": h.status_anterior,
                "status_novo": h.status_novo,
                "usuario_ou_sistema": h.usuario_ou_sistema,
                "justificativa": h.justificativa,
                "detalhes": h.detalhes_json,
                "timestamp": h.timestamp,
            }
            for h in historico
        ],
    }


@router.post("/pendencias/{pendencia_id}/classificar")
async def classificar_pendencia(
    pendencia_id: int,
    payload: ClassificarPayload,
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Classifica a pendência com uma conta-folha oficial válida.

    Rejeita a conta 198966 e contas pai/inativas/não observadas.
    Invalida qualquer aprovação ou proposta prévia.
    """
    item = service.obter_pendencia(pendencia_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")

    require_unit_access(current_user, item.empresa_codigo)

    revisor = current_user.get("sub") or current_user.get("email") or "cockpit_user"

    try:
        atualizado = service.revisar_e_classificar(
            pendencia_id=pendencia_id,
            versao_esperada=payload.versao,
            plano_definitivo_codigo=payload.plano_definitivo_codigo,
            plano_definitivo_descricao=payload.plano_definitivo_descricao or "",
            revisor=revisor,
            centro_custo_definitivo_codigo=payload.centro_custo_definitivo_codigo,
            justificativa=payload.justificativa,
        )
        return {
            "status": "SUCESSO",
            "mensagem": "Classificação registrada com sucesso na base local.",
            "item": _serializar_item(atualizado),
        }
    except Exception as err:
        err_name = type(err).__name__
        if err_name == "RevisaoConcorrenteErro" or isinstance(err, RevisaoConcorrenteErro):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
        if err_name == "TransicaoInvalidaErro" or isinstance(err, TransicaoInvalidaErro):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        if isinstance(err, ValueError):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))
        raise


@router.post("/pendencias/{pendencia_id}/bloquear")
async def bloquear_pendencia(
    pendencia_id: int,
    payload: BloquearPayload,
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Bloqueia a pendência manualmente justificando travas encontradas."""
    item = service.obter_pendencia(pendencia_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")

    require_unit_access(current_user, item.empresa_codigo)
    autor = current_user.get("sub") or current_user.get("email") or "cockpit_user"

    try:
        atualizado = service.bloquear_pendencia(
            pendencia_id=pendencia_id,
            versao_esperada=payload.versao,
            travas=payload.travas or ["BLOQUEIO_MANUAL_OPERADOR"],
            motivo=payload.motivo,
            autor=autor,
        )
        return {
            "status": "BLOQUEADO",
            "item": _serializar_item(atualizado),
        }
    except Exception as err:
        err_name = type(err).__name__
        if err_name == "RevisaoConcorrenteErro" or isinstance(err, RevisaoConcorrenteErro):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
        if err_name == "TransicaoInvalidaErro" or isinstance(err, TransicaoInvalidaErro):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        raise


@router.post("/pendencias/{pendencia_id}/cancelar")
async def cancelar_pendencia(
    pendencia_id: int,
    payload: CancelarPayload,
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Cancela a pendência (ex: transação descartada ou inexistente)."""
    item = service.obter_pendencia(pendencia_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")

    require_unit_access(current_user, item.empresa_codigo)
    autor = current_user.get("sub") or current_user.get("email") or "cockpit_user"

    try:
        atualizado = service.cancelar_pendencia(
            pendencia_id=pendencia_id,
            versao_esperada=payload.versao,
            motivo=payload.motivo,
            autor=autor,
        )
        return {
            "status": "CANCELADO",
            "item": _serializar_item(atualizado),
        }
    except Exception as err:
        err_name = type(err).__name__
        if err_name == "RevisaoConcorrenteErro" or isinstance(err, RevisaoConcorrenteErro):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
        if err_name == "TransicaoInvalidaErro" or isinstance(err, TransicaoInvalidaErro):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        raise


@router.get("/casos-semelhantes")
async def consultar_casos_semelhantes(
    descricao: str = Query(..., min_length=2),
    empresa_codigo: Optional[int] = Query(None),
    limite: int = Query(5, ge=1, le=20),
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Recupera exemplos humanos confirmados com descrições semelhantes."""
    if empresa_codigo:
        require_unit_access(current_user, empresa_codigo)

    exemplos = service.recuperar_casos_semelhantes(
        descricao=descricao, empresa_codigo=empresa_codigo, limite=limite
    )
    return {
        "busca": descricao,
        "total": len(exemplos),
        "exemplos": [
            {
                "id": ex.id,
                "pendencia_id": ex.pendencia_id,
                "empresa_codigo": ex.empresa_codigo,
                "descricao_padronizada": ex.descricao_padronizada,
                "valor": float(ex.valor) if ex.valor else None,
                "plano_conta_codigo": ex.plano_conta_codigo,
                "plano_conta_descricao": ex.plano_conta_descricao,
                "revisor": ex.revisor,
                "confirmado_em": ex.confirmado_em,
            }
            for ex in exemplos
        ],
    }


@router.get("/metricas")
async def obter_metricas(
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Retorna métricas consolidadas de acurácia da IA e volumetria."""
    m = service.gerar_metricas_ia()
    return {
        "total_avaliados": m.total_avaliados,
        "acertos_ia": m.acertos_ia,
        "taxa_acerto_ia": m.taxa_acerto_ia,
        "total_pendentes": m.total_pendentes,
        "total_bloqueados": m.total_bloqueados,
        "total_classificados": m.total_classificados,
        "total_cancelados": m.total_cancelados,
    }


@router.get("/planos-validos")
async def listar_planos_validos(
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Retorna somente planos ativos, observados, folhas e candidatos válidos.

    Exclui categoricamente contas pai e a conta temporária 198966.
    """
    planos = service.listar_planos_folha_validos()
    return {
        "total": len(planos),
        "planos": planos,
    }


@router.get("/regras-candidatas")
async def listar_regras_candidatas(
    status_regra: Optional[str] = Query(None),
    current_user: Dict = Depends(get_current_user),
    service: ClassificationReviewService = Depends(get_classification_review_service),
):
    """Lista regras candidatas extraídas de correções humanas repetidas.

    Regras com >= 3 casos são indicadas como elegíveis para revisão,
    sem ativar qualquer automação ou lançamento no ERP.
    """
    st_enum = None
    if status_regra:
        try:
            st_enum = StatusRegraCandidata(status_regra.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail="Status de regra inválido.")

    regras = service.listar_regras_candidatas(status=st_enum)
    return {
        "total": len(regras),
        "regras": [
            {
                "id": r.id,
                "padrao_descricao": r.padrao_descricao,
                "empresa_codigo": r.empresa_codigo,
                "plano_conta_sugerido": r.plano_conta_sugerido,
                "total_casos_confirmados": r.total_casos_confirmados,
                "casos_minimos_promocao": r.casos_minimos_promocao,
                "elegivel_para_revisao": r.total_casos_confirmados >= r.casos_minimos_promocao,
                "status_regra": r.status_regra.value,
                "aprovado_por": r.aprovado_por,
                "aprovado_em": r.aprovado_em,
                "automacao_ativa": False,  # Automação/lançamento estritamente inativos
            }
            for r in regras
        ],
    }
