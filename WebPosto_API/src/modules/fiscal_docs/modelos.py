"""Modelos de documento fiscal (imutáveis)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

FUSO = ZoneInfo("America/Recife")

TipoDoc = Literal["nfe", "nfse", "cte"]
Situacao = Literal["autorizada", "cancelada", "so_resumo"]


class XmlInvalido(ValueError):
    """XML ilegível ou de leiaute não suportado."""


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True)


class Item(_Base):
    n_item: int
    codigo: str
    descricao: str
    ncm: str | None = None
    cfop: str | None = None
    cprod_anp: str | None = None
    quantidade: Decimal
    unidade: str
    valor_unitario: Decimal
    valor_total: Decimal
    icms_mono: Decimal | None = None


class Transporte(_Base):
    mod_frete: str
    mod_frete_texto: str
    transportadora_cnpj: str | None = None
    transportadora_nome: str | None = None
    placa: str | None = None
    uf_placa: str | None = None
    volumes: Decimal | None = None
    peso_bruto: Decimal | None = None


class Impostos(_Base):
    icms: Decimal = Decimal("0")
    icms_st: Decimal = Decimal("0")
    ipi: Decimal = Decimal("0")
    iss: Decimal = Decimal("0")
    retencoes: Decimal = Decimal("0")
    frete: Decimal = Decimal("0")


class DocumentoFiscal(_Base):
    tipo: TipoDoc
    chave: str
    numero: str
    serie: str | None
    emissao_em: datetime
    competencia: str
    emitente_cnpj: str
    emitente_nome: str
    destinatario_cnpj: str | None
    valor_total: Decimal
    impostos: Impostos
    situacao: Situacao
    combustivel: bool
    itens: tuple[Item, ...] = ()
    transporte: Transporte | None = None
    descricao_servico: str | None = None


def competencia_de(dt: datetime) -> str:
    """Mês (AAAA-MM) da data no fuso de Recife."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=FUSO)
    return dt.astimezone(FUSO).strftime("%Y-%m")
