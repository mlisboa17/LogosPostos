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


def test_ligar_premmia_pela_tela_e_coletar_o_mes(cli, con, postos, monkeypatch):
    chamadas, feito = [], threading.Event()

    async def falso(con, **kw):
        chamadas.append(kw)
        feito.set()
        return []

    monkeypatch.setattr(rotina, "executar", falso)
    csrf = _logado(cli)
    html = cli.get("/premmia").text
    assert f'action="/premmia/{postos["cc"]}/ligar"' in html and "Ligar o Premmia neste posto" in html
    r = cli.post(f"/premmia/{postos['cc']}/ligar",
                 data={"csrf": csrf, "usuario": "70001", "senha": "segredo-x", "chave_webposto": "CHAVE-X"})
    assert r.status_code == 303 and r.headers["location"] == "/premmia?iniciada=1"
    assert credenciais.ler(f"{postos['cc']}/premmia/usuario") == "70001"
    assert credenciais.ler(f"{postos['cc']}/webposto/chave") == "CHAVE-X"
    ativos = {f["tipo"]: f["ativo"] for f in banco.fontes_do_posto(con, postos["cc"])}
    assert ativos == {"premmia": 1, "webposto": 1}
    assert feito.wait(2) and chamadas[0]["posto_id"] == postos["cc"] and chamadas[0]["visivel"] is True
    log = " ".join(r[0] for r in con.execute("SELECT detalhe FROM log_acesso"))
    assert "segredo-x" not in log and "CHAVE-X" not in log


def test_ligar_sem_senha_explica(cli, postos):
    csrf = _logado(cli)
    r = cli.post(f"/premmia/{postos['cc']}/ligar", data={"csrf": csrf, "usuario": "70001"})
    assert r.status_code == 400 and "Informe o usuário e a senha" in r.text


def test_cartao_avisa_quando_falta_a_chave_do_webposto(cli, con, postos):
    banco.registrar_coleta(con, postos["f_doze"], ontem(), "ok", 1, Decimal("10"), None)
    _logado(cli)
    assert "Sem comparação com o webPosto: falta a chave" in cli.get("/premmia").text


def test_conferente_nao_liga_premmia(cli, postos):
    _logado(cli, "bia")
    assert "/ligar" not in cli.get("/premmia").text


def _divergencias_exemplo(con, pid):
    from apps.match import sugestoes
    banco.gravar_divergencias(con, pid, ontem(), "premmia", [
        {"tipo": "falta_no_webposto", "valor_esperado": Decimal("57.30"), "valor_encontrado": Decimal(0),
         "responsavel": "JOSÉ (7)", "acao": "incluir", "criterios": ["valor igual", "abastecido 3 min antes"],
         "abastecimento": "abastecimento 123 · bico 4 · 10:02", "referencia": "Premmia NSU 1 · 10:05",
         "explicacao_pt": "Venda no Premmia sem lançamento.", "correcao_pt": "Lançar no caixa de JOSÉ (7)."},
        {"tipo": "sobra_no_webposto", "valor_esperado": Decimal(0), "valor_encontrado": Decimal("40.00"),
         "responsavel": "MARIA (9)", "acao": "excluir", "criterios": ["não está no portal Premmia"],
         "referencia": "cartão 900 · venda 777", "explicacao_pt": "possível divergência de caixa",
         "correcao_pt": "Excluir depois de conferir."},
    ])
    assert sugestoes.ACOES


def test_relatorio_consolidado_com_totais_funcionarios_e_acoes(cli, con, postos):
    cid = banco.registrar_coleta(con, postos["f_doze"], ontem(), "ok", 12, Decimal("1000.00"), None)
    banco.salvar_total_webposto(con, cid, Decimal("982.70"))
    _divergencias_exemplo(con, postos["doze"])
    _logado(cli)
    assert f'/premmia/{postos["doze"]}/conciliacao' in cli.get("/premmia").text
    html = cli.get(f"/premmia/{postos['doze']}/conciliacao").text
    for trecho in ("R$ 1.000,00", "R$ 982,70", "R$ 17,30", "JOSÉ (7)", "MARIA (9)", "Incluir no webPosto · 1",
                   "Excluir do webPosto · 1", "abastecido 3 min antes", "bico 4"):
        assert trecho in html, trecho
    so_excluir = cli.get(f"/premmia/{postos['doze']}/conciliacao?acao=excluir").text
    assert "possível divergência de caixa" in so_excluir and "Venda no Premmia sem lançamento" not in so_excluir


