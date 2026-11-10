"""Parte 1 da usabilidade: esqueci minha senha, mostrar senha, manter conectado, e-mail do usuário."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco, recuperar_senha
from apps.match.acesso import Perfil
from apps.match.canais import email_smtp
from apps.match.painel import criar_app

SENHA = "senha-forte-1"


@pytest.fixture
def fab(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
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
def emails(monkeypatch):
    enviados = []
    monkeypatch.setattr(email_smtp, "enviar_arquivos",
                        lambda canal, dest, assunto, texto, anexos: enviados.append((dest, assunto, texto)))
    return enviados


def _csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _usuario(con, email="ana@posto.com.br"):
    uid = acesso.criar_usuario(con, "Ana", "ana", SENHA, Perfil.ADMINISTRADOR, [])
    acesso.definir_email(con, uid, email)
    banco.inserir_canal(con, "email", {"servidor": "smtp.x", "usuario": "match@x.com"})
    return uid


def _cookie_sessao(resp) -> str:
    return next(c for c in resp.headers.get_list("set-cookie") if c.startswith("lm_sessao=")).lower()


def _codigo(texto: str) -> str:
    return re.search(r"\b(\d{6})\b", texto).group(1)


def _entrar(cli, login, senha, **extra):
    tok = _csrf(cli.get("/entrar").text)
    return cli.post("/entrar", data={"login": login, "senha": senha, "csrf": tok, **extra})


# ---------------------------------------------------------------- esqueci minha senha

def test_tela_de_login_tem_esqueci_e_mostrar_senha(cli, con):
    _usuario(con)
    html = cli.get("/entrar").text
    assert 'href="/esqueci"' in html and "Esqueci minha senha" in html
    assert '<script src="/static/painel.js" defer></script>' in html
    assert "script-src 'self'" in cli.get("/entrar").headers["content-security-policy"]


def test_codigo_por_email_troca_a_senha(cli, con, emails):
    _usuario(con)
    tok = _csrf(cli.get("/esqueci").text)
    r = cli.post("/esqueci", data={"csrf": tok, "login": "ana"})
    assert r.status_code == 200 and recuperar_senha.MSG_ENVIADO in r.text
    [(dest, assunto, texto)] = emails
    assert dest == ["ana@posto.com.br"] and "15 minutos" in texto
    tok = _csrf(r.text)
    r = cli.post("/esqueci/codigo", data={"csrf": tok, "login": "ana", "codigo": _codigo(texto),
                                          "senha": "nova-senha-123", "senha2": "nova-senha-123"})
    assert r.status_code == 303 and r.headers["location"] == "/entrar?senha_alterada=1"
    assert "Sua senha foi alterada" in cli.get("/entrar?senha_alterada=1").text
    assert _entrar(cli, "ana", SENHA).status_code == 401
    assert _entrar(cli, "ana", "nova-senha-123").status_code == 303


def test_usuario_inexistente_recebe_a_mesma_resposta(cli, con, emails):
    _usuario(con)
    tok = _csrf(cli.get("/esqueci").text)
    r = cli.post("/esqueci", data={"csrf": tok, "login": "ninguem"})
    assert r.status_code == 200 and recuperar_senha.MSG_ENVIADO in r.text and emails == []


def test_pedir_pelo_email_tambem_funciona(con, emails):
    uid = _usuario(con)
    assert recuperar_senha.pedir_codigo(con, "ANA@posto.com.br", datetime.now(timezone.utc)) == uid
    assert len(emails) == 1


def test_codigo_errado_cinco_vezes_invalida(con, emails):
    _usuario(con)
    agora = datetime.now(timezone.utc)
    recuperar_senha.pedir_codigo(con, "ana", agora)
    certo = _codigo(emails[0][2])
    errado = "000000" if certo != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(ValueError):
            recuperar_senha.trocar_senha(con, "ana", errado, "nova-senha-123", agora)
    with pytest.raises(ValueError, match="Peça um código novo"):
        recuperar_senha.trocar_senha(con, "ana", certo, "nova-senha-123", agora)


def test_codigo_expira_em_15_minutos(con, emails):
    _usuario(con)
    agora = datetime.now(timezone.utc)
    recuperar_senha.pedir_codigo(con, "ana", agora)
    with pytest.raises(ValueError, match="venceu"):
        recuperar_senha.trocar_senha(con, "ana", _codigo(emails[0][2]), "nova-senha-123",
                                     agora + timedelta(minutes=16))


def test_codigo_so_vale_uma_vez(con, emails):
    _usuario(con)
    agora = datetime.now(timezone.utc)
    recuperar_senha.pedir_codigo(con, "ana", agora)
    codigo = _codigo(emails[0][2])
    recuperar_senha.trocar_senha(con, "ana", codigo, "nova-senha-123", agora)
    with pytest.raises(ValueError):
        recuperar_senha.trocar_senha(con, "ana", codigo, "outra-senha-123", agora)


def test_sem_email_configurado_explica_o_que_fazer(cli, con):
    acesso.criar_usuario(con, "Ana", "ana", SENHA, Perfil.ADMINISTRADOR, [])
    html = cli.get("/esqueci").text
    assert "Peça ao administrador" in html and "--redefinir-admin" in html


def test_senhas_diferentes_avisam(cli, con, emails):
    _usuario(con)
    tok = _csrf(cli.get("/esqueci").text)
    r = cli.post("/esqueci", data={"csrf": tok, "login": "ana"})
    r = cli.post("/esqueci/codigo", data={"csrf": _csrf(r.text), "login": "ana", "codigo": _codigo(emails[0][2]),
                                          "senha": "nova-senha-123", "senha2": "outra-senha-123"})
    assert r.status_code == 400 and "As duas senhas não são iguais" in r.text


# ---------------------------------------------------------------- e-mail do usuário

def test_admin_cadastra_email_do_usuario(cli, con):
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    _entrar(cli, "admin", SENHA)
    tok = _csrf(cli.get("/usuarios").text)
    r = cli.post("/usuarios", data={"csrf": tok, "acao": "criar", "nome": "Bia", "login": "bia",
                                    "senha": SENHA, "perfil": "conferente", "email": "bia@x.com"})
    assert r.status_code == 303
    assert con.execute("SELECT email FROM usuario WHERE login='bia'").fetchone()[0] == "bia@x.com"
    r = cli.post("/usuarios", data={"csrf": tok, "acao": "criar", "nome": "Caio", "login": "caio",
                                    "senha": SENHA, "perfil": "conferente", "email": "nao-e-email"})
    assert r.status_code == 400 and "e-mail" in r.text.lower()


# ---------------------------------------------------------------- manter conectado

def test_manter_conectado_sobrevive_a_reinicio(fab, con):
    acesso.criar_usuario(con, "Ana", "ana", SENHA, Perfil.ADMINISTRADOR, [])
    c1 = TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)
    r = _entrar(c1, "ana", SENHA, lembrar="1")
    assert "max-age=604800" in _cookie_sessao(r)
    c2 = TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)  # app reiniciado
    c2.cookies.update(c1.cookies)
    assert c2.get("/historico").status_code == 200
    token = c1.cookies.get("lm_sessao")
    assert token not in str([tuple(x) for x in con.execute("SELECT * FROM sessao_lembrada")])


def test_sem_manter_conectado_reinicio_pede_login(fab, con):
    acesso.criar_usuario(con, "Ana", "ana", SENHA, Perfil.ADMINISTRADOR, [])
    c1 = TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)
    r = _entrar(c1, "ana", SENHA)
    assert "max-age" not in _cookie_sessao(r)
    c2 = TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)
    c2.cookies.update(c1.cookies)
    assert c2.get("/historico").headers["location"] == "/entrar"


def test_sair_apaga_a_sessao_lembrada(fab, con):
    acesso.criar_usuario(con, "Ana", "ana", SENHA, Perfil.ADMINISTRADOR, [])
    c1 = TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)
    _entrar(c1, "ana", SENHA, lembrar="1")
    tok = _csrf(c1.get("/historico").text)
    c1.post("/sair", data={"csrf": tok})
    assert con.execute("SELECT COUNT(*) FROM sessao_lembrada").fetchone()[0] == 0
