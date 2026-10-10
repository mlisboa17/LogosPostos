from __future__ import annotations

import json
import os
from pathlib import Path

from ..domain.models import ContaCompartilhada, Unidade

ARQUIVO = Path(__file__).with_name("units.json")
DIAS_TOLERANCIA_CONSOLIDACAO_PADRAO = 2


def carregar_unidades(caminho: Path = ARQUIVO) -> dict[int, Unidade]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {u["empresa_codigo"]: Unidade.model_validate(u) for u in dados["unidades"]}


def carregar_contas_compartilhadas(caminho: Path = ARQUIVO) -> dict[str, ContaCompartilhada]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {c["nome"]: ContaCompartilhada.model_validate(c) for c in dados.get("contas_compartilhadas", [])}


def dias_tolerancia_consolidacao() -> int:
    valor = os.getenv("CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO")
    if valor is None:
        return DIAS_TOLERANCIA_CONSOLIDACAO_PADRAO
    try:
        dias = int(valor)
    except ValueError:
        raise ValueError("CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO deve ser um inteiro não negativo.") from None
    if dias < 0:
        raise ValueError("CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO deve ser um inteiro não negativo.")
    return dias
