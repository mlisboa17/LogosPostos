"""Testes unitários do leitor geral de extratos (adapters/extrato_reader.py).

Fixtures 100% sintéticas, sem chamar serviços externos nem dados sensíveis.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.modules.cash_reconciliation.adapters.extrato_reader import (
    ExtratoBancario,
    LancamentoBancario,
    ler_arquivo,
    ler_ofx,
    validar_cabecalho_ofx,
)


def _gerar_ofx_sgml(bankid: str, acctid: str, trns: str, encoding: str = "cp1252") -> bytes:
    conteudo = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS><DTSERVER>20261011120000[-3:BRT]<LANGUAGE>POR</SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><STMTRS>
<BANKACCTFROM><BANKID>{bankid}<ACCTID>{acctid}</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20261001<DTEND>20261010
{trns}
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>"""
    return conteudo.encode(encoding)


def _gerar_ofx_pagbank_xml_style(trns: str) -> bytes:
    conteudo = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:100
SECURITY:NONE
ENCODING:UTF-8
CHARSET:NONE
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE
<OFX>
  <SIGNONMSGSRSV1>
    <SONRS>
      <STATUS><CODE>0</CODE><SEVERITY>INFO</SEVERITY></STATUS>
      <DTSERVER>20261011113418[-3:BRT]</DTSERVER>
      <LANGUAGE>POR</LANGUAGE>
      <FI><ORG>PagSeguro Internet S/A</ORG><FID>290</FID></FI>
    </SONRS>
  </SIGNONMSGSRSV1>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STATUS><CODE>0</CODE><SEVERITY>INFO</SEVERITY></STATUS>
      <STMTRS>
        <BANKACCTFROM>
          <BANKID>290</BANKID>
          <ACCTID>84369048-8</ACCTID>
          <ACCTTYPE>CHECKING</ACCTTYPE>
        </BANKACCTFROM>
        <BANKTRANLIST>
          <DTSTART>20261001</DTSTART>
          <DTEND>20261011</DTEND>
          {trns}
        </BANKTRANLIST>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>"""
    return conteudo.encode("utf-8")


def test_leitura_ofx_pagbank_in_out_com_hora_e_fuso():
    trns = """
    <STMTTRN>
      <TRNTYPE>IN</TRNTYPE>
      <DTPOSTED>20261001233317[-3:BRT]</DTPOSTED>
      <TRNAMT>19.87</TRNAMT>
      <FITID>uuid-1</FITID>
      <MEMO>Vendas - Disponivel DEBITO MASTERCARD</MEMO>
    </STMTTRN>
    <STMTTRN>
      <TRNTYPE>OUT</TRNTYPE>
      <DTPOSTED>20261002142000[-3:BRT]</DTPOSTED>
      <TRNAMT>150.00</TRNAMT>
      <FITID>uuid-2</FITID>
      <MEMO>Pix enviado fornecedor</MEMO>
    </STMTTRN>
    """
    raw = _gerar_ofx_pagbank_xml_style(trns)
    extrato = ler_ofx(raw)

    assert extrato.banco == "PAGBANK"
    assert extrato.conta_sufixo == "9048-8"
    assert extrato.quantidade == 2
    assert extrato.total_creditos == Decimal("19.87")
    assert extrato.total_debitos == Decimal("150.00")
    assert extrato.saldo_liquido == Decimal("19.87") - Decimal("150.00")

    l1, l2 = extrato.lancamentos
    assert l1.tipo == "CREDIT"
    assert l1.tipo_original == "IN"
    assert l1.valor == Decimal("19.87")
    assert l1.data == date(2026, 10, 1)
    assert l1.momento is not None
    assert l1.categoria == "vendas cartão"

    assert l2.tipo == "DEBIT"
    assert l2.tipo_original == "OUT"
    assert l2.valor == Decimal("-150.00")
    assert l2.categoria == "PIX enviado"


def test_leitura_ofx_bb_sgml_credit_debit():
    trns = """
    <STMTTRN>
      <TRNTYPE>CREDIT
      <DTPOSTED>20261001000000[-3:BRT]
      <TRNAMT>500.00
      <FITID>bb-1
      <CHECKNUM>12345
      <NAME>Dep dinheiro Bco 24h
      <MEMO>01/10 10:24 POSTO REAL FOSFATO ATMR
    </STMTTRN>
    <STMTTRN>
      <TRNTYPE>DEBIT
      <DTPOSTED>20261002000000[-3:BRT]
      <TRNAMT>-85.50
      <FITID>bb-2
      <MEMO>Tarifa Bancaria
    </STMTTRN>
    """
    raw = _gerar_ofx_sgml("001", "114068-X", trns, encoding="cp1252")
    extrato = ler_ofx(raw)

    assert extrato.banco == "BB"
    assert extrato.conta_sufixo == "4068-X"
    assert extrato.quantidade == 2
    assert extrato.total_creditos == Decimal("500.00")
    assert extrato.total_debitos == Decimal("85.50")
    assert extrato.lancamentos[0].categoria == "depósito"
    assert extrato.lancamentos[1].categoria == "tarifa"


def test_tolerancia_virgula_decimal_e_tags_sem_fechamento():
    trns = """
    <STMTTRN>
      <TRNTYPE>CREDIT
      <DTPOSTED>20261005
      <TRNAMT>1.250,50
      <FITID>fit-virgula
      <MEMO>PIX RECEBIDO CLIENTE
    <STMTTRN>
      <TRNTYPE>DEBIT
      <DTPOSTED>20261006
      <TRNAMT>-10,00
      <FITID>fit-deb
      <MEMO>TARIFA
    """
    raw = _gerar_ofx_sgml("237", "001234-5", trns)
    extrato = ler_ofx(raw)

    assert extrato.banco == "BRADESCO"
    assert extrato.quantidade == 2
    assert extrato.lancamentos[0].valor == Decimal("1250.50")
    assert extrato.lancamentos[1].valor == Decimal("-10.00")


def test_deduplicacao_de_lancamentos_duplicados_no_arquivo():
    trns = """
    <STMTTRN>
      <TRNTYPE>CREDIT</TRNTYPE>
      <DTPOSTED>20261001</DTPOSTED>
      <TRNAMT>100.00</TRNAMT>
      <FITID>dup-1</FITID>
      <MEMO>Venda</MEMO>
    </STMTTRN>
    <STMTTRN>
      <TRNTYPE>CREDIT</TRNTYPE>
      <DTPOSTED>20261001</DTPOSTED>
      <TRNAMT>100.00</TRNAMT>
      <FITID>dup-1</FITID>
      <MEMO>Venda</MEMO>
    </STMTTRN>
    """
    raw = _gerar_ofx_pagbank_xml_style(trns)
    extrato = ler_ofx(raw)
    assert extrato.quantidade == 1


def test_recusa_arquivo_sem_cabecalho_ofx():
    with pytest.raises(ValueError, match="cabeçalho OFX ausente"):
        validar_cabecalho_ofx(b"Data;Valor;Descricao\n10/10/2026;100;PIX")

    with pytest.raises(ValueError, match="cabeçalho OFX ausente"):
        ler_ofx(b"<html><body>Nao e OFX</body></html>")


def test_recusa_extensao_diferente_de_ofx(tmp_path):
    arquivo_csv = tmp_path / "extrato.csv"
    arquivo_csv.write_text("cabeçalho falso", encoding="utf-8")
    with pytest.raises(ValueError, match="Somente arquivos .ofx são permitidos"):
        ler_arquivo(arquivo_csv)
