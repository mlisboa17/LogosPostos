"""Telas do módulo Notas Fiscais: consulta, empresas, escritórios, pacotes e importação."""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from apps.match import acesso, banco, caminhos
from apps.match.acesso import Acao
from apps.match.fiscal import captura, captura_nfse, certificados, envio_mensal, repositorio as repo
from apps.match.painel.rotas import (Ctx, Recusado, _com_conexao, _ctx, _ctx_post, _em_segundo_plano, _int,
                                     _ints, _ir, _itens_configuracao, _pagina, _txt)
from src.modules.cash_reconciliation.domain.tempo import hoje
from src.modules.fiscal_docs import acervo, pdf
from src.modules.fiscal_docs.modelos import FUSO, XmlInvalido
from src.modules.fiscal_docs.parser import ler

router = APIRouter()

MAX_UPLOAD = 50 * 1024 * 1024
MAX_ARQUIVOS = 2000
_RE_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_TIPOS = {"": "Todos", "nfe": "NF-e", "nfse": "NFS-e", "cte": "CT-e"}
_SITUACOES = {"": "Todas", "autorizada": "Autorizada", "cancelada": "Cancelada", "so_resumo": "Só resumo"}
_SITUACAO_PACOTE = {"gerado": "📦 pronto para baixar", "retido": "⚠ retido", "aprovado": "✅ aprovado", "enviando": "⏳ enviando",
                    "enviado": "✅ enviado", "erro": "❌ erro"}


def _empresas(ctx: Ctx) -> list[int]:
    return acesso.empresas_visiveis(ctx.con, acesso.carregar_usuario(ctx.con, ctx.uid))


def _exigir_empresa(ctx: Ctx, empresa_id: int | None) -> int:
    if empresa_id is None or empresa_id not in _empresas(ctx):
        raise Recusado(403, "Você não tem acesso a esta empresa.")
    return empresa_id


def _data(texto: str | None) -> date | None:
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _decimal(texto: str | None) -> Decimal | None:
    try:
        return Decimal(texto.replace(".", "").replace(",", ".")) if texto else None
    except InvalidOperation:
        return None


# ---------------------------------------------------------------- consulta

@router.get("/notas")
async def notas(ctx: Ctx = Depends(_ctx), empresa_id: str = "", inicio: str = "", fim: str = "",
                fornecedor: str = "", tipo: str = "", situacao: str = "", combustivel: str = "",
                valor_min: str = "", valor_max: str = ""):
    ctx.exigir(Acao.VER_FISCAL)
    visiveis = _empresas(ctx)
    hoje_ = hoje()
    ini = _data(inicio) or (hoje_.replace(day=1) - timedelta(days=1)).replace(day=1)
    fi = _data(fim) or hoje_
    escolhida = int(empresa_id) if empresa_id.isdigit() and int(empresa_id) in visiveis else None
    filtro = repo.FiltroDocs(
        empresas=[escolhida] if escolhida else visiveis, inicio=ini, fim=fi, fornecedor=fornecedor or None,
        tipo=tipo if tipo in _TIPOS and tipo else None, situacao=situacao if situacao in _SITUACOES and situacao else None,
        combustivel={"sim": True, "nao": False}.get(combustivel), valor_min=_decimal(valor_min),
        valor_max=_decimal(valor_max))
    docs = repo.buscar_documentos(ctx.con, filtro)
    total = sum((Decimal(d["valor_total"]) for d in docs), Decimal(0))
    fim_mes_passado = hoje_.replace(day=1) - timedelta(days=1)
    atalhos = [("Mês passado", fim_mes_passado.replace(day=1), fim_mes_passado),
               ("Este mês", hoje_.replace(day=1), hoje_), ("Últimos 30 dias", hoje_ - timedelta(days=30), hoje_)]
    return _pagina(ctx, "fiscal_notas.html", docs=docs, total=total, empresas=repo.listar_empresas(ctx.con, visiveis),
                   atalhos=[(n, a.isoformat(), b.isoformat()) for n, a, b in atalhos],
                   pode_buscar=ctx.pode(Acao.GERIR_FISCAL),
                   f={"empresa_id": escolhida, "inicio": ini.isoformat(), "fim": fi.isoformat(),
                      "fornecedor": fornecedor, "tipo": tipo, "situacao": situacao, "combustivel": combustivel,
                      "valor_min": valor_min, "valor_max": valor_max},
                   tipos=_TIPOS, situacoes=_SITUACOES)


