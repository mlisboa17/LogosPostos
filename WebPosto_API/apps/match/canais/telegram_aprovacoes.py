"""Notificações e callbacks de aprovação do Telegram."""
from __future__ import annotations

import json
import logging
import re
import threading
import time

import httpx

from apps.match import credenciais
from apps.match.canais import telegram
from apps.match.extratos import aprovacoes
from src.shared.notificacao.telegram import API_BASE, TIMEOUT_SEGUNDOS

logger = logging.getLogger(__name__)

_CALLBACK = re.compile(r"lm:([ar]):([A-Za-z0-9_-]+)\Z")
_OFFSETS: dict[int, int] = {}
_AVISO_DIAS_IGNORADOS = "Dias que o webPosto já tiver serão ignorados por ele na importação."


def _atende(canal, posto_id: int) -> bool:
    postos = json.loads(canal["config_json"] or "{}").get("postos") or []
    return not postos or posto_id in postos


def _texto_previa(resumo: dict, tipo: str = "importar_extrato") -> str:
    posto = resumo.get("posto") or {}
    conta = resumo.get("conta") or {}
    nome = posto.get("apelido") or posto.get("nome") or "Posto"
    if tipo == "lancamento":
        plano = resumo.get("plano_conta")
        centro = resumo.get("centro_custo")
        plano_nome = plano.get("nome", "") if isinstance(plano, dict) else plano or ""
        centro_nome = centro.get("nome", "") if isinstance(centro, dict) else centro or ""
        return "\n".join((
            f"Logos Match — lançamento faltando no financeiro — {nome}",
            f"Data: {resumo.get('data', '')} · Valor: R$ {resumo.get('valor', '')}",
            f"Descrição: {resumo.get('descricao', '')}",
            f"Tipo sugerido: {resumo.get('tipo_sugerido', '')}",
            f"Plano de conta: {plano_nome}",
            f"Centro de custo: {centro_nome}",
            resumo.get("explicacao_pt", ""),
        ))
    linhas = [
        f"Logos Match — aprovação de extrato — {nome}",
        f"Conta: {conta.get('banco', 'Banco')} / final {conta.get('conta_sufixo', '')}",
    ]
    for periodo in resumo.get("periodos") or []:
        linhas.append(
            f"{periodo['de']} a {periodo['ate']}: {periodo['quantidade']} lançamento(s) a enviar; "
            f"entradas {periodo['entradas']}; saídas {periodo['saidas']}"
        )
        dias = periodo.get("dias_ja_enviados") or []
        if dias:
            linhas.append(f"Dias já enviados pelo Logos Match: {', '.join(dias)}")
    linhas.append(f"Total a enviar: {resumo.get('total_linhas', 0)} lançamento(s).")
    linhas.append(resumo.get("aviso") or _AVISO_DIAS_IGNORADOS)
    return "\n".join(linhas)


def notificar_aprovacao(con, resumo: dict, ticket: str, cliente=None,
                        tipo: str = "importar_extrato") -> None:
    """Envia a prévia aos canais Telegram inscritos e associados ao posto."""
    posto_id = (resumo.get("posto") or {}).get("id")
    if not isinstance(posto_id, int):
        posto = con.execute(
            """SELECT p.id, p.nome, p.apelido FROM aprovacao a
               JOIN posto p ON p.id=a.posto_id WHERE a.ticket=?""",
            (ticket,),
        ).fetchone()
        if posto is not None:
            posto_id = posto["id"]
            resumo = {**resumo, "posto": dict(posto)}
    if not isinstance(posto_id, int):
        return
    canais = con.execute(
        "SELECT * FROM canal WHERE ativo=1 AND tipo='telegram' ORDER BY id"
    ).fetchall()
    botoes = [("Aprovar", f"lm:a:{ticket}"), ("Recusar", f"lm:r:{ticket}")]
    texto = _texto_previa(resumo, tipo)
    for canal in canais:
        try:
            config = json.loads(canal["config_json"] or "{}")
            if config.get("aprovacoes") is not True or not _atende(canal, posto_id):
                continue
            telegram.enviar(canal, texto, None, cliente=cliente, botoes=botoes)
        except Exception as exc:  # noqa: BLE001 - erro do canal não invalida a aprovação
            logger.warning("Notificação de aprovação Telegram falhou tipo=%s",
                           type(exc).__name__)


