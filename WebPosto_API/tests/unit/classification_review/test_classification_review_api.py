"""Testes de integração HTTP e segurança da API de Revisão de Classificação."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.security.jwt_utils import create_access_token
from src.interfaces.http.routes.classification_review_routes import (
    get_classification_review_service,
    router as review_router,
)
from WebPosto_API.src.modules.classification_review import (
    CONTA_TEMPORARIA_CLASSIFICACAO,
    ClassificationReviewService,
    EstadoRevisao,
    SqliteClassificationReviewRepository,
)
from WebPosto_API.src.modules.master_data.adapters.migrations.migration_001_planos_conta_hierarquia import (
    migrar as migrar_001,
)
from WebPosto_API.src.modules.master_data.adapters.migrations.migration_002_fila_revisao_classificacao import (
    migrar as migrar_002,
)


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Banco SQLite temporário com esquema de master data e classificação."""
    db_file = tmp_path / "test_api_revisao.sqlite3"
    conn = sqlite3.connect(str(db_file))
    try:
        # Tabela master_planos_conta mínima
        conn.execute(
            """
            CREATE TABLE master_planos_conta (
                plano_conta_codigo INTEGER PRIMARY KEY,
                descricao TEXT NOT NULL,
                natureza TEXT NOT NULL DEFAULT 'DESPESA',
                grupo TEXT,
                ativo INTEGER NOT NULL DEFAULT 1,
                permite_despesa INTEGER NOT NULL DEFAULT 1,
                confiabilidade TEXT NOT NULL DEFAULT 'OFICIAL_ERP',
                origem_dado TEXT NOT NULL DEFAULT 'SYNC',
                atualizado_em TEXT NOT NULL DEFAULT '2026-10-23T00:00:00Z'
            );
            """
        )
        migrar_001(conn)
        migrar_002(conn)

        # Inserir planos para testes
        # 1. Folha candidata oficial válida
        conn.execute(
            """
            INSERT INTO master_planos_conta (
                plano_conta_codigo, descricao, hierarquia, pai_codigo, pai_hierarquia,
                nivel, eh_folha, candidato_lancavel, observado_ultima_sincronizacao
            ) VALUES (158764, 'MARCIO-PROLABORE', '2.02.05.005', 148303, '2.02.05', 4, 1, 1, 1);
            """
        )
        # 2. Outra folha válida
        conn.execute(
            """
            INSERT INTO master_planos_conta (
                plano_conta_codigo, descricao, hierarquia, pai_codigo, pai_hierarquia,
                nivel, eh_folha, candidato_lancavel, observado_ultima_sincronizacao
            ) VALUES (29031, 'OUTRAS SAIDAS DIVERSAS', '2.04.01', 29000, '2.04', 3, 1, 1, 1);
            """
        )
        # 3. Conta-pai estrutural (não lançável)
        conn.execute(
            """
            INSERT INTO master_planos_conta (
                plano_conta_codigo, descricao, hierarquia, pai_codigo, pai_hierarquia,
                nivel, eh_folha, candidato_lancavel, observado_ultima_sincronizacao
            ) VALUES (29021, 'PRO LABORE', '2.02.05', 29000, '2.02', 3, 0, 0, 1);
            """
        )
        # 4. Conta temporária 198966 (bloqueada para lançamento)
        conn.execute(
            """
            INSERT INTO master_planos_conta (
                plano_conta_codigo, descricao, hierarquia, pai_codigo, pai_hierarquia,
                nivel, eh_folha, candidato_lancavel, observado_ultima_sincronizacao
            ) VALUES (198966, 'SAÍDAS PENDENTES DE CLASSIFICAÇÃO', '2.04.10', 29031, '2.04', 3, 1, 0, 1);
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_file


@pytest.fixture
def review_service(test_db: Path) -> ClassificationReviewService:
    repo = SqliteClassificationReviewRepository(db_path=test_db)
    return ClassificationReviewService(repository=repo)


@pytest.fixture
def app_client(review_service: ClassificationReviewService) -> TestClient:
    app = FastAPI()
    app.include_router(review_router)
    app.dependency_overrides[get_classification_review_service] = lambda: review_service
    return TestClient(app)


def _token(role: str = "diretor", company_id: int | None = None) -> str:
    return create_access_token(
        f"{role}@logos.com",
        extra={"role": role, "company_id": company_id, "token_type": "access"},
    )


def _auth_headers(role: str = "diretor", company_id: int | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(role, company_id)}"}


# =====================================================================
# TESTES
# =====================================================================

def test_01_nao_autenticado_retorna_401(app_client: TestClient):
    res = app_client.get("/api/v1/classification-review/pendencias")
    assert res.status_code == 401


def test_02_listar_pendencias_com_filtros(app_client: TestClient, review_service: ClassificationReviewService):
    # Cadastrar 2 itens fictícios no banco temporário isolado
    review_service.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-10",
        valor="100.00",
        descricao="DESPESA A",
        confianca_ia=0.5,
    )
    review_service.registrar_movimento_para_revisao(
        empresa_codigo=5556,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-10",
        valor="200.00",
        descricao="DESPESA B",
        confianca_ia=0.5,
    )

    headers = _auth_headers("diretor")
    res = app_client.get("/api/v1/classification-review/pendencias", headers=headers)
    assert res.status_code == 200
    dados = res.json()
    assert dados["total"] == 2

    # Filtro por empresa
    res_filial = app_client.get("/api/v1/classification-review/pendencias?empresa_codigo=5555", headers=headers)
    assert res_filial.status_code == 200
    assert res_filial.json()["total"] == 1
    assert res_filial.json()["itens"][0]["empresa_codigo"] == 5555


def test_03_consultar_detalhes_e_historico(app_client: TestClient, review_service: ClassificationReviewService):
    it, _ = review_service.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-11",
        valor="75.00",
        descricao="COMPRA PECA",
        referencia_evidencias="fitid:999 token: secret12345",
        confianca_ia=0.6,
    )

    headers = _auth_headers("diretor")
    res_det = app_client.get(f"/api/v1/classification-review/pendencias/{it.id}", headers=headers)
    assert res_det.status_code == 200
    detalhes = res_det.json()
    assert detalhes["id"] == it.id
    assert "[REDACTED]" in detalhes["referencia_evidencias"]
    assert "secret12345" not in detalhes["referencia_evidencias"]

    # Histórico
    res_hist = app_client.get(f"/api/v1/classification-review/pendencias/{it.id}/historico", headers=headers)
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert hist["total"] == 1
    assert hist["eventos"][0]["acao"] == "CRIACAO"


def test_04_classificar_com_conta_folha_valida(app_client: TestClient, review_service: ClassificationReviewService):
    it, _ = review_service.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-12",
        valor="150.00",
        descricao="DESPESA MARCIO",
        confianca_ia=0.5,
    )

    headers = _auth_headers("diretor")
    payload = {
        "versao": it.versao,
        "plano_definitivo_codigo": 158764,  # MARCIO-PROLABORE (folha válida)
        "plano_definitivo_descricao": "MARCIO-PROLABORE",
        "centro_custo_definitivo_codigo": 7295,
        "justificativa": "Classificação confirmada",
    }
    res = app_client.post(
        f"/api/v1/classification-review/pendencias/{it.id}/classificar",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "SUCESSO"
    assert body["item"]["status"] == "CLASSIFICADO"
    assert body["item"]["versao"] == 2
    assert body["item"]["plano_definitivo_codigo"] == 158764


def test_05_rejeitar_plano_198966_como_definitivo(app_client: TestClient, review_service: ClassificationReviewService):
    it, _ = review_service.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-12",
        valor="150.00",
        descricao="DESPESA X",
        confianca_ia=0.5,
    )

    headers = _auth_headers("diretor")
    payload = {
        "versao": it.versao,
        "plano_definitivo_codigo": CONTA_TEMPORARIA_CLASSIFICACAO,  # 198966
        "justificativa": "Tentativa indevida de usar 198966",
    }
    res = app_client.post(
        f"/api/v1/classification-review/pendencias/{it.id}/classificar",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 422
    assert "198966 é temporária" in res.json()["detail"]


def test_06_rejeitar_plano_invalido_ou_pai(app_client: TestClient, review_service: ClassificationReviewService):
    it, _ = review_service.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-12",
        valor="150.00",
        descricao="DESPESA X",
        confianca_ia=0.5,
    )

    headers = _auth_headers("diretor")
    # Tentativa de usar conta-pai 29021 (PRO LABORE)
    payload = {
        "versao": it.versao,
        "plano_definitivo_codigo": 29021,
        "justificativa": "Tentativa de usar conta pai",
    }
    res = app_client.post(
        f"/api/v1/classification-review/pendencias/{it.id}/classificar",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 422
    assert "conta-pai estrutural" in res.json()["detail"]


def test_07_proteger_contra_concorrencia_e_replay(app_client: TestClient, review_service: ClassificationReviewService):
    it, _ = review_service.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-13",
        valor="180.00",
        descricao="DESPESA CONCORRENCIA",
        confianca_ia=0.5,
    )

    headers = _auth_headers("diretor")
    # 1. Primeira classificação (sucesso, versao 1 -> 2)
    payload1 = {
        "versao": 1,
        "plano_definitivo_codigo": 158764,
        "justificativa": "Primeira revisão",
    }
    res1 = app_client.post(
        f"/api/v1/classification-review/pendencias/{it.id}/classificar",
        json=payload1,
        headers=headers,
    )
    assert res1.status_code == 200

    # 2. Replay ou processo desatualizado com versao=1
    res2 = app_client.post(
        f"/api/v1/classification-review/pendencias/{it.id}/classificar",
        json=payload1,
        headers=headers,
    )
    assert res2.status_code == 409
    assert "Conflito de concorrência" in res2.json()["detail"]


def test_08_bloquear_e_cancelar_pendencia(app_client: TestClient, review_service: ClassificationReviewService):
    it, _ = review_service.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-14",
        valor="55.00",
        descricao="DESPESA SUSPEITA",
        confianca_ia=0.5,
    )
    headers = _auth_headers("diretor")

    # Bloqueio
    res_block = app_client.post(
        f"/api/v1/classification-review/pendencias/{it.id}/bloquear",
        json={"versao": 1, "motivo": "Comprovante ilegível"},
        headers=headers,
    )
    assert res_block.status_code == 200
    assert res_block.json()["status"] == "BLOQUEADO"

    # Cancelamento
    res_cancel = app_client.post(
        f"/api/v1/classification-review/pendencias/{it.id}/cancelar",
        json={"versao": 2, "motivo": "Lançamento cancelado pelo diretor"},
        headers=headers,
    )
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELADO"


def test_09_casos_semelhantes_e_metricas(app_client: TestClient, review_service: ClassificationReviewService):
    headers = _auth_headers("diretor")

    # Métricas iniciais
    res_met = app_client.get("/api/v1/classification-review/metricas", headers=headers)
    assert res_met.status_code == 200
    assert "taxa_acerto_ia" in res_met.json()

    # Casos semelhantes
    res_sem = app_client.get("/api/v1/classification-review/casos-semelhantes?descricao=PROLABORE", headers=headers)
    assert res_sem.status_code == 200
    assert "exemplos" in res_sem.json()


def test_10_planos_validos_exclui_198966_e_pais(app_client: TestClient):
    headers = _auth_headers("diretor")
    res = app_client.get("/api/v1/classification-review/planos-validos", headers=headers)
    assert res.status_code == 200
    planos = res.json()["planos"]

    codigos = [p["plano_conta_codigo"] for p in planos]
    assert 158764 in codigos  # Folha válida incluída
    assert 29031 in codigos   # Folha válida incluída
    assert 29021 not in codigos  # Conta pai excluída
    assert CONTA_TEMPORARIA_CLASSIFICACAO not in codigos  # 198966 rigorosamente excluída!


def test_11_regra_candidata_3_casos_elegivel_sem_automacao(app_client: TestClient, review_service: ClassificationReviewService):
    # Simular 3 revisões com o mesmo padrão para atingir o limiar
    for i in range(1, 4):
        it, _ = review_service.registrar_movimento_para_revisao(
            5555, 17837, f"2026-10-{10+i}", "20.00", "LAVAGEM PISTA CENTRAL", confianca_ia=0.5
        )
        review_service.revisar_e_classificar(it.id, 1, 29031, "OUTRAS SAIDAS", "rev")

    headers = _auth_headers("diretor")
    res = app_client.get("/api/v1/classification-review/regras-candidatas", headers=headers)
    assert res.status_code == 200
    regras = res.json()["regras"]
    assert len(regras) >= 1
    regra = regras[0]
    assert regra["total_casos_confirmados"] == 3
    assert regra["elegivel_para_revisao"] is True
    assert regra["status_regra"] == "CANDIDATA"
    assert regra["automacao_ativa"] is False  # Automação/lançamento estritamente inativos


def test_12_ausencia_total_escrita_erp_webposto(app_client: TestClient, review_service: ClassificationReviewService):
    with patch("httpx.Client.post") as m_post, \
         patch("httpx.Client.put") as m_put, \
         patch("httpx.Client.patch") as m_patch, \
         patch("httpx.Client.delete") as m_delete:

        headers = _auth_headers("diretor")

        it, _ = review_service.registrar_movimento_para_revisao(
            5555, 17837, "2026-10-15", "626.00", "PRÓ-LABORE — MÁRCIO", confianca_ia=0.5
        )

        app_client.get("/api/v1/classification-review/pendencias", headers=headers)
        app_client.get(f"/api/v1/classification-review/pendencias/{it.id}", headers=headers)
        app_client.post(
            f"/api/v1/classification-review/pendencias/{it.id}/classificar",
            json={"versao": 1, "plano_definitivo_codigo": 158764},
            headers=headers,
        )
        app_client.get("/api/v1/classification-review/metricas", headers=headers)
        app_client.get("/api/v1/classification-review/planos-validos", headers=headers)

        # Assegurar ZERO chamadas de mutação ao ERP webPosto
        erp_calls = [
            c
            for c in m_post.call_args_list
            if any(
                term in str(c).lower()
                for term in ("qualityautomacao", "webposto", "titulos_pagar", "movimentos_conta")
            )
        ]
        assert len(erp_calls) == 0
        m_put.assert_not_called()
        m_patch.assert_not_called()
        m_delete.assert_not_called()


def test_13_rbac_gerente_acesso_outra_unidade_negado(app_client: TestClient, review_service: ClassificationReviewService):
    # Gerente da empresa 5555 tenta acessar dados da empresa 5556
    it_5556, _ = review_service.registrar_movimento_para_revisao(
        5556, 17837, "2026-10-16", "50.00", "OUTRO POSTO", confianca_ia=0.5
    )

    headers_gerente_5555 = _auth_headers("gerente", company_id=5555)

    # Consulta de pendência de outra unidade deve retornar 403
    res = app_client.get(
        f"/api/v1/classification-review/pendencias/{it_5556.id}",
        headers=headers_gerente_5555,
    )
    assert res.status_code == 403
    assert "Acesso negado para esta unidade" in res.json()["detail"]