def _docs_permitidos(ctx: Ctx, ids: list[int]) -> list:
    visiveis = set(_empresas(ctx))
    docs = [ctx.con.execute("SELECT * FROM documento WHERE id=?", (i,)).fetchone() for i in ids[:2000]]
    docs = [d for d in docs if d is not None and d["empresa_id"] in visiveis and d["xml_path"]]
    if not docs:
        raise Recusado(404, "Nenhuma nota com XML selecionada.")
    return docs


def _zip(arquivos: list[tuple[str, bytes]], nome: str) -> Response:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, dados in arquivos:
            z.writestr(n, dados)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/notas/xml")
async def notas_xml(ctx: Ctx = Depends(_ctx), ids: list[int] = Query(default=[])):
    ctx.exigir(Acao.VER_FISCAL)
    docs = _docs_permitidos(ctx, ids)
    return _zip([(f"{d['chave']}.xml", Path(d["xml_path"]).read_bytes()) for d in docs], "notas-xml.zip")


@router.get("/notas/pdf")
async def notas_pdf(ctx: Ctx = Depends(_ctx), ids: list[int] = Query(default=[]), modo: str = "separados"):
    ctx.exigir(Acao.VER_FISCAL)
    docs = _docs_permitidos(ctx, ids)

    def gerar():
        saida = []
        for d in docs:
            xml = Path(d["xml_path"]).read_bytes()
            saida.append((d["chave"], pdf.gerar_pdf(xml, ler(xml))))
        return saida
    pdfs = await run_in_threadpool(gerar)
    if modo == "unificado":
        return Response(pdf.unir([b for _, b in pdfs]), media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="notas.pdf"'})
    return _zip([(f"{c}.pdf", b) for c, b in pdfs], "notas-pdf.zip")


@router.get("/notas/planilha")
async def notas_planilha(ctx: Ctx = Depends(_ctx), empresa_id: int = 0, competencia: str = ""):
    ctx.exigir(Acao.VER_FISCAL)
    _exigir_empresa(ctx, empresa_id)
    if not re.fullmatch(r"\d{4}-\d{2}", competencia):
        raise Recusado(400, "Competência inválida.")
    from apps.match.fiscal import planilha
    destino = caminhos.pacotes() / "planilhas" / f"Resumo_{empresa_id}_{competencia}.xlsx"
    await run_in_threadpool(_com_conexao, ctx.request.app.state.con_factory,
                            lambda con: planilha.gerar_planilha(con, empresa_id, competencia, destino))
    return FileResponse(destino, filename=destino.name)


# ---------------------------------------------------------------- caminho guiado

def _linha_comecar(con, e) -> dict:
    ultima = repo.ultima_captura(con, e["id"], captura_nfse.FONTE)
    if ultima is None:
        resultado = "—"
    elif ultima["situacao"] == "erro":
        resultado = f"❌ {ultima['erro_texto']}"
    elif ultima["qtd_novas"]:
        resultado = f"✅ {ultima['qtd_novas']} nota(s) nova(s)."
    else:
        resultado = captura_nfse.MSG_NENHUMA
    proxima = repo.nsu_de(con, e["id"])["proxima_consulta_em"]
    if proxima and datetime.fromisoformat(proxima) > datetime.now(timezone.utc):
        proxima = datetime.fromisoformat(proxima).astimezone(FUSO).strftime("%d/%m/%Y %H:%M")
    else:
        proxima = None
    return {"e": e, "cert": certificados.situacao(con, e["id"]), "ultima": ultima, "resultado": resultado,
            "proxima": proxima}


def pagina_comecar(ctx: Ctx, status: int = 200, buscando: bool = False, **dados):
    linhas = [_linha_comecar(ctx.con, e) for e in repo.listar_empresas(ctx.con)]
    total = ctx.con.execute("SELECT COUNT(*) FROM documento WHERE tipo='nfse'").fetchone()[0]
    return _pagina(ctx, "comecar.html", status, empresas=linhas, total_nfse=total,
                   tem_certificado=any(l["cert"] for l in linhas),
                   buscando=buscando or captura_nfse.em_andamento(), **dados)


@router.get("/comecar")
async def comecar(ctx: Ctx = Depends(_ctx), buscando: int = 0):
    ctx.exigir(Acao.GERIR_FISCAL)
    return pagina_comecar(ctx, buscando=bool(buscando))


@router.post("/comecar/certificado")
async def comecar_certificado(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.GERIR_FISCAL)
    arquivo, senha = ctx.form.get("arquivo"), _txt(ctx.form, "senha", cru=True)
    if arquivo is None or isinstance(arquivo, str) or not senha:
        return pagina_comecar(ctx, 400, erro="Escolha o arquivo do certificado (.pfx ou .p12) e digite a senha.")
    pfx = await arquivo.read(certificados.MAX_BYTES + 1)
    try:
        empresa_id, info = certificados.criar_empresa_pelo_certificado(ctx.con, pfx, senha)
    except certificados.CertificadoInvalido as exc:
        return pagina_comecar(ctx, 400, erro=str(exc))
    finally:
        senha = ""
    acesso.registrar(ctx.con, ctx.uid, "enviar_certificado", f"empresa={empresa_id} cnpj={info.cnpj}")
    return pagina_comecar(ctx, mensagem=f"Certificado de {info.titular} salvo, vale até "
                                        f"{info.valido_ate:%d/%m/%Y}. Agora clique em Buscar notas de serviço.")


@router.post("/comecar/buscar")
async def comecar_buscar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.GERIR_FISCAL)
    _em_segundo_plano("busca-nfse", captura_nfse.buscar_todas, ctx.request.app.state.con_factory)
    acesso.registrar(ctx.con, ctx.uid, "buscar_nfse", "")
    return _ir("/comecar?buscando=1")


