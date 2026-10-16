"""Worker e CLI para recepção de comprovantes pelo Telegram (Parte B).

Uso:
    python -m src.jobs.receber_comprovantes --escutar
    python -m src.jobs.receber_comprovantes --uma-vez
    python -m src.jobs.receber_comprovantes --arquivo caminho/comprovante.jpg --texto "paguei ao pedreiro"
    python -m src.jobs.receber_comprovantes --listar-fila
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Carrega .env exclusivamente via load_dotenv (nunca imprimir nem editar)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.modules.cash_reconciliation.application.fila_despesas import carregar_fila
from src.modules.cash_reconciliation.application.processar_comprovante import (
    processar_comprovante_recebido,
)
from src.shared.notificacao.telegram import API_BASE, enviar_mensagem

logger = logging.getLogger(__name__)


def _obter_chat_ids_diretor() -> set[str]:
    """Retorna o conjunto de IDs de chat autorizados do diretor."""
    raw = os.getenv("TELEGRAM_CHAT_IDS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


async def _baixar_arquivo_telegram(
    token: str,
    file_id: str,
    client: httpx.AsyncClient,
) -> tuple[bytes, str]:
    """Obtém os bytes e o nome do arquivo a partir de file_id do Telegram."""
    resp = await client.get(f"{API_BASE}/bot{token}/getFile?file_id={file_id}", timeout=20.0)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok"):
        raise ValueError(f"Telegram getFile erro: {payload}")

    file_path = payload["result"]["file_path"]
    download_url = f"{API_BASE}/file/bot{token}/{file_path}"
    resp_dl = await client.get(download_url, timeout=30.0)
    resp_dl.raise_for_status()
    return resp_dl.content, Path(file_path).name


async def processar_atualizacao_telegram(
    atualizacao: dict[str, Any],
    token: str,
    chat_ids_autorizados: set[str],
    client: httpx.AsyncClient,
) -> bool:
    """Processa uma única mensagem vinda do Telegram."""
    callback = atualizacao.get("callback_query")
    if callback and str(callback.get("data", "")).startswith("cartao:"):
        from src.modules.cash_reconciliation.adapters.telegram_cartoes import atender_callback
        return await atender_callback(callback, token=token, client=client)
    msg = atualizacao.get("message") or atualizacao.get("edited_message")
    if not msg:
        return False
    from src.modules.cash_reconciliation.adapters.telegram_cartoes import eh_mensagem_mais, atender_mais_pagamentos
    if eh_mensagem_mais(msg):
        return await atender_mais_pagamentos(msg, token=token, client=client)

    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))
    msg_id = msg.get("message_id")

    # 1. Filtro estrito: somente chat do diretor (chat_id autorizado)
    if chat_id not in chat_ids_autorizados:
        logger.warning("Mensagem ignorada de chat não autorizado: %s", chat_id)
        return False

    texto = msg.get("text") or msg.get("caption") or ""
    reply_to = msg.get("reply_to_message", {}).get("message_id")

    arquivo_bytes: bytes | None = None
    nome_arquivo: str | None = None
    mime_type: str | None = None
    audio_bytes: bytes | None = None

    # Verifica tipo de anexo
    if "photo" in msg and msg["photo"]:
        # Pega a foto de maior resolução (último item da lista)
        foto_maior = msg["photo"][-1]
        file_id = foto_maior["file_id"]
        arquivo_bytes, nome_arquivo = await _baixar_arquivo_telegram(token, file_id, client)
        mime_type = "image/jpeg"
    elif "document" in msg:
        doc = msg["document"]
        file_id = doc["file_id"]
        nome_arquivo = doc.get("file_name", "comprovante.pdf")
        mime_type = doc.get("mime_type", "application/pdf")
        arquivo_bytes, _ = await _baixar_arquivo_telegram(token, file_id, client)
    elif "voice" in msg:
        voice = msg["voice"]
        file_id = voice["file_id"]
        audio_bytes, _ = await _baixar_arquivo_telegram(token, file_id, client)
        nome_arquivo = "audio.ogg"
        mime_type = "audio/ogg"
    elif "audio" in msg:
        audio = msg["audio"]
        file_id = audio["file_id"]
        audio_bytes, _ = await _baixar_arquivo_telegram(token, file_id, client)
        nome_arquivo = audio.get("file_name", "audio.ogg")
        mime_type = audio.get("mime_type", "audio/ogg")

    if not arquivo_bytes and not audio_bytes and not texto:
        return False

    print(f"\n[Telegram] Processando mensagem do diretor (chat {chat_id}, msg {msg_id})...")

    # Orquestra extração, casamento com extratos e persistência na fila local
    item = await processar_comprovante_recebido(
        arquivo_bytes=arquivo_bytes,
        nome_arquivo=nome_arquivo,
        mime_type=mime_type,
        texto=texto,
        audio_bytes=audio_bytes,
        telegram_message_id=msg_id,
        telegram_reply_to_message_id=reply_to,
        telegram_chat_id=chat_id,
    )

    print(f"[Telegram] Resultado: {item.status.upper()}")
    print(f"[Telegram] Resposta: {item.resposta_bot}\n")

    # Envia resposta de volta ao diretor pelo Telegram
    enviar_mensagem(item.resposta_bot, token=token, chat_ids=[chat_id])
    return True


async def executar_polling(
    token: str,
    chat_ids_autorizados: set[str],
    uma_vez: bool = False,
    intervalo: float = 2.0,
) -> None:
    """Escuta mensagens do bot via getUpdates."""
    print("Iniciando escuta de comprovantes pelo Telegram (somente chat do diretor)...")
    print(f"Diretor autorizado: {chat_ids_autorizados or 'NENHUM (defina TELEGRAM_CHAT_IDS no .env)'}")
    print("Pressione Ctrl+C para encerrar.\n")

    offset = None
    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            try:
                url = f"{API_BASE}/bot{token}/getUpdates?timeout=20"
                if offset:
                    url += f"&offset={offset}"
                resp = await client.get(url, params={
                    "allowed_updates": json.dumps(["message", "edited_message", "callback_query"]),
                })
                if resp.status_code == 200:
                    payload = resp.json()
                    resultados = payload.get("result", [])
                    for at in resultados:
                        offset = at["update_id"] + 1
                        await processar_atualizacao_telegram(
                            at,
                            token=token,
                            chat_ids_autorizados=chat_ids_autorizados,
                            client=client,
                        )
                elif resp.status_code != 409:
                    logger.warning("getUpdates status HTTP %s", resp.status_code)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Erro no loop de polling Telegram: %s", exc)

            if uma_vez:
                break
            await asyncio.sleep(intervalo)


async def processar_arquivo_local(caminho: Path, texto: str = "") -> None:
    """Permite testar a extração e fila diretamente com um arquivo local."""
    if not caminho.is_file():
        print(f"Erro: arquivo {caminho} não encontrado.", file=sys.stderr)
        return

    conteudo = caminho.read_bytes()
    ext = caminho.suffix.lower()
    is_audio = ext in (".ogg", ".mp3", ".wav", ".m4a")
    is_pdf = ext == ".pdf"
    mime = "audio/ogg" if is_audio else ("application/pdf" if is_pdf else "image/jpeg")

    print(f"Processando arquivo local: {caminho.name} ({mime})...")
    item = await processar_comprovante_recebido(
        arquivo_bytes=None if is_audio else conteudo,
        nome_arquivo=caminho.name,
        mime_type=None if is_audio else mime,
        texto=texto,
        audio_bytes=conteudo if is_audio else None,
    )

    print("\n" + "=" * 80)
    print("ITEM PROCESSADO E GRAVADO NA FILA LOCAL (fila.json):")
    print("=" * 80)
    print(f"ID:           {item.id}")
    print(f"Status:       {item.status.upper()}")
    print(f"Valor:        {item.comprovante.valor}")
    print(f"Favorecido:   {item.comprovante.favorecido}")
    print(f"Data:         {item.comprovante.data}")
    print(f"Unidade:      {item.unidade_nome} ({item.unidade_codigo})")
    print(f"Extrato FITID:{item.debito_casado_fitid or 'Aguardando extrato'}")
    print(f"Sugestão:     {item.sugestao_plano_nome} ({item.sugestao_plano_codigo}) | CC: {item.sugestao_centro_nome}")
    print("-" * 80)
    print(f"Resposta Bot: {item.resposta_bot}")
    print("=" * 80)
    print("STATUS: SOMENTE LEITURA (Nenhuma alteração foi realizada no webPosto)\n")


def listar_fila() -> None:
    """Exibe todos os itens da fila local."""
    itens = carregar_fila()
    print("\n" + "=" * 90)
    print(f"FILA LOCAL DE DESPESAS AVULSAS (data/despesas_avulsas/fila.json) — {len(itens)} itens")
    print("=" * 90)
    if not itens:
        print("A fila está vazia no momento.")
    for i, it in enumerate(itens, 1):
        v_str = f"R$ {it.comprovante.valor:,.2f}" if it.comprovante.valor else "R$ ?"
        dt_str = it.comprovante.data.strftime("%d/%m/%Y") if it.comprovante.data else "?"
        plano_str = f"{it.sugestao_plano_nome} ({it.sugestao_plano_codigo})" if it.sugestao_plano_codigo else it.sugestao_plano_nome
        ext_str = f"FITID: {it.debito_casado_fitid} ({it.debito_casado_banco})" if it.debito_casado_fitid else "Sem extrato"
        print(
            f"{i:2d}. [{it.status.upper()}] {dt_str} | {v_str:>10} | {it.unidade_apelido:<6} | "
            f"Favorecido: {it.comprovante.favorecido:<25} | Plano: {plano_str}"
        )
        print(f"    Extrato: {ext_str} | Comprovante: {it.arquivo_comprovante or 'nenhum'}")
    print("=" * 90 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recepção e processamento de comprovantes via Telegram (somente fila local)."
    )
    parser.add_argument("--escutar", action="store_true", help="Inicia polling contínuo de mensagens do Telegram")
    parser.add_argument("--uma-vez", action="store_true", help="Verifica atualizações uma única vez e sai")
    parser.add_argument("--arquivo", type=str, help="Processa arquivo local (foto, PDF ou áudio) para teste")
    parser.add_argument("--texto", type=str, default="", help="Texto ou observação complementar para teste de arquivo local")
    parser.add_argument("--listar-fila", action="store_true", help="Lista os itens da fila local data/despesas_avulsas/fila.json")

    args = parser.parse_args()

    if args.listar_fila:
        listar_fila()
        return

    if args.arquivo:
        asyncio.run(processar_arquivo_local(Path(args.arquivo), texto=args.texto))
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = _obter_chat_ids_diretor()

    if args.escutar or args.uma_vez:
        if not token:
            print("Erro: TELEGRAM_BOT_TOKEN não configurado no .env.", file=sys.stderr)
            sys.exit(1)
        asyncio.run(executar_polling(token=token, chat_ids=chat_ids, uma_vez=args.uma_vez))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
