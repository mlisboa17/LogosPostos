"""
api_webposto: Reflex Frontend Application
Entry point for Reflex framework

Pages:
- /: Home/Index
- /login: Login
- /dashboard: Dashboard (protected)
- /audit: Audit Logs (protected)
"""

import reflex as rx


# =============================================================================
# Global State
# =============================================================================

class State(rx.State):
    """Global app state"""
    
    # Authentication
    is_authenticated: bool = False
    user_email: str = ""
    user_role: str = ""
    
    # UI
    dark_mode: bool = True


# =============================================================================
# Components
# =============================================================================

def navbar() -> rx.Component:
    """Navigation bar"""
    return rx.hstack(
        rx.heading("🚀 Api WebPosto", size="lg"),
        rx.spacer(),
        rx.cond(
            State.is_authenticated,
            rx.hstack(
                rx.text(State.user_email, size="sm"),
                rx.badge(State.user_role, size="sm"),
                rx.button("Logout", on_click=lambda: State.set_is_authenticated(False)),
                spacing="2",
            ),
            rx.link(rx.button("Login"), href="/login"),
        ),
        width="100%",
        padding="4",
        border_bottom="1px solid #e2e8f0",
        bg="white",
        box_shadow="sm",
    )


# =============================================================================
# Pages
# =============================================================================

@rx.page(route="/", title="Home - Api WebPosto")
def home() -> rx.Component:
    """Home page"""
    return rx.vstack(
        navbar(),
        rx.box(
            rx.vstack(
                rx.heading("Welcome to Api WebPosto", size="xl"),
                rx.text("Enterprise Sync Platform with Security Infrastructure"),
                
                rx.divider(),
                
                # Features
                rx.heading("✨ Features", size="md"),
                rx.unordered_list(
                    rx.list_item("JWT RS256 Authentication"),
                    rx.list_item("Role-Based Access Control (RBAC)"),
                    rx.list_item("Real-time Audit Logging"),
                    rx.list_item("Rate Limiting & DDoS Protection"),
                    rx.list_item("Encrypted Data Storage"),
                ),
                
                rx.divider(),
                
                # Quick Links
                rx.hstack(
                    rx.link(rx.button("📊 Dashboard", color_scheme="blue"), href="/dashboard"),
                    rx.link(rx.button("🔐 Login", color_scheme="green"), href="/login"),
                    rx.link(rx.button("📋 Audit", color_scheme="purple"), href="/audit"),
                    spacing="4",
                ),
                
                spacing="4",
                padding="6",
            ),
            width="100%",
            max_width="600px",
            margin="0 auto",
        ),
        width="100%",
        min_height="100vh",
        spacing="0",
    )


@rx.page(route="/login", title="Login - Api WebPosto")
def login() -> rx.Component:
    """Login page"""
    return rx.vstack(
        navbar(),
        rx.box(
            rx.vstack(
                rx.heading("🔐 Sign In", size="xl"),
                
                rx.vstack(
                    rx.text("Email", font_weight="bold"),
                    rx.input(placeholder="user@company.com", width="100%"),
                ),
                
                rx.vstack(
                    rx.text("Password", font_weight="bold"),
                    rx.input(placeholder="••••••••", type_="password", width="100%"),
                ),
                
                rx.button(
                    "Sign In",
                    width="100%",
                    on_click=lambda: State.set_is_authenticated(True),
                ),
                
                spacing="4",
                padding="6",
            ),
            width="100%",
            max_width="400px",
            margin="0 auto",
            border="1px solid #e2e8f0",
            border_radius="lg",
            margin_top="4",
        ),
        width="100%",
        min_height="100vh",
        spacing="0",
    )


@rx.page(route="/dashboard", title="Dashboard - Api WebPosto")
def dashboard() -> rx.Component:
    """Dashboard page (protected)"""
    return rx.vstack(
        navbar(),
        rx.cond(
            State.is_authenticated,
            rx.box(
                rx.vstack(
                    rx.heading("📊 Dashboard", size="xl"),
                    rx.text("Welcome to your dashboard"),
                    
                    rx.divider(),
                    
                    # Metrics
                    rx.hstack(
                        rx.box(
                            rx.vstack(
                                rx.text("💰 Total", font_weight="bold"),
                                rx.text("$50,000", size="lg"),
                            ),
                            padding="4",
                            border="1px solid #e2e8f0",
                            border_radius="md",
                        ),
                        rx.box(
                            rx.vstack(
                                rx.text("📈 Growth", font_weight="bold"),
                                rx.text("+12%", size="lg", color="green"),
                            ),
                            padding="4",
                            border="1px solid #e2e8f0",
                            border_radius="md",
                        ),
                        rx.box(
                            rx.vstack(
                                rx.text("👥 Users", font_weight="bold"),
                                rx.text("1,234", size="lg"),
                            ),
                            padding="4",
                            border="1px solid #e2e8f0",
                            border_radius="md",
                        ),
                        width="100%",
                        spacing="4",
                    ),
                    
                    spacing="4",
                    padding="6",
                ),
                width="100%",
                max_width="900px",
                margin="0 auto",
            ),
            rx.box(
                rx.vstack(
                    rx.heading("❌ Access Denied", size="xl"),
                    rx.text("You need to be logged in to view this page"),
                    rx.link(rx.button("Go to Login"), href="/login"),
                    spacing="4",
                    padding="6",
                ),
                width="100%",
                max_width="600px",
                margin="0 auto",
            ),
        ),
        width="100%",
        min_height="100vh",
        spacing="0",
    )


@rx.page(route="/audit", title="Audit Logs - Api WebPosto")
def audit() -> rx.Component:
    """Audit page (protected)"""
    return rx.vstack(
        navbar(),
        rx.cond(
            State.is_authenticated,
            rx.box(
                rx.vstack(
                    rx.heading("📋 Audit Logs", size="xl"),
                    rx.text("Recent activity and security events"),
                    
                    rx.divider(),
                    
                    # Audit table placeholder
                    rx.table(
                        rx.thead(
                            rx.tr(
                                rx.th("Timestamp"),
                                rx.th("Action"),
                                rx.th("User"),
                                rx.th("Status"),
                            ),
                        ),
                        rx.tbody(
                            rx.tr(
                                rx.td("2026-05-09 20:30:00"),
                                rx.td("login_success"),
                                rx.td("user@company.com"),
                                rx.td("✓"),
                            ),
                            rx.tr(
                                rx.td("2026-05-09 20:25:00"),
                                rx.td("data_accessed"),
                                rx.td("user@company.com"),
                                rx.td("✓"),
                            ),
                        ),
                        width="100%",
                    ),
                    
                    spacing="4",
                    padding="6",
                ),
                width="100%",
                max_width="900px",
                margin="0 auto",
            ),
            rx.box(
                rx.vstack(
                    rx.heading("❌ Access Denied", size="xl"),
                    rx.text("You need to be logged in to view this page"),
                    rx.link(rx.button("Go to Login"), href="/login"),
                    spacing="4",
                    padding="6",
                ),
                width="100%",
                max_width="600px",
                margin="0 auto",
            ),
        ),
        width="100%",
        min_height="100vh",
        spacing="0",
    )


# =============================================================================
# App
# =============================================================================

# Create app
app = rx.App()

# This will auto-discover pages decorated with @rx.page()
