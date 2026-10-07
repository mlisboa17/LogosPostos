"""Contrato publico dos recebimentos, sem comprovantes individuais dos casados."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .cartoes import CartaoErp, Investigacao, ParProvavel, ResultadoCartoes
from .models import Proveniencia


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ResumoCasados(_Frozen):
    quantidade: int
    total: Decimal


class RecebimentoAdquirente(_Frozen):
    adquirente: str
    situacao: Literal["ok", "pendente", "credencial inválida", "erro"]
    erro: str | None = None
    casados: ResumoCasados | None = None
    a_maior: tuple[Investigacao, ...] = ()
    a_menor: tuple[CartaoErp, ...] = ()
    pares_provaveis: tuple[ParProvavel, ...] = ()
    proveniencia: Proveniencia | None = None

    @classmethod
    def de_resultado(cls, resultado: ResultadoCartoes) -> RecebimentoAdquirente:
        return cls(
            adquirente=resultado.adquirente,
            situacao="ok",
            casados=ResumoCasados(
                quantidade=len(resultado.casados),
                total=sum((c.transacao.valor for c in resultado.casados), Decimal(0)),
            ),
            a_maior=resultado.a_maior,
            a_menor=resultado.a_menor,
            pares_provaveis=resultado.pares_provaveis,
            proveniencia=resultado.proveniencia,
        )


class ResultadoRecebimentos(_Frozen):
    empresa_codigo: int
    dia: date
    adquirentes: tuple[RecebimentoAdquirente, ...]
