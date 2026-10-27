"""
Reflex Pages - Entry point for page routing
Auto-discovered by Reflex framework
"""

import reflex as rx


# =============================================================================
# Simple App State
# =============================================================================

class State(rx.State):
    """Basic app state"""
    pass


# =============================================================================
# Index Page
# =============================================================================

def index() -> rx.Component:
    """
    Main index page
    """
    return rx.box(
        rx.vstack(
            # Logo/Title
            rx.vstack(
                rx.heading("🚀 Api WebPosto", size="2xl"),
                rx.text(
                    "Enterprise Sync Platform with Security Infrastructure",
                    color="gray",
                    size="lg",
                ),
                spacing="2",
                text_align="center",
            ),
            
            # Status
            rx.divider(),
            
            rx.vstack(
                rx.heading("✅ System Status", size="lg"),
                rx.unordered_list(
                    rx.list_item("🟢 Frontend: Running"),
                    rx.list_item("🟢 State Management: Ready"),
                    rx.list_item("🟢 Security: JWT + RBAC"),
                    rx.list_item("🟡 Backend: Not connected"),
                ),
                spacing="2",
            ),
            
            # Navigation
            rx.divider(),
            
            rx.hstack(
                rx.link(
                    rx.button("📊 Dashboard", color_scheme="blue"),
                    href="/dashboard"
                ),
                rx.link(
                    rx.button("🔐 Login", color_scheme="green"),
                    href="/login"
                ),
                rx.link(
                    rx.button("📋 Audit Logs", color_scheme="purple"),
                    href="/audit"
                ),
                spacing="4",
                justify="center",
            ),
            
            # Info
            rx.divider(),
            
            rx.vstack(
                rx.heading("📚 Documentation", size="md"),
                rx.unordered_list(
                    rx.list_item(
                        rx.link(
                            "Security Implementation",
                            href="file:///SECURITY_IMPLEMENTATION.md",
                            is_external=True,
                        )
                    ),
                    rx.list_item(
                        rx.link(
                            "Frontend Complete",
                            href="file:///PHASE7_8_FRONTEND_COMPLETE.md",
                            is_external=True,
                        )
                    ),
                ),
                spacing="2",
            ),
            
            # Footer
            rx.divider(),
            rx.text(
                "✨ Built with Reflex v0.6 + Turbopack + React 18 | Secure by design",
                size="sm",
                color="gray",
                text_align="center",
            ),
            
            spacing="6",
            padding="8",
            max_width="600px",
        ),
        
        width="100%",
        min_height="100vh",
        display="flex",
        justify_content="center",
        align_items="center",
        bg="linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
        color="white",
    )
