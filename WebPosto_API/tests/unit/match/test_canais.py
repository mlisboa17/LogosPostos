import smtplib
import ssl
import sys
from datetime import date
from decimal import Decimal

import httpx
import pytest

from apps.match import banco, credenciais
from apps.match.canais import CanalErro, email_smtp, envio, telegram, toast
from apps.match.coletas import ResultadoFonte

DIA = date(2026, 10, 17)


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "t.db")
    yield c
    c.close()


def _res(posto_id, fonte="premmia", situacao="ok", divs=()):
    return ResultadoFonte(posto_id, fonte, DIA, situacao, 1, Decimal("10"), "msg", list(divs))


def _posto(con, apelido="Doze"):
    return banco.inserir_posto(con, "Posto Doze", apelido, None, 74014)


class SmtpFalso:
    enviadas = []

    def __init__(self, servidor, porta, timeout=None, context=None):
        self.porta = porta
        self.tls = False
        self.ctx = context

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls = True
        self.ctx = context or self.ctx

    def login(self, u, s):
        self.login_ = (u, s)

    def send_message(self, msg):
        SmtpFalso.enviadas.append((self, msg))


def test_resumo_icones(con):
    pid = _posto(con)
    posto = banco.listar_postos(con)[0]
    txt = envio.texto_resumo([_res(pid, "premmia", "ok"), _res(pid, "pagbank_edi", "erro")], posto, DIA)
    assert txt.splitlines()[0] == "Logos Match — Doze — 17/10/2026"
    assert "✅ Premmia" in txt and "❌ PagBank" in txt
    assert "⚠️" in envio.texto_resumo([_res(pid, situacao="sem_comparacao")], posto, DIA)


def test_resumo_limita_dez_divergencias(con):
    pid = _posto(con)
    posto = banco.listar_postos(con)[0]
    divs = [{"explicacao_pt": f"divergencia {i}"} for i in range(13)]
    txt = envio.texto_resumo([_res(pid, divs=divs)], posto, DIA)
    assert txt.count("divergencia ") == 10
    assert "e mais 3 na planilha" in txt


def test_telegram_falha_de_destinatario_levanta(con):
    cid = banco.inserir_canal(con, "telegram", {"chat_ids": ["1"]})
    credenciais.salvar(f"canal/{cid}/token", "TOKEN")
    canal = con.execute("SELECT * FROM canal WHERE id=?", (cid,)).fetchone()
    ruim = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"ok": False})))
    with pytest.raises(CanalErro):
        telegram.enviar(canal, "oi", None, cliente=ruim)
    bom = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True})))
    telegram.enviar(canal, "oi", None, cliente=bom)


def test_canal_limitado_a_posto(con, monkeypatch):
    p1, p2 = _posto(con, "Um"), _posto(con, "Dois")
    cid = banco.inserir_canal(con, "telegram", {"chat_ids": ["1"], "postos": [p2]})
    chamadas = []
    monkeypatch.setattr(telegram, "enviar", lambda c, t, a: chamadas.append(t))
    envio.enviar_dia(con, [_res(p1), _res(p2)], DIA)
    assert len(chamadas) == 1 and "Dois" in chamadas[0]
    assert con.execute("SELECT COUNT(*) FROM envio WHERE canal_id=?", (cid,)).fetchone()[0] == 1


def test_falha_telegram_nao_impede_email(con, monkeypatch):
    pid = _posto(con)
    banco.inserir_canal(con, "telegram", {"chat_ids": ["1"]})
    banco.inserir_canal(con, "email", {"servidor": "s", "porta": 587, "usuario": "a@b.c",
                                       "destinatarios": ["x@y.z"]})
    SmtpFalso.enviadas = []
    monkeypatch.setattr(email_smtp.smtplib, "SMTP", SmtpFalso)

    def quebra(*a, **k):
        raise RuntimeError("token SEGREDO123")
    monkeypatch.setattr(telegram, "enviar", quebra)
    envio.enviar_dia(con, [_res(pid)], DIA)
    assert len(SmtpFalso.enviadas) == 1 and SmtpFalso.enviadas[0][0].tls
    assert [r["situacao"] for r in con.execute("SELECT * FROM envio ORDER BY id")] == ["erro", "ok"]
    erro = con.execute("SELECT erro_texto FROM envio WHERE situacao='erro'").fetchone()[0]
    assert erro and "SEGREDO123" not in erro


def test_envio_registrado(con, monkeypatch):
    pid = _posto(con)
    cid = banco.inserir_canal(con, "toast", {})
    avisos = []
    monkeypatch.setattr(toast, "avisar", lambda t, x: avisos.append(t))
    envio.enviar_dia(con, [_res(pid)], DIA)
    row = con.execute("SELECT * FROM envio WHERE canal_id=?", (cid,)).fetchone()
    assert row["situacao"] == "ok" and row["dia"] == "2026-10-17" and row["enviado_em"]
    assert avisos and avisos[0].startswith("Logos Match")


def test_email_anexa_planilha(con, monkeypatch):
    pid = _posto(con)
    cid = banco.inserir_canal(con, "email", {"servidor": "s", "porta": 465, "usuario": "a@b.c",
                                             "destinatarios": ["x@y.z", "w@y.z"]})
    credenciais.salvar(f"canal/{cid}/senha", "pw")
    SmtpFalso.enviadas = []
    monkeypatch.setattr(email_smtp.smtplib, "SMTP_SSL", SmtpFalso)
    envio.enviar_dia(con, [_res(pid)], DIA)
    smtp, msg = SmtpFalso.enviadas[0]
    assert smtp.porta == 465 and not smtp.tls and smtp.login_ == ("a@b.c", "pw")
    anexos = list(msg.iter_attachments())
    assert len(anexos) == 1 and anexos[0].get_filename().endswith(".xlsx")
    assert anexos[0].get_content_type() == \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert msg["To"] == "x@y.z, w@y.z"


