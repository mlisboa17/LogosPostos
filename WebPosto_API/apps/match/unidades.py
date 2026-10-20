"""Unidades (postos) vindas do banco local, no formato do módulo cash_reconciliation."""
from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from apps.match import banco, credenciais, registro_rede, relatorio_xlsx
from src.modules.cash_reconciliation.config import definir_provedor_unidades
from src.modules.cash_reconciliation.domain.models import Unidade
from src.shared.segredos import definir_resolvedor

logger = logging.getLogger(__name__)

_RE_LC = re.compile(r"^LC_(\d+)_(WEBPOSTO|PREMMIA)_(CHAVE|USUARIO|SENHA)$")
_RE_PAGBANK = re.compile(r"^PAGBANK_(USER|TOKEN)_(-?\d+)$")
_CAMPO_PAGBANK = {"USER": "usuario", "TOKEN": "token"}


def codigo_empresa(posto) -> int:
    codigo = posto["empresa_codigo_webposto"]
    return codigo if codigo is not None else -posto["id"]


class CodigoInvalido(ValueError):
    """Mensagem própria, em português, pronta para a tela."""


CODIGO_INVALIDO = "Código do webPosto inválido."
CODIGO_REPETIDO = "Já existe um posto com esse código do webPosto."


def validar_codigo(con, codigo: int | None, posto_id: int | None = None, *,
                   reservados: set[int] = frozenset()) -> None:
    """Código digitado/importado: positivo e de um só posto (negativos são o sintético -id)."""
    if codigo is None:
        return
    if isinstance(codigo, bool) or not isinstance(codigo, int) or codigo <= 0:
        raise CodigoInvalido(CODIGO_INVALIDO)
    if codigo in reservados or any(
            p["id"] != posto_id and p["empresa_codigo_webposto"] == codigo
            for p in banco.listar_postos(con, so_ativos=False)):
        raise CodigoInvalido(CODIGO_REPETIDO)


def codigo_em_conflito(con, posto) -> bool:
    """Outro posto resolve para o mesmo código (dados antigos): coletar misturaria os dois."""
    meu = codigo_empresa(posto)
    return any(p["id"] != posto["id"] and codigo_empresa(p) == meu
               for p in banco.listar_postos(con, so_ativos=False))


_RE_SEGREDO = re.compile(r"senha|token|chave|secret|password", re.IGNORECASE)


def _config(fonte) -> dict:
    return json.loads(fonte["config_json"] or "{}")


def _sem_segredos(cfg: dict) -> dict:
    return {k: v for k, v in cfg.items() if not _RE_SEGREDO.search(str(k))}


def do_posto(con, p) -> Unidade:
    """Unidade de um posto pelo seu id (credenciais LC_{id}_*), nunca a de outro posto."""
    fontes = {f["tipo"]: f for f in banco.fontes_do_posto(con, p["id"])}
    premmia, pagbank = fontes.get("premmia"), fontes.get("pagbank_edi")
    origem = premmia or pagbank
    adm = _config(origem).get("administradoras", {}) if origem else {}
    pid = p["id"]
    codigo = codigo_empresa(p)
    return Unidade(
        empresa_codigo=codigo, nome=p["nome"], apelido=p["apelido"] or f"P{pid}",
        chave_env=f"LC_{pid}_WEBPOSTO_CHAVE",
        premmia_ativo=bool(premmia and premmia["ativo"]),
        premmia_usuario_env=f"LC_{pid}_PREMMIA_USUARIO",
        premmia_senha_env=f"LC_{pid}_PREMMIA_SENHA",
        destinos=(), administradoras={k: tuple(v) for k, v in adm.items()})


def montar(con) -> dict[int, Unidade]:
    return {codigo_empresa(p): do_posto(con, p) for p in banco.listar_postos(con)}


@contextmanager
def _conexao_propria(caminho: str):
    """Conexão curta por chamada: sqlite3 não atravessa threads (asyncio.to_thread)."""
    c = banco.conectar(Path(caminho))
    try:
        yield c
    finally:
        c.close()


