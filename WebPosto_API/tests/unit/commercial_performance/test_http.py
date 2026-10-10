from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.security.jwt_utils import create_access_token
from src.modules.commercial_performance.adapters.persistencia import PersistenciaErro
from src.modules.commercial_performance.application import placar as aplicacao
from src.modules.commercial_performance.config import MetasErro, POSTOS
from src.modules.commercial_performance.domain.models import Placar, Proveniencia
from src.modules.commercial_performance.interfaces import http


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(http.router)
    client = TestClient(app)
    client.cookies.set(
        "access_token",
        create_access_token("director@example.invalid", extra={"role": "diretor", "token_type": "access"}),
    )
    return client


def placar_sintetico() -> Placar:
    return Placar(
        posto=11495,
        mes="2026-10",
        dia=date(2026, 10, 2),
        parcial=True,
        dias_mes=31,
        dias_restantes=30,
        frentistas_ativos=1,
        acumulado=Decimal("20"),
        realizado_dia=Decimal("10"),
        atendimentos=2,
        abastecimentos=2,
        atendimentos_fallback=2,
        ticket=Decimal("10"),
        projecao=Decimal("310"),
        nivel_projetado="abaixo_bronze",
        percentual_aditivado=Decimal(0),
        niveis={},
        diario=(),
        frentistas=(),
        mix=(),
        proveniencia=Proveniencia(
            executado_em=datetime(2026, 10, 2, 12),
            execucao_id="execucao-sintetica",
            versao_regra="PLACAR_V1",
            fontes=("/INTEGRACAO/V1/ABASTECIMENTOS",),
            metas_cadastradas=False,
        ),
    )


def test_placar_retorna_resultado_e_repasse_dos_parametros(client, monkeypatch):
    chamadas = []
    esperado = placar_sintetico()

    async def obter(posto, mes, dia):
        chamadas.append((posto, mes, dia))
        return esperado

    monkeypatch.setattr(http, "obter_placar", obter)
    response = client.get(
        "/api/v1/commercial/placar",
        params={"posto": 11495, "mes": "2026-10", "dia": "2026-10-02"},
    )

    assert response.status_code == 200
    assert response.json()["proveniencia"]["versao_regra"] == "PLACAR_V1"
    assert response.json()["atendimentos_fallback"] == 2
    assert chamadas == [(11495, "2026-10", date(2026, 10, 2))]


def test_placar_sem_dia_usa_data_padrao_da_aplicacao(client, monkeypatch):
    chamadas = []

    async def obter(*args):
        chamadas.append(args)
        return placar_sintetico()

    monkeypatch.setattr(http, "obter_placar", obter)
    response = client.get("/api/v1/commercial/placar", params={"posto": 11495, "mes": "2026-10"})

    assert response.status_code == 200
    assert chamadas == [(11495, "2026-10", None)]


def test_posto_fora_do_escopo_retorna_404_sem_consultar_aplicacao(client, monkeypatch):
    async def proibido(*args):
        pytest.fail("Posto não autorizado não deve consultar aplicação.")

    monkeypatch.setattr(http, "obter_placar", proibido)
    response = client.get("/api/v1/commercial/placar", params={"posto": 118508, "mes": "2026-10"})

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"posto": 11495, "mes": "2026-13"}, 422),
        ({"posto": 11495, "mes": "2026-10", "dia": "2026-10-32"}, 422),
    ],
)
def test_parametros_invalidos_retorna_422(client, monkeypatch, params, status):
    async def rejeitar(*args):
        raise ValueError("Parâmetro inválido.")

    monkeypatch.setattr(http, "obter_placar", rejeitar)
    response = client.get("/api/v1/commercial/placar", params=params)

    assert response.status_code == status


def test_fonte_indisponivel_retorna_erro_generico(client, monkeypatch):
    async def indisponivel(*args):
        raise aplicacao.FonteIndisponivel("URL privada e CHAVE secreta")

    monkeypatch.setattr(http, "obter_placar", indisponivel)
    response = client.get("/api/v1/commercial/placar", params={"posto": 11495, "mes": "2026-10"})

    assert response.status_code == 502
    assert "secreta" not in response.text
    assert response.json()["detail"] == "Fonte indisponível. Tente novamente."


