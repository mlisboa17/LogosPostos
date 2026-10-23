"""Envio do pacote do mês a cada escritório de contabilidade (spec §8, mensal)."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from apps.match import acesso, banco, caminhos
from apps.match.canais import email_smtp, envio
from apps.match.fiscal import conferencia, pacote, repositorio as repo

logger = logging.getLogger(__name__)
MSG_SEM_EMAIL = "Cadastre um canal de e-mail em Canais para enviar à contabilidade."
_TEXTO = ("Segue o pacote de notas fiscais recebidas por {nome} (CNPJ {cnpj}) na competência {mmaaaa}: "
          "XMLs, PDFs e planilha resumo.\n\nEnviado automaticamente pelo Logos Match.")


def competencia_anterior(hoje: date) -> str:
    return (hoje.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def _mmaaaa(competencia: str) -> str:
    aaaa, mm = competencia.split("-")
    return f"{mm}/{aaaa}"


def _canal_email(con):
    return next((c for c in banco.listar_canais(con) if c["tipo"] == "email" and c["ativo"]), None)


def _avisar_admin(con, assunto: str, texto: str) -> None:
    for canal in banco.listar_canais(con):
        if not canal["ativo"]:
            continue
        try:
            envio._despachar(canal, assunto, texto, None)
        except Exception as exc:  # noqa: BLE001 - aviso nunca derruba o envio
            logger.warning("Aviso fiscal não enviado canal=%s tipo=%s", canal["id"], type(exc).__name__)


def _escritorio_da_empresa(con, empresa_id: int):
    return con.execute("SELECT o.* FROM escritorio o JOIN escritorio_empresa x ON x.escritorio_id=o.id"
                       " WHERE x.empresa_id=? AND o.ativo=1 ORDER BY o.id LIMIT 1", (empresa_id,)).fetchone()


def _pasta(empresa, competencia: str) -> Path:
    return caminhos.pacotes() / empresa["cnpj"] / competencia


def _enviar_partes(con, escritorio, empresa, competencia: str, partes: list[Path], complementar: bool) -> None:
    canal = _canal_email(con)
    if canal is None:
        raise LookupError(MSG_SEM_EMAIL)
    destinos = json.loads(escritorio["emails_json"] or "[]")
    base = f"Notas fiscais {empresa['apelido'] or empresa['razao_social']} — {_mmaaaa(competencia)}"
    if complementar:
        base += " (complementar)"
    texto = _TEXTO.format(nome=empresa["razao_social"], cnpj=empresa["cnpj"], mmaaaa=_mmaaaa(competencia))
    for i, parte in enumerate(partes, 1):
        assunto = base if len(partes) == 1 else f"{base} (parte {i}/{len(partes)})"
        email_smtp.enviar_arquivos(canal, destinos, assunto, texto, [parte])


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _processar(con, escritorio, empresa, competencia: str, agora: datetime, existente=None,
               forcar: bool = False, usuario_id: int | None = None) -> dict:
    achados = [] if forcar else conferencia.conferir(con, empresa["id"], competencia, agora)
    motivo = conferencia.texto_retencao(achados)
    if motivo:
        if existente is None:
            repo.salvar_pacote(con, empresa["id"], competencia, "retido", [], motivo)
            _avisar_admin(con, f"Pacote fiscal retido — {empresa['apelido'] or empresa['razao_social']}",
                          f"O pacote de {_mmaaaa(competencia)} não foi enviado: {motivo} "
                          "Abra o Logos Match em Pacotes para enviar mesmo assim.")
        else:
            repo.atualizar_pacote(con, existente["id"], motivo_retencao=motivo)
        return {"empresa_id": empresa["id"], "situacao": "retido", "motivo": motivo}
    partes = pacote.montar(con, empresa["id"], competencia, escritorio["pdf"], _pasta(empresa, competencia))
    if not partes:
        return {"empresa_id": empresa["id"], "situacao": "sem_documentos"}
    arquivos = [str(p) for p in partes]
    pid = existente["id"] if existente is not None else repo.salvar_pacote(
        con, empresa["id"], competencia, "gerado", arquivos)
    extra = {"aprovado_por": usuario_id} if usuario_id is not None else {}
    if escritorio["modo"] == "so_gerar":
        repo.atualizar_pacote(con, pid, situacao="gerado", arquivos_json=json.dumps(arquivos), motivo_retencao=None,
                              **extra)
        _avisar_admin(con, "Pacote fiscal pronto", f"O pacote de {_mmaaaa(competencia)} de "
                      f"{empresa['apelido'] or empresa['razao_social']} está pronto para baixar em Pacotes.")
        return {"empresa_id": empresa["id"], "situacao": "gerado"}
    try:
        _enviar_partes(con, escritorio, empresa, competencia, partes, complementar=False)
    except LookupError:
        repo.atualizar_pacote(con, pid, situacao="erro", motivo_retencao=MSG_SEM_EMAIL,
                              arquivos_json=json.dumps(arquivos))
        return {"empresa_id": empresa["id"], "situacao": "erro", "motivo": MSG_SEM_EMAIL}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Envio fiscal falhou empresa=%s tipo=%s", empresa["id"], type(exc).__name__)
        motivo = "O e-mail não foi enviado. Confira o canal de e-mail e use Reenviar."
        repo.atualizar_pacote(con, pid, situacao="erro", motivo_retencao=motivo, arquivos_json=json.dumps(arquivos))
        return {"empresa_id": empresa["id"], "situacao": "erro", "motivo": motivo}
    repo.atualizar_pacote(con, pid, situacao="enviado", enviado_em=_agora(), motivo_retencao=None,
                          arquivos_json=json.dumps(arquivos), **extra)
    return {"empresa_id": empresa["id"], "situacao": "enviado"}


def _pacote_principal(con, empresa_id: int, competencia: str):
    return con.execute("SELECT * FROM pacote WHERE empresa_id=? AND competencia=? AND complementar=0"
                       " ORDER BY id DESC LIMIT 1", (empresa_id, competencia)).fetchone()


def rodar(con, hoje: date, *, agora: datetime | None = None) -> list[dict]:
    """Envia (ou gera) o pacote do mês anterior para cada escritório cujo dia de envio já chegou.

    Idempotente: pacote enviado/gerado não sai de novo; retido é reavaliado a cada execução;
    com erro de envio, tenta de novo.
    """
    agora = agora or datetime.now(timezone.utc)
    competencia = competencia_anterior(hoje)
    resultados = []
    for escritorio in repo.listar_escritorios(con, so_ativos=True):
        if hoje.day < escritorio["dia_envio"]:
            continue
        for empresa in repo.empresas_do_escritorio(con, escritorio["id"]):
            if not empresa["ativo"]:
                continue
            existente = _pacote_principal(con, empresa["id"], competencia)
            if existente is not None and existente["situacao"] in ("enviado", "gerado", "aprovado"):
                continue
            try:
                resultados.append(_processar(con, escritorio, empresa, competencia, agora, existente))
            except Exception as exc:  # noqa: BLE001 - uma empresa não impede as outras
                logger.warning("Pacote fiscal falhou empresa=%s tipo=%s", empresa["id"], type(exc).__name__)
    return resultados


def aprovar_e_enviar(con, pacote_id: int, usuario_id: int) -> dict:
    p = repo.obter_pacote(con, pacote_id)
    empresa = repo.obter_empresa(con, p["empresa_id"])
    escritorio = _escritorio_da_empresa(con, empresa["id"])
    if escritorio is None:
        raise ValueError("Esta empresa não tem escritório de contabilidade cadastrado.")
    acesso.registrar(con, usuario_id, "aprovar_pacote", f"pacote={pacote_id} competencia={p['competencia']}")
    return _processar(con, escritorio, empresa, p["competencia"], datetime.now(timezone.utc), p,
                      forcar=True, usuario_id=usuario_id)


def reenviar(con, pacote_id: int, usuario_id: int) -> dict:
    p = repo.obter_pacote(con, pacote_id)
    empresa = repo.obter_empresa(con, p["empresa_id"])
    escritorio = _escritorio_da_empresa(con, empresa["id"])
    if escritorio is None:
        raise ValueError("Esta empresa não tem escritório de contabilidade cadastrado.")
    acesso.registrar(con, usuario_id, "reenviar_pacote", f"pacote={pacote_id} competencia={p['competencia']}")
    partes = [Path(a) for a in json.loads(p["arquivos_json"] or "[]")]
    if not partes or not all(a.exists() for a in partes):
        return _processar(con, escritorio, empresa, p["competencia"], datetime.now(timezone.utc), p, forcar=True,
                          usuario_id=usuario_id)
    _enviar_partes(con, escritorio, empresa, p["competencia"], partes, complementar=bool(p["complementar"]))
    repo.atualizar_pacote(con, pacote_id, situacao="enviado", enviado_em=_agora())
    return {"empresa_id": empresa["id"], "situacao": "enviado"}


def enviar_complementares(con, agora: datetime) -> list[dict]:
    """Notas de competência já enviada que chegaram depois: vão num pacote complementar."""
    resultados = []
    enviados = con.execute("SELECT empresa_id, competencia, MAX(enviado_em) AS ultimo FROM pacote"
                           " WHERE situacao='enviado' GROUP BY empresa_id, competencia").fetchall()
    for linha in enviados:
        empresa = repo.obter_empresa(con, linha["empresa_id"])
        escritorio = _escritorio_da_empresa(con, empresa["id"])
        if escritorio is None or escritorio["modo"] != "enviar" or _canal_email(con) is None:
            continue
        desde = datetime.fromisoformat(linha["ultimo"])
        try:
            partes = pacote.montar(con, empresa["id"], linha["competencia"], escritorio["pdf"],
                                   _pasta(empresa, linha["competencia"]), complementar=True, desde=desde)
            if not partes:
                continue
            pid = repo.salvar_pacote(con, empresa["id"], linha["competencia"], "gerado", [str(p) for p in partes],
                                     complementar=True)
            _enviar_partes(con, escritorio, empresa, linha["competencia"], partes, complementar=True)
            repo.atualizar_pacote(con, pid, situacao="enviado", enviado_em=_agora())
            resultados.append({"empresa_id": empresa["id"], "situacao": "enviado", "complementar": True})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Complementar falhou empresa=%s tipo=%s", empresa["id"], type(exc).__name__)
    return resultados
