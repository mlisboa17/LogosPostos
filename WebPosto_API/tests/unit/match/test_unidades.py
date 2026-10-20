import json
import threading
from pathlib import Path

import pytest

from apps.match import banco, credenciais, relatorio_xlsx, unidades
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


def test_resolvedor_nao_cai_no_ambiente(con, keyring_falso, monkeypatch):
    pid = banco.inserir_posto(con, "Doze", None, None, 74014)
    monkeypatch.setenv(f"LC_{pid}_WEBPOSTO_CHAVE", "do-ambiente")
    monkeypatch.setenv("PAGBANK_TOKEN_74014", "do-ambiente")
    r = unidades.resolvedor(con)
    assert r(f"LC_{pid}_WEBPOSTO_CHAVE") is None
    assert r("PAGBANK_TOKEN_74014") is None


def test_exportar_nao_tem_segredo(con, keyring_falso):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    banco.salvar_fonte(con, pid, "premmia", True, {"administradoras": {}, "senha": "S-cfg"})
    banco.salvar_fonte(con, pid, "pagbank_edi", True, {})
    banco.salvar_fonte(con, pid, "webposto", True, {})
    credenciais.salvar(f"{pid}/premmia/senha", "S3gr3d0!")
    credenciais.salvar(f"{pid}/pagbank/token", "TOK-PB")
    credenciais.salvar(f"{pid}/webposto/chave", "CHAVE-WP")
    con.execute("INSERT INTO canal(tipo, config_json, ref_credencial) VALUES (?,?,?)",
                ("telegram", json.dumps({"chat_id": "1", "token": "TOK-TG"}), "canal/1/token"))
    credenciais.salvar("canal/1/token", "TOK-TG-KR")
    con.commit()
    saida = json.dumps(unidades.exportar_config(con))
    for segredo in ("S3gr3d0!", "TOK-PB", "CHAVE-WP", "TOK-TG", "TOK-TG-KR", "S-cfg", "ref_credencial"):
        assert segredo not in saida
    assert '"chat_id": "1"' in saida


def test_exportar_importar_roundtrip(con, tmp_path):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    banco.salvar_fonte(con, pid, "webposto", True, {})
    con.execute("INSERT INTO canal(tipo, config_json) VALUES (?,?)", ("telegram", '{"chat_id": "1"}'))
    con.commit()
    dados = unidades.exportar_config(con)
    c2 = banco.conectar(tmp_path / "b.db")
    assert unidades.importar_config(c2, dados) == 1
    assert unidades.importar_config(c2, dados) == 0
    assert len(banco.fontes_do_posto(c2, banco.listar_postos(c2)[0]["id"])) == 1
    assert c2.execute("SELECT COUNT(*) FROM canal").fetchone()[0] == 1
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


def test_resolvedor_e_provedor_funcionam_em_outra_thread(con, keyring_falso):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    credenciais.salvar(f"{pid}/pagbank/token", "TOK")
    unidades.ativar(con)
    saida = {}

    def trabalho():
        saida["tok"] = segredos.obter_segredo("PAGBANK_TOKEN_74014")
        saida["un"] = list(cfg.carregar_unidades())

    t = threading.Thread(target=trabalho)
    t.start()
    t.join()
    assert saida == {"tok": "TOK", "un": [74014]}


def test_validar_codigo(con):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    unidades.validar_codigo(con, None)
    unidades.validar_codigo(con, 74014, posto_id=pid)  # o próprio posto
    with pytest.raises(unidades.CodigoInvalido, match="Já existe um posto com esse código do webPosto."):
        unidades.validar_codigo(con, 74014)
    for ruim in (0, -1, -pid):
        with pytest.raises(unidades.CodigoInvalido, match="Código do webPosto inválido."):
            unidades.validar_codigo(con, ruim)


def test_do_posto_monta_a_unidade_do_proprio_posto(con):
    a = banco.inserir_posto(con, "A", "A", None, 74014)
    b = banco.inserir_posto(con, "B", "B", None, 74014)  # legado: duplicado no banco
    ub = unidades.do_posto(con, banco.obter_posto(con, b))
    assert ub.nome == "B" and ub.chave_env == f"LC_{b}_WEBPOSTO_CHAVE"
    assert unidades.codigo_em_conflito(con, banco.obter_posto(con, a))
    c = banco.inserir_posto(con, "C", "C", None, 5)
    assert not unidades.codigo_em_conflito(con, banco.obter_posto(con, c))


def test_importar_units_json_recusa_codigo_invalido_ou_repetido(con, tmp_path):
    arq = tmp_path / "u.json"
    arq.write_text(json.dumps({"unidades": [{"nome": "X", "empresa_codigo": 0}]}), encoding="utf-8")
    with pytest.raises(unidades.CodigoInvalido):
        unidades.importar_units_json(con, arq)
    arq.write_text(json.dumps({"unidades": [{"nome": "X", "empresa_codigo": 7},
                                            {"nome": "Y", "empresa_codigo": 7}]}), encoding="utf-8")
    with pytest.raises(unidades.CodigoInvalido):
        unidades.importar_units_json(con, arq)
    assert banco.listar_postos(con, so_ativos=False) == []


