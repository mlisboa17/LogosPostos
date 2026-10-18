from datetime import datetime, timedelta, timezone

import pytest

from apps.match import acesso
from apps.match.acesso import Acao, Perfil, pode
from apps.match.banco import conectar, inserir_posto

P1, P2 = 1, 2
T0 = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    assert inserir_posto(c, "Posto 1", "P1", "1", 1) == P1
    assert inserir_posto(c, "Posto 2", "P2", "2", 2) == P2
    yield c
    c.close()


def _user(con, perfil, postos, login=None):
    uid = acesso.criar_usuario(con, "Fulano", login or f"u_{perfil.value}", "senha-forte-1",
                               perfil, postos)
    return acesso.carregar_usuario(con, uid)


# (perfil, acao, no posto proprio?, esperado) - uma linha por celula da matriz 7A
MATRIZ = [
    (Perfil.ADMINISTRADOR, a, proprio, True) for a in Acao for proprio in (True, False)
] + [
    (Perfil.GERENTE, Acao.VER, True, True), (Perfil.GERENTE, Acao.VER, False, False),
    (Perfil.GERENTE, Acao.COLETAR, True, True), (Perfil.GERENTE, Acao.COLETAR, False, False),
    (Perfil.GERENTE, Acao.TROCAR_CREDENCIAL, True, True),
    (Perfil.GERENTE, Acao.TROCAR_CREDENCIAL, False, False),
    (Perfil.GERENTE, Acao.CADASTRAR_POSTO, True, False),
    (Perfil.GERENTE, Acao.CONFIGURAR, True, False),
    (Perfil.GERENTE, Acao.GERIR_USUARIOS, True, False),
    (Perfil.CONFERENTE, Acao.VER, True, True), (Perfil.CONFERENTE, Acao.VER, False, False),
    (Perfil.CONFERENTE, Acao.COLETAR, True, True),
    (Perfil.CONFERENTE, Acao.COLETAR, False, False),
    (Perfil.CONFERENTE, Acao.TROCAR_CREDENCIAL, True, False),
    (Perfil.CONFERENTE, Acao.CADASTRAR_POSTO, True, False),
    (Perfil.CONFERENTE, Acao.CONFIGURAR, True, False),
    (Perfil.CONFERENTE, Acao.GERIR_USUARIOS, True, False),
]


@pytest.mark.parametrize("perfil,acao,proprio,esperado", MATRIZ)
def test_matriz_de_acesso(con, perfil, acao, proprio, esperado):
    u = _user(con, perfil, [P1])
    posto = P1 if proprio else P2
    assert pode(u, acao, posto) is esperado


def test_posto_none(con):
    adm = _user(con, Perfil.ADMINISTRADOR, [], "a")
    ger = _user(con, Perfil.GERENTE, [P1], "g")
    ger0 = _user(con, Perfil.GERENTE, [], "g0")
    conf = _user(con, Perfil.CONFERENTE, [P1], "c")
    assert pode(adm, Acao.VER) and pode(ger, Acao.VER) and not pode(ger0, Acao.VER)
    assert pode(ger, Acao.TROCAR_CREDENCIAL) and not pode(conf, Acao.TROCAR_CREDENCIAL)
    assert not pode(ger, Acao.GERIR_USUARIOS)


def test_postos_visiveis(con):
    adm = _user(con, Perfil.ADMINISTRADOR, [], "a")
    assert acesso.postos_visiveis(con, adm) == [P1, P2]
    assert acesso.postos_visiveis(con, _user(con, Perfil.GERENTE, [P2], "g")) == [P2]


def test_senha_curta_recusa(con):
    with pytest.raises(ValueError, match="pelo menos 8 caracteres"):
        acesso.criar_usuario(con, "X", "x", "1234567", Perfil.GERENTE, [])


def test_hash_nao_e_a_senha(con):
    _user(con, Perfil.GERENTE, [P1], "g")
    h = con.execute("SELECT senha_hash FROM usuario WHERE login='g'").fetchone()[0]
    assert h.startswith("scrypt$") and "senha-forte-1" not in h


def test_autenticar_ok_e_desconhecido(con):
    _user(con, Perfil.GERENTE, [P1], "g")
    u = acesso.autenticar(con, "g", "senha-forte-1", T0)
    assert u["login"] == "g" and u["ultimo_acesso_em"] and pode(u, Acao.VER, P1)
    assert acesso.autenticar(con, "nao-existe", "x", T0) is None
    assert con.execute("SELECT COUNT(*) FROM usuario").fetchone()[0] == 1


def test_bloqueio_apos_5_falhas(con):
    _user(con, Perfil.GERENTE, [P1], "g")
    for _ in range(5):
        assert acesso.autenticar(con, "g", "errada-errada", T0) is None
    assert acesso.autenticar(con, "g", "senha-forte-1", T0) is None  # 6a, senha certa
    assert acesso.autenticar(con, "g", "senha-forte-1", T0 + timedelta(minutes=14)) is None
    assert acesso.autenticar(con, "g", "senha-forte-1", T0 + timedelta(minutes=16)) is not None


def test_sucesso_zera_falhas(con):
    _user(con, Perfil.GERENTE, [P1], "g")
    for _ in range(4):
        acesso.autenticar(con, "g", "errada-errada", T0)
    assert acesso.autenticar(con, "g", "senha-forte-1", T0) is not None
    assert acesso.autenticar(con, "g", "errada-errada", T0) is None
    assert acesso.autenticar(con, "g", "senha-forte-1", T0) is not None