@router.get("/configuracoes")
async def configuracoes(ctx: Ctx = Depends(_ctx)):
    return _pagina(ctx, "configuracoes.html", itens=_itens_configuracao(ctx))


# ---------------------------------------------------------------- empresas

def _pagina_empresas(ctx: Ctx, status: int = 200, **dados):
    linhas = [{"e": e, "ultima": repo.ultima_captura(ctx.con, e["id"]),
               "cert": certificados.situacao(ctx.con, e["id"])} for e in repo.listar_empresas(ctx.con)]
    return _pagina(ctx, "fiscal_empresas.html", status, empresas=linhas, postos=banco.listar_postos(ctx.con, False),
                   **dados)


@router.get("/empresas")
async def empresas(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.GERIR_FISCAL)
    return _pagina_empresas(ctx)


@router.post("/empresas")
async def salvar_empresa(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.GERIR_FISCAL)
    f = ctx.form
    cnpj = repo.so_digitos(_txt(f, "cnpj"))
    if len(cnpj) != 14 or not _txt(f, "razao_social"):
        return _pagina_empresas(ctx, 400, erro="Informe o CNPJ (14 dígitos) e a razão social.")
    try:
        repo.salvar_empresa(ctx.con, cnpj, _txt(f, "razao_social"), _txt(f, "apelido") or None,
                            _txt(f, "municipio") or None, (_txt(f, "uf") or "PE").upper()[:2],
                            _int(f, "posto_id"), _int(f, "empresa_id"))
    except Exception:  # noqa: BLE001 - CNPJ repetido ou posto inválido
        ctx.con.rollback()
        return _pagina_empresas(ctx, 400, erro="Não foi possível salvar: confira se o CNPJ já está cadastrado.")
    acesso.registrar(ctx.con, ctx.uid, "salvar_empresa", cnpj)
    return _ir("/empresas")


