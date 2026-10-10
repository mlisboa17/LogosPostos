from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest

from src.modules.cash_reconciliation.adapters.webposto_caixas import (
    buscar_apresentados, para_caixa, para_modalidades,
)
from src.modules.cash_reconciliation.application.auditar_fechamento import auditar
from src.modules.cash_reconciliation.config import dias_tolerancia_consolidacao
from src.modules.cash_reconciliation.domain.fechamento import (
    AuditoriaCaixa,
    MovimentoDespesa,
    Severidade,
    ValeFuncionario,
)
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
    a = auditar_caixa(caixa(consolidado=False), (), [], hoje=date(2026, 10, 6))
    assert [(x.codigo, x.mensagem) for x in a.alertas] == [("NAO_CONSOLIDADO", "Fechado há 0 dias sem consolidar")]
    assert a.severidade is Severidade.LARANJA


def test_tolerancia_de_consolidacao_padrao_configuravel_e_validada(monkeypatch):
    monkeypatch.delenv("CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO", raising=False)
    assert dias_tolerancia_consolidacao() == 2
    monkeypatch.setenv("CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO", "4")
    assert dias_tolerancia_consolidacao() == 4
    monkeypatch.setenv("CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO", "-1")
    with pytest.raises(ValueError, match="inteiro não negativo"):
        dias_tolerancia_consolidacao()


def test_nao_consolidado_fica_vermelho_depois_da_tolerancia():
    a = auditar_caixa(caixa(consolidado=False), (), [], hoje=date(2026, 10, 9))
    (alerta,) = a.alertas
    assert alerta.codigo == "NAO_CONSOLIDADO"
    assert alerta.severidade is Severidade.VERMELHO
    assert alerta.mensagem == "Fechado há 3 dias sem consolidar"


def test_caixa_aberto_nao_gera_quebra():
    linhas = para_modalidades({**APRESENTADO_API, "dinheiroDiferenca": -11560.89})
    a = auditar_caixa(caixa(fechado=False, consolidado=False, fechamento=None), linhas, [])
    assert [x.codigo for x in a.alertas] == ["CAIXA_ABERTO"]
    assert a.quebra == Decimal(0) and a.severidade is Severidade.LARANJA


def test_sangrias_sem_destino_e_alterada_do_proprio_caixa():
    a = auditar_caixa(caixa(), (), [S(1, conta=None), S(2, alterada=True), S(3, conta=None, caixa_cod=2)])
    assert [(x.codigo, x.referencia) for x in a.alertas] == [("SANGRIA_SEM_DESTINO", 1), ("SANGRIA_ALTERADA", 2)]
    assert a.severidade is Severidade.VERMELHO and len(a.sangrias) == 2


def test_sangria_repassada_e_informativa_com_destino_configurado():
    a = auditar_caixa(
        caixa(), (), [S(1, conta=None)],
        repasse_sangria_para=5555,
        nome_destino_repasse="AP CASA CAIADA",
    )
    assert not any(alerta.codigo == "SANGRIA_SEM_DESTINO" for alerta in a.alertas)
    assert a.informativos == ("Sangria de R$ 300,00 às 14:30 repassada ao AP CASA CAIADA",)
    assert a.severidade is None


def test_resultado_v3_sem_campo_informativos_continua_valido():
    legado = auditar_caixa(caixa(), (), [S(1)]).model_dump(mode="python")
    legado.pop("informativos")
    assert AuditoriaCaixa.model_validate(legado).informativos == ()


def test_falta_em_dinheiro_sem_vale_gera_alerta_vermelho():
    linhas = para_modalidades({**APRESENTADO_API, "dinheiroDiferenca": -50})
    a = auditar_caixa(caixa(), linhas, [])
    assert a.desconto_falta.situacao == "sem_desconto"
    assert a.desconto_falta.falta == Decimal("50")
    assert any(x.codigo == "FALTA_SEM_DESCONTO" and x.severidade is Severidade.VERMELHO for x in a.alertas)


