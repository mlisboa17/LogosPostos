import logging
from typing import Any

try:
    import structlog
except ImportError:  # pragma: no cover
    structlog = None  # type: ignore


def silenciar_urls_http() -> None:
    """Impede que httpx/httpcore registrem URLs (com CHAVE) em nivel INFO/DEBUG."""
    for nome in ("httpx", "httpcore"):
        logging.getLogger(nome).setLevel(logging.WARNING)


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configura logging estruturado com structlog."""

    # A API webPosto exige a CHAVE na query string e o httpx registra a URL completa em INFO:
    # sem isso, toda chamada vaza a chave da unidade no log (ARCH01).
    silenciar_urls_http()

    if structlog is None:
        logging.basicConfig(
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            level=getattr(logging, log_level.upper(), logging.INFO),
        )
        return

    if log_format == "json":
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
    )


def get_logger(name: str) -> Any:
    """Retorna um logger estruturado."""
    if structlog is None:
        return logging.getLogger(name)
    return structlog.get_logger(name)