def _responder_callback(cliente: httpx.Client, token: str, query_id: str,
                        texto: str, chat_id: int | str, message_id: int) -> None:
    raiz = f"{API_BASE}/bot{token}"
    resposta = cliente.post(
        f"{raiz}/answerCallbackQuery",
        json={"callback_query_id": query_id, "text": texto},
        timeout=TIMEOUT_SEGUNDOS,
    )
    if resposta.status_code != 200:
        raise httpx.HTTPStatusError("Telegram callback answer failed", request=resposta.request,
                                   response=resposta)
    _validar_resposta(resposta)
    resposta = cliente.post(
        f"{raiz}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": texto,
            "reply_markup": {"inline_keyboard": []},
        },
        timeout=TIMEOUT_SEGUNDOS,
    )
    if resposta.status_code != 200:
        raise httpx.HTTPStatusError("Telegram message edit failed", request=resposta.request,
                                   response=resposta)
    _validar_resposta(resposta)


def _validar_resposta(resposta: httpx.Response) -> None:
    payload = resposta.json()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ValueError("Resposta Telegram inválida.")


def _iniciar_execucao(con_factory, aprovacao_id: int) -> threading.Thread:
    def executar():
        from apps.match.extratos import camada1

        con = con_factory()
        try:
            camada1.executar(con, aprovacao_id)
        except Exception as exc:  # noqa: BLE001 - falha isolada à execução desta aprovação
            logger.warning("Execução de aprovação Telegram falhou tipo=%s",
                           type(exc).__name__)
        finally:
            con.close()

    thread = threading.Thread(target=executar, name="logosmatch-aprovacao-telegram",
                              daemon=True)
    thread.start()
    return thread


def processar_lote(con_factory, canal, updates: list[dict],
                   cliente: httpx.Client) -> int:
    """Processa um lote do getUpdates; exposto para testes sem long polling."""
    canal_id = int(canal["id"])
    token = credenciais.ler(f"canal/{canal_id}/token")
    if not token:
        raise ValueError("Credencial Telegram indisponível.")
    offset = _OFFSETS.get(canal_id, 0)
    config = json.loads(canal["config_json"] or "{}")
    chats = {str(chat_id) for chat_id in config.get("chat_ids") or []}
    permitidos = {str(user_id) for user_id in config.get("aprovadores") or []}

    for update in updates:
        update_id = update.get("update_id")
        novo_offset = max(offset, update_id + 1) if isinstance(update_id, int) else offset
        callback = update.get("callback_query")
        if not isinstance(callback, dict):
            offset = novo_offset
            _OFFSETS[canal_id] = offset
            continue
        mensagem = callback.get("message") or {}
        chat = mensagem.get("chat") or {}
        usuario = callback.get("from") or {}
        chat_id, user_id = chat.get("id"), usuario.get("id")
        if (chat_id is None or str(chat_id) not in chats or user_id is None
                or (permitidos and str(user_id) not in permitidos)):
            offset = novo_offset
            _OFFSETS[canal_id] = offset
            continue
        correspondencia = _CALLBACK.fullmatch(str(callback.get("data") or ""))
        if correspondencia is None:
            offset = novo_offset
            _OFFSETS[canal_id] = offset
            continue
        query_id = callback.get("id")
        message_id = mensagem.get("message_id")
        if not isinstance(query_id, str) or not isinstance(message_id, int):
            offset = novo_offset
            _OFFSETS[canal_id] = offset
            continue

        aprovar = correspondencia.group(1) == "a"
        ticket = correspondencia.group(2)
        con = con_factory()
        try:
            row = con.execute(
                "SELECT id, tipo FROM aprovacao WHERE ticket=?", (ticket,)
            ).fetchone()
            if row is not None and row["tipo"] == "lancamento":
                from apps.match.extratos import camada2

                decidido, _resultado = camada2.decidir(
                    con, ticket, "aprovar" if aprovar else "recusar",
                    quem=f"telegram:{user_id}", canal="telegram",
                )
            else:
                decidido, _resultado = aprovacoes.decidir(
                    con, ticket, aprovar, f"telegram:{user_id}", "telegram"
                )
        finally:
            con.close()

        resposta = (
            ("Aprovado." if aprovar else "Recusado.")
            if decidido else "Já resolvido."
        )
        try:
            if decidido and aprovar and row is not None and row["tipo"] == "importar_extrato":
                _iniciar_execucao(con_factory, row["id"])
            _responder_callback(cliente, token, query_id, resposta, chat_id, message_id)
        except Exception as exc:
            logger.warning("Resposta de aprovação Telegram falhou tipo=%s", type(exc).__name__)
        finally:
            offset = novo_offset
            _OFFSETS[canal_id] = offset

    _OFFSETS[canal_id] = offset
    return offset


