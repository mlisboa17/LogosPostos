"""Gera um hash PBKDF2-SHA256 para cadastro de usuário."""
from __future__ import annotations

import getpass

from .passwords import hash_password


def main() -> int:
    senha = getpass.getpass("Senha: ")
    confirmacao = getpass.getpass("Confirme a senha: ")
    if not senha or senha != confirmacao:
        raise SystemExit("As senhas estão vazias ou não conferem.")
    print(hash_password(senha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
