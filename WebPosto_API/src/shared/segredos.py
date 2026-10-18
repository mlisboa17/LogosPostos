"""Resolução injetável de segredos: padrão é o ambiente; o app instalável injeta o cofre."""
from __future__ import annotations

import os
from typing import Callable

_resolvedor: Callable[[str], str | None] | None = None


def definir_resolvedor(f: Callable[[str], str | None] | None) -> None:
    global _resolvedor
    _resolvedor = f


def obter_segredo(nome: str) -> str:
    valor = _resolvedor(nome) if _resolvedor is not None else os.getenv(nome)
    return (valor or "").strip()
