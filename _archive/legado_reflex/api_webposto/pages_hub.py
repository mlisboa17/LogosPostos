# DEPRECATED - Rotas movidas para api_webposto/pages.py
# Este arquivo está vazio agora para evitar conflitos de roteamento
# FALLBACK PAGES (Para compatibilidade e debugging)
# ─────────────────────────────────────────────────────────

def error_page(error: str = "404") -> rx.Component:
    """Página de erro genérica"""
    return rx.vstack(
        rx.heading(f"Erro {error}", size="1", color="#FF4444"),
        rx.text("Página não encontrada", color="#A0A0A0"),
        rx.link(rx.button("← Voltar ao Hub", color_scheme="cyan"), href="/"),
        spacing="4",
        align_items="center",
        justify_content="center",
        height="100vh",
    )


# ─────────────────────────────────────────────────────────
# EXPORTS (Para compatibilidade com imports existentes)
# ─────────────────────────────────────────────────────────

# Manter compatibilidade com imports antigos
__all__ = [
    "executive_hub",
    "index",
    "tax_audit",
    "margin",
    "audit",
    "error_page",
]