def _caminho_db(con) -> str:
    return con.execute("PRAGMA database_list").fetchone()[2]


def resolvedor(con) -> Callable[[str], str | None]:
    caminho = _caminho_db(con)

    def resolver(nome: str) -> str | None:
        m = _RE_LC.match(nome)
        if m:
            pid, fonte, campo = m.group(1), m.group(2).lower(), m.group(3).lower()
            return credenciais.ler(f"{pid}/{fonte}/{campo}")
        m = _RE_PAGBANK.match(nome)
        if m:
            emp = int(m.group(2))
            with _conexao_propria(caminho) as c:
                postos = banco.listar_postos(c)
            for p in postos:
                if codigo_empresa(p) == emp:
                    return credenciais.ler(f"{p['id']}/pagbank/{_CAMPO_PAGBANK[m.group(1)]}")
        return None
    return resolver


def ativar(con) -> None:
    definir_resolvedor(resolvedor(con))
    caminho = _caminho_db(con)

    def provedor() -> dict[int, Unidade]:
        with _conexao_propria(caminho) as c:
            return montar(c)

    definir_provedor_unidades(provedor)


MSG_APELIDO = "Já existe um posto com esse apelido (ou um apelido equivalente)."


def _validar_apelidos(con, novos: list[str | None]) -> None:
    """Cada novo posto precisa de nome de arquivo único (entre si e entre os existentes)."""
    ocupados: set[str] = set()
    prox = relatorio_xlsx.proximo_id(con)
    for ap in novos:
        if relatorio_xlsx.nome_em_uso(con, ap, None, ocupados, prox):
            raise CodigoInvalido(MSG_APELIDO)
        ocupados.add(relatorio_xlsx.nome_seguro(ap, prox).casefold())
        prox += 1


_TIPOS_FONTE = ("premmia", "pagbank_edi", "webposto")


def _texto_ou_nada(v) -> bool:
    return v is None or isinstance(v, str)


def _validar_formato_posto(p) -> None:
    """Formato de um posto de importar_config (antes de tocar a pasta da rede ou o banco)."""
    if not isinstance(p, dict) or not isinstance(p.get("nome"), str) or not p["nome"].strip():
        raise ValueError("posto inválido")
    if not (_texto_ou_nada(p.get("apelido")) and _texto_ou_nada(p.get("cnpj"))
            and isinstance(p.get("ativo", True), bool) and isinstance(p.get("fontes", []), list)):
        raise ValueError("posto inválido")
    for f in p.get("fontes", []):
        if (not isinstance(f, dict) or f.get("tipo") not in _TIPOS_FONTE
                or not isinstance(f.get("ativo", False), bool)
                or not isinstance(f.get("config", {}), dict)):
            raise ValueError("fonte inválida")


def _validar_formato_unidade(u) -> None:
    """Formato de uma unidade do units.json (antes de tocar a pasta da rede ou o banco)."""
    if not isinstance(u, dict) or not isinstance(u.get("nome"), str) or not u["nome"].strip():
        raise ValueError("unidade inválida")
    adq = u.get("adquirentes", [])
    if (not _texto_ou_nada(u.get("apelido")) or not isinstance(u.get("administradoras", {}), dict)
            or not isinstance(adq, list) or not all(isinstance(a, dict) for a in adq)):
        raise ValueError("unidade inválida")


def _validar_formato_canais(canais) -> None:
    if not isinstance(canais, list) or any(
            not isinstance(c, dict) or not isinstance(c.get("tipo"), str)
            or not isinstance(c.get("config", {}), dict) for c in canais):
        raise ValueError("canal inválido")


def _de_outra_maquina(con, candidatos: list[tuple[int, str | None, str]],
                      pulados: list[str] | None) -> tuple[set[int], set[int]]:
    """(postos de outra máquina, postos sem dono) entre os novos, lendo a pasta da rede.

    Pasta inacessível levanta `PastaIndisponivel` antes de qualquer gravação.
    """
    pasta = banco.pasta_rede(con)
    if pasta is None:
        return set(), set()
    meu = banco.id_instalacao(con)
    fora, livres = set(), set()
    for i, chave, nome in candidatos:
        if chave is None:
            continue
        d = registro_rede.dono(pasta, chave)
        if d is None:
            livres.add(i)
        elif d.id_instalacao != meu:
            fora.add(i)
            if pulados is not None:
                pulados.append(f"{nome}: {registro_rede.mensagem_bloqueio(d)}")
    return fora, livres


