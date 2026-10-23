"""Captura diária de NF-e recebidas pelo webPosto (somente GET) para o acervo e o banco."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import httpx

from apps.match import banco, caminhos, coletas, explicar, unidades
from apps.match.banco import _agora
from apps.match.fiscal import repositorio as repo
from src.modules.fiscal_docs import acervo, webposto_notas as wn
from src.modules.fiscal_docs.parser import ler

logger = logging.getLogger(__name__)
FONTE = "webposto"
MSG_SEM_CHAVE = "Cadastre a chave do webPosto do posto para capturar as notas."
MSG_OUTRA_MAQUINA = "O posto desta empresa é coletado em outra máquina."
_RECUO = timedelta(days=5)
_TRAVA_FISCAL = threading.Lock()


@dataclass
class ResultadoCaptura:
    empresa_id: int
    situacao: Literal["ok", "erro", "sem_chave"]
    novas: int
    pendentes: int
    mensagem: str


def janela(con, empresa_id: int, hoje: date) -> tuple[date, date]:
    ultima = repo.ultima_data_lida(con, empresa_id)
    if ultima is not None:
        return ultima - _RECUO, hoje
    primeiro_deste_mes = hoje.replace(day=1)
    return (primeiro_deste_mes - timedelta(days=1)).replace(day=1), hoje


_MAX_RESUMOS_ANTIGOS = 200


async def _baixar_e_gravar(con, unidade, empresa, base, chave: str, entrada, client) -> bool:
    """True se o XML veio e completou/criou o documento; False se o webPosto ainda não tem o XML."""
    xml = await wn.baixar_xml(unidade, chave, client=client)
    if xml is None:
        return False
    doc = ler(xml)
    caminho = acervo.gravar(base, empresa["cnpj"], doc, xml, FONTE)
    return repo.gravar_documento(con, empresa["id"], doc, caminho, hashlib.sha256(xml).hexdigest(), FONTE, entrada)


def _ainda_resumo(con, chave: str) -> bool:
    r = con.execute("SELECT situacao FROM documento WHERE chave=?", (chave,)).fetchone()
    return r is not None and r[0] == "so_resumo"


def _resumos_antigos(con, empresa_id: int, listadas: set[str]) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT chave FROM documento WHERE empresa_id=? AND situacao='so_resumo' ORDER BY emissao_em DESC LIMIT ?",
        (empresa_id, _MAX_RESUMOS_ANTIGOS)) if r[0] not in listadas]


def _texto(novas: int, pendentes: int) -> str:
    base = f"{novas} nota(s) nova(s)."
    return base + (f" {pendentes} ainda sem XML no webPosto; nova tentativa mais tarde." if pendentes else "")


async def capturar_empresa(con, empresa_id: int, hoje: date, *,
                           client: httpx.AsyncClient | None = None) -> ResultadoCaptura:
    iniciada = _agora()
    empresa = repo.obter_empresa(con, empresa_id)
    posto = banco.obter_posto(con, empresa["posto_id"]) if empresa["posto_id"] else None
    if posto is None or not coletas.tem_chave_webposto(con, posto):
        repo.registrar_captura(con, empresa_id, FONTE, iniciada, "sem_chave", 0, 0, MSG_SEM_CHAVE)
        return ResultadoCaptura(empresa_id, "sem_chave", 0, 0, MSG_SEM_CHAVE)
    unidade = unidades.do_posto(con, posto)
    inicio, fim = janela(con, empresa_id, hoje)
    base = caminhos.fiscal(con)
    novas = pendentes = 0
    try:
        notas = await wn.listar_notas(unidade, inicio, fim, client=client)
        entradas = await wn.listar_entradas(unidade, inicio, fim, client=client)
        completas = {r[0] for r in con.execute(
            "SELECT chave FROM documento WHERE empresa_id=? AND situacao != 'so_resumo'", (empresa_id,))}
        for nota in notas:
            entrada = entradas.get(nota.chave)
            if nota.chave in completas:
                if entrada is not None:  # frete/CT-e chega quando a nota é lançada no webPosto
                    repo.atualizar_frete(con, nota.chave, entrada)
                continue
            try:
                if await _baixar_e_gravar(con, unidade, empresa, base, nota.chave, entrada, client):
                    novas += 1
                    continue
            except wn.WebPostoErro as exc:
                if exc.status_http in (401, 403):
                    raise  # chave recusada: a empresa toda está sem acesso
                logger.warning("Nota não capturada empresa=%s tipo=%s", empresa_id, type(exc).__name__)
            except Exception as exc:  # noqa: BLE001 - uma nota ruim nunca congela a empresa
                logger.warning("Nota não capturada empresa=%s tipo=%s", empresa_id, type(exc).__name__)
            if repo.registrar_so_resumo(con, empresa_id, nota) or _ainda_resumo(con, nota.chave):
                pendentes += 1
        listadas = {n.chave for n in notas}
        for chave in _resumos_antigos(con, empresa_id, listadas):
            try:  # fora da janela do webPosto: tenta direto pela chave
                if await _baixar_e_gravar(con, unidade, empresa, base, chave, None, client):
                    novas += 1
            except wn.WebPostoErro as exc:
                if exc.status_http in (401, 403):
                    raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Nota antiga não capturada empresa=%s tipo=%s", empresa_id, type(exc).__name__)
    except Exception as exc:  # noqa: BLE001 - a captura de uma empresa nunca derruba as outras
        logger.warning("Captura fiscal falhou empresa=%s tipo=%s", empresa_id, type(exc).__name__)
        msg = explicar.erro_pt(exc)
        repo.registrar_captura(con, empresa_id, FONTE, iniciada, "erro", novas, pendentes, msg)
        return ResultadoCaptura(empresa_id, "erro", novas, pendentes, msg)
    repo.salvar_ultima_data_lida(con, empresa_id, fim)
    msg = _texto(novas, pendentes)
    repo.registrar_captura(con, empresa_id, FONTE, iniciada, "ok", novas, pendentes, None)
    return ResultadoCaptura(empresa_id, "ok", novas, pendentes, msg)


def _empresas_capturaveis(con, so_pendentes: bool) -> list[int]:
    """Empresas ativas cujo posto é desta máquina (posto ativo e não registrado por outra)."""
    ids = []
    for e in repo.listar_empresas(con):
        if not e["ativo"] or e["posto_id"] is None:
            continue
        posto = banco.obter_posto(con, e["posto_id"])
        if posto is None or not posto["ativo"] or coletas._dono_na_rede(con, posto)[0] is not None:
            continue
        if so_pendentes and not con.execute(
                "SELECT 1 FROM documento WHERE empresa_id=? AND situacao='so_resumo' LIMIT 1", (e["id"],)).fetchone():
            continue
        ids.append(e["id"])
    return ids


def capturar_todas(con_factory, hoje: date, *, so_pendentes: bool = False) -> list[ResultadoCaptura]:
    if not _TRAVA_FISCAL.acquire(blocking=False):
        logger.info("Captura fiscal já em andamento; ignorando nova chamada")
        return []
    con = con_factory()
    try:
        unidades.ativar(con)
        return [asyncio.run(capturar_empresa(con, eid, hoje))
                for eid in _empresas_capturaveis(con, so_pendentes)]
    finally:
        con.close()
        _TRAVA_FISCAL.release()
