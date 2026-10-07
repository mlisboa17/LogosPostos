"""Registro diario persistido com escopo de unidade e proveniencia."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator

from .fechamento import ResultadoAuditoria
from .models import Proveniencia
from .recebimentos import ResultadoRecebimentos


class ResultadoDiario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    empresa_codigo: int
    dia: date
    fechamento: ResultadoAuditoria | None
    erro_fechamento: str | None = None
    recebimentos: ResultadoRecebimentos
    proveniencia: Proveniencia
    versoes_regras: tuple[str, ...]

    @model_validator(mode="after")
    def validar_escopo(self) -> ResultadoDiario:
        if (self.fechamento is None) == (self.erro_fechamento is None):
            raise ValueError("Fechamento deve conter resultado ou erro, exclusivamente.")
        if self.recebimentos.empresa_codigo != self.empresa_codigo or self.recebimentos.dia != self.dia:
            raise ValueError("Recebimentos fora do escopo do registro.")
        for item in self.recebimentos.adquirentes:
            cartoes = (*item.a_menor, *(par.cartao for par in item.pares_provaveis))
            investigacoes = (*item.a_maior, *(par.investigacao for par in item.pares_provaveis))
            if any(c.empresa_codigo != self.empresa_codigo for c in cartoes):
                raise ValueError("Cartao fora do escopo do registro.")
            if any(c.abastecimento.empresa_codigo != self.empresa_codigo
                   for inv in investigacoes for c in inv.candidatos):
                raise ValueError("Candidato fora do escopo do registro.")
        if self.fechamento is not None:
            if (self.fechamento.empresa_codigo != self.empresa_codigo
                    or self.fechamento.inicio != self.dia or self.fechamento.fim != self.dia):
                raise ValueError("Fechamento fora do escopo do registro.")
            if any(c.caixa.empresa_codigo != self.empresa_codigo or c.caixa.data != self.dia
                   for c in self.fechamento.caixas):
                raise ValueError("Caixa fora do escopo do registro.")
        return self
