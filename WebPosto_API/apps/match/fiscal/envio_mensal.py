"""Envio do pacote do mês a cada escritório de contabilidade (spec §8, mensal).

Garantias:
- cada nota vai em um pacote só (`pacote_documento`); o complementar leva o que nunca foi enviado;
- um pacote só sai uma vez: estado `enviando` reivindicado de forma atômica + trava do processo;
- envio em partes é retomado da parte que falhou; `enviando` parado há mais de 2 h é retomado;
- mês cujo dia de envio passou com o PC desligado é enviado depois (se o escritório já existia).
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from apps.match import acesso, banco, caminhos
from apps.match.canais import email_smtp, envio
from apps.match.fiscal import conferencia, pacote, repositorio as repo

logger = logging.getLogger(__name__)
MSG_SEM_EMAIL = "Cadastre um canal de e-mail em Canais para enviar à contabilidade."
MSG_FALHA_EMAIL = "O e-mail não foi enviado. Confira o canal de e-mail; o Logos Match tenta de novo."
MSG_SEM_NOTAS = "Nenhuma nota com XML para enviar nesta competência."
_TEXTO = ("Segue o pacote de notas fiscais recebidas por {nome} (CNPJ {cnpj}) na competência {mmaaaa}: "
          "XMLs, PDFs e planilha resumo.\n\nEnviado automaticamente pelo Logos Match.")
PARADO = timedelta(hours=2)
_MESES_ATRAS = 3
_TRAVA = threading.RLock()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def competencia_anterior(hoje: date) -> str:
    return (hoje.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def _mmaaaa(competencia: str) -> str:
    aaaa, mm = competencia.split("-")
    return f"{mm}/{aaaa}"


def _nome(empresa) -> str:
    return empresa["apelido"] or empresa["razao_social"]


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


def _parado(p, agora: datetime) -> bool:
    return p["situacao"] == "enviando" and datetime.fromisoformat(p["gerado_em"]) < agora - PARADO


def _reivindicar(con, pacote_id: int, de: tuple[str, ...]) -> bool:
    """Passa o pacote para `enviando` só se ele ainda estiver num dos estados `de` (atômico)."""
    marcas = ",".join("?" * len(de))
    cur = con.execute(f"UPDATE pacote SET situacao='enviando', gerado_em=? WHERE id=? AND situacao IN ({marcas})",
                      (_agora().isoformat(), pacote_id, *de))
    con.commit()
    return cur.rowcount == 1


def _arquivos(p) -> list[Path]:
    return [Path(a) for a in json.loads(p["arquivos_json"] or "[]")]


def _enviar_pacote(con, pacote_id: int) -> dict:
    """Manda as partes ainda não enviadas de um pacote em `enviando` e grava o resultado."""
    p = repo.obter_pacote(con, pacote_id)
    empresa = repo.obter_empresa(con, p["empresa_id"])
    escritorio = _escritorio_da_empresa(con, empresa["id"])
    resultado = {"empresa_id": empresa["id"], "pacote_id": pacote_id}
    canal = _canal_email(con)
    if canal is None or escritorio is None:
        repo.atualizar_pacote(con, pacote_id, situacao="erro", motivo_retencao=MSG_SEM_EMAIL)
        return {**resultado, "situacao": "erro", "motivo": MSG_SEM_EMAIL}
    partes = _arquivos(p)
    destinos = json.loads(escritorio["emails_json"] or "[]")
    base = f"Notas fiscais {_nome(empresa)} — {_mmaaaa(p['competencia'])}"
    if p["complementar"]:
        base += " (complementar)"
    texto = _TEXTO.format(nome=empresa["razao_social"], cnpj=empresa["cnpj"], mmaaaa=_mmaaaa(p["competencia"]))
    for i in range(p["partes_enviadas"], len(partes)):
        assunto = base if len(partes) == 1 else f"{base} (parte {i + 1}/{len(partes)})"
        try:
            email_smtp.enviar_arquivos(canal, destinos, assunto, texto, [partes[i]])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Envio fiscal falhou pacote=%s parte=%s tipo=%s", pacote_id, i + 1, type(exc).__name__)
            repo.atualizar_pacote(con, pacote_id, situacao="erro", motivo_retencao=MSG_FALHA_EMAIL)
            return {**resultado, "situacao": "erro", "motivo": MSG_FALHA_EMAIL}
        repo.atualizar_pacote(con, pacote_id, partes_enviadas=i + 1)
    repo.atualizar_pacote(con, pacote_id, situacao="enviado", enviado_em=_agora().isoformat(), motivo_retencao=None)
    return {**resultado, "situacao": "enviado"}


def _montar_e_enviar(con, escritorio, empresa, competencia: str, pacote_id: int, *, complementar: bool,
                     usuario_id: int | None = None) -> dict:
    """Pacote já em `enviando` (ou novo): gera os arquivos com as notas que nenhum outro pacote levou."""
    excluir = repo.documentos_ja_enviados(con, empresa["id"], competencia, exceto=pacote_id)
    m = pacote.montar(con, empresa["id"], competencia, escritorio["pdf"], _pasta(empresa, competencia),
                      complementar=complementar, excluir=excluir)
    if not m.partes:
        repo.atualizar_pacote(con, pacote_id, situacao="retido", motivo_retencao=MSG_SEM_NOTAS)
        return {"empresa_id": empresa["id"], "situacao": "sem_documentos"}
    extra = {"aprovado_por": usuario_id} if usuario_id is not None else {}
    repo.atualizar_pacote(con, pacote_id, arquivos_json=json.dumps([str(a) for a in m.partes]), partes_enviadas=0,
                          motivo_retencao=None, **extra)
    repo.vincular_documentos(con, pacote_id, m.documentos)
    if escritorio["modo"] == "so_gerar" and not complementar:
        repo.atualizar_pacote(con, pacote_id, situacao="gerado")
        _avisar_admin(con, "Pacote fiscal pronto", f"O pacote de {_mmaaaa(competencia)} de {_nome(empresa)} "
                      "está pronto para baixar em Pacotes.")
        return {"empresa_id": empresa["id"], "situacao": "gerado"}
    return _enviar_pacote(con, pacote_id)


def _pacote_principal(con, empresa_id: int, competencia: str):
    return con.execute("SELECT * FROM pacote WHERE empresa_id=? AND competencia=? AND complementar=0"
                       " ORDER BY id DESC LIMIT 1", (empresa_id, competencia)).fetchone()


def _competencias_devidas(escritorio, hoje: date) -> list[str]:
    """Competências cujo dia de envio já chegou e que caem depois do cadastro do escritório."""
    criado = datetime.fromisoformat(escritorio["criado_em"]).date() if escritorio["criado_em"] else None
    saida, mes = [], hoje.replace(day=1)
    for _ in range(_MESES_ATRAS):
        devido = mes.replace(day=escritorio["dia_envio"])
        competencia = (mes - timedelta(days=1)).strftime("%Y-%m")
        if devido <= hoje and (criado is None or devido >= criado):
            saida.append(competencia)
        mes = (mes - timedelta(days=1)).replace(day=1)
    return sorted(saida)


def _tem_notas(con, empresa_id: int, competencia: str) -> bool:
    return con.execute("SELECT 1 FROM documento WHERE empresa_id=? AND competencia=? LIMIT 1",
                       (empresa_id, competencia)).fetchone() is not None


def _cuidar(con, escritorio, empresa, competencia: str, agora: datetime, hoje: date) -> dict | None:
    p = _pacote_principal(con, empresa["id"], competencia)
    if p is None and competencia != competencia_anterior(hoje) and not _tem_notas(con, empresa["id"], competencia):
        return None  # mês antigo sem nenhuma nota: nada a conferir nem avisar
    if p is not None and (p["situacao"] in ("enviado", "aprovado", "gerado")
                          or (p["situacao"] == "enviando" and not _parado(p, agora))):
        return None
    retomar = p is not None and p["situacao"] in ("erro", "enviando") and _arquivos(p) \
        and all(a.exists() for a in _arquivos(p))
    if retomar:
        return _enviar_pacote(con, p["id"]) if _reivindicar(con, p["id"], ("erro", "enviando")) else None
    achados = conferencia.conferir(con, empresa["id"], competencia, agora)
    motivo = conferencia.texto_retencao(achados)
    if motivo:
        if p is None:
            repo.salvar_pacote(con, empresa["id"], competencia, "retido", [], motivo)
            _avisar_admin(con, f"Pacote fiscal retido — {_nome(empresa)}",
                          f"O pacote de {_mmaaaa(competencia)} não foi enviado: {motivo} "
                          "Abra o Logos Match em Pacotes para enviar mesmo assim.")
        elif p["situacao"] != "retido" or p["motivo_retencao"] != motivo:
            repo.atualizar_pacote(con, p["id"], situacao="retido", motivo_retencao=motivo)
        return {"empresa_id": empresa["id"], "situacao": "retido", "motivo": motivo}
    if p is None:
        if not pacote._documentos(con, empresa["id"], competencia,
                                  repo.documentos_ja_enviados(con, empresa["id"], competencia)):
            return None  # nada a enviar nesta competência
        pid = repo.salvar_pacote(con, empresa["id"], competencia, "enviando", [])
    elif _reivindicar(con, p["id"], ("retido", "erro", "enviando")):
        pid = p["id"]
    else:
        return None
    return _montar_e_enviar(con, escritorio, empresa, competencia, pid, complementar=False)


def rodar(con, hoje: date, *, agora: datetime | None = None) -> list[dict]:
    """Envia (ou gera) os pacotes devidos de cada escritório. Idempotente; nunca envia duas vezes."""
    agora = agora or _agora()
    resultados = []
    with _TRAVA:
        for escritorio in repo.listar_escritorios(con, so_ativos=True):
            for empresa in repo.empresas_do_escritorio(con, escritorio["id"]):
                if not empresa["ativo"]:
                    continue
                for competencia in _competencias_devidas(escritorio, hoje):
                    try:
                        r = _cuidar(con, escritorio, empresa, competencia, agora, hoje)
                    except Exception as exc:  # noqa: BLE001 - uma empresa não impede as outras
                        logger.warning("Pacote fiscal falhou empresa=%s tipo=%s", empresa["id"], type(exc).__name__)
                        continue
                    if r is not None:
                        resultados.append(r)
    return resultados


def _exigir_escritorio(con, empresa_id: int):
    escritorio = _escritorio_da_empresa(con, empresa_id)
    if escritorio is None:
        raise ValueError("Esta empresa não tem escritório de contabilidade cadastrado.")
    return escritorio


def aprovar_e_enviar(con, pacote_id: int, usuario_id: int | None) -> dict:
    """"Enviar mesmo assim": só para pacote retido ou com erro."""
    with _TRAVA:
        p = repo.obter_pacote(con, pacote_id)
        empresa = repo.obter_empresa(con, p["empresa_id"])
        escritorio = _exigir_escritorio(con, empresa["id"])
        if not _reivindicar(con, pacote_id, ("retido", "erro")):
            raise ValueError("Este pacote já foi enviado ou está sendo enviado agora.")
        if usuario_id is not None:
            acesso.registrar(con, usuario_id, "aprovar_pacote", f"pacote={pacote_id} competencia={p['competencia']}")
        if _arquivos(p) and all(a.exists() for a in _arquivos(p)):
            if usuario_id is not None:
                repo.atualizar_pacote(con, pacote_id, aprovado_por=usuario_id)
            return _enviar_pacote(con, pacote_id)
        return _montar_e_enviar(con, escritorio, empresa, p["competencia"], pacote_id,
                                complementar=bool(p["complementar"]), usuario_id=usuario_id)


def reenviar(con, pacote_id: int, usuario_id: int | None) -> dict:
    """Manda de novo um pacote já enviado (ou gerado para baixar), com as mesmas notas."""
    with _TRAVA:
        p = repo.obter_pacote(con, pacote_id)
        empresa = repo.obter_empresa(con, p["empresa_id"])
        escritorio = _exigir_escritorio(con, empresa["id"])
        if not _reivindicar(con, pacote_id, ("enviado", "gerado")):
            raise ValueError("Só dá para reenviar um pacote que já foi enviado ou gerado.")
        if usuario_id is not None:
            acesso.registrar(con, usuario_id, "reenviar_pacote", f"pacote={pacote_id} competencia={p['competencia']}")
        repo.atualizar_pacote(con, pacote_id, partes_enviadas=0)
        if _arquivos(p) and all(a.exists() for a in _arquivos(p)):
            return _enviar_pacote(con, pacote_id)
        return _montar_e_enviar(con, escritorio, empresa, p["competencia"], pacote_id,
                                complementar=bool(p["complementar"]))


def enviar_complementares(con, agora: datetime) -> list[dict]:
    """Notas de competência já enviada que chegaram depois vão num pacote complementar.

    Complementar com erro é retomado (não cria outro); só nasce um novo quando há nota nunca enviada.
    """
    resultados = []
    with _TRAVA:
        pendentes = con.execute("SELECT * FROM pacote WHERE complementar=1 AND situacao IN ('erro','enviando')"
                                ).fetchall()
        for p in pendentes:
            if p["situacao"] == "enviando" and not _parado(p, agora):
                continue
            if _arquivos(p) and all(a.exists() for a in _arquivos(p)) and _reivindicar(con, p["id"], ("erro", "enviando")):
                resultados.append(_enviar_pacote(con, p["id"]))
        enviados = con.execute("SELECT DISTINCT empresa_id, competencia FROM pacote WHERE complementar=0"
                               " AND situacao='enviado'").fetchall()
        for linha in enviados:
            empresa = repo.obter_empresa(con, linha["empresa_id"])
            escritorio = _escritorio_da_empresa(con, empresa["id"])
            if escritorio is None or escritorio["modo"] != "enviar" or _canal_email(con) is None:
                continue
            ja = repo.documentos_ja_enviados(con, empresa["id"], linha["competencia"])
            if not pacote._documentos(con, empresa["id"], linha["competencia"], ja):
                continue
            try:
                pid = repo.salvar_pacote(con, empresa["id"], linha["competencia"], "enviando", [], complementar=True)
                resultados.append(_montar_e_enviar(con, escritorio, empresa, linha["competencia"], pid,
                                                   complementar=True))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Complementar falhou empresa=%s tipo=%s", empresa["id"], type(exc).__name__)
    return resultados
