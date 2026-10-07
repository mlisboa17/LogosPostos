"""Modelos do contexto Cash & Reconciliation (CASH-ARCH-01, ver ADR-002).

Valores monetarios em Decimal. Todo resultado carrega Proveniencia (diretiva 6.2).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class TipoDestino(str, Enum):
    DEPOSITO_DIRETO = "deposito_direto"  # sangria vai direto ao banco (caixa 24h / cofre inteligente)
    COFRE = "cofre"                      # sangria fica no cofre e e depositada depois


class Canal(str, Enum):
    BCO24H = "bco24h"      # terminal Banco24Horas / cofre inteligente
    ATM_AGENCIA = "atm"    # caixa eletronico da agencia
    OUTRO = "outro"


class Sangria(_Frozen):
    codigo: int
    empresa_codigo: int
    caixa_codigo: int
    conta_codigo: int | None
    funcionario_codigo: int
    valor: Decimal
    momento: datetime
    alterada: bool = False


class DepositoBancario(_Frozen):
    fitid: str
    banco: str
    conta: str
    valor: Decimal
    data: date
    momento: datetime | None  # None quando o extrato nao informa hora
    canal: Canal
    terminal: str | None = None

    @property
    def referencia(self) -> datetime:
        return self.momento or datetime.combine(self.data, datetime.min.time())


class Destino(_Frozen):
    conta_codigo: int | None              # None = sangrias lancadas sem conta no webPosto
    tipo: TipoDestino
    banco: str
    conta_sufixo: str = ""                 # opcional; numero de conta nao vai para o repositorio
    terminais: tuple[str, ...] = ()        # filtro de terminal para deposito direto (vazio = qualquer)
    prazo_dias: int = 1


class SituacaoAdquirente(str, Enum):
    ATIVO = "ativo"
    PENDENTE = "pendente"
    CREDENCIAL_INVALIDA = "credencial inválida"


class AdquirenteConfigurada(_Frozen):
    nome: Literal["PAGBANK", "MAIS_PAGAMENTOS", "REDE", "CIELO", "PREMMIA"]
    situacao: SituacaoAdquirente
    modalidades: tuple[Literal["cartoes", "pix", "premmia"], ...]
    setores: tuple[str, ...] = ()


class Unidade(_Frozen):
    empresa_codigo: int
    nome: str
    chave_env: str                         # NOME da variavel de ambiente com a CHAVE (nunca o valor)
    destinos: tuple[Destino, ...]
    destino_padrao: int | None = None      # conta assumida quando a sangria vem sem contaCodigo
    adquirentes: tuple[AdquirenteConfigurada, ...] = ()

    def destino(self, conta_codigo: int | None) -> Destino | None:
        return next((d for d in self.destinos if d.conta_codigo == conta_codigo), None)

    def conta_efetiva(self, s: "Sangria") -> int | None:
        return s.conta_codigo if s.conta_codigo is not None else self.destino_padrao


class ContaCompartilhada(_Frozen):
    """Conta bancaria que recebe especie de mais de uma unidade."""
    nome: str
    banco: str
    membros: tuple[int, ...]  # empresaCodigo das unidades que depositam nela


class Casamento(_Frozen):
    deposito: DepositoBancario
    sangrias: tuple[Sangria, ...]
    regra: str

    @property
    def diferenca(self) -> Decimal:
        return sum((s.valor for s in self.sangrias), Decimal(0)) - self.deposito.valor


class FluxoDireto(_Frozen):
    destino: Destino
    casamentos: tuple[Casamento, ...]
    sangrias_sem_deposito: tuple[Sangria, ...]
    depositos_sem_sangria: tuple[DepositoBancario, ...]


class DiaCofre(_Frozen):
    dia: date
    entradas: Decimal
    depositos: Decimal
    saldo: Decimal


class FluxoCofre(_Frozen):
    destino: Destino
    dias: tuple[DiaCofre, ...]

    @property
    def saldo_final(self) -> Decimal:
        return self.dias[-1].saldo if self.dias else Decimal(0)


class Proveniencia(_Frozen):
    execucao_id: str
    executado_em: datetime
    versao_regra: str
    fonte_sangrias: str
    extratos: tuple[str, ...]  # "<arquivo>:<sha256>"
    outras_fontes: tuple[str, ...] = ()


class ResultadoConciliacao(_Frozen):
    empresa_codigo: int
    inicio: date
    fim: date
    fluxos_diretos: tuple[FluxoDireto, ...]
    fluxos_cofre: tuple[FluxoCofre, ...]
    sangrias_sem_destino: tuple[Sangria, ...] = Field(default=())
    sangrias_alteradas: tuple[Sangria, ...] = Field(default=())
    proveniencia: Proveniencia


class ResultadoContaCompartilhada(_Frozen):
    conta: ContaCompartilhada
    inicio: date
    fim: date
    dias: tuple[DiaCofre, ...]
    entradas_por_unidade: tuple[tuple[int, Decimal], ...]
    sangrias_sem_destino: tuple[Sangria, ...] = Field(default=())
    sangrias_alteradas: tuple[Sangria, ...] = Field(default=())
    proveniencia: Proveniencia

    @property
    def saldo_final(self) -> Decimal:
        return self.dias[-1].saldo if self.dias else Decimal(0)
