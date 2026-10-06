from datetime import date, datetime
from decimal import Decimal

from src.modules.cash_reconciliation.adapters.ofx_reader import Extrato
from src.modules.cash_reconciliation.application.conciliar import conciliar
from src.modules.cash_reconciliation.config import carregar_unidades
from src.modules.cash_reconciliation.domain.models import (
    Canal, DepositoBancario, Destino, Sangria, TipoDestino, Unidade,
)
from src.modules.cash_reconciliation.rules.matching import VERSAO

UNIDADE = Unidade(
    empresa_codigo=1, nome="TESTE", chave_env="X",
    destinos=(
        Destino(conta_codigo=24, tipo=TipoDestino.DEPOSITO_DIRETO, banco="BB", terminais=("POSTO T",)),
        Destino(conta_codigo=99, tipo=TipoDestino.COFRE, banco="BB"),
    ),
)


def S(cod, conta, valor, quando, alterada=False, empresa=1):
    return Sangria(codigo=cod, empresa_codigo=empresa, caixa_codigo=1, conta_codigo=conta, funcionario_codigo=7,
                   valor=Decimal(valor), momento=datetime.fromisoformat(quando), alterada=alterada)


def D(fitid, valor, quando, canal=Canal.BCO24H, terminal="POSTO T", banco="BB"):
    m = datetime.fromisoformat(quando)
    return DepositoBancario(fitid=fitid, banco=banco, conta="x", valor=Decimal(valor), data=m.date(),
                            momento=m, canal=canal, terminal=terminal)


def extrato(*deps):
    return {"bb.ofx": Extrato(banco="BB", conta_sufixo="x", inicio=None, fim=None, sha256="h" * 64, depositos=deps)}


def test_fluxo_direto_e_cofre():
    sangrias = [
        S(1, 24, "500", "2026-09-01T10:02"),            # direto, casa com d1
        S(2, 24, "80", "2026-09-01T11:00"),             # direto, sem deposito
        S(3, 99, "1000", "2026-09-01T20:00"),           # cofre dia 1
        S(4, 99, "600", "2026-09-02T20:00", alterada=True),
        S(5, None, "50", "2026-09-02T21:00"),           # sem destino
        S(6, 24, "999", "2026-09-02T09:00", empresa=2), # outra unidade: ignorada
    ]
    deps = extrato(
        D("d1", "500", "2026-09-01T10:00"),
        D("d2", "1000", "2026-09-02T16:00"),                        # deposito do cofre via 24h
        D("d3", "300", "2026-09-02T12:00", canal=Canal.ATM_AGENCIA, terminal="AG"),
        D("d4", "70", "2026-09-02T12:00", banco="ITAU"),            # outro banco: ignorado
    )
    r = conciliar(UNIDADE, sangrias, deps, date(2026, 9, 1), date(2026, 9, 2))

    (direto,) = r.fluxos_diretos
    assert [c.deposito.fitid for c in direto.casamentos] == ["d1"]
    assert [s.codigo for s in direto.sangrias_sem_deposito] == [2]
    assert [d.fitid for d in direto.depositos_sem_sangria] == ["d2"]

    (cofre,) = r.fluxos_cofre
    assert [(d.entradas, d.depositos, d.saldo) for d in cofre.dias] == [
        (Decimal(1000), Decimal(0), Decimal(1000)),
        (Decimal(600), Decimal(1300), Decimal(300)),
    ]
    assert [s.codigo for s in r.sangrias_sem_destino] == [5]
    assert [s.codigo for s in r.sangrias_alteradas] == [4]
    assert r.proveniencia.versao_regra == VERSAO and r.proveniencia.extratos == ("bb.ofx:" + "h" * 64,)


def test_config_real_carrega_e_nao_tem_segredos():
    unidades = carregar_unidades()
    assert set(unidades) == {74014, 11495, 5555, 118508}
    assert unidades[74014].destino(86248).tipo is TipoDestino.DEPOSITO_DIRETO
    assert all(u.chave_env.startswith("WEBPOSTO_API_KEY_") for u in unidades.values())
    assert all(not d.conta_sufixo for u in unidades.values() for d in u.destinos)


def test_destino_padrao_entra_no_cofre_mas_segue_como_alerta():
    unidade = UNIDADE.model_copy(update={"destino_padrao": 99})
    r = conciliar(unidade, [S(1, None, "200", "2026-09-01T20:00")], extrato(), date(2026, 9, 1), date(2026, 9, 1))
    assert r.fluxos_cofre[0].saldo_final == Decimal(200)
    assert [s.codigo for s in r.sangrias_sem_destino] == [1]
