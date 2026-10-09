"""Tempo compartilhado em Recife; transporte permanece ISO 8601."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from time import time
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AfterValidator

FUSO = ZoneInfo("America/Recife")


def agora() -> datetime:
    return datetime.fromtimestamp(time(), FUSO)


def hoje() -> date:
    return agora().date()


def ontem() -> date:
    return hoje() - timedelta(days=1)


def para_local(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=FUSO)
    return dt.astimezone(FUSO)


def ler_data_hora(texto: str) -> datetime:
    return para_local(datetime.fromisoformat(texto.replace("Z", "+00:00")))


DataHoraLocal = Annotated[datetime, AfterValidator(para_local)]


def formatar_data(d: date) -> str:
    local = para_local(d).date() if isinstance(d, datetime) else d
    return local.strftime("%d/%m/%Y")


def formatar_hora(dt: datetime) -> str:
    return para_local(dt).strftime("%H:%M")


def formatar_data_hora(dt: datetime) -> str:
    return para_local(dt).strftime("%d/%m/%Y %H:%M")


def ler_data(texto: str) -> date:
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            resultado = datetime.strptime(texto, formato).date()
        except ValueError:
            continue
        if resultado.strftime(formato) == texto:
            return resultado
    raise ValueError("Data inválida. Use dd/mm/aaaa ou aaaa-mm-dd.")
