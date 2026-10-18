import asyncio
from datetime import date, datetime
from decimal import Decimal

import pytest

from apps.match import banco, coletas, credenciais, unidades
from src.modules.cash_reconciliation import config as cfg
from src.modules.cash_reconciliation.adapters import pagbank_edi, premmia_portal
from src.modules.cash_reconciliation.application import conciliar_cartoes
from src.modules.cash_reconciliation.domain.cartoes import CartaoErp, TransacaoAdquirente
from src.modules.cash_reconciliation.domain.tempo import FUSO

DIA = date(2026, 10, 17)


def _t(adquirente, nsu, valor, dia=DIA):
    return TransacaoAdquirente(adquirente=adquirente, identificador=f"{adquirente}-{nsu}-{dia}",
                               nsu=nsu, autorizacao=None, valor=Decimal(valor),
                               momento=datetime(dia.year, dia.month, dia.day, 14, 5, tzinfo=FUSO))


def _cartao(codigo, nsu, valor, administradora):
    return CartaoErp(codigo=codigo, empresa_codigo=74014, venda_codigo=codigo, valor=Decimal(valor),
                     momento=datetime(2026, 10, 17, 14, 5, tzinfo=FUSO), administradora=administradora,
                     nsu=nsu, nsu_tef=None, autorizacao=None, frentista=42, nome_frentista="JOÃO")


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "t.db")
    cfg.definir_provedor_unidades(lambda: unidades.montar(c))
    yield c
    cfg.definir_provedor_unidades(None)
    c.close()


def _posto(con, *, chave=True, premmia=True, pagbank=True):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    if premmia:
        banco.salvar_fonte(con, pid, "premmia", True, {})
    if pagbank:
        banco.salvar_fonte(con, pid, "pagbank_edi", True, {})
    banco.salvar_fonte(con, pid, "webposto", True, {})
    if chave:
        credenciais.salvar(f"{pid}/webposto/chave", "K")
    return pid


@pytest.fixture
def adaptadores(monkeypatch):
    chamadas = {"coletar": [], "liberar": [], "contexto": 0, "pagbank": [], "ordem": []}
    estado = {"premmia": [_t("PREMMIA", "P1", "50.00")],
              "pagbank": {DIA: [_t("PAGBANK", "123", "150.00")]},
              "cartoes": [_cartao(1, "P1", "50.00", "PREMMIA"), _cartao(2, "999", "80.00", "PAGSEGURO")],
              "erro_pagbank": None, "erro_premmia": None}

    async def coletar(unidade, *, ate=None, visivel=False, diretorio=None):
        chamadas["coletar"].append((unidade.empresa_codigo, ate, visivel, diretorio))
        chamadas["ordem"].append("coletar")
        if estado["erro_premmia"]:
            raise estado["erro_premmia"]

    def buscar_premmia(unidade, dia, diretorio=None):
        return list(estado["premmia"])

    def liberar(unidade, diretorio):
        chamadas["liberar"].append((unidade.empresa_codigo, diretorio))
        chamadas["ordem"].append("liberar")

    async def buscar_pagbank(emp, dia):
        chamadas["pagbank"].append(dia)
        if estado["erro_pagbank"]:
            raise estado["erro_pagbank"]
        return list(estado["pagbank"].get(dia, []))

    async def contexto(emp, dia):
        chamadas["contexto"] += 1
        return list(estado["cartoes"]), [], set()

    monkeypatch.setattr(premmia_portal, "coletar", coletar)
    monkeypatch.setattr(premmia_portal, "buscar_transacoes", buscar_premmia)
    monkeypatch.setattr(premmia_portal, "liberar_nova_tentativa", liberar)
    monkeypatch.setattr(pagbank_edi, "buscar_transacoes", buscar_pagbank)
    monkeypatch.setattr(conciliar_cartoes, "coletar_contexto_cartoes", contexto)
    return chamadas, estado


def _rodar(con, pid, **kw):
    return {r.fonte: r for r in asyncio.run(coletas.coletar_posto(con, pid, DIA, **kw))}


