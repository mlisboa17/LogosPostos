"""Isola os testes do banco real de pendências (data/pendencias)."""
from __future__ import annotations

from pathlib import Path
import pytest

from src.modules.cash_reconciliation.adapters import pendencias
from src.modules.cash_reconciliation.application import fila_despesas
from src.modules.cash_reconciliation.adapters import webposto_escrita_cartao


@pytest.fixture(autouse=True)
def _banco_pendencias_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(pendencias, "DIRETORIO_PENDENCIAS", tmp_path / "pendencias")
    monkeypatch.setattr(pendencias, "BANCO_PENDENCIAS", tmp_path / "pendencias" / "pendencias.sqlite3")

    pasta_comp = tmp_path / "despesas_avulsas" / "comprovantes"
    monkeypatch.setattr(fila_despesas, "obter_pasta_comprovantes", lambda: pasta_comp)
    monkeypatch.setattr(fila_despesas, "obter_caminho_fila", lambda: tmp_path / "despesas_avulsas" / "fila.json")


@pytest.fixture(autouse=True)
def _piloto_isolado(tmp_path_factory, monkeypatch):
    raiz = tmp_path_factory.mktemp("piloto")
    env = raiz / ".env"
    env.write_text("WEBPOSTO_WRITES=0\nLOGOS_ERP_ESCRITA=0\nLOGOS_CARTAO_AUTOMATICO=0\n", encoding="utf-8")
    monkeypatch.setattr(webposto_escrita_cartao, "resolver_caminho_env", lambda caminho=None: Path(caminho) if caminho else env)
    monkeypatch.setattr(webposto_escrita_cartao, "DIRETORIO_AUDITORIA_PADRAO", raiz / "auditoria")
