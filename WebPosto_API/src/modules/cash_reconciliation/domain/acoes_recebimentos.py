"""Recomendacoes locais; nenhuma acao modifica o ERP."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .recebimentos import ResumoCasados, ResumoForma
from .tempo import DataHoraLocal
from .cartoes import Abastecimento

GrupoRecebimento = Literal[1, 2, 3, 4]


class ResponsavelRecebimento(BaseModel):
    model_config = ConfigDict(frozen=True)
    codigo: int | None
    nome: str | None = None
    identificacao: str
    nota: int = Field(default=0, ge=0, le=100)
    motivos: tuple[str, ...] = ()
    caixa: int | None = None

    @property
    def descricao(self) -> str:
        pessoa = f"{self.nome or 'nome indisponível'} ({self.codigo})" if self.codigo is not None else "frentista não identificado"
        return f"{pessoa} · {self.identificacao} · nota {self.nota} · {', '.join(self.motivos)}"


class PagamentoAcao(BaseModel):
    model_config = ConfigDict(frozen=True)
    adquirente: str
    momento: DataHoraLocal
    valor: Decimal
    forma: str | None = None
    nsu: str | None = None
    terminal: str | None = None
    abastecimento: Abastecimento | None = None
    forma_venda: str | None = None
    responsaveis: tuple[ResponsavelRecebimento, ...] = ()


class AcaoRecebimento(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    unidade: int
    grupo: GrupoRecebimento
    motivo: str
    de: str | None = None
    para: str | None = None
    valor: Decimal
    momento: DataHoraLocal
    adquirente: str
    forma: str
    nsu: str | None = None
    venda: int | None = None
    caixa: int | None = None
    frentista: int | None = None
    nome_frentista: str | None = None
    motivo_frentista: str = "sem operador identificavel nos dados gravados"
    regra: str = "RN-CARTAO-010"
    evidencias: tuple[str, ...] = ()
    troca_de_forma: bool = False
    reincidente: bool = False
    reincidencia_quantidade: int = 0
    reincidencia_total: Decimal = Decimal(0)
    conferencia: Literal["conferido", "nao_encontrado"] | None = None
    observacao: str | None = None
    lancamento: int | None = None
    certeza: str = "Recomendação baseada nas evidências gravadas; validar antes de executar"
    nota_certeza: int = Field(default=0, ge=0, le=100)
    proposta_status: Literal["proposta", "executada pelo gerente", "descartada"] = "proposta"
    referencias_legadas: tuple[str, ...] = ()
    pagamentos: tuple[PagamentoAcao, ...] = ()
    responsaveis: tuple[ResponsavelRecebimento, ...] = ()
    tipo_inclusao: str | None = None
    momento_lancamento: DataHoraLocal | None = None
    valor_lancamento: Decimal | None = None

    @property
    def responsavel(self) -> str:
        if self.responsaveis:
            return "; ".join(r.descricao for r in self.responsaveis)
        if self.frentista is None:
            return f"frentista não identificado — {self.motivo_frentista}"
        return f"{self.nome_frentista or 'nome indisponível'} ({self.frentista})"


class FormaConferencia(BaseModel):
    model_config = ConfigDict(frozen=True)
    adquirente: str
    resumo: ResumoForma


class ConferenciaRecebimentos(BaseModel):
    model_config = ConfigDict(frozen=True)
    unidade: int
    inicio: date
    fim: date
    conferidos: ResumoCasados
    itens: tuple[AcaoRecebimento, ...]
    formas: tuple[FormaConferencia, ...] = ()
    avisos: tuple[str, ...] = ()
    diario: tuple["DiaConferencia", ...] = ()
    totais_adquirentes: tuple["TotalAdquirente", ...] = ()
    diferenca_periodo: Decimal | None = None


class TotalAdquirente(BaseModel):
    model_config = ConfigDict(frozen=True)
    adquirente: str
    situacao: str
    webposto: Decimal | None = None
    recebido: Decimal | None = None
    diferenca: Decimal | None = None


class DiaConferencia(BaseModel):
    model_config = ConfigDict(frozen=True)
    dia: date
    adquirentes: tuple[TotalAdquirente, ...]
    diferenca: Decimal | None = None
    compensacao: Literal["sem compensacao", "compensacao identificada", "compensação a apurar"] = "sem compensacao"