def test_importar_config_recusa_codigo_de_outro_posto(con):
    banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    with pytest.raises(unidades.CodigoInvalido, match="Já existe um posto"):
        unidades.importar_config(con, {"postos": [{"nome": "Outro", "empresa_codigo_webposto": 74014}]})
    with pytest.raises(unidades.CodigoInvalido, match="inválido"):
        unidades.importar_config(con, {"postos": [{"nome": "Neg", "empresa_codigo_webposto": -3}]})
    assert len(banco.listar_postos(con, so_ativos=False)) == 1


def test_importar_config_recusa_apelido_equivalente(con):
    banco.inserir_posto(con, "A", "Doze Filial", None, 1)
    dados = {"postos": [{"nome": "B", "apelido": "Doze_Filial", "empresa_codigo_webposto": 2}]}
    with pytest.raises(unidades.CodigoInvalido, match="apelido equivalente"):
        unidades.importar_config(con, dados)
    assert len(banco.listar_postos(con, so_ativos=False)) == 1
    dois = {"postos": [{"nome": "B", "apelido": "X Y", "empresa_codigo_webposto": 2},
                       {"nome": "C", "apelido": "X_Y", "empresa_codigo_webposto": 3}]}
    with pytest.raises(unidades.CodigoInvalido):
        unidades.importar_config(con, dois)
    assert len(banco.listar_postos(con, so_ativos=False)) == 1


def test_importar_units_recusa_apelido_equivalente(con, tmp_path):
    banco.inserir_posto(con, "A", "Doze Filial", None, 1)
    arq = tmp_path / "u.json"
    arq.write_text(json.dumps({"unidades": [
        {"nome": "B", "apelido": "Doze_Filial", "empresa_codigo": 2}]}), encoding="utf-8")
    with pytest.raises(unidades.CodigoInvalido, match="apelido equivalente"):
        unidades.importar_units_json(con, arq)
    assert len(banco.listar_postos(con, so_ativos=False)) == 1


def test_importar_config_tres_sem_apelido_ok(con):
    dados = {"postos": [{"nome": f"N{i}", "empresa_codigo_webposto": 10 + i} for i in range(3)]}
    assert unidades.importar_config(con, dados) == 3
    n = [p["id"] for p in banco.listar_postos(con, so_ativos=False)]
    assert len(n) == 3


def test_importar_config_apelido_colide_com_id_previsto(con):
    prox = relatorio_xlsx.proximo_id(con)
    dados = {"postos": [{"nome": "A", "apelido": f"P{prox + 1}", "empresa_codigo_webposto": 11},
                        {"nome": "B", "empresa_codigo_webposto": 12}]}
    with pytest.raises(unidades.CodigoInvalido, match="apelido equivalente"):
        unidades.importar_config(con, dados)
    assert banco.listar_postos(con, so_ativos=False) == []


def test_importar_pula_posto_de_outra_maquina(con, tmp_path):
    from apps.match import registro_rede as rr
    rede = tmp_path / "rede"
    rede.mkdir()
    banco.salvar_pasta_rede(con, str(rede))
    rr.registrar(rede, "9", "OUTRA", "Nove")
    dados = {"postos": [{"nome": "Nove", "empresa_codigo_webposto": 9},
                        {"nome": "Dez", "empresa_codigo_webposto": 10}]}
    pulados: list[str] = []
    assert unidades.importar_config(con, dados, pulados=pulados) == 1
    assert [p["nome"] for p in banco.listar_postos(con)] == ["Dez"]
    assert rr.dono(rede, "10").id_instalacao == banco.id_instalacao(con)
    assert pulados == ["Nove: " + rr.mensagem_bloqueio(rr.dono(rede, "9"))]
    codigos = [u["empresa_codigo"] for u in json.loads(UNITS.read_text(encoding="utf-8"))["unidades"]]
    rr.registrar(rede, str(codigos[0]), "OUTRA", "X")
    pulados = []
    n = unidades.importar_units_json(con, UNITS, pulados=pulados)
    assert n == len(codigos) - 1 and len(pulados) == 1
    assert codigos[0] not in {p["empresa_codigo_webposto"] for p in banco.listar_postos(con)}


def test_importar_pasta_indisponivel_nao_grava(con, tmp_path):
    from apps.match import registro_rede as rr
    banco.salvar_pasta_rede(con, str(tmp_path / "offline"))
    with pytest.raises(rr.PastaIndisponivel):
        unidades.importar_config(con, {"postos": [{"nome": "Dez", "empresa_codigo_webposto": 10}]})
    with pytest.raises(rr.PastaIndisponivel):
        unidades.importar_units_json(con, UNITS)
    assert banco.listar_postos(con, so_ativos=False) == []
