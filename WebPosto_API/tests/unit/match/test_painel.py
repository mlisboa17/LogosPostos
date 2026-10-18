import json
import re
import threading

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco, coletas, credenciais, rotina
from apps.match.acesso import Perfil
from apps.match.painel import criar_app, rotas
from src.modules.cash_reconciliation import config as cfg
from src.modules.cash_reconciliation.domain.tempo import ontem
from src.shared import segredos

SENHA = "senha-forte-1"
SEGREDO = "SEGREDO-NAO-MOSTRAR-123"


@pytest.fixture(autouse=True)
def _limpa():
    yield
    segredos.definir_resolvedor(None)
    cfg.definir_provedor_unidades(None)


@pytest.fixture
def fab(tmp_path):
    caminho = tmp_path / "m.db"
    banco.conectar(caminho).close()
    return lambda: banco.conectar(caminho)


@pytest.fixture
def con(fab):
    c = fab()
    yield c
    c.close()


@pytest.fixture
def cli(fab):
    return TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)


@pytest.fixture
def admin(con):
    return acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])


@pytest.fixture
def executar_falso(monkeypatch):
    chamadas, feito = [], threading.Event()

    async def falso(con, **kw):
        chamadas.append(kw)
        feito.set()
        return []

    monkeypatch.setattr(rotina, "executar", falso)
    return chamadas, feito


def _csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _entrar(cli, login="admin", senha=SENHA):
    tok = _csrf(cli.get("/entrar").text)
    return cli.post("/entrar", data={"login": login, "senha": senha, "csrf": tok})


def _logado(cli, login="admin") -> str:
    r = _entrar(cli, login)
    assert r.status_code == 303, r.text
    return _csrf(cli.get("/").text)


def _posto(con, nome="Doze", codigo=74014) -> int:
    return banco.inserir_posto(con, nome, nome, None, codigo)


def test_sem_login_redireciona(cli, admin):
    for rota in ("/", "/postos", "/usuarios", "/agenda", "/historico", "/config/exportar"):
        r = cli.get(rota)
        assert r.status_code == 303 and r.headers["location"] == "/entrar", rota
    r = cli.post("/coletar?posto_id=1", data={"csrf": "x"})
    assert r.status_code == 303 and r.headers["location"] == "/entrar"


def test_primeiro_uso_cria_admin(cli, con):
    r = cli.get("/entrar")
    assert r.status_code == 303 and r.headers["location"] == "/primeiro-uso"
    tok = _csrf(cli.get("/primeiro-uso").text)
    r = cli.post("/primeiro-uso", data={"nome": "Dono", "login": "dono", "senha": SENHA,
                                        "senha2": SENHA, "csrf": tok})
    assert r.status_code == 303 and r.headers["location"] == "/entrar"
    assert not acesso.precisa_primeiro_uso(con)
    assert cli.get("/primeiro-uso").headers["location"] == "/entrar"
    r = cli.post("/primeiro-uso", data={"nome": "Intruso", "login": "intruso", "senha": SENHA,
                                        "senha2": SENHA, "csrf": tok})
    assert r.status_code == 403
    assert con.execute("SELECT COUNT(*) FROM usuario").fetchone()[0] == 1
    assert _entrar(cli, "dono").status_code == 303


def test_primeiro_uso_sem_csrf_recusa(cli, con):
    r = cli.post("/primeiro-uso", data={"nome": "X", "login": "x", "senha": SENHA, "senha2": SENHA})
    assert r.status_code == 403
    assert acesso.precisa_primeiro_uso(con)


def test_login_errado_nao_entra(cli, admin):
    r = _entrar(cli, senha="errada-errada")
    assert r.status_code == 401
    assert "lm_sessao" not in r.cookies
    assert cli.get("/").headers["location"] == "/entrar"


def test_login_cookie_seguro_e_sair(cli, admin):
    r = _entrar(cli)
    cookie = r.headers["set-cookie"]
    assert "lm_sessao=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie.replace("Strict", "strict")
    tok = _csrf(cli.get("/").text)
    assert cli.post("/sair", data={"csrf": tok}).status_code == 303
    assert cli.get("/").headers["location"] == "/entrar"


def test_sessao_expira(cli, admin, monkeypatch):
    _logado(cli)
    agora = rotas._relogio()
    monkeypatch.setattr(rotas, "_relogio", lambda: agora + 12 * 3600 + 1)
    assert cli.get("/").headers["location"] == "/entrar"


def test_host_externo_recusado(fab, admin):
    c = TestClient(criar_app(fab), base_url="http://ataque.exemplo", follow_redirects=False)
    assert c.get("/entrar").status_code == 400


