"""Evidências de diferença de dinheiro; valores positivos explicam falta."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from .tempo import DataHoraLocal


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
    consolidado: bool = True

    @property
    def sem_explicacao(self) -> Decimal:
        return self.falta - sum((p.valor for p in self.partes), Decimal(0))


class ConferenciaPixCnpj(BaseModel):
    model_config = ConfigDict(frozen=True)
    coberto: bool = False
    clientes: int = 0
    ignorados: int = 0
    casados: int = 0
    pendencias: tuple[str, ...] = ()
    fontes: tuple[str, ...] = ()
    erro: str | None = None


class ConferenciaMais(BaseModel):
    model_config = ConfigDict(frozen=True)
    total: Decimal | None
    webposto: Decimal | None
    fonte: str = "total informado pelo diretor"
    aviso: str | None = None
    informado_em: DataHoraLocal | None = None

    @property
    def diferenca(self):
        return self.total - self.webposto if self.webposto is not None and self.total is not None else None
