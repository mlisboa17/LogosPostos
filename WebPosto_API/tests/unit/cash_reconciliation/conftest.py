"""Isola os testes do banco real de pendências (data/pendencias)."""
from __future__ import annotations

import pytest

from src.modules.cash_reconciliation.adapters import pendencias
from src.modules.cash_reconciliation.application import fila_despesas


@pytest.fixture(autouse=True)
def _banco_pendencias_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(pendencias, "DIRETORIO_PENDENCIAS", tmp_path / "pendencias")
    monkeypatch.setattr(pendencias, "BANCO_PENDENCIAS", tmp_path / "pendencias" / "pendencias.sqlite3")

    pasta_comp = tmp_path / "despesas_avulsas" / "comprovantes"
    monkeypatch.setattr(fila_despesas, "obter_pasta_comprovantes", lambda: pasta_comp)
    monkeypatch.setattr(fila_despesas, "obter_caminho_fila", lambda: tmp_path / "despesas_avulsas" / "fila.json")