def test_post_sem_csrf_recusa(cli, admin, con):
    tok = _logado(cli)
    assert cli.post("/postos", data={"acao": "novo", "nome": "X"}).status_code == 403
    assert cli.post("/postos", data={"acao": "novo", "nome": "X", "csrf": "outro"}).status_code == 403
    assert banco.listar_postos(con, so_ativos=False) == []
    assert cli.post("/postos", data={"acao": "novo", "nome": "X", "csrf": tok}).status_code == 303
    assert [p["nome"] for p in banco.listar_postos(con)] == ["X"]


def test_gerente_posto_alheio_403(cli, admin, con, executar_falso):
    ids = [_posto(con, f"P{i}", 1000 + i) for i in range(7)]
    assert ids[-1] == 7
    acesso.criar_usuario(con, "Gê", "gerente", SENHA, Perfil.GERENTE, [1])
    tok = _logado(cli, "gerente")
    r = cli.get("/postos/7/fontes")
    assert r.status_code == 403 and "Você não tem acesso a isto." in r.text
    r = cli.post("/coletar?posto_id=7&visivel=0", data={"csrf": tok})
    assert r.status_code == 403
    assert executar_falso[0] == []
    assert cli.get("/postos/1/fontes").status_code == 200
    for rota in ("/usuarios", "/canais", "/agenda", "/config/exportar", "/usuarios/log"):
        assert cli.get(rota).status_code == 403, rota


def test_conferente_nao_troca_credencial(cli, admin, con):
    pid = _posto(con)
    acesso.criar_usuario(con, "Cê", "conf", SENHA, Perfil.CONFERENTE, [pid])
    tok = _logado(cli, "conf")
    r = cli.post(f"/postos/{pid}/fontes/premmia", data={"csrf": tok, "ativo": "1",
                                                        "senha": SEGREDO, "usuario": "u"})
    assert r.status_code == 403
    assert not credenciais.tem(f"{pid}/premmia/senha")
    assert cli.get(f"/postos/{pid}/fontes").status_code == 403


def test_hoje_lista_so_postos_visiveis(cli, admin, con):
    a, _b = _posto(con, "Posto Alfa", 1), _posto(con, "Posto Beta", 2)
    acesso.criar_usuario(con, "Gê", "gerente", SENHA, Perfil.GERENTE, [a])
    _logado(cli, "gerente")
    html = cli.get("/").text
    assert "Posto Alfa" in html and "Posto Beta" not in html
    menu = re.search(r"<nav.*?</nav>", html, re.S).group(0)
    assert "/usuarios" not in menu and "/canais" not in menu and "/agenda" not in menu


def test_hoje_mostra_responsavel(cli, admin, con):
    pid = _posto(con)
    banco.gravar_divergencias(con, pid, ontem(), "pagbank_edi", [{
        "tipo": "falta_no_webposto", "valor_esperado": "10", "valor_encontrado": "0",
        "responsavel": "JOÃO (42)", "explicacao_pt": "Venda <b>sem</b> lançamento.",
        "correcao_pt": "Lançar o cartão."}])
    _logado(cli)
    html = cli.get("/").text
    assert "JOÃO (42)" in html and "Lançar o cartão." in html
    assert "Venda &lt;b&gt;sem&lt;/b&gt; lançamento." in html  # autoescape


def test_log_registra_troca_de_credencial(cli, admin, con):
    pid = _posto(con)
    tok = _logado(cli)
    r = cli.post(f"/postos/{pid}/fontes/premmia", data={"csrf": tok, "ativo": "1",
                                                        "usuario": "user", "senha": SEGREDO})
    assert r.status_code == 303
    assert credenciais.ler(f"{pid}/premmia/senha") == SEGREDO
    logs = con.execute("SELECT * FROM log_acesso WHERE acao='trocar_credencial'").fetchall()
    assert len(logs) == 1 and logs[0]["usuario_id"] == admin
    assert SEGREDO not in logs[0]["detalhe"] and "senha" in logs[0]["detalhe"]
    assert all(SEGREDO not in (r["detalhe"] or "") for r in con.execute("SELECT detalhe FROM log_acesso"))


def test_senha_em_branco_mantem_anterior(cli, admin, con):
    pid = _posto(con)
    credenciais.salvar(f"{pid}/pagbank/token", SEGREDO)
    tok = _logado(cli)
    r = cli.post(f"/postos/{pid}/fontes/pagbank_edi", data={"csrf": tok, "ativo": "1",
                                                            "usuario": "novo", "token": ""})
    assert r.status_code == 303
    assert credenciais.ler(f"{pid}/pagbank/token") == SEGREDO
    assert credenciais.ler(f"{pid}/pagbank/usuario") == "novo"
    fonte = {f["tipo"]: f for f in banco.fontes_do_posto(con, pid)}["pagbank_edi"]
    assert fonte["ativo"] == 1


