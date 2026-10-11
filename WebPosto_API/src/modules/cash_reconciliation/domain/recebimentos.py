"""Contrato publico dos recebimentos, sem comprovantes individuais dos casados."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .cartoes import (
    AlertaCartao,
    Casamento,
    CartaoErp,
    GrupoProvavel,
    Investigacao,
    ParProvavel,
    ResultadoCartoes,
    TransacaoAdquirente,
)
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
    grupos_provaveis: tuple[GrupoProvavel, ...] = ()
    casados_valor_divergente: ResumoCasados = ResumoCasados(quantidade=0, total=Decimal(0))
    divergencias_valor: tuple[Casamento, ...] = ()
    cancelados: ResumoCasados = ResumoCasados(quantidade=0, total=Decimal(0))
    transacoes_canceladas: tuple[TransacaoAdquirente, ...] = ()
    alertas: tuple[AlertaCartao, ...] = ()
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
            grupos_provaveis=resultado.grupos_provaveis,
            divergencias_valor=tuple(c for c in resultado.casados if c.valor_divergente),
            casados_valor_divergente=ResumoCasados(
                quantidade=sum(c.valor_divergente for c in resultado.casados),
                total=sum(
                    (c.diferenca for c in resultado.casados if c.valor_divergente), Decimal(0)
                ),
            ),
            cancelados=ResumoCasados(
                quantidade=len(resultado.cancelados),
                total=sum((c.valor for c in resultado.cancelados), Decimal(0)),
            ),
            transacoes_canceladas=resultado.cancelados,
            alertas=resultado.alertas,
            proveniencia=resultado.proveniencia,
        )


class ResultadoRecebimentos(_Frozen):
    empresa_codigo: int
    dia: date
    adquirentes: tuple[RecebimentoAdquirente, ...]