def test_compara_e_grava_divergencias(con, adaptadores):
    pid = _posto(con)
    res = _rodar(con, pid)
    assert res["premmia"].situacao == "ok" and res["premmia"].divergencias == []
    pag = res["pagbank_edi"]
    assert pag.situacao == "ok" and pag.qtd == 1 and pag.total == Decimal("150.00")
    assert pag.dia == DIA and pag.posto_id == pid
    assert sorted(d["tipo"] for d in pag.divergencias) == ["falta_no_webposto", "sobra_no_webposto"]
    assert sorted(adaptadores[0]["pagbank"]) == [date(2026, 10, 16), DIA, date(2026, 10, 18)]
    linhas = con.execute("SELECT fonte, tipo FROM divergencia ORDER BY tipo").fetchall()
    assert [(r["fonte"], r["tipo"]) for r in linhas] == [
        ("pagbank_edi", "falta_no_webposto"), ("pagbank_edi", "sobra_no_webposto")]
    assert con.execute("SELECT COUNT(*) FROM transacao").fetchone()[0] == 2
    assert {r["situacao"] for r in con.execute("SELECT situacao FROM coleta")} == {"ok"}


def test_erro_numa_fonte_nao_para_as_outras(con, adaptadores):
    pid = _posto(con)
    adaptadores[1]["erro_pagbank"] = pagbank_edi.PagBankCredencialInvalida("token=abc")
    res = _rodar(con, pid)
    assert len(res) == 2
    assert res["pagbank_edi"].situacao == "erro"
    assert res["pagbank_edi"].mensagem == "PagBank recusou o usuário/token. Confira em Fontes do posto."
    assert res["premmia"].situacao == "ok"
    erro = con.execute("SELECT situacao, erro_texto FROM coleta c JOIN fonte f ON f.id=c.fonte_id"
                       " WHERE f.tipo='pagbank_edi'").fetchone()
    assert erro["situacao"] == "erro" and "abc" not in erro["erro_texto"]


def test_dia_sem_movimento(con, adaptadores):
    pid = _posto(con, premmia=False)
    adaptadores[1]["pagbank"] = {}
    adaptadores[1]["cartoes"] = []
    [r] = asyncio.run(coletas.coletar_posto(con, pid, DIA))
    assert r.situacao == "sem_movimento" and r.qtd == 0 and r.total == Decimal(0)
    assert "sem vendas registradas" in r.mensagem


def test_posto_sem_chave_webposto_nao_compara(con, adaptadores):
    pid = _posto(con, chave=False)
    res = _rodar(con, pid)
    assert {r.situacao for r in res.values()} == {"sem_comparacao"}
    assert adaptadores[0]["contexto"] == 0
    assert all(r.divergencias == [] for r in res.values())
    assert {r["situacao"] for r in con.execute("SELECT situacao FROM coleta")} == {"ok"}


def test_sem_empresa_codigo_nao_compara(con, adaptadores):
    pid = _posto(con)
    con.execute("UPDATE posto SET empresa_codigo_webposto=NULL WHERE id=?", (pid,))
    res = _rodar(con, pid)
    assert {r.situacao for r in res.values()} == {"sem_comparacao"}
    assert adaptadores[0]["contexto"] == 0


def test_verificacao_humana(con, adaptadores):
    pid = _posto(con)
    adaptadores[1]["erro_premmia"] = premmia_portal.PremmiaVerificacaoHumana()
    res = _rodar(con, pid)
    assert res["premmia"].situacao == "verificacao_humana"
    assert res["premmia"].mensagem == "O Premmia pediu verificação humana. Clique em Coletar agora (visível)."
    assert res["pagbank_edi"].situacao == "ok"


def test_visivel_libera_travas(con, adaptadores, tmp_path):
    pid = _posto(con)
    _rodar(con, pid, visivel=True)
    chamadas = adaptadores[0]
    diretorio = tmp_path / "dados" / "premmia" / str(pid)
    assert chamadas["liberar"] == [(74014, diretorio)]
    assert chamadas["coletar"] == [(74014, DIA, True, diretorio)]
    assert chamadas["ordem"] == ["liberar", "coletar"]


def test_so_falhas_pula_ok(con, adaptadores):
    pid = _posto(con)
    adaptadores[1]["erro_pagbank"] = pagbank_edi.PagBankErro("x")
    _rodar(con, pid)
    adaptadores[1]["erro_pagbank"] = None
    adaptadores[0]["coletar"].clear()
    res = _rodar(con, pid, so_falhas=True)
    assert list(res) == ["pagbank_edi"] and res["pagbank_edi"].situacao == "ok"
    assert adaptadores[0]["coletar"] == []


