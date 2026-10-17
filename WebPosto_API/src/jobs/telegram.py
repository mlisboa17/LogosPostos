"""Comandos explícitos de descoberta, teste e reenvio de resumo local."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import date, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from src.shared.notificacao.telegram import API_BASE, enviar_mensagem
from src.modules.cash_reconciliation.adapters.saude_robo import caminho_resumo
from src.modules.cash_reconciliation.application.resumo_diario import dividir_resumo


def _dia_resumo(valor: str) -> date:
    try:
        dia = datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError:
        raise argparse.ArgumentTypeError("Informe uma data válida no formato dd/mm/aaaa.") from None
    if valor != dia.strftime("%d/%m/%Y"):
        raise argparse.ArgumentTypeError("Informe a data no formato dd/mm/aaaa.")
    return dia


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
    grupo.add_argument("--propostas-cartao", action="store_true", help="Envia propostas somente ao diretor")
    grupo.add_argument("--ouvir-cartoes", action="store_true", help="Processa os botões privados do diretor")
    parser.add_argument("--unidade", type=int)
    parser.add_argument("--dia", type=_dia_resumo)
    grupo.add_argument(
        "--reenviar-resumo", type=_dia_resumo, metavar="dd/mm/aaaa",
        help="Reenvia somente o resumo local gravado; executar apenas após o ok do diretor.",
    )
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    for nome in ("httpx", "httpcore"):
        logging.getLogger(nome).setLevel(logging.WARNING)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        parser.error("Defina TELEGRAM_BOT_TOKEN no arquivo .env.")
    if args.propostas_cartao or args.ouvir_cartoes:
        from src.modules.cash_reconciliation.adapters import telegram_cartoes
        from src.modules.cash_reconciliation.adapters.webposto_http import WebPostoErro
        if args.propostas_cartao and (args.unidade is None or args.dia is None):
            parser.error("--propostas-cartao exige --unidade e --dia.")
        try:
            if args.propostas_cartao:
                asyncio.run(telegram_cartoes.enviar_propostas(args.unidade, args.dia, token=token))
                print("Propostas enviadas somente à conversa privada do diretor.")
            else:
                asyncio.run(telegram_cartoes.ouvir(token=token))
        except (ValueError, OSError, WebPostoErro) as exc:
            print(f"Operação interrompida: {exc}")
            return 1
        return 0

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
        encontrados = 0
        for atualizacao in payload.get("resultados", payload.get("result", [])):
            mensagem = atualizacao.get("message") or atualizacao.get("edited_message") or {}
            remetente = mensagem.get("from") or {}
            if remetente.get("id") is not None:
                encontrados += 1
                print(f"{remetente['id']} {remetente.get('first_name', '')}".rstrip())
        if not encontrados:
            print("Token ok, mas o bot ainda não recebeu mensagem. Mande /start e um 'oi' ao bot e rode de novo.")
        return 0

    try:
        ids = _chat_ids()
    except ValueError as exc:
        parser.error(str(exc))
    mensagens = ["LOGOS — teste de envio"]
    if args.reenviar_resumo is not None:
        try:
            resumo = caminho_resumo(args.reenviar_resumo).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"Falha ao ler o resumo gravado ({type(exc).__name__}). Nenhum envio realizado.")
            return 1
        if not resumo.strip():
            print("Resumo gravado vazio. Nenhum envio realizado.")
            return 1
        mensagens = dividir_resumo(
            "<b>LOGOS — REENVIO HISTÓRICO</b>\n"
            f"Referência: {args.reenviar_resumo:%d/%m/%Y}\n"
            "Arquivo local; execução original não revalidada. "
            "Este reenvio não representa nova coleta ou auditoria atual.\n\n" + resumo
        )
    for mensagem in mensagens:
        envio = enviar_mensagem(
            mensagem, token=token, chat_ids=ids,
            parse_mode="HTML" if args.reenviar_resumo is not None else None,
        )
        if not envio:
            print("Telegram envio=falhou motivo=sem destinatários; envio interrompido.")
            return 1
        falha = next((resultado for resultado in envio if not resultado.sucesso), None)
        if falha is not None:
            detalhe = f"HTTP {falha.status_http}" if falha.status_http is not None else falha.tipo_erro
            print(f"Telegram envio=falhou motivo={detalhe or 'erro desconhecido'}; envio interrompido.")
            return 1
    print(f"Telegram envio=ok destinatarios={len(ids)} mensagens={len(mensagens)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
