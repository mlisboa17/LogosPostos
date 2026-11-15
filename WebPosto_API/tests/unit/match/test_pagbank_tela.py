import re
import threading
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco, credenciais, rotina
from apps.match.acesso import Perfil
from apps.match.painel import criar_app
from src.modules.cash_reconciliation import config as cfg
from src.modules.cash_reconciliation.domain.tempo import ontem
from src.shared import segredos

SENHA = "senha-forte-1"


@pytest.fixture(autouse=True)
def _limpa():
    yield
    segredos.definir_resolvedor(None)
    cfg.definir_provedor_unidades(None)


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
    f = banco.salvar_fonte(con, doze, "pagbank_edi", True, {})
    credenciais.salvar(f"{doze}/pagbank/usuario", "u")
    credenciais.salvar(f"{doze}/pagbank/token", "t")
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    return {"doze": doze, "cc": cc, "f": f}


def _logado(cli) -> str:
    tok = re.search(r'name="csrf" value="([^"]+)"', cli.get("/entrar").text).group(1)
    assert cli.post("/entrar", data={"login": "admin", "senha": SENHA, "csrf": tok}).status_code == 303
    return re.search(r'name="csrf" value="([^"]+)"', cli.get("/pagbank").text).group(1)


def test_tela_pagbank_mostra_diferenca_do_dia(cli, con, postos):
    cid = banco.registrar_coleta(con, postos["f"], ontem(), "ok", 40, Decimal("5230.10"), None)
    banco.salvar_total_webposto(con, cid, Decimal("5180.10"))
    _logado(cli)
    html = cli.get("/pagbank").text
    assert 'href="/pagbank"' in html and "PagBank <b>R$ 5.230,10</b> · lançado no webPosto <b>R$ 5.180,10</b>" in html
    assert "R$ 50,00" in html and "Ligar o PagBank neste posto" in html  # Casa Caiada ainda desligado
    assert f'/pagbank/{postos["doze"]}/conciliacao' in html


def test_conciliacao_pagbank_usa_o_nome_certo(cli, con, postos):
    cid = banco.registrar_coleta(con, postos["f"], ontem(), "ok", 40, Decimal("5230.10"), None)
    banco.salvar_total_webposto(con, cid, Decimal("5180.10"))
    banco.gravar_divergencias(con, postos["doze"], ontem(), "pagbank_edi", [
        {"tipo": "falta_no_webposto", "valor_esperado": Decimal("50"), "valor_encontrado": Decimal(0),
         "responsavel": "ANA (3)", "acao": "incluir", "criterios": ["valor igual"], "referencia": "PagBank NSU 9",
         "explicacao_pt": "Venda no PagBank sem lançamento.", "correcao_pt": "Lançar."}])
    _logado(cli)
    html = cli.get(f"/pagbank/{postos['doze']}/conciliacao").text
    assert "Conciliação PagBank × webPosto" in html and "Venda no PagBank sem lançamento." in html
    assert "Premmia" not in html.split("</nav>", 1)[1]  # fora do menu, nada de Premmia
    r = cli.get(f"/pagbank/{postos['doze']}/conciliacao.xlsx")
    assert r.status_code == 200 and "Conciliacao_PagBank_Doze" in r.headers["content-disposition"]


def test_ligar_pagbank_pela_tela(cli, con, postos, monkeypatch):
    feito = threading.Event()

    async def falso(con, **kw):
        feito.set()
        return []

    monkeypatch.setattr(rotina, "executar", falso)
    csrf = _logado(cli)
    r = cli.post(f"/pagbank/{postos['cc']}/ligar", data={"csrf": csrf, "usuario": "cc-user", "token": "cc-token"})
    assert r.status_code == 303 and credenciais.ler(f"{postos['cc']}/pagbank/token") == "cc-token"
    assert {f["tipo"]: f["ativo"] for f in banco.fontes_do_posto(con, postos["cc"])} == {"pagbank_edi": 1}
    assert feito.wait(2)
    assert cli.post(f"/pagbank/{postos['cc']}/ligar", data={"csrf": csrf}).status_code == 303  # já tem: mantém


def test_coletar_periodo_pela_tela(cli, postos, monkeypatch):
    from datetime import timedelta
    chamadas, feito = [], threading.Event()

    async def falso(con, posto_id, inicio, fim, **kw):
        chamadas.append((posto_id, inicio, fim))
        feito.set()
        return []

    monkeypatch.setattr(rotina, "executar_periodo", falso)
    monkeypatch.setattr(rotina, "em_andamento", lambda: False)  # independente da ordem dos testes
    csrf = _logado(cli)
    assert "Coletar outro dia ou período" in cli.get("/pagbank").text
    ini = ontem() - timedelta(days=5)
    r = cli.post(f"/pagbank/periodo?posto_id={postos['doze']}",
                 data={"csrf": csrf, "inicio": ini.isoformat(), "fim": ontem().isoformat()})
    assert r.status_code == 303 and feito.wait(2) and chamadas == [(postos["doze"], ini, ontem())]
    longe = cli.post(f"/pagbank/periodo?posto_id={postos['doze']}",
                     data={"csrf": csrf, "inicio": (ontem() - timedelta(days=40)).isoformat(), "fim": ontem().isoformat()})
    assert longe.status_code == 400 and "31 dias" in longe.text
    futuro = cli.post(f"/pagbank/periodo?posto_id={postos['doze']}",
                      data={"csrf": csrf, "inicio": (ontem() + timedelta(days=2)).isoformat(),
                            "fim": (ontem() + timedelta(days=3)).isoformat()})
    assert futuro.status_code == 400 and "até ontem" in futuro.text
