"""Rotas do painel local.

Segurança: a sessão (em memória) guarda só o usuario_id; cada requisição recarrega o
usuário e decide com `acesso.pode_agora` / `postos_visiveis_agora`. Todo POST exige o
campo `csrf`. Segredos nunca são exibidos nem registrados: a tela só mostra `••••`.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import jinja2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from apps.match import (acesso, agendador, banco, coletas, credenciais, explicar, relatorio_xlsx,
                        rotina, unidades)
from apps.match.acesso import Acao, Perfil
from apps.match.canais import envio
from src.modules.cash_reconciliation import config as config_cr
from src.modules.cash_reconciliation.adapters import pagbank_edi, webposto_caixas
from src.modules.cash_reconciliation.domain.tempo import agora, formatar_data_hora, ontem

logger = logging.getLogger(__name__)

PASTA = Path(__file__).resolve().parent
COOKIE, COOKIE_PRE = "lm_sessao", "lm_pre"
EXPIRA_SEGUNDOS = 12 * 3600
SEM_ACESSO = "Você não tem acesso a isto."
FORM_EXPIRADO = "Formulário expirado ou inválido. Recarregue a página e tente de novo."
AVISO_POSTO = "Cadastre cada posto em uma só máquina para evitar coleta duplicada."
COLETA_EM_ANDAMENTO = "Já existe uma coleta em andamento. Aguarde terminar."
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

class Sessoes:
    """token -> [usuario_id, último uso (monotônico), csrf]. Some ao reiniciar o app."""

    def __init__(self):
        self._d: dict[str, list] = {}
        self._trava = threading.Lock()

    def criar(self, usuario_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self._trava:
            self._d[token] = [usuario_id, _relogio(), secrets.token_urlsafe(32)]
        return token

    def obter(self, token: str | None) -> tuple[int, str] | None:
        if not token:
            return None
        with self._trava:
            s = self._d.get(token)
            if s is None:
                return None
            if _relogio() - s[1] > EXPIRA_SEGUNDOS:
                del self._d[token]
                return None
            s[1] = _relogio()
            return s[0], s[2]

    def encerrar(self, token: str | None) -> None:
        with self._trava:
            self._d.pop(token or "", None)

    def encerrar_usuario(self, usuario_id: int, exceto: str | None = None) -> None:
        with self._trava:
            for tok in [t for t, s in self._d.items() if s[0] == usuario_id and t != exceto]:
                del self._d[tok]


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
                    fonte=lambda t: _NOME_FONTE.get(t, t))
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


def _menu(ctx: Ctx) -> list[tuple[str, str]]:
    itens = [("/", "Hoje")]
    if ctx.pode(Acao.CADASTRAR_POSTO) or ctx.pode(Acao.TROCAR_CREDENCIAL):
        itens.append(("/postos", "Postos"))
    if ctx.pode(Acao.CONFIGURAR):
        itens += [("/canais", "Canais"), ("/agenda", "Agenda")]
    itens.append(("/historico", "Histórico"))
    if ctx.pode(Acao.GERIR_USUARIOS):
        itens.append(("/usuarios", "Usuários"))
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
async def entrar_form(request: Request, con=Depends(_conexao)):
    if acesso.precisa_primeiro_uso(con):
        return _ir("/primeiro-uso")
    return _publica(request, "entrar.html")


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
    token = sessoes.criar(usuario["id"])
    acesso.registrar(con, usuario["id"], "entrar", "")
    resp = _ir("/")
    resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")
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
async def hoje(ctx: Ctx = Depends(_ctx)):
    return _pagina_hoje(ctx)


def _coletar(con_factory, posto_id: int, visivel: bool) -> None:
    _com_conexao(con_factory, lambda con: asyncio.run(
        rotina.executar(con, posto_id=posto_id, visivel=visivel)))


@router.post("/coletar")
async def coletar(posto_id: int, visivel: int = 0, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.COLETAR, posto_id)
    posto = _posto_ou_404(ctx, posto_id)
    if not posto["ativo"]:
        raise Recusado(400, "Este posto está desativado.")
    if rotina.em_andamento():
        return _pagina_hoje(ctx, erro=COLETA_EM_ANDAMENTO)
    _em_segundo_plano("coleta", _coletar, ctx.request.app.state.con_factory, posto_id, bool(visivel))
    acesso.registrar(ctx.con, ctx.uid, "coletar", f"posto={posto_id} visivel={int(bool(visivel))}")
    return _pagina_hoje(ctx, mensagem="Coleta iniciada. Atualize a página em alguns minutos.")


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


@router.get("/planilha")
async def planilha(posto_id: int, dia: str = "", ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER, posto_id)
    _posto_ou_404(ctx, posto_id)
    d = _dia_param(dia)
    if d is None:
        raise Recusado(400, "Dia inválido. Use dd-mm-aaaa.")
    arquivo = relatorio_xlsx.mais_recente(ctx.con, posto_id, d) or relatorio_xlsx.gerar(ctx.con, posto_id, d)
    acesso.registrar(ctx.con, ctx.uid, "baixar_planilha", f"posto={posto_id} dia={d}")
    return FileResponse(arquivo, media_type=XLSX, filename=arquivo.name)


# ---------------------------------------------------------------- Postos

def _pagina_postos(ctx: Ctx, status: int = 200, **dados):
    if ctx.pode(Acao.CADASTRAR_POSTO):
        postos = banco.listar_postos(ctx.con, so_ativos=False)
    else:
        postos = [p for p in (banco.obter_posto(ctx.con, i) for i in ctx.postos()) if p]
    itens = [{"posto": p, "pode_fontes": ctx.pode(Acao.TROCAR_CREDENCIAL, p["id"])} for p in postos]
    units = Path(config_cr.__file__).parent / "units.json"
    return _pagina(ctx, "postos.html", status, postos=itens, aviso=AVISO_POSTO,
                   pode_cadastrar=ctx.pode(Acao.CADASTRAR_POSTO), tem_units=units.exists(), **dados)


@router.get("/postos")
async def postos(ctx: Ctx = Depends(_ctx)):
    if not (ctx.pode(Acao.CADASTRAR_POSTO) or ctx.pode(Acao.TROCAR_CREDENCIAL)):
        raise Recusado(403, SEM_ACESSO)
    return _pagina_postos(ctx)


@router.post("/postos")
async def postos_gravar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CADASTRAR_POSTO)
    f, acao = ctx.form, _txt(ctx.form, "acao")
    if acao in ("desativar", "ativar", "editar"):
        pid = _int(f, "id")
        _posto_ou_404(ctx, pid or 0)
    if acao in ("desativar", "ativar"):
        banco.definir_posto_ativo(ctx.con, pid, acao == "ativar")
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
    dados = (nome, _txt(f, "apelido") or None, _txt(f, "cnpj") or None, codigo)
    if acao == "novo":
        pid = banco.inserir_posto(ctx.con, *dados)
    else:
        banco.atualizar_posto(ctx.con, pid, *dados)
    acesso.registrar(ctx.con, ctx.uid, f"{acao}_posto", f"posto={pid}")
    return _ir("/postos")


@router.post("/postos/importar-logos")
async def importar_logos(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CADASTRAR_POSTO)
    caminho = Path(config_cr.__file__).parent / "units.json"
    if not caminho.exists():
        return _pagina_postos(ctx, 404, erro="Arquivo units.json não encontrado nesta instalação.")
    try:
        n = unidades.importar_units_json(ctx.con, caminho)
    except unidades.CodigoInvalido as exc:  # mensagem própria, em português
        ctx.con.rollback()
        return _pagina_postos(ctx, 400, erro=f"units.json não importado: {exc}")
    except (ValueError, KeyError, TypeError, sqlite3.Error):
        ctx.con.rollback()
        return _pagina_postos(ctx, 400, erro="Não foi possível ler o units.json.")
    acesso.registrar(ctx.con, ctx.uid, "importar_units_json", f"criados={n}")
    return _pagina_postos(ctx, mensagem=f"{n} posto(s) importado(s) do units.json.")


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
    try:
        if arquivo is None or isinstance(arquivo, str):
            raise ValueError
        bruto = await arquivo.read(_MAX_IMPORTAR + 1)
        if len(bruto) > _MAX_IMPORTAR:
            raise ValueError
        dados = json.loads(bruto.decode("utf-8"))
        if not isinstance(dados, dict):
            raise ValueError
        n = unidades.importar_config(ctx.con, dados)
    except unidades.CodigoInvalido as exc:  # mensagem própria, em português
        ctx.con.rollback()
        return _pagina_postos(ctx, 400, erro=f"Configuração não importada: {exc}")
    except (ValueError, KeyError, TypeError, AttributeError, sqlite3.Error):
        ctx.con.rollback()
        return _pagina_postos(ctx, 400, erro="Arquivo de configuração inválido.")
    acesso.registrar(ctx.con, ctx.uid, "importar_config", f"criados={n}")
    return _pagina_postos(ctx, mensagem=f"{n} posto(s) importado(s). Cadastre as senhas em Fontes.")


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
        cfg = {"chat_ids": _lista(_txt(form, "chat_ids"))}
    elif tipo == "email":
        porta = _txt(form, "porta") or "587"
        if not porta.isdigit():
            raise ValueError("A porta do servidor de e-mail deve ser um número.")
        cfg = {"servidor": _txt(form, "servidor"), "porta": int(porta), "usuario": _txt(form, "usuario"),
               "destinatarios": _lista(_txt(form, "destinatarios"))}
    else:
        cfg = {}
    cfg["postos"] = _ints(form, "postos")
    return {**(atual or {}), **cfg}


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

@router.get("/agenda")
async def agenda(salvo: int = 0, ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.CONFIGURAR)
    coleta, repescagem = rotina.horarios(ctx.con)
    return _pagina(ctx, "agenda.html", hora_coleta=coleta, hora_repescagem=repescagem,
                   mensagem="Horários salvos." if salvo else None)


@router.post("/agenda")
async def agenda_gravar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.CONFIGURAR)
    coleta, repescagem = _txt(ctx.form, "hora_coleta"), _txt(ctx.form, "hora_repescagem")
    if not (_RE_HORA.match(coleta) and _RE_HORA.match(repescagem)):
        return _pagina(ctx, "agenda.html", 400, hora_coleta=coleta, hora_repescagem=repescagem,
                       erro="Horário inválido. Use HH:MM, por exemplo 06:00.")
    banco.salvar_horarios(ctx.con, coleta, repescagem)
    sched = ctx.request.app.state.sched
    if sched is not None:
        agendador.reagendar(sched, ctx.request.app.state.con_factory)
    acesso.registrar(ctx.con, ctx.uid, "agenda", f"coleta={coleta} repescagem={repescagem}")
    return _ir("/agenda?salvo=1")


# ---------------------------------------------------------------- Histórico

@router.get("/historico")
async def historico(ctx: Ctx = Depends(_ctx)):
    envios = banco.ultimos_envios(ctx.con) if ctx.pode(Acao.CONFIGURAR) else None
    return _pagina(ctx, "historico.html", coletas=banco.ultimas_coletas(ctx.con, ctx.postos()),
                   envios=envios)


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
