import re
import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco, caminhos, credenciais, rotina, unidades
from apps.match.acesso import Perfil
from apps.match.painel import criar_app
from src.modules.cash_reconciliation import config as cfg
from src.modules.cash_reconciliation.adapters import premmia_portal
from src.modules.cash_reconciliation.domain.tempo import ontem
from src.shared import segredos

SENHA = "senha-forte-1"


@pytest.fixture(autouse=True)
def _limpa():
    yield
    segredos.definir_resolvedor(None)
    cfg.definir_provedor_unidades(None)
    premmia_portal.ETAPA_ATUAL.clear()


@pytest.fixture
def fab(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
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
def postos(con):
    doze = banco.inserir_posto(con, "Posto Doze", "Doze", None, 74014)
    cc = banco.inserir_posto(con, "Casa Caiada", "Casa Caiada", None, 5555)
    banco.inserir_posto(con, "Sem Premmia", "Sem", None, 6666)
    f_doze = banco.salvar_fonte(con, doze, "premmia", True, {})
    banco.salvar_fonte(con, cc, "premmia", True, {})
    credenciais.salvar(f"{doze}/premmia/usuario", "u")
    credenciais.salvar(f"{doze}/premmia/senha", "s")
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    acesso.criar_usuario(con, "Bia", "bia", SENHA, Perfil.CONFERENTE, [cc])
    return {"doze": doze, "cc": cc, "f_doze": f_doze}


def _csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _logado(cli, login="admin") -> str:
    tok = _csrf(cli.get("/entrar").text)
    assert cli.post("/entrar", data={"login": login, "senha": SENHA, "csrf": tok}).status_code == 303
    return _csrf(cli.get("/premmia").text)


def test_cartao_mostra_ultimo_dia_e_o_que_falta(cli, con, postos):
    banco.registrar_coleta(con, postos["f_doze"], ontem(), "ok", 12, Decimal("345.60"), None)
    _logado(cli)
    html = cli.get("/premmia").text
    assert "Doze" in html and "R$ 345,60" in html and "12 venda(s)" in html
    assert "Casa Caiada" in html and "falta usuário e senha" in html and "Sem Premmia" not in html
    assert html.count('action="/premmia/coletar?posto_id=') == 2  # só o Doze (normal e visível)
    assert 'href="/premmia"' in html  # está no menu


def test_erro_e_verificacao_explicam_o_que_fazer(cli, con, postos):
    banco.registrar_coleta(con, postos["f_doze"], ontem(), "verificacao_humana", 0, Decimal(0), "x")
    _logado(cli)
    assert "Coletar mostrando o navegador e resolva" in cli.get("/premmia").text
    banco.registrar_coleta(con, postos["f_doze"], ontem(), "erro", 0, Decimal(0), "Falha inesperada na coleta (X).")
    assert "Falha inesperada na coleta (X)." in cli.get("/premmia").text


def test_coletar_mostrando_o_navegador(cli, postos, monkeypatch):
    chamadas, feito = [], threading.Event()

    async def falso(con, **kw):
        chamadas.append(kw)
        feito.set()
        return []

    monkeypatch.setattr(rotina, "executar", falso)
    csrf = _logado(cli)
    r = cli.post(f"/premmia/coletar?posto_id={postos['doze']}&visivel=1", data={"csrf": csrf})
    assert r.status_code == 303 and r.headers["location"].startswith("/premmia")
    assert feito.wait(2) and chamadas[0]["posto_id"] == postos["doze"] and chamadas[0]["visivel"] is True


def test_tela_mostra_a_etapa_em_andamento(cli, postos, monkeypatch):
    monkeypatch.setattr(rotina, "em_andamento", lambda: True)
    premmia_portal.ETAPA_ATUAL[74014] = "download XLSX"
    _logado(cli)
    html = cli.get("/premmia").text
    assert "<strong>Doze</strong>: baixando a planilha" in html and "coletando agora" in html


def test_baixar_planilha_do_mes(cli, con, postos):
    dia = ontem()
    unidade = unidades.do_posto(con, banco.obter_posto(con, postos["doze"]))
    premmia_portal.acrescentar_coleta(unidade, [], [dia], caminhos.premmia(postos["doze"]))
    _logado(cli)
    html = cli.get("/premmia").text
    assert f'/premmia/planilha/{postos["doze"]}?mes={dia:%Y-%m}' in html
    r = cli.get(f"/premmia/planilha/{postos['doze']}?mes={dia:%Y-%m}")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    outro = (dia.replace(day=1) - timedelta(days=70)).strftime("%Y-%m")
    assert cli.get(f"/premmia/planilha/{postos['doze']}?mes={outro}").status_code == 404


def test_conferente_so_ve_e_baixa_o_seu_posto(cli, postos):
    _logado(cli, "bia")
    html = cli.get("/premmia").text
    assert "Casa Caiada" in html and "Doze" not in html
    assert cli.get(f"/premmia/planilha/{postos['doze']}?mes=2026-11").status_code == 403