def test_planilha_falha_envia_sem_anexo(con, monkeypatch):
    pid = _posto(con)
    banco.inserir_canal(con, "telegram", {"chat_ids": ["1"]})
    recebidos = []
    monkeypatch.setattr(telegram, "enviar", lambda c, t, a: recebidos.append(a))

    def quebra(*a):
        raise OSError("disco")
    monkeypatch.setattr(envio.relatorio_xlsx, "gerar", quebra)
    envio.enviar_dia(con, [_res(pid)], DIA)
    assert recebidos == [None]


def test_testar_canal(con, monkeypatch):
    cid = banco.inserir_canal(con, "toast", {})
    monkeypatch.setattr(toast, "avisar", lambda t, x: None)
    assert envio.testar_canal(con, cid) == "ok"
    tg = banco.inserir_canal(con, "telegram", {"chat_ids": []})
    assert "Telegram" in envio.testar_canal(con, tg)


def test_toast_falha_so_loga(monkeypatch):
    monkeypatch.setitem(sys.modules, "windows_toasts", None)
    toast.avisar("a", "b")


def _verifica(ctx):
    return ctx is not None and ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


@pytest.mark.parametrize("porta,attr", [(465, "SMTP_SSL"), (587, "SMTP")])
def test_email_valida_certificado(con, monkeypatch, porta, attr):
    pid = _posto(con)
    banco.inserir_canal(con, "email", {"servidor": "s", "porta": porta, "usuario": "a@b.c",
                                       "destinatarios": ["x@y.z"]})
    SmtpFalso.enviadas = []
    monkeypatch.setattr(email_smtp.smtplib, attr, SmtpFalso)
    envio.enviar_dia(con, [_res(pid)], DIA)
    assert _verifica(SmtpFalso.enviadas[0][0].ctx)


def test_email_destinatarios_string(con, monkeypatch):
    pid = _posto(con)
    banco.inserir_canal(con, "email", {"servidor": "s", "porta": 587, "usuario": "a@b.c",
                                       "destinatarios": "x@y.z; w@y.z"})
    SmtpFalso.enviadas = []
    monkeypatch.setattr(email_smtp.smtplib, "SMTP", SmtpFalso)
    envio.enviar_dia(con, [_res(pid)], DIA)
    assert SmtpFalso.enviadas[0][1]["To"] == "x@y.z, w@y.z"


def test_canal_corrompido_nao_impede_outros(con, monkeypatch):
    pid = _posto(con)
    ruim = con.execute("INSERT INTO canal(tipo, config_json) VALUES ('toast', '{quebrado')").lastrowid
    con.commit()
    banco.inserir_canal(con, "toast", {})
    monkeypatch.setattr(toast, "avisar", lambda t, x: None)
    envio.enviar_dia(con, [_res(pid)], DIA)
    sit = {r["canal_id"]: r["situacao"] for r in con.execute("SELECT * FROM envio")}
    assert sit[ruim] == "erro" and "ok" in sit.values()


def test_tipo_desconhecido(con):
    pid = _posto(con)
    cid = con.execute("INSERT INTO canal(tipo, config_json) VALUES ('toast', '{}')").lastrowid
    canal = con.execute("SELECT * FROM canal WHERE id=?", (cid,)).fetchone()
    desconhecido = dict(canal, tipo="sms")
    with pytest.raises(CanalErro, match="desconhecido"):
        envio._despachar(desconhecido, "a", "b", None)


def test_erro_envio_pt():
    from apps.match.canais import erro_envio_pt
    assert "usuário/senha" in erro_envio_pt(smtplib.SMTPAuthenticationError(535, b"SEGREDO"))
    assert "conectar ao servidor de e-mail" in erro_envio_pt(smtplib.SMTPException("SEGREDO"))
    assert "conectar ao servidor de e-mail" in erro_envio_pt(OSError("SEGREDO"))
    assert "Telegram" in erro_envio_pt(httpx.ConnectError("SEGREDO"))
    assert erro_envio_pt(CanalErro("minha msg")) == "minha msg"
    txt = erro_envio_pt(RuntimeError("SEGREDO"))
    assert "RuntimeError" in txt and "SEGREDO" not in txt and "coleta" not in txt


def test_resumo_icones_humano_e_sem_movimento(con):
    pid = _posto(con)
    posto = banco.listar_postos(con)[0]
    txt = envio.texto_resumo([_res(pid, "premmia", "verificacao_humana"),
                              _res(pid, "pagbank_edi", "sem_movimento")], posto, DIA)
    assert "❌ Premmia" in txt and "⚠️ PagBank" in txt


def test_telegram_401_nao_vaza_token(con, monkeypatch):
    pid = _posto(con)
    cid = banco.inserir_canal(con, "telegram", {"chat_ids": ["1"]})
    credenciais.salvar(f"canal/{cid}/token", "TOKENSECRETO")
    real = httpx.Client
    mock = httpx.MockTransport(lambda r: httpx.Response(401, json={"ok": False}))
    monkeypatch.setattr(httpx, "Client", lambda **k: real(transport=mock))
    envio.enviar_dia(con, [_res(pid)], DIA)
    row = con.execute("SELECT * FROM envio WHERE canal_id=?", (cid,)).fetchone()
    assert row["situacao"] == "erro" and row["erro_texto"]
    assert "TOKENSECRETO" not in row["erro_texto"]
