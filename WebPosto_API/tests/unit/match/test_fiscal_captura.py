import asyncio
from datetime import date
from pathlib import Path

import httpx
import pytest

from apps.match import banco, credenciais, unidades
from apps.match.fiscal import captura, repositorio as repo
from src.shared.segredos import definir_resolvedor

DADOS = Path(__file__).resolve().parents[1] / "fiscal_docs" / "dados"
XML_COMB = (DADOS / "nfe_combustivel.xml").read_bytes()
XML_PROD = (DADOS / "nfe_produto.xml").read_bytes()
CH_COMB = "26261011111111000191550010000123451000012345"
CH_PROD = "26261033333333000191550020000000771000000771"
CH_FALTA = "2" * 44
SEGREDO = "chave-secreta-xyz"
HOJE = date(2026, 11, 3)


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "t.db")
    definir_resolvedor(unidades.resolvedor(c))
    yield c
    definir_resolvedor(None)
    c.close()


def _empresa(con, *, chave=True):
    pid = banco.inserir_posto(con, "Doze", "doze", "52308604000284", 74014)
    banco.salvar_fonte(con, pid, "webposto", True, {})
    if chave:
        credenciais.salvar(f"{pid}/webposto/chave", SEGREDO)
    return repo.salvar_empresa(con, "52308604000284", "POSTO DOZE", "doze", "Abreu e Lima", "PE", pid)


def _nota(cod, chave):
    return {"codigo": cod, "chaveDocumento": chave, "cnpjFornecedor": "11111111000191",
            "razaoSocialFornecedor": "DISTRIB", "dataEmissao": "2026-10-20", "valor": 10}


class WebpostoFalso:
    def __init__(self):
        self.xmls = {CH_COMB: XML_COMB, CH_PROD: XML_PROD}
        self.lista = [_nota(1, CH_COMB), _nota(2, CH_PROD), _nota(3, CH_FALTA)]
        self.erro_lista = False

    def __call__(self, req):
        p = req.url.path
        if p.endswith("NOTAS_MANIFESTACAO"):
            if self.erro_lista:
                return httpx.Response(500, text=f"erro CHAVE={SEGREDO}")
            return httpx.Response(200, json={"ultimoCodigo": None, "resultados": self.lista})
        if p.endswith("/NOTAS_ENTRADA"):
            return httpx.Response(200, json={"ultimoCodigo": None, "resultados": [
                {"codigo": 1, "chaveDocumento": CH_COMB, "tipoFrete": "F", "valorFrete": 350, "cteNumero": "998"}]})
        chave = p.rsplit("/", 1)[-1]
        if chave in self.xmls:
            return httpx.Response(200, content=self.xmls[chave])
        return httpx.Response(404, text="XML não encontrado.")


def _capturar(con, eid, wp):
    async def go():
        async with httpx.AsyncClient(base_url="https://wp.teste", transport=httpx.MockTransport(wp)) as c:
            return await captura.capturar_empresa(con, eid, HOJE, client=c)
    return asyncio.run(go())


def test_xml_faltando_vira_so_resumo_e_depois_completa(con):
    eid = _empresa(con)
    wp = WebpostoFalso()
    r = _capturar(con, eid, wp)
    assert (r.situacao, r.novas, r.pendentes) == ("ok", 2, 1)
    assert con.execute("SELECT situacao FROM documento WHERE chave=?", (CH_FALTA,)).fetchone()[0] == "so_resumo"
    assert con.execute("SELECT cte_numero FROM documento WHERE chave=?", (CH_COMB,)).fetchone()[0] == "998"
    xml_falta = XML_PROD.replace(CH_PROD.encode(), CH_FALTA.encode())
    wp.xmls[CH_FALTA] = xml_falta
    r2 = _capturar(con, eid, wp)
    assert (r2.novas, r2.pendentes) == (1, 0)
    assert con.execute("SELECT situacao FROM documento WHERE chave=?", (CH_FALTA,)).fetchone()[0] == "autorizada"


