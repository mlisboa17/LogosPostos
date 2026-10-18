"""Segredos no Credential Manager do Windows (via keyring)."""
from __future__ import annotations

import keyring
from keyring.errors import PasswordDeleteError

SERVICO = "LogosMatch"


def salvar(chave: str, valor: str) -> None:
    if not valor:
        return
    keyring.set_password(SERVICO, chave, valor)


def ler(chave: str) -> str | None:
    return keyring.get_password(SERVICO, chave)


def apagar(chave: str) -> None:
    try:
        keyring.delete_password(SERVICO, chave)
    except PasswordDeleteError:
        pass


def tem(chave: str) -> bool:
    return bool(ler(chave))
