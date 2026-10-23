import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from apps.match import banco, credenciais
from apps.match.canais import email_smtp
from apps.match.fiscal import envio_mensal, repositorio as repo
from src.modules.fiscal_docs import acervo
from src.modules.fiscal_docs.parser import ler

DADOS = Path(__file__).resolve().parents[1] / "fiscal_docs" / "dados"
CNPJ = "52308604000284"


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "e.db")
    yield c
    c.close()


@pytest.fixture
def enviados(monkeypatch):
    lista = []
    monkeypatch.setattr(email_smtp, "enviar_arquivos",
                        lambda canal, dest, assunto, texto, anexos: lista.append((dest, assunto, list(anexos))))
    return lista


def _cenario(con, tmp_path, *, modo="enviar", email=True):
    pid = banco.inserir_posto(con, "Doze", "doze", CNPJ, 74014)
    banco.salvar_fonte(con, pid, "webposto", True, {})
    credenciais.salvar(f"{pid}/webposto/chave", "K")
    eid = repo.salvar_empresa(con, CNPJ, "POSTO DOZE", "doze", "Abreu e Lima", "PE", pid)
    repo.salvar_escritorio(con, "Contab A", ["conta@x.com"], 5, modo, "unificado", [eid])
    if email:
        banco.inserir_canal(con, "email", {"servidor": "smtp.x", "usuario": "eu@x", "destinatarios": "eu@x"})
    _gravar(con, eid, tmp_path, "nfe_combustivel.xml")
    return eid


def _gravar(con, eid, tmp_path, nome):
    xml = (DADOS / nome).read_bytes()
    doc = ler(xml)
    repo.gravar_documento(con, eid, doc, acervo.gravar(tmp_path / "ac", CNPJ, doc, xml, "webposto"),
                          "h", "webposto")


def test_dia_4_nao_envia_dia_5_envia_uma_vez(con, tmp_path, enviados):
    _cenario(con, tmp_path)
    assert envio_mensal.rodar(con, date(2026, 11, 4)) == []
    envio_mensal.rodar(con, date(2026, 11, 5))
    assert len(enviados) == 1
    dest, assunto, anexos = enviados[0]
    assert dest == ["conta@x.com"]
    assert assunto == "Notas fiscais doze — 10/2026"
    assert anexos[0].name == f"{CNPJ}_2026-10.zip"
    envio_mensal.rodar(con, date(2026, 11, 5))
    envio_mensal.rodar(con, date(2026, 11, 6))
    assert len(enviados) == 1
    assert con.execute("SELECT situacao FROM pacote").fetchone()[0] == "enviado"


def test_pc_desligado_no_dia_5_envia_no_dia_7(con, tmp_path, enviados):
    _cenario(con, tmp_path)
    envio_mensal.rodar(con, date(2026, 11, 7))
    assert len(enviados) == 1


def test_retido_nao_envia_e_aprovar_envia(con, tmp_path, enviados):
    eid = _cenario(con, tmp_path)
    repo.registrar_captura(con, eid, "webposto", datetime(2026, 11, 4, tzinfo=timezone.utc).isoformat(),
                           "erro", 0, 0, "x")
    envio_mensal.rodar(con, date(2026, 11, 5), agora=datetime(2026, 11, 5, 11, tzinfo=timezone.utc))
    assert enviados == []
    p = con.execute("SELECT id, situacao, motivo_retencao FROM pacote").fetchone()
    assert p["situacao"] == "retido" and "erro" in p["motivo_retencao"]
    uid = con.execute("INSERT INTO usuario(nome, login, senha_hash, perfil, criado_em) "
                      "VALUES ('a','a','h','administrador','x')").lastrowid
    envio_mensal.aprovar_e_enviar(con, p["id"], uid)
    assert len(enviados) == 1
    row = con.execute("SELECT situacao, aprovado_por FROM pacote WHERE id=?", (p["id"],)).fetchone()
    assert tuple(row) == ("enviado", uid)


def test_sem_canal_de_email_vira_erro(con, tmp_path, enviados):
    _cenario(con, tmp_path, email=False)
    envio_mensal.rodar(con, date(2026, 11, 5))
    p = con.execute("SELECT situacao, motivo_retencao FROM pacote").fetchone()
    assert tuple(p) == ("erro", envio_mensal.MSG_SEM_EMAIL)


def test_so_gerar_nao_envia(con, tmp_path, enviados):
    _cenario(con, tmp_path, modo="so_gerar")
    envio_mensal.rodar(con, date(2026, 11, 5))
    envio_mensal.rodar(con, date(2026, 11, 6))
    assert enviados == []
    assert [r[0] for r in con.execute("SELECT situacao FROM pacote")] == ["gerado"]


def test_complementar_para_nota_atrasada(con, tmp_path, enviados):
    eid = _cenario(con, tmp_path)
    envio_mensal.rodar(con, date(2026, 11, 5))
    _gravar(con, eid, tmp_path, "nfe_produto.xml")
    envio_mensal.enviar_complementares(con, datetime.now(timezone.utc))
    assert len(enviados) == 2
    _, assunto, anexos = enviados[1]
    assert "complementar" in assunto
    with zipfile.ZipFile(anexos[0]) as z:
        assert [n for n in z.namelist() if n.startswith("xml/")] == [
            "xml/26261033333333000191550020000000771000000771.xml"]
    envio_mensal.enviar_complementares(con, datetime.now(timezone.utc))
    assert len(enviados) == 2


def test_enviar_arquivos_smtp(monkeypatch, tmp_path):
    mensagens = []

    class SMTPFalso:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, msg): mensagens.append(msg)

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", SMTPFalso)
    z = tmp_path / "a.zip"
    z.write_bytes(b"PK")
    canal = {"id": 1, "config_json": '{"servidor": "s", "usuario": "u@x", "porta": 587}'}
    email_smtp.__dict__["enviar_arquivos"](canal, ["c@x"], "Assunto", "Texto", [z])
    assert mensagens[0]["To"] == "c@x"
    [anexo] = list(mensagens[0].iter_attachments())
    assert anexo.get_filename() == "a.zip" and anexo.get_content_type() == "application/zip"
