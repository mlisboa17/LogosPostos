from datetime import date, datetime
from decimal import Decimal

from src.modules.cash_reconciliation.domain.models import Canal, DepositoBancario, Sangria
from src.modules.cash_reconciliation.rules.matching import casar


def S(cod: int, valor: str, quando: str) -> Sangria:
    return Sangria(codigo=cod, empresa_codigo=1, caixa_codigo=1, conta_codigo=10, funcionario_codigo=1,
                   valor=Decimal(valor), momento=datetime.fromisoformat(quando))


def D(fitid: str, valor: str, quando: str | None, dia: str | None = None) -> DepositoBancario:
    m = datetime.fromisoformat(quando) if quando else None
    return DepositoBancario(fitid=fitid, banco="BB", conta="x", valor=Decimal(valor),
                            data=m.date() if m else date.fromisoformat(dia), momento=m, canal=Canal.BCO24H)


def regras(casados):
    return sorted((c.regra, c.deposito.fitid, tuple(s.codigo for s in c.sangrias)) for c in casados)


def test_exato_deposito_minutos_antes_da_sangria():
    c, ss, dd = casar([S(1, "1520", "2026-09-01T16:49")], [D("a", "1520", "2026-09-01T16:47")])
    assert regras(c) == [("exato", "a", (1,))] and not ss and not dd


def test_prefere_deposito_mais_proximo():
    c, _, dd = casar([S(1, "100", "2026-09-01T10:00")],
                     [D("longe", "100", "2026-09-01T07:30"), D("perto", "100", "2026-09-01T09:58")])
    assert c[0].deposito.fitid == "perto" and [d.fitid for d in dd] == ["longe"]


def test_moedas_ficam_fora_do_deposito():
    c, _, _ = casar([S(1, "1200.08", "2026-09-08T10:25")], [D("a", "1200", "2026-09-08T10:24")])
    assert regras(c) == [("moedas", "a", (1,))] and c[0].diferenca == Decimal("0.08")


def test_duas_sangrias_num_deposito():
    c, ss, dd = casar([S(1, "330", "2026-09-03T18:04"), S(2, "30", "2026-09-03T18:13")],
                      [D("a", "360", "2026-09-03T18:03")])
    assert regras(c) == [("soma", "a", (1, 2))] and not ss and not dd


def test_janela_ampla_apos_curta():
    c, _, _ = casar([S(1, "700", "2026-09-04T00:07")], [D("a", "700", "2026-09-04T08:51")])
    assert regras(c) == [("janela24h", "a", (1,))]


def test_deposito_sem_hora_casa_por_dia():
    c, _, _ = casar([S(1, "750", "2026-09-28T22:00")], [D("a", "750", None, "2026-09-29")])
    assert regras(c) == [("exato", "a", (1,))]


def test_sem_par_sobra_dos_dois_lados():
    c, ss, dd = casar([S(1, "51", "2026-09-02T18:43")], [D("a", "1500", "2026-09-04T14:45")])
    assert not c and [s.codigo for s in ss] == [1] and [d.fitid for d in dd] == ["a"]


def test_cada_deposito_usado_uma_vez():
    c, ss, _ = casar([S(1, "100", "2026-09-01T10:00"), S(2, "100", "2026-09-01T10:01")],
                     [D("a", "100", "2026-09-01T09:59")])
    assert len(c) == 1 and len(ss) == 1
