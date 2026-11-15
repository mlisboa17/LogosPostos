"""Copia as credenciais do Premmia e as chaves do webPosto de um .env do LOGOS para o Logos Match.

Liga cada posto ao .env pelo units.json do robô (empresa_codigo -> nomes das variáveis). Nunca devolve
nem registra os valores, só o que foi feito em cada posto. Trocar o usuário do Premmia apaga as vendas
do login antigo (ver premmia_tela.recomecar).
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from apps.match import banco, coletas, credenciais, premmia_tela
from src.modules.cash_reconciliation import config as config_cr

UNITS = Path(config_cr.__file__).resolve().parent / "units.json"  # o mesmo do robô (vai junto no instalador)


def _norm(t: str | None) -> str:
    t = unicodedata.normalize("NFKD", (t or "").casefold())
    return "".join(c for c in t if c.isalnum())


def _unidades(caminho: Path = UNITS) -> list[dict]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return dados.get("unidades", []) if isinstance(dados, dict) else dados


def _unidade_do_posto(posto, lista: list[dict]) -> dict | None:
    codigo = posto["empresa_codigo_webposto"]
    por_codigo = next((u for u in lista if codigo is not None and u.get("empresa_codigo") == codigo), None)
    if por_codigo:
        return por_codigo
    nomes = {_norm(posto["apelido"]), _norm(posto["nome"])} - {""}
    return next((u for u in lista if _norm(u.get("apelido")) in nomes), None)


def importar(con, env: dict, lista: list[dict] | None = None) -> list[str]:
    """Uma linha por posto ativo dizendo o que foi feito. `env`: valores do .env (nunca exibidos)."""
    lista = _unidades() if lista is None else lista

    def valor(nome: str | None) -> str:
        return (env.get(nome) or "").strip() if nome else ""

    linhas = []
    for posto in banco.listar_postos(con):
        nome = posto["apelido"] or posto["nome"]
        u = _unidade_do_posto(posto, lista)
        if u is None:
            linhas.append(f"{nome}: não achei este posto no units.json (confira o código do webPosto).")
            continue
        pid = posto["id"]
        usuario, senha = valor(u.get("premmia_usuario_env")), valor(u.get("premmia_senha_env"))
        chave = valor(u.get("chave_env"))
        feito = []
        if posto["empresa_codigo_webposto"] is None and u.get("empresa_codigo"):
            banco.atualizar_posto(con, pid, posto["nome"], posto["apelido"], posto["cnpj"], u["empresa_codigo"])
            con.commit()
            feito.append(f"código do webPosto {u['empresa_codigo']}")
        if usuario and senha:
            anterior = (credenciais.ler(f"{pid}/premmia/usuario") or "").strip()
            premmia_tela.ligar(con, pid, usuario, senha, chave)
            feito.append("Premmia ligado")
            if anterior and anterior != usuario:
                feito.append("usuário do Premmia trocado: vendas do login antigo apagadas, o mês será coletado de novo")
            if chave:
                feito.append("chave do webPosto")
        elif chave:
            atual = {f["tipo"]: f for f in banco.fontes_do_posto(con, pid)}.get("webposto")
            banco.salvar_fonte(con, pid, "webposto", True, json.loads(atual["config_json"] or "{}") if atual else {})
            credenciais.salvar(f"{pid}/webposto/chave", chave)
            feito.append("chave do webPosto (sem Premmia no .env)")
        linhas.append(f"{nome}: " + (", ".join(feito) if feito else "nada no .env para este posto."))
    for posto in banco.listar_postos(con):
        outro = coletas.posto_com_mesmo_login(con, posto["id"])
        if outro:
            linhas.append(f"ATENÇÃO: {posto['apelido'] or posto['nome']} e {outro} estão com o mesmo usuário do Premmia.")
    return linhas
