"""Evidências de diferença de dinheiro; valores positivos explicam falta."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ParteFalta(BaseModel):
    model_config = ConfigDict(frozen=True)
    referencia: str
    caixa_codigo: int
    descricao: str
    valor: Decimal
    fonte: str
    correcao: str
    lancavel: bool = False


class ExplicacaoCaixa(BaseModel):
    model_config = ConfigDict(frozen=True)
    caixa_codigo: int
    caixa: str
    falta: Decimal
    partes: tuple[ParteFalta, ...]

    @property
    def sem_explicacao(self) -> Decimal:
        return self.falta - sum((p.valor for p in self.partes), Decimal(0))
