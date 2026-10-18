"""Usuarios, senhas e niveis de acesso (spec 7A). Nunca registra segredo.

A sessao do painel guarda SOMENTE o usuario_id. A cada requisicao use `pode_agora` /
`postos_visiveis_agora`, que recarregam perfil, ativo e postos do banco. `pode` decide
sobre uma Row ja carregada (snapshot) e pode estar desatualizada.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from enum import Enum

from apps.match.banco import _agora

SENHA_MIN = 8
FALHAS_MAX = 5
BLOQUEIO = timedelta(minutes=15)
_SCRYPT = dict(n=2**14, r=8, p=1)

# A Row do usuario carrega a coluna `postos` (ids separados por virgula) para que
# `pode` decida sem acessar o banco.
_SELECT = ("SELECT u.*, (SELECT group_concat(posto_id) FROM usuario_posto"
           " WHERE usuario_id = u.id) AS postos FROM usuario u")


class Perfil(str, Enum):
    ADMINISTRADOR = "administrador"
    GERENTE = "gerente"
    CONFERENTE = "conferente"


class Acao(str, Enum):
    VER = "ver"
    COLETAR = "coletar"
    TROCAR_CREDENCIAL = "trocar_credencial"
    CADASTRAR_POSTO = "cadastrar_posto"
    CONFIGURAR = "configurar"
    GERIR_USUARIOS = "gerir_usuarios"


# Acoes que gerente/conferente podem fazer, apenas nos seus postos. O resto e so do admin.
_POR_POSTO = {
    Perfil.GERENTE.value: {Acao.VER, Acao.COLETAR, Acao.TROCAR_CREDENCIAL},
    Perfil.CONFERENTE.value: {Acao.VER, Acao.COLETAR},
}


def _postos_da_row(usuario) -> set[int]:
    bruto = usuario["postos"]
    return {int(p) for p in bruto.split(",")} if bruto else set()


def pode(usuario, acao: Acao, posto_id: int | None = None) -> bool:
    """Matriz 7A sobre uma Row carregada (snapshot: pode estar desatualizada; no painel
    use `pode_agora`). Exige a coluna `postos` de autenticar/carregar_usuario."""
    if usuario is None:
        return False
    postos = _postos_da_row(usuario)  # falha alto com Row crua, para qualquer perfil
    if not usuario["ativo"]:
        return False
    perfil = usuario["perfil"]
    if perfil == Perfil.ADMINISTRADOR.value:
        return True
    if acao not in _POR_POSTO.get(perfil, set()):
        return False
    return bool(postos) if posto_id is None else posto_id in postos


def postos_visiveis(con, usuario) -> list[int]:
    if usuario is None or not usuario["ativo"]:
        return []
    if usuario["perfil"] == Perfil.ADMINISTRADOR.value:
        return [r[0] for r in con.execute("SELECT id FROM posto ORDER BY id")]
    return [r[0] for r in con.execute(
        "SELECT posto_id FROM usuario_posto WHERE usuario_id=? ORDER BY posto_id",
        (usuario["id"],))]


def pode_agora(con, usuario_id: int, acao: Acao, posto_id: int | None = None) -> bool:
    return pode(carregar_usuario(con, usuario_id), acao, posto_id)


def postos_visiveis_agora(con, usuario_id: int) -> list[int]:
    return postos_visiveis(con, carregar_usuario(con, usuario_id))


def _hash(senha: str) -> str:
    sal = os.urandom(16)
    h = hashlib.scrypt(senha.encode("utf-8"), salt=sal, **_SCRYPT)
    return f"scrypt${sal.hex()}${h.hex()}"


def _confere(senha: str, guardado: str) -> bool:
    try:
        tipo, sal_hex, h_hex = guardado.split("$")
        if tipo != "scrypt":
            return False
        calc = hashlib.scrypt(senha.encode("utf-8"), salt=bytes.fromhex(sal_hex), **_SCRYPT)
        return hmac.compare_digest(calc, bytes.fromhex(h_hex))
    except (ValueError, TypeError):
        return False


_HASH_FALSO = "scrypt$" + "00" * 16 + "$" + "00" * 64


def _norm_login(login) -> str:
    return (login or "").strip().lower()


def _validar_senha(senha: str) -> None:
    if len(senha or "") < SENHA_MIN:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")


def carregar_usuario(con, usuario_id: int):
    return con.execute(_SELECT + " WHERE u.id=?", (usuario_id,)).fetchone()


def criar_usuario(con, nome, login, senha, perfil: Perfil, postos: list[int]) -> int:
    _validar_senha(senha)
    perfil = Perfil(perfil)
    try:
        cur = con.execute(
            "INSERT INTO usuario(nome, login, senha_hash, perfil, ativo, criado_em)"
            " VALUES (?,?,?,?,1,?)", (nome, _norm_login(login), _hash(senha), perfil.value, _agora()))
        uid = cur.lastrowid
        con.executemany("INSERT INTO usuario_posto(usuario_id, posto_id) VALUES (?,?)",
                        [(uid, int(p)) for p in dict.fromkeys(postos or [])])
        con.commit()
    except sqlite3.Error:
        con.rollback()
        raise
    return uid


def autenticar(con, login, senha, agora_: datetime):
    """Devolve a Row do usuario ou None. 5 falhas seguidas bloqueiam por 15 min."""
    if agora_.tzinfo is None:
        raise ValueError("agora_ precisa ter fuso horário")
    agora_ = agora_.astimezone(timezone.utc)
    linha = con.execute("SELECT id, senha_hash, ativo, bloqueado_ate"
                        " FROM usuario WHERE login=?", (_norm_login(login),)).fetchone()
    if linha is None or not linha["ativo"]:
        _confere(senha or "", _HASH_FALSO)  # custo igual, nao revela se o login existe
        return None
    if linha["bloqueado_ate"] and agora_ < datetime.fromisoformat(linha["bloqueado_ate"]):
        return None  # bloqueado: nao conta nova falha
    if not _confere(senha or "", linha["senha_hash"]):
        con.execute("UPDATE usuario SET tentativas_falhas = tentativas_falhas + 1 WHERE id=?",
                    (linha["id"],))
        con.execute("UPDATE usuario SET tentativas_falhas=0, bloqueado_ate=?"
                    " WHERE id=? AND tentativas_falhas >= ?",
                    ((agora_ + BLOQUEIO).isoformat(), linha["id"], FALHAS_MAX))
        con.commit()
        return None
    con.execute("UPDATE usuario SET tentativas_falhas=0, bloqueado_ate=NULL,"
                " ultimo_acesso_em=? WHERE id=?", (agora_.isoformat(), linha["id"]))
    con.commit()
    return carregar_usuario(con, linha["id"])


def precisa_primeiro_uso(con) -> bool:
    return con.execute("SELECT 1 FROM usuario WHERE perfil='administrador' AND ativo=1"
                       " LIMIT 1").fetchone() is None


def redefinir_admin(con, senha_nova: str) -> str:
    _validar_senha(senha_nova)
    existe = con.execute("SELECT id FROM usuario WHERE login='admin'").fetchone()
    if existe:
        con.execute("UPDATE usuario SET nome='Administrador', perfil='administrador', ativo=1, senha_hash=?,"
                    " tentativas_falhas=0, bloqueado_ate=NULL WHERE id=?",
                    (_hash(senha_nova), existe["id"]))
        con.commit()
    else:
        criar_usuario(con, "Administrador", "admin", senha_nova, Perfil.ADMINISTRADOR, [])
    return "admin"


def registrar(con, usuario_id: int | None, acao: str, detalhe: str = "") -> None:
    """Append em log_acesso. `detalhe` nunca deve receber segredo."""
    con.execute("INSERT INTO log_acesso(usuario_id, momento, acao, detalhe) VALUES (?,?,?,?)",
                (usuario_id, _agora(), acao, (detalhe or "")[:500]))
    con.commit()
