"""Propostas privadas e callbacks do diretor; nunca inicia envio ao importar."""
from __future__ import annotations

import secrets
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import httpx

from .webposto_escrita_cartao import BarreiraCartaoErro, ler_travas
from ..application import piloto_cartao
from ..domain.tempo import agora
from src.shared.notificacao.telegram import API_BASE

BANCO = Path(__file__).resolve().parents[4] / "data" / "lancamentos_logos" / "telegram.sqlite3"


def diretor(caminho_env=None) -> tuple[str, str]:
    valores = ler_travas(caminho_env)
    ids = []
    for nome in ("TELEGRAM_DIRETOR_CHAT_ID", "TELEGRAM_DIRETOR_USER_ID"):
        linhas = valores[nome]
        if len(linhas) != 1 or not linhas[0][1] or not linhas[0][1].isdigit():
            raise BarreiraCartaoErro("Configure uma única conversa privada e usuário do diretor no .env.")
        ids.append(linhas[0][1])
    if ids[0] != ids[1]:
        raise BarreiraCartaoErro("A aprovação exige a conversa privada do próprio diretor.")
    return ids[0], ids[1]


def _conectar(banco: Path):
    banco.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(banco, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS propostas (
        ticket TEXT PRIMARY KEY, unidade INTEGER NOT NULL, dia TEXT NOT NULL,
        acao_id TEXT NOT NULL, expira TEXT NOT NULL, estado TEXT NOT NULL)""")
    return con


async def _api(http, token, metodo, dados):
    try:
        resp = await http.post(f"{API_BASE}/bot{token}/{metodo}", json=dados)
        if resp.status_code != 200 or resp.json().get("ok") is not True:
            raise piloto_cartao.PilotoErro("Telegram recusou a operação; confira o envio.")
        return resp.json().get("result")
    except (httpx.HTTPError, ValueError) as exc:
        raise piloto_cartao.PilotoErro("Falha ao consultar Telegram; não vou repetir o lançamento.") from exc


async def enviar_propostas(unidade, dia, *, token, caminho_env=None, banco=None, client=None):
    chat, _ = diretor(caminho_env)
    propostas = await piloto_cartao.preparar(unidade, dia)
    http = client or httpx.AsyncClient(timeout=40)
    try:
        for p in propostas:
            dados = {"chat_id": chat, "text": p.texto}
            if p.elegivel:
                ticket = secrets.token_hex(12)
                with _conectar(banco or BANCO) as con:
                    con.execute("INSERT INTO propostas VALUES (?,?,?,?,?,?)",
                                (ticket, unidade, str(dia), p.id, (agora() + timedelta(hours=24)).isoformat(), "pendente"))
                dados["reply_markup"] = {"inline_keyboard": [[
                    {"text": "Lançar", "callback_data": f"cartao:s:{ticket}"},
                    {"text": "Não lançar", "callback_data": f"cartao:n:{ticket}"},
                ]]}
            await _api(http, token, "sendMessage", dados)
    finally:
        if client is None:
            await http.aclose()


async def processar_callback(callback, *, caminho_env=None, banco=None):
    chat, usuario = diretor(caminho_env)
    mensagem = callback.get("message") or {}
    conversa = mensagem.get("chat") or {}
    if (str(conversa.get("id")) != chat or conversa.get("type") != "private"
            or str((callback.get("from") or {}).get("id")) != usuario):
        raise piloto_cartao.PilotoErro("Aprovação permitida somente ao diretor na conversa privada.")
    partes = (callback.get("data") or "").split(":")
    if len(partes) != 3 or partes[0] != "cartao" or partes[1] not in {"s", "n"}:
        raise piloto_cartao.PilotoErro("Botão inválido.")
    with _conectar(banco or BANCO) as con:
        con.execute("BEGIN IMMEDIATE")
        registro = con.execute("SELECT * FROM propostas WHERE ticket=?", (partes[2],)).fetchone()
        if not registro or registro["estado"] != "pendente" or registro["expira"] < agora().isoformat():
            raise piloto_cartao.PilotoErro("Esta proposta expirou ou já foi decidida. Consulte o painel.")
        con.execute("UPDATE propostas SET estado='executando' WHERE ticket=?", (partes[2],))
    try:
        resultado = await piloto_cartao.decidir(
            registro["unidade"], date.fromisoformat(registro["dia"]), registro["acao_id"],
            "aprovar" if partes[1] == "s" else "recusar", autor=f"diretor:telegram:{usuario}",
            caminho_env=caminho_env,
        )
    except (ValueError, OSError, piloto_cartao.WebPostoErro):
        with _conectar(banco or BANCO) as con:
            con.execute("UPDATE propostas SET estado='erro' WHERE ticket=?", (partes[2],))
        raise
    with _conectar(banco or BANCO) as con:
        con.execute("UPDATE propostas SET estado=? WHERE ticket=?", (resultado["estado"], partes[2]))
    return resultado


async def atender_callback(callback, *, token, client, caminho_env=None):
    try:
        resultado = await processar_callback(callback, caminho_env=caminho_env)
        texto = resultado["mensagem"]
        decidido = True
    except (ValueError, OSError, piloto_cartao.WebPostoErro) as exc:
        texto = str(exc)
        decidido = False
    await _api(client, token, "answerCallbackQuery", {
        "callback_query_id": callback["id"], "text": texto[:200], "show_alert": True,
    })
    if decidido and callback.get("message"):
        await _api(client, token, "editMessageReplyMarkup", {
            "chat_id": callback["message"]["chat"]["id"],
            "message_id": callback["message"]["message_id"], "reply_markup": {"inline_keyboard": []},
        })
    return decidido


async def ouvir(*, token, caminho_env=None, client=None):
    diretor(caminho_env)
    http = client or httpx.AsyncClient(timeout=45)
    offset = 0
    try:
        while True:
            updates = await _api(http, token, "getUpdates", {
                "offset": offset, "timeout": 30, "allowed_updates": ["callback_query"],
            })
            for update in updates:
                offset = max(offset, update["update_id"] + 1)
                callback = update.get("callback_query")
                if not callback:
                    continue
                await atender_callback(callback, token=token, client=http, caminho_env=caminho_env)
    finally:
        if client is None:
            await http.aclose()
