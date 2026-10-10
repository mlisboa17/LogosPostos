"""Contratos da fila de pendências da auditoria."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


StatusPendencia = Literal["aberta", "justificada", "aprovada", "recusada", "substituida"]
SeveridadePendencia = Literal["vermelho", "laranja"]


class NovaPendencia(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    unidade: int
    dia: date
    tipo: str
    severidade: SeveridadePendencia
    valor: Decimal | None = None
    referencia: str
    mensagem: str
    identidade: str | None = None


class EventoPendencia(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    acao: str
    status_anterior: StatusPendencia | None
    status_novo: StatusPendencia
    usuario: str
    justificativa: str | None
    registrado_em: datetime


class Pendencia(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    unidade: int
    dia: date
    tipo: str
    severidade: SeveridadePendencia
    valor: Decimal | None
    referencia: str
    mensagem: str
    status: StatusPendencia
    responsavel: str | None
    criada_em: datetime
    historico: tuple[EventoPendencia, ...] = ()