@router.post("/empresas/{empresa_id}/certificado")
async def enviar_certificado(empresa_id: int, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.GERIR_FISCAL)
    if repo.obter_empresa(ctx.con, empresa_id) is None:
        raise Recusado(404, "Empresa não encontrada.")
    arquivo, senha = ctx.form.get("arquivo"), _txt(ctx.form, "senha", cru=True)
    if arquivo is None or isinstance(arquivo, str) or not senha:
        return _pagina_empresas(ctx, 400, erro="Escolha o arquivo do certificado (.pfx ou .p12) e digite a senha.")
    pfx = await arquivo.read(certificados.MAX_BYTES + 1)
    try:
        info = certificados.salvar(ctx.con, empresa_id, pfx, senha)
    except certificados.CertificadoInvalido as exc:
        return _pagina_empresas(ctx, 400, erro=str(exc))
    finally:
        senha = ""
    acesso.registrar(ctx.con, ctx.uid, "enviar_certificado", f"empresa={empresa_id} cnpj={info.cnpj}")
    matriz = " Certificado da matriz: vale para esta filial." if info.da_matriz else ""
    return _pagina_empresas(ctx, mensagem=f"Certificado salvo: {info.titular}, vale até "
                                          f"{info.valido_ate:%d/%m/%Y} ({info.dias_restantes} dias).{matriz}")


@router.post("/empresas/{empresa_id}/capturar")
async def capturar_agora(empresa_id: int, ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.GERIR_FISCAL)
    fabrica = ctx.request.app.state.con_factory
    _em_segundo_plano("captura-fiscal", captura.capturar_todas, fabrica, hoje())
    acesso.registrar(ctx.con, ctx.uid, "capturar_notas", str(empresa_id))
    return _pagina_empresas(ctx, mensagem="Captura iniciada. Atualize a página em alguns minutos.")


# ---------------------------------------------------------------- escritórios

def _pagina_escritorios(ctx: Ctx, status: int = 200, **dados):
    lista = [{"o": o, "emails": ", ".join(json.loads(o["emails_json"] or "[]")),
              "empresas": [e["id"] for e in repo.empresas_do_escritorio(ctx.con, o["id"])]}
             for o in repo.listar_escritorios(ctx.con)]
    return _pagina(ctx, "fiscal_escritorios.html", status, escritorios=lista,
                   empresas=repo.listar_empresas(ctx.con), **dados)


@router.get("/escritorios")
async def escritorios(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.GERIR_FISCAL)
    return _pagina_escritorios(ctx)


@router.post("/escritorios")
async def salvar_escritorio(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.GERIR_FISCAL)
    f = ctx.form
    emails = [e.strip() for e in re.split(r"[,;\s]+", _txt(f, "emails")) if e.strip()]
    dia, modo, modo_pdf = _int(f, "dia_envio"), _txt(f, "modo"), _txt(f, "pdf")
    if (not _txt(f, "nome") or not emails or not all(_RE_EMAIL.match(e) for e in emails)
            or dia is None or not 1 <= dia <= 28 or modo not in ("enviar", "so_gerar")
            or modo_pdf not in ("separados", "unificado", "ambos")):
        return _pagina_escritorios(ctx, 400, erro="Confira nome, e-mails (separados por vírgula), "
                                                  "dia de envio (1 a 28), modo e formato dos PDFs.")
    validas = {e["id"] for e in repo.listar_empresas(ctx.con)}
    repo.salvar_escritorio(ctx.con, _txt(f, "nome"), emails, dia, modo, modo_pdf,
                           [e for e in _ints(f, "empresas") if e in validas], _int(f, "escritorio_id"))
    acesso.registrar(ctx.con, ctx.uid, "salvar_escritorio", _txt(f, "nome"))
    return _ir("/escritorios")


