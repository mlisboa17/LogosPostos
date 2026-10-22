import asyncio
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv

_ENV = Path(__file__).resolve().parents[1] / ".env"
if _ENV.is_file():
    load_dotenv(_ENV, override=False)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.repositories.models import Base

_tentativas_portal = []

_TEST_RUN_ID = uuid4().hex
_TEST_TMP_ROOT = Path(__file__).resolve().parent / "_test_tmp" / _TEST_RUN_ID
_TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def tmp_path(request):
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in request.node.name)
    p = _TEST_TMP_ROOT / safe_name
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture(autouse=True)
def _jwt_secret_exclusivo_de_teste(monkeypatch):
    """Evita usar o segredo padrão curto sem acessar ou alterar credenciais reais."""
    from src.infrastructure.config.settings import settings

    monkeypatch.setattr(
        settings,
        "secret_key",
        "logos-test-only-jwt-secret-32-bytes-minimum",
    )


@pytest.fixture(autouse=True)
def bloquear_navegadores_e_portal_premmia(monkeypatch, tmp_path):
    import httpx
    from playwright.sync_api import BrowserType as SyncBrowserType
    from playwright.async_api import BrowserType as AsyncBrowserType
    from playwright.sync_api._context_manager import PlaywrightContextManager
    from playwright.async_api._context_manager import (
        PlaywrightContextManager as AsyncContextManager,
    )

    tentativas = []
    from src.modules.cash_reconciliation.adapters import propostas_lancamento

    monkeypatch.setattr(propostas_lancamento, "DIRETORIO", tmp_path / "propostas_lancamento")

    def bloquear(*args, **kwargs):
        tentativas.append("Playwright/portal")
        _tentativas_portal.append("Playwright/portal")
        pytest.fail("Teste tentou abrir navegador ou acessar o portal Premmia.", pytrace=False)

    for classe, metodos in (
        (PlaywrightContextManager, ("__enter__",)),
        (AsyncContextManager, ("__aenter__",)),
        (SyncBrowserType, ("launch", "launch_persistent_context", "connect", "connect_over_cdp")),
        (AsyncBrowserType, ("launch", "launch_persistent_context", "connect", "connect_over_cdp")),
    ):
        for metodo in metodos:
            monkeypatch.setattr(classe, metodo, bloquear)

    enviar_sync = httpx.Client.send
    enviar_async = httpx.AsyncClient.send

    def enviar(self, request, *args, **kwargs):
        if request.url.host == "cn.vibraenergia.com.br":
            bloquear()
        return enviar_sync(self, request, *args, **kwargs)

    async def enviar_assincrono(self, request, *args, **kwargs):
        if request.url.host == "cn.vibraenergia.com.br":
            bloquear()
        return await enviar_async(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", enviar)
    monkeypatch.setattr(httpx.AsyncClient, "send", enviar_assincrono)
    yield
    assert not tentativas, "Tentativa de acesso real interceptada durante o teste."


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(
        f"Isolamento Premmia: {len(_tentativas_portal)} tentativas reais de navegador/portal."
    )


@pytest.fixture(scope="session")
def event_loop():
    """Fixture para event loop."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session() -> AsyncSession:
    """Fixture para sessão de banco em memória."""
    # Usar SQLite em memória para testes
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # Criar tabelas
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Criar session factory
    AsyncTestingSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, future=True
    )

    async with AsyncTestingSessionLocal() as session:
        yield session

    # Cleanup
    await engine.dispose()


@pytest.fixture
def cliente_dict():
    """Fixture: Dados de cliente para testes."""
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "nome": "Cliente Teste",
        "cnpj": "12345678901234",
        "ativo": True,
        "webposto_id": "WP001",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


@pytest.fixture
def abastecimento_dict():
    """Fixture: Dados de abastecimento para testes."""
    return {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "cliente_id": "550e8400-e29b-41d4-a716-446655440000",
        "data": datetime.utcnow(),
        "valor": 150.00,
        "litros": 30.0,
        "produto_id": "PROD001",
        "webposto_id": "ABA001",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
