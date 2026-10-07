from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.infrastructure.config.database import close_db, init_db
from src.infrastructure.config.gateway_database import init_gateway_db
from src.infrastructure.config.settings import settings
from src.interfaces.http.routes import clientes, expenses, gateway_expenses, health, sync
from src.interfaces.http.routes import fechamento_enterprise
from src.interfaces.http.routes import auth
from src.interfaces.http.routes import metrics
from src.interfaces.http.routes import analytics
from src.interfaces.http.routes import finance_center
from src.interfaces.http.routes import cash_flow
from src.interfaces.http.routes import financial_intelligence
from src.modules.cash_reconciliation.interfaces.http import router as cash_audit_router
from src.shared.logger import setup_logging


def create_app() -> FastAPI:
    """Factory para criar instância da aplicação FastAPI."""

    root = Path(__file__).resolve().parents[3]
    # Modulos (ex.: cash_reconciliation) leem chaves por unidade via os.getenv
    load_dotenv(root / ".env", override=False)

    # Setup logging
    setup_logging(settings.log_level, settings.log_format)

    # Criar app
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        debug=settings.debug,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Incluir rotas
    app.include_router(health.router)
    app.include_router(gateway_expenses.router)
    app.include_router(fechamento_enterprise.router)
    app.include_router(expenses.router)
    app.include_router(clientes.router)
    app.include_router(sync.router)
    app.include_router(auth.router)
    app.include_router(metrics.router)
    app.include_router(analytics.router)
    app.include_router(finance_center.router)
    app.include_router(cash_flow.router)
    app.include_router(financial_intelligence.router)
    app.include_router(cash_audit_router)

    frontend_dir = root / "frontend"
    if frontend_dir.is_dir():
        app.mount("/frontend", StaticFiles(directory=str(frontend_dir)), name="frontend")

        @app.get("/app/financial")
        async def financial_frontend() -> FileResponse:
            return FileResponse(frontend_dir / "index.html", media_type="text/html; charset=utf-8")

    # Startup event
    @app.on_event("startup")
    async def on_startup():
        """Executado ao iniciar a aplicação."""
        await init_db()
        await init_gateway_db()

    # Shutdown event
    @app.on_event("shutdown")
    async def on_shutdown():
        """Executado ao desligar a aplicação."""
        await close_db()

    return app


app = create_app()