def test_salvar_fonte_preserva_config(cli, admin, con):
    pid = _posto(con)
    banco.salvar_fonte(con, pid, "premmia", False, {"administradoras": {"PREMMIA": [5]}})
    tok = _logado(cli)
    cli.post(f"/postos/{pid}/fontes/premmia", data={"csrf": tok, "ativo": "1"})
    fonte = banco.fontes_do_posto(con, pid)[0]
    assert json.loads(fonte["config_json"]) == {"administradoras": {"PREMMIA": [5]}}
    assert fonte["ativo"] == 1


def test_tela_nao_mostra_segredo(cli, admin, con):
    pid = _posto(con)
    for chave in ("premmia/usuario", "premmia/senha", "pagbank/usuario", "pagbank/token", "webposto/chave"):
        credenciais.salvar(f"{pid}/{chave}", f"{SEGREDO}-{chave}")
    _logado(cli)
    html = cli.get(f"/postos/{pid}/fontes").text
    assert SEGREDO not in html
    assert "••••" in html


def test_testar_pagbank_usa_erro_pt(cli, admin, con, monkeypatch):
    from src.modules.cash_reconciliation.adapters import pagbank_edi
    pid = _posto(con)
    vistos = []

    async def falso(emp, dia, **kw):
        vistos.append((emp, dia))
        raise pagbank_edi.PagBankCredencialInvalida(f"token {SEGREDO}")

    monkeypatch.setattr(pagbank_edi, "buscar_transacoes", falso)
    tok = _logado(cli)
    r = cli.post(f"/postos/{pid}/fontes/pagbank_edi/testar", data={"csrf": tok})
    assert r.status_code == 200
    assert "PagBank recusou o usuário/token" in r.text and SEGREDO not in r.text
    assert vistos == [(74014, ontem())]


def test_testar_webposto_ok(cli, admin, con, monkeypatch):
    from src.modules.cash_reconciliation.adapters import webposto_caixas
    pid = _posto(con)
    vistos = []

    async def falso(unidade, inicio, fim, **kw):
        vistos.append((unidade.empresa_codigo, inicio, fim))
        return [object(), object()]

    monkeypatch.setattr(webposto_caixas, "buscar_caixas", falso)
    tok = _logado(cli)
    r = cli.post(f"/postos/{pid}/fontes/webposto/testar", data={"csrf": tok})
    assert "2 caixa(s)" in r.text
    assert vistos == [(74014, ontem(), ontem())]


def test_testar_premmia_so_confere_existencia(cli, admin, con):
    pid = _posto(con)
    tok = _logado(cli)
    assert "Falta" in cli.post(f"/postos/{pid}/fontes/premmia/testar", data={"csrf": tok}).text
    credenciais.salvar(f"{pid}/premmia/usuario", "u")
    credenciais.salvar(f"{pid}/premmia/senha", "s")
    assert "estão salvos" in cli.post(f"/postos/{pid}/fontes/premmia/testar", data={"csrf": tok}).text


def test_coletar_inicia_em_thread(cli, admin, con, executar_falso):
    pid = _posto(con)
    tok = _logado(cli)
    r = cli.post(f"/coletar?posto_id={pid}&visivel=1", data={"csrf": tok})
    assert r.status_code == 200 and "Coleta iniciada" in r.text
    chamadas, feito = executar_falso
    assert feito.wait(5)
    assert chamadas == [{"posto_id": pid, "visivel": True}]
    assert con.execute("SELECT COUNT(*) FROM log_acesso WHERE acao='coletar'").fetchone()[0] == 1


def test_coletar_em_andamento(cli, admin, con, executar_falso):
    pid = _posto(con)
    tok = _logado(cli)
    assert rotina._TRAVA.acquire(blocking=False)
    try:
        r = cli.post(f"/coletar?posto_id={pid}&visivel=0", data={"csrf": tok})
    finally:
        rotina._TRAVA.release()
    assert "Já existe uma coleta em andamento. Aguarde terminar." in r.text
    assert executar_falso[0] == []


