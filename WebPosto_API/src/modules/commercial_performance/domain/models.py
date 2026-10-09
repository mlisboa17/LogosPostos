from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.modules.webposto_integration.tempo import DataHoraLocal

Positivo = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Volume = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class Modelo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Posto(Modelo):
    empresa_codigo: int
    nome: str
    chave_env: str


class MetaFrentista(Modelo):
    meta_ticket: Positivo


class MetasPosto(Modelo):
    bronze: Positivo
    prata: Positivo
    ouro: Positivo
    frentistas: dict[int, MetaFrentista] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validar_niveis(self) -> MetasPosto:
        if not self.bronze < self.prata < self.ouro:
            raise ValueError("Metas devem ser crescentes: Bronze < Prata < Ouro.")
        if any(codigo <= 0 for codigo in self.frentistas):
            raise ValueError("Codigo de frentista deve ser positivo.")
        return self


class MetasMes(Modelo):
    mes: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    definido_por: str = Field(min_length=1)
    postos: dict[int, MetasPosto]

    @model_validator(mode="after")
    def validar_postos(self) -> MetasMes:
        if set(self.postos) - {11495, 74014, 5555}:
            raise ValueError("Metas restritas aos tres postos.")
        return self


class Abastecimento(Modelo):
    codigo: int
    empresa_codigo: int
    momento: DataHoraLocal
    litros: Volume
    produto: int
    frentista: int | None
    venda: int | None = None


class Produto(Modelo):
    codigo: int
    nome: str
    aditivado: bool


class Nivel(Modelo):
    meta: Positivo
    percentual: Volume
    faltante: Volume
    media_exigida: Volume
    meta_viva: Volume | None
    meta_viva_frentista: Volume | None
    status_media: str
    status_viva: str | None


class Dia(Modelo):
    dia: date
    litros: Volume
    acumulado: Volume
    atendimentos: int
    abastecimentos: int
    fechado: bool
    niveis: dict[str, Nivel]


class Frentista(Modelo):
    codigo: int | None
    nome: str | None
    litros: Volume
    atendimentos: int
    abastecimentos: int
    ticket: Volume | None
    meta_ticket: Positivo | None
    ganho_bico: Decimal | None
    abaixo_meta: bool | None
    impacto_projetado: Volume | None
    percentual_aditivado: Volume | None
    ranking_ticket: int
    ranking_volume: int


class Mix(Modelo):
    produto: int
    nome: str | None
    litros: Volume
    percentual: Volume
    aditivado: bool | None


class Proveniencia(Modelo):
    executado_em: DataHoraLocal
    execucao_id: str
    versao_regra: str
    fontes: tuple[str, ...]
    metas_cadastradas: bool


class Placar(Modelo):
    posto: int
    mes: str
    dia: date
    parcial: bool
    dias_mes: int
    dias_restantes: int
    frentistas_ativos: int
    acumulado: Volume
    realizado_dia: Volume
    atendimentos: int
    abastecimentos: int
    atendimentos_fallback: int
    ticket: Volume | None
    projecao: Volume
    nivel_projetado: str | None
    percentual_aditivado: Volume | None
    niveis: dict[str, Nivel]
    diario: tuple[Dia, ...]
    frentistas: tuple[Frentista, ...]
    mix: tuple[Mix, ...]
    proveniencia: Proveniencia
