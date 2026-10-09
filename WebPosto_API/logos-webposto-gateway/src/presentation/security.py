import hmac
import os
from typing import Annotated, Optional

from fastapi import Header, HTTPException


def _validar(recebido: Optional[str], variavel: str, erro: str) -> None:
    # Sem valor padrao: token nao configurado recusa o acesso (antes aceitava "dev-*-token", publico no Git).
    esperado = (os.getenv(variavel) or "").strip()
    if not esperado:
        raise HTTPException(status_code=503, detail=f"{variavel.lower()}_nao_configurado")
    if not recebido or not hmac.compare_digest(recebido.encode(), esperado.encode()):
        raise HTTPException(status_code=401, detail=erro)


def require_consumer_token(
    x_consumer_token: Annotated[Optional[str], Header(alias="X-Consumer-Token")] = None,
) -> None:
    _validar(x_consumer_token, "CONSUMER_TOKEN", "consumer_unauthorized")


def require_admin_token(
    x_admin_token: Annotated[Optional[str], Header(alias="X-Admin-Token")] = None,
) -> None:
    _validar(x_admin_token, "ADMIN_TOKEN", "admin_unauthorized")
