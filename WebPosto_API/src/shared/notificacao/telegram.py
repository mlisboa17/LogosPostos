"""Adaptador genérico para envio de mensagens pelo Telegram."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx

API_BASE = "https://api.telegram.org"
TIMEOUT_SEGUNDOS = 15.0
TENTATIVAS = 2


@dataclass(frozen=True)
class ResultadoDestinatario:
    chat_id: str
    sucesso: bool
    status_http: int | None = None
    tipo_erro: str | None = None


def _resposta_telegram_ok(resposta: httpx.Response) -> tuple[bool, str | None]:
    try:
        payload = resposta.json()
    except ValueError:
        return False, "JSONDecodeError"
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return False, "TelegramResponseError"
    return True, None


def enviar_mensagem(
    texto: str,
    *,
    token: str,
    chat_ids: Iterable[str | int],
    cliente: httpx.Client | None = None,
    parse_mode: str | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> list[ResultadoDestinatario]:
    resultados = []
    ids = list(dict.fromkeys(str(chat_id).strip() for chat_id in chat_ids if str(chat_id).strip()))
    proprio_cliente = cliente is None
    http = cliente or httpx.Client(timeout=TIMEOUT_SEGUNDOS)
    try:
        for chat_id in ids:
            resultado = None
            for _ in range(TENTATIVAS):
                try:
                    payload: dict[str, Any] = {
                        "chat_id": chat_id,
                        "text": texto,
                    }
                    if parse_mode:
                        payload["parse_mode"] = parse_mode
                    if reply_markup:
                        payload["reply_markup"] = reply_markup
                    resposta = http.post(
                        f"{API_BASE}/bot{token}/sendMessage",
                        json=payload,
                        timeout=TIMEOUT_SEGUNDOS,
                    )
                except httpx.HTTPError as exc:
                    resultado = ResultadoDestinatario(
                        chat_id=chat_id,
                        sucesso=False,
                        tipo_erro=type(exc).__name__,
                    )
                    continue
                if resposta.status_code != 200:
                    resultado = ResultadoDestinatario(
                        chat_id=chat_id,
                        sucesso=False,
                        status_http=resposta.status_code,
                        tipo_erro="HTTPStatusError",
                    )
                    continue
                sucesso, erro = _resposta_telegram_ok(resposta)
                if sucesso:
                    resultado = ResultadoDestinatario(
                        chat_id=chat_id,
                        sucesso=True,
                        status_http=resposta.status_code,
                    )
                    break
                resultado = ResultadoDestinatario(
                    chat_id=chat_id,
                    sucesso=False,
                    status_http=resposta.status_code,
                    tipo_erro=erro,
                )
            resultados.append(resultado)
    finally:
        if proprio_cliente:
            http.close()
    return resultados


def enviar_documento(
    caminho: Path,
    legenda: str,
    *,
    token: str,
    chat_ids: Iterable[str | int],
    cliente: httpx.Client | None = None,
) -> list[ResultadoDestinatario]:
    resultados = []
    ids = list(dict.fromkeys(str(chat_id).strip() for chat_id in chat_ids if str(chat_id).strip()))
    proprio_cliente = cliente is None
    http = cliente or httpx.Client(timeout=TIMEOUT_SEGUNDOS)
    try:
        for chat_id in ids:
            resultado = None
            for _ in range(TENTATIVAS):
                try:
                    with Path(caminho).open("rb") as documento:
                        resposta = http.post(
                            f"{API_BASE}/bot{token}/sendDocument",
                            data={"chat_id": chat_id, "caption": legenda},
                            files={
                                "document": (
                                    Path(caminho).name,
                                    documento,
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                )
                            },
                            timeout=TIMEOUT_SEGUNDOS,
                        )
                except httpx.HTTPError as exc:
                    resultado = ResultadoDestinatario(
                        chat_id=chat_id,
                        sucesso=False,
                        tipo_erro=type(exc).__name__,
                    )
                    continue
                except OSError as exc:
                    resultado = ResultadoDestinatario(
                        chat_id=chat_id,
                        sucesso=False,
                        tipo_erro=type(exc).__name__,
                    )
                    break
                if resposta.status_code != 200:
                    resultado = ResultadoDestinatario(
                        chat_id=chat_id,
                        sucesso=False,
                        status_http=resposta.status_code,
                        tipo_erro="HTTPStatusError",
                    )
                    continue
                sucesso, erro = _resposta_telegram_ok(resposta)
                if sucesso:
                    resultado = ResultadoDestinatario(
                        chat_id=chat_id,
                        sucesso=True,
                        status_http=resposta.status_code,
                    )
                    break
                resultado = ResultadoDestinatario(
                    chat_id=chat_id,
                    sucesso=False,
                    status_http=resposta.status_code,
                    tipo_erro=erro,
                )
            resultados.append(resultado)
    finally:
        if proprio_cliente:
            http.close()
    return resultados
