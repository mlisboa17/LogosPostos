import io
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco
from apps.match.acesso import Perfil
from apps.match.fiscal import repositorio as repo
from apps.match.painel import criar_app
from src.shared import segredos

DADOS = Path(__file__).resolve().parents[1] / "fiscal_docs" / "dados"
SENHA = "senha-forte-1"
CNPJ = "52308604000284"


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    yield
    segredos.definir_resolvedor(None)


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
def cenario(con):
    p1 = banco.inserir_posto(con, "Doze", "doze", CNPJ, 74014)
    p2 = banco.inserir_posto(con, "Casa Caiada", "cc", "04284939000186", 5555)
    e1 = repo.salvar_empresa(con, CNPJ, "POSTO DOZE", "doze", "Abreu e Lima", "PE", p1)
    e2 = repo.salvar_empresa(con, "04284939000186", "POSTO CASA CAIADA", "cc", "Olinda", "PE", p2)
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    acesso.criar_usuario(con, "Contadora", "conta", SENHA, Perfil.CONTABILIDADE, [p1])
    return {"e1": e1, "e2": e2, "p1": p1}


def _csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _logar(cli, login) -> str:
    tok = _csrf(cli.get("/entrar").text)
    r = cli.post("/entrar", data={"login": login, "senha": SENHA, "csrf": tok})
    assert r.status_code == 303
    return _csrf(cli.get("/notas").text)


def _importar(cli, csrf, empresa_id, nome, conteudo):
    return cli.post("/importar", data={"csrf": csrf, "empresa_id": str(empresa_id)},
                    files=[("arquivos", (nome, conteudo, "application/octet-stream"))])


def test_contabilidade_so_ve_fiscal_do_seu_escopo(cli, cenario):
    csrf = _logar(cli, "conta")
    assert cli.get("/postos").status_code == 403
    r = cli.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/notas"
    html = cli.get("/notas").text
    assert "POSTO DOZE" in html and "POSTO CASA CAIADA" not in html
    assert 'href="/coleta"' not in html and 'href="/pacotes"' in html
    assert cli.get("/empresas").status_code == 403
    xml = (DADOS / "nfe_produto.xml").read_bytes().replace(CNPJ.encode(), b"04284939000186")
    assert _importar(cli, csrf, cenario["e2"], "a.xml", xml).status_code == 403


def test_importar_duas_vezes_e_filtro(cli, cenario):
    csrf = _logar(cli, "admin")
    xml = (DADOS / "nfe_combustivel.xml").read_bytes()
    r1 = _importar(cli, csrf, cenario["e1"], "a.xml", xml)
    assert "1 notas importadas, 0 já existiam, 0 não reconhecidas" in r1.text
    r2 = _importar(cli, csrf, cenario["e1"], "a.xml", xml)
    assert "0 notas importadas, 1 já existia, 0 não reconhecidas" in r2.text
    _importar(cli, csrf, cenario["e1"], "b.xml", (DADOS / "nfe_produto.xml").read_bytes())
    html = cli.get("/notas", params={"empresa_id": cenario["e1"], "fornecedor": "distrib",
                                     "inicio": "2026-10-01", "fim": "2026-11-30"}).text
    assert "DISTRIBUIDORA TESTE LTDA" in html and "FORNECEDOR PRODUTOS LTDA" not in html


def test_importar_zip_ignora_caminho_perigoso_e_outro_cnpj(cli, cenario):
    csrf = _logar(cli, "admin")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../fora.xml", (DADOS / "nfe_combustivel.xml").read_bytes())
        z.writestr("ok/nfse.xml", (DADOS / "nfse_nacional.xml").read_bytes())
        z.writestr("outro.xml", (DADOS / "nfe_produto.xml").read_bytes().replace(CNPJ.encode(), b"11111111000191"))
    r = _importar(cli, csrf, cenario["e1"], "lote.zip", buf.getvalue())
    assert "1 notas importadas" in r.text
    assert "outro.xml" in r.text and "fora.xml" in r.text
    assert not (Path(".") / "fora.xml").exists()


def test_baixar_xml_e_pdf_unificado(cli, cenario, con):
    csrf = _logar(cli, "admin")
    _importar(cli, csrf, cenario["e1"], "a.xml", (DADOS / "nfe_combustivel.xml").read_bytes())
    _importar(cli, csrf, cenario["e1"], "b.xml", (DADOS / "nfe_produto.xml").read_bytes())
    ids = [r[0] for r in con.execute("SELECT id FROM documento ORDER BY id")]
    rx = cli.get("/notas/xml", params=[("ids", i) for i in ids])
    with zipfile.ZipFile(io.BytesIO(rx.content)) as z:
        assert len(z.namelist()) == 2
    rp = cli.get("/notas/pdf", params=[("ids", i) for i in ids] + [("modo", "unificado")])
    assert rp.content.startswith(b"%PDF")


def test_cadastro_escritorio_valida_email(cli, cenario):
    csrf = _logar(cli, "admin")
    r = cli.post("/escritorios", data={"csrf": csrf, "nome": "Contab", "emails": "isso-nao-e-email",
                                       "dia_envio": "5", "modo": "enviar", "pdf": "ambos",
                                       "empresas": [str(cenario["e1"])]})
    assert r.status_code == 400
    r = cli.post("/escritorios", data={"csrf": csrf, "nome": "Contab", "emails": "a@x.com, b@y.com",
                                       "dia_envio": "5", "modo": "enviar", "pdf": "ambos",
                                       "empresas": [str(cenario["e1"])]})
    assert r.status_code == 303


def test_aprovar_pacote_pela_tela(cli, cenario, con, monkeypatch):
    from apps.match.canais import email_smtp
    enviados = []
    monkeypatch.setattr(email_smtp, "enviar_arquivos", lambda *a: enviados.append(a))
    csrf = _logar(cli, "admin")
    _importar(cli, csrf, cenario["e1"], "a.xml", (DADOS / "nfe_combustivel.xml").read_bytes())
    repo.salvar_escritorio(con, "Contab", ["c@x.com"], 5, "enviar", "separados", [cenario["e1"]])
    banco.inserir_canal(con, "email", {"servidor": "s", "usuario": "u@x"})
    pid = repo.salvar_pacote(con, cenario["e1"], "2026-10", "retido", [], "motivo")
    r = cli.post(f"/pacotes/{pid}/aprovar", data={"csrf": csrf})
    assert r.status_code == 200, r.text[:300]
    assert "Pacote enviado." in r.text and len(enviados) == 1
    r = cli.post(f"/pacotes/{pid}/reenviar", data={"csrf": csrf})
    assert r.status_code == 200 and len(enviados) == 2


def test_zip_com_senha_vira_aviso_e_nao_erro(cli, cenario, monkeypatch):
    csrf = _logar(cli, "admin")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("protegida.xml", b"<x/>")

    def recusa(self, nome, pwd=None):
        raise RuntimeError("File is encrypted, password required for extraction")

    monkeypatch.setattr(zipfile.ZipFile, "read", recusa)
    r = _importar(cli, csrf, cenario["e1"], "senha.zip", buf.getvalue())
    assert r.status_code == 200
    assert "protegida.xml (protegido por senha ou compactação não suportada)" in r.text