# ---------------------------------------------------------------- pacotes

def _pagina_pacotes(ctx: Ctx, status: int = 200, **dados):
    lista = [{"p": p, "situacao": _SITUACAO_PACOTE.get(p["situacao"], p["situacao"]),
              "partes": len(json.loads(p["arquivos_json"] or "[]"))}
             for p in repo.pacotes(ctx.con, _empresas(ctx))]
    return _pagina(ctx, "fiscal_pacotes.html", status, pacotes=lista,
                   pode_aprovar=ctx.pode(Acao.APROVAR_PACOTE), **dados)


def _pacote_permitido(ctx: Ctx, pacote_id: int):
    p = repo.obter_pacote(ctx.con, pacote_id)
    if p is None or p["empresa_id"] not in _empresas(ctx):
        raise Recusado(404, "Pacote não encontrado.")
    return p


@router.get("/pacotes")
async def pacotes(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER_FISCAL)
    return _pagina_pacotes(ctx)


async def _acao_pacote(ctx: Ctx, pacote_id: int, funcao, ok: str):
    ctx.exigir(Acao.APROVAR_PACOTE)
    p = _pacote_permitido(ctx, pacote_id)
    empresa = repo.obter_empresa(ctx.con, p["empresa_id"])
    if empresa["posto_id"] is not None:
        ctx.exigir(Acao.APROVAR_PACOTE, empresa["posto_id"])
    fabrica = ctx.request.app.state.con_factory  # sqlite3: conexão própria na thread do envio
    try:
        r = await run_in_threadpool(_com_conexao, fabrica, lambda con: funcao(con, pacote_id, ctx.uid))
    except ValueError as exc:
        return _pagina_pacotes(ctx, 400, erro=str(exc))
    if r.get("situacao") in ("erro", "retido"):
        return _pagina_pacotes(ctx, 400, erro=r.get("motivo") or "Não foi possível enviar.")
    return _pagina_pacotes(ctx, mensagem=ok)


@router.post("/pacotes/{pacote_id}/aprovar")
async def aprovar(pacote_id: int, ctx: Ctx = Depends(_ctx_post)):
    return await _acao_pacote(ctx, pacote_id, envio_mensal.aprovar_e_enviar, "Pacote enviado.")


@router.post("/pacotes/{pacote_id}/reenviar")
async def reenviar(pacote_id: int, ctx: Ctx = Depends(_ctx_post)):
    return await _acao_pacote(ctx, pacote_id, envio_mensal.reenviar, "Pacote reenviado.")


@router.get("/pacotes/{pacote_id}/baixar")
async def baixar(pacote_id: int, parte: int = 1, ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER_FISCAL)
    p = _pacote_permitido(ctx, pacote_id)
    arquivos = json.loads(p["arquivos_json"] or "[]")
    if not 1 <= parte <= len(arquivos) or not Path(arquivos[parte - 1]).exists():
        raise Recusado(404, "Arquivo do pacote não encontrado. Use Reenviar para gerar de novo.")
    caminho = Path(arquivos[parte - 1])
    return FileResponse(caminho, filename=caminho.name)


# ---------------------------------------------------------------- importação manual

def _pagina_importar(ctx: Ctx, status: int = 200, **dados):
    return _pagina(ctx, "fiscal_importar.html", status, empresas=repo.listar_empresas(ctx.con, _empresas(ctx)),
                   **dados)


