"""User registry for the existing cookie/JWT authentication flow."""
from __future__ import annotations

import hmac
import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

from src.infrastructure.config.settings import settings
from src.infrastructure.security.passwords import verify_password

AuthRole = Literal["diretor", "gerente", "auditor"]

_ROLE_ALIASES = {
    "diretor": "diretor",
    "director": "diretor",
    "gerente": "gerente",
    "manager": "gerente",
    "auditor": "auditor",
}


class AuthConfigurationError(RuntimeError):
    """Authentication settings are missing or invalid."""


class AuthUserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3)
    password_hash: str = Field(min_length=1)
    role: AuthRole
    company_id: int | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if "@" not in normalized:
            raise ValueError("Email inválido.")
        return normalized

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return _ROLE_ALIASES.get(value.strip().casefold(), value)

    @field_validator("password_hash")
    @classmethod
    def require_supported_hash(cls, value: str) -> str:
        try:
            algorithm, salt, digest = value.split("$", 2)
            bytes.fromhex(salt)
            bytes.fromhex(digest)
        except ValueError:
            raise ValueError("Hash de senha inválido.") from None
        if algorithm != "pbkdf2_sha256" or len(digest) != 64:
            raise ValueError("Hash de senha não suportado.")
        return value

    @model_validator(mode="after")
    def require_manager_unit(self) -> AuthUserConfig:
        if self.role == "gerente" and (self.company_id is None or self.company_id <= 0):
            raise ValueError("Gerente precisa de company_id válido.")
        return self


@dataclass(frozen=True)
class AuthIdentity:
    email: str
    role: AuthRole
    company_id: int | None
    password_hash: str | None = field(default=None, repr=False)
    legacy_password: str | None = field(default=None, repr=False)

    def verify(self, password: str) -> bool:
        if self.password_hash:
            return verify_password(password, self.password_hash)
        if self.legacy_password is not None:
            return hmac.compare_digest(password, self.legacy_password)
        return False


def _legacy_identity() -> AuthIdentity:
    email = settings.auth_user_email.strip().casefold()
    if "@" not in email or not (settings.auth_user_password_hash or settings.auth_user_password):
        raise AuthConfigurationError("Credenciais legadas inválidas.")
    role = _ROLE_ALIASES.get(settings.auth_user_role.strip().casefold())
    if role is None:
        raise AuthConfigurationError("Perfil do usuário legado inválido.")
    company_id = None
    if role == "gerente":
        try:
            company_id = int(settings.auth_user_company_id)
        except (TypeError, ValueError):
            raise AuthConfigurationError("Unidade do gerente legado inválida.") from None
        if company_id <= 0:
            raise AuthConfigurationError("Unidade do gerente legado inválida.")
    return AuthIdentity(
        email=email,
        role=role,
        company_id=company_id,
        password_hash=settings.auth_user_password_hash or None,
        legacy_password=settings.auth_user_password if not settings.auth_user_password_hash else None,
    )


def load_auth_users() -> tuple[AuthIdentity, ...]:
    raw = settings.auth_users_json.strip()
    if not raw:
        return (_legacy_identity(),)
    try:
        decoded = json.loads(raw)
        records = TypeAdapter(list[AuthUserConfig]).validate_python(decoded)
    except (json.JSONDecodeError, ValidationError, TypeError):
        raise AuthConfigurationError("AUTH_USERS_JSON está inválido.") from None
    if not records:
        raise AuthConfigurationError("AUTH_USERS_JSON não pode estar vazio.")
    emails = [record.email for record in records]
    if len(set(emails)) != len(emails):
        raise AuthConfigurationError("AUTH_USERS_JSON contém emails duplicados.")
    return tuple(
        AuthIdentity(
            email=record.email,
            role=record.role,
            company_id=record.company_id,
            password_hash=record.password_hash,
        )
        for record in records
    )


def authenticate_user(email: str, password: str) -> AuthIdentity | None:
    normalized = email.strip().casefold()
    for identity in load_auth_users():
        if identity.email == normalized and identity.verify(password):
            return identity
    return None


def find_auth_user(email: str) -> AuthIdentity | None:
    normalized = email.strip().casefold()
    return next((user for user in load_auth_users() if user.email == normalized), None)
