"""Leitor geral de extratos bancários (OFX SGML e XML).

Regras da SPRINT 17 e 17B:
- Suporta OFX SGML 1.00/1.02 e XML 2.x;
- Tolera tags com e sem fechamento, BOM, linhas em branco, espaços e caracteres especiais (\xa0);
- Detecção de encoding: UTF-8, CP1252, ISO-8859-1;
- TRNTYPE: IN (crédito) e OUT (débito) do PagBank; CREDIT/DEBIT dos bancos tradicionais;
- DTPOSTED: com ou sem fuso horário (ex.: [-3:BRT]), com ou sem hora;
- TRNAMT: decimal com ponto ou vírgula;
- Barreira: recusa qualquer arquivo que não inicie por cabeçalho OFX.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..domain.tempo import para_local

BANCOS_CONHECIDOS = {
    "1": "BB",
    "001": "BB",
    "290": "PAGBANK",
    "237": "BRADESCO",
    "0237": "BRADESCO",
    "341": "ITAU",
    "0341": "ITAU",
    "104": "CAIXA",
    "033": "SANTANDER",
    "33": "SANTANDER",
    "260": "NUBANK",
}


@dataclass(frozen=True)
class LancamentoBancario:
    fitid: str
    data: date
    momento: datetime | None
    valor: Decimal  # Com sinal: positivo para créditos, negativo para débitos
    tipo: str  # "CREDIT" ou "DEBIT"
    tipo_original: str
    descricao: str
    documento: str | None = None
    categoria: str = "outros"

    @property
    def eh_credito(self) -> bool:
        return self.tipo == "CREDIT" or self.valor > 0

    @property
    def eh_debito(self) -> bool:
        return self.tipo == "DEBIT" or self.valor < 0


@dataclass(frozen=True)
class ExtratoBancario:
    banco: str
    agencia: str | None
    conta_sufixo: str
    inicio: date | None
    fim: date | None
    sha256: str
    lancamentos: tuple[LancamentoBancario, ...]

    @property
    def total_creditos(self) -> Decimal:
        return sum((l.valor for l in self.lancamentos if l.eh_credito), Decimal("0"))

    @property
    def total_debitos(self) -> Decimal:
        return sum((abs(l.valor) for l in self.lancamentos if l.eh_debito), Decimal("0"))

    @property
    def saldo_liquido(self) -> Decimal:
        return self.total_creditos - self.total_debitos

    @property
    def quantidade(self) -> int:
        return len(self.lancamentos)


def _classificar_categoria(desc: str) -> str:
    texto = desc.upper()
    if "PIX" in texto:
        if any(w in texto for w in ["RECEBIDO", "REC", "CRED"]):
            return "PIX recebido"
        if any(w in texto for w in ["ENVIADO", "ENV", "TRANSF"]):
            return "PIX enviado"
        return "PIX"
    if any(w in texto for w in ["VENDAS", "DEBITO MASTERCARD", "CREDITO MASTERCARD", "DEBITO VISA", "CREDITO VISA"]):
        return "vendas cartão"
    if any(w in texto for w in ["DEP DINHEIRO", "DEP DIN", "DEPOSITO"]):
        return "depósito"
    if any(w in texto for w in ["TARIFA", "TAXA", "MANUTENCAO"]):
        return "tarifa"
    if any(w in texto for w in ["RENDIMENTO", "REMUNERACAO", "JUROS"]):
        return "rendimento"
    if any(w in texto for w in ["TED", "DOC"]):
        return "TED/DOC"
    return "outros"


def _parse_data_hora(valor: str) -> tuple[date | None, datetime | None]:
    if not valor:
        return None, None
    valor = valor.strip()
    if len(valor) < 8 or not valor[:8].isdigit():
        return None, None
    d = datetime.strptime(valor[:8], "%Y%m%d").date()
    momento = None
    if len(valor) >= 14 and valor[8:14].isdigit():
        h = int(valor[8:10])
        mi = int(valor[10:12])
        s = int(valor[12:14])
        dt = datetime(d.year, d.month, d.day, h, mi, s)
        momento = para_local(dt)
    return d, momento


def _extrair_tag(bloco: str, nome: str) -> str:
    m = re.search(rf"<{nome}>([^<\r\n]*)", bloco, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def validar_cabecalho_ofx(conteudo: bytes) -> None:
    """Barreira: aceita apenas arquivo com cabeçalho OFX válido."""
    amostra = conteudo[:500].lstrip(b"\xef\xbb\xbf \t\r\n")  # remove BOM e espaços iniciais
    if not (
        amostra.startswith(b"OFXHEADER:")
        or amostra.startswith(b"<OFX")
        or (amostra.startswith(b"<?xml") and b"<OFX" in amostra[:500].upper())
    ):
        raise ValueError("Arquivo recusado: não é um arquivo OFX válido (cabeçalho OFX ausente).")


def _parse_decimal(val_str: str) -> Decimal:
    v = val_str.strip()
    if not v:
        return Decimal("0")
    if "." in v and "," in v:
        # Ex.: 1.250,50 -> 1250.50
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        # Ex.: 1250,50 -> 1250.50
        v = v.replace(",", ".")
    return Decimal(v)


def ler_ofx(conteudo: bytes) -> ExtratoBancario:
    """Lê bytes de um arquivo OFX e retorna ExtratoBancario."""
    validar_cabecalho_ofx(conteudo)
    sha256 = hashlib.sha256(conteudo).hexdigest()

    # Detecção de encoding
    texto = None
    for enc in ("utf-8", "cp1252", "iso-8859-1", "latin-1"):
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        texto = conteudo.decode("latin-1", errors="replace")

    # Limpeza de caracteres não-quebráveis e BOM
    texto = texto.replace("\ufeff", "").replace("\xa0", " ")

    bankid_raw = _extrair_tag(texto, "BANKID")
    banco = BANCOS_CONHECIDOS.get(bankid_raw, BANCOS_CONHECIDOS.get(bankid_raw.lstrip("0"), bankid_raw or "?"))
    
    agencia = _extrair_tag(texto, "BRANCHID") or None
    acctid = _extrair_tag(texto, "ACCTID")
    conta_sufixo = acctid[-6:] if len(acctid) >= 6 else acctid

    dtstart, _ = _parse_data_hora(_extrair_tag(texto, "DTSTART"))
    dtend, _ = _parse_data_hora(_extrair_tag(texto, "DTEND"))

    # Expressão flexível para blocos STMTTRN com ou sem tag de fechamento
    trn_blocks = re.findall(
        r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))",
        texto,
        re.DOTALL | re.IGNORECASE,
    )

    lancamentos: list[LancamentoBancario] = []
    vistos: set[tuple[str, str, Decimal, str]] = set()

    for idx, bloco in enumerate(trn_blocks):
        trntype = _extrair_tag(bloco, "TRNTYPE").upper()
        amt_str = _extrair_tag(bloco, "TRNAMT")
        try:
            val_raw = _parse_decimal(amt_str)
        except Exception as exc:
            raise ValueError(f"Valor numérico inválido na transação {idx + 1}: {amt_str}") from exc

        fitid = _extrair_tag(bloco, "FITID") or f"TRN_{idx + 1}"
        memo = _extrair_tag(bloco, "MEMO").strip()
        name = _extrair_tag(bloco, "NAME").strip()
        desc = f"{name} - {memo}" if name and memo and name != memo else (memo or name or "SEM DESCRICAO")
        checknum = _extrair_tag(bloco, "CHECKNUM") or None
        d, momento = _parse_data_hora(_extrair_tag(bloco, "DTPOSTED"))
        if d is None:
            continue

        # Normalização de tipo e sinal
        # PagBank usa IN e OUT
        if trntype in ("IN", "CREDIT"):
            tipo = "CREDIT"
            valor = abs(val_raw)
        elif trntype in ("OUT", "DEBIT"):
            tipo = "DEBIT"
            valor = -abs(val_raw)
        else:
            tipo = "CREDIT" if val_raw >= 0 else "DEBIT"
            valor = val_raw

        # Deduplicação por (fitid) ou por (data, valor, desc)
        chave_dedup = (fitid, str(d), valor, desc)
        if chave_dedup in vistos:
            continue
        vistos.add(chave_dedup)

        lancamentos.append(
            LancamentoBancario(
                fitid=fitid,
                data=d,
                momento=momento,
                valor=valor,
                tipo=tipo,
                tipo_original=trntype,
                descricao=desc,
                documento=checknum or fitid,
                categoria=_classificar_categoria(desc),
            )
        )

    return ExtratoBancario(
        banco=banco,
        agencia=agencia,
        conta_sufixo=conta_sufixo,
        inicio=dtstart,
        fim=dtend,
        sha256=sha256,
        lancamentos=tuple(lancamentos),
    )


def ler_arquivo(caminho: Path | str) -> ExtratoBancario:
    p = Path(caminho)
    if not p.suffix.lower().endswith(".ofx"):
        raise ValueError(f"Extensão inválida: {p.suffix}. Somente arquivos .ofx são permitidos.")
    return ler_ofx(p.read_bytes())