def _desfazer_na_rede(con, chaves: list[str]) -> None:
    """Libera chaves registradas por esta importação (nunca as que já eram desta máquina)."""
    pasta = banco.pasta_rede(con)
    if pasta is None:
        return
    meu = banco.id_instalacao(con)
    for chave in chaves:
        try:
            registro_rede.liberar(pasta, chave, meu)
        except Exception as exc:  # noqa: BLE001 - o erro original é o que importa
            logger.warning("Desfazer registro na pasta da rede falhou tipo=%s", type(exc).__name__)


def _registrar_na_rede(con, candidatos: list[tuple[int, str | None, str]],
                       livres: set[int]) -> dict[int, str]:
    """Registra os postos novos na pasta da rede antes de inseri-los.

    Devolve {índice: chave} dos que estavam sem dono (os únicos que um desfazer pode liberar).
    Se falhar no meio, libera esses e relança.
    """
    pasta = banco.pasta_rede(con)
    if pasta is None:
        return {}
    meu = banco.id_instalacao(con)
    novos: dict[int, str] = {}
    try:
        for i, chave, nome in candidatos:
            if chave is not None:
                registro_rede.registrar(pasta, chave, meu, nome)
                if i in livres:
                    novos[i] = chave
    except Exception:
        _desfazer_na_rede(con, list(novos.values()))
        raise
    return novos


@contextmanager
def _desfazer_se_falhar(con, registrados: dict[int, str], inseridos: set[int]):
    """Falha no meio dos inserts: libera na rede as chaves dos postos que não chegaram ao banco."""
    try:
        yield
    except Exception:
        _desfazer_na_rede(con, [c for i, c in registrados.items() if i not in inseridos])
        raise


def _chave(codigo, cnpj) -> str | None:
    return registro_rede.chave_posto({"empresa_codigo_webposto": codigo, "cnpj": cnpj})


