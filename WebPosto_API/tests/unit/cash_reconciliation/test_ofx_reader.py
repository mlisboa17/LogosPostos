"""Leitor OFX — fixtures sinteticos no formato observado de cada banco."""
from datetime import date, datetime
from decimal import Decimal

from src.modules.cash_reconciliation.adapters.ofx_reader import ler_ofx
from src.modules.cash_reconciliation.domain.models import Canal


def _ofx(bankid: str, trns: str) -> bytes:
    return f"""OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>
<BANKACCTFROM><BANKID>{bankid}<ACCTID>99999-9</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20260901<DTEND>20260930
{trns}
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>""".encode("cp1252")


def _trn(fitid: str, valor: str, posted: str, memo: str, name: str = "") -> str:
    nome = f"<NAME>{name}</NAME>" if name else ""
    return f"<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>{posted}<TRNAMT>{valor}<FITID>{fitid}{nome}<MEMO>{memo}</STMTTRN>"


def test_bb_classifica_bco24h_atm_e_ignora_pix_e_debitos():
    e = ler_ofx(_ofx("1", "".join([
        _trn("1", "500.00", "20260901000000[-3:BRT]", "01/09 05:21 TERMINAL X ATMR", "Dep dinheiro Bco 24h"),
        _trn("2", "1200.00", "20260928000000[-3:BRT]", "28/09 12:41 AGENCIA Y", "Dep dinheiro ATM"),
        _trn("3", "90.00", "20260901000000[-3:BRT]", "01/09 19:36 FULANO", "Pix - Recebido"),
        _trn("4", "-50.00", "20260901000000[-3:BRT]", "01/09 10:00 X", "Dep dinheiro Bco 24h"),
    ])))
    assert e.banco == "BB" and e.conta_sufixo == "9999-9" and e.inicio == date(2026, 9, 1)
    assert [d.fitid for d in e.depositos] == ["1", "2"]
    d24, atm = e.depositos
    assert d24.canal is Canal.BCO24H and d24.terminal == "TERMINAL X ATMR"
    assert d24.momento == datetime(2026, 9, 1, 5, 21) and d24.valor == Decimal("500.00")
    assert atm.canal is Canal.ATM_AGENCIA


def test_bb_usa_data_do_memo_quando_difere_da_postagem():
    e = ler_ofx(_ofx("1", _trn("1", "10", "20260908000000", "07/09 20:00 T", "Dep dinheiro Bco 24h")))
    assert e.depositos[0].data == date(2026, 9, 7)


def test_bradesco_varejo_com_e_sem_hora_e_atm():
    e = ler_ofx(_ofx("0237", "".join([
        _trn("A", "300.00", "20260901120000", "DEP DIN MAIS VAREJO 00080921 01091653"),
        _trn("B", "200.00", "20261006120000", "DEP DIN MAIS VAREJO"),
        _trn("C", "100.00", "20260908120000", "DEP DINHEIRO ATM AG06298MAQ050616SEQ08271"),
        _trn("D", "999.00", "20260908120000", "CIELO AMEX"),
    ])))
    a, b, c = e.depositos
    assert e.banco == "BRADESCO"
    assert a.canal is Canal.BCO24H and a.terminal == "00080921" and a.momento == datetime(2026, 9, 1, 16, 53)
    assert b.momento is None and b.data == date(2026, 10, 6)
    assert c.canal is Canal.ATM_AGENCIA


def test_itau_bco24h_sem_hora():
    e = ler_ofx(_ofx("0341", _trn("1", "750.00", "20260929100000[-03:EST]", "DEP DIN BCO24H 173744775")))
    (d,) = e.depositos
    assert e.banco == "ITAU" and d.canal is Canal.BCO24H and d.momento is None and d.data == date(2026, 9, 29)


def test_hash_identifica_o_arquivo():
    a = ler_ofx(_ofx("1", ""))
    b = ler_ofx(_ofx("1", _trn("1", "1", "20260901", "01/09 01:00 T", "Dep dinheiro Bco 24h")))
    assert len(a.sha256) == 64 and a.sha256 != b.sha256
