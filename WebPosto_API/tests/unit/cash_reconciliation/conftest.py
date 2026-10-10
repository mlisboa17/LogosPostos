"""Isola os testes do banco real de pendências (data/pendencias)."""
from __future__ import annotations

import pytest

from src.modules.cash_reconciliation.adapters import pendencias


@pytest.fixture(autouse=True)
def _banco_pendencias_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(pendencias, "DIRETORIO_PENDENCIAS", tmp_path / "pendencias")
    monkeypatch.setattr(pendencias, "BANCO_PENDENCIAS", tmp_path / "pendencias" / "pendencias.sqlite3")
