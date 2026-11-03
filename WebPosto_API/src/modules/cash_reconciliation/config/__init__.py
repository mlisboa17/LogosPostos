from __future__ import annotations

import json
import os
from pathlib import Path

from src.core.company_scope import validate_new_process_company_codes

from ..domain.models import ContaCompartilhada, Unidade

ARQUIVO = Path(__file__).with_name("units.json")
DIAS_TOLERANCIA_CONSOLIDACAO_PADRAO = 2


def carregar_unidades(caminho: Path = ARQUIVO) -> dict[int, Unidade]:
    return _carregar_unidades(caminho, novos_processos=True)


def carregar_unidades_historicas(caminho: Path = ARQUIVO) -> dict[int, Unidade]:
    """Le metadados sem aplicar escopo de novos processos; nao autoriza operacoes."""
    return _carregar_unidades(caminho, novos_processos=False)


def _carregar_unidades(caminho: Path, *, novos_processos: bool) -> dict[int, Unidade]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or not isinstance(dados.get("unidades"), list):
        raise ValueError("Configuração inválida de unidades.")
    unidades = dados["unidades"]
    if any(not isinstance(u, dict) or "empresa_codigo" not in u for u in unidades):
        raise ValueError("Configuração inválida de unidade: empresa_codigo ausente.")
    if novos_processos:
        validate_new_process_company_codes(u["empresa_codigo"] for u in unidades)
    modelos = [Unidade.model_validate(u) for u in unidades]
    return {u.empresa_codigo: u for u in modelos}


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