def test_repetir_nao_duplica(con, tmp_path):
    eid = _empresa(con)
    wp = WebpostoFalso()
    _capturar(con, eid, wp)
    r = _capturar(con, eid, wp)
    assert r.novas == 0
    assert con.execute("SELECT COUNT(*) FROM documento").fetchone()[0] == 3
    indice = tmp_path / "dados" / "fiscal" / "52308604000284" / "indice.jsonl"
    assert len(indice.read_text(encoding="utf-8").splitlines()) == 2


def test_sem_chave(con):
    eid = _empresa(con, chave=False)
    r = _capturar(con, eid, WebpostoFalso())
    assert r.situacao == "sem_chave"
    assert r.mensagem == "Cadastre a chave do webPosto do posto para capturar as notas."


def test_erro_na_lista_sem_vazar_chave(con):
    eid = _empresa(con)
    wp = WebpostoFalso()
    wp.erro_lista = True
    r = _capturar(con, eid, wp)
    assert r.situacao == "erro"
    erro = con.execute("SELECT erro_texto FROM captura ORDER BY id DESC").fetchone()[0]
    assert SEGREDO not in erro and SEGREDO not in r.mensagem


def test_janela_primeira_vez_e_seguintes(con):
    eid = _empresa(con)
    assert captura.janela(con, eid, HOJE) == (date(2026, 10, 1), HOJE)
    repo.salvar_ultima_data_lida(con, eid, date(2026, 11, 2))
    assert captura.janela(con, eid, HOJE) == (date(2026, 10, 28), HOJE)


def test_capturar_todas_pula_empresa_sem_posto_e_pendentes(con, tmp_path, monkeypatch):
    eid = _empresa(con)
    repo.salvar_empresa(con, "33333333000191", "SEM POSTO", "x", None, "PE", None)
    chamadas = []

    async def falso(con_, empresa_id, hoje, *, client=None):
        chamadas.append(empresa_id)
        return captura.ResultadoCaptura(empresa_id, "ok", 0, 0, "")

    monkeypatch.setattr(captura, "capturar_empresa", falso)
    fabrica = lambda: banco.conectar(tmp_path / "t.db")
    assert [r.empresa_id for r in captura.capturar_todas(fabrica, HOJE)] == [eid]
    assert captura.capturar_todas(fabrica, HOJE, so_pendentes=True) == []


def test_so_resumo_fora_da_janela_e_tentado_pela_chave(con):
    from decimal import Decimal
    from src.modules.fiscal_docs.webposto_notas import NotaListada
    eid = _empresa(con)
    velha = XML_PROD.replace(CH_PROD.encode(), CH_FALTA.encode())
    repo.registrar_so_resumo(con, eid, NotaListada(chave=CH_FALTA, emitente_cnpj="3", emitente_nome="X",
                                                   emissao=date(2026, 6, 1), valor=Decimal(1)))
    repo.salvar_ultima_data_lida(con, eid, date(2026, 11, 2))
    wp = WebpostoFalso()
    wp.lista = []  # webPosto não lista mais a nota antiga
    wp.xmls[CH_FALTA] = velha
    r = _capturar(con, eid, wp)
    assert r.novas == 1
    assert con.execute("SELECT situacao FROM documento WHERE chave=?", (CH_FALTA,)).fetchone()[0] == "autorizada"


def test_uma_nota_ruim_nao_congela_a_empresa(con):
    eid = _empresa(con)
    wp = WebpostoFalso()
    wp.xmls[CH_PROD] = XML_PROD.replace(b'nItem="1"', b'nItem="x"')
    wp.lista = wp.lista + [{"codigo": 9, "chaveDocumento": "8" * 44}]  # sem dataEmissao
    r = _capturar(con, eid, wp)
    assert r.situacao == "ok"
    assert con.execute("SELECT situacao FROM documento WHERE chave=?", (CH_COMB,)).fetchone()[0] == "autorizada"
    assert con.execute("SELECT situacao FROM documento WHERE chave=?", (CH_PROD,)).fetchone()[0] == "so_resumo"
    assert repo.ultima_data_lida(con, eid) == HOJE
