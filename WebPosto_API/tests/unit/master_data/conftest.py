"""Conftest local para testes de master_data.

Garante que o fixture tmp_path aponte para um diretório local do workspace,
evitando dependência de diretórios temporários externos ao repositório ou permissões de symlink.
"""

from __future__ import annotations

import shutil
from pathlib import Path
import pytest

LOCAL_TMP_DIR = Path(__file__).resolve().parent / "_test_tmp"
LOCAL_TMP_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def tmp_path(request):
    """Fixture tmp_path local que provê um diretório temporário isolado por teste."""
    nome_limpo = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in request.node.name)
    caminho = LOCAL_TMP_DIR / nome_limpo
    if caminho.exists():
        shutil.rmtree(caminho, ignore_errors=True)
    caminho.mkdir(parents=True, exist_ok=True)
    yield caminho
    shutil.rmtree(caminho, ignore_errors=True)
