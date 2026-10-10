import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel
from jwt import PyJWTError

from src.infrastructure.config.settings import settings
from src.infrastructure.security.jwt_utils import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.infrastructure.security.auth_users import (
    AuthConfigurationError,
    AuthNotConfiguredError,
    authenticate_user,
    find_auth_user,
)
from src.interfaces.http.dependencies import get_current_user
from src.modules.commercial_performance.config import POSTOS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    email: str
    password: str


def _access_token(email: str, role: str, company_id: int | None) -> str:
    return create_access_token(
        email,
        extra={"role": role, "company_id": company_id, "token_type": "access"},
    )


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=60 * settings.access_token_expire_minutes,
        path="/",
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "refresh_token",
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=60 * 60 * 24 * settings.refresh_token_expire_days,
        path="/auth/refresh",
    )


def _public_user(email: str, role: str, company_id: int | None) -> dict[str, object]:
    return {"sub": email, "email": email, "role": role, "company_id": company_id}


@router.post("/login")
async def login(payload: LoginPayload, response: Response):
    """Validate credentials and issue HttpOnly access/refresh cookies."""
    try:
        user = authenticate_user(payload.email, payload.password)
    except AuthNotConfiguredError:
        logger.warning("Login recusado: nenhuma credencial foi configurada.")
        raise HTTPException(status_code=503, detail="Login não configurado.") from None
    except AuthConfigurationError:
        logger.error("Cadastro de autenticação inválido.")
        raise HTTPException(status_code=503, detail="Autenticação indisponível.") from None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = _access_token(user.email, user.role, user.company_id)
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, create_refresh_token(user.email))
    return {
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": _public_user(user.email, user.role, user.company_id),
    }


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = decode_token(refresh_token)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None
    if payload.get("token_type") not in (None, "refresh"):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    subject = payload.get("sub")
    try:
        user = find_auth_user(subject) if isinstance(subject, str) else None
    except AuthConfigurationError:
        logger.error("Cadastro de autenticação inválido.")
        raise HTTPException(status_code=503, detail="Autenticação indisponível.") from None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    _set_access_cookie(response, _access_token(user.email, user.role, user.company_id))
    return {"user": _public_user(user.email, user.role, user.company_id)}


class DisplayTokenPayload(BaseModel):
    unidade: int


@router.post("/tv-token")
async def create_display_token(
    payload: DisplayTokenPayload,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    if current_user["role"] != "diretor":
        raise HTTPException(status_code=403, detail="Somente diretor pode emitir token de exibição.")
    if payload.unidade not in POSTOS:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
    token = create_access_token(
        f"tv:{payload.unidade}",
        extra={
            "token_type": "display",
            "role": "tv",
            "company_id": payload.unidade,
            "scope": "commercial:read",
        },
        expires_delta=timedelta(hours=settings.auth_tv_token_expire_hours),
    )
    response.set_cookie(
        "display_token",
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_tv_token_expire_hours * 60 * 60,
        path="/api/v1/commercial",
    )
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")
    return {"unidade": payload.unidade, "expires_in": settings.auth_tv_token_expire_hours * 60 * 60}


@router.get("/me")
async def get_session(current_user: dict = Depends(get_current_user)):
    return _public_user(
        str(current_user["sub"]),
        str(current_user["role"]),
        current_user.get("company_id"),
    )


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")
    response.delete_cookie("display_token", path="/api/v1/commercial")
    return {"ok": True}