def test_usuario_inativo_nao_pode(con):
    u = _user(con, Perfil.ADMINISTRADOR, [], "a")
    con.execute("UPDATE usuario SET ativo=0 WHERE id=?", (u["id"],))
    con.commit()
    u = acesso.carregar_usuario(con, u["id"])
    assert not pode(u, Acao.VER, P1) and acesso.postos_visiveis(con, u) == []
    assert acesso.autenticar(con, "a", "senha-forte-1", T0) is None


def test_primeiro_uso(con):
    assert acesso.precisa_primeiro_uso(con)
    _user(con, Perfil.GERENTE, [P1], "g")
    assert acesso.precisa_primeiro_uso(con)
    _user(con, Perfil.ADMINISTRADOR, [], "a")
    assert not acesso.precisa_primeiro_uso(con)


def test_redefinir_admin(con):
    assert acesso.redefinir_admin(con, "nova-senha-1") == "admin"
    assert acesso.autenticar(con, "admin", "nova-senha-1", T0)["perfil"] == "administrador"
    con.execute("UPDATE usuario SET ativo=0, perfil='conferente' WHERE login='admin'")
    con.commit()
    acesso.redefinir_admin(con, "outra-senha-2")
    u = acesso.autenticar(con, "admin", "outra-senha-2", T0)
    assert u["perfil"] == "administrador" and u["ativo"] == 1
    with pytest.raises(ValueError):
        acesso.redefinir_admin(con, "curta")


def test_registrar_trunca(con):
    acesso.registrar(con, None, "login", "x" * 900)
    assert len(con.execute("SELECT detalhe FROM log_acesso").fetchone()[0]) == 500


def test_pode_agora_reflete_mudancas_imediatas(con):
    u = _user(con, Perfil.GERENTE, [P1, P2], "g")
    assert acesso.pode_agora(con, u["id"], Acao.VER, P1)
    con.execute("DELETE FROM usuario_posto WHERE usuario_id=? AND posto_id=?", (u["id"], P1))
    con.commit()
    assert not acesso.pode_agora(con, u["id"], Acao.VER, P1)
    assert acesso.postos_visiveis_agora(con, u["id"]) == [P2]
    assert pode(u, Acao.VER, P1)  # snapshot antigo continua desatualizado
    con.execute("UPDATE usuario SET perfil='conferente' WHERE id=?", (u["id"],))
    con.commit()
    assert not acesso.pode_agora(con, u["id"], Acao.TROCAR_CREDENCIAL, P2)
    con.execute("UPDATE usuario SET ativo=0 WHERE id=?", (u["id"],))
    con.commit()
    assert not acesso.pode_agora(con, u["id"], Acao.VER, P2)
    assert acesso.postos_visiveis_agora(con, u["id"]) == []
    assert not acesso.pode_agora(con, 9999, Acao.VER) and acesso.postos_visiveis_agora(con, 9999) == []


def test_pode_com_row_crua_falha_para_todos_os_perfis(con):
    _user(con, Perfil.ADMINISTRADOR, [], "a")
    crua = con.execute("SELECT * FROM usuario WHERE login='a'").fetchone()
    with pytest.raises(IndexError):
        pode(crua, Acao.VER, P1)


def test_agora_ingenuo_recusado(con):
    _user(con, Perfil.GERENTE, [P1], "g")
    with pytest.raises(ValueError, match="fuso horário"):
        acesso.autenticar(con, "g", "senha-forte-1", datetime(2026, 10, 18, 8, 0))


def test_timestamps_em_utc(con):
    from zoneinfo import ZoneInfo
    _user(con, Perfil.GERENTE, [P1], "g")
    acesso.autenticar(con, "g", "senha-forte-1", datetime(2026, 10, 18, 5, 0, tzinfo=ZoneInfo("America/Recife")))
    v = con.execute("SELECT ultimo_acesso_em FROM usuario").fetchone()[0]
    assert v.endswith("+00:00") and "08:00" in v


def test_login_normalizado(con):
    acesso.criar_usuario(con, "X", "  Maria ", "senha-forte-1", Perfil.GERENTE, [P1])
    assert con.execute("SELECT login FROM usuario").fetchone()[0] == "maria"
    assert acesso.autenticar(con, " MARIA", "senha-forte-1", T0) is not None


def test_login_desconhecido_gasta_hash(con, monkeypatch):
    chamadas = []
    orig = acesso._confere
    monkeypatch.setattr(acesso, "_confere", lambda s, h: chamadas.append(h) or orig(s, h))
    assert acesso.autenticar(con, "fantasma", "qualquer-coisa", T0) is None
    assert len(chamadas) == 1


def test_redefinir_admin_bloqueado_e_nome(con):
    acesso.redefinir_admin(con, "nova-senha-1")
    for _ in range(5):
        acesso.autenticar(con, "admin", "errada-errada", T0)
    assert acesso.autenticar(con, "admin", "nova-senha-1", T0) is None
    con.execute("UPDATE usuario SET nome='Outro' WHERE login='admin'")
    con.commit()
    acesso.redefinir_admin(con, "outra-senha-2")
    u = acesso.autenticar(con, "admin", "outra-senha-2", T0)
    assert u is not None and u["nome"] == "Administrador"
