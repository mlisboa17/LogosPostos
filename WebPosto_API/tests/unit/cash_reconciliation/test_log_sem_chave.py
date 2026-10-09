"""ARCH01: nenhuma CHAVE do webPosto pode aparecer em log (o httpx registra a URL completa em INFO)."""
import logging

import httpx

from src.modules.cash_reconciliation.adapters import webposto_http  # noqa: F401  (configura os loggers)
from src.shared.logger import setup_logging


def test_httpx_nao_registra_url_com_chave(caplog):
    setup_logging("INFO", "text")
    with caplog.at_level(logging.INFO):
        transporte = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
        with httpx.Client(transport=transporte) as c:
            c.get("http://t/INTEGRACAO/V1/CAIXAS", params={"CHAVE": "segredo-de-teste"})
    assert "segredo-de-teste" not in caplog.text
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
