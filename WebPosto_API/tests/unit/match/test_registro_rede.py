import json
import os
from pathlib import Path

import pytest

from apps.match import banco, registro_rede as rr


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "local"))
    (tmp_path / "local").mkdir()
    c = banco.conectar(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture
def rede(tmp_path):
    p = tmp_path / "rede"
    p.mkdir()
    return p


def _grava(rede, nome, **campos):
    d = rr.pasta_postos(rede)
    d.mkdir(parents=True, exist_ok=True)
    base = dict(id_instalacao="A", maquina="PC-A", usuario_windows="u",
                posto_nome="Doze", registrado_em="2026-10-01T12:00:00+00:00")
    base.update(campos)
    (d / nome).write_text(json.dumps(base), encoding="utf-8")


def test_chave_por_codigo_cnpj_ou_nada(con):
    banco.inserir_posto(con, "A", None, "12.345.678/0001-90", 74014)
    banco.inserir_posto(con, "B", None, "12.345.678/0001-90", None)
    banco.inserir_posto(con, "C", None, None, None)
    a, b, c = banco.listar_postos(con)
    assert rr.chave_posto(a) == "74014"
    assert rr.chave_posto(b) == "12345678000190"
    assert rr.chave_posto(c) is None


def test_registrar_e_dono(rede):
    d = rr.registrar(rede, "74014", "A", "Doze")
    assert rr.dono(rede, "74014") == d
    assert d.id_instalacao == "A" and d.posto_nome == "Doze"
    assert rr.dono(rede, "999") is None


def test_outra_instalacao_bloqueia_com_mensagem(rede):
    _grava(rede, "74014.json", maquina="PC-A", registrado_em="2026-10-01T12:00:00+00:00")
    with pytest.raises(rr.PostoDeOutraMaquina) as e:
        rr.registrar(rede, "74014", "B", "Doze")
    assert rr.mensagem_bloqueio(e.value.dono) == (
        "Este posto já está cadastrado na máquina PC-A desde 01/10/2026 09:00. "
        "Desative lá ou use 'Assumir posto'.")


def test_reregistrar_proprio_mantem_data(rede):
    _grava(rede, "74014.json", id_instalacao="A")
    d = rr.registrar(rede, "74014", "A", "Doze")
    assert d.registrado_em == "2026-10-01T12:00:00+00:00"
    assert rr.dono(rede, "74014").registrado_em == "2026-10-01T12:00:00+00:00"


def test_copia_de_conflito_mais_antiga_vence(rede):
    _grava(rede, "74014.json", id_instalacao="B", registrado_em="2026-10-05T12:00:00+00:00")
    _grava(rede, "74014-PC-A.json", id_instalacao="A", registrado_em="2026-10-02T12:00:00+00:00")
    _grava(rede, "740140.json", id_instalacao="X", registrado_em="2020-01-01T00:00:00+00:00")
    assert rr.dono(rede, "74014").id_instalacao == "A"
    with pytest.raises(rr.PostoDeOutraMaquina):
        rr.registrar(rede, "74014", "B", "Doze")


def test_json_invalido_ignorado(rede):
    d = rr.pasta_postos(rede)
    d.mkdir(parents=True)
    (d / "74014.json").write_text("{nao é json", encoding="utf-8")
    (d / "74014-x.json").write_text(json.dumps({"id_instalacao": "A"}), encoding="utf-8")
    assert rr.dono(rede, "74014") is None
    assert rr.registrar(rede, "74014", "B", "Doze").id_instalacao == "B"


def test_pasta_inexistente_levanta_indisponivel(tmp_path):
    with pytest.raises(rr.PastaIndisponivel) as e:
        rr.dono(tmp_path / "nao_existe", "74014")
    assert str(e.value) == rr.MSG_INDISPONIVEL
    arquivo = tmp_path / "arq"
    arquivo.write_text("x")
    with pytest.raises(rr.PastaIndisponivel):
        rr.registrar(arquivo, "74014", "A", "Doze")


def test_assumir_sobrescreve_e_remove_copias(rede):
    _grava(rede, "74014.json", id_instalacao="A")
    _grava(rede, "74014-PC-A.json", id_instalacao="A")
    _grava(rede, "740140.json", id_instalacao="X")
    d = rr.assumir(rede, "74014", "B", "Doze")
    assert d.id_instalacao == "B" and d.registrado_em > "2026-10-02"
    assert rr.dono(rede, "74014").id_instalacao == "B"
    nomes = sorted(p.name for p in rr.pasta_postos(rede).iterdir())
    assert nomes == ["74014.json", "740140.json"]


def test_liberar_so_o_proprio(rede):
    rr.registrar(rede, "74014", "A", "Doze")
    assert rr.liberar(rede, "74014", "B") is False
    assert rr.dono(rede, "74014") is not None
    assert rr.liberar(rede, "74014", "A") is True
    assert rr.dono(rede, "74014") is None
    assert rr.liberar(rede, "74014", "A") is False


def test_registro_sem_segredos(rede):
    rr.registrar(rede, "74014", "A", "Doze")
    dados = json.loads((rr.pasta_postos(rede) / "74014.json").read_text(encoding="utf-8"))
    assert set(dados) == {"id_instalacao", "maquina", "usuario_windows", "posto_nome", "registrado_em"}
    assert not [p for p in rr.pasta_postos(rede).iterdir() if p.suffix != ".json"]


def test_migracao_4(con, tmp_path):
    assert banco.pasta_rede(con) is None
    banco.salvar_pasta_rede(con, str(tmp_path / "rede"))
    assert banco.pasta_rede(con) == Path(tmp_path / "rede")
    banco.salvar_pasta_rede(con, None)
    assert banco.pasta_rede(con) is None
    assert con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4


@pytest.mark.parametrize("chave", ["", "..", "74014/../x", "7401a", "-1", "74014.json"])
def test_chave_so_digitos(rede, chave):
    for chamada in (lambda: rr.dono(rede, chave),
                    lambda: rr.registrar(rede, chave, "A", "Doze"),
                    lambda: rr.assumir(rede, chave, "A", "Doze"),
                    lambda: rr.liberar(rede, chave, "A")):
        with pytest.raises(ValueError):
            chamada()
    assert not rr.pasta_postos(rede).exists()


def test_empate_de_data_desempata_por_id(rede):
    _grava(rede, "74014.json", id_instalacao="A", registrado_em="2026-10-02T12:00:00+00:00")
    _grava(rede, "74014-PC-B.json", id_instalacao="B", registrado_em="2026-10-02T09:00:00-03:00")
    assert rr.dono(rede, "74014").id_instalacao == "A"


def test_liberar_arquivo_sumido_nao_e_indisponivel(rede, monkeypatch):
    rr.registrar(rede, "74014", "A", "Doze")
    original = rr._ler
    chamadas = []

    def some(arq):
        d = original(arq)
        chamadas.append(1)
        if len(chamadas) > 1:  # o OneDrive remove o arquivo entre a leitura e a remoção
            arq.unlink()
        return d
    monkeypatch.setattr(rr, "_ler", some)
    assert rr.liberar(rede, "74014", "A") is True
