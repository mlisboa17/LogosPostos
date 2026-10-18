import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError


class _KeyringMemoria(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self._d = {}

    def set_password(self, servico, usuario, senha):
        self._d[(servico, usuario)] = senha

    def get_password(self, servico, usuario):
        return self._d.get((servico, usuario))

    def delete_password(self, servico, usuario):
        if (servico, usuario) not in self._d:
            raise PasswordDeleteError("inexistente")
        del self._d[(servico, usuario)]


@pytest.fixture
def keyring_falso():
    anterior = keyring.get_keyring()
    falso = _KeyringMemoria()
    keyring.set_keyring(falso)
    yield falso
    keyring.set_keyring(anterior)
