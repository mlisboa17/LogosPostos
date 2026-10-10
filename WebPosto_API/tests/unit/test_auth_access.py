import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.config.settings import settings
from src.infrastructure.security.jwt_utils import create_access_token, create_refresh_token, decode_token
from src.infrastructure.security.passwords import hash_password
from src.interfaces.http.routes import auth
from src.modules.cash_reconciliation.interfaces.http import router as cash_audit_router
from src.modules.commercial_performance.config import POSTOS
from src.modules.commercial_performance.interfaces.http import router as commercial_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(cash_audit_router)
    app.include_router(commercial_router)
    return TestClient(app)


def _user_config(email: str, role: str, company_id: int | None = None) -> dict:
    return {
        "email": email,
        "password_hash": hash_password("synthetic-test-password"),
        "role": role,
        "company_id": company_id,
    }


def _set_users(monkeypatch, *users: dict) -> None:
    monkeypatch.setattr(settings, "auth_users_json", json.dumps(users))
    monkeypatch.setattr(settings, "auth_cookie_secure", False)


def _set_access(client: TestClient, *, role: str, company_id: int | None = None) -> None:
    token = create_access_token(
        "unit-test@example.invalid",
        extra={"role": role, "company_id": company_id, "token_type": "access"},
    )
    client.cookies.set("access_token", token)


def test_rotas_financeiras_rejeitam_sessao_ausente():
    client = _client()

    assert client.get("/api/v1/cash-audit/unidades").status_code == 401
    assert client.get("/api/v1/commercial/postos").status_code == 401


def test_gerente_lista_e_consulta_apenas_a_propria_unidade(monkeypatch):
    unidade, outra_unidade = tuple(POSTOS)[:2]
    _set_users(monkeypatch, _user_config("gerente@example.invalid", "gerente", unidade))
    client = _client()
    _set_access(client, role="gerente", company_id=unidade)

    postos = client.get("/api/v1/commercial/postos")
    assert postos.status_code == 200
    assert [posto["empresa_codigo"] for posto in postos.json()] == [unidade]
    assert client.get(
        f"/api/v1/commercial/placar?posto={outra_unidade}&mes=2026-10"
    ).status_code == 403
    assert client.get(f"/api/v1/cash-audit/fechamento?unidade={outra_unidade}&inicio=2026-10-06&fim=2026-10-06").status_code == 403


def test_diretor_tem_acesso_a_todas_as_unidades(monkeypatch):
    _set_users(monkeypatch, _user_config("diretor@example.invalid", "diretor"))
    client = _client()
    _set_access(client, role="diretor")

    assert client.get("/api/v1/cash-audit/unidades").status_code == 200
    assert len(client.get("/api/v1/commercial/postos").json()) == len(POSTOS)


def test_auditor_pode_ler_todas_as_unidades_mas_nao_emitir_token_tv(monkeypatch):
    unidade = next(iter(POSTOS))
    _set_users(monkeypatch, _user_config("auditor@example.invalid", "auditor"))
    client = _client()
    _set_access(client, role="auditor")

    assert len(client.get("/api/v1/commercial/postos").json()) == len(POSTOS)
    assert client.post("/auth/tv-token", json={"unidade": unidade}).status_code == 403


def test_login_json_emite_cookie_com_perfil_e_unidade_sem_devolver_jwt(monkeypatch):
    unidade = next(iter(POSTOS))
    _set_users(monkeypatch, _user_config("gerente@example.invalid", "gerente", unidade))
    client = _client()

    response = client.post(
        "/auth/login",
        json={"email": "GERENTE@example.invalid", "password": "synthetic-test-password"},
    )

    assert response.status_code == 200
    assert response.json()["user"] == {
        "sub": "gerente@example.invalid",
        "email": "gerente@example.invalid",
        "role": "gerente",
        "company_id": unidade,
    }
    assert "access_token" not in response.json()
    assert "refresh_token" not in response.json()
    token = decode_token(response.cookies["access_token"])
    assert token["role"] == "gerente"
    assert token["company_id"] == unidade


def test_token_tv_fica_limitado_ao_placar_de_uma_unidade(monkeypatch):
    unidade, outra_unidade = tuple(POSTOS)[:2]
    _set_users(monkeypatch, _user_config("diretor@example.invalid", "diretor"))
    client = _client()
    _set_access(client, role="diretor")
    client.cookies.set("refresh_token", create_refresh_token("diretor@example.invalid"))

    response = client.post("/auth/tv-token", json={"unidade": unidade})
    assert response.status_code == 200
    assert response.cookies.get("display_token")
    display = decode_token(response.cookies["display_token"])
    assert display["token_type"] == "display"
    assert display["scope"] == "commercial:read"
    assert display["company_id"] == unidade
    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith("access_token=") and "Max-Age=0" in cookie for cookie in cookies)
    assert any(cookie.startswith("refresh_token=") and "Max-Age=0" in cookie for cookie in cookies)

    client.cookies.clear()
    client.cookies.set("display_token", response.cookies["display_token"], path="/api/v1/commercial")
    headers = {"X-Display-Mode": "true"}
    postos = client.get("/api/v1/commercial/postos", headers=headers)
    assert postos.status_code == 200
    assert [posto["empresa_codigo"] for posto in postos.json()] == [unidade]
    assert client.get("/api/v1/cash-audit/unidades").status_code == 401
    assert client.get(
        f"/api/v1/commercial/placar?posto={outra_unidade}&mes=2026-10",
        headers=headers,
    ).status_code == 403


def test_refresh_reconstroi_perfil_e_unidade(monkeypatch):
    unidade = next(iter(POSTOS))
    _set_users(monkeypatch, _user_config("gerente@example.invalid", "gerente", unidade))
    client = _client()
    client.cookies.set("refresh_token", create_refresh_token("gerente@example.invalid"))

    response = client.post("/auth/refresh")

    assert response.status_code == 200
    token = decode_token(response.cookies["access_token"])
    assert token["role"] == "gerente"
    assert token["company_id"] == unidade


def test_access_token_nao_pode_ser_usado_como_refresh(monkeypatch):
    _set_users(monkeypatch, _user_config("diretor@example.invalid", "diretor"))
    client = _client()
    client.cookies.set(
        "refresh_token",
        create_access_token("diretor@example.invalid", extra={"token_type": "access"}),
    )

    assert client.post("/auth/refresh").status_code == 401


def test_login_com_cadastro_json_rejeita_configuracao_invalida(monkeypatch):
    monkeypatch.setattr(settings, "auth_users_json", "[")
    client = _client()

    response = client.post(
        "/auth/login",
        json={"email": "invalid@example.invalid", "password": "synthetic-test-password"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Autenticação indisponível."
