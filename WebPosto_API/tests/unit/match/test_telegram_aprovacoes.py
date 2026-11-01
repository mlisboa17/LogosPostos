import json
import logging
import re
import sqlite3
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco, credenciais
from apps.match.acesso import Perfil
from apps.match.canais import telegram, telegram_aprovacoes
from apps.match.extratos import aprovacoes, camada1
from apps.match.painel import criar_app

SENHA = "senha-forte-1"


@pytest.fixture
def fab(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    caminho = tmp_path / "telegram.db"
    banco.conectar(caminho).close()
    return lambda: banco.conectar(caminho)


@pytest.fixture
def con(fab):
    telegram_aprovacoes._OFFSETS.clear()
    conexao = fab()
    yield conexao
    conexao.close()
    telegram_aprovacoes._OFFSETS.clear()


@pytest.fixture
def cli(fab):
    return TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)


def _canal(con, *, chat_ids=None, aprovadores=None, postos=None):
    canal_id = banco.inserir_canal(
        con,
        "telegram",
        {
            "chat_ids": chat_ids or ["-100"],
            "aprovacoes": True,
            "aprovadores": aprovadores or [],
            "postos": postos or [],
        },
    )
    credenciais.salvar(f"canal/{canal_id}/token", "TOKEN-TESTE")
    return con.execute("SELECT * FROM canal WHERE id=?", (canal_id,)).fetchone()


def _aprovacao(con, situacao="pendente"):
    posto_id = banco.inserir_posto(con, "Posto Teste", "Teste", None, 74014)
    aprovacao = aprovacoes.criar(
        con,
        "importar_extrato",
        posto_id,
        None,
        {
            "posto": {"id": posto_id, "nome": "Posto Teste", "apelido": "Teste"},
            "conta": {"banco": "BB", "conta_sufixo": "4068-X"},
            "periodos": [
                {"de": "2026-10-31", "ate": "2026-10-31", "quantidade": 2,
                 "entradas": "20.00", "saidas": "0.00", "dias_ja_enviados": []}
            ],
            "total_linhas": 2,
            "aviso": camada1.AVISO_DIAS_IGNORADOS,
        },
    )
    if situacao != "pendente":
        aprovacoes.decidir(con, aprovacao["ticket"], True, "painel", "painel")
    return aprovacao


def _callback(ticket, *, chat_id=-100, user_id=88, update_id=1, acao="a"):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"callback-{update_id}",
            "from": {"id": user_id},
            "message": {"message_id": 91, "chat": {"id": chat_id}, "text": "Prévia"},
            "data": f"lm:{acao}:{ticket}",
        },
    }


def _transport(registros, *, status=200):
    def handle(request):
        registros.append((request.url.path, json.loads(request.content)))
        return httpx.Response(status, json={"ok": status == 200, "result": []})

    return httpx.MockTransport(handle)


def _csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _login(cli):
    csrf = _csrf(cli.get("/entrar").text)
    resposta = cli.post(
        "/entrar",
        data={"login": "admin", "senha": SENHA, "csrf": csrf},
    )
    assert resposta.status_code == 303


def test_aprovacao_envia_botoes_sem_dados_sensiveis(con, monkeypatch):
    _canal(con)
    posto_id = banco.inserir_posto(con, "Posto Teste", "Teste", None, 74014)
    conta = con.execute(
        """INSERT INTO conta_bancaria
           (posto_id, banco, conta_sufixo, cd_conta_webposto)
           VALUES (?, 'BB', '4068-X', 86248)""",
        (posto_id,),
    )
    con.execute(
        """INSERT INTO extrato_arquivo(sha256, nome_original, recebido_em, situacao)
           VALUES ('hash-local', 'extrato.ofx', '2026-11-01T10:00:00+00:00', 'lido')"""
    )
    arquivo_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.execute(
        """INSERT INTO extrato_linha
           (conta_bancaria_id, arquivo_id, chave, fitid, data, valor, tipo, descricao,
            documento, categoria)
           VALUES (?, ?, 'fit-1', 'fit-1', '2026-10-31', '15.00', 'CREDIT',
                   'Venda', 'doc', 'outros')""",
        (conta.lastrowid, arquivo_id),
    )
    con.commit()
    monkeypatch.setattr(camada1, "hoje", lambda: date(2026, 11, 1))
    registros = []
    client = httpx.Client(transport=_transport(registros))
    enviar_original = telegram_aprovacoes.telegram.enviar

    def enviar_com_cliente(canal, texto, anexo, **kwargs):
        kwargs.pop("cliente", None)
        return enviar_original(canal, texto, anexo, cliente=client, **kwargs)

    monkeypatch.setattr(telegram_aprovacoes.telegram, "enviar", enviar_com_cliente)

    previa = camada1.montar_previa(con, conta.lastrowid)

    client.close()
    assert previa is not None
    assert len(registros) == 1
    endpoint, payload = registros[0]
    assert endpoint.endswith("/sendMessage")
    assert camada1.AVISO_DIAS_IGNORADOS in payload["text"]
    teclado = payload["reply_markup"]["inline_keyboard"]
    assert [(b["text"], b["callback_data"]) for linha in teclado for b in linha] == [
        ("Aprovar", f"lm:a:{previa['ticket']}"),
        ("Recusar", f"lm:r:{previa['ticket']}"),
    ]
    assert all(
        re.fullmatch(r"lm:[ar]:[A-Za-z0-9_-]+", b["callback_data"])
        for linha in teclado for b in linha
    )
    assert all(
        re.fullmatch(r"lm:[ar]:" + re.escape(previa["ticket"]), b["callback_data"])
        for linha in teclado for b in linha
    )


