"""Conferência do dia: totais webPosto x sites (Premmia, PagBank) primeiro, divergências depois, detalhe no clique.

Sem tolerância de valor: R$ 0,01 de diferença já é DIVERGENTE. Diferença = webPosto − site
(positiva: o webPosto tem mais; negativa: o site tem mais).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.match import banco, caminhos, unidades
from apps.match.explicar import dinheiro
from src.modules.cash_reconciliation.adapters import premmia_portal

SISTEMAS = (("premmia", "PREMMIA"), ("pagbank_edi", "PAGBANK"))
CONCILIADO, DIVERGENTE, SEM_DADOS = "CONCILIADO", "DIVERGENTE", "SEM DADOS"

ACAO_WEBPOSTO_MAIOR = ("WebPostos possui valor maior que o site. Verificar transações existentes apenas no WebPostos.",
                       ("Venda não processada pelo parceiro.", "Arquivo não importado.", "Falha na sincronização.",
                        "Lançamento duplicado no WebPostos.", "Transação pendente."))
ACAO_SITE_MAIOR = ("Site possui valor maior que o WebPostos. Verificar transações existentes apenas no site.",
                   ("Venda processada pelo parceiro e não recebida pelo WebPostos.", "Importação incompleta.",
                    "Falha de integração.", "Registro ausente no banco local."))
RESULTADO = {
    "falta_no_webposto": "Encontrado apenas no Site",
    "sobra_no_webposto": "Encontrado apenas no WebPostos",
    "valor_diferente": "Valores diferentes",
}


@dataclass
class Bloco:
    sistema: str                 # PREMMIA | PAGBANK
    webposto: Decimal | None
    site: Decimal | None
    motivo_sem_dados: str = ""

    @property
    def diferenca(self) -> Decimal | None:
        return None if self.webposto is None or self.site is None else self.webposto - self.site

    @property
    def status(self) -> str:
        if self.diferenca is None:
            return SEM_DADOS
        return CONCILIADO if self.diferenca == 0 else DIVERGENTE

    @property
    def acao(self) -> tuple[str, tuple[str, ...]] | None:
        if self.status != DIVERGENTE:
            return None
        return ACAO_WEBPOSTO_MAIOR if self.diferenca > 0 else ACAO_SITE_MAIOR


@dataclass
class Linha:
    id: int
    sistema: str
    identificador: str
    valor_webposto: Decimal
    valor_site: Decimal
    resultado: str
    acao: str
    situacao: str

    @property
    def diferenca(self) -> Decimal:
        return self.valor_webposto - self.valor_site


@dataclass
class Conferencia:
    posto: object
    dia: date
    blocos: list[Bloco]
    linhas: list[Linha] = field(default_factory=list)

    @property
    def comparados(self) -> list[Bloco]:
        return [b for b in self.blocos if b.diferenca is not None]

    @property
    def total_webposto(self) -> Decimal:
        return sum((b.webposto for b in self.comparados), Decimal(0))

    @property
    def total_sites(self) -> Decimal:
        return sum((b.site for b in self.comparados), Decimal(0))

    @property
    def divergencia(self) -> Decimal:
        return self.total_webposto - self.total_sites

    @property
    def status(self) -> str:
        if any(b.status == DIVERGENTE for b in self.blocos):
            return DIVERGENTE
        if not self.comparados or any(b.status == SEM_DADOS for b in self.blocos):
            return SEM_DADOS
        return CONCILIADO


def _bloco(con, posto_id: int, tipo: str, nome: str, dia: date) -> Bloco | None:
    fonte = next((f for f in banco.fontes_do_posto(con, posto_id) if f["tipo"] == tipo), None)
    if fonte is None or not fonte["ativo"]:
        return None
    c = con.execute("SELECT situacao, total, total_webposto, erro_texto FROM coleta WHERE fonte_id=? AND dia=?",
                    (fonte["id"], str(dia))).fetchone()
    if c is None:
        return Bloco(nome, None, None, "Dia ainda não coletado. Use Coletar outro dia ou período.")
    if c["situacao"] not in ("ok", "sem_movimento"):
        return Bloco(nome, None, None, c["erro_texto"] or "A coleta deste dia falhou.")
    if c["total_webposto"] is None:
        return Bloco(nome, None, Decimal(c["total"] or 0), "Coletado sem comparação com o webPosto (falta a chave).")
    return Bloco(nome, Decimal(c["total_webposto"]), Decimal(c["total"] or 0))


def _identificador(r, dados: list[dict]) -> str:
    for d in dados:
        if d.get("nsu") and d["nsu"] != "—":
            return f"NSU {d['nsu']}"
    for d in dados:
        if d.get("autorizacao") and d["autorizacao"] != "—":
            return f"Aut. {d['autorizacao']}"
    return r["referencia"] or "—"


def montar(con, posto_id: int, dia: date) -> Conferencia | None:
    posto = banco.obter_posto(con, posto_id)
    if posto is None:
        return None
    blocos = [b for tipo, nome in SISTEMAS if (b := _bloco(con, posto_id, tipo, nome, dia)) is not None]
    nome_por_tipo = dict(SISTEMAS)
    linhas = []
    for r in con.execute("SELECT * FROM divergencia WHERE posto_id=? AND dia=? ORDER BY fonte, id",
                         (posto_id, str(dia))):
        dados = json.loads(r["dados_json"]) if r["dados_json"] else []
        linhas.append(Linha(
            id=r["id"], sistema=nome_por_tipo.get(r["fonte"], r["fonte"]), identificador=_identificador(r, dados),
            valor_webposto=Decimal(r["valor_encontrado"] or 0), valor_site=Decimal(r["valor_esperado"] or 0),
            resultado=RESULTADO.get(r["tipo"], "Dados divergentes"), acao=r["correcao_pt"] or "",
            situacao=r["situacao"]))
    return Conferencia(posto, dia, blocos, linhas)


# ---------------------------------------------------------------- detalhe (segunda camada)

def _mascarar_cpf(cpf) -> str:
    dig = re.sub(r"\D", "", str(cpf or ""))
    return f"***.{dig[3:6]}.{dig[6:9]}-**" if len(dig) == 11 else "—"


def _cpfs_premmia(con, posto, dia: date) -> dict[str, str]:
    """NSU -> CPF mascarado, da planilha do Premmia guardada no computador (o PagBank não informa CPF)."""
    try:
        registros, _ = premmia_portal.ler_mensal(premmia_portal.caminho_mensal(
            unidades.do_posto(con, posto), dia, caminhos.premmia(posto["id"])))
    except Exception:  # noqa: BLE001 - sem planilha, sem CPF
        return {}
    return {str(r.get("Código Transação") or "").strip(): _mascarar_cpf(r.get("CPF")) for r in registros}


@dataclass
class Detalhe:
    linha: Linha
    dia: date
    webposto: list[dict]
    site: list[dict]
    explicacao: str
    criterios: list[str]


def detalhe(con, divergencia_id: int) -> Detalhe | None:
    r = con.execute("SELECT * FROM divergencia WHERE id=?", (divergencia_id,)).fetchone()
    if r is None:
        return None
    dia = date.fromisoformat(r["dia"])
    conf = montar(con, r["posto_id"], dia)
    linha = next(l for l in conf.linhas if l.id == divergencia_id)
    dados = json.loads(r["dados_json"]) if r["dados_json"] else []
    cpfs = _cpfs_premmia(con, conf.posto, dia) if r["fonte"] == "premmia" else {}

    def campos(d: dict, site: bool) -> dict:
        return {"Data": dia.strftime("%d/%m/%Y"), "Hora": d.get("hora", "—"),
                "CPF": cpfs.get(str(d.get("nsu") or ""), "—") if site else "—",
                "NSU": d.get("nsu") or "—", "Código da venda": "—" if site else (d.get("venda") or "—"),
                "Valor": d.get("valor", "—"), "Autorização": d.get("autorizacao") or "—",
                "Administradora": d.get("administradora") or "—", "Funcionário": d.get("funcionario") or "—"}

    return Detalhe(linha, dia, [campos(d, False) for d in dados if d.get("lado") == "webPosto"],
                   [campos(d, True) for d in dados if d.get("lado") != "webPosto"], r["explicacao_pt"] or "",
                   json.loads(r["criterios_json"]) if r["criterios_json"] else [])


def valor(v) -> str:
    return dinheiro(v) if v is not None else "—"
