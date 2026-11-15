"""Tela do PagBank: um cartão por posto com o último dia, a diferença com o webPosto e a ligação da fonte."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from apps.match import banco, coletas, credenciais, explicar
from apps.match.premmia_tela import Cartao


def _tem(pid: int) -> bool:
    return credenciais.tem(f"{pid}/pagbank/usuario") and credenciais.tem(f"{pid}/pagbank/token")


def cartao(con, posto) -> Cartao:
    pid = posto["id"]
    fonte = next((f for f in banco.fontes_do_posto(con, pid) if f["tipo"] == "pagbank_edi"), None)
    base = {"posto": posto, "ativo": bool(fonte and fonte["ativo"]), "tem_credencial": _tem(pid),
            "comparacao": coletas.tem_chave_webposto(con, posto),
            "tem_codigo": posto["empresa_codigo_webposto"] is not None}
    if not base["ativo"]:
        return Cartao(**base, estado="desligado", rotulo="PagBank desligado neste posto", classe="")
    if not base["tem_credencial"]:
        return Cartao(**base, estado="sem_credencial", rotulo="falta usuário e token", classe="estado-alerta",
                      mensagem="Informe o usuário e o token do PagBank (EDI) deste posto.")
    ultima = banco.ultima_coleta(con, fonte["id"])
    if ultima is None:
        return Cartao(**base, estado="nunca", rotulo="ainda não coletou", classe="")
    dia = date.fromisoformat(ultima["dia"])
    qtd, total = ultima["qtd"] or 0, Decimal(ultima["total"] or 0)
    total_wp = Decimal(ultima["total_webposto"]) if ultima["total_webposto"] is not None else None
    if ultima["situacao"] in ("ok", "sem_movimento"):
        diferente = total_wp is not None and total_wp != total
        return Cartao(**base, estado="ok", dia=dia, qtd=qtd, total=total, total_webposto=total_wp,
                      rotulo=f"{dia:%d/%m}: diferença com o webPosto" if diferente else f"{dia:%d/%m}: {qtd} venda(s)",
                      classe="estado-critico" if diferente else "estado-ok",
                      mensagem=f"{qtd} venda(s) em {dia:%d/%m/%Y}, {explicar.dinheiro(total)}.")
    return Cartao(**base, estado="erro", rotulo="erro na última coleta", classe="estado-critico", dia=dia,
                  mensagem=ultima["erro_texto"] or "A coleta falhou.")


def cartoes(con, posto_ids: list[int]) -> list[Cartao]:
    saida = []
    for pid in posto_ids:
        p = banco.obter_posto(con, pid)
        if p is not None and p["ativo"]:
            saida.append(cartao(con, p))
    return saida


def ligar(con, posto_id: int, usuario: str, token: str, chave_webposto: str) -> list[str]:
    """Liga o PagBank (e a comparação, se vier a chave). Em branco mantém o salvo. Devolve só os nomes trocados."""
    trocados = []
    for campo, valor in (("usuario", usuario), ("token", token)):
        if valor:
            credenciais.salvar(f"{posto_id}/pagbank/{campo}", valor)
            trocados.append(f"pagbank/{campo}")
    if not _tem(posto_id):
        raise ValueError("Informe o usuário e o token do PagBank deste posto.")
    fontes = {f["tipo"]: f for f in banco.fontes_do_posto(con, posto_id)}
    for tipo in ("pagbank_edi",) + (("webposto",) if chave_webposto else ()):
        atual = fontes.get(tipo)
        banco.salvar_fonte(con, posto_id, tipo, True, json.loads(atual["config_json"] or "{}") if atual else {})
    if chave_webposto:
        credenciais.salvar(f"{posto_id}/webposto/chave", chave_webposto)
        trocados.append("webposto/chave")
    return trocados
