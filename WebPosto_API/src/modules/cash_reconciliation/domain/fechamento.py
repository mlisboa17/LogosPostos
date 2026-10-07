"""Auditoria do fechamento de caixa (sem banco) — dados exclusivamente do webPosto."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from .models import Proveniencia, Sangria


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


# prefixo do campo em CAIXAS_APRESENTADO -> rotulo exibido
MODALIDADES: dict[str, str] = {
    "dinheiro": "Dinheiro",
    "cartao": "Cartão",
    "transfBanc": "PIX / Transferência",
    "notaPrazo": "Frotistas / Prazo",
    "cheque": "Cheque",
    "chequePre": "Cheque pré",
    "cartaFrete": "Carta-frete",
    "valeCliente": "Vale cliente",
    "valeFun": "Vale funcionário",
    "prePag": "Pré-pago",
    "despesa": "Despesas",
    "emprestimo": "Empréstimo",
    "chequePagar": "Cheque a pagar",
    "transfDeb": "Transferência débito",
    "fundoCxDeb": "Fundo de caixa",
}


class Severidade(str, Enum):
    VERMELHO = "vermelho"
    LARANJA = "laranja"


class Caixa(_Frozen):
    codigo: int
    empresa_codigo: int
    data: date
    turno: str
    pdv_codigo: int
    centro_custo: int | None = None  # distingue pista x conveniencia quando ha 2 caixas no dia
    funcionario_codigo: int
    abertura: datetime
    fechamento: datetime | None
    fechado: bool
    consolidado: bool
    bloqueado: bool


class LinhaModalidade(_Frozen):
    modalidade: str
    rotulo: str
    apresentado: Decimal
    apurado: Decimal
    diferenca: Decimal  # apresentado - apurado (negativo = falta)


class Alerta(_Frozen):
    codigo: str
    severidade: Severidade
    mensagem: str
    valor: Decimal | None = None
    referencia: int | None = None  # caixaCodigo ou sangriaCodigo


class AuditoriaCaixa(_Frozen):
    caixa: Caixa
    modalidades: tuple[LinhaModalidade, ...]
    sangrias: tuple[Sangria, ...]
    alertas: tuple[Alerta, ...]

    @property
    def quebra(self) -> Decimal:
        return sum((m.diferenca for m in self.modalidades), Decimal(0))

    @property
    def severidade(self) -> Severidade | None:
        sev = {a.severidade for a in self.alertas}
        return Severidade.VERMELHO if Severidade.VERMELHO in sev else Severidade.LARANJA if sev else None


class ResultadoAuditoria(_Frozen):
    empresa_codigo: int
    inicio: date
    fim: date
    caixas: tuple[AuditoriaCaixa, ...]
    proveniencia: Proveniencia

    @property
    def quebra_total(self) -> Decimal:
        return sum((c.quebra for c in self.caixas), Decimal(0))
