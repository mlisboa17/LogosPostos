"""Adaptador offline do contrato oficial de empresas WebPosto."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..domain.models import MasterEmpresa


class WebPostoEmpresaSource(BaseModel):
    """Registro de origem com aliases e tipos preservados como recebidos."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True, strict=True)

    empresa_codigo: int = Field(alias="empresaCodigo")
    codigo: Optional[int] = None
    empresa_codigo_externo: Optional[Any] = Field(default=None, alias="empresaCodigoExterno")
    cnpj: Optional[str] = None
    razao: Optional[str] = None
    fantasia: Optional[str] = None
    endereco: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    tipo_imposto: Optional[str] = Field(default=None, alias="tipoImposto")


class WebPostoEmpresasResponse(BaseModel):
    """Envelope de paginação observado na resposta oficial sanitizada."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True, strict=True)

    resultados: list[WebPostoEmpresaSource]
    ultimo_codigo: Optional[int] = Field(default=None, alias="ultimoCodigo")


@dataclass(frozen=True)
class EmpresaWebPostoNormalizada:
    source: WebPostoEmpresaSource
    master: MasterEmpresa


def parse_empresas_response(payload: Any) -> WebPostoEmpresasResponse:
    """Valida o envelope sem descartar campos extras da origem."""
    if not isinstance(payload, dict):
        raise ValueError("Resposta de empresas deve ser um objeto JSON.")
    return WebPostoEmpresasResponse.model_validate(payload)


def _texto_identidade_normalizado(value: str) -> str:
    return " ".join(value.split()).casefold()


def _cnpj_normalizado(value: str) -> str:
    return re.sub(r"\D", "", value)


def _valor_de_origem(value: Optional[str]) -> Optional[str]:
    return value if value is not None and value.strip() else None


def normalizar_empresa(
    source: WebPostoEmpresaSource,
    existente: MasterEmpresa,
) -> EmpresaWebPostoNormalizada:
    """Mapeia somente identidade presente e não conflitante para o modelo atual."""
    valores_origem = {
        "razao_social": _valor_de_origem(source.razao),
        "nome_fantasia": _valor_de_origem(source.fantasia),
        "cnpj": _valor_de_origem(source.cnpj),
    }

    comparadores = {
        "razao_social": _texto_identidade_normalizado,
        "nome_fantasia": _texto_identidade_normalizado,
        "cnpj": _cnpj_normalizado,
    }
    for campo, valor_origem in valores_origem.items():
        if valor_origem is None:
            continue
        valor_existente = getattr(existente, campo)
        if comparadores[campo](valor_origem) != comparadores[campo](valor_existente):
            raise ValueError(
                f"Identidade da empresa {source.empresa_codigo} diverge no campo {campo}."
            )
    updates = {campo: valor for campo, valor in valores_origem.items() if valor is not None}
    houve_alteracao = (
        any(getattr(existente, campo) != valor for campo, valor in updates.items())
        or existente.origem_dado != "webposto_integracao_empresas"
    )
    if houve_alteracao:
        updates["origem_dado"] = "webposto_integracao_empresas"
        updates["atualizado_em"] = datetime.now(timezone.utc)
    master = existente.model_copy(update=updates)

    return EmpresaWebPostoNormalizada(source=source, master=master)
