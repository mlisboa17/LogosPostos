from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.config.settings import settings
from src.infrastructure.security.passwords import hash_password
from src.interfaces.http.routes import auth


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(auth.router)
    return TestClient(app)


def _set_legacy_credentials(monkeypatch, *, email="diretor@example.invalid", password="synthetic-test-password"):
    monkeypatch.setattr(settings, "auth_users_json", "")
    monkeypatch.setattr(settings, "auth_user_email", email)
    monkeypatch.setattr(settings, "auth_user_password", password)
    monkeypatch.setattr(settings, "auth_user_password_hash", "")
    monkeypatch.setattr(settings, "auth_user_role", "diretor")
    monkeypatch.setattr(settings, "auth_user_company_id", "")


def test_login_com_credenciais_legadas_validas(monkeypatch):
    _set_legacy_credentials(monkeypatch)
    client = _build_client()

    response = client.post(
        "/auth/login",
        json={"email": "diretor@example.invalid", "password": "synthetic-test-password"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == "diretor@example.invalid"
    assert payload["user"]["role"] == "diretor"
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    assert "access_token" not in payload
    assert "refresh_token" not in payload


def test_login_rejeita_credenciais_invalidas(monkeypatch):
    _set_legacy_credentials(monkeypatch)
    client = _build_client()

    response = client.post(
        "/auth/login",
        json={"email": "diretor@example.invalid", "password": "senha_incorreta"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_sem_configuracao_e_recusado_com_mensagem_clara(monkeypatch):
    _set_legacy_credentials(monkeypatch, email="", password="")
    client = _build_client()

    response = client.post(
        "/auth/login",
        json={"email": "admin@company.com", "password": "password"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Login não configurado."


def test_senha_padrao_nao_autentica_sem_credencial_configurada(monkeypatch):
    _set_legacy_credentials(monkeypatch, email="admin@company.com", password="")
    client = _build_client()

    response = client.post(
        "/auth/login",
        json={"email": "admin@company.com", "password": "password"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Login não configurado."


def test_login_com_hash_em_auth_users_json(monkeypatch):
    client = _build_client()
    senha = "synthetic-test-password"
    senha_hash = hash_password(senha)

    monkeypatch.setattr(
        settings,
        "auth_users_json",
        '[{"email":"secure@example.invalid","password_hash":"%s","role":"diretor"}]' % senha_hash,
    )

    response = client.post(
        "/auth/login",
        json={"email": "secure@example.invalid", "password": senha},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "secure@example.invalid"


def test_auth_users_json_rejeita_senha_em_texto_claro(monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_users_json",
        '[{"email":"secure@example.invalid","password_hash":"synthetic-test-password","role":"diretor"}]',
    )

    response = _build_client().post(
        "/auth/login",
        json={"email": "secure@example.invalid", "password": "synthetic-test-password"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Autenticação indisponível."