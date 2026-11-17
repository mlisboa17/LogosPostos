import re
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco, conferencia_dia
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
def doze(con):
    pid = banco.inserir_posto(con, "Posto Doze", "Doze", None, 74014)
    fp = banco.salvar_fonte(con, pid, "premmia", True, {})
    fb = banco.salvar_fonte(con, pid, "pagbank_edi", True, {})
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    return {"pid": pid, "premmia": fp, "pagbank": fb}


def _coleta(con, fonte, site, webposto, dia=None):
    cid = banco.registrar_coleta(con, fonte, dia or ontem(), "ok", 10, Decimal(site), None)
    banco.salvar_total_webposto(con, cid, Decimal(webposto))


def test_um_centavo_ja_e_divergente_e_o_sinal_diz_quem_e_maior(con, doze):
    _coleta(con, doze["premmia"], "10000.00", "10000.01")  # webPosto maior
    _coleta(con, doze["pagbank"], "5230.10", "5230.10")
    c = conferencia_dia.montar(con, doze["pid"], ontem())
    premmia, pagbank = c.blocos
    assert (premmia.diferenca, premmia.status) == (Decimal("0.01"), "DIVERGENTE")
    assert premmia.acao[0].startswith("WebPostos possui valor maior que o site")
    assert (pagbank.status, c.status, c.divergencia) == ("CONCILIADO", "DIVERGENTE", Decimal("0.01"))


def test_site_maior_e_dia_sem_coleta(con, doze):
    _coleta(con, doze["premmia"], "10000.00", "9800.00")
    c = conferencia_dia.montar(con, doze["pid"], ontem())
    assert c.blocos[0].diferenca == Decimal("-200.00") and c.blocos[0].acao[0].startswith("Site possui valor maior")
    assert c.blocos[1].status == "SEM DADOS" and "não coletado" in c.blocos[1].motivo_sem_dados


def test_tela_mostra_totais_status_e_so_as_divergencias(cli, con, doze):
    _coleta(con, doze["premmia"], "1922.43", "1822.09")
    _coleta(con, doze["pagbank"], "5230.10", "5230.10")
    banco.gravar_divergencias(con, doze["pid"], ontem(), "premmia", [
        {"tipo": "falta_no_webposto", "valor_esperado": Decimal("100.34"), "valor_encontrado": Decimal(0),
         "responsavel": "LENILSON (299249)", "acao": "incluir", "referencia": "Premmia NSU 884512",
         "explicacao_pt": "Venda no Premmia sem lançamento.", "correcao_pt": "Lançar no caixa de LENILSON (299249).",
         "dados": [{"lado": "Premmia", "administradora": "Premmia Crédito", "autorizacao": "A1", "nsu": "884512",
                    "valor": "R$ 100,34", "hora": "20:16", "funcionario": "LENILSON (299249)"}]}])
    tok = re.search(r'name="csrf" value="([^"]+)"', cli.get("/entrar").text).group(1)
    cli.post("/entrar", data={"login": "admin", "senha": SENHA, "csrf": tok})
    html = cli.get(f"/conferencia?posto_id={doze['pid']}").text
    assert f"DATA: {ontem():%d/%m/%Y}" in html and 'href="/conferencia"' in html
    for trecho in ("CONCILIAÇÃO PREMMIA", "WEBPOSTOS PREMMIA", "R$ 1.822,09", "PREMMIA SITE", "R$ 1.922,43",
                   "-R$ 100,34", "CONCILIAÇÃO PAGBANK", "CONCILIADO", "RESUMO GERAL", "TOTAL WEBPOSTOS",
                   "TOTAL SITES", "DIVERGENTE", "Quantidade: 1", "Encontrado apenas no Site", "NSU 884512",
                   "Site possui valor maior que o WebPostos"):
        assert trecho in html, trecho
    did = con.execute("SELECT id FROM divergencia").fetchone()[0]
    det = cli.get(f"/conferencia/ocorrencia/{did}").text
    assert "WEBPOSTOS" in det and "SITE (PREMMIA)" in det and "Nada encontrado aqui." in det
    assert "20:16" in det and "884512" in det and "AÇÃO NECESSÁRIA" in det and "Lançar no caixa de LENILSON" in det


def test_data_futura_vira_ontem_e_anterior(cli, con, doze):
    tok = re.search(r'name="csrf" value="([^"]+)"', cli.get("/entrar").text).group(1)
    cli.post("/entrar", data={"login": "admin", "senha": SENHA, "csrf": tok})
    html = cli.get(f"/conferencia?dia={(ontem() + timedelta(days=5)).isoformat()}").text
    assert f"DATA: {ontem():%d/%m/%Y}" in html and (ontem() - timedelta(days=1)).isoformat() in html


def test_cpf_aparece_mascarado():
    assert conferencia_dia._mascarar_cpf("123.456.789-01") == "***.456.789-**"
    assert conferencia_dia._mascarar_cpf(None) == "—"


def test_inicio_mostra_a_conferencia_de_ontem_de_cada_posto(cli, con, doze):
    _coleta(con, doze["premmia"], "1922.43", "1822.09")
    _coleta(con, doze["pagbank"], "5230.10", "5230.10")
    tok = re.search(r'name="csrf" value="([^"]+)"', cli.get("/entrar").text).group(1)
    cli.post("/entrar", data={"login": "admin", "senha": SENHA, "csrf": tok})
    html = cli.get("/").text
    assert f"Conferência de {ontem():%d/%m/%Y}" in html
    assert f'/conferencia?posto_id={doze["pid"]}&amp;dia={ontem().isoformat()}' in html
    assert "-R$ 100,34" in html and "✓ conciliado" in html and ">DIVERGENTE<" in html


def test_aviso_do_dia_no_formato_da_conferencia(con, doze):
    from apps.match.canais import envio
    _coleta(con, doze["premmia"], "1922.43", "1822.09")
    _coleta(con, doze["pagbank"], "5230.10", "5230.10")
    banco.gravar_divergencias(con, doze["pid"], ontem(), "premmia", [
        {"tipo": "falta_no_webposto", "valor_esperado": Decimal("100.34"), "valor_encontrado": Decimal(0),
         "referencia": "Premmia NSU 884512", "correcao_pt": "Lançar no caixa de LENILSON (299249).",
         "dados": [{"lado": "Premmia", "nsu": "884512"}]}])
    texto = envio.texto_resumo([], banco.obter_posto(con, doze["pid"]), ontem(), con=con)
    linhas = texto.splitlines()
    assert linhas[0] == f"Logos Match — Doze — {ontem():%d/%m/%Y} — DIVERGENTE"
    assert "❌ PREMMIA: DIVERGENTE · webPosto R$ 1.822,09 · site R$ 1.922,43 · diferença -R$ 100,34" in linhas
    assert any(l.startswith("✅ PAGBANK: CONCILIADO") for l in linhas)
    assert "Divergências a tratar: 1" in linhas
    assert any("NSU 884512: Encontrado apenas no Site" in l and "LENILSON" in l for l in linhas)
