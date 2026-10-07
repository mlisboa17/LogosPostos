from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.cash_reconciliation.adapters.webposto_http import WebPostoErro
from src.modules.cash_reconciliation.domain.fechamento import (
    Alerta,
    AuditoriaCaixa,
    Caixa,
    LinhaModalidade,
    Severidade,
    ResultadoAuditoria,
)
from src.modules.cash_reconciliation.domain.models import Proveniencia, Unidade
from src.modules.cash_reconciliation.interfaces import http


@pytest.fixture
def client(monkeypatch):
    unit = Unidade(
        empresa_codigo=321,
        nome="Unidade Sintética",
        chave_env="TESTE_CHAVE",
        destinos=(),
    )
    monkeypatch.setattr(http, "carregar_unidades", lambda: {321: unit})
    app = FastAPI()
    app.include_router(http.router)
    return TestClient(app)


def resultado_sintetico():
    caixa = Caixa(
        codigo=10,
        empresa_codigo=321,
        data=date(2026, 10, 1),
        turno="Turno sintético",
        pdv_codigo=1,
        centro_custo=2,
        funcionario_codigo=3,
        abertura=datetime(2026, 10, 1, 8),
        fechamento=datetime(2026, 10, 1, 16),
        fechado=True,
        consolidado=True,
        bloqueado=False,
    )
    modalidade = LinhaModalidade(
        modalidade="dinheiro",
        rotulo="Dinheiro",
        apresentado=Decimal("12.50"),
        apurado=Decimal("10.00"),
        diferenca=Decimal("2.50"),
    )
    alerta = Alerta(
        codigo="QUEBRA",
        severidade=Severidade.VERMELHO,
        mensagem="Diferença sintética",
        valor=Decimal("2.50"),
        referencia=10,
    )
    auditoria = AuditoriaCaixa(
        caixa=caixa,
        modalidades=(modalidade,),
        sangrias=(),
        alertas=(alerta,),
    )
    return ResultadoAuditoria(
        empresa_codigo=321,
        inicio=date(2026, 10, 1),
        fim=date(2026, 10, 1),
        caixas=(auditoria,),
        proveniencia=Proveniencia(
            execucao_id="execucao-sintetica",
            executado_em=datetime(2026, 10, 1, 17),
            versao_regra="FECHAMENTO_V1",
            fonte_sangrias="sintetica",
            extratos=(),
            outras_fontes=(),
        ),
    )


def test_retorna_fechamento_com_propriedades_calculadas(client, monkeypatch):
    async def auditar(*args):
        return resultado_sintetico()

    monkeypatch.setattr(http, "auditar_unidade", auditar)

    response = client.get(
        "/api/v1/cash-audit/fechamento",
        params={"unidade": 321, "inicio": "2026-10-01", "fim": "2026-10-01"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["caixas"][0]["caixa"]["codigo"] == 10
    assert payload["caixas"][0]["modalidades"][0]["modalidade"] == "dinheiro"
    assert payload["caixas"][0]["alertas"][0]["mensagem"] == "Diferença sintética"
    assert payload["caixas"][0]["quebra"] == "2.50"
    assert payload["caixas"][0]["severidade"] == "vermelho"
    assert payload["quebra_total"] == "2.50"
    assert payload["proveniencia"]["versao_regra"] == "FECHAMENTO_V1"


def test_unidade_inexistente_retorna_404(client):
    response = client.get(
        "/api/v1/cash-audit/fechamento",
        params={"unidade": 999, "inicio": "2026-10-01", "fim": "2026-10-01"},
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("inicio", "fim"),
    [
        ("data-invalida", "2026-10-01"),
        ("2026-10-02", "2026-10-01"),
        ("2026-10-01", "2026-11-01"),
    ],
)
def test_datas_invalidas_ou_periodo_longo_retorna_422(client, inicio, fim):
    response = client.get(
        "/api/v1/cash-audit/fechamento",
        params={"unidade": 321, "inicio": inicio, "fim": fim},
    )

    assert response.status_code == 422


def test_webposto_erro_retorna_mensagem_generica_sem_segredo(client, monkeypatch):
    async def falhar(*args):
        raise WebPostoErro("HTTP 400: ... segredo ...")

    monkeypatch.setattr(http, "auditar_unidade", falhar)
    response = client.get(
        "/api/v1/cash-audit/fechamento",
        params={"unidade": 321, "inicio": "2026-10-01", "fim": "2026-10-01"},
    )

    assert response.status_code == 502
    assert "segredo" not in response.text
    assert response.json()["detail"] == "Falha ao consultar os dados operacionais."


def test_listagem_de_unidades_nao_expoe_chave_env(client):
    response = client.get("/api/v1/cash-audit/unidades")

    assert response.status_code == 200
    assert response.json() == [{"empresa_codigo": 321, "nome": "Unidade Sintética"}]
    assert "chave_env" not in response.text