def test_reenviar_usa_dados_salvos(cli, admin, con, monkeypatch):
    pid = _posto(con)
    fid = banco.salvar_fonte(con, pid, "pagbank_edi", True, {})
    banco.registrar_coleta(con, fid, ontem(), "ok", 3, "30.00", None)
    enviados, feito = [], threading.Event()

    def falso(c, resultados, dia):
        enviados.append((resultados, dia))
        feito.set()

    monkeypatch.setattr(rotas.envio, "enviar_dia", falso)
    tok = _logado(cli)
    r = cli.post(f"/reenviar?posto_id={pid}", data={"csrf": tok})
    assert "Reenvio iniciado" in r.text
    assert feito.wait(5)
    resultados, dia = enviados[0]
    assert dia == ontem() and [(x.fonte, x.qtd) for x in resultados] == [("pagbank_edi", 3)]


def test_resultados_salvos_sem_coleta(con):
    pid = _posto(con)
    banco.salvar_fonte(con, pid, "pagbank_edi", True, {})
    assert coletas.resultados_salvos(con, pid, ontem()) == []


def test_exportar_sem_segredo(cli, admin, con):
    pid = _posto(con)
    banco.salvar_fonte(con, pid, "webposto", True, {"chave": SEGREDO})
    credenciais.salvar(f"{pid}/webposto/chave", SEGREDO)
    _logado(cli)
    r = cli.get("/config/exportar")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert SEGREDO not in r.text
    assert r.json()["postos"][0]["nome"] == "Doze"


def test_importar_config(cli, admin, con):
    tok = _logado(cli)
    dados = json.dumps({"postos": [{"nome": "Novo", "empresa_codigo_webposto": 9}]})
    r = cli.post("/config/importar", data={"csrf": tok},
                 files={"arquivo": ("c.json", dados, "application/json")})
    assert r.status_code == 200 and "1 posto(s)" in r.text
    assert [p["nome"] for p in banco.listar_postos(con)] == ["Novo"]
    r = cli.post("/config/importar", data={"csrf": tok},
                 files={"arquivo": ("c.json", "não é json", "application/json")})
    assert r.status_code == 400


def test_agenda_hora_invalida_recusa(cli, admin, con):
    tok = _logado(cli)
    r = cli.post("/agenda", data={"csrf": tok, "hora_coleta": "25:00", "hora_repescagem": "10:00"})
    assert r.status_code == 400 and "Horário inválido" in r.text
    assert rotina.horarios(con) == ("06:00", "10:00")
    r = cli.post("/agenda", data={"csrf": tok, "hora_coleta": "05:30", "hora_repescagem": "11:15"})
    assert r.status_code == 303
    assert rotina.horarios(con) == ("05:30", "11:15")


def test_historico_datas_brasil(cli, admin, con):
    pid = _posto(con)
    fid = banco.salvar_fonte(con, pid, "pagbank_edi", True, {})
    banco.registrar_coleta(con, fid, ontem(), "erro", 0, "0", "PagBank recusou o usuário/token.")
    _logado(cli)
    html = cli.get("/historico").text
    assert f"{ontem():%d/%m/%Y}" in html and "PagBank recusou" in html
    assert re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", html)


def test_canais_cria_e_mantem_token(cli, admin, con):
    tok = _logado(cli)
    r = cli.post("/canais", data={"csrf": tok, "acao": "novo", "tipo": "telegram",
                                  "token": SEGREDO, "chat_ids": "11, 22", "ativo": "1"})
    assert r.status_code == 303
    canal = con.execute("SELECT * FROM canal").fetchone()
    assert json.loads(canal["config_json"])["chat_ids"] == ["11", "22"]
    assert SEGREDO not in canal["config_json"]
    assert credenciais.ler(f"canal/{canal['id']}/token") == SEGREDO
    cli.post("/canais", data={"csrf": tok, "acao": "editar", "id": canal["id"], "tipo": "telegram",
                              "token": "", "chat_ids": "33", "ativo": "1"})
    assert credenciais.ler(f"canal/{canal['id']}/token") == SEGREDO
    assert SEGREDO not in cli.get("/canais").text


def test_usuarios_criar_e_nao_desativar_ultimo_admin(cli, admin, con):
    pid = _posto(con)
    tok = _logado(cli)
    r = cli.post("/usuarios", data={"csrf": tok, "acao": "criar", "nome": "Gê", "login": "ge",
                                    "senha": SENHA, "perfil": "gerente", "postos": [str(pid)]})
    assert r.status_code == 303
    ge = con.execute("SELECT id FROM usuario WHERE login='ge'").fetchone()["id"]
    assert acesso.postos_visiveis_agora(con, ge) == [pid]
    r = cli.post("/usuarios", data={"csrf": tok, "acao": "desativar", "id": admin})
    assert r.status_code == 400
    assert acesso.carregar_usuario(con, admin)["ativo"] == 1
    r = cli.post("/usuarios", data={"csrf": tok, "acao": "editar", "id": admin, "nome": "Admin",
                                    "perfil": "gerente"})
    assert r.status_code == 400
    assert not acesso.precisa_primeiro_uso(con)
    assert "criar_usuario" in cli.get("/usuarios/log").text


