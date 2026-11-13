"""Tela do Premmia: um cartão por posto, etapa da coleta em andamento e planilhas do mês."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from apps.match import banco, caminhos, credenciais, explicar, rotina, unidades
from src.modules.cash_reconciliation.adapters import premmia_portal

logger = logging.getLogger(__name__)

# Etapa técnica do premmia_portal -> frase para quem está olhando a tela.
ETAPAS = {
    "iniciar navegador": "abrindo o navegador",
    "abrir login": "abrindo o portal do Premmia",
    "enviar login": "entrando com o usuário do posto",
    "confirmar login": "entrando com o usuário do posto",
    "abrir pagamentos/products": "abrindo a página de pagamentos",
    "filtro pela URL": "escolhendo os dias",
    "aguardar Exportar": "esperando o portal montar a lista",
    "download XLSX": "baixando a planilha",
    "validar/persistir XLSX": "lendo as vendas",
}
_MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


@dataclass
class Planilha:
    mes: str      # AAAA-MM
    rotulo: str   # "nov/2026"


@dataclass
class Cartao:
    posto: object
    ativo: bool
    tem_credencial: bool
    estado: str          # ok | sem_movimento | erro | verificacao_humana | nunca | desligado | sem_credencial
    rotulo: str
    classe: str          # estado-ok | estado-alerta | estado-critico | ""
    dia: date | None = None
    qtd: int = 0
    total: Decimal = Decimal(0)
    mensagem: str = ""
    faltando: list[date] = field(default_factory=list)
    planilhas: list[Planilha] = field(default_factory=list)
    pode_coletar: bool = False


def _planilhas(unidade, pasta: Path, hoje: date) -> list[Planilha]:
    saida = []
    mes = hoje.replace(day=1)
    for _ in range(3):  # este mês e os dois anteriores
        if premmia_portal.caminho_mensal(unidade, mes, pasta).exists():
            saida.append(Planilha(f"{mes:%Y-%m}", f"{_MESES[mes.month - 1]}/{mes.year}"))
        mes = (mes - timedelta(days=1)).replace(day=1)
    return saida


def _faltando(unidade, pasta: Path, hoje: date) -> list[date]:
    ontem = hoje - timedelta(days=1)
    try:
        return [d for d in premmia_portal.dias_faltantes(unidade, ontem, pasta) if d.month == ontem.month]
    except Exception as exc:  # noqa: BLE001 - planilha ilegível não derruba a tela
        logger.warning("Premmia: não li a planilha do mês tipo=%s", type(exc).__name__)
        return []


def cartao(con, posto, hoje: date) -> Cartao | None:
    fonte = next((f for f in banco.fontes_do_posto(con, posto["id"]) if f["tipo"] == "premmia"), None)
    if fonte is None:
        return None
    pid = posto["id"]
    tem = credenciais.tem(f"{pid}/premmia/usuario") and credenciais.tem(f"{pid}/premmia/senha")
    base = {"posto": posto, "ativo": bool(fonte["ativo"]), "tem_credencial": tem}
    if not fonte["ativo"]:
        return Cartao(**base, estado="desligado", rotulo="Premmia desligado neste posto", classe="")
    if not tem:
        return Cartao(**base, estado="sem_credencial", rotulo="falta usuário e senha", classe="estado-alerta",
                      mensagem="Cadastre o usuário e a senha do Premmia em Configurações › Postos › Fontes.")
    unidade = unidades.do_posto(con, posto)
    pasta = caminhos.premmia(pid)
    extras = {"faltando": _faltando(unidade, pasta, hoje), "planilhas": _planilhas(unidade, pasta, hoje)}
    ultima = banco.ultima_coleta(con, fonte["id"])
    if ultima is None:
        return Cartao(**base, **extras, estado="nunca", rotulo="ainda não coletou", classe="")
    dia = date.fromisoformat(ultima["dia"])
    qtd, total = ultima["qtd"] or 0, Decimal(ultima["total"] or 0)
    situacao = ultima["situacao"]
    if situacao == "ok":
        return Cartao(**base, **extras, estado="ok", rotulo=f"{dia:%d/%m}: {qtd} venda(s)", classe="estado-ok",
                      dia=dia, qtd=qtd, total=total,
                      mensagem=f"{qtd} venda(s) em {dia:%d/%m/%Y}, {explicar.dinheiro(total)}.")
    if situacao == "sem_movimento":
        return Cartao(**base, **extras, estado="sem_movimento", rotulo=f"{dia:%d/%m}: sem vendas", classe="estado-ok",
                      dia=dia, mensagem=f"O Premmia não mostra vendas em {dia:%d/%m/%Y}.")
    if situacao == "verificacao_humana":
        return Cartao(**base, **extras, estado="verificacao_humana", rotulo="pediu verificação", classe="estado-alerta",
                      dia=dia, mensagem="O portal do Premmia pediu verificação (\"não sou robô\"). Clique em "
                                        "Coletar mostrando o navegador e resolva na janela que abrir.")
    return Cartao(**base, **extras, estado="erro", rotulo="erro na última coleta", classe="estado-critico", dia=dia,
                  mensagem=ultima["erro_texto"] or "A coleta falhou.")


def cartoes(con, posto_ids: list[int], hoje: date) -> list[Cartao]:
    saida = []
    for pid in posto_ids:
        p = banco.obter_posto(con, pid)
        if p is not None and p["ativo"]:
            c = cartao(con, p, hoje)
            if c is not None:
                saida.append(c)
    return saida


def andamento(con) -> dict:
    """{'posto': nome, 'etapa': frase} enquanto a coleta roda; vazio se nada está rodando."""
    if not rotina.em_andamento():
        return {}
    for codigo, etapa in list(premmia_portal.ETAPA_ATUAL.items()):
        for p in banco.listar_postos(con):
            if unidades.codigo_empresa(p) == codigo:
                return {"posto": p["apelido"] or p["nome"], "etapa": ETAPAS.get(etapa, etapa)}
    return {"posto": "", "etapa": "coletando"}


def planilha(con, posto, mes: str) -> Path | None:
    try:
        dia = date.fromisoformat(f"{mes}-01")
    except ValueError:
        return None
    caminho = premmia_portal.caminho_mensal(unidades.do_posto(con, posto), dia, caminhos.premmia(posto["id"]))
    return caminho if caminho.exists() else None
