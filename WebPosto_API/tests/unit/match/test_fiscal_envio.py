import json
import zipfile
from datetime import date, datetime, timedelta, timezone
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
    con.execute("UPDATE escritorio SET criado_em='2026-01-01T00:00:00+00:00'")
    con.commit()
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


# ---------------------------------------------------------------- achados da revisão final

def _contar(con, sql, *a):
    return con.execute(sql, a).fetchone()[0]


def test_nota_capturada_durante_o_envio_vai_no_complementar(con, tmp_path, monkeypatch):
    eid = _cenario(con, tmp_path)
    lista = []

    def enviar(canal, dest, assunto, texto, anexos):
        if not lista:  # captura das 08:30 roda enquanto o e-mail das 08:00 ainda está saindo
            _gravar(con, eid, tmp_path, "nfe_produto.xml")
        lista.append((assunto, list(anexos)))

    monkeypatch.setattr(email_smtp, "enviar_arquivos", enviar)
    envio_mensal.rodar(con, date(2026, 11, 5))
    envio_mensal.enviar_complementares(con, datetime.now(timezone.utc))
    assert len(lista) == 2 and "complementar" in lista[1][0]
    with zipfile.ZipFile(lista[1][1][0]) as z:
        assert [n for n in z.namelist() if n.startswith("xml/")] == [
            "xml/26261033333333000191550020000000771000000771.xml"]


def test_aprovar_pacote_ja_enviado_nao_reenvia(con, tmp_path, enviados):
    _cenario(con, tmp_path)
    envio_mensal.rodar(con, date(2026, 11, 5))
    pid = _contar(con, "SELECT id FROM pacote")
    with pytest.raises(ValueError):
        envio_mensal.aprovar_e_enviar(con, pid, None)
    assert len(enviados) == 1


def test_falha_na_parte_2_retoma_so_a_parte_2(con, tmp_path, monkeypatch):
    from apps.match.fiscal import pacote
    eid = _cenario(con, tmp_path)
    _gravar(con, eid, tmp_path, "nfe_produto.xml")
    monkeypatch.setattr(pacote, "LIMITE_BYTES", 8 * 1024)
    chamadas = []

    def enviar(canal, dest, assunto, texto, anexos):
        chamadas.append(anexos[0].name)
        if len(chamadas) == 2:
            raise OSError("smtp caiu")

    monkeypatch.setattr(email_smtp, "enviar_arquivos", enviar)
    envio_mensal.rodar(con, date(2026, 11, 5))
    assert con.execute("SELECT situacao, partes_enviadas FROM pacote").fetchone()[:] == ("erro", 1)
    nomes = [Path(a).name for a in json.loads(_contar(con, "SELECT arquivos_json FROM pacote"))]
    envio_mensal.rodar(con, date(2026, 11, 6))
    assert chamadas[2:] == nomes[1:]  # retomou da parte 2, sem repetir a 1
    assert _contar(con, "SELECT situacao FROM pacote") == "enviado"


def test_envio_interrompido_e_retomado(con, tmp_path, enviados):
    eid = _cenario(con, tmp_path)
    antigo = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    con.execute("INSERT INTO pacote(empresa_id, competencia, gerado_em, situacao) VALUES (?,?,?, 'enviando')",
                (eid, "2026-10", antigo))
    con.commit()
    envio_mensal.rodar(con, date(2026, 11, 5))
    assert len(enviados) == 1 and _contar(con, "SELECT situacao FROM pacote") == "enviado"


def test_envio_em_andamento_recente_nao_duplica(con, tmp_path, enviados):
    eid = _cenario(con, tmp_path)
    con.execute("INSERT INTO pacote(empresa_id, competencia, gerado_em, situacao) VALUES (?,?,?, 'enviando')",
                (eid, "2026-10", datetime.now(timezone.utc).isoformat()))
    con.commit()
    envio_mensal.rodar(con, date(2026, 11, 5))
    assert enviados == []


def test_mes_perdido_com_pc_desligado_e_enviado(con, tmp_path, enviados):
    eid = _cenario(con, tmp_path)
    _gravar(con, eid, tmp_path, "nfse_nacional.xml")  # competência 2026-09
    con.execute("UPDATE escritorio SET dia_envio=28, criado_em='2026-09-01T00:00:00+00:00'")
    con.commit()
    envio_mensal.rodar(con, date(2026, 11, 1))
    assert [a[1] for a in enviados] == ["Notas fiscais doze — 09/2026"]


def test_escritorio_novo_nao_manda_meses_antigos(con, tmp_path, enviados):
    eid = _cenario(con, tmp_path)
    _gravar(con, eid, tmp_path, "nfse_nacional.xml")
    con.execute("UPDATE escritorio SET dia_envio=28, criado_em='2026-10-30T00:00:00+00:00'")
    con.commit()
    envio_mensal.rodar(con, date(2026, 11, 1))
    assert enviados == []


def test_complementar_com_erro_nao_gera_linha_nova_e_aprovar_manda_so_ele(con, tmp_path, monkeypatch):
    eid = _cenario(con, tmp_path)
    lista, falhar = [], [False]

    def enviar(canal, dest, assunto, texto, anexos):
        if falhar[0]:
            raise OSError("smtp caiu")
        lista.append((assunto, list(anexos)))

    monkeypatch.setattr(email_smtp, "enviar_arquivos", enviar)
    envio_mensal.rodar(con, date(2026, 11, 5))
    _gravar(con, eid, tmp_path, "nfe_produto.xml")
    falhar[0] = True
    envio_mensal.enviar_complementares(con, datetime.now(timezone.utc))
    envio_mensal.enviar_complementares(con, datetime.now(timezone.utc))
    assert _contar(con, "SELECT COUNT(*) FROM pacote WHERE complementar=1") == 1
    falhar[0] = False
    pid = _contar(con, "SELECT id FROM pacote WHERE complementar=1")
    envio_mensal.aprovar_e_enviar(con, pid, None)
    assert "complementar" in lista[-1][0]
    with zipfile.ZipFile(lista[-1][1][0]) as z:
        assert [n for n in z.namelist() if n.startswith("xml/")] == [
            "xml/26261033333333000191550020000000771000000771.xml"]


def test_meses_antigos_sem_notas_nao_viram_pacote_retido(con, tmp_path, enviados):
    eid = _cenario(con, tmp_path)
    repo.registrar_captura(con, eid, "webposto", datetime(2026, 11, 4, tzinfo=timezone.utc).isoformat(),
                           "erro", 0, 0, "x")
    envio_mensal.rodar(con, date(2026, 11, 5), agora=datetime(2026, 11, 5, 11, tzinfo=timezone.utc))
    assert [r[0] for r in con.execute("SELECT competencia FROM pacote")] == ["2026-10"]