def test_relatorio_em_planilha(cli, con, postos):
    from openpyxl import load_workbook
    import io
    cid = banco.registrar_coleta(con, postos["f_doze"], ontem(), "ok", 12, Decimal("1000.00"), None)
    banco.salvar_total_webposto(con, cid, Decimal("982.70"))
    _divergencias_exemplo(con, postos["doze"])
    _logado(cli)
    r = cli.get(f"/premmia/{postos['doze']}/conciliacao.xlsx")
    assert r.status_code == 200 and "Conciliacao_Premmia_Doze" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Resumo", "Por funcionário", "Por dia", "Ocorrências"]
    linhas = list(wb["Ocorrências"].iter_rows(values_only=True))
    assert linhas[1][1] == "Incluir no webPosto" and "abastecido 3 min antes" in linhas[1][8]


def test_periodo_do_relatorio_limitado_a_90_dias(cli, postos):
    _logado(cli)
    html = cli.get(f"/premmia/{postos['doze']}/conciliacao?inicio=2026-01-01&fim=2026-12-31").text
    assert "vai até 90 dias" in html


def test_tolerancia_configuravel_so_admin(cli, con, postos):
    csrf = _logado(cli)
    r = cli.post("/premmia/tolerancias", data={"csrf": csrf, "janela": "25", "relogio": "3",
                                               "volta": f"/premmia/{postos['doze']}/conciliacao"})
    assert r.status_code == 303 and banco.tolerancias(con) == (25, 3)
    assert cli.post("/premmia/tolerancias", data={"csrf": csrf, "janela": "0", "relogio": "3"}).status_code == 400


def test_conferente_nao_ve_conciliacao_de_outro_posto(cli, postos):
    _logado(cli, "bia")
    assert cli.get(f"/premmia/{postos['doze']}/conciliacao").status_code == 403


def test_dia_com_diferenca_mostra_os_dois_totais(cli, con, postos):
    cid = banco.registrar_coleta(con, postos["f_doze"], ontem(), "ok", 12, Decimal("1922.43"), None)
    banco.salvar_total_webposto(con, cid, Decimal("1822.09"))
    _divergencias_exemplo(con, postos["doze"])
    _logado(cli)
    cartao = cli.get("/premmia").text
    assert "Premmia <b>R$ 1.922,43</b> · lançado no webPosto <b>R$ 1.822,09</b>" in cartao
    assert "R$ 100,34" in cartao and "diferença com o webPosto" in cartao
    conc = cli.get(f"/premmia/{postos['doze']}/conciliacao").text
    assert "Dias com diferença (1)" in conc and "R$ 1.922,43" in conc and "R$ 1.822,09" in conc
    assert f"{ontem():%d/%m/%Y} · Premmia R$ 1.922,43 · webPosto R$ 1.822,09 · diferença" in conc


def test_dia_sem_diferenca_nao_mostra_alerta(cli, con, postos):
    cid = banco.registrar_coleta(con, postos["f_doze"], ontem(), "ok", 11, Decimal("792.79"), None)
    banco.salvar_total_webposto(con, cid, Decimal("792.79"))
    _logado(cli)
    assert "lançado no webPosto" not in cli.get("/premmia").text
    assert "Nenhum dia com diferença" in cli.get(f"/premmia/{postos['doze']}/conciliacao").text


def test_trocar_o_usuario_do_premmia_apaga_o_que_veio_do_login_antigo(cli, con, postos, monkeypatch):
    async def falso(con, **kw):
        return []

    monkeypatch.setattr(rotina, "executar", falso)
    banco.registrar_coleta(con, postos["f_doze"], ontem(), "ok", 15, Decimal("1640.79"), None)
    unidade = unidades.do_posto(con, banco.obter_posto(con, postos["doze"]))
    premmia_portal.acrescentar_coleta(unidade, [], [ontem()], caminhos.premmia(postos["doze"]))
    csrf = _logado(cli)
    cli.post(f"/premmia/{postos['doze']}/ligar", data={"csrf": csrf, "usuario": "u", "senha": ""})  # mesmo usuário
    assert con.execute("SELECT COUNT(*) FROM coleta").fetchone()[0] == 1
    cli.post(f"/premmia/{postos['doze']}/ligar", data={"csrf": csrf, "usuario": "outro-usuario", "senha": "x"})
    assert con.execute("SELECT COUNT(*) FROM coleta").fetchone()[0] == 0
    assert not list(caminhos.premmia(postos["doze"]).glob("*.xlsx"))
