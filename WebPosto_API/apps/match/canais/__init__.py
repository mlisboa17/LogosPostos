"""Canais de envio do Logos Match."""
import smtplib

import httpx


class CanalErro(Exception):
    """Falha de envio com mensagem já em português e sem segredo (pode ser mostrada)."""


def erro_envio_pt(exc: Exception) -> str:
    """Nunca usa str(exc) de exceções que não sejam CanalErro (podem carregar segredo)."""
    if isinstance(exc, CanalErro):
        return str(exc)
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "O servidor de e-mail recusou usuário/senha. Confira em Canais."
    if isinstance(exc, (smtplib.SMTPException, OSError)):
        return "Não foi possível conectar ao servidor de e-mail."
    if isinstance(exc, httpx.HTTPError):
        return "Não foi possível falar com o Telegram."
    return f"Falha inesperada no envio ({type(exc).__name__})."
