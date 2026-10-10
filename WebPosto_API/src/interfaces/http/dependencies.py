from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.cliente_service import ClienteService
from src.application.services.sync_service import SyncService
from src.infrastructure.config.database import AsyncSessionLocal
from src.infrastructure.event_bus.redis_event_bus import RedisEventBus
from src.infrastructure.repositories.cliente_repository import (
    SQLAlchemyClienteRepository,
)
from src.infrastructure.webposto.client import WebPostoClient
from src.application.usecases.extract_expenses import ExtractExpensesFromCashMovement
from fastapi import Depends, HTTPException, Request
from typing import Dict
from src.infrastructure.security.jwt_utils import decode_token
from jwt import PyJWTError


def _role(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return {
        "director": "diretor",
        "diretor": "diretor",
        "manager": "gerente",
        "gerente": "gerente",
        "auditor": "auditor",
    }.get(value.strip().casefold())


async def get_current_user(request: Request) -> Dict:
    """Dependency: extrai usuário do cookie de access token e valida."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("token_type") not in (None, "access") or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    role = _role(payload.get("role"))
    if role is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    company_id = payload.get("company_id")
    if role == "gerente" and (
        isinstance(company_id, bool) or not isinstance(company_id, int) or company_id <= 0
    ):
        raise HTTPException(status_code=401, detail="Invalid token")
    return {**payload, "role": role, "company_id": company_id}


async def get_tv_user(request: Request) -> Dict:
    token = request.cookies.get("display_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid display token") from None
    company_id = payload.get("company_id")
    if (
        payload.get("token_type") != "display"
        or payload.get("role") != "tv"
        or not payload.get("sub")
        or payload.get("scope") != "commercial:read"
        or isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise HTTPException(status_code=401, detail="Invalid display token")
    return {**payload, "role": "tv", "company_id": company_id}


async def get_commercial_user(request: Request) -> Dict:
    if request.headers.get("X-Display-Mode", "").casefold() == "true":
        return await get_tv_user(request)
    return await get_current_user(request)


def require_unit_access(user: Dict, unit: int) -> None:
    role = user.get("role")
    if role in {"diretor", "auditor"}:
        return
    if role in {"gerente", "tv"} and user.get("company_id") == unit:
        return
    raise HTTPException(status_code=403, detail="Acesso negado para esta unidade.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: Sessão do banco de dados."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_cliente_repository(
    db: AsyncSession = Depends(get_db),
) -> SQLAlchemyClienteRepository:
    """Dependency: Repositório de Clientes."""
    return SQLAlchemyClienteRepository(db)


async def get_event_bus() -> RedisEventBus:
    """Dependency: Event Bus."""
    event_bus = RedisEventBus()
    await event_bus.connect()
    return event_bus


async def get_webposto_client() -> WebPostoClient:
    """Dependency: Cliente webPosto."""
    return WebPostoClient()


async def get_cliente_service(
    repository: SQLAlchemyClienteRepository = Depends(get_cliente_repository),
    event_bus: RedisEventBus = Depends(get_event_bus),
) -> ClienteService:
    """Dependency: Serviço de Clientes."""
    return ClienteService(repository, event_bus)


async def get_sync_service(
    webposto_client: WebPostoClient = Depends(get_webposto_client),
    cliente_service: ClienteService = Depends(get_cliente_service),
    event_bus: RedisEventBus = Depends(get_event_bus),
) -> SyncService:
    """Dependency: Serviço de Sincronização."""
    return SyncService(webposto_client, cliente_service, event_bus)


async def get_extract_expenses_usecase(
    event_bus: RedisEventBus = Depends(get_event_bus),
) -> ExtractExpensesFromCashMovement:
    """Dependency: Caso de uso de extração/classificação de despesas."""
    return ExtractExpensesFromCashMovement(event_bus=event_bus)
