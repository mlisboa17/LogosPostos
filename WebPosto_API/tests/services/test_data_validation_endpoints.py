"""Testes HTTP de data-validation (auth fail-closed)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints import data_validation
from src.interfaces.http.dependencies import get_current_user


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(data_validation.router, prefix="/api/v1")
    yield application
    application.dependency_overrides.clear()


def test_data_validation_compras_sem_credencial_401(app):
    with TestClient(app) as client:
        resp = client.get("/api/v1/data-validation/compras")

    assert resp.status_code == 401


def test_data_validation_compras_com_credencial_nao_401(app, monkeypatch):
    class _Validator:
        async def generate_data_quality_report(self, *args, **kwargs):
            return {
                "status": "ok",
                "periodo": "teste",
                "total_compras": 0,
                "compras_com_problema": 0,
                "cobertura_dados_percentual": 100.0,
                "fornecedores_analisados": 0,
                "fornecedores_com_anomalia": 0,
                "problemas_encontrados": [],
                "recomendacoes": [],
            }

    monkeypatch.setattr(data_validation, "get_validator", lambda: _Validator())
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "tester",
        "role": "diretor",
        "company_id": None,
    }

    with TestClient(app) as client:
        resp = client.get("/api/v1/data-validation/compras")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
