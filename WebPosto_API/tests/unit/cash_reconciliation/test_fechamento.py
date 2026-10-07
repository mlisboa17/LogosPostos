from datetime import date, datetime
from decimal import Decimal

import httpx

from src.modules.cash_reconciliation.adapters.webposto_caixas import (
    buscar_apresentados, para_caixa, para_modalidades,
)
from src.modules.cash_reconciliation.application.auditar_fechamento import auditar
from src.modules.cash_reconciliation.domain.fechamento import Severidade
from src.modules.cash_reconciliation.domain.models import Sangria, Unidade
from src.modules.cash_reconciliation.rules.fechamento import VERSAO, auditar_caixa

CAIXA_API = {"caixaCodigo": 1, "empresaCodigo": 5555, "dataMovimento": "2026-10-05", "turnoCodigo": 1,
             "turno": "1º TURNO", "pdvCodigo": 9, "centroCusto": 7295, "funcionarioCodigo": 7,
             "abertura": "2026-10-05T00:17:16.000-03:00", "fechamento": "2026-10-06T00:03:40.000-03:00",
             "fechado": True, "consolidado": True, "bloqueado": False}
APRESENTADO_API = {"caixaCodigo": 1, "dinheiroApresentado": 1772.6, "dinheiroApurado": 1769.68,
                   "dinheiroDiferenca": 2.92, "cartaoApresentado": 100, "cartaoApurado": 150,
                   "cartaoDiferenca": -50, "chequeApresentado": 0, "chequeApurado": 0, "chequeDiferenca": 0}


def caixa(**kw):
    return para_caixa({**CAIXA_API, **kw})


def S(cod, conta=10, alterada=False, caixa_cod=1):
    return Sangria(codigo=cod, empresa_codigo=5555, caixa_codigo=caixa_cod, conta_codigo=conta,
                   funcionario_codigo=7, valor=Decimal("300"), momento=datetime(2026, 10, 5, 14, 30), alterada=alterada)


def test_mapeia_caixa_e_ignora_modalidades_zeradas():
    c = caixa()
    assert c.data == date(2026, 10, 5) and c.fechamento is not None and c.consolidado and c.centro_custo == 7295
    linhas = para_modalidades(APRESENTADO_API)
    assert [m.modalidade for m in linhas] == ["dinheiro", "cartao"]
    assert linhas[0].diferenca == Decimal("2.92") and linhas[1].rotulo == "Cartão"


def test_caixa_limpo_sem_alertas():
    a = auditar_caixa(caixa(), para_modalidades({**APRESENTADO_API, "cartaoDiferenca": 0}), [S(1)])
    assert a.alertas == () and a.severidade is None and a.quebra == Decimal("2.92")


def test_quebra_acima_do_limite_e_vermelha():
    a = auditar_caixa(caixa(), para_modalidades(APRESENTADO_API), [])
    (alerta,) = a.alertas
    assert alerta.codigo == "QUEBRA" and alerta.severidade is Severidade.VERMELHO
    assert "Cartão: falta de R$ 50,00" == alerta.mensagem


def test_fechado_nao_consolidado_e_laranja():
    a = auditar_caixa(caixa(consolidado=False), (), [])
    assert [(x.codigo, x.mensagem) for x in a.alertas] == [("NAO_CONSOLIDADO", "Caixa fechado e não consolidado")]
    assert a.severidade is Severidade.LARANJA


def test_caixa_aberto_nao_gera_quebra():
    linhas = para_modalidades({**APRESENTADO_API, "dinheiroDiferenca": -11560.89})
    a = auditar_caixa(caixa(fechado=False, consolidado=False, fechamento=None), linhas, [])
    assert [x.codigo for x in a.alertas] == ["CAIXA_ABERTO"]
    assert a.quebra == Decimal(0) and a.severidade is Severidade.LARANJA


def test_sangrias_sem_destino_e_alterada_do_proprio_caixa():
    a = auditar_caixa(caixa(), (), [S(1, conta=None), S(2, alterada=True), S(3, conta=None, caixa_cod=2)])
    assert [(x.codigo, x.referencia) for x in a.alertas] == [("SANGRIA_SEM_DESTINO", 1), ("SANGRIA_ALTERADA", 2)]
    assert a.severidade is Severidade.VERMELHO and len(a.sangrias) == 2


def test_auditar_filtra_unidade_periodo_e_tem_proveniencia():
    caixas = [caixa(), caixa(caixaCodigo=2, empresaCodigo=1), caixa(caixaCodigo=3, dataMovimento="2026-10-07")]
    r = auditar(5555, caixas, {1: para_modalidades(APRESENTADO_API)}, [S(1)], date(2026, 10, 5), date(2026, 10, 6))
    assert [c.caixa.codigo for c in r.caixas] == [1]
    assert r.quebra_total == Decimal("-47.08") and r.proveniencia.versao_regra == VERSAO


async def test_apresentados_filtrados_pelos_caixas_da_unidade(monkeypatch):
    monkeypatch.setenv("TEST_CHAVE", "k")
    handler = lambda req: httpx.Response(200, json={"ultimoCodigo": None, "resultados": [
        APRESENTADO_API, {**APRESENTADO_API, "caixaCodigo": 99}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t") as c:
        r = await buscar_apresentados(Unidade(empresa_codigo=5555, nome="T", chave_env="TEST_CHAVE", destinos=()),
                                      date(2026, 10, 5), date(2026, 10, 5), {1}, client=c)
    assert list(r) == [1]
