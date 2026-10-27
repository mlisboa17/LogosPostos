"""
api_webposto: Reflex Pages Module - HUB EXECUTIVO SPA
Integra novo sistema de navegacao com shell corporativo

SIMPLIFICADO: Apenas importa paginas decoradas do pages_hub.py
Reflex auto-descobre e registra automaticamente via @rx.page()
"""

# Importar paginas decoradas (@rx.page) do pages_hub
from api_webposto import pages_hub  # noqa: F401

__all__ = ["pages_hub"]