def _nome_seguro(nome: str) -> bool:
    p = PurePosixPath(nome.replace("\\", "/"))
    return bool(nome) and not p.is_absolute() and ".." not in p.parts and not re.match(r"^[A-Za-z]:", nome)


def _xmls_do_upload(nome: str, bruto: bytes, recusados: list[str]) -> list[tuple[str, bytes]]:
    if not nome.lower().endswith(".zip"):
        return [(nome, bruto)]
    saida = []
    try:
        with zipfile.ZipFile(io.BytesIO(bruto)) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
            if len(infos) > MAX_ARQUIVOS:
                recusados.append(f"{nome} (mais de {MAX_ARQUIVOS} arquivos)")
                return []
            total = 0
            for info in infos:
                if not _nome_seguro(info.filename) or not info.filename.lower().endswith(".xml"):
                    recusados.append(info.filename)
                    continue
                total += info.file_size
                if total > MAX_UPLOAD:
                    recusados.append(f"{nome} (conteúdo grande demais)")
                    return saida
                try:
                    saida.append((info.filename, z.read(info)))
                except (RuntimeError, NotImplementedError, zipfile.BadZipFile):
                    recusados.append(f"{info.filename} (protegido por senha ou compactação não suportada)")
    except zipfile.BadZipFile:
        recusados.append(nome)
    return saida


def _processar_importacao(con, empresa_id: int, uploads: list[tuple[str, bytes]],
                          recusados: list[str]) -> tuple[int, int]:
    """Lê, confere o CNPJ e grava cada nota. Roda numa thread com conexão própria."""
    empresa = repo.obter_empresa(con, empresa_id)
    base = caminhos.fiscal(con)
    novas = existentes = 0
    for nome_arquivo, bruto in uploads:
        for nome, xml in _xmls_do_upload(nome_arquivo, bruto, recusados):
            try:
                doc = ler(xml)
            except XmlInvalido:
                recusados.append(nome)
                continue
            if repo.so_digitos(doc.destinatario_cnpj) != empresa["cnpj"]:
                recusados.append(f"{nome} (nota de outro CNPJ: {doc.destinatario_cnpj or 'sem destinatário'})")
                continue
            caminho = acervo.gravar(base, empresa["cnpj"], doc, xml, "importado")
            if repo.gravar_documento(con, empresa_id, doc, caminho, hashlib.sha256(xml).hexdigest(), "importado"):
                novas += 1
            else:
                existentes += 1
    return novas, existentes


@router.get("/importar")
async def importar_form(ctx: Ctx = Depends(_ctx)):
    ctx.exigir(Acao.VER_FISCAL)
    return _pagina_importar(ctx)


@router.post("/importar")
async def importar(ctx: Ctx = Depends(_ctx_post)):
    ctx.exigir(Acao.VER_FISCAL)
    empresa_id = _exigir_empresa(ctx, _int(ctx.form, "empresa_id"))
    recusados: list[str] = []
    uploads: list[tuple[str, bytes]] = []
    for arquivo in ctx.form.getlist("arquivos"):
        if isinstance(arquivo, str):
            continue
        bruto = await arquivo.read(MAX_UPLOAD + 1)
        if len(bruto) > MAX_UPLOAD:
            recusados.append(f"{arquivo.filename} (maior que 50 MB)")
            continue
        uploads.append((arquivo.filename or "arquivo", bruto))
    fabrica = ctx.request.app.state.con_factory  # sqlite3: conexão própria na thread
    novas, existentes = await run_in_threadpool(
        _com_conexao, fabrica, lambda con: _processar_importacao(con, empresa_id, uploads, recusados))
    acesso.registrar(ctx.con, ctx.uid, "importar_notas", f"empresa={empresa_id} novas={novas}")
    resumo = (f"{novas} notas importadas, {existentes} já {'existia' if existentes == 1 else 'existiam'}, "
              f"{len(recusados)} não reconhecidas.")
    return _pagina_importar(ctx, mensagem=resumo, recusados=recusados)
