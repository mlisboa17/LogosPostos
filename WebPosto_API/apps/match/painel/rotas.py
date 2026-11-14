"""Rotas do painel local.

Segurança: a sessão (em memória) guarda só o usuario_id; cada requisição recarrega o
usuário e decide com `acesso.pode_agora` / `postos_visiveis_agora`. Todo POST exige o
campo `csrf`. Segredos nunca são exibidos nem registrados: a tela só mostra `••••`.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import jinja2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from apps.match import (acesso, agendador, banco, caminhos, coletas, credenciais, explicar, inicio,
                        premmia_tela, recuperar_senha, registro_rede, relatorio_premmia, relatorio_xlsx, rotina,
                        sugestoes, unidades)
from apps.match.acesso import Acao, Perfil
from apps.match.canais import envio
from apps.match.extratos import aprovacoes, autonomia, camada1, camada2, entrada, repositorio
from src.modules.cash_reconciliation import config as config_cr
from src.modules.cash_reconciliation.adapters import pagbank_edi, webposto_caixas
from src.modules.cash_reconciliation.domain.tempo import agora, formatar_data_hora, ontem

logger = logging.getLogger(__name__)

PASTA = Path(__file__).resolve().parent
COOKIE, COOKIE_PRE = "lm_sessao", "lm_pre"
EXPIRA_SEGUNDOS = 12 * 3600
LEMBRAR_SEGUNDOS = 7 * 24 * 3600
SEM_ACESSO = "Você não tem acesso a isto."
FORM_EXPIRADO = "Formulário expirado ou inválido. Recarregue a página e tente de novo."
AVISO_POSTO = "Cadastre cada posto em uma só máquina para evitar coleta duplicada."
COLETA_EM_ANDAMENTO = "Já existe uma coleta em andamento. Aguarde terminar."
MSG_CHAVE = ("Informe o código do webPosto ou o CNPJ para proteger este posto contra cadastro"
             " em duas máquinas.")
MSG_PASTA_INVALIDA = ("Pasta não encontrada ou sem permissão de escrita. Informe o caminho completo"
                      " de uma pasta que todas as máquinas enxergam.")
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_MAX_IMPORTAR = 1_000_000

_relogio = time.monotonic

# tipo da fonte -> (nome na tela, prefixo da credencial, campos secretos (chave, rótulo))
FONTES = {
    "premmia": ("Premmia", "premmia", (("usuario", "Usuário"), ("senha", "Senha"))),
    "pagbank_edi": ("PagBank EDI", "pagbank", (("usuario", "Usuário"), ("token", "Token"))),
    "webposto": ("webPosto", "webposto", (("chave", "Chave da API"),)),
}
_NOME_FONTE = {"premmia": "Premmia", "pagbank_edi": "PagBank", "webposto": "webPosto"}
_SEGREDO_CANAL = {"telegram": ("token", "Token do robô"), "email": ("senha", "Senha de app")}
_ICONE = {"ok": "✅", "sem_movimento": "⚠", "erro": "❌", "verificacao_humana": "❌"}

router = APIRouter()


# ---------------------------------------------------------------- sessões

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Sessoes:
    """token -> [usuario_id, último uso (monotônico), csrf, lembrada]. Em memória.

    Com "manter conectado", a sessão também vai para o banco (só o hash do token) e volta
    depois que o app reinicia, até 7 dias.
    """

    def __init__(self, con_factory=None):
        self._d: dict[str, list] = {}
        self._trava = threading.Lock()
        self._fab = con_factory

    def criar(self, usuario_id: int, lembrar: bool = False) -> str:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self._trava:
            self._d[token] = [usuario_id, _relogio(), csrf, lembrar]
        if lembrar and self._fab is not None:
            expira = datetime.now(timezone.utc) + timedelta(seconds=LEMBRAR_SEGUNDOS)
            self._no_banco("INSERT INTO sessao_lembrada VALUES (?,?,?,?)",
                           (_hash_token(token), usuario_id, csrf, expira.isoformat()))
        return token

    def _no_banco(self, sql: str, args: tuple, ler: bool = False):
        con = self._fab()
        try:
            if ler:
                return con.execute(sql, args).fetchone()
            con.execute(sql, args)
            con.commit()
        finally:
            con.close()

    def _do_banco(self, token: str) -> list | None:
        if self._fab is None:
            return None
        r = self._no_banco("SELECT usuario_id, csrf, expira_em FROM sessao_lembrada WHERE token_hash=?",
                           (_hash_token(token),), ler=True)
        if r is None or datetime.fromisoformat(r[2]) < datetime.now(timezone.utc):
            return None
        return [r[0], _relogio(), r[1], True]

    def obter(self, token: str | None) -> tuple[int, str] | None:
        if not token:
            return None
        with self._trava:
            s = self._d.get(token)
        if s is None:
            s = self._do_banco(token)
            if s is None:
                return None
            with self._trava:
                self._d[token] = s
        with self._trava:
            limite = LEMBRAR_SEGUNDOS if s[3] else EXPIRA_SEGUNDOS
            if _relogio() - s[1] > limite:
                self._d.pop(token, None)
                return None
            s[1] = _relogio()
            return s[0], s[2]

    def encerrar(self, token: str | None) -> None:
        with self._trava:
            self._d.pop(token or "", None)
        if token and self._fab is not None:
            self._no_banco("DELETE FROM sessao_lembrada WHERE token_hash=?", (_hash_token(token),))

    def encerrar_usuario(self, usuario_id: int, exceto: str | None = None) -> None:
        with self._trava:
            for tok in [t for t, s in self._d.items() if s[0] == usuario_id and t != exceto]:
                del self._d[tok]
        if self._fab is not None:
            manter = _hash_token(exceto) if exceto else ""
            self._no_banco("DELETE FROM sessao_lembrada WHERE usuario_id=? AND token_hash != ?",
                           (usuario_id, manter))


class Redirecionar(Exception):
    def __init__(self, url: str):
        self.url = url


class Recusado(Exception):
    def __init__(self, status: int, mensagem: str):
        self.status, self.mensagem = status, mensagem


async def tratar_redirecionar(request: Request, exc: Redirecionar):
    return RedirectResponse(exc.url, status_code=303)


async def tratar_recusado(request: Request, exc: Recusado):
    return _TPL.TemplateResponse(request, "erro.html", {"menu": [], "erro": exc.mensagem, "mensagem": None},
                                 status_code=exc.status)


# ---------------------------------------------------------------- templates

def _data(valor) -> str:
    if not valor:
        return "—"
    d = valor if isinstance(valor, date) else date.fromisoformat(str(valor)[:10])
    return f"{d:%d/%m/%Y}"


def _data_hora(valor) -> str:
    if not valor:
        return "—"
    try:
        return formatar_data_hora(datetime.fromisoformat(str(valor)))
    except ValueError:
        return "—"


_ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(str(PASTA / "templates")),
                          autoescape=True)
_ENV.filters.update(data=_data, data_hora=_data_hora,
                    dinheiro=lambda v: explicar.dinheiro(Decimal(str(v or 0))),
                    fonte=lambda t: _NOME_FONTE.get(t, t),
                    cnpj=lambda c: (f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if c and len(c) == 14 else c or ""))
_TPL = Jinja2Templates(env=_ENV)


# ---------------------------------------------------------------- dependências

@dataclass
class Ctx:
    request: Request
    con: sqlite3.Connection
    uid: int
    nome: str
    csrf: str
    token: str
    form: object = None

    def pode(self, acao: Acao, posto_id: int | None = None) -> bool:
        return acesso.pode_agora(self.con, self.uid, acao, posto_id)

    def exigir(self, acao: Acao, posto_id: int | None = None) -> None:
        if not self.pode(acao, posto_id):
            raise Recusado(403, SEM_ACESSO)

    def postos(self) -> list[int]:
        return acesso.postos_visiveis_agora(self.con, self.uid)


async def _conexao(request: Request):
    con = request.app.state.con_factory()
    try:
        yield con
    finally:
        con.close()


async def _ctx(request: Request, con=Depends(_conexao)) -> Ctx:
    sessoes: Sessoes = request.app.state.sessoes
    token = request.cookies.get(COOKIE)
    sessao = sessoes.obter(token)
    if sessao is None:
        raise Redirecionar("/entrar")
    uid, csrf = sessao
    usuario = acesso.carregar_usuario(con, uid)
    if usuario is None or not usuario["ativo"]:
        sessoes.encerrar(token)
        raise Redirecionar("/entrar")
    return Ctx(request, con, uid, usuario["nome"], csrf, token)


def _igual(a, b) -> bool:
    return isinstance(a, str) and isinstance(b, str) and bool(a) and hmac.compare_digest(a, b)


async def _ctx_post(ctx: Ctx = Depends(_ctx)) -> Ctx:
    ctx.form = await ctx.request.form()
    if not _igual(ctx.form.get("csrf"), ctx.csrf):
        raise Recusado(403, FORM_EXPIRADO)
    return ctx


def _txt(form, nome: str, *, cru: bool = False) -> str:
    v = form.get(nome)
    if not isinstance(v, str):
        return ""
    return v if cru else v.strip()


def _int(form, nome: str) -> int | None:
    try:
        return int(_txt(form, nome))
    except ValueError:
        return None


def _ints(form, nome: str) -> list[int]:
    return [int(v) for v in form.getlist(nome) if isinstance(v, str) and v.strip().isdigit()]


def _so_fiscal(ctx: Ctx) -> bool:
    """Perfil contabilidade: enxerga só o módulo de notas fiscais."""
    u = acesso.carregar_usuario(ctx.con, ctx.uid)
    return u is not None and u["perfil"] == Perfil.CONTABILIDADE.value


def _itens_configuracao(ctx: Ctx) -> list[tuple[str, str, str]]:
    itens = []
    if ctx.pode(Acao.GERIR_FISCAL):
        itens += [("/empresas", "Empresas", "CNPJs, certificados e ligação com os postos"),
                  ("/escritorios", "Escritórios", "Contabilidade: e-mails, dia do envio e formato")]
    if ctx.pode(Acao.CADASTRAR_POSTO) or ctx.pode(Acao.TROCAR_CREDENCIAL):
        itens.append(("/postos", "Postos", "Postos, Premmia, PagBank e chave do webPosto"))
    if ctx.pode(Acao.CONFIGURAR):
        itens += [("/canais", "Canais", "E-mail, Telegram e avisos do Windows"),
                  ("/agenda", "Agenda", "Horários da coleta"),
                  ("/extratos/autonomia", "Autonomia", "O que os extratos fazem sem pedir aprovação")]
    if ctx.pode(Acao.GERIR_USUARIOS):
        itens.append(("/usuarios", "Usuários", "Quem acessa e o que pode fazer"))
    return itens


def _menu(ctx: Ctx) -> list[tuple[str, str]]:
    if _so_fiscal(ctx):
        return [("/notas", "Notas fiscais"), ("/pacotes", "Pacotes")]
    itens = [("/", "Início")]
    if ctx.pode(Acao.GERIR_FISCAL):
        itens.append(("/comecar", "Buscar notas"))
    if ctx.pode(Acao.VER_FISCAL):
        itens.append(("/notas", "Notas fiscais"))
    itens.append(("/caixa", "Caixa"))
    itens.append(("/premmia", "Premmia"))
    if _itens_configuracao(ctx):
        itens.append(("/configuracoes", "Configurações"))
    return itens


def _pagina(ctx: Ctx, nome: str, status: int = 200, **dados):
    base = {"menu": _menu(ctx), "csrf": ctx.csrf, "usuario_nome": ctx.nome,
            "atual": ctx.request.url.path, "mensagem": None, "erro": None}
    return _TPL.TemplateResponse(ctx.request, nome, {**base, **dados}, status_code=status)


def _ir(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _posto_ou_404(ctx: Ctx, posto_id: int):
    posto = banco.obter_posto(ctx.con, posto_id)
    if posto is None:
        raise Recusado(404, "Posto não encontrado.")
    return posto


def _em_segundo_plano(nome: str, alvo, *args) -> threading.Thread:
    def rodar():
        try:
            alvo(*args)
        except Exception as exc:  # noqa: BLE001 - thread do painel nunca derruba o app
            logger.warning("Tarefa %s falhou tipo=%s", nome, type(exc).__name__)  # nunca a mensagem
    t = threading.Thread(target=rodar, name=f"logosmatch-{nome}", daemon=True)
    t.start()
    return t


def _com_conexao(con_factory, funcao):
    con = con_factory()
    try:
        return funcao(con)
    finally:
        con.close()


# ---------------------------------------------------------------- entrar / primeiro uso

def _publica(request: Request, nome: str, status: int = 200, **dados):
    tok = request.cookies.get(COOKIE_PRE) or secrets.token_urlsafe(32)
    resp = _TPL.TemplateResponse(request, nome, {"menu": [], "csrf": tok, "mensagem": None,
                                                 "erro": None, **dados}, status_code=status)
    resp.set_cookie(COOKIE_PRE, tok, httponly=True, samesite="strict", path="/")
    return resp


async def _form_publico(request: Request):
    form = await request.form()
    if not _igual(form.get("csrf"), request.cookies.get(COOKIE_PRE)):
        raise Recusado(403, FORM_EXPIRADO)
    return form


_TRAVA_PRIMEIRO_USO = threading.Lock()


@router.get("/entrar")
async def entrar_form(request: Request, con=Depends(_conexao), senha_alterada: int = 0):
    if acesso.precisa_primeiro_uso(con):
        return _ir("/primeiro-uso")
    return _publica(request, "entrar.html",
                    mensagem="Sua senha foi alterada. Entre com a senha nova." if senha_alterada else None)


@router.get("/esqueci")
async def esqueci_form(request: Request, con=Depends(_conexao)):
    return _publica(request, "esqueci.html", disponivel=recuperar_senha.disponivel(con),
                    msg_sem_email=recuperar_senha.MSG_SEM_EMAIL, pedido=False)


@router.post("/esqueci")
async def esqueci(request: Request, con=Depends(_conexao)):
    form = await _form_publico(request)
    login = _txt(form, "login")
    await run_in_threadpool(_com_conexao, request.app.state.con_factory,
                            lambda c: recuperar_senha.pedir_codigo(c, login, datetime.now(timezone.utc)))
    return _publica(request, "esqueci.html", disponivel=True, pedido=True, login=login,
                    mensagem=recuperar_senha.MSG_ENVIADO)


@router.post("/esqueci/codigo")
async def esqueci_codigo(request: Request, con=Depends(_conexao)):
    form = await _form_publico(request)
    login, senha = _txt(form, "login"), _txt(form, "senha", cru=True)
    erro = "As duas senhas não são iguais." if senha != _txt(form, "senha2", cru=True) else None
    if erro is None:
        try:
            uid = recuperar_senha.trocar_senha(con, login, _txt(form, "codigo"), senha, datetime.now(timezone.utc))
            request.app.state.sessoes.encerrar_usuario(uid)
            return _ir("/entrar?senha_alterada=1")
        except ValueError as exc:  # mensagens próprias, em português
            erro = str(exc)
    return _publica(request, "esqueci.html", status=400, disponivel=True, pedido=True, login=login, erro=erro)


@router.post("/entrar")
async def entrar(request: Request, con=Depends(_conexao)):
    form = await _form_publico(request)
    login = _txt(form, "login")
    usuario = acesso.autenticar(con, login, _txt(form, "senha", cru=True), agora())
    if usuario is None:
        existe = con.execute("SELECT id FROM usuario WHERE login=?", (login.lower(),)).fetchone()
        acesso.registrar(con, existe["id"] if existe else None, "login_falhou", "")
        return _publica(request, "entrar.html", status=401,
                        erro="Usuário ou senha incorretos. Depois de 5 tentativas erradas"
                             " o acesso fica bloqueado por 15 minutos.")
    sessoes: Sessoes = request.app.state.sessoes
    sessoes.encerrar(request.cookies.get(COOKIE))  # token novo a cada login
    lembrar = _txt(form, "lembrar") == "1"
    token = sessoes.criar(usuario["id"], lembrar=lembrar)
    acesso.registrar(con, usuario["id"], "entrar", "manter conectado" if lembrar else "")
    resp = _ir("/")
    resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/",
                    max_age=LEMBRAR_SEGUNDOS if lembrar else None)
    resp.delete_cookie(COOKIE_PRE, path="/")
    return resp


@router.get("/primeiro-uso")
async def primeiro_uso_form(request: Request, con=Depends(_conexao)):
    if not acesso.precisa_primeiro_uso(con):
        return _ir("/entrar")
    return _publica(request, "primeiro_uso.html")


@router.post("/primeiro-uso")
async def primeiro_uso(request: Request, con=Depends(_conexao)):
    form = await _form_publico(request)
    nome, login = _txt(form, "nome"), _txt(form, "login")
    senha, senha2 = _txt(form, "senha", cru=True), _txt(form, "senha2", cru=True)
    with _TRAVA_PRIMEIRO_USO:
        if not acesso.precisa_primeiro_uso(con):
            raise Recusado(403, "O administrador já foi criado. Entre com usuário e senha.")
        erro = None
        if not nome or not login:
            erro = "Preencha nome e usuário."
        elif senha != senha2:
            erro = "As duas senhas não são iguais."
        else:
            try:
                uid = acesso.criar_usuario(con, nome, login, senha, Perfil.ADMINISTRADOR, [])
            except ValueError as exc:  # mensagem própria, em português
                erro = str(exc)
        if erro:
            return _publica(request, "primeiro_uso.html", status=400, erro=erro, nome=nome, login=login)
    acesso.registrar(con, uid, "primeiro_uso", f"usuario={uid}")
    return _ir("/entrar")


@router.post("/sair")
async def sair(ctx: Ctx = Depends(_ctx_post)):
    ctx.request.app.state.sessoes.encerrar(ctx.token)
    acesso.registrar(ctx.con, ctx.uid, "sair", "")
    resp = _ir("/entrar")
    resp.delete_cookie(COOKIE, path="/")
    return resp


# ---------------------------------------------------------------- Hoje

def _texto_coleta(c) -> tuple[str, str]:
    if c is None:
        return "⚪", "ainda não coletado."
    situacao = c["situacao"]
    if situacao == "ok":
        texto = f"{c['qtd']} venda(s), {explicar.dinheiro(Decimal(c['total']))}."
    elif situacao == "sem_movimento":
        texto = "dia sem vendas registradas."
    else:
        texto = c["erro_texto"] or "a coleta falhou."
    return _ICONE.get(situacao, "⚠"), f"{texto} (dia {_data(c['dia'])})"


def _dia_do_posto(con, posto_id: int) -> date:
    row = con.execute("SELECT MAX(c.dia) FROM coleta c JOIN fonte f ON f.id=c.fonte_id"
                      " WHERE f.posto_id=?", (posto_id,)).fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else ontem()


def _pagina_hoje(ctx: Ctx, status: int = 200, **dados):
    itens = []
    for pid in ctx.postos():
        posto = banco.obter_posto(ctx.con, pid)
        if posto is None or not posto["ativo"]:
            continue
        dia = _dia_do_posto(ctx.con, pid)
        fontes, total = [], Decimal(0)
        for f in banco.fontes_do_posto(ctx.con, pid):
            if f["tipo"] == "webposto":
                continue
            c = banco.ultima_coleta(ctx.con, f["id"])
            icone, texto = _texto_coleta(c)
            if not f["ativo"]:
                icone, texto = "⚪", "desativado."
            fontes.append({"nome": _NOME_FONTE[f["tipo"]], "icone": icone, "texto": texto})
            if c is not None and c["dia"] == str(dia) and c["situacao"] == "ok":
                total += Decimal(c["total"])
        itens.append({"posto": posto, "dia": dia, "fontes": fontes, "total": total,
                      "divergencias": banco.divergencias_do_dia(ctx.con, pid, dia),
                      "pode_coletar": ctx.pode(Acao.COLETAR, pid)})
    return _pagina(ctx, "hoje.html", status, postos=itens, **dados)


@router.get("/")
async def inicio_pagina(ctx: Ctx = Depends(_ctx)):
    if _so_fiscal(ctx):
        return _ir("/notas")
    resumo = inicio.montar(ctx.con, ctx.uid)
    return _pagina(ctx, "inicio.html", resumo=resumo, hoje=datetime.now(timezone.utc).astimezone(
        inicio.FUSO).strftime("%d/%m/%Y"))


@router.get("/caixa")
async def hoje(ctx: Ctx = Depends(_ctx)):
    if _so_fiscal(ctx):
        return _ir("/notas")
    return _pagina_hoje(ctx)


def _coletar(con_factory, posto_id: int, visivel: bool, usuario_id: int | None = None) -> None:
    _com_conexao(con_factory, lambda con: asyncio.run(
        rotina.executar(con, posto_id=posto_id, visivel=visivel, origem="painel",
                        usuario_id=usuario_id)))


@router.post("/coletar")
async def coletar(posto_id: int, visivel: int = 0, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.COLETAR, posto_id)
    posto = _posto_ou_404(ctx, posto_id)
    if not posto["ativo"]:
        raise Recusado(400, "Este posto está desativado.")
    if rotina.em_andamento():
        return _ir("/coleta?ja=1")
    t = _em_segundo_plano("coleta", _coletar, ctx.request.app.state.con_factory, posto_id,
                          bool(visivel), ctx.uid)
    acesso.registrar(ctx.con, ctx.uid, "coletar", f"posto={posto_id} visivel={int(bool(visivel))}")
    # Espera a rotina pegar a trava (ou terminar) para /coleta já mostrar esta coleta.
    limite = _relogio() + 2
    while t.is_alive() and not rotina.em_andamento() and _relogio() < limite:
        await asyncio.sleep(0.02)
    return _ir("/coleta?iniciada=1")


@router.get("/premmia")
async def premmia(ctx: Ctx = Depends(_ctx), iniciada: int = 0):
    ctx.exigir(Acao.VER)
    rodando = rotina.em_andamento()
    cartoes = premmia_tela.cartoes(ctx.con, ctx.postos(), agora().date(),
                                   todos=any(ctx.pode(Acao.TROCAR_CREDENCIAL, p) for p in ctx.postos()))
    for c in cartoes:
        c.pode_coletar = ctx.pode(Acao.COLETAR, c.posto["id"]) and c.estado not in ("desligado", "sem_credencial")
        c.pode_ligar = ctx.pode(Acao.TROCAR_CREDENCIAL, c.posto["id"])
    cartoes = [c for c in cartoes if c.ativo or c.pode_ligar or c.estado != "desligado"]
    return _pagina(ctx, "premmia.html", cartoes=cartoes, rodando=rodando,
                   andamento=premmia_tela.andamento(ctx.con),
                   mensagem="Coleta iniciada. Esta página mostra cada etapa." if iniciada and rodando else None)


@router.post("/premmia/coletar")
async def premmia_coletar(posto_id: int, visivel: int = 0, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.COLETAR, posto_id)
    posto = _posto_ou_404(ctx, posto_id)
    if not posto["ativo"]:
        raise Recusado(400, "Este posto está desativado.")
    if rotina.em_andamento():
        return _ir("/premmia")
    t = _em_segundo_plano("coleta", _coletar, ctx.request.app.state.con_factory, posto_id, bool(visivel), ctx.uid)
    acesso.registrar(ctx.con, ctx.uid, "coletar", f"posto={posto_id} visivel={int(bool(visivel))} tela=premmia")
    limite = _relogio() + 2
    while t.is_alive() and not rotina.em_andamento() and _relogio() < limite:
        await asyncio.sleep(0.02)
    return _ir("/premmia?iniciada=1")


@router.post("/premmia/{posto_id}/ligar")
async def premmia_ligar(posto_id: int, ctx: Ctx = Depends(_ctx_post)):
    """Liga o Premmia (e a comparação com o webPosto) e já coleta o mês com o navegador visível."""
    ctx.exigir(Acao.TROCAR_CREDENCIAL, posto_id)
    posto = _posto_ou_404(ctx, posto_id)
    try:
        trocados = premmia_tela.ligar(ctx.con, posto_id, _txt(ctx.form, "usuario"),
                                      _txt(ctx.form, "senha", cru=True), _txt(ctx.form, "chave_webposto"))
    except ValueError as exc:
        return _pagina(ctx, "premmia.html", 400, erro=str(exc), rodando=rotina.em_andamento(), andamento={},
                       cartoes=premmia_tela.cartoes(ctx.con, ctx.postos(), agora().date(), todos=True))
    acesso.registrar(ctx.con, ctx.uid, "salvar_fonte", f"posto={posto_id} fonte=premmia ativo=1 tela=premmia")
    if trocados:
        acesso.registrar(ctx.con, ctx.uid, "trocar_credencial", f"posto={posto_id} campos={','.join(trocados)}")
    if posto["ativo"] and ctx.pode(Acao.COLETAR, posto_id) and not rotina.em_andamento():
        _em_segundo_plano("coleta", _coletar, ctx.request.app.state.con_factory, posto_id, True, ctx.uid)
        return _ir("/premmia?iniciada=1")
    return _ir("/premmia")


def _periodo_conciliacao(inicio: str, fim: str) -> tuple[date, date, str | None]:
    padrao_fim = ontem()
    try:
        fi = date.fromisoformat(fim) if fim else padrao_fim
        ini = date.fromisoformat(inicio) if inicio else fi.replace(day=1)
    except ValueError:
        ini, fi = padrao_fim.replace(day=1), padrao_fim
    if fi < ini:
        ini, fi = fi, ini
    aviso = None
    if (fi - ini).days >= relatorio_premmia.MAX_DIAS:
        fi = ini + timedelta(days=relatorio_premmia.MAX_DIAS - 1)
        aviso = f"O período vai até {relatorio_premmia.MAX_DIAS} dias. Mostrando de {ini:%d/%m/%Y} a {fi:%d/%m/%Y}."
    return ini, fi, aviso


def _relatorio_premmia(ctx: Ctx, posto_id: int, inicio: str, fim: str):
    ctx.exigir(Acao.VER, posto_id)
    if posto_id not in ctx.postos():
        raise Recusado(403, SEM_ACESSO)
    ini, fi, aviso = _periodo_conciliacao(inicio, fim)
    rel = relatorio_premmia.montar(ctx.con, posto_id, ini, fi)
    if rel is None:
        raise Recusado(404, "Este posto não usa o Premmia.")
    return rel, aviso


@router.get("/premmia/{posto_id}/conciliacao")
async def premmia_conciliacao(posto_id: int, inicio: str = "", fim: str = "", acao: str = "",
                              ctx: Ctx = Depends(_ctx)):
    rel, aviso = _relatorio_premmia(ctx, posto_id, inicio, fim)
    hoje_ = ontem()
    mes_passado = hoje_.replace(day=1) - timedelta(days=1)
    atalhos = [("Ontem", hoje_, hoje_), ("Últimos 7 dias", hoje_ - timedelta(days=6), hoje_),
               ("Este mês", hoje_.replace(day=1), hoje_), ("Mês passado", mes_passado.replace(day=1), mes_passado)]
    lista = [(d, o) for d, o in rel.ocorrencias if not acao or o.acao == acao]
    janela, relogio = banco.tolerancias(ctx.con)
    return _pagina(ctx, "premmia_conciliacao.html", rel=rel, ocorrencias=lista, acao=acao, acoes=sugestoes.ACOES,
                   atalhos=[(n, a.isoformat(), b.isoformat(), (a, b) == (rel.inicio, rel.fim)) for n, a, b in atalhos],
                   aviso=aviso, janela=janela, relogio=relogio, pode_configurar=ctx.pode(Acao.CONFIGURAR),
                   max_dias=relatorio_premmia.MAX_DIAS)


@router.get("/premmia/{posto_id}/conciliacao.xlsx")
async def premmia_conciliacao_xlsx(posto_id: int, inicio: str = "", fim: str = "", ctx: Ctx = Depends(_ctx)):
    rel, _ = _relatorio_premmia(ctx, posto_id, inicio, fim)
    nome = re.sub(r"[^A-Za-z0-9]+", "", rel.posto["apelido"] or rel.posto["nome"]) or "posto"
    return Response(relatorio_premmia.planilha(rel),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="Conciliacao_Premmia_{nome}_'
                                                    f'{rel.inicio:%Y%m%d}_{rel.fim:%Y%m%d}.xlsx"'})


@router.post("/premmia/tolerancias")
async def premmia_tolerancias(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    volta = _txt(ctx.form, "volta")
    volta = volta if volta.startswith("/premmia/") else "/premmia"
    try:
        banco.salvar_tolerancias(ctx.con, _int(ctx.form, "janela") or 0, _int(ctx.form, "relogio") or 0)
    except ValueError as exc:
        raise Recusado(400, str(exc))
    acesso.registrar(ctx.con, ctx.uid, "configurar", "tolerancias da conciliacao premmia")
    return _ir(volta)


@router.get("/premmia/planilha/{posto_id}")
async def premmia_planilha(posto_id: int, mes: str = "", ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER, posto_id)
    if posto_id not in ctx.postos():
        raise Recusado(403, SEM_ACESSO)
    caminho = premmia_tela.planilha(ctx.con, _posto_ou_404(ctx, posto_id), mes)
    if caminho is None:
        raise Recusado(404, "Não há planilha do Premmia deste mês para este posto.")
    return FileResponse(caminho, filename=caminho.name)


@router.post("/reenviar")
async def reenviar(posto_id: int, ctx: Ctx = Depends(_ctx_post)):
    """Reenvia o resumo do último dia coletado, montado do banco (não coleta de novo)."""
    ctx.exigir(Acao.COLETAR, posto_id)
    _posto_ou_404(ctx, posto_id)
    dia = _dia_do_posto(ctx.con, posto_id)
    resultados = coletas.resultados_salvos(ctx.con, posto_id, dia)
    if not resultados:
        return _pagina_hoje(ctx, erro="Ainda não há coleta salva deste posto para reenviar.")
    fab = ctx.request.app.state.con_factory
    _em_segundo_plano("reenvio", _com_conexao, fab,
                      lambda con: envio.enviar_dia(con, resultados, dia))
    acesso.registrar(ctx.con, ctx.uid, "reenviar", f"posto={posto_id} dia={dia}")
    return _pagina_hoje(ctx, mensagem=f"Reenvio iniciado: resumo de {dia:%d/%m/%Y} pelos canais ativos.")


def _dia_param(texto: str) -> date | None:
    for formato in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _versoes(con, posto_id: int, dia: date) -> dict[int, Path]:
    """Versões da planilha do dia ({número: arquivo}); vazio se o apelido está em conflito."""
    posto = banco.obter_posto(con, posto_id)
    if posto is None or relatorio_xlsx.conflito(con, posto_id):
        return {}
    return dict(relatorio_xlsx.versoes_numeradas(posto_id, dia, posto["apelido"]))


@router.get("/planilha")
async def planilha(posto_id: int, dia: str = "", versao: int | None = None,
                   ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER, posto_id)
    _posto_ou_404(ctx, posto_id)
    d = _dia_param(dia)
    if d is None:
        raise Recusado(400, "Dia inválido. Use dd-mm-aaaa.")
    if relatorio_xlsx.conflito(ctx.con, posto_id):
        raise Recusado(409, "Apelido em conflito com outro posto; ajuste o cadastro.")
    if versao is not None:
        apelido = banco.obter_posto(ctx.con, posto_id)["apelido"]
        arquivo = dict(relatorio_xlsx.versoes_numeradas(posto_id, d, apelido)).get(versao)
        if arquivo is None:
            raise Recusado(404, "Versão não encontrada.")
    else:
        # sempre a partir do banco: reaproveita a mais nova se os dados não mudaram, nunca sobrescreve
        arquivo = relatorio_xlsx.gerar(ctx.con, posto_id, d)
    detalhe = f"posto={posto_id} dia={d}" + (f" versao={versao}" if versao is not None else "")
    acesso.registrar(ctx.con, ctx.uid, "baixar_planilha", detalhe)
    return FileResponse(arquivo, media_type=XLSX, filename=arquivo.name)


# ---------------------------------------------------------------- Postos

def _protecao(con, postos) -> dict[int, dict]:
    """Situação de cada posto na pasta da rede: {posto_id: {"texto", "outra"}}."""
    pasta = banco.pasta_rede(con)
    if pasta is None:
        return {}
    meu = banco.id_instalacao(con)
    res = {}
    for p in postos:
        chave = registro_rede.chave_posto(p)
        d = None
        if chave is not None:
            try:
                d = registro_rede.dono(pasta, chave)
            except registro_rede.PastaIndisponivel:
                return {q["id"]: {"texto": "Pasta da rede inacessível", "outra": False} for q in postos}
        if d is None:
            res[p["id"]] = {"texto": "Sem proteção", "outra": False}
        elif d.id_instalacao == meu:
            res[p["id"]] = {"texto": "Protegido (esta máquina)", "outra": False}
        else:
            res[p["id"]] = {"texto": f"Pertence à máquina {d.maquina}", "outra": True}
    return res


def _pagina_postos(ctx: Ctx, status: int = 200, **dados):
    if ctx.pode(Acao.CADASTRAR_POSTO):
        postos = banco.listar_postos(ctx.con, so_ativos=False)
    else:
        postos = [p for p in (banco.obter_posto(ctx.con, i) for i in ctx.postos()) if p]
    protecao = _protecao(ctx.con, postos)
    sem = {"texto": "Sem proteção", "outra": False}
    itens = [{"posto": p, "pode_fontes": ctx.pode(Acao.TROCAR_CREDENCIAL, p["id"]),
              "protecao": protecao.get(p["id"], sem)} for p in postos]
    units = Path(config_cr.__file__).parent / "units.json"
    return _pagina(ctx, "postos.html", status, postos=itens, aviso=AVISO_POSTO,
                   pode_cadastrar=ctx.pode(Acao.CADASTRAR_POSTO), pode_assumir=ctx.pode(Acao.CONFIGURAR),
                   pasta_ligada=banco.pasta_rede(ctx.con) is not None, tem_units=units.exists(), **dados)


def _proteger(ctx: Ctx, chave: str | None, nome: str, ao_bloquear=None):
    """Com a pasta da rede ligada, registra o posto nela ANTES de gravar no banco.

    Devolve a página de recusa (nada foi gravado) ou None para seguir. Posto de outra máquina:
    `ao_bloquear(dono)` decide a resposta (cadastro novo) ou recusa com 409.
    """
    pasta = banco.pasta_rede(ctx.con)
    if pasta is None:
        return None
    if chave is None:
        return _pagina_postos(ctx, 400, erro=MSG_CHAVE)
    try:
        registro_rede.registrar(pasta, chave, banco.id_instalacao(ctx.con), nome)
    except registro_rede.PostoDeOutraMaquina as exc:
        if ao_bloquear is not None:
            return ao_bloquear(exc.dono)
        return _pagina_postos(ctx, 409, erro=registro_rede.mensagem_bloqueio(exc.dono))
    except registro_rede.PastaIndisponivel:
        return _pagina_postos(ctx, 503, erro=registro_rede.MSG_INDISPONIVEL)
    return None


def _liberar_na_rede(con, chave: str | None) -> None:
    """Remove o registro desta instalação; falha não impede desativar (só o tipo vai ao log)."""
    pasta = banco.pasta_rede(con)
    if pasta is None or chave is None:
        return
    try:
        registro_rede.liberar(pasta, chave, banco.id_instalacao(con))
    except Exception as exc:  # noqa: BLE001 - desativar nunca depende da pasta da rede
        logger.warning("Liberar posto na pasta da rede falhou tipo=%s", type(exc).__name__)


@router.get("/postos")
async def postos(assumido: int = 0, ctx: Ctx = Depends(_ctx)):
    if not (ctx.pode(Acao.CADASTRAR_POSTO) or ctx.pode(Acao.TROCAR_CREDENCIAL)):
        raise Recusado(403, SEM_ACESSO)
    mensagem = "Posto assumido. Clique em Ativar para voltar a coletar." if assumido else None
    return _pagina_postos(ctx, mensagem=mensagem)


@router.post("/postos")
async def postos_gravar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CADASTRAR_POSTO)
    f, acao = ctx.form, _txt(ctx.form, "acao")
    posto = None
    if acao in ("desativar", "ativar", "editar"):
        pid = _int(f, "id")
        posto = _posto_ou_404(ctx, pid or 0)
    if acao in ("desativar", "ativar"):
        if acao == "ativar":
            recusa = _proteger(ctx, registro_rede.chave_posto(posto), posto["nome"])
            if recusa is not None:
                return recusa
        banco.definir_posto_ativo(ctx.con, pid, acao == "ativar")
        if acao == "desativar":
            _liberar_na_rede(ctx.con, registro_rede.chave_posto(posto))
        acesso.registrar(ctx.con, ctx.uid, f"{acao}_posto", f"posto={pid}")
        return _ir("/postos")
    if acao not in ("novo", "editar"):
        raise Recusado(400, "Ação desconhecida.")
    nome, codigo_txt = _txt(f, "nome"), _txt(f, "empresa_codigo_webposto")
    if not nome:
        return _pagina_postos(ctx, 400, erro="Informe o nome do posto.")
    if codigo_txt and not codigo_txt.lstrip("-").isdigit():
        return _pagina_postos(ctx, 400, erro="O código da empresa no webPosto deve ser um número.")
    codigo = int(codigo_txt) if codigo_txt else None
    try:
        unidades.validar_codigo(ctx.con, codigo, pid if acao == "editar" else None)
    except unidades.CodigoInvalido as exc:  # mensagem própria, em português
        return _pagina_postos(ctx, 400, erro=str(exc))
    apelido = _txt(f, "apelido") or None
    if relatorio_xlsx.nome_em_uso(ctx.con, apelido, pid if acao == "editar" else None):
        return _pagina_postos(ctx, 400, erro=unidades.MSG_APELIDO)
    cnpj = _txt(f, "cnpj") or None
    chave = registro_rede.chave_posto({"empresa_codigo_webposto": codigo, "cnpj": cnpj})
    dados = (nome, apelido, cnpj, codigo)

    def salvar_desativado(dono):
        """Máquina substituta: grava desativado, sem tocar na pasta da rede, para poder Assumir."""
        novo = banco.inserir_posto(ctx.con, *dados, ativo=False)
        acesso.registrar(ctx.con, ctx.uid, "novo_posto", f"posto={novo} desativado=outra_maquina")
        return _pagina_postos(ctx, mensagem=registro_rede.mensagem_salvo_desativado(dono))

    protege = acao == "novo" or bool(posto["ativo"])  # posto desativado não ocupa a pasta da rede
    if protege:
        recusa = _proteger(ctx, chave, nome, salvar_desativado if acao == "novo" else None)
        if recusa is not None:
            return recusa
    if acao == "novo":
        pid = banco.inserir_posto(ctx.con, *dados)
    else:
        banco.atualizar_posto(ctx.con, pid, *dados)
        antiga = registro_rede.chave_posto(posto)
        if protege and antiga != chave:
            _liberar_na_rede(ctx.con, antiga)
    acesso.registrar(ctx.con, ctx.uid, f"{acao}_posto", f"posto={pid}")
    return _ir("/postos")


@router.post("/postos/{posto_id}/assumir")
async def assumir_posto(posto_id: int, ctx: Ctx = Depends(_ctx_post)):
    """A outra máquina quebrou ou foi trocada (ou este PC foi reinstalado): esta passa a coletar."""
    ctx.exigir(Acao.CONFIGURAR)
    posto = _posto_ou_404(ctx, posto_id)
    pasta = banco.pasta_rede(ctx.con)
    if pasta is None:
        return _pagina_postos(ctx, 400,
                              erro="Configure a Pasta da rede (em Agenda) antes de assumir um posto.")
    chave = registro_rede.chave_posto(posto)
    if chave is None:
        return _pagina_postos(ctx, 400, erro=MSG_CHAVE)
    if _txt(ctx.form, "confirmar") != "1":
        return _pagina_postos(ctx, 400, erro="Marque a confirmação de que a outra máquina não coleta"
                                             " mais este posto.")
    try:
        anterior = registro_rede.dono(pasta, chave)
        registro_rede.assumir(pasta, chave, banco.id_instalacao(ctx.con), posto["nome"])
    except registro_rede.PastaIndisponivel:
        return _pagina_postos(ctx, 503, erro=registro_rede.MSG_INDISPONIVEL)
    antes = anterior.maquina if anterior else "-"
    acesso.registrar(ctx.con, ctx.uid, "assumir_posto", f"posto={posto_id};antes={antes}")
    return _ir("/postos?assumido=1")


def _texto_desativados(desativados: list[str]) -> str:
    if not desativados:
        return ""
    return (f" {len(desativados)} posto(s) salvo(s) desativado(s): já cadastrado(s) em outra máquina."
            " Use 'Assumir posto' se a outra máquina não coleta mais.")


@router.post("/postos/importar-logos")
async def importar_logos(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CADASTRAR_POSTO)
    caminho = Path(config_cr.__file__).parent / "units.json"
    if not caminho.exists():
        return _pagina_postos(ctx, 404, erro="Arquivo units.json não encontrado nesta instalação.")
    desativados: list[str] = []
    try:
        n = unidades.importar_units_json(ctx.con, caminho, desativados=desativados)
    except unidades.CodigoInvalido as exc:  # mensagem própria, em português
        ctx.con.rollback()
        return _pagina_postos(ctx, 400, erro=f"units.json não importado: {exc}")
    except registro_rede.PastaIndisponivel:
        ctx.con.rollback()
        return _pagina_postos(ctx, 503, erro=registro_rede.MSG_INDISPONIVEL)
    except registro_rede.PostoDeOutraMaquina as exc:
        ctx.con.rollback()
        return _pagina_postos(ctx, 409, erro=registro_rede.mensagem_bloqueio(exc.dono))
    except (ValueError, KeyError, TypeError, sqlite3.Error):
        ctx.con.rollback()
        return _pagina_postos(ctx, 400, erro="Não foi possível ler o units.json.")
    acesso.registrar(ctx.con, ctx.uid, "importar_units_json",
                     f"criados={n} desativados={len(desativados)}")
    mensagem = f"{n} posto(s) importado(s) do units.json.{_texto_desativados(desativados)}"
    return _pagina_postos(ctx, mensagem=mensagem, desativados=desativados)


@router.get("/config/exportar")
async def exportar(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.CADASTRAR_POSTO)
    dados = unidades.exportar_config(ctx.con)
    acesso.registrar(ctx.con, ctx.uid, "exportar_config", "")
    return Response(json.dumps(dados, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="logosmatch-config.json"'})


@router.post("/config/importar")
async def importar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CADASTRAR_POSTO)
    arquivo = ctx.form.get("arquivo")
    desativados: list[str] = []
    try:
        if arquivo is None or isinstance(arquivo, str):
            raise ValueError
        bruto = await arquivo.read(_MAX_IMPORTAR + 1)
        if len(bruto) > _MAX_IMPORTAR:
            raise ValueError
        dados = json.loads(bruto.decode("utf-8"))
        if not isinstance(dados, dict):
            raise ValueError
        n = unidades.importar_config(ctx.con, dados, desativados=desativados)
    except unidades.CodigoInvalido as exc:  # mensagem própria, em português
        ctx.con.rollback()
        return _pagina_postos(ctx, 400, erro=f"Configuração não importada: {exc}")
    except registro_rede.PastaIndisponivel:
        ctx.con.rollback()
        return _pagina_postos(ctx, 503, erro=registro_rede.MSG_INDISPONIVEL)
    except registro_rede.PostoDeOutraMaquina as exc:
        ctx.con.rollback()
        return _pagina_postos(ctx, 409, erro=registro_rede.mensagem_bloqueio(exc.dono))
    except (ValueError, KeyError, TypeError, AttributeError, sqlite3.Error):
        ctx.con.rollback()
        return _pagina_postos(ctx, 400, erro="Arquivo de configuração inválido.")
    acesso.registrar(ctx.con, ctx.uid, "importar_config",
                     f"criados={n} desativados={len(desativados)}")
    return _pagina_postos(ctx, mensagem=f"{n} posto(s) importado(s). Cadastre as senhas em Fontes."
                                        f"{_texto_desativados(desativados)}", desativados=desativados)


# ---------------------------------------------------------------- Fontes do posto

def _pagina_fontes(ctx: Ctx, posto, status: int = 200, resultado: dict | None = None, **dados):
    salvas = {f["tipo"]: f for f in banco.fontes_do_posto(ctx.con, posto["id"])}
    itens = []
    for tipo, (nome, prefixo, campos) in FONTES.items():
        f = salvas.get(tipo)
        itens.append({
            "tipo": tipo, "nome": nome, "ativo": bool(f and f["ativo"]), "existe": f is not None,
            "ultimo_teste_em": f["ultimo_teste_em"] if f else None,
            "ultimo_teste_ok": f["ultimo_teste_ok"] if f else None,
            "campos": [{"chave": c, "rotulo": r,
                        "salvo": credenciais.tem(f"{posto['id']}/{prefixo}/{c}")} for c, r in campos],
            "resultado": (resultado or {}).get(tipo)})
    return _pagina(ctx, "posto_fontes.html", status, posto=posto, fontes=itens, **dados)


def _fonte_ou_404(tipo: str):
    if tipo not in FONTES:
        raise Recusado(404, "Fonte desconhecida.")
    return FONTES[tipo]


@router.get("/postos/{posto_id}/fontes")
async def fontes(posto_id: int, salvo: int = 0, ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.TROCAR_CREDENCIAL, posto_id)
    posto = _posto_ou_404(ctx, posto_id)
    return _pagina_fontes(ctx, posto, mensagem="Salvo." if salvo else None)


@router.post("/postos/{posto_id}/fontes/{tipo}")
async def fonte_gravar(posto_id: int, tipo: str, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.TROCAR_CREDENCIAL, posto_id)
    _, prefixo, campos = _fonte_ou_404(tipo)
    _posto_ou_404(ctx, posto_id)
    atual = {f["tipo"]: f for f in banco.fontes_do_posto(ctx.con, posto_id)}.get(tipo)
    config = json.loads(atual["config_json"] or "{}") if atual else {}
    ativo = _txt(ctx.form, "ativo") == "1"
    banco.salvar_fonte(ctx.con, posto_id, tipo, ativo, config)
    trocados = []
    for chave, _rotulo in campos:
        valor = _txt(ctx.form, chave, cru=(chave == "senha"))
        if tipo == "premmia" and chave == "usuario" and valor:
            anterior = credenciais.ler(f"{posto_id}/premmia/usuario")
            if anterior and anterior.strip() != valor.strip():
                premmia_tela.recomecar(ctx.con, posto_id)
        if valor:  # em branco = manter o atual
            credenciais.salvar(f"{posto_id}/{prefixo}/{chave}", valor)
            trocados.append(chave)
    acesso.registrar(ctx.con, ctx.uid, "salvar_fonte", f"posto={posto_id} fonte={tipo} ativo={int(ativo)}")
    if trocados:
        acesso.registrar(ctx.con, ctx.uid, "trocar_credencial",
                         f"posto={posto_id} fonte={tipo} campos={','.join(trocados)}")
    return _ir(f"/postos/{posto_id}/fontes?salvo=1")


async def _testar(con, posto, tipo: str) -> tuple[bool, str]:
    d = ontem()
    pid = posto["id"]
    if tipo == "premmia":
        if credenciais.tem(f"{pid}/premmia/usuario") and credenciais.tem(f"{pid}/premmia/senha"):
            return True, ("Usuário e senha do Premmia estão salvos. O login de verdade só acontece"
                          " na coleta (o Premmia aceita uma tentativa por noite).")
        return False, "Falta o usuário ou a senha do Premmia."
    unidades.ativar(con)
    if tipo == "pagbank_edi":
        try:
            transacoes = await pagbank_edi.buscar_transacoes(unidades.codigo_empresa(posto), d)
        except Exception as exc:  # noqa: BLE001 - nunca str(exc)
            return False, explicar.erro_pt(exc)
        return True, f"PagBank respondeu: {len(transacoes)} venda(s) em {d:%d/%m/%Y}."
    if posto["empresa_codigo_webposto"] is None:
        return False, "Informe o código da empresa no webPosto (em Postos) antes de testar."
    if not posto["ativo"]:
        return False, "Ative o posto antes de testar."
    if unidades.codigo_em_conflito(con, posto):
        return False, coletas.CODIGO_REPETIDO
    unidade = unidades.do_posto(con, posto)
    try:
        caixas = await webposto_caixas.buscar_caixas(unidade, d, d)
    except Exception as exc:  # noqa: BLE001 - nunca str(exc)
        return False, explicar.erro_pt(exc)
    return True, f"webPosto respondeu: {len(caixas)} caixa(s) em {d:%d/%m/%Y}."


@router.post("/postos/{posto_id}/fontes/{tipo}/testar")
async def fonte_testar(posto_id: int, tipo: str, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.TROCAR_CREDENCIAL, posto_id)
    _fonte_ou_404(tipo)
    posto = _posto_ou_404(ctx, posto_id)
    ok, texto = await _testar(ctx.con, posto, tipo)
    atual = {f["tipo"]: f for f in banco.fontes_do_posto(ctx.con, posto_id)}.get(tipo)
    if atual is not None:
        banco.marcar_teste_fonte(ctx.con, atual["id"], ok)
    acesso.registrar(ctx.con, ctx.uid, "testar_fonte", f"posto={posto_id} fonte={tipo} ok={int(ok)}")
    return _pagina_fontes(ctx, posto, resultado={tipo: {"ok": ok, "texto": texto}})


# ---------------------------------------------------------------- Canais

def _lista(texto: str) -> list[str]:
    return [p.strip() for p in texto.replace(";", ",").split(",") if p.strip()]


def _pagina_canais(ctx: Ctx, status: int = 200, **dados):
    itens = []
    for c in banco.listar_canais(ctx.con):
        cfg = json.loads(c["config_json"] or "{}")
        segredo = _SEGREDO_CANAL.get(c["tipo"])
        itens.append({"canal": c, "cfg": cfg, "postos": cfg.get("postos") or [],
                      "segredo": segredo,
                      "aprovacoes_erro": cfg.get("aprovacoes_erro"),
                      "segredo_salvo": bool(segredo and credenciais.tem(f"canal/{c['id']}/{segredo[0]}"))})
    return _pagina(ctx, "canais.html", status, canais=itens,
                   todos_postos=banco.listar_postos(ctx.con, so_ativos=False), **dados)


@router.get("/canais")
async def canais(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.CONFIGURAR)
    return _pagina_canais(ctx)


def _config_canal(tipo: str, form, atual: dict | None = None) -> dict:
    """Mescla sobre a config atual: chaves que a tela não edita são preservadas."""
    if tipo == "telegram":
        cfg = {
            "chat_ids": _lista(_txt(form, "chat_ids")),
            "aprovacoes": _txt(form, "aprovacoes") == "1",
            "aprovadores": _lista(_txt(form, "aprovadores")),
        }
    elif tipo == "email":
        porta = _txt(form, "porta") or "587"
        if not porta.isdigit():
            raise ValueError("A porta do servidor de e-mail deve ser um número.")
        cfg = {"servidor": _txt(form, "servidor"), "porta": int(porta), "usuario": _txt(form, "usuario"),
               "destinatarios": _lista(_txt(form, "destinatarios"))}
    else:
        cfg = {}
    cfg["postos"] = _ints(form, "postos")
    resultado = {**(atual or {}), **cfg}
    resultado.pop("aprovacoes_erro", None)
    return resultado


@router.post("/canais")
async def canais_gravar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    f, acao = ctx.form, _txt(ctx.form, "acao")
    if acao == "novo":
        tipo = _txt(f, "tipo")
        if tipo not in ("telegram", "email", "toast"):
            return _pagina_canais(ctx, 400, erro="Escolha o tipo do canal.")
        atual = None
    elif acao in ("editar", "desativar", "ativar"):
        atual = ctx.con.execute("SELECT * FROM canal WHERE id=?", (_int(f, "id"),)).fetchone()
        if atual is None:
            raise Recusado(404, "Canal não encontrado.")
        tipo = atual["tipo"]
    else:
        raise Recusado(400, "Ação desconhecida.")
    if acao in ("desativar", "ativar"):
        banco.atualizar_canal(ctx.con, atual["id"], json.loads(atual["config_json"] or "{}"), acao == "ativar")
        acesso.registrar(ctx.con, ctx.uid, f"{acao}_canal", f"canal={atual['id']}")
        return _ir("/canais")
    try:
        cfg = _config_canal(tipo, f, json.loads(atual["config_json"] or "{}") if atual else None)
    except ValueError as exc:  # mensagem própria, em português
        return _pagina_canais(ctx, 400, erro=str(exc))
    ativo = _txt(f, "ativo") == "1"
    if atual is None:
        cid = banco.inserir_canal(ctx.con, tipo, cfg, ativo)
    else:
        cid = atual["id"]
        banco.atualizar_canal(ctx.con, cid, cfg, ativo)
    acesso.registrar(ctx.con, ctx.uid, f"{acao}_canal", f"canal={cid} tipo={tipo}")
    campo = _SEGREDO_CANAL.get(tipo, ("",))[0]
    valor = _txt(f, campo, cru=(campo == "senha")) if campo else ""
    if valor.strip():  # em branco = manter o atual
        credenciais.salvar(f"canal/{cid}/{campo}", valor)
        acesso.registrar(ctx.con, ctx.uid, "trocar_credencial", f"canal={cid} campos={campo}")
    return _ir("/canais")


@router.post("/canais/{canal_id}/testar")
async def canal_testar(canal_id: int, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    fab = ctx.request.app.state.con_factory
    resultado = await run_in_threadpool(_com_conexao, fab, lambda con: envio.testar_canal(con, canal_id))
    ok = resultado == "ok"
    acesso.registrar(ctx.con, ctx.uid, "testar_canal", f"canal={canal_id} ok={int(ok)}")
    if ok:
        return _pagina_canais(ctx, mensagem="Teste enviado. Confira se chegou.")
    return _pagina_canais(ctx, erro=resultado)


# ---------------------------------------------------------------- Agenda

def _pagina_agenda(ctx: Ctx, status: int = 200, **dados):
    coleta, repescagem = rotina.horarios(ctx.con)
    pasta = banco.pasta_rede(ctx.con)
    base = {"hora_coleta": coleta, "hora_repescagem": repescagem,
            "pasta_rede": str(pasta) if pasta else "", "pasta_ligada": pasta is not None,
            "conflitos": []}
    return _pagina(ctx, "agenda.html", status, **{**base, **dados})


@router.get("/agenda")
async def agenda(salvo: int = 0, rede: int = 0, ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.CONFIGURAR)
    mensagem = "Horários salvos." if salvo else ("Pasta da rede desligada." if rede else None)
    return _pagina_agenda(ctx, mensagem=mensagem)


@router.post("/agenda")
async def agenda_gravar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    coleta, repescagem = _txt(ctx.form, "hora_coleta"), _txt(ctx.form, "hora_repescagem")
    if not (_RE_HORA.match(coleta) and _RE_HORA.match(repescagem)):
        return _pagina_agenda(ctx, 400, hora_coleta=coleta, hora_repescagem=repescagem,
                              erro="Horário inválido. Use HH:MM, por exemplo 06:00.")
    banco.salvar_horarios(ctx.con, coleta, repescagem)
    sched = ctx.request.app.state.sched
    if sched is not None:
        agendador.reagendar(sched, ctx.request.app.state.con_factory)
    acesso.registrar(ctx.con, ctx.uid, "agenda", f"coleta={coleta} repescagem={repescagem}")
    return _ir("/agenda?salvo=1")


def _pasta_gravavel(pasta: Path) -> bool:
    """A pasta existe e aceita gravação: cria LogosMatch/postos e um arquivo temporário."""
    try:
        if not pasta.is_absolute() or not pasta.is_dir():
            return False
        alvo = registro_rede.pasta_postos(pasta)
        alvo.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=alvo):
            pass
        return True
    except (OSError, ValueError):
        return False


@router.post("/pasta-rede")
async def pasta_rede_gravar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    acao, con = _txt(ctx.form, "acao"), ctx.con
    if acao == "desligar":
        banco.salvar_pasta_rede(con, None)
        acesso.registrar(con, ctx.uid, "pasta_rede", "desligada")
        return _ir("/agenda?rede=1")
    if acao != "salvar":
        raise Recusado(400, "Ação desconhecida.")
    caminho = _txt(ctx.form, "caminho")
    pasta = Path(caminho) if caminho else None
    if pasta is None or not _pasta_gravavel(pasta):
        return _pagina_agenda(ctx, 400, pasta_rede=caminho, erro=MSG_PASTA_INVALIDA)
    meu = banco.id_instalacao(con)
    protegidos, sem_chave, de_outra = 0, 0, []
    try:
        for p in banco.listar_postos(con):  # só os ativos ocupam a pasta da rede
            chave = registro_rede.chave_posto(p)
            if chave is None:
                sem_chave += 1
                continue
            try:
                registro_rede.registrar(pasta, chave, meu, p["nome"])
                protegidos += 1
            except registro_rede.PostoDeOutraMaquina as exc:
                de_outra.append((p, exc.dono))
    except registro_rede.PastaIndisponivel:
        # nada é salvo: nem o caminho, nem a desativação dos postos de outra máquina
        acesso.registrar(con, ctx.uid, "pasta_rede", "ligada falha=indisponivel")
        return _pagina_agenda(ctx, 503, pasta_rede=caminho, erro=registro_rede.MSG_INDISPONIVEL)
    banco.salvar_pasta_rede(con, str(pasta))
    conflitos = []
    for p, dono in de_outra:
        banco.definir_posto_ativo(con, p["id"], False)
        acesso.registrar(con, ctx.uid, "desativar_posto", f"posto={p['id']} motivo=outra_maquina")
        conflitos.append(f"{p['nome']} foi desativado: {registro_rede.mensagem_bloqueio(dono)}")
    acesso.registrar(con, ctx.uid, "pasta_rede",
                     f"ligada protegidos={protegidos} conflitos={len(conflitos)} sem_chave={sem_chave}")
    mensagem = f"Pasta da rede salva. {protegidos} posto(s) protegido(s)."
    if sem_chave:
        mensagem += f" {sem_chave} posto(s) sem código do webPosto nem CNPJ ficaram sem proteção."
    return _pagina_agenda(ctx, conflitos=conflitos, mensagem=mensagem)


# ---------------------------------------------------------------- Coleta em andamento / Histórico

_ORIGEM = {"agendada": "Agendada", "repescagem": "Repescagem", "recuperacao": "Recuperação",
           "painel": "Painel", "bandeja": "Bandeja"}
_ESTADO = {"aguardando": "Aguardando", "coletando": "Coletando…", "ok": "OK",
           "sem_movimento": "Sem movimento", "sem_comparacao": "Sem comparação com webPosto",
           "erro": "Erro", "verificacao_humana": "Precisa de verificação humana"}
_SITUACAO_EXEC = {"em_andamento": "Em andamento", "concluida": "Concluída", "falhou": "Falhou"}
_CLASSE = {"ok": "ok", "sem_movimento": "alerta", "sem_comparacao": "alerta", "erro": "erro",
           "verificacao_humana": "erro", "nao_concluido": "erro"}


def _momento(valor) -> datetime | None:
    try:
        m = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None
    return m if m.tzinfo else m.replace(tzinfo=timezone.utc)


def _duracao(inicio, fim=None) -> str:
    a, b = _momento(inicio), (_momento(fim) if fim else datetime.now(timezone.utc))
    if a is None or b is None:
        return "—"
    seg = max(0, int((b - a).total_seconds()))
    return f"{seg // 60}m {seg % 60}s"


def _execucao_tela(con, ex, visiveis: set[int], rodando: bool) -> dict:
    """Execução pronta para a tela, só com as linhas dos postos visíveis.

    `em_andamento` no banco sem coleta rodando (app fechado no meio) é tratada como interrompida.
    """
    interrompida = ex["situacao"] == "em_andamento" and not rodando
    aberta = ex["situacao"] == "em_andamento" and rodando
    nomes: dict[int, str] = {}
    itens = []
    for i in banco.itens_execucao(con, ex["id"]):
        pid = i["posto_id"]
        if pid not in visiveis:
            continue
        if pid not in nomes:
            p = banco.obter_posto(con, pid)
            nomes[pid] = (p["apelido"] or p["nome"]) if p else f"Posto {pid}"
        situacao = i["situacao"]
        if not aberta and situacao in ("aguardando", "coletando"):
            situacao, estado = "nao_concluido", "Não concluído"  # vale a situação da execução
        else:
            estado = _ESTADO.get(situacao, situacao)
        itens.append({"posto": nomes[pid], "fonte": _NOME_FONTE.get(i["fonte"], i["fonte"]),
                      "estado": estado, "classe": _CLASSE.get(situacao, ""),
                      "mensagem": i["mensagem"] or "",
                      "tempo": (_duracao(i["iniciada_em"], i["terminada_em"])
                                if i["iniciada_em"] and situacao != "nao_concluido" else "—")})
    origem = _ORIGEM.get(ex["origem"], ex["origem"])
    quem = origem
    if ex["usuario_id"] is not None:
        u = con.execute("SELECT nome FROM usuario WHERE id=?", (ex["usuario_id"],)).fetchone()
        quem = u["nome"] if u else origem
    situacao = "Interrompida" if interrompida else _SITUACAO_EXEC.get(ex["situacao"], ex["situacao"])
    return {"ex": ex, "aberta": aberta, "interrompida": interrompida, "itens": itens, "postos": nomes,
            "quem": quem, "origem": origem, "situacao": situacao,
            "duracao": (None if aberta or interrompida
                        else _duracao(ex["iniciada_em"], ex["terminada_em"]))}


@router.get("/coleta")
async def coleta(ja: int = 0, iniciada: int = 0, ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER)
    visiveis = ctx.postos()
    configurar = ctx.pode(Acao.CONFIGURAR)
    atual = banco.execucao_atual(ctx.con)
    rodando = rotina.em_andamento()
    # trava pega, mas a execução ainda não foi aberta no banco: não mostrar a anterior como atual
    preparando = rodando and atual is None
    dados = None
    if not preparando:
        # sem CONFIGURAR: a mais recente que toca algum posto visível (como no /historico)
        for ex in ([atual] if atual else []) + list(banco.ultimas_execucoes(ctx.con)):
            tela = _execucao_tela(ctx.con, ex, set(visiveis), rodando)
            if configurar or tela["itens"]:
                dados = tela
                break
    ativa = preparando or bool(dados and dados["aberta"])
    coletar = []
    if not rodando:
        for pid in visiveis:
            posto = banco.obter_posto(ctx.con, pid)
            if posto is not None and posto["ativo"] and ctx.pode(Acao.COLETAR, pid):
                coletar.append(posto)
    return _pagina(ctx, "andamento.html", execucao=dados, preparando=preparando, coletar=coletar,
                   atualizar=ativa,
                   # o aviso só vale enquanto a coleta roda (o refresh já aponta para /coleta limpo)
                   erro=COLETA_EM_ANDAMENTO if ja and (rodando or ativa) else None,
                   mensagem="Coleta iniciada." if iniciada and not ja and (rodando or ativa) else None)


@router.get("/historico")
async def historico(ctx: Ctx = Depends(_ctx)):
    visiveis = set(ctx.postos())
    configurar = ctx.pode(Acao.CONFIGURAR)
    rodando = rotina.em_andamento()
    execucoes = []
    for ex in banco.ultimas_execucoes(ctx.con):
        dados = _execucao_tela(ctx.con, ex, visiveis, rodando)
        if not dados["itens"] and not configurar:
            continue  # gerente/conferente: só execuções que tocaram os seus postos
        dia = date.fromisoformat(ex["dia"])
        dados["dia"] = dia
        dados["planilhas"] = [{"posto": nome, "posto_id": pid, "dia": f"{dia:%d-%m-%Y}",
                               "versoes": sorted(_versoes(ctx.con, pid, dia))}
                              for pid, nome in dados["postos"].items()]
        dados["envios"] = banco.envios_da_execucao(ctx.con, ex["id"]) if configurar else None
        execucoes.append(dados)
    envios = banco.ultimos_envios(ctx.con) if configurar else None
    return _pagina(ctx, "historico.html", execucoes=execucoes,
                   coletas=banco.ultimas_coletas(ctx.con, ctx.postos()), envios=envios)


# ---------------------------------------------------------------- Extratos OFX

_ROTULO_APROVACAO = {
    "pendente": "Aguardando aprovação",
    "executada": "Importado no webPosto",
    "falhou": "Falhou",
    "recusada": "Recusado",
    "automatica": "Importado automaticamente",
    "aprovada": "Aprovada",
}


def _extratos_da_tela(ctx: Ctx):
    visiveis = set(ctx.postos())
    configurar = ctx.pode(Acao.CONFIGURAR)
    contas = [c for c in repositorio.contas(ctx.con)
              if configurar or c["posto_id"] in visiveis]
    arquivos_db = ctx.con.execute(
        """SELECT a.*, c.posto_id, p.nome AS posto_nome, p.apelido AS posto_apelido
           FROM extrato_arquivo a
           LEFT JOIN conta_bancaria c ON c.id=a.conta_bancaria_id
           LEFT JOIN posto p ON p.id=c.posto_id
           ORDER BY a.recebido_em DESC, a.id DESC LIMIT 100"""
    ).fetchall()
    arquivos = [a for a in arquivos_db
                if configurar or (a["posto_id"] is not None and a["posto_id"] in visiveis)]
    aprovacoes_db = ctx.con.execute(
        "SELECT * FROM aprovacao ORDER BY criada_em DESC, id DESC LIMIT 100"
    ).fetchall()
    historico = []
    pendentes = []
    lancamentos_pendentes = []
    for row in aprovacoes_db:
        if not configurar and row["posto_id"] not in visiveis:
            continue
        item = dict(row)
        item["resumo"] = json.loads(row["resumo_json"])
        if row["tipo"] == "lancamento":
            posto = banco.obter_posto(ctx.con, row["posto_id"])
            if posto:
                item["resumo"]["posto"] = {
                    "id": posto["id"], "nome": posto["nome"], "apelido": posto["apelido"],
                }
        item["rotulo"] = _ROTULO_APROVACAO.get(row["situacao"], row["situacao"])
        if (row["tipo"] == "importar_extrato" and row["situacao"] == "automatica"
                and row["decidida_em"] is None):
            item["rotulo"] = "Aguardando importação automática"
        if row["tipo"] == "lancamento":
            if row["situacao"] == "automatica":
                item["rotulo"] = "Pronto para lançar sozinho"
            elif row["situacao"] == "aprovada":
                item["rotulo"] = ("Corrigido" if row["resultado"] == "Corrigido."
                                  else "Aprovado — aguardando liberação")
            elif row["situacao"] == "recusada":
                item["rotulo"] = "Recusado"
        historico.append(item)
        if row["tipo"] == "importar_extrato" and row["situacao"] == "pendente":
            pendentes.append(item)
        if row["tipo"] == "lancamento" and row["situacao"] == "pendente":
            lancamentos_pendentes.append(item)
    aguardando = [a for a in arquivos if a["situacao"] == "aguardando_vinculo"]
    postos_vinculo = banco.listar_postos(ctx.con, so_ativos=False) if configurar else []
    postos_config = ctx.con.execute(
        "SELECT id, nome, apelido, enviar_extratos_webposto FROM posto ORDER BY nome"
    ).fetchall() if configurar else []
    if not configurar:
        postos_config = []
    return (contas, arquivos, pendentes, historico, aguardando, postos_vinculo,
            postos_config, lancamentos_pendentes)


def _pagina_extratos(ctx: Ctx, *, erro=None, mensagem=None):
    (contas, arquivos, pendentes, historico, aguardando,
     postos_vinculo, postos_config, lancamentos_pendentes) = _extratos_da_tela(ctx)
    return _pagina(
        ctx, "extratos.html", contas=contas, arquivos=arquivos, pendentes=pendentes,
        historico=historico, aguardando=aguardando, postos_vinculo=postos_vinculo,
        postos_config=postos_config, lancamentos_pendentes=lancamentos_pendentes,
        pasta=caminhos.extratos(ctx.con), pode_configurar=ctx.pode(Acao.CONFIGURAR),
        pode_abrir=ctx.pode(Acao.CONFIGURAR),
        pode_aprovar={r["id"]: ctx.pode(Acao.COLETAR, r["posto_id"])
                      for r in pendentes + lancamentos_pendentes},
        pode_conferir={c["id"]: ctx.pode(Acao.COLETAR, c["posto_id"]) for c in contas},
        bloqueios={c["id"]: camada1.bloqueio_previa(ctx.con, c["id"]) for c in contas},
        pode_repropor={a["id"]: ctx.pode(Acao.COLETAR, a["posto_id"]) for a in historico},
        formato_debito=banco.formato_debito(ctx.con),
        formatos_debito=banco.formatos_debito(),
        erro=erro, mensagem=mensagem,
    )


@router.get("/extratos")
async def extratos_tela(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER)
    return _pagina_extratos(ctx)


@router.post("/extratos/formato-debito")
async def extratos_formato_debito(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    formato = _txt(ctx.form, "formato") or None
    try:
        banco.salvar_formato_debito(ctx.con, formato)
    except ValueError:
        raise Recusado(400, "Formato de débito inválido.")
    acesso.registrar(ctx.con, ctx.uid, "configurar_formato_debito",
                     f"formato={formato or 'nao_confirmado'}")
    return _ir("/extratos")


@router.post("/extratos/aprovacoes/{ticket}/repropor")
async def extratos_repropor(ticket: str, ctx: Ctx = Depends(_ctx_post)):
    row = ctx.con.execute("SELECT * FROM aprovacao WHERE ticket=?", (ticket,)).fetchone()
    if row is None or row["tipo"] != "importar_extrato":
        raise Recusado(404, "Aprovação de extrato não encontrada.")
    ctx.exigir(Acao.COLETAR, row["posto_id"])
    if not camada1.propor_de_novo(ctx.con, ticket):
        raise Recusado(400, "Este extrato não está disponível para reproposta.")
    acesso.registrar(ctx.con, ctx.uid, "repropor_extrato", f"aprovacao={row['id']}")
    return _ir("/extratos")


@router.post("/extratos/analisar")
async def extratos_analisar(ctx: Ctx = Depends(_ctx_post)):
    conta_id = _int(ctx.form, "conta_id")
    inicio, fim = _txt(ctx.form, "de"), _txt(ctx.form, "ate")
    if not conta_id:
        raise Recusado(400, "Escolha uma conta bancária.")
    conta = repositorio.conta_por_id(ctx.con, conta_id)
    if conta is None:
        raise Recusado(404, "Conta bancária não encontrada.")
    ctx.exigir(Acao.COLETAR, conta["posto_id"])
    try:
        data_de, data_ate = date.fromisoformat(inicio), date.fromisoformat(fim)
    except ValueError:
        return _pagina_extratos(ctx, erro="Informe um período válido.")
    try:
        factory = ctx.request.app.state.con_factory
        propostas = await run_in_threadpool(
            _com_conexao,
            factory,
            lambda con: camada2.analisar(con, conta_id, data_de, data_ate),
        )
    except Exception as exc:
        logger.warning("Conferência financeira de extrato falhou tipo=%s", type(exc).__name__)
        return _pagina_extratos(ctx, erro=explicar.erro_pt(exc))
    return _pagina_extratos(
        ctx, mensagem=f"{len(propostas)} proposta(s) nova(s) de lançamento."
    )


@router.get("/extratos/aprovacoes/{ticket}")
async def extrato_aprovacao(ticket: str, ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER)
    row = ctx.con.execute("SELECT * FROM aprovacao WHERE ticket=?", (ticket,)).fetchone()
    if row is None:
        raise Recusado(404, "Aprovação não encontrada.")
    ctx.exigir(Acao.VER, row["posto_id"])
    item = dict(row)
    item["resumo"] = json.loads(row["resumo_json"])
    if row["tipo"] == "lancamento":
        posto = banco.obter_posto(ctx.con, row["posto_id"])
        if posto:
            item["resumo"]["posto"] = {
                "id": posto["id"], "nome": posto["nome"], "apelido": posto["apelido"],
            }
    item["rotulo"] = _ROTULO_APROVACAO.get(row["situacao"], row["situacao"])
    if (row["tipo"] == "importar_extrato" and row["situacao"] == "automatica"
            and row["decidida_em"] is None):
        item["rotulo"] = "Aguardando importação automática"
    if row["tipo"] == "lancamento":
        if row["situacao"] == "automatica":
            item["rotulo"] = "Pronto para lançar sozinho"
        elif row["situacao"] == "aprovada":
            item["rotulo"] = ("Corrigido" if row["resultado"] == "Corrigido."
                              else "Aprovado — aguardando liberação")
        elif row["situacao"] == "recusada":
            item["rotulo"] = "Recusado"
    return _pagina(ctx, "extrato_aprovacao.html", aprovacao=item,
                   pode_decidir=ctx.pode(Acao.COLETAR, row["posto_id"]))


@router.post("/extratos/vincular")
async def extratos_vincular(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    arquivo_id = _int(ctx.form, "arquivo_id")
    posto_id = _int(ctx.form, "posto_id")
    cd_conta = _int(ctx.form, "cd_conta_webposto")
    if not arquivo_id or not posto_id or not cd_conta or cd_conta < 0:
        raise Recusado(400, "Informe arquivo, posto e conta válida do webPosto.")
    arquivo = ctx.con.execute(
        "SELECT situacao FROM extrato_arquivo WHERE id=?", (arquivo_id,)
    ).fetchone()
    if arquivo is None or arquivo["situacao"] != "aguardando_vinculo":
        raise Recusado(404, "Extrato aguardando vínculo não encontrado.")
    _posto_ou_404(ctx, posto_id)
    novas = entrada.vincular(ctx.con, arquivo_id, posto_id, cd_conta)
    acesso.registrar(ctx.con, ctx.uid, "vincular_conta_extrato",
                     f"arquivo={arquivo_id} posto={posto_id} conta={cd_conta} linhas={novas}")
    return _ir("/extratos")


@router.post("/postos/{posto_id}/extratos-webposto")
async def extratos_webposto_gravar(posto_id: int, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    _posto_ou_404(ctx, posto_id)
    valores = ctx.form.getlist("permitir")
    if not valores or any(valor not in ("0", "1") for valor in valores):
        raise Recusado(400, "Opção de envio inválida.")
    valor = "1" if "1" in valores else "0"
    ctx.con.execute(
        "UPDATE posto SET enviar_extratos_webposto=? WHERE id=?", (int(valor), posto_id)
    )
    ctx.con.commit()
    acesso.registrar(ctx.con, ctx.uid, "configurar_envio_extratos",
                     f"posto={posto_id} permitido={valor}")
    return _ir("/extratos")


@router.get("/extratos/autonomia")
async def extratos_autonomia(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.CONFIGURAR)
    tipos = ctx.con.execute(
        "SELECT * FROM autonomia ORDER BY chave_tipo"
    ).fetchall()
    return _pagina(ctx, "extratos_autonomia.html", tipos=tipos)


@router.post("/extratos/autonomia")
async def extratos_autonomia_gravar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    chave_tipo = _txt(ctx.form, "chave_tipo")
    acao = _txt(ctx.form, "acao")
    if not chave_tipo or acao not in ("desligar", "religar"):
        raise Recusado(400, "Ação de autonomia inválida.")
    existente = ctx.con.execute(
        "SELECT id FROM autonomia WHERE chave_tipo=?", (chave_tipo,)
    ).fetchone()
    if existente is None:
        raise Recusado(404, "Tipo de autonomia não encontrado.")
    ligado = acao == "religar"
    autonomia.definir_automatico(ctx.con, chave_tipo, ligado)
    acesso.registrar(
        ctx.con,
        ctx.uid,
        "religar_automatico_extrato" if ligado else "desligar_automatico_extrato",
        f"tipo={chave_tipo}",
    )
    return _ir("/extratos/autonomia")


@router.post("/extratos/aprovacoes/{ticket}")
async def extratos_decidir(ticket: str, ctx: Ctx = Depends(_ctx_post)):
    row = ctx.con.execute("SELECT * FROM aprovacao WHERE ticket=?", (ticket,)).fetchone()
    if row is None:
        raise Recusado(404, "Aprovação não encontrada.")
    ctx.exigir(Acao.COLETAR, row["posto_id"])
    acao = _txt(ctx.form, "acao")
    if row["tipo"] == "lancamento":
        if acao not in ("aprovar", "recusar", "corrigir"):
            raise Recusado(400, "Escolha aprovar, recusar ou corrigir.")
        try:
            ok, mensagem = camada2.decidir(
                ctx.con, ticket, acao,
                plano_conta=_txt(ctx.form, "plano_conta"),
                centro_custo=_txt(ctx.form, "centro_custo"),
                quem=f"usuario:{ctx.uid}",
            )
        except ValueError as exc:
            raise Recusado(
                400, "Informe o plano de conta e o centro de custo corrigidos."
            ) from exc
    else:
        if row["tipo"] != "importar_extrato" or acao not in ("aprovar", "recusar"):
            raise Recusado(400, "Escolha aprovar ou recusar.")
        ok, mensagem = aprovacoes.decidir(
            ctx.con, ticket, acao == "aprovar", f"usuario:{ctx.uid}", "painel"
        )
    if not ok:
        return _ir("/extratos?resolvido=1")
    acesso.registrar(ctx.con, ctx.uid, f"{acao}_aprovacao_extrato",
                     f"aprovacao={row['id']} posto={row['posto_id']}")
    if acao == "aprovar" and row["tipo"] == "importar_extrato":
        factory = ctx.request.app.state.con_factory

        def executar(factory_, aprovacao_id):
            return _com_conexao(factory_, lambda con: camada1.executar(con, aprovacao_id))

        _em_segundo_plano("importar-extrato", executar, factory, row["id"])
    return _ir("/extratos")


def _abrir_pasta_extratos(caminho: str) -> None:
    os.startfile(caminho)


@router.post("/extratos/abrir-pasta")
async def extratos_abrir_pasta(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    _em_segundo_plano("abrir-pasta-extratos", _abrir_pasta_extratos,
                      str(caminhos.extratos(ctx.con)))
    return _ir("/extratos")


# ---------------------------------------------------------------- Usuários

def _pagina_usuarios(ctx: Ctx, status: int = 200, **dados):
    usuarios = [{"u": u, "postos": [int(p) for p in (u["postos"] or "").split(",") if p]}
                for u in acesso.listar_usuarios(ctx.con)]
    return _pagina(ctx, "usuarios.html", status, usuarios=usuarios, perfis=[p.value for p in Perfil],
                   todos_postos=banco.listar_postos(ctx.con, so_ativos=False), **dados)


@router.get("/usuarios")
async def usuarios(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.GERIR_USUARIOS)
    return _pagina_usuarios(ctx)


@router.post("/usuarios")
async def usuarios_gravar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.GERIR_USUARIOS)
    f, acao, con = ctx.form, _txt(ctx.form, "acao"), ctx.con
    perfil = _txt(f, "perfil")
    if acao in ("criar", "editar") and perfil not in {p.value for p in Perfil}:
        return _pagina_usuarios(ctx, 400, erro="Escolha o perfil.")
    if acao in ("criar", "editar") and any(banco.obter_posto(con, p) is None for p in _ints(f, "postos")):
        return _pagina_usuarios(ctx, 400, erro="Posto inválido.")
    try:
        if acao == "criar":
            nome, login = _txt(f, "nome"), _txt(f, "login")
            if not nome or not login:
                return _pagina_usuarios(ctx, 400, erro="Preencha nome e usuário.")
            uid = acesso.criar_usuario(con, nome, login, _txt(f, "senha", cru=True),
                                       Perfil(perfil), _ints(f, "postos"))
            try:
                acesso.definir_email(con, uid, _txt(f, "email"))
            except ValueError:
                con.execute("DELETE FROM usuario_posto WHERE usuario_id=?", (uid,))
                con.execute("DELETE FROM usuario WHERE id=?", (uid,))
                con.commit()
                raise
            acesso.registrar(con, ctx.uid, "criar_usuario", f"usuario={uid} perfil={perfil}")
            return _ir("/usuarios")
        uid = _int(f, "id")
        alvo = acesso.carregar_usuario(con, uid) if uid else None
        if alvo is None:
            raise Recusado(404, "Usuário não encontrado.")
        sessoes: Sessoes = ctx.request.app.state.sessoes
        if acao == "editar":
            acesso.atualizar_usuario(con, uid, _txt(f, "nome") or alvo["nome"], Perfil(perfil),
                                     _ints(f, "postos"))
            acesso.definir_email(con, uid, _txt(f, "email"))
            acesso.registrar(con, ctx.uid, "editar_usuario", f"usuario={uid} perfil={perfil}")
        elif acao in ("desativar", "ativar"):
            acesso.definir_ativo(con, uid, acao == "ativar")
            if acao == "desativar":
                sessoes.encerrar_usuario(uid)
            acesso.registrar(con, ctx.uid, f"{acao}_usuario", f"usuario={uid}")
        elif acao == "senha":
            acesso.definir_senha(con, uid, _txt(f, "senha", cru=True))
            sessoes.encerrar_usuario(uid, exceto=ctx.token)
            acesso.registrar(con, ctx.uid, "redefinir_senha", f"usuario={uid}")
        else:
            raise Recusado(400, "Ação desconhecida.")
    except sqlite3.IntegrityError:
        con.rollback()
        return _pagina_usuarios(ctx, 400, erro="Esse usuário (login) já existe.")
    except ValueError as exc:  # mensagens próprias, em português
        return _pagina_usuarios(ctx, 400, erro=str(exc))
    return _ir("/usuarios")


@router.get("/usuarios/log")
async def usuarios_log(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.GERIR_USUARIOS)
    linhas = ctx.con.execute(
        "SELECT l.*, u.nome, u.login FROM log_acesso l LEFT JOIN usuario u ON u.id = l.usuario_id"
        " ORDER BY l.id DESC LIMIT 300").fetchall()
    return _pagina(ctx, "log.html", linhas=linhas)
