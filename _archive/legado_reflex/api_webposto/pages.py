"""
api_webposto: Reflex Pages Module - TESTE BASICO

SUPER SIMPLES: Sem imports, só uma página básica
"""

import reflex as rx


@rx.page(title="LOGOS Hub", route="/")
def index():
    """Página de teste mínima"""
    return rx.vstack(
        rx.heading("Hello LOGOS", size="1"),
        rx.text("Test page"),
        padding="20px",
        bg="#050506",
        color="white",
        min_height="100vh",
    )


@rx.page(title="Auditoria Adelaide", route="/tax-audit")
def tax_audit():
    """Tax audit page"""
    return rx.vstack(
        rx.heading("Adelaide Audit", size="1"),
        rx.text("Auditoria tributária"),
        padding="20px",
        bg="#050506",
        color="white",
        min_height="100vh",
    )


@rx.page(title="Margem Real", route="/margin")
def margin():
    """Margin page"""
    return rx.vstack(
        rx.heading("Margem Real", size="1"),
        rx.text("Análise de margens"),
        padding="20px",
        bg="#050506",
        color="white",
        min_height="100vh",
    )


@rx.page(title="Análise Tributária", route="/audit")
def audit():
    """Audit page"""
    return rx.vstack(
        rx.heading("Análise Tributária", size="1"),
        rx.text("Relatório de achados"),
        padding="20px",
        bg="#050506",
        color="white",
        min_height="100vh",
    )

