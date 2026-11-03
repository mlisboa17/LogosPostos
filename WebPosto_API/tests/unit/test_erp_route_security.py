"""ERP routes: offline authentication, RBAC and write barrier regressions."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.infrastructure.config.settings import settings
from src.infrastructure.security.jwt_utils import create_access_token

ROUTES = [
    ("GET", "/api/v1/proxy/PRODUTO"),
    ("GET", "/api/v1/webposto/grupos-produto"),
    ("GET", "/api/v1/webposto/produtos"),
    ("GET", "/api/v1/webposto/produtos/1"),
    ("POST", "/api/v1/webposto/produtos"),
    ("PUT", "/api/v1/webposto/produtos/1"),
]
CREATE = {"descricao": "Produto sintético", "grupoCodigo": 1, "precoVenda": 1}


@pytest.fixture(params=["unified", "http"])
def erp(request, monkeypatch, tmp_path):
    import redis

    monkeypatch.setattr(redis.Redis, "ping", Mock(side_effect=ConnectionError("offline")))
    from src.presentation import app as presentation
    from src.interfaces.http import app as http

    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "environment", "development")
    resolve = Mock(return_value="synthetic-integration-key")
    monkeypatch.setattr(presentation, "_resolve_chave", resolve)
    monkeypatch.setattr(presentation, "_make_webposto_client", Mock(return_value=object()))
    monkeypatch.setattr(presentation, "obter_produto", AsyncMock(return_value=None))
    monkeypatch.setattr(
        presentation.httpx,
        "AsyncClient",
        Mock(side_effect=AssertionError("Unexpected external ERP request")),
    )

    from src.infrastructure.cache.valkey_manager import ValkeyManager
    from src.infrastructure.services.cache_service import CacheService
    from src.application.usecases import fetch_unidade_webposto
    from src.modules.cash_reconciliation.adapters import webposto_escrita_despesa
    from src import webposto

    cache = ValkeyManager()
    monkeypatch.setattr(presentation, "get_cache", lambda: cache)
    monkeypatch.setattr(presentation, "get_cache_service", lambda: CacheService(cache))
    monkeypatch.setattr(webposto, "WebPostoClient", Mock(return_value=object()))
    monkeypatch.setattr(
        fetch_unidade_webposto, "fetch_unidade_webposto", AsyncMock(return_value=None)
    )
    flags = tmp_path / "write-flags.conf"
    flags.write_text("WEBPOSTO_WRITES=0\nLOGOS_ERP_ESCRITA=0\n", encoding="utf-8")
    verify_flags = webposto_escrita_despesa.verificar_travas_despesa
    monkeypatch.setattr(
        webposto_escrita_despesa,
        "verificar_travas_despesa",
        lambda _: verify_flags(flags),
    )
    monkeypatch.setattr(presentation, "app", presentation.create_unified_app())
    app = presentation.app if request.param == "unified" else http.create_app()
    app.state.test_flags = flags
    return TestClient(app, raise_server_exceptions=False), presentation, resolve


def headers(role="diretor", company_id=None, **claims):
    token = create_access_token(
        "erp-test@example.invalid",
        extra={"role": role, "company_id": company_id, "token_type": "access", **claims},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("method,path", ROUTES)
def test_missing_auth_is_denied_before_server_key(erp, method, path):
    client, _, resolve = erp
    response = client.request(method, path, json=CREATE)
    assert response.status_code == 401
    resolve.assert_not_called()


@pytest.mark.parametrize("kind", ["invalid", "expired", "refresh", "display", "missing-sub"])
def test_invalid_credentials_fail_closed_in_demo(erp, kind):
    client, _, resolve = erp
    token = "invalid-synthetic-token"
    if kind == "expired":
        token = create_access_token(
            "erp-test@example.invalid",
            extra={"role": "diretor", "token_type": "access"},
            expires_delta=timedelta(seconds=-1),
        )
    elif kind in {"refresh", "display"}:
        token = create_access_token(
            "erp-test@example.invalid",
            extra={"role": "diretor", "token_type": kind},
        )
    elif kind == "missing-sub":
        token = create_access_token("", extra={"role": "diretor"})
    response = client.get(
        "/api/v1/webposto/produtos/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    resolve.assert_not_called()


def test_invalid_cookie_cannot_be_replaced_by_demo_or_bearer(erp):
    client, _, resolve = erp
    client.cookies.set("access_token", "invalid-synthetic-token")
    response = client.get("/api/v1/webposto/produtos/1", headers=headers())
    assert response.status_code == 401
    resolve.assert_not_called()


@pytest.mark.parametrize("method,path", ROUTES)
@pytest.mark.parametrize("company", [11495, 5555])
def test_company_restricted_manager_cannot_use_unscoped_routes(erp, method, path, company):
    client, _, resolve = erp
    response = client.request(
        method,
        path,
        params={"empresaCodigo": company, "filial": company},
        headers=headers("gerente", 11495),
        json=CREATE,
    )
    assert response.status_code == 403
    resolve.assert_not_called()


@pytest.mark.parametrize("method,path", ROUTES[-2:])
def test_read_role_cannot_write_even_with_flags(erp, method, path):
    client, _, resolve = erp
    client.app.state.test_flags.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n")
    response = client.request(method, path, headers=headers("auditor"), json=CREATE)
    assert response.status_code == 403
    resolve.assert_not_called()


@pytest.mark.parametrize(
    "flags",
    [
        "",
        "WEBPOSTO_WRITES=0\nLOGOS_ERP_ESCRITA=1\n",
        "WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=0\n",
        "WEBPOSTO_WRITES=1\nWEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n",
        "WEBPOSTO_WRITES=true\nLOGOS_ERP_ESCRITA=1\n",
    ],
)
@pytest.mark.parametrize("method,path", ROUTES[-2:])
def test_physical_flags_fail_closed_despite_process_environment(
    erp, monkeypatch, flags, method, path
):
    client, _, resolve = erp
    monkeypatch.setenv("WEBPOSTO_WRITES", "1")
    monkeypatch.setenv("LOGOS_ERP_ESCRITA", "1")
    client.app.state.test_flags.write_text(flags)
    response = client.request(method, path, headers=headers(), json=CREATE)
    assert response.status_code == 403
    resolve.assert_not_called()


def test_missing_physical_flag_file_blocks_write(erp):
    client, _, resolve = erp
    client.app.state.test_flags.unlink()
    response = client.post("/api/v1/webposto/produtos", headers=headers(), json=CREATE)
    assert response.status_code == 403
    resolve.assert_not_called()


@pytest.mark.parametrize("role", ["diretor", "auditor"])
def test_authorized_reads_and_cache_contract(erp, monkeypatch, role):
    client, presentation, resolve = erp
    from src.domain.catalog.grupo_schema import GruposProdutoResponse
    from src.domain.catalog.product_schema import PaginatedProdutosResponse, WebPostoProdutoSchema

    groups = AsyncMock(return_value=GruposProdutoResponse())
    products = AsyncMock(
        return_value=PaginatedProdutosResponse(
            pagina_atual=1,
            total_paginas=1,
            total_registros=1,
            produtos=[WebPostoProdutoSchema(id=1, descricao="Produto sintético")],
        )
    )
    monkeypatch.setattr(presentation, "fetch_produto_grupos", groups)
    monkeypatch.setattr(presentation, "fetch_produtos_catalog", products)
    monkeypatch.setattr(presentation, "fetch_produtos_catalog_completo", products)
    presentation.obter_produto.return_value = WebPostoProdutoSchema(
        id=1, descricao="Produto sintético"
    )
    auth = headers(role)
    assert client.get("/api/v1/webposto/grupos-produto", headers=auth).status_code == 200
    for query in ("?limit=30", "?todos=true", "?grupos=1,2&situacao=ativos"):
        response = client.get("/api/v1/webposto/produtos" + query, headers=auth)
        assert response.status_code == 200
        assert response.json()["produtos"][0]["id"] == 1
    assert client.get("/api/v1/webposto/produtos/1", headers=auth).status_code == 200
    assert resolve.called
    assert client.get("/api/v1/webposto/produtos?limit=30").status_code == 401


@pytest.mark.parametrize(
    "method,path,operation",
    [
        ("POST", "/api/v1/webposto/produtos", "criar_produto"),
        ("PUT", "/api/v1/webposto/produtos/1", "atualizar_produto"),
    ],
)
def test_director_write_requires_both_physical_flags(erp, monkeypatch, method, path, operation):
    client, presentation, _ = erp
    from src.domain.catalog.produto_crud_schema import ProdutoCrudResponse

    client.app.state.test_flags.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n")
    execute = AsyncMock(return_value=ProdutoCrudResponse(mensagem="Operação simulada"))
    monkeypatch.setattr(presentation, operation, execute)
    response = client.request(method, path, headers=headers(), json=CREATE)
    assert response.status_code == 200
    assert response.json()["ok"] is True
    execute.assert_awaited_once()


@pytest.mark.parametrize(
    "operation,path,status",
    [
        ("obter_produto", "/api/v1/webposto/produtos/1", 502),
        ("fetch_produto_grupos", "/api/v1/webposto/grupos-produto", 503),
        ("fetch_produtos_catalog", "/api/v1/webposto/produtos", 503),
        ("criar_produto", "/api/v1/webposto/produtos", 502),
        ("atualizar_produto", "/api/v1/webposto/produtos/1", 502),
    ],
)
def test_internal_errors_do_not_expose_integration_key(
    erp, monkeypatch, caplog, operation, path, status
):
    client, presentation, _ = erp
    client.app.state.test_flags.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n")
    monkeypatch.setattr(
        presentation,
        operation,
        AsyncMock(side_effect=RuntimeError("synthetic-integration-key")),
    )
    method = {"criar_produto": "POST", "atualizar_produto": "PUT"}.get(operation, "GET")
    response = client.request(method, path, headers=headers(), json=CREATE)
    assert response.status_code == status
    assert "synthetic-integration-key" not in response.text + caplog.text


def test_missing_or_rejected_integration_key(erp):
    client, presentation, resolve = erp
    from src.webposto.exceptions import AuthError

    resolve.return_value = ""
    assert client.get("/api/v1/webposto/produtos/1", headers=headers()).status_code == 401
    presentation.obter_produto.assert_not_awaited()
    resolve.return_value = "synthetic-integration-key"
    presentation.obter_produto.side_effect = AuthError("synthetic-integration-key")
    response = client.get("/api/v1/webposto/produtos/1", headers=headers())
    assert response.status_code == 401
    assert "synthetic-integration-key" not in response.text


@pytest.mark.parametrize("result", ["ok", "network", "upstream", "invalid-json"])
def test_proxy_authorization_forwarding_and_safe_errors(erp, monkeypatch, caplog, result):
    client, presentation, _ = erp
    upstream = Mock()
    upstream.get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"resultados": []},
            request=httpx.Request("GET", "https://erp.invalid"),
        )
    )
    if result == "network":
        upstream.get.side_effect = httpx.ConnectError("synthetic-integration-key")
    elif result == "upstream":
        upstream.get.return_value = httpx.Response(500, text="synthetic-integration-key")
    elif result == "invalid-json":
        upstream.get.return_value = httpx.Response(200, text="synthetic-integration-key")
    context = AsyncMock()
    context.__aenter__.return_value = upstream
    monkeypatch.setattr(presentation.httpx, "AsyncClient", Mock(return_value=context))
    response = client.get(
        "/api/v1/proxy/PRODUTO?pagina=2&CHAVE=unexpected-key",
        headers=headers("auditor"),
    )
    assert (
        response.status_code
        == {"ok": 200, "network": 502, "upstream": 500, "invalid-json": 502}[result]
    )
    assert upstream.get.call_args.kwargs["params"] == {
        "CHAVE": "synthetic-integration-key",
        "pagina": "2",
    }
    assert "synthetic-integration-key" not in response.text + caplog.text
    if result == "ok":
        assert response.json()["data"] == {"resultados": []}


def test_same_origin_consumer_uses_existing_login_cookie(erp, monkeypatch):
    client, _, _ = erp
    monkeypatch.setattr(settings, "auth_users_json", "")
    monkeypatch.setattr(settings, "auth_user_email", "erp-test@example.invalid")
    monkeypatch.setattr(settings, "auth_user_password", "synthetic-test-password")
    monkeypatch.setattr(settings, "auth_user_password_hash", "")
    monkeypatch.setattr(settings, "auth_user_role", "diretor")
    monkeypatch.setattr(settings, "auth_user_company_id", "")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    login = client.post(
        "/auth/login",
        json={
            "email": "erp-test@example.invalid",
            "password": "synthetic-test-password",
        },
    )
    assert login.status_code == 200
    assert client.get("/api/v1/webposto/produtos/1").status_code == 404
