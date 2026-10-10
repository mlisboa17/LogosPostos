"""Adaptador genérico para envio de mensagens pelo Telegram."""

from __future__ import annotations

from dataclasses import dataclass
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


def enviar_mensagem(
    texto: str,
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
                    resposta = http.post(
                        f"{API_BASE}/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": texto},
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
                try:
                    sucesso = resposta.json().get("ok") is True
                except ValueError:
                    sucesso = False
                    erro = "JSONDecodeError"
                else:
                    erro = "TelegramResponseError"
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
