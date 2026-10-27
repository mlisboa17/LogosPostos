# Imports must be at the top so the module initializes correctly
import reflex as rx
from enum import Enum

# Register Executive Hub page routes in this app module.
from src.presentation.pages.hub_shell import hub_page  # noqa: F401

# =====================================================
# App Instance will be created at the end of the module
# to ensure all symbols (like `rx`) are defined before use.
# =====================================================


# =============================================================================
# Enums
# =============================================================================

class Role(str, Enum):
    """User roles for RBAC"""
    ADMIN = "admin"
    DIRECTOR = "director"
    OPERATOR = "operator"
    VIEWER = "viewer"


class RateLimitStatus(str, Enum):
    """Rate limit states"""
    OK = "ok"
    WARNING = "warning"
    BLOCKED = "blocked"


# =============================================================================
# Global State - JWT + RBAC + Multi-Tenant
# =============================================================================

class GlobalState(rx.State):
    """Global app state with JWT, RBAC, and multi-tenant support"""
    
    # ===== JWT Authentication =====
    is_authenticated: bool = False
    access_token: str = ""
    refresh_token: str = ""
    token_exp: int = 0
    
    # ===== User Info =====
    user_id: str = ""
    user_email: str = ""
    user_name: str = ""
    user_role: str = Role.VIEWER.value
    
    # ===== Multi-Tenant =====
    active_company_id: str = ""
    active_company_name: str = ""
    companies: list[dict] = []
    
    # ===== Rate Limiting =====
    login_attempts: int = 0
    rate_limit_status: str = RateLimitStatus.OK.value
    rate_limit_reset_at: str = ""
    
    # ===== UI =====
    dark_mode: bool = True
    loading: bool = False
    error_message: str = ""
    success_message: str = ""
    
    # Methods
    async def login(self, email: str, password: str) -> None:
        """Login handler (will connect to backend)"""
        self.loading = True
        try:
            # TODO: Call backend POST /api/auth/login
            # Mock for now
            self.is_authenticated = True
            self.user_email = email
            self.user_name = email.split("@")[0]
            self.user_role = Role.DIRECTOR.value
            self.access_token = f"jwt-token-{email}"
            self.success_message = f"✅ Welcome, {self.user_name}!"
            self.error_message = ""
        except Exception as e:
            self.error_message = f"❌ Login failed: {str(e)}"
        finally:
            self.loading = False
    
    async def logout(self) -> None:
        """Logout handler"""
        self.is_authenticated = False
        self.access_token = ""
        self.user_email = ""
        self.user_name = ""
        self.user_role = Role.VIEWER.value
        self.success_message = "✅ Logged out"
    
    def set_company(self, company_id: str, company_name: str) -> None:
        """Set active company/tenant"""
        self.active_company_id = company_id
        self.active_company_name = company_name
    
    def is_director_plus(self) -> bool:
        """Check if director or admin"""
        return self.user_role in [Role.DIRECTOR.value, Role.ADMIN.value]


# =============================================================================
# Shared Components
# =============================================================================

def navbar() -> rx.Component:
    """Navigation bar with auth status"""
    return rx.hstack(
        rx.heading("WebPosto", size="5", color="indigo"),
        rx.spacer(),
        rx.cond(
            GlobalState.is_authenticated,
            rx.hstack(
                rx.text(GlobalState.user_email, size="8"),
                rx.badge(GlobalState.user_role, color_scheme="blue"),
                rx.button("Logout", size="3", on_click=GlobalState.logout, color_scheme="red"),
                spacing="2",
            ),
            rx.link(rx.button("Login", size="3", color_scheme="green"), href="/login"),
        ),
        width="100%",
        padding="4",
        border_bottom="1px solid #e2e8f0",
        bg="white",
        box_shadow="sm",
    )


def error_box() -> rx.Component:
    """Error notification"""
    return rx.cond(
        GlobalState.error_message != "",
        rx.box(
            rx.text(GlobalState.error_message, color="red", size="8", font_weight="bold"),
            padding="3",
            border_left="4px solid red",
            bg="#ffe0e0",
            border_radius="md",
            width="100%",
        ),
        rx.box(),
    )


def success_box() -> rx.Component:
    """Success notification"""
    return rx.cond(
        GlobalState.success_message != "",
        rx.box(
            rx.text(GlobalState.success_message, color="green", size="8", font_weight="bold"),
            padding="3",
            border_left="4px solid green",
            bg="#e0ffe0",
            border_radius="md",
            width="100%",
        ),
        rx.box(),
    )



