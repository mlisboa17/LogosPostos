"""
GEMINI 2.0 + CLAUDE 3.7: Reflex Configuration (v0.6+)
High-performance frontend with Turbopack and NextJS 15 runtime

Performance Targets:
- Docker image: <250MB
- Lighthouse: >95
- Hot reload: <100ms
- State update: <20ms
"""

import reflex as rx
from pathlib import Path
import os

# Project metadata
APP_NAME = "webposto"
APP_VERSION = "1.0.0"

# Explicitly set module import to root-level webposto.py
# This avoids the nested package discovery issue in Reflex v0.9
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Frontend configuration
config = rx.Config(
    app_name=APP_NAME,
    app_module_import="webposto.webposto",  # Explicitly specify module import path
    # Removido o rx.Env(mode=...) que causou o erro em Reflex 0.6+
    # db_url não é usado no frontend
    
    # GEMINI 2.0: Performance optimization
    compile_mode="prod" if not DEBUG else "dev",
    
    # Build configuration
    # Keep only optional UI libs here. Core React/Next versions are managed by Reflex.
    frontend_packages=[],
    
    # CLAUDE 3.7: State management
    state_management="reflex",  # Built-in Reflex state
    
    # API Configuration
    api_url=API_URL,
    backend_url=API_URL,
    
    # Asset optimization
    assets_dir="assets",
    
    # Telemetry (disable in production)
    telemetry_enabled=False if ENVIRONMENT == "production" else True,
)


# GEMINI 2.0: Turbopack/Webpack configuration
if hasattr(config, "next_config"):
    config.next_config = {
        "swcMinify": True,
        "compress": True,
        "productionBrowserSourceMaps": False,
        
        # Turbopack configuration
        "turbo": {
            "rules": {
                "*.svg": ["@svgr/webpack"],
            },
            "resolveAlias": {
                "@components": "./src/presentation/frontend/components",
                "@styles": "./src/presentation/frontend/styles",
                "@utils": "./src/presentation/frontend/utils",
            },
        },
        
        # Image optimization
        "images": {
            "formats": ["image/avif", "image/webp"],
            "deviceSizes": [320, 640, 750, 828, 1080, 1200, 1920, 2048, 3840],
            "imageSizes": [16, 32, 48, 64, 96, 128, 256, 384],
        },
        
        # Compression
        "compress": True,
        "gzip": True,
        "brotli": True,
        
        # Cache control
        "onDemandEntries": {
            "maxInactiveAge": 60 * 1000,  # 60 seconds
            "pagesBufferLength": 5,
        },
    }


# CLAUDE 3.7 + GROK 4: Custom webpack configuration
class CustomNextConfig:
    """Enhanced Next.js configuration for performance"""
    
    @staticmethod
    def get_webpack_config():
        return {
            "optimization": {
                "minimize": True,
                "splitChunks": {
                    "chunks": "all",
                    "cacheGroups": {
                        "default": False,
                        "vendors": False,
                        # React libraries
                        "react": {
                            "name": "react",
                            "chunks": "all",
                            "reuseExistingChunk": True,
                            "priority": 10,
                            "test": r"[\\/]node_modules[\\/](react|react-dom)[\\/]",
                        },
                        # UI libraries
                        "ui": {
                            "name": "ui",
                            "chunks": "all",
                            "reuseExistingChunk": True,
                            "priority": 20,
                            "test": r"[\\/]node_modules[\\/](radix-ui|framer-motion|recharts)[\\/]",
                        },
                        # Utilities
                        "common": {
                            "name": "common",
                            "chunks": "all",
                            "reuseExistingChunk": True,
                            "priority": 5,
                            "minChunks": 2,
                        },
                    },
                },
            },
            "module": {
                "rules": [
                    # SVG optimization
                    {
                        "test": r"\.svg$",
                        "use": [
                            {
                                "loader": "@svgr/webpack",
                                "options": {
                                    "svgo": True,
                                    "titleProp": True,
                                },
                            }
                        ],
                    },
                    # Image optimization
                    {
                        "test": r"\.(png|jpg|jpeg|gif)$",
                        "use": [
                            {
                                "loader": "image-webpack-loader",
                                "options": {
                                    "mozjpeg": {"progressive": True, "quality": 75},
                                    "optipng": {"enabled": False},
                                    "pngquant": {"quality": [0.65, 0.90], "speed": 4},
                                    "gifsicle": {"interlaced": False},
                                },
                            }
                        ],
                    },
                ]
            },
        }


# GROK 4: Theme system integration
THEME_CONFIG = {
    "colorMode": "dark",  # Default to dark mode
    "colors": {
        "primary": "#6366F1",      # Indigo
        "secondary": "#8B5CF6",    # Violet
        "success": "#10B981",      # Emerald
        "warning": "#F59E0B",      # Amber
        "danger": "#EF4444",       # Red
        "background": "#0F172A",   # Near-black slate
        "surface": "#1E293B",      # Dark slate
    },
    "typography": {
        "fontFamily": "'Inter', 'Helvetica Neue', sans-serif",
        "fontSizes": {
            "xs": "0.75rem",
            "sm": "0.875rem",
            "base": "1rem",
            "lg": "1.125rem",
            "xl": "1.25rem",
            "2xl": "1.5rem",
        },
    },
    "spacing": {
        "xs": "0.5rem",
        "sm": "1rem",
        "md": "1.5rem",
        "lg": "2rem",
        "xl": "3rem",
    },
}


