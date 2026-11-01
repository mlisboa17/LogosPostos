"""Envio pelo Telegram (reaproveita o adaptador compartilhado)."""
from __future__ import annotations

import json
from pathlib import Path

from apps.match import credenciais
from apps.match.canais import CanalErro
from src.shared.notificacao import telegram as tg


def enviar(
    canal,
    texto: str,
    anexo: Path | None,
    cliente=None,
    botoes: list[tuple[str, str]] | None = None,
) -> None:
    token = credenciais.ler(f"canal/{canal['id']}/token")
    chat_ids = json.loads(canal["config_json"]).get("chat_ids") or []
    if not token or not chat_ids:
        raise CanalErro("Telegram sem token ou sem conversa configurada. Confira em Canais de envio.")
    reply_markup = None
    if botoes:
        reply_markup = {
            "inline_keyboard": [[
                {"text": rotulo, "callback_data": callback_data}
                for rotulo, callback_data in botoes
            ]]
        }
    resultados = tg.enviar_mensagem(
        texto, token=token, chat_ids=chat_ids, cliente=cliente, reply_markup=reply_markup
    )
    if anexo is not None:
        resultados += tg.enviar_documento(anexo, "Planilha do dia", token=token,
                                          chat_ids=chat_ids, cliente=cliente)
    if not resultados or not all(r is not None and r.sucesso for r in resultados):
        raise CanalErro("O Telegram recusou o envio. Confira o token e se o robô está na conversa.")
