"""Leitor de extrato OFX (SGML 1.02) — extrai apenas depositos em especie.

Padroes observados em set/2026 (AS-IS comprovado, ver ADR-002):
  BB (001)       NAME "Dep dinheiro Bco 24h" | "Dep dinheiro ATM"; MEMO "dd/mm hh:mm TERMINAL"
  Bradesco (237) MEMO "DEP DIN MAIS VAREJO <terminal> <DDMMHHMM>" | "DEP DINHEIRO ATM AG..MAQ..SEQ.."
  Itau (341)     MEMO "DEP DIN BCO24H <nsu>"  (sem hora)
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..domain.models import Canal, DepositoBancario
from ..domain.tempo import para_local

BANCOS = {"1": "BB", "001": "BB", "237": "BRADESCO", "0237": "BRADESCO", "341": "ITAU", "0341": "ITAU"}

_BB_MEMO = re.compile(r"^(\d{2})/(\d{2}) (\d{2}):(\d{2})\s*(.*)$")
_BRADESCO_VAREJO = re.compile(r"DEP DIN MAIS VAREJO(?:\s+(\d+)\s+(\d{2})(\d{2})(\d{2})(\d{2}))?")


@dataclass(frozen=True)
class Extrato:
    banco: str
    conta_sufixo: str
    inicio: date | None
    fim: date | None
    sha256: str
    depositos: tuple[DepositoBancario, ...]


def _tag(bloco: str, nome: str) -> str:
    m = re.search(rf"<{nome}>([^<\r\n]*)", bloco)
    return m.group(1).strip() if m else ""


def _data(valor: str) -> date | None:
    return datetime.strptime(valor[:8], "%Y%m%d").date() if len(valor) >= 8 else None


def _momento(postado: date, dia: int, mes: int, hora: int, minuto: int) -> datetime:
    ano = postado.year - (1 if mes > postado.month + 1 else 0)  # virada de ano
    return para_local(datetime(ano, mes, dia, hora, minuto))


def _classificar(banco: str, nome: str, memo: str, postado: date) -> tuple[Canal, str | None, datetime | None] | None:
    texto = f"{nome} {memo}".upper()
    if banco == "BB":
        if "DEP DINHEIRO" not in texto:
            return None
        canal = Canal.BCO24H if "BCO 24H" in texto else Canal.ATM_AGENCIA if "ATM" in texto else Canal.OUTRO
        m = _BB_MEMO.match(memo.strip())
        if m:
            d, mes, h, mi, terminal = m.groups()
            return canal, terminal.strip() or None, _momento(postado, int(d), int(mes), int(h), int(mi))
        return canal, None, None
    if banco == "BRADESCO":
        m = _BRADESCO_VAREJO.search(texto)
        if m:
            terminal, d, mes, h, mi = m.groups()
            momento = _momento(postado, int(d), int(mes), int(h), int(mi)) if d else None
            return Canal.BCO24H, terminal, momento
        if "DEP DINHEIRO ATM" in texto:
            return Canal.ATM_AGENCIA, None, None
        return None
    if "DEP DIN" in texto:  # Itau e demais
        canal = Canal.BCO24H if "BCO24H" in texto.replace(" ", "") else Canal.ATM_AGENCIA if "ATM" in texto else Canal.OUTRO
        return canal, None, None
    return None


def ler_ofx(conteudo: bytes) -> Extrato:
    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252")
    banco = BANCOS.get(_tag(texto, "BANKID"), _tag(texto, "BANKID") or "?")
    conta = _tag(texto, "ACCTID")
    sufixo = conta[-6:]
    depositos = []
    for bloco in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", texto, re.S):
        valor = Decimal(_tag(bloco, "TRNAMT").replace(",", ".") or "0")
        postado = _data(_tag(bloco, "DTPOSTED"))
        if valor <= 0 or postado is None:
            continue
        cls = _classificar(banco, _tag(bloco, "NAME"), _tag(bloco, "MEMO"), postado)
        if cls is None:
            continue
        canal, terminal, momento = cls
        depositos.append(
            DepositoBancario(
                fitid=_tag(bloco, "FITID"),
                banco=banco,
                conta=sufixo,
                valor=valor,
                data=momento.date() if momento else postado,
                momento=momento,
                canal=canal,
                terminal=terminal,
            )
        )
    return Extrato(
        banco=banco,
        conta_sufixo=sufixo,
        inicio=_data(_tag(texto, "DTSTART")),
        fim=_data(_tag(texto, "DTEND")),
        sha256=hashlib.sha256(conteudo).hexdigest(),
        depositos=tuple(depositos),
    )


def ler_arquivo(caminho: Path) -> Extrato:
    return ler_ofx(Path(caminho).read_bytes())
