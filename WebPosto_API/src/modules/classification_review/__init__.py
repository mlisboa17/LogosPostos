"""Módulo de Fila Local de Revisão e Aprendizagem (Classification Review)."""

from .adapters.sqlite_classification_review_repository import (
    SqliteClassificationReviewRepository,
)
from .application.classification_review_service import (
    CONTA_TEMPORARIA_CLASSIFICACAO,
    ClassificationReviewService,
)
from .domain.models import (
    DadoEssencialAusenteErro,
    EstadoRevisao,
    ExemploConfirmado,
    HistoricoRevisao,
    ItemFilaRevisao,
    MetricasAcertoIA,
    RegraCandidata,
    RevisaoConcorrenteErro,
    StatusRegraCandidata,
    TransicaoInvalidaErro,
)

__all__ = [
    "CONTA_TEMPORARIA_CLASSIFICACAO",
    "ClassificationReviewService",
    "DadoEssencialAusenteErro",
    "EstadoRevisao",
    "ExemploConfirmado",
    "HistoricoRevisao",
    "ItemFilaRevisao",
    "MetricasAcertoIA",
    "RegraCandidata",
    "RevisaoConcorrenteErro",
    "SqliteClassificationReviewRepository",
    "StatusRegraCandidata",
    "TransicaoInvalidaErro",
]
