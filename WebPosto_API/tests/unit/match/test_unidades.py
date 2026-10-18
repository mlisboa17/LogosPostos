import json
from pathlib import Path

import pytest

from apps.match import banco, credenciais, unidades
from src.modules.cash_reconciliation import config as cfg
from src.shared import segredos

UNITS = Path(cfg.__file__).parent / "units.json"


@pytest.fixture
def con(tmp_path):
    c = banco.conectar(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _limpa():
    yield
    segredos.definir_resolvedor(None)
    cfg.definir_provedor_unidades(None)


def test_resolvedor_pagbank_por_empresa(con, keyring_falso):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    credenciais.salvar(f"{pid}/pagbank/token", "TOK")
    unidades.ativar(con)
    assert segredos.obter_segredo("PAGBANK_TOKEN_74014") == "TOK"


def test_resolvedor_lc_e_nome_desconhecido(con, keyring_falso, monkeypatch):
    pid = banco.inserir_posto(con, "Doze", None, None, 74014)
    credenciais.salvar(f"{pid}/webposto/chave", "K")
    credenciais.salvar(f"{pid}/premmia/usuario", "U")
    r = unidades.resolvedor(con)
    assert r(f"LC_{pid}_WEBPOSTO_CHAVE") == "K"
    assert r(f"LC_{pid}_PREMMIA_USUARIO") == "U"
    monkeypatch.setenv("OUTRO", "x")
    assert r("OUTRO") is None
    assert r("PAGBANK_TOKEN_99999") is None


def test_posto_sem_webposto_tem_codigo_negativo(con):
    pid = banco.inserir_posto(con, "Novo", None, None, None)
    u = unidades.montar(con)
    assert list(u) == [-pid]
    assert u[-pid].apelido == f"P{pid}"
    assert u[-pid].chave_env == f"LC_{pid}_WEBPOSTO_CHAVE"


def test_resolvedor_posto_codigo_negativo(con, keyring_falso):
    pid = banco.inserir_posto(con, "Novo", None, None, None)
    credenciais.salvar(f"{pid}/pagbank/usuario", "usr")
    assert unidades.resolvedor(con)(f"PAGBANK_USER_{-pid}") == "usr"


def test_montar_usa_fonte_premmia_e_administradoras(con):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    banco.salvar_fonte(con, pid, "premmia", True, {"administradoras": {"PREMMIA": ["PREMMIA"]}})
    u = unidades.montar(con)[74014]
    assert u.premmia_ativo is True
    assert u.administradoras == {"PREMMIA": ("PREMMIA",)}


def test_exportar_nao_tem_segredo(con, keyring_falso):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    banco.salvar_fonte(con, pid, "premmia", True, {"administradoras": {}})
    credenciais.salvar(f"{pid}/premmia/senha", "S3gr3d0!")
    assert "S3gr3d0!" not in json.dumps(unidades.exportar_config(con))


def test_exportar_importar_roundtrip(con, tmp_path):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    banco.salvar_fonte(con, pid, "webposto", True, {})
    dados = unidades.exportar_config(con)
    c2 = banco.conectar(tmp_path / "b.db")
    assert unidades.importar_config(c2, dados) == 1
    assert unidades.importar_config(c2, dados) == 0
    assert len(banco.fontes_do_posto(c2, banco.listar_postos(c2)[0]["id"])) == 1
    c2.close()


def test_importar_units_json_idempotente(con):
    n = unidades.importar_units_json(con, UNITS)
    assert n > 0
    assert unidades.importar_units_json(con, UNITS) == 0
    doze = next(p for p in banco.listar_postos(con) if p["empresa_codigo_webposto"] == 74014)
    fontes = {f["tipo"]: f for f in banco.fontes_do_posto(con, doze["id"])}
    assert set(fontes) == {"premmia", "pagbank_edi", "webposto"}
    assert not any(f["ativo"] for f in fontes.values())
    assert "PAGBANK" in json.loads(fontes["pagbank_edi"]["config_json"])["administradoras"]
