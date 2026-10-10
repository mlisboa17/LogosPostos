"""Contrato da recorrência mensal de conferências por funcionário."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FuncionarioReincidencia(BaseModel):
    model_config = ConfigDict(frozen=True)

    funcionario_codigo: int
    nome: str | None
    quebras: int
    faltas_total: Decimal
    sangrias_alteradas: int
    recebimentos_a_maior_atribuidos: int
    valor_recebimentos_a_maior_atribuidos: Decimal
    recebimentos_a_maior_sugeridos: int
    valor_recebimentos_a_maior_sugeridos: Decimal


class ResultadoReincidencia(BaseModel):
    model_config = ConfigDict(frozen=True)

    empresa_codigo: int
    mes: str
    dias_com_dados: tuple[str, ...]
    dias_sem_dados: tuple[str, ...]
    dias_sem_fechamento: tuple[str, ...]
    dias_sem_recebimentos: tuple[str, ...]
    funcionarios: tuple[FuncionarioReincidencia, ...]