def importar_units_json(con, caminho: Path, *, pulados: list[str] | None = None) -> int:
    """Importa os postos do units.json. `pulados` recebe os que pertencem a outra máquina."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    existentes = {p["empresa_codigo_webposto"] for p in banco.listar_postos(con, so_ativos=False)}
    novos: set[int] = set()
    unidades_ = dados.get("unidades", [])
    if not isinstance(unidades_, list):
        raise ValueError("unidades inválidas")
    for u in unidades_:
        _validar_formato_unidade(u)
    for u in unidades_:  # valida tudo antes de gravar qualquer posto
        codigo = u["empresa_codigo"]
        if codigo is None or codigo not in existentes:
            validar_codigo(con, codigo, reservados=novos)
            novos.add(codigo)
    candidatos = [(i, _chave(u["empresa_codigo"], None), u["nome"]) for i, u in enumerate(unidades_)
                  if u["empresa_codigo"] not in existentes]
    fora, livres = _de_outra_maquina(con, candidatos, pulados)
    candidatos = [c for c in candidatos if c[0] not in fora]
    _validar_apelidos(con, [unidades_[i].get("apelido") for i, _c, _n in candidatos])
    registrados = _registrar_na_rede(con, candidatos, livres)
    criados, inseridos = 0, set()
    with _desfazer_se_falhar(con, registrados, inseridos):
        for i, u in enumerate(unidades_):
            codigo = u["empresa_codigo"]
            if codigo in existentes or i in fora:
                continue
            pid = banco.inserir_posto(con, u["nome"], u.get("apelido"), None, codigo)
            inseridos.add(i)
            adm = u.get("administradoras", {})
            tem_pagbank = any(a.get("nome") == "PAGBANK" for a in u.get("adquirentes", []))
            if u.get("premmia_ativo") or u.get("premmia_usuario_env") or u.get("premmia_senha_env"):
                banco.salvar_fonte(con, pid, "premmia", False, {"administradoras": adm})
            if tem_pagbank:
                banco.salvar_fonte(con, pid, "pagbank_edi", False, {"administradoras": adm})
            banco.salvar_fonte(con, pid, "webposto", False, {})
            existentes.add(codigo)
            criados += 1
    return criados


def exportar_config(con) -> dict:
    postos = []
    for p in banco.listar_postos(con, so_ativos=False):
        postos.append({
            "nome": p["nome"], "apelido": p["apelido"], "cnpj": p["cnpj"],
            "empresa_codigo_webposto": p["empresa_codigo_webposto"], "ativo": bool(p["ativo"]),
            "fontes": [{"tipo": f["tipo"], "ativo": bool(f["ativo"]), "config": _sem_segredos(_config(f))}
                       for f in banco.fontes_do_posto(con, p["id"])]})
    canais = [{"tipo": c["tipo"], "ativo": bool(c["ativo"]),
               "config": _sem_segredos(json.loads(c["config_json"] or "{}"))}
              for c in con.execute("SELECT * FROM canal ORDER BY id")]
    return {"postos": postos, "canais": canais}


def importar_config(con, dados: dict, *, pulados: list[str] | None = None) -> int:
    """Importa postos e canais. `pulados` recebe os postos que pertencem a outra máquina."""
    existentes = {(p["nome"], p["empresa_codigo_webposto"])
                  for p in banco.listar_postos(con, so_ativos=False)}
    novos: set[int] = set()
    postos = dados.get("postos", [])
    if not isinstance(postos, list):
        raise ValueError("postos inválidos")
    for p in postos:
        _validar_formato_posto(p)
    _validar_formato_canais(dados.get("canais", []))
    for p in postos:  # valida tudo antes de gravar qualquer posto
        codigo = p.get("empresa_codigo_webposto")
        if (p["nome"], codigo) not in existentes:
            validar_codigo(con, codigo, reservados=novos)
            if codigo is not None:
                novos.add(codigo)
    # posto importado desativado não ocupa a pasta da rede: a reativação confere
    ativos = [(i, _chave(p.get("empresa_codigo_webposto"), p.get("cnpj")), p["nome"])
              for i, p in enumerate(postos)
              if (p["nome"], p.get("empresa_codigo_webposto")) not in existentes and p.get("ativo", True)]
    fora, livres = _de_outra_maquina(con, ativos, pulados)
    _validar_apelidos(con, [p.get("apelido") for i, p in enumerate(postos)
                            if (p["nome"], p.get("empresa_codigo_webposto")) not in existentes
                            and i not in fora])
    registrados = _registrar_na_rede(con, [c for c in ativos if c[0] not in fora], livres)
    criados, inseridos = 0, set()
    with _desfazer_se_falhar(con, registrados, inseridos):
        for i, p in enumerate(postos):
            chave = (p["nome"], p.get("empresa_codigo_webposto"))
            if chave in existentes or i in fora:
                continue
            pid = banco.inserir_posto(con, p["nome"], p.get("apelido"), p.get("cnpj"),
                                      p.get("empresa_codigo_webposto"))
            inseridos.add(i)
            if not p.get("ativo", True):
                con.execute("UPDATE posto SET ativo=0 WHERE id=?", (pid,))
            for f in p.get("fontes", []):
                banco.salvar_fonte(con, pid, f["tipo"], f.get("ativo", False), f.get("config", {}))
            existentes.add(chave)
            criados += 1
    canais_existentes = {(c["tipo"], c["config_json"])
                         for c in con.execute("SELECT tipo, config_json FROM canal")}
    for c in dados.get("canais", []):
        cfg_json = json.dumps(c.get("config", {}), ensure_ascii=False)
        if (c["tipo"], cfg_json) in canais_existentes:
            continue
        canais_existentes.add((c["tipo"], cfg_json))
        con.execute("INSERT INTO canal(tipo, config_json, ativo) VALUES (?,?,?)",
                    (c["tipo"], cfg_json, int(c.get("ativo", True))))
    con.commit()
    return criados
