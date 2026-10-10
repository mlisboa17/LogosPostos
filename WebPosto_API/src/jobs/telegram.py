"""Comandos explícitos de descoberta do chat e teste do bot Telegram."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from src.shared.notificacao.telegram import API_BASE, enviar_mensagem


def _chat_ids() -> list[str]:
    valores = [item.strip() for item in os.getenv("TELEGRAM_CHAT_IDS", "").split(",")]
    ids = list(dict.fromkeys(item for item in valores if item))
    if not ids:
        raise ValueError("Defina TELEGRAM_CHAT_IDS no arquivo .env.")
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Utilitários explícitos do bot Telegram.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--descobrir-chat", action="store_true")
    grupo.add_argument("--teste", action="store_true")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    for nome in ("httpx", "httpcore"):
        logging.getLogger(nome).setLevel(logging.WARNING)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        parser.error("Defina TELEGRAM_BOT_TOKEN no arquivo .env.")

    if args.descobrir_chat:
        try:
            resposta = httpx.get(
                f"{API_BASE}/bot{token}/getUpdates",
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            print(f"Falha ao consultar Telegram ({type(exc).__name__}).")
            return 1
        if resposta.status_code != 200:
            print(f"Falha ao consultar Telegram (HTTP {resposta.status_code}).")
            return 1
        try:
            payload = resposta.json()
        except ValueError:
            print("Falha ao interpretar a resposta do Telegram.")
            return 1
        if payload.get("ok") is not True:
            print("Falha ao consultar Telegram (resposta inválida).")
            return 1
        for atualizacao in payload.get("resultados", payload.get("result", [])):
            mensagem = atualizacao.get("message") or atualizacao.get("edited_message") or {}
            remetente = mensagem.get("from") or {}
            if remetente.get("id") is not None:
                print(f"{remetente['id']} {remetente.get('first_name', '')}".rstrip())
        return 0

    try:
        ids = _chat_ids()
    except ValueError as exc:
        parser.error(str(exc))
    resultados = enviar_mensagem("LOGOS — teste de envio", token=token, chat_ids=ids)
    if all(resultado.sucesso for resultado in resultados):
        print(f"Telegram envio=ok destinatarios={len(resultados)}")
        return 0
    falha = next(resultado for resultado in resultados if not resultado.sucesso)
    detalhe = f"HTTP {falha.status_http}" if falha.status_http is not None else falha.tipo_erro
    print(f"Telegram envio=falhou motivo={detalhe or 'erro desconhecido'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
