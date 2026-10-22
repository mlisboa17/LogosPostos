"""Painel local do Logos Match (FastAPI + Jinja2, só em 127.0.0.1, com login)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from apps.match.painel import rotas

HOSTS_LOCAIS = ("127.0.0.1", "localhost")

_CABECALHOS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": ("default-src 'self'; style-src 'self'; script-src 'none';"
                                " frame-ancestors 'none'; form-action 'self'; base-uri 'none'"),
}


def criar_app(con_factory, sched=None) -> FastAPI:
    """`con_factory()` abre uma conexão nova; `sched` (opcional) é o agendador a reagendar."""
    app = FastAPI(title="Logos Match", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.con_factory = con_factory
    app.state.sched = sched
    app.state.sessoes = rotas.Sessoes()
    app.mount("/static", StaticFiles(directory=str(rotas.PASTA / "static")), name="static")
    app.include_router(rotas.router)
    app.add_exception_handler(rotas.Redirecionar, rotas.tratar_redirecionar)
    app.add_exception_handler(rotas.Recusado, rotas.tratar_recusado)

    @app.middleware("http")
    async def _cabecalhos(request, call_next):
        resposta = await call_next(request)
        for nome, valor in _CABECALHOS.items():
            resposta.headers.setdefault(nome, valor)
        return resposta

    # Contra DNS rebinding: só aceita o painel chamado pelo nome local.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(HOSTS_LOCAIS))
    return app