# GEMINI 2.0: Runtime optimization + Redis state persistence
class PerformanceConfig:
    """Performance tuning for production with Redis state"""
    
    # Redis Connection (State Persistence)
    REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "1"))  # DB 1 for state (DB 2 is rate-limit)
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
    
    # Connection pooling
    REDIS_POOL_SIZE = 10
    REDIS_POOL_TIMEOUT = 30
    REDIS_URL = f"redis://{':' + REDIS_PASSWORD + '@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    
    # Cache settings
    CACHE_TTL_DEFAULT = 3600  # 1 hour
    CACHE_TTL_STATE = 300     # 5 minutes (user state)
    
    # Request timeouts
    API_TIMEOUT = 30  # seconds
    WEBSOCKET_TIMEOUT = 300  # 5 minutes
    
    # Rate limiting
    RATE_LIMIT_REQUESTS = 1000
    RATE_LIMIT_WINDOW = 60  # seconds

    # Backend process tuning (for production with Gunicorn + Uvicorn workers)
    BACKEND_WORKERS = int(os.getenv("BACKEND_WORKERS", "4"))
    BACKEND_THREADS = int(os.getenv("BACKEND_THREADS", "2"))
    # Example gunicorn command: gunicorn -k uvicorn.workers.UvicornWorker -w {workers} -t 30 main:app
    GUNICORN_CMD = os.getenv(
        "GUNICORN_CMD",
        "gunicorn -k uvicorn.workers.UvicornWorker -w {w} -t 30 main:app".format(w=BACKEND_WORKERS),
    )


# GEMINI 2.0: CORS Configuration (Restricted to backend)
class CORSConfig:
    """CORS settings for secure frontend-backend communication"""
    
    ALLOWED_ORIGINS = [
        os.getenv("BACKEND_URL", "http://localhost:8000"),
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
    ]
    
    if ENVIRONMENT == "production":
        ALLOWED_ORIGINS = [
            "https://api.logos.dev",
            "https://app.logos.dev",
        ]
    
    ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    ALLOWED_HEADERS = [
        "Content-Type",
        "Authorization",
        "X-CSRF-Token",
        "X-Requested-With",
    ]
    
    ALLOW_CREDENTIALS = True
    MAX_AGE = 3600  # 1 hour


# GEMINI 2.0: Asset Cache Headers
class AssetCacheConfig:
    """Cache control for static assets (Gzip + Brotli)"""
    
    CACHE_CONTROL = {
        # CSS/JS bundles (immutable after build)
        r"\.(?:js|css)$": "public, max-age=31536000, immutable",
        # Images (1 year)
        r"\.(png|jpg|jpeg|gif|webp|svg)$": "public, max-age=31536000",
        # Fonts (1 year)
        r"\.(woff|woff2|eot|ttf|otf)$": "public, max-age=31536000",
        # HTML (must revalidate)
        r"\.html$": "public, max-age=3600, must-revalidate",
        # Default
        r".*": "public, max-age=604800",  # 1 week
    }
    
    # Content encoding (Gzip + Brotli)
    COMPRESSION_FORMATS = ["br", "gzip"]  # Brotli first (better compression)
    
    # Response headers
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }


# GEMINI 2.0: Hot-reload Configuration (Development)
class HotReloadConfig:
    """Development-only hot-reload optimization"""
    
    ENABLED = DEBUG and ENVIRONMENT == "development"
    
    # Fast refresh settings
    FAST_REFRESH = True
    FAST_REFRESH_ON_EDIT = True
    
    # File watch settings
    WATCH_PATTERNS = [
        "src/presentation/frontend/**/*.py",
        "src/presentation/frontend/**/*.jsx",
        "rxconfig.py",
    ]
    
    WATCH_IGNORE_PATTERNS = [
        ".next/**/*",
        "node_modules/**/*",
        ".git/**/*",
        "__pycache__/**/*",
    ]
    
    # Rebuild debounce
    DEBOUNCE_MS = 300
    
    # Volume mount paths (Docker)
    VOLUME_MOUNTS = [
        "src/presentation/frontend:/app/src/presentation/frontend",
        "rxconfig.py:/app/rxconfig.py",
    ]
    
    # Database connection pool
    DB_POOL_SIZE = 20
    DB_POOL_RECYCLE = 3600


# Export configuration
__all__ = [
    "config",
    "THEME_CONFIG",
    "PerformanceConfig",
    "CustomNextConfig",
    "API_URL",
    "ENVIRONMENT",
    "DEBUG",
]
