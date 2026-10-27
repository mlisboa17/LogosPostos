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
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import pages to register them with the app
from . import pages  # noqa: F401

# Import Executive Hub
from src.presentation.pages.hub_shell import hub_page  # noqa: F401


# =============================================================================
# App
# =============================================================================

# Create app
app = rx.App()

# This will auto-discover pages decorated with @rx.page()

