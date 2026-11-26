"""Testes HTTP do Comprador IA (TestClient + auth)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints import buyer_ai
from src.interfaces.http.dependencies import get_current_user


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(buyer_ai.router, prefix="/api/v1")
    yield application
    application.dependency_overrides.clear()


def _auth(app) -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "tester",
        "role": "diretor",
        "company_id": None,
    }


def test_ruptures_risk_fonte_indisponivel_retorna_200(app, monkeypatch):
    class _Analyzer:
        async def find_rupture_risk(self):
            return {
                "status": "fonte_indisponivel",
                "motivo": "ESTOQUES retornou nulo",
            }

    monkeypatch.setattr(buyer_ai, "get_analyzer", lambda: _Analyzer())
    _auth(app)

    with TestClient(app) as client:
        resp = client.get("/api/v1/buyer-ai/ruptures-risk")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "fonte_indisponivel"
    assert "nulo" in body["motivo"]


def test_ruptures_risk_lista_filtra_dias_ahead(app, monkeypatch):
    class _Analyzer:
        async def find_rupture_risk(self):
            return [
                {"produto_id": "A", "dias_de_estoque": 3, "descricao": "perto"},
                {"produto_id": "B", "dias_de_estoque": 20, "descricao": "longe"},
            ]

    monkeypatch.setattr(buyer_ai, "get_analyzer", lambda: _Analyzer())
    _auth(app)

    with TestClient(app) as client:
        resp = client.get("/api/v1/buyer-ai/ruptures-risk", params={"dias_ahead": 7})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["produto_id"] == "A"


def test_ruptures_risk_sem_credencial_401(app):
    with TestClient(app) as client:
        resp = client.get("/api/v1/buyer-ai/ruptures-risk")

    assert resp.status_code == 401
