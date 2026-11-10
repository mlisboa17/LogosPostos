"""Esqueci minha senha: código de 6 dígitos por e-mail, válido por 15 minutos e por uma única troca.

A resposta para quem pede é sempre a mesma, exista ou não o usuário (não revela quem tem conta).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from apps.match import acesso, banco
from apps.match.canais import email_smtp

logger = logging.getLogger(__name__)
VALIDADE = timedelta(minutes=15)
INTERVALO_REENVIO = timedelta(seconds=60)
TENTATIVAS_MAX = 5
MSG_ENVIADO = ("Se o usuário tiver e-mail cadastrado, enviamos um código de 6 dígitos para ele. "
               "Digite o código abaixo junto com a nova senha.")
MSG_SEM_EMAIL = ("Este Logos Match não tem e-mail configurado para enviar o código. Peça ao administrador "
                 "para trocar sua senha em Configurações → Usuários. Se você é o administrador, rode "
                 "LogosMatch.exe --redefinir-admin neste computador.")
_TEXTO = ("Seu código para criar uma nova senha no Logos Match é {codigo}.\n\n"
          "Ele vale por 15 minutos e só pode ser usado uma vez. Se não foi você que pediu, ignore este e-mail.")


def _canal(con):
    return next((c for c in banco.listar_canais(con) if c["tipo"] == "email" and c["ativo"]), None)


def disponivel(con) -> bool:
    return _canal(con) is not None


def _hash(sal: str, codigo: str) -> str:
    return hashlib.sha256(f"{sal}:{codigo}".encode()).hexdigest()


def _usuario(con, login_ou_email: str):
    alvo = (login_ou_email or "").strip().lower()
    if not alvo:
        return None
    return con.execute("SELECT * FROM usuario WHERE ativo=1 AND (login=? OR lower(email)=?)",
                       (alvo, alvo)).fetchone()


def pedir_codigo(con, login_ou_email: str, agora: datetime) -> int | None:
    """Gera e manda o código. Devolve o id do usuário quando mandou (uso interno e testes)."""
    canal, u = _canal(con), _usuario(con, login_ou_email)
    if canal is None or u is None or not u["email"]:
        return None
    atual = con.execute("SELECT criado_em FROM recuperacao_senha WHERE usuario_id=?", (u["id"],)).fetchone()
    if atual and datetime.fromisoformat(atual[0]) > agora - INTERVALO_REENVIO:
        return None  # já mandou há pouco
    codigo, sal = f"{secrets.randbelow(10**6):06d}", secrets.token_hex(16)
    con.execute("INSERT INTO recuperacao_senha(usuario_id, sal, codigo_hash, expira_em, tentativas, criado_em)"
                " VALUES (?,?,?,?,0,?) ON CONFLICT(usuario_id) DO UPDATE SET sal=excluded.sal,"
                " codigo_hash=excluded.codigo_hash, expira_em=excluded.expira_em, tentativas=0,"
                " criado_em=excluded.criado_em",
                (u["id"], sal, _hash(sal, codigo), (agora + VALIDADE).isoformat(), agora.isoformat()))
    con.commit()
    try:
        email_smtp.enviar_arquivos(canal, [u["email"]], "Logos Match: código para nova senha",
                                   _TEXTO.format(codigo=codigo), [])
    except Exception as exc:  # noqa: BLE001 - quem pediu vê a mesma mensagem; o admin vê no log
        logger.warning("Código de senha não enviado tipo=%s", type(exc).__name__)
        acesso.registrar(con, u["id"], "codigo_senha_falhou", "")
        return None
    acesso.registrar(con, u["id"], "codigo_senha_enviado", "")
    return u["id"]


def trocar_senha(con, login_ou_email: str, codigo: str, senha_nova: str, agora: datetime) -> int:
    """Confere o código e troca a senha. Mensagens de erro em português, prontas para a tela."""
    u = _usuario(con, login_ou_email)
    pedido = u and con.execute("SELECT * FROM recuperacao_senha WHERE usuario_id=?", (u["id"],)).fetchone()
    if not pedido or pedido["tentativas"] >= TENTATIVAS_MAX:
        raise ValueError("Código inválido. Peça um código novo.")
    if datetime.fromisoformat(pedido["expira_em"]) < agora:
        raise ValueError("O código venceu. Peça um código novo.")
    if not hmac.compare_digest(_hash(pedido["sal"], (codigo or "").strip()), pedido["codigo_hash"]):
        con.execute("UPDATE recuperacao_senha SET tentativas=tentativas+1 WHERE usuario_id=?", (u["id"],))
        con.commit()
        restam = TENTATIVAS_MAX - pedido["tentativas"] - 1
        raise ValueError(f"Código errado. Você ainda pode tentar {restam} vez(es)." if restam > 0
                         else "Código errado. Peça um código novo.")
    acesso.definir_senha(con, u["id"], senha_nova)  # valida o tamanho da senha
    con.execute("DELETE FROM recuperacao_senha WHERE usuario_id=?", (u["id"],))
    con.execute("DELETE FROM sessao_lembrada WHERE usuario_id=?", (u["id"],))
    con.commit()
    acesso.registrar(con, u["id"], "senha_recuperada", "")
    return u["id"]