def test_callback_aprova_e_executa(con, fab, monkeypatch):
    canal = _canal(con, aprovadores=["88"])
    aprovacao = _aprovacao(con)
    registros = []
    client = httpx.Client(transport=_transport(registros))
    execucoes = []
    threads = []

    def executar_em_conexao_propria(conexao, aprovacao_id):
        execucoes.append((conexao, aprovacao_id))

    monkeypatch.setattr(camada1, "executar", executar_em_conexao_propria)
    iniciar_original = telegram_aprovacoes._iniciar_execucao

    def iniciar(factory, aprovacao_id):
        thread = iniciar_original(factory, aprovacao_id)
        threads.append(thread)
        return thread

    monkeypatch.setattr(telegram_aprovacoes, "_iniciar_execucao", iniciar)

    proximo = telegram_aprovacoes.processar_lote(
        fab, canal, [_callback(aprovacao["ticket"])], client
    )

    client.close()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert proximo == 2
    assert aprovacoes.pendentes(con) == []
    decisao = con.execute("SELECT decidida_por, canal_decisao FROM aprovacao").fetchone()
    assert tuple(decisao) == ("telegram:88", "telegram")
    assert len(execucoes) == 1
    conexao_execucao, id_execucao = execucoes[0]
    assert conexao_execucao is not con and id_execucao == aprovacao["id"]
    with pytest.raises(sqlite3.ProgrammingError):
        conexao_execucao.execute("SELECT 1")
    assert [body["text"] for path, body in registros
            if path.endswith("/answerCallbackQuery")] == ["Aprovado."]
    assert [body["text"] for path, body in registros
            if path.endswith("/editMessageText")] == ["Aprovado."]


def test_callback_de_quem_nao_pode_e_ignorado(con, fab, monkeypatch):
    canal = _canal(con, aprovadores=["99"])
    aprovacao = _aprovacao(con)
    registros = []
    client = httpx.Client(transport=_transport(registros))

    telegram_aprovacoes.processar_lote(
        fab, canal,
        [
            _callback(aprovacao["ticket"], user_id=88, update_id=1),
            _callback(aprovacao["ticket"], user_id=99, chat_id=-200, update_id=2),
        ],
        client,
    )

    client.close()
    assert con.execute("SELECT situacao FROM aprovacao").fetchone()[0] == "pendente"
    assert registros == []


def test_clique_repetido_ja_resolvido(con, fab, monkeypatch):
    canal = _canal(con)
    aprovacao = _aprovacao(con, situacao="aprovada")
    registros = []
    client = httpx.Client(transport=_transport(registros))
    execucoes = []
    monkeypatch.setattr(
        telegram_aprovacoes, "_iniciar_execucao",
        lambda *args: execucoes.append(args),
    )

    telegram_aprovacoes.processar_lote(
        fab, canal, [_callback(aprovacao["ticket"])], client
    )

    client.close()
    respostas = [body["text"] for path, body in registros
                 if path.endswith("/answerCallbackQuery")]
    assert respostas == ["Já resolvido."]
    assert execucoes == []


def test_409_desliga_e_avisa_no_canal(cli, fab, con):
    canal = _canal(con)
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    requests = []

    def conflict(request):
        requests.append(json.loads(request.content))
        return httpx.Response(409, json={"ok": False, "description": "Conflict"})

    client = httpx.Client(transport=httpx.MockTransport(conflict))

    continuar = telegram_aprovacoes.pollar_uma_vez(fab, canal["id"], client)

    client.close()
    assert continuar is False
    assert requests == [{"offset": 0, "timeout": 25}]
    cfg = json.loads(con.execute(
        "SELECT config_json FROM canal WHERE id=?", (canal["id"],)
    ).fetchone()[0])
    assert cfg["aprovacoes_erro"] == "conflito"
    _login(cli)
    tela = cli.get("/canais")
    assert tela.status_code == 200
    assert "Este bot já é usado por outro programa; crie um bot só para o Logos Match." in tela.text
    assert "Receber aprovações por este canal" in tela.text
    assert "TOKEN-TESTE" not in tela.text


def test_erro_de_rede_nao_derruba(con, fab, caplog):
    canal = _canal(con)
    esperas = []

    def falhar(_request):
        raise httpx.ConnectError("TOKEN-TESTE")

    client = httpx.Client(transport=httpx.MockTransport(falhar))

    with caplog.at_level(logging.WARNING, logger="apps.match.canais.telegram_aprovacoes"):
        continuar = telegram_aprovacoes.pollar_uma_vez(
            fab, canal["id"], client, esperar=esperas.append
        )

    client.close()
    assert continuar is True
    assert esperas == [30]
    assert "TOKEN-TESTE" not in caplog.text