def test_metas_indisponiveis_retorna_erro_generico(client, monkeypatch):
    async def indisponivel(*args):
        raise MetasErro("caminho privado")

    monkeypatch.setattr(http, "obter_placar", indisponivel)
    response = client.get("/api/v1/commercial/placar", params={"posto": 11495, "mes": "2026-10"})

    assert response.status_code == 500
    assert "caminho privado" not in response.text


def test_snapshot_indisponivel_retorna_erro_generico(client, monkeypatch):
    async def indisponivel(*args):
        raise PersistenciaErro("caminho privado")

    monkeypatch.setattr(http, "obter_placar", indisponivel)
    response = client.get(
        "/api/v1/commercial/placar",
        params={"posto": 11495, "mes": "2026-10"},
    )

    assert response.status_code == 500
    assert "caminho privado" not in response.text


def test_lista_apenas_os_tres_postos_sem_chave_env(client):
    response = client.get("/api/v1/commercial/postos")

    assert response.status_code == 200
    assert response.json() == [
        {"empresa_codigo": posto.empresa_codigo, "nome": posto.nome} for posto in POSTOS.values()
    ]
    assert "chave_env" not in response.text


def test_painel_resumo_usa_apenas_snapshots_persistidos_e_calcula_percentuais(client, monkeypatch):
    monkeypatch.setattr(
        http,
        "agora",
        lambda: datetime(2026, 10, 9, 12, tzinfo=ZoneInfo("America/Recife")),
    )
    postos = {codigo: POSTOS[codigo] for codigo in (11495, 74014, 5555)}
    monkeypatch.setattr(http, "POSTOS", postos)
    chamadas = []

    def carregar(posto, mes):
        chamadas.append((posto, mes))
        if posto == 5555:
            return None
        nivel = "bronze" if posto == 11495 else "ouro"
        return placar_sintetico().model_copy(update={"posto": posto, "nivel_projetado": nivel})

    def proibido(*args):
        pytest.fail("O resumo do painel não pode buscar placar no ERP.")

    monkeypatch.setattr(http, "carregar_placar", carregar)
    monkeypatch.setattr(http, "obter_placar", proibido)
    response = client.get("/api/v1/commercial/painel-resumo")

    assert response.status_code == 200
    resultado = response.json()
    assert resultado["mes"] == "2026-10"
    assert resultado["postos_com_snapshot"] == 2
    assert resultado["postos_com_projecao"] == 2
    assert resultado["percentuais"] == {"bronze": 50.0, "prata": 0.0, "ouro": 50.0}
    assert resultado["postos"][2]["com_snapshot"] is False
    assert chamadas == [(11495, "2026-10"), (74014, "2026-10"), (5555, "2026-10")]


def test_painel_resumo_escopo_de_gerente_e_perfil_auditor(client, monkeypatch):
    monkeypatch.setattr(
        http,
        "agora",
        lambda: datetime(2026, 10, 9, 12, tzinfo=ZoneInfo("America/Recife")),
    )
    chamadas = []
    monkeypatch.setattr(http, "carregar_placar", lambda posto, mes: chamadas.append((posto, mes)) or None)
    client.cookies.set(
        "access_token",
        create_access_token("manager@example.invalid", extra={
            "role": "gerente", "company_id": 11495, "token_type": "access",
        }),
    )
    response = client.get("/api/v1/commercial/painel-resumo")
    assert response.status_code == 200
    assert response.json()["total_postos"] == 1
    assert chamadas == [(11495, "2026-10")]

    client.cookies.set(
        "access_token",
        create_access_token("auditor@example.invalid", extra={"role": "auditor", "token_type": "access"}),
    )
    assert client.get("/api/v1/commercial/painel-resumo").status_code == 403
