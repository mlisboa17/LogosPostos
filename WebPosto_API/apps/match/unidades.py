"""Unidades (postos) vindas do banco local, no formato do módulo cash_reconciliation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from apps.match import banco, credenciais
from src.modules.cash_reconciliation.config import definir_provedor_unidades
from src.modules.cash_reconciliation.domain.models import Unidade
from src.shared.segredos import definir_resolvedor

_RE_LC = re.compile(r"^LC_(\d+)_(WEBPOSTO|PREMMIA)_(CHAVE|USUARIO|SENHA)$")
_RE_PAGBANK = re.compile(r"^PAGBANK_(USER|TOKEN)_(-?\d+)$")
_CAMPO_PAGBANK = {"USER": "usuario", "TOKEN": "token"}


def codigo_empresa(posto) -> int:
    codigo = posto["empresa_codigo_webposto"]
    return codigo if codigo is not None else -posto["id"]


def _config(fonte) -> dict:
    return json.loads(fonte["config_json"] or "{}")


def montar(con) -> dict[int, Unidade]:
    resultado: dict[int, Unidade] = {}
    for p in banco.listar_postos(con):
        fontes = {f["tipo"]: f for f in banco.fontes_do_posto(con, p["id"])}
        premmia, pagbank = fontes.get("premmia"), fontes.get("pagbank_edi")
        origem = premmia or pagbank
        adm = _config(origem).get("administradoras", {}) if origem else {}
        pid = p["id"]
        codigo = codigo_empresa(p)
        resultado[codigo] = Unidade(
            empresa_codigo=codigo, nome=p["nome"], apelido=p["apelido"] or f"P{pid}",
            chave_env=f"LC_{pid}_WEBPOSTO_CHAVE",
            premmia_ativo=bool(premmia and premmia["ativo"]),
            premmia_usuario_env=f"LC_{pid}_PREMMIA_USUARIO",
            premmia_senha_env=f"LC_{pid}_PREMMIA_SENHA",
            destinos=(), administradoras={k: tuple(v) for k, v in adm.items()})
    return resultado


def resolvedor(con) -> Callable[[str], str | None]:
    def resolver(nome: str) -> str | None:
        m = _RE_LC.match(nome)
        if m:
            pid, fonte, campo = m.group(1), m.group(2).lower(), m.group(3).lower()
            return credenciais.ler(f"{pid}/{fonte}/{campo}")
        m = _RE_PAGBANK.match(nome)
        if m:
            emp = int(m.group(2))
            for p in banco.listar_postos(con):
                if codigo_empresa(p) == emp:
                    return credenciais.ler(f"{p['id']}/pagbank/{_CAMPO_PAGBANK[m.group(1)]}")
        return None
    return resolver


def ativar(con) -> None:
    definir_resolvedor(resolvedor(con))
    definir_provedor_unidades(lambda: montar(con))


def importar_units_json(con, caminho: Path) -> int:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    existentes = {p["empresa_codigo_webposto"] for p in banco.listar_postos(con, so_ativos=False)}
    criados = 0
    for u in dados.get("unidades", []):
        codigo = u["empresa_codigo"]
        if codigo in existentes:
            continue
        pid = banco.inserir_posto(con, u["nome"], u.get("apelido"), None, codigo)
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
            "fontes": [{"tipo": f["tipo"], "ativo": bool(f["ativo"]), "config": _config(f)}
                       for f in banco.fontes_do_posto(con, p["id"])]})
    canais = [{"tipo": c["tipo"], "ativo": bool(c["ativo"]),
               "config": json.loads(c["config_json"] or "{}")}
              for c in con.execute("SELECT * FROM canal ORDER BY id")]
    return {"postos": postos, "canais": canais}


def importar_config(con, dados: dict) -> int:
    existentes = {(p["nome"], p["empresa_codigo_webposto"])
                  for p in banco.listar_postos(con, so_ativos=False)}
    criados = 0
    for p in dados.get("postos", []):
        chave = (p["nome"], p.get("empresa_codigo_webposto"))
        if chave in existentes:
            continue
        pid = banco.inserir_posto(con, p["nome"], p.get("apelido"), p.get("cnpj"),
                                  p.get("empresa_codigo_webposto"))
        if not p.get("ativo", True):
            con.execute("UPDATE posto SET ativo=0 WHERE id=?", (pid,))
        for f in p.get("fontes", []):
            banco.salvar_fonte(con, pid, f["tipo"], f.get("ativo", False), f.get("config", {}))
        existentes.add(chave)
        criados += 1
    for c in dados.get("canais", []):
        con.execute("INSERT INTO canal(tipo, config_json, ativo) VALUES (?,?,?)",
                    (c["tipo"], json.dumps(c.get("config", {}), ensure_ascii=False),
                     int(c.get("ativo", True))))
    con.commit()
    return criados
