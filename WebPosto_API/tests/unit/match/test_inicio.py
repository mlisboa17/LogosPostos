import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco, inicio
from apps.match.acesso import Perfil
from apps.match.fiscal import certificados, repositorio as repo
from apps.match.painel import criar_app
from tests.unit.match.test_fiscal_certificados import SENHA as SENHA_PFX, gerar_pfx

SENHA = "senha-forte-1"
AGORA = datetime(2026, 11, 10, 13, 0, tzinfo=timezone.utc)  # 10:00 em Recife


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


def _csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def test_instalacao_nova_mostra_os_primeiros_passos(con):
    uid = acesso.criar_usuario(con, "Marcio Lisboa", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    r = inicio.montar(con, uid, AGORA)
    assert r.saudacao == "Bom dia, Marcio"
    assert r.passos_pendentes
    assert [p.titulo for p in r.passos][0] == "Enviar o certificado de uma empresa"
    assert not any(p.feito for p in r.passos)


def test_certificado_conta_no_cartao_e_marca_o_passo(con):
    uid = acesso.criar_usuario(con, "Marcio", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    certificados.criar_empresa_pelo_certificado(con, gerar_pfx("POSTO DOZE:52308604000284", dias=20), SENHA_PFX)
    repo.salvar_empresa(con, "04284939000186", "CASA CAIADA", "Casa Caiada", None, "PE", None)
    r = inicio.montar(con, uid, AGORA)
    cert = next(c for c in r.cartoes if c.rotulo == "Certificados")
    assert cert.valor == "1 de 2" and cert.estado == "critico"
    assert r.passos[0].feito and r.passos[1].titulo == "Enviar o certificado das outras empresas"
    assert "Casa Caiada" in r.passos[1].detalhe


def test_tudo_configurado_esconde_os_passos(con):
    uid = acesso.criar_usuario(con, "Marcio", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    acesso.definir_email(con, uid, "m@x.com")
    eid, _ = certificados.criar_empresa_pelo_certificado(con, gerar_pfx("POSTO DOZE:52308604000284"), SENHA_PFX)
    banco.inserir_canal(con, "email", {"servidor": "s", "usuario": "u@x"})
    repo.salvar_escritorio(con, "Contab", ["c@x.com"], 5, "enviar", "ambos", [eid])
    r = inicio.montar(con, uid, AGORA)
    assert not r.passos_pendentes
    envio = next(c for c in r.cartoes if c.rotulo == "Próximo envio ao contador")
    assert envio.valor == "05/12" and envio.estado == "ok"


def test_conferente_nao_ve_fiscal_nem_passos(con):
    pid = banco.inserir_posto(con, "Doze", "doze", None, 74014)
    uid = acesso.criar_usuario(con, "Bia", "bia", SENHA, Perfil.CONFERENTE, [pid])
    r = inicio.montar(con, uid, AGORA)
    assert [c.rotulo for c in r.cartoes] == [f"Conferência de caixa ({date(2026, 11, 9):%d/%m})"]
    assert r.passos == []


def test_tela_inicio_e_caixa(fab, con):
    acesso.criar_usuario(con, "Marcio", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    banco.inserir_posto(con, "Posto Alfa", "Alfa", None, 1)
    cli = TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)
    tok = _csrf(cli.get("/entrar").text)
    cli.post("/entrar", data={"login": "admin", "senha": SENHA, "csrf": tok})
    html = cli.get("/").text
    assert "Primeiros passos" in html and 'href="/comecar"' in html
    nav = html[html.index("<nav"):html.index("</nav>")]
    assert nav.index('href="/"') < nav.index('href="/conferencia"') < nav.index('href="/comecar"') < nav.index('href="/notas"')
    assert 'href="/caixa"' not in nav and 'href="/premmia"' not in nav  # ficam nas abas da Conferência
    abas = cli.get("/caixa").text
    assert 'class="abas"' in abas and 'href="/premmia"' in abas and 'href="/pagbank"' in abas
    assert "<svg" in nav
    assert "Posto Alfa" in cli.get("/caixa").text
