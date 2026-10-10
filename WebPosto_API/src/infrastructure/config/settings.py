from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class Settings(BaseSettings):
    """Configurações da aplicação, com dotenv carregado explicitamente."""

    # Ambiente
    environment: str = "development"
    debug: bool = True

    # webPosto API
    webposto_base_url: str = "http://web.qualityautomacao.com.br"
    webposto_api_key: str = ""
    webposto_vip_posto_id: str = "VIP"
    webposto_vip_posto_nome: str = "POSTO_VIP"
    webposto_sync_interval_seconds: int = 3600
    webposto_timeout_seconds: int = 30
    webposto_money_debug: bool = False

    # Banco de Dados
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/webposto"
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout: int = 30

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8040
    api_workers: int = 4
    api_title: str = "webPosto Service API"
    api_version: str = "0.1.0"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Security / Auth
    secret_key: str = "changeme_replace_in_env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    consumer_token: str = ""  # obrigatorio via .env; sem padrao (ARCH01)
    admin_token: str = ""  # obrigatorio via .env; sem padrao (ARCH01)
    auth_user_email: str = ""
    auth_user_password: str = ""
    auth_user_password_hash: str = ""
    auth_user_role: str = "director"
    auth_user_company_id: str = "default-company"
    auth_users_json: str = ""
    auth_cookie_secure: bool = True
    auth_tv_token_expire_hours: int = Field(default=12, ge=1, le=24)

    # Circuit Breaker
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60

    class Config:
        env_file = None
        case_sensitive = False
        extra = "ignore"


# Instância global de settings
settings = Settings()
