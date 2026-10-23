"""Modelos de domínio para a Fila Local de Revisão e Aprendizagem."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class EstadoRevisao(str, Enum):
    """Ciclo de vida auditável das pendências de classificação."""

    PENDENTE_REVISAO = "PENDENTE_REVISAO"
    CLASSIFICADO = "CLASSIFICADO"
    BLOQUEADO = "BLOQUEADO"
    CANCELADO = "CANCELADO"


class StatusRegraCandidata(str, Enum):
    """Status da regra extraída para aprovação progressiva."""

    CANDIDATA = "CANDIDATA"
    PROMOVIDA = "PROMOVIDA"
    REJEITADA = "REJEITADA"


class RevisaoConcorrenteErro(RuntimeError):
    """Lançado quando uma revisão tenta alterar uma pendência já modificada por outro processo."""

    pass


class TransicaoInvalidaErro(RuntimeError):
    """Lançado quando uma transição de status não é permitida pelo ciclo de vida."""

    pass


class DadoEssencialAusenteErro(ValueError):
    """Lançado quando dados essenciais da movimentação financeira estão ausentes."""

    pass


# Transições válidas do ciclo de vida
TRANSICOES_VALIDAS: dict[EstadoRevisao, set[EstadoRevisao]] = {
    EstadoRevisao.PENDENTE_REVISAO: {
        EstadoRevisao.CLASSIFICADO,
        EstadoRevisao.BLOQUEADO,
        EstadoRevisao.CANCELADO,
    },
    EstadoRevisao.BLOQUEADO: {
        EstadoRevisao.PENDENTE_REVISAO,  # Desbloqueio manual justificado
        EstadoRevisao.CANCELADO,
    },
    EstadoRevisao.CLASSIFICADO: set(),  # Estado terminal
    EstadoRevisao.CANCELADO: set(),  # Estado terminal
}


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def sanitizar_evidencia(texto: Optional[str]) -> str:
    """Remove credenciais, chaves de API, tokens e senhas para segurança estrita."""
    if not texto:
        return ""
    sanitizado = re.sub(r"(?i)(token|bearer|api_key|senha|password|secret)[\s:=]+['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?", r"\1: [REDACTED]", texto)
    sanitizado = re.sub(r"\b(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})\b", r"****-****-****-\4", sanitizado)
    return sanitizado


def calcular_hash_idempotencia(
    empresa_codigo: int,
    conta_financeira_codigo: int,
    data_movimento: str,
    valor: Decimal | str,
    descricao: str,
) -> str:
    """Gera hash unívoco SHA-256 para idempotência estrita."""
    desc_norm = " ".join(descricao.strip().upper().split())
    valor_norm = f"{Decimal(str(valor)):.2f}"
    payload = f"{empresa_codigo}|{conta_financeira_codigo}|{data_movimento.strip()}|{valor_norm}|{desc_norm}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ItemFilaRevisao:
    """Registro da fila de revisão de classificação."""

    id: Optional[int]
    hash_idempotencia: str
    empresa_codigo: int
    conta_financeira_codigo: int
    data_movimento: str
    valor: Decimal
    descricao: str
    referencia_evidencias: Optional[str] = None
    sugestao_plano_codigo: Optional[int] = None
    sugestao_plano_descricao: Optional[str] = None
    confianca_ia: float = 0.0
    justificativa_ia: Optional[str] = None
    travas_encontradas: list[str] = field(default_factory=list)
    status: EstadoRevisao = EstadoRevisao.PENDENTE_REVISAO
    decisao_humana: Optional[str] = None
    plano_definitivo_codigo: Optional[int] = None
    plano_definitivo_descricao: Optional[str] = None
    centro_custo_definitivo_codigo: Optional[int] = None
    revisor: Optional[str] = None
    revisado_em: Optional[str] = None
    versao: int = 1
    criado_em: str = field(default_factory=lambda: agora_utc().isoformat())
    atualizado_em: str = field(default_factory=lambda: agora_utc().isoformat())


@dataclass
class HistoricoRevisao:
    """Entrada append-only na trilha de auditoria."""

    id: Optional[int]
    pendencia_id: int
    acao: str
    status_anterior: Optional[str]
    status_novo: str
    usuario_ou_sistema: str
    justificativa: Optional[str]
    detalhes_json: Optional[str]
    timestamp: str = field(default_factory=lambda: agora_utc().isoformat())


@dataclass
class ExemploConfirmado:
    """Exemplo consolidado por revisão humana para aprendizado."""

    id: Optional[int]
    pendencia_id: Optional[int]
    empresa_codigo: int
    descricao_padronizada: str
    valor: Optional[Decimal]
    plano_conta_codigo: int
    plano_conta_descricao: str
    revisor: str
    confirmado_em: str
    hash_exemplo: str


@dataclass
class RegraCandidata:
    """Regra extraída que exige múltiplos casos e aprovação antes de promoção."""

    id: Optional[int]
    padrao_descricao: str
    empresa_codigo: Optional[int]
    plano_conta_sugerido: int
    total_casos_confirmados: int = 1
    casos_minimos_promocao: int = 3
    status_regra: StatusRegraCandidata = StatusRegraCandidata.CANDIDATA
    aprovado_por: Optional[str] = None
    aprovado_em: Optional[str] = None
    criado_em: str = field(default_factory=lambda: agora_utc().isoformat())
    atualizado_em: str = field(default_factory=lambda: agora_utc().isoformat())


@dataclass
class MetricasAcertoIA:
    """Métricas de avaliação e acurácia das sugestões de IA."""

    total_avaliados: int
    acertos_ia: int
    taxa_acerto_ia: float
    total_pendentes: int
    total_bloqueados: int
    total_classificados: int
    total_cancelados: int