def test_coletar_todos_percorre_postos_ativos(con, adaptadores):
    pid = _posto(con, chave=False)
    outro = banco.inserir_posto(con, "Inativo", None, None, 1)
    banco.salvar_fonte(con, outro, "pagbank_edi", True, {})
    con.execute("UPDATE posto SET ativo=0 WHERE id=?", (outro,))
    resultados = asyncio.run(coletas.coletar_todos(con, DIA))
    assert {r.posto_id for r in resultados} == {pid} and len(resultados) == 2


MSG_ATRASO = ("O PagBank ainda não mostra vendas de 17/10/2026, mas o webPosto tem cartões lançados."
              " Nova tentativa na repescagem.")


def test_pagbank_vazio_com_cartoes_no_webposto_vira_erro_e_repesca(con, adaptadores):
    pid = _posto(con, premmia=False)
    banco.gravar_divergencias(con, pid, DIA, "pagbank_edi", [{"tipo": "antiga"}])
    adaptadores[1]["pagbank"] = {}
    [r] = asyncio.run(coletas.coletar_posto(con, pid, DIA))
    assert r.situacao == "erro" and r.mensagem == MSG_ATRASO and r.divergencias == []
    assert con.execute("SELECT COUNT(*) FROM divergencia").fetchone()[0] == 0
    coleta = con.execute("SELECT situacao, erro_texto FROM coleta").fetchone()
    assert (coleta["situacao"], coleta["erro_texto"]) == ("erro", MSG_ATRASO)
    adaptadores[1]["pagbank"] = {DIA: [_t("PAGBANK", "999", "80.00")]}
    [r] = asyncio.run(coletas.coletar_posto(con, pid, DIA, so_falhas=True))
    assert r.situacao == "ok" and r.divergencias == []


def test_pagbank_vazio_sem_cartoes_pagbank_e_sem_movimento(con, adaptadores):
    pid = _posto(con, premmia=False)
    adaptadores[1]["pagbank"] = {}
    adaptadores[1]["cartoes"] = [_cartao(1, "P1", "50.00", "PREMMIA")]
    [r] = asyncio.run(coletas.coletar_posto(con, pid, DIA))
    assert r.situacao == "sem_movimento" and "sem vendas registradas" in r.mensagem


def test_premmia_vazio_com_cartoes_premmia_vira_erro(con, adaptadores):
    pid = _posto(con, pagbank=False)
    adaptadores[1]["premmia"] = []
    [r] = asyncio.run(coletas.coletar_posto(con, pid, DIA))
    assert r.situacao == "erro" and r.mensagem.startswith("O Premmia ainda não mostra vendas de 17/10/2026")


def test_falha_na_gravacao_vira_erro_da_fonte(con, adaptadores, monkeypatch):
    pid = _posto(con)
    original = banco.gravar_transacoes

    def falha(con_, coleta_id, posto_id, fonte, transacoes):
        if fonte == "premmia":
            raise RuntimeError("disco")
        return original(con_, coleta_id, posto_id, fonte, transacoes)

    monkeypatch.setattr(banco, "gravar_transacoes", falha)
    res = _rodar(con, pid)
    assert res["premmia"].situacao == "erro" and res["pagbank_edi"].situacao == "ok"


def test_posto_inexistente_ou_inativo_retorna_vazio(con, adaptadores):
    pid = _posto(con)
    assert asyncio.run(coletas.coletar_posto(con, 999, DIA)) == []
    con.execute("UPDATE posto SET ativo=0 WHERE id=?", (pid,))
    assert asyncio.run(coletas.coletar_posto(con, pid, DIA)) == []


def test_coletar_todos_isola_posto_com_falha(con, adaptadores, monkeypatch):
    ruim = _posto(con, chave=False)
    bom = banco.inserir_posto(con, "Zeta", "Zeta", None, 5)
    banco.salvar_fonte(con, bom, "pagbank_edi", True, {})
    original = coletas.coletar_posto

    async def talvez_falha(con_, posto_id, dia, **kw):
        if posto_id == ruim:
            raise RuntimeError("token=abc")
        return await original(con_, posto_id, dia, **kw)

    monkeypatch.setattr(coletas, "coletar_posto", talvez_falha)
    resultados = asyncio.run(coletas.coletar_todos(con, DIA))
    por_posto = {(r.posto_id, r.fonte): r.situacao for r in resultados}
    assert por_posto[(ruim, "premmia")] == "erro" and por_posto[(ruim, "pagbank_edi")] == "erro"
    assert (bom, "pagbank_edi") in por_posto
    assert all("abc" not in r.mensagem for r in resultados)