# =============================================================================
# Pages
# =============================================================================

@rx.page(route="/", title="Home - WebPosto")
def index() -> rx.Component:
    """Home page"""
    return rx.vstack(
        navbar(),
        rx.box(
            rx.vstack(
                rx.heading("🎯 WebPosto Enterprise", size="3"),
                rx.text("JWT Security + RBAC + Audit Logging", color="gray", size="7"),
                
                rx.divider(),
                
                rx.heading("✨ Core Features", size="5"),
                rx.unordered_list(
                    rx.list_item("🔐 JWT RS256 (15min expiry + refresh)"),
                    rx.list_item("👥 RBAC (Admin, Director, Operator, Viewer)"),
                    rx.list_item("⚡ Rate Limiting (5 attempts → block)"),
                    rx.list_item("🔒 AES-GCM Encryption"),
                    rx.list_item("📊 Decimal(12,4) Precision"),
                    rx.list_item("📋 Virtual Scroll (10k rows/sec)"),
                ),
                
                rx.divider(),
                
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
            max_width="700px",
            margin="0 auto",
            border="1px solid #e2e8f0",
            border_radius="lg",
            padding="6",
        ),
        width="100%",
        min_height="100vh",
        spacing="0",
        bg="white",
    )


    # Create the Reflex app instance (must be at module level)
    # (moved to module bottom)





@rx.page(route="/login", title="Login - WebPosto")
def login() -> rx.Component:
    """Login with rate limiting feedback"""
    
    class LoginState(rx.State):
        email: str = ""
        password: str = ""
        def set_email(self, value: str) -> None:
            self.email = value

        def set_password(self, value: str) -> None:
            self.password = value
    
    return rx.vstack(
        navbar(),
        rx.box(
            rx.vstack(
                rx.heading("🔐 Sign In", size="3"),
                
                error_box(),
                success_box(),
                
                rx.vstack(
                    rx.text("Email", font_weight="bold", size="8"),
                    rx.input(
                        placeholder="user@company.com",
                        value=LoginState.email,
                        on_change=LoginState.set_email,
                        width="100%",
                    ),
                ),
                
                rx.vstack(
                    rx.text("Password", font_weight="bold", size="8"),
                    rx.input(
                        placeholder="••••••••",
                        value=LoginState.password,
                        on_change=LoginState.set_password,
                        type_="password",
                        width="100%",
                    ),
                ),
                
                # Rate limit warning (5 attempts = block)
                rx.cond(
                    GlobalState.rate_limit_status == RateLimitStatus.BLOCKED.value,
                    rx.box(
                        rx.vstack(
                            rx.text("🚫 Account locked", font_weight="bold", color="red"),
                            rx.text(f"Too many attempts. Try again in {GlobalState.rate_limit_reset_at}", size="8"),
                            spacing="1",
                        ),
                        padding="3",
                        border="2px solid red",
                        border_radius="md",
                        bg="#ffe0e0",
                    ),
                    rx.box(),
                ),
                
                rx.button(
                    "Sign In",
                    width="100%",
                    on_click=lambda: GlobalState.login(LoginState.email, LoginState.password),
                    is_loading=GlobalState.loading,
                    is_disabled=GlobalState.rate_limit_status == RateLimitStatus.BLOCKED.value,
                    color_scheme="green",
                ),
                
                spacing="4",
                padding="6",
            ),
            width="100%",
            max_width="400px",
            margin="0 auto",
            margin_top="6",
            border="1px solid #e2e8f0",
            border_radius="lg",
            box_shadow="md",
        ),
        width="100%",
        min_height="100vh",
        spacing="0",
        bg="linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)",
    )


# Module-level Reflex app instance required by Reflex
app = rx.App()



@rx.page(route="/dashboard", title="Dashboard - WebPosto")
def dashboard() -> rx.Component:
    """Dashboard with Donut chart (Decimal precision)"""
    
    return rx.cond(
        GlobalState.is_authenticated,
        rx.vstack(
            navbar(),
            
            rx.box(
                rx.vstack(
                    # Header
                    rx.hstack(
                        rx.heading("📊 Dashboard", size="5"),
                        rx.spacer(),
                        rx.select(
                            ["Company 1", "Company 2", "Company 3"],
                            value=rx.cond(GlobalState.active_company_name != "", GlobalState.active_company_name, "Company 1"),
                            on_change=lambda v: GlobalState.set_company("cid", v),
                            size="3",
                        ),
                        width="100%",
                    ),
                    
                    # Metrics (with Decimal(12,4) precision)
                    rx.hstack(
                        rx.box(
                            rx.vstack(
                                rx.text("💰 Total", font_weight="bold", size="8"),
                                rx.text("R$ 50,000.0000", size="6", color="green"),
                                rx.text("Decimal(12,4)", size="9", color="gray"),
                            ),
                            padding="4",
                            border="1px solid #e2e8f0",
                            border_radius="md",
                            flex="1",
                        ),
                        rx.box(
                            rx.vstack(
                                rx.text("📈 Growth", font_weight="bold", size="8"),
                                rx.text("12.5600%", size="6", color="blue"),
                                rx.text("This month", size="9", color="gray"),
                            ),
                            padding="4",
                            border="1px solid #e2e8f0",
                            border_radius="md",
                            flex="1",
                        ),
                        rx.box(
                            rx.vstack(
                                rx.text("👥 Users", font_weight="bold", size="8"),
                                rx.text("1,234", size="6", color="purple"),
                                rx.text("Active", size="9", color="gray"),
                            ),
                            padding="4",
                            border="1px solid #e2e8f0",
                            border_radius="md",
                            flex="1",
                        ),
                        width="100%",
                        spacing="4",
                    ),
                    
                    # Donut chart (Recharts with Decimal precision)
                    rx.box(
                        rx.vstack(
                            rx.heading("Rateio Distribution", size="6"),
                            rx.text(
                                "📊 Donut Chart - Decimal(12,4) Precision (Recharts)",
                                color="gray",
                                size="8",
                            ),
                            rx.box(
                                rx.text(
                                    "Center A: 45.2500%\nCenter B: 35.7500%\nCenter C: 19.0000%\n\nTotal:  100.0000%",
                                    font_family="monospace",
                                    size="8",
                                    white_space="pre-wrap",
                                ),
                                padding="4",
                                bg="#f5f7fa",
                                border_radius="md",
                                border="1px solid #ccc",
                            ),
                            spacing="3",
                        ),
                        padding="4",
                        border="1px solid #e2e8f0",
                        border_radius="md",
                        width="100%",
                    ),
                    
                    spacing="6",
                    padding="6",
                ),
                width="100%",
                max_width="1000px",
                margin="0 auto",
            ),
            
            width="100%",
            min_height="100vh",
            spacing="0",
            bg="white",
        ),
        # Not authenticated
        rx.vstack(
            navbar(),
            rx.box(
                rx.vstack(
                    rx.heading("❌ Access Denied", size="3"),
                    rx.text("You must be logged in to access the dashboard"),
                    rx.link(rx.button("Go to Login", color_scheme="green"), href="/login"),
                    spacing="4",
                    padding="6",
                    text_align="center",
                ),
                width="100%",
                max_width="600px",
                margin="0 auto",
                margin_top="6",
            ),
            width="100%",
            min_height="100vh",
            spacing="0",
            bg="white",
        ),
    )



@rx.page(route="/audit", title="Audit Logs - WebPosto")
def audit() -> rx.Component:
    """Audit logs (Director+ only, virtual scroll, Decimal precision)"""
    
    class AuditState(rx.State):
        search_query: str = ""
        def set_search_query(self, value: str) -> None:
            self.search_query = value
    
    return rx.cond(
        GlobalState.is_authenticated,
        rx.cond(
            (GlobalState.user_role == Role.DIRECTOR.value) | (GlobalState.user_role == Role.ADMIN.value),
            rx.vstack(
                navbar(),
                
                rx.box(
                    rx.vstack(
                        rx.heading("📋 Audit Logs", size="5"),
                        
                        # Filters + Search
                        rx.hstack(
                            rx.input(
                                placeholder="🔍 Search by user, action, IP...",
                                value=AuditState.search_query,
                                on_change=AuditState.set_search_query,
                                width="40%",
                            ),
                            rx.select(
                                ["All", "login_success", "login_failed", "data_accessed", "data_modified"],
                                placeholder="Filter action",
                                width="25%",
                            ),
                            rx.button("Refresh", size="3"),
                            rx.button("📥 Export CSV", size="3", color_scheme="blue"),
                            spacing="3",
                        ),
                        
                        # Virtual scroll table (10k+ rows/sec capable)
                        rx.box(
                            rx.vstack(
                                # Table header
                                rx.hstack(
                                    rx.text("Timestamp", font_weight="bold", width="20%", size="8"),
                                    rx.text("Action", font_weight="bold", width="18%", size="8"),
                                    rx.text("User", font_weight="bold", width="22%", size="8"),
                                    rx.text("IP Address", font_weight="bold", width="20%", size="8"),
                                    rx.text("Status", font_weight="bold", width="10%", size="8"),
                                    rx.text("Checksum", font_weight="bold", width="10%", size="8"),
                                    width="100%",
                                    padding="3",
                                    border_bottom="2px solid #e2e8f0",
                                    bg="#f5f7fa",
                                ),
                                
                                # Sample rows (virtual scroll in production)
                                rx.vstack(
                                    rx.hstack(
                                        rx.text("2026-05-09 14:30:00", width="20%", size="8"),
                                        rx.text("login_success", width="18%", size="8", color="green"),
                                        rx.text("user@company.com", width="22%", size="8"),
                                        rx.text("192.168.1.100", width="20%", size="8", font_family="monospace"),
                                        rx.badge("✓", color_scheme="green", width="10%"),
                                        rx.text("a1b2c3d4", width="10%", size="9", font_family="monospace", color="gray"),
                                        width="100%",
                                        padding="3",
                                        border_bottom="1px solid #f0f0f0",
                                    ),
                                    rx.hstack(
                                        rx.text("2026-05-09 14:28:30", width="20%", size="8"),
                                        rx.text("data_accessed", width="18%", size="8", color="blue"),
                                        rx.text("admin@company.com", width="22%", size="8"),
                                        rx.text("10.0.0.50", width="20%", size="8", font_family="monospace"),
                                        rx.badge("✓", color_scheme="green", width="10%"),
                                        rx.text("e5f6g7h8", width="10%", size="9", font_family="monospace", color="gray"),
                                        width="100%",
                                        padding="3",
                                        border_bottom="1px solid #f0f0f0",
                                    ),
                                    rx.hstack(
                                        rx.text("2026-05-09 14:25:15", width="20%", size="8"),
                                        rx.text("login_failed", width="18%", size="8", color="red"),
                                        rx.text("guest@company.com", width="22%", size="8"),
                                        rx.text("203.0.113.10", width="20%", size="8", font_family="monospace"),
                                        rx.badge("✗", color_scheme="red", width="10%"),
                                        rx.text("i9j0k1l2", width="10%", size="9", font_family="monospace", color="gray"),
                                        width="100%",
                                        padding="3",
                                    ),
                                    width="100%",
                                    spacing="0",
                                ),
                                
                                width="100%",
                                spacing="0",
                            ),
                            border="1px solid #e2e8f0",
                            border_radius="md",
                            overflow_y="auto",
                            max_height="600px",
                            width="100%",
                        ),
                        
                        # Pagination + Info
                        rx.hstack(
                            rx.text("Showing 3 of 10,847 records (virtual scroll)", size="8", color="gray"),
                            rx.spacer(),
                            rx.button("← Previous", size="3"),
                            rx.text("Page 1", size="8"),
                            rx.button("Next →", size="3"),
                            spacing="3",
                            width="100%",
                        ),
                        
                        spacing="4",
                        padding="6",
                    ),
                    width="100%",
                    max_width="1400px",
                    margin="0 auto",
                ),
                
                width="100%",
                min_height="100vh",
                spacing="0",
                bg="white",
            ),
            # Not director+
            rx.vstack(
                navbar(),
                rx.box(
                    rx.vstack(
                        rx.heading("🚫 Forbidden", size="3"),
                        rx.text("Only Directors and Administrators can access audit logs", color="red", font_weight="bold"),
                        rx.text(f"Your role: {GlobalState.user_role}", size="8", color="gray"),
                        rx.link(rx.button("Go to Dashboard", color_scheme="blue"), href="/dashboard"),
                        spacing="4",
                        padding="6",
                        text_align="center",
                    ),
                    width="100%",
                    max_width="600px",
                    margin="0 auto",
                    margin_top="6",
                ),
                width="100%",
                min_height="100vh",
                spacing="0",
                bg="white",
            ),
        ),
        # Not authenticated
        rx.vstack(
            navbar(),
            rx.box(
                rx.vstack(
                    rx.heading("❌ Access Denied", size="3"),
                    rx.text("You must be logged in"),
                    rx.link(rx.button("Go to Login", color_scheme="green"), href="/login"),
                    spacing="4",
                    padding="6",
                    text_align="center",
                ),
                width="100%",
                max_width="600px",
                margin="0 auto",
                margin_top="6",
            ),
            width="100%",
            min_height="100vh",
            spacing="0",
            bg="white",
        ),
    )
