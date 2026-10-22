from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.match import banco, caminhos
from src.modules.cash_reconciliation.domain.cartoes import TransacaoAdquirente

FUSO = ZoneInfo("America/Recife")


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    c = banco.conectar(tmp_path / "t.db")
    yield c
    c.close()


def _trans(ident="T1", valor="10.10"):
    return TransacaoAdquirente(
        adquirente="premmia", identificador=ident, nsu="123", autorizacao="A1",
        valor=Decimal(valor), momento=datetime(2026, 10, 17, 10, 30, tzinfo=FUSO),
        bandeira="VISA", terminal="SN1", situacao="ok",
    )


def _coleta(con):
    p = banco.inserir_posto(con, "Posto A", "A", "00.000.000/0001-00", 74014)
    f = banco.salvar_fonte(con, p, "premmia", True, {"x": 1})
    c = banco.registrar_coleta(con, f, "2026-10-17", "ok", 1, Decimal("10.10"), None)
    return p, f, c


def test_caminhos_respeitam_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "x"))
    assert caminhos.raiz() == tmp_path / "x" and caminhos.raiz().is_dir()
    assert caminhos.premmia(3) == tmp_path / "x" / "premmia" / "3"
    assert caminhos.planilhas().is_dir() and caminhos.logs().is_dir()


def test_migracao_idempotente(tmp_path):
    arq = tmp_path / "m.db"
    banco.conectar(arq).close()
    c = banco.conectar(arq)
    rows = c.execute("SELECT version FROM schema_version").fetchall()
    assert [r[0] for r in rows] == [1, 2, 3, 4]
    nomes = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"instalacao", "posto", "fonte", "coleta", "transacao", "caixa_webposto",
            "divergencia", "canal", "envio", "usuario", "usuario_posto", "log_acesso"} <= nomes
    c.close()


def test_fonte_tipo_invalido(con):
    p = banco.inserir_posto(con, "P", "p", "1", None)
    with pytest.raises(Exception):
        banco.salvar_fonte(con, p, "outro", True, {})


def test_transacao_repetida_ignorada(con):
    p, f, c = _coleta(con)
    assert banco.gravar_transacoes(con, c, p, "premmia", [_trans()]) == 1
    assert banco.gravar_transacoes(con, c, p, "premmia", [_trans()]) == 0
    assert con.execute("SELECT COUNT(*) FROM transacao").fetchone()[0] == 1


def test_coleta_mesmo_dia_atualiza(con):
    p, f, c1 = _coleta(con)
    c2 = banco.registrar_coleta(con, f, "2026-10-17", "erro", 0, Decimal("0"), "falhou")
    assert c1 == c2
    rows = con.execute("SELECT situacao, erro_texto FROM coleta").fetchall()
    assert len(rows) == 1 and rows[0]["situacao"] == "erro" and rows[0]["erro_texto"] == "falhou"


def test_valor_decimal_preservado(con):
    p, f, c = _coleta(con)
    banco.gravar_transacoes(con, c, p, "premmia", [_trans()])
    r = con.execute("SELECT valor, momento, forma, bandeira FROM transacao").fetchone()
    assert Decimal(r["valor"]) == Decimal("10.10") and r["valor"] == "10.10"
    assert r["momento"].startswith("2026-10-17T10:30:00") and "-03:00" in r["momento"]
    assert r["forma"] == "VISA" == r["bandeira"]
    tot = con.execute("SELECT total FROM coleta").fetchone()[0]
    assert Decimal(tot) == Decimal("10.10")


def test_gravar_divergencias_substitui(con):
    p, f, c = _coleta(con)
    item = dict(tipo="faltando", valor_esperado=Decimal("5.00"), valor_encontrado=Decimal("4.00"),
                nsu="9", caixa_codigo=7, responsavel="Joao (12)", explicacao_pt="e", correcao_pt="c")
    banco.gravar_divergencias(con, p, "2026-10-17", "premmia", [item, item])
    banco.gravar_divergencias(con, p, "2026-10-17", "premmia", [item])
    rows = con.execute("SELECT * FROM divergencia").fetchall()
    assert len(rows) == 1
    assert rows[0]["caixa_codigo"] == 7 and rows[0]["responsavel"] == "Joao (12)"
    assert rows[0]["valor_esperado"] == "5.00" and rows[0]["situacao"] == "aberta"


def test_postos_e_fontes(con):
    p = banco.inserir_posto(con, "P", "p", "1", None)
    assert [r["id"] for r in banco.listar_postos(con)] == [p]
    f = banco.salvar_fonte(con, p, "webposto", True, {"a": 1})
    assert banco.salvar_fonte(con, p, "webposto", False, {"a": 2}) == f
    fs = banco.fontes_do_posto(con, p)
    assert len(fs) == 1 and fs[0]["ativo"] == 0


def test_id_instalacao_estavel(con):
    a = banco.id_instalacao(con)
    assert a and banco.id_instalacao(con) == a


def test_migracao_3_de_banco_v2(tmp_path):
    import sqlite3
    caminho = tmp_path / "v2.db"
    raw = sqlite3.connect(str(caminho))
    raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    raw.executescript(banco._SCHEMA_V1 + banco._SCHEMA_V2)
    raw.executemany("INSERT INTO schema_version(version) VALUES (?)", [(1,), (2,)])
    raw.execute("INSERT INTO posto(nome, criado_em) VALUES ('Doze', 'x')")
    raw.execute("INSERT INTO canal(tipo) VALUES ('toast')")
    raw.execute("INSERT INTO envio(canal_id, dia) VALUES (1, '2026-10-17')")
    raw.commit()
    raw.close()
    con = banco.conectar(caminho)
    try:
        assert con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4
        assert con.execute("SELECT nome FROM posto").fetchone()[0] == "Doze"
        assert tuple(con.execute("SELECT dia, execucao_id FROM envio").fetchone()) == ("2026-10-17", None)
        eid = banco.abrir_execucao(con, "painel", None, "2026-10-17")
        banco.item_execucao(con, eid, 1, "premmia", "aguardando")
        banco.item_execucao(con, eid, 1, "premmia", "coletando")
        banco.item_execucao(con, eid, 1, "premmia", "ok", "feito")
        (item,) = banco.itens_execucao(con, eid)
        assert item["situacao"] == "ok" and item["iniciada_em"] and item["terminada_em"]
        with pytest.raises(sqlite3.IntegrityError):
            banco.abrir_execucao(con, "invalida", None, "2026-10-17")
    finally:
        con.close()
