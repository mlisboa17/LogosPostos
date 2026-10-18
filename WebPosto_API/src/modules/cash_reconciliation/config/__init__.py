from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from ..domain.models import ContaCompartilhada, Unidade

ARQUIVO = Path(__file__).with_name("units.json")
DIAS_TOLERANCIA_CONSOLIDACAO_PADRAO = 2


_provedor_unidades: Callable[[], dict[int, Unidade]] | None = None


def definir_provedor_unidades(f: Callable[[], dict[int, Unidade]] | None) -> None:
    global _provedor_unidades
    _provedor_unidades = f


def carregar_unidades(caminho: Path = ARQUIVO) -> dict[int, Unidade]:
    if _provedor_unidades is not None and caminho == ARQUIVO:
        return _provedor_unidades()
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {u["empresa_codigo"]: Unidade.model_validate(u) for u in dados["unidades"]}


def carregar_contas_compartilhadas(caminho: Path = ARQUIVO) -> dict[str, ContaCompartilhada]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {
        c["nome"]: ContaCompartilhada.model_validate(c)
        for c in dados.get("contas_compartilhadas", [])
    }


def dias_tolerancia_consolidacao() -> int:
    valor = os.getenv("CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO")
    if valor is None:
        return DIAS_TOLERANCIA_CONSOLIDACAO_PADRAO
    try:
        dias = int(valor)
    except ValueError:
        raise ValueError(
            "CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO deve ser um inteiro não negativo."
        ) from None
    if dias < 0:
        raise ValueError(
            "CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO deve ser um inteiro não negativo."
        )
    return dias


def prazos_pendencia_dias() -> dict[str, int]:
    prazos = json.loads(ARQUIVO.read_text(encoding="utf-8")).get("prazo_pendencia_dias")
    if not isinstance(prazos, dict) or any(
        isinstance(prazos.get(severidade), bool)
        or not isinstance(prazos.get(severidade), int)
        or prazos[severidade] < 0
        for severidade in ("vermelho", "laranja")
    ):
        raise ValueError("Configuração inválida para os prazos das pendências.")
    return {"vermelho": prazos["vermelho"], "laranja": prazos["laranja"]}