def test_vale_correspondente_e_vale_divergente():
    linhas = para_modalidades({**APRESENTADO_API, "dinheiroDiferenca": -50})
    vale = ValeFuncionario(
        codigo=10, empresa_codigo=5555, caixa_codigo=1, funcionario_codigo=7,
        origem="D", valor=Decimal("50"),
    )
    descontado = auditar_caixa(caixa(), linhas, [], vales=[vale])
    assert descontado.desconto_falta.situacao == "descontado"
    assert descontado.desconto_falta.total_vale == Decimal("50")
    assert not any(x.codigo == "FALTA_SEM_DESCONTO" for x in descontado.alertas)

    divergente = auditar_caixa(
        caixa(), linhas, [],
        vales=[vale.model_copy(update={"valor": Decimal("45")})],
    )
    alerta = next(x for x in divergente.alertas if x.codigo == "VALE_DIVERGENTE")
    assert divergente.desconto_falta.situacao == "divergente"
    assert alerta.severidade is Severidade.LARANJA and alerta.valor == Decimal("5")


def test_vale_de_outro_operador_caixa_ou_origem_nao_desconta_falta():
    linhas = para_modalidades({**APRESENTADO_API, "dinheiroDiferenca": -50})
    vales = [
        ValeFuncionario(codigo=1, empresa_codigo=5555, caixa_codigo=2, funcionario_codigo=7, origem="D", valor=50),
        ValeFuncionario(codigo=2, empresa_codigo=5555, caixa_codigo=1, funcionario_codigo=8, origem="D", valor=50),
        ValeFuncionario(codigo=3, empresa_codigo=5555, caixa_codigo=1, funcionario_codigo=7, origem="C", valor=50),
    ]
    a = auditar_caixa(caixa(), linhas, [], vales=vales)
    assert a.vales_falta == ()
    assert a.desconto_falta.situacao == "sem_desconto"


def test_despesas_d_do_caixa_exibidas_e_alertadas_quando_sem_classificacao():
    despesas = [
        MovimentoDespesa(
            codigo=11, caixa_codigo=1, tipo="D", valor=Decimal("20"),
            plano_conta_codigo=None, descricao=None,
        ),
        MovimentoDespesa(
            codigo=12, caixa_codigo=1, tipo="C", valor=Decimal("15"),
            plano_conta_codigo=None, descricao=None,
        ),
        MovimentoDespesa(
            codigo=13, caixa_codigo=2, tipo="D", valor=Decimal("5"),
            plano_conta_codigo=None, descricao=None,
        ),
    ]
    a = auditar_caixa(caixa(), (), [], despesas=despesas)
    assert [item.codigo for item in a.despesas] == [11]
    assert {item.codigo for item in a.alertas} == {"DESPESA_SEM_PLANO", "DESPESA_SEM_DESCRICAO"}


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


@pytest.mark.asyncio
async def test_auditar_unidade_carrega_nome_de_destino_da_configuracao(monkeypatch):
    from src.modules.cash_reconciliation.application import auditar_fechamento as aplicacao

    unidades = {
        118508: Unidade(
            empresa_codigo=118508,
            nome="CONVENIENCIA 24 HORAS",
            chave_env="CHAVE_ORIGEM",
            destinos=(),
            repasse_sangria_para=5555,
        ),
        5555: Unidade(
            empresa_codigo=5555,
            nome="Casa Caiada",
            chave_env="CHAVE_DESTINO",
            destinos=(),
        ),
    }
    monkeypatch.setattr(aplicacao, "carregar_unidades", lambda: unidades)

    async def buscar_caixas_fake(*args):
        return [caixa(empresaCodigo=118508)]

    async def buscar_apresentados_fake(*args):
        return {}

    async def buscar_sangrias_fake(*args):
        return [S(1, conta=None).model_copy(update={"empresa_codigo": 118508})]

    async def vazio(*args):
        return []

    monkeypatch.setattr(aplicacao, "buscar_caixas", buscar_caixas_fake)
    monkeypatch.setattr(aplicacao, "buscar_apresentados", buscar_apresentados_fake)
    monkeypatch.setattr(aplicacao, "buscar_sangrias", buscar_sangrias_fake)
    monkeypatch.setattr(aplicacao, "buscar_vales", vazio)
    monkeypatch.setattr(aplicacao, "buscar_despesas", vazio)

    resultado = await aplicacao.auditar_unidade(
        118508,
        date(2026, 10, 5),
        date(2026, 10, 5),
    )
    assert resultado.caixas[0].informativos == (
        "Sangria de R$ 300,00 às 14:30 repassada ao Casa Caiada",
    )
