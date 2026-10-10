from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.config.settings import settings
from src.infrastructure.security.passwords import hash_password
from src.interfaces.http.routes import auth


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(auth.router)
    return TestClient(app)


def test_login_com_credenciais_validas():
    client = _build_client()

    response = client.post(
        "/auth/login",
        json={"email": settings.auth_user_email, "password": settings.auth_user_password},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == settings.auth_user_email
    assert payload["user"]["role"] == "diretor"
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    assert "access_token" not in payload
    assert "refresh_token" not in payload


def test_login_rejeita_credenciais_invalidas():
    client = _build_client()

    response = client.post(
        "/auth/login",
        json={"email": settings.auth_user_email, "password": "senha_incorreta"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_com_hash_de_senha(monkeypatch):
    client = _build_client()
    senha = "SenhaMuitoForte@123"
    senha_hash = hash_password(senha)

    monkeypatch.setattr(settings, "auth_user_email", "secure@company.com")
    monkeypatch.setattr(settings, "auth_user_password", "")
    monkeypatch.setattr(settings, "auth_user_password_hash", senha_hash)

    response = client.post(
        "/auth/login",
        json={"email": "secure@company.com", "password": senha},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "secure@company.com"