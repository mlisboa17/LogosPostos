from __future__ import annotations

import json
from pathlib import Path

from ..domain.models import ContaCompartilhada, Unidade

ARQUIVO = Path(__file__).with_name("units.json")


def carregar_unidades(caminho: Path = ARQUIVO) -> dict[int, Unidade]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {u["empresa_codigo"]: Unidade.model_validate(u) for u in dados["unidades"]}


def carregar_contas_compartilhadas(caminho: Path = ARQUIVO) -> dict[str, ContaCompartilhada]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {c["nome"]: ContaCompartilhada.model_validate(c) for c in dados.get("contas_compartilhadas", [])}