def _canal(con_factory, canal_id: int):
    con = con_factory()
    try:
        return con.execute(
            "SELECT * FROM canal WHERE id=? AND tipo='telegram' AND ativo=1", (canal_id,)
        ).fetchone()
    finally:
        con.close()


def _registrar_conflito(con_factory, canal_id: int) -> None:
    con = con_factory()
    try:
        row = con.execute("SELECT config_json FROM canal WHERE id=?", (canal_id,)).fetchone()
        if row is None:
            return
        config = json.loads(row["config_json"] or "{}")
        config["aprovacoes_erro"] = "conflito"
        con.execute("UPDATE canal SET config_json=? WHERE id=?",
                    (json.dumps(config, ensure_ascii=False), canal_id))
        con.commit()
    finally:
        con.close()


def _esperar(parar: threading.Event | None, segundos: int, aguardar) -> None:
    if parar is not None:
        parar.wait(segundos)
    else:
        aguardar(segundos)


def pollar_uma_vez(con_factory, canal_id: int, cliente: httpx.Client, *,
                   parar: threading.Event | None = None, esperar=time.sleep) -> bool:
    """Faz uma chamada getUpdates. False significa que o canal entrou em conflito."""
    canal = _canal(con_factory, canal_id)
    if canal is None:
        return False
    config = json.loads(canal["config_json"] or "{}")
    if config.get("aprovacoes") is not True or config.get("aprovacoes_erro") == "conflito":
        return False
    token = credenciais.ler(f"canal/{canal_id}/token")
    if not token:
        logger.warning("Poller de aprovação Telegram sem credencial tipo=CredentialUnavailable")
        _esperar(parar, 30, esperar)
        return True
    try:
        resposta = cliente.post(
            f"{API_BASE}/bot{token}/getUpdates",
            json={"offset": _OFFSETS.get(canal_id, 0), "timeout": 25},
            timeout=TIMEOUT_SEGUNDOS + 25,
        )
        if resposta.status_code == 409:
            _registrar_conflito(con_factory, canal_id)
            return False
        if resposta.status_code != 200:
            raise httpx.HTTPStatusError(
                "Telegram getUpdates failed", request=resposta.request, response=resposta
            )
        payload = resposta.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise ValueError("Resposta Telegram inválida.")
        atualizacoes = payload.get("result")
        if not isinstance(atualizacoes, list):
            raise ValueError("Lote Telegram inválido.")
        processar_lote(con_factory, canal, atualizacoes, cliente)
        return True
    except Exception as exc:  # noqa: BLE001 - falha de um canal não encerra o poller
        logger.warning("Poller de aprovação Telegram falhou tipo=%s", type(exc).__name__)
        _esperar(parar, 30, esperar)
        return True


def _canais_ativos(con_factory) -> list[int]:
    con = con_factory()
    try:
        ids = []
        for canal in con.execute(
            "SELECT id, config_json FROM canal WHERE tipo='telegram' AND ativo=1 ORDER BY id"
        ).fetchall():
            config = json.loads(canal["config_json"] or "{}")
            if (config.get("aprovacoes") is True
                    and config.get("aprovacoes_erro") != "conflito"):
                ids.append(canal["id"])
        return ids
    finally:
        con.close()


def rodar(con_factory, parar: threading.Event) -> None:
    """Long-polling serial dos canais Telegram habilitados para aprovações."""
    with httpx.Client(timeout=TIMEOUT_SEGUNDOS + 25) as cliente:
        while not parar.is_set():
            try:
                canais = _canais_ativos(con_factory)
            except Exception as exc:  # noqa: BLE001 - falha no banco não encerra a thread
                logger.warning("Leitura dos canais Telegram falhou tipo=%s",
                               type(exc).__name__)
                parar.wait(30)
                continue
            if not canais:
                parar.wait(5)
                continue
            for canal_id in canais:
                if parar.is_set():
                    break
                try:
                    pollar_uma_vez(con_factory, canal_id, cliente, parar=parar)
                except Exception as exc:  # noqa: BLE001 - cada canal é isolado
                    logger.warning("Poller de aprovação Telegram falhou tipo=%s",
                                   type(exc).__name__)
                    parar.wait(30)
