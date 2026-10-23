"""Fábrica compartilhada do cliente WebPosto para os endpoints de IA."""

from __future__ import annotations

import os

from src.webposto import WebPostoClient, WebPostoConfig


def make_webposto_client() -> WebPostoClient:
    """Cria o cliente com as mesmas variáveis de ambiente usadas pela auditoria."""
    chave = (os.getenv("WEBPOSTO_API_KEY") or os.getenv("WEBPOSTO_CHAVE") or "").strip()
    base = os.getenv("WEBPOSTO_BASE_URL", "https://web.qualityautomacao.com.br").strip()
    return WebPostoClient(WebPostoConfig(chave=chave, base_url=base, max_retries=2))
