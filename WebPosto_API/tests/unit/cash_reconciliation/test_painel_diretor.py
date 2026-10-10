from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.security.jwt_utils import create_access_token
from src.modules.cash_reconciliation.adapters import pendencias, persistencia, saude_robo
from src.modules.cash_reconciliation.interfaces import http
from src.modules.webposto_integration.tempo import FUSO

from .test_noturno import DIA, EMPRESA, diario, unidade


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "carregar_unidades", lambda: {
        EMPRESA: unidade(EMPRESA),
        322: unidade(322),
    })
    monkeypatch.setattr(persistencia, "DIRETORIO", tmp_path / "snapshots")
    monkeypatch.setattr(pendencias, "BANCO_PENDENCIAS", tmp_path / "pendencias.sqlite3")
    monkeypatch.setattr(saude_robo, "CAMINHO_ESTADO", tmp_path / "estado_robo.json")
    monkeypatch.setattr(http, "agora", lambda: datetime(2026, 10, 9, 12, tzinfo=FUSO))
    app = FastAPI()
    app.include_router(http.router)
    with TestClient(app) as test_client:
        test_client.cookies.set(
            "access_token",
            create_access_token("director@example.invalid", extra={"role": "diretor", "token_type": "access"}),
        )
        yield test_client


def set_role(client, role, company_id=None):
    client.cookies.set(
        "access_token",
        create_access_token(
            f"{role}@example.invalid",
            extra={"role": role, "company_id": company_id, "token_type": "access"},
        ),
    )


def test_painel_usa_snapshots_sem_chamar_o_erp_e_filtra_escopo_do_gerente(client, monkeypatch, tmp_path):
    persistencia.salvar_dia(diario(), diretorio=tmp_path / "snapshots")
    saude_robo.salvar_estado(
        saude_robo.EstadoRobo(
            ultima_execucao=datetime(2026, 10, 9, 11, tzinfo=FUSO),
            dia_processado=DIA,
            unidades_processadas=(EMPRESA, 322),
            unidades_com_falha=(322,),
            resumo_gerado=True,
        ),
        caminho=tmp_path / "estado_robo.json",
    )

    async def proibido(*args, **kwargs):
        pytest.fail("O painel não pode consultar o ERP.")

    monkeypatch.setattr(http, "auditar_unidade", proibido)
    monkeypatch.setattr(http, "conciliar_recebimentos", proibido)
    response = client.get("/api/v1/cash-audit/painel-diretor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["saude_robo"]["alerta_atraso"] is False
    assert payload["saude_robo"]["unidades_com_falha"] == [322]
    posto = next(item for item in payload["unidades"] if item["empresa_codigo"] == EMPRESA)
    assert posto["fechamento"]["quebra_total"] == "2.50"
    assert posto["recebimentos_a_maior_total"] == "0"
    assert posto["pendencias_abertas"] is None
    assert {item["situacao"] for item in posto["adquirentes"]} == {"ativo", "pendente"}

    set_role(client, "gerente", EMPRESA)
    response = client.get("/api/v1/cash-audit/painel-diretor")
    assert response.status_code == 200
    payload = response.json()
    assert [item["empresa_codigo"] for item in payload["unidades"]] == [EMPRESA]
    assert payload["saude_robo"]["unidades_processadas"] == [EMPRESA]
    assert payload["saude_robo"]["unidades_com_falha"] == []


@pytest.mark.parametrize(
    ("ultima_execucao", "alerta"),
    [
        (datetime(2026, 10, 8, 10, tzinfo=FUSO), False),
        (datetime(2026, 10, 8, 9, 59, 59, tzinfo=FUSO), True),
    ],
)
def test_alerta_de_saude_aplica_limite_exato_de_26_horas(client, tmp_path, ultima_execucao, alerta):
    saude_robo.salvar_estado(
        saude_robo.EstadoRobo(
            ultima_execucao=ultima_execucao,
            dia_processado=DIA,
            unidades_processadas=(EMPRESA,),
            unidades_com_falha=(),
            resumo_gerado=True,
        ),
        caminho=tmp_path / "estado_robo.json",
    )
    response = client.get("/api/v1/cash-audit/painel-diretor")
    assert response.status_code == 200
    assert response.json()["saude_robo"]["alerta_atraso"] is alerta


def test_painel_nao_substitui_snapshot_ausente_por_zero(client):
    response = client.get("/api/v1/cash-audit/painel-diretor")
    assert response.status_code == 200
    unidade_sem_snapshot = next(
        item for item in response.json()["unidades"] if item["empresa_codigo"] == 322
    )
    assert unidade_sem_snapshot["fechamento"] is None
    assert unidade_sem_snapshot["recebimentos_a_maior_total"] is None
    assert unidade_sem_snapshot["recebimentos_a_menor_total"] is None
    assert unidade_sem_snapshot["pendencias_abertas"] is None


def test_execucao_recente_sem_unidades_gera_alerta_operacional(client, tmp_path):
    saude_robo.salvar_estado(
        saude_robo.EstadoRobo(
            ultima_execucao=datetime(2026, 10, 9, 11, tzinfo=FUSO),
            dia_processado=DIA,
            unidades_processadas=(),
            unidades_com_falha=(),
            resumo_gerado=True,
        ),
        caminho=tmp_path / "estado_robo.json",
    )
    response = client.get("/api/v1/cash-audit/painel-diretor")
    assert response.status_code == 200
    saude = response.json()["saude_robo"]
    assert saude["alerta_atraso"] is False
    assert saude["execucao_sem_unidades"] is True
    assert saude["alerta_operacional"] is True


def test_painel_restringe_auditor_e_erro_de_estado_corrompido(client, tmp_path):
    set_role(client, "auditor")
    assert client.get("/api/v1/cash-audit/painel-diretor").status_code == 403

    client.cookies.set(
        "access_token",
        create_access_token("director@example.invalid", extra={"role": "diretor", "token_type": "access"}),
    )
    caminho = tmp_path / "estado_robo.json"
    caminho.write_text("inválido", encoding="utf-8")
    assert client.get("/api/v1/cash-audit/painel-diretor").status_code == 500


def test_contagem_local_e_so_leitura_e_ausente_permanece_indisponivel(tmp_path):
    banco = tmp_path / "inexistente.sqlite3"
    assert pendencias.contar_abertas_somente_leitura(unidade=EMPRESA, banco=banco) is None
    assert not banco.exists()