def test_todas_as_telas_abrem_para_admin(cli, admin, con):
    pid = _posto(con)
    banco.inserir_canal(con, "telegram", {"chat_ids": ["1"], "postos": [pid]})
    banco.inserir_canal(con, "email", {"servidor": "s", "porta": 587, "usuario": "a@b.c",
                                       "destinatarios": ["x@y.z"]})
    banco.inserir_canal(con, "toast", {}, ativo=False)
    banco.registrar_envio(con, 1, ontem(), "erro", "Não foi possível falar com o Telegram.")
    _logado(cli)
    for rota in ("/", "/postos", f"/postos/{pid}/fontes", "/canais", "/agenda", "/historico",
                 "/usuarios", "/usuarios/log", "/static/estilo.css"):
        r = cli.get(rota)
        assert r.status_code == 200, rota
        assert r.headers["x-frame-options"] == "DENY"
    assert "Cadastre cada posto em uma só máquina para evitar coleta duplicada." in cli.get("/postos").text
    assert "Não foi possível falar com o Telegram." in cli.get("/historico").text


def test_usuario_desativado_perde_sessao(fab, admin, con):
    acesso.criar_usuario(con, "Gê", "ge", SENHA, Perfil.GERENTE, [])
    c1 = TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)
    _logado(c1, "ge")
    con.execute("UPDATE usuario SET ativo=0 WHERE login='ge'")
    con.commit()
    assert c1.get("/").headers["location"] == "/entrar"


def test_gerente_posto_alheio_403_fontes_e_reenviar(cli, admin, con):
    _posto(con, "Meu", 1)
    alheio = _posto(con, "Alheio", 2)
    acesso.criar_usuario(con, "Gê", "gerente", SENHA, Perfil.GERENTE, [1])
    tok = _logado(cli, "gerente")
    for rota in (f"/postos/{alheio}/fontes/premmia", f"/postos/{alheio}/fontes/pagbank_edi/testar",
                 f"/reenviar?posto_id={alheio}"):
        r = cli.post(rota, data={"csrf": tok, "ativo": "1", "senha": SEGREDO})
        assert r.status_code == 403, rota
    assert not credenciais.tem(f"{alheio}/premmia/senha")


def test_usuario_com_posto_invalido(cli, admin, con):
    tok = _logado(cli)
    r = cli.post("/usuarios", data={"csrf": tok, "acao": "criar", "nome": "Gê", "login": "ge",
                                    "senha": SENHA, "perfil": "gerente", "postos": ["999"]})
    assert r.status_code == 400 and "Posto inválido." in r.text and "já existe" not in r.text
    assert con.execute("SELECT COUNT(*) FROM usuario WHERE login='ge'").fetchone()[0] == 0


def test_editar_canal_preserva_chaves_desconhecidas(cli, admin, con):
    cid = banco.inserir_canal(con, "telegram", {"chat_ids": ["1"], "extra": "manter"})
    tok = _logado(cli)
    cli.post("/canais", data={"csrf": tok, "acao": "editar", "id": cid, "chat_ids": "2", "ativo": "1"})
    cfg = json.loads(con.execute("SELECT config_json FROM canal WHERE id=?", (cid,)).fetchone()[0])
    assert cfg == {"chat_ids": ["2"], "extra": "manter", "postos": []}


def test_falha_em_segundo_plano_nao_loga_mensagem(caplog, fab, monkeypatch):
    import logging
    from apps.match import agendador
    from apps.match.canais import toast

    def explode(*a, **k):
        raise RuntimeError("SEGREDO-XYZ")

    async def explode_async(*a, **k):
        raise RuntimeError("SEGREDO-XYZ")

    monkeypatch.setattr(rotina, "executar", explode_async)
    monkeypatch.setattr(rotina, "limpar_antigos", explode)
    monkeypatch.setattr(toast, "avisar", explode)
    caplog.set_level(logging.DEBUG)
    rotas._em_segundo_plano("teste", explode).join(5)
    agendador._rodar(fab, so_falhas=False, limpar=True)
    assert caplog.records
    for rec in caplog.records:
        assert "SEGREDO-XYZ" not in rec.getMessage()
        assert "SEGREDO-XYZ" not in (rec.exc_text or "")
        assert rec.exc_info is None
