"""
CLAUDE 3.7 + GROK 4: Reflex App Entry Point
Main application with page routing

Routes:
- /: Dashboard (public)
- /login: Login page
- /audit: Audit logs (@require_director)
"""

import reflex as rx
from src.presentation.frontend.state_jwt import GlobalState
from src.presentation.frontend.rbac_router import PermissionRouter, unauthorized_view

# Import page components
try:
    from src.presentation.frontend.pages.login import login_page
    from src.presentation.frontend.pages.dashboard import dashboard_page
    from src.presentation.frontend.pages.audit import audit_page
except ImportError:
    # Fallback if pages not yet created
    login_page = lambda: rx.text("Login Page - Coming Soon")
    dashboard_page = lambda: rx.text("Dashboard - Coming Soon")
    audit_page = lambda: rx.text("Audit - Coming Soon")


# =============================================================================
# Index Page (Redirect to Dashboard or Login)
# =============================================================================

def index_page() -> rx.Component:
    """
    Index page - redirects based on authentication
    """
    return rx.cond(
        GlobalState.is_authenticated,
        rx.vstack(
            rx.heading("🎉 Welcome", size="xl"),
            rx.text("Redirecting to dashboard..."),
            rx.redirect("/dashboard"),
            spacing="4",
            padding="4",
        ),
        rx.redirect("/login")
    )


# =============================================================================
# App Configuration
# =============================================================================

# Create app instance
app = rx.App()

# Add pages with routes
app.add_page(
    index_page,
    route="/",
    title="Api WebPosto",
)

app.add_page(
    login_page,
    route="/login",
    title="Login - Api WebPosto",
)

app.add_page(
    dashboard_page,
    route="/dashboard",
    title="Dashboard - Api WebPosto",
)

app.add_page(
    audit_page,
    route="/audit",
    title="Audit Logs - Api WebPosto",
)


# =============================================================================
# App Compilation
# =============================================================================

if __name__ == "__main__":
    # This will be run by: reflex run
    pass
