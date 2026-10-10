import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.security.jwt_utils import create_access_token
from src.modules.cash_reconciliation.adapters import pendencias as repositorio
from src.modules.cash_reconciliation.application.gerar_pendencias import (
    pendencias_de_reincidencia,
    pendencias_do_dia,
)
from src.modules.cash_reconciliation.domain.execucao import ResultadoDiario
from src.modules.cash_reconciliation.domain.fechamento import (
    Alerta,
    AuditoriaCaixa,
    Caixa,
    ResultadoAuditoria,
    Severidade,
)
from src.modules.cash_reconciliation.domain.models import Proveniencia, Unidade
from src.modules.cash_reconciliation.domain.recebimentos import ResultadoRecebimentos
from src.modules.cash_reconciliation.interfaces import http

EMPRESA = 321
DIA = date(2026, 10, 6)


def criar_diario(dia: date, unidade: int = EMPRESA) -> ResultadoDiario:
    caixa = Caixa(
        codigo=100 + dia.day,
        empresa_codigo=unidade,
        data=dia,
        turno="Sintético",
        pdv_codigo=1,
        funcionario_codigo=7,
        abertura=datetime.combine(dia, datetime.min.time()),
        fechamento=datetime.combine(dia, datetime.min.time()),
        fechado=True,
        consolidado=True,
        bloqueado=False,
    )
    alerta = Alerta(
        codigo="QUEBRA",
        severidade=Severidade.VERMELHO,
        mensagem="Dinheiro: falta sintética",
        valor=Decimal("-25.00"),
        referencia=caixa.codigo,
    )
    proveniencia = Proveniencia(
        execucao_id=f"sintetica-{dia.isoformat()}",
        executado_em=datetime.combine(dia, datetime.min.time()),
        versao_regra="FECHAMENTO_V3",
        fonte_sangrias="sintética",
        extratos=(),
    )
    fechamento = ResultadoAuditoria(
        empresa_codigo=unidade,
        inicio=dia,
        fim=dia,
        caixas=(AuditoriaCaixa(caixa=caixa, modalidades=(), sangrias=(), alertas=(alerta,)),),
        proveniencia=proveniencia,
    )
    return ResultadoDiario(
        empresa_codigo=unidade,
        dia=dia,
        fechamento=fechamento,
        recebimentos=ResultadoRecebimentos(empresa_codigo=unidade, dia=dia, adquirentes=()),
        proveniencia=proveniencia,
        versoes_regras=("FECHAMENTO_V3", "CARTOES_V1"),
    )


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", tmp_path / "pendencias.sqlite3")
    monkeypatch.setattr(
        http,
        "carregar_unidades",
        lambda: {
            EMPRESA: Unidade(
                empresa_codigo=EMPRESA,
                nome="Unidade sintética",
                chave_env="CHAVE_TESTE",
                destinos=(),
            ),
            654: Unidade(
                empresa_codigo=654,
                nome="Outra unidade sintética",
                chave_env="OUTRA_CHAVE_TESTE",
                destinos=(),
            ),
        },
    )
    app = FastAPI()
    app.include_router(http.router)
    return TestClient(app)


def autenticar(client: TestClient, perfil: str, unidade: int | None = None, usuario: str | None = None):
    client.cookies.clear()
    client.cookies.set(
        "access_token",
        create_access_token(
            usuario or f"{perfil}@example.invalid",
            extra={"role": perfil, "company_id": unidade, "token_type": "access"},
        ),
    )


def test_alertas_criam_pendencias_com_chave_idempotente_e_historico_append_only(tmp_path):
    banco = tmp_path / "data" / "pendencias.sqlite3"
    candidatas = pendencias_do_dia(criar_diario(DIA))

    assert len(candidatas) == 1
    assert candidatas[0].tipo == "fechamento_quebra"
    assert repositorio.registrar(candidatas, banco=banco) == 1
    assert repositorio.registrar(candidatas, banco=banco) == 0

    itens, total = repositorio.listar(unidade=EMPRESA, banco=banco)
    assert total == 1
    assert itens[0].status == "aberta"
    assert itens[0].historico[0].acao == "criada"
    assert itens[0].historico[0].status_novo == "aberta"

    with sqlite3.connect(banco) as conexao:
        with pytest.raises(sqlite3.IntegrityError, match="imutavel"):
            conexao.execute("UPDATE historico_pendencias SET usuario = 'alterado'")
        with pytest.raises(sqlite3.IntegrityError, match="imutavel"):
            conexao.execute("DELETE FROM historico_pendencias")


def test_reincidencia_gera_um_alerta_so_apos_duas_ocorrencias():
    primeiro = criar_diario(DIA)
    segundo = criar_diario(date(2026, 10, 7))

    assert pendencias_de_reincidencia(EMPRESA, "2026-10", [primeiro]) == []
    reincidencias = pendencias_de_reincidencia(EMPRESA, "2026-10", [primeiro, segundo])

    assert len(reincidencias) == 1
    assert reincidencias[0].tipo == "reincidencia_quebra"
    assert reincidencias[0].dia == date(2026, 10, 7)
    assert reincidencias[0].referencia == "funcionario:7"


def test_gerente_justifica_e_diretor_decide_sem_alterar_historico(client, tmp_path):
    candidatas = pendencias_do_dia(criar_diario(DIA))
    repositorio.registrar(candidatas, banco=tmp_path / "pendencias.sqlite3")

    autenticar(client, "gerente", EMPRESA, "gerente@example.invalid")
    fila = client.get("/api/v1/cash-audit/pendencias", params={"unidade": EMPRESA})
    assert fila.status_code == 200
    pendencia_id = fila.json()["items"][0]["id"]
    assert client.get(
        "/api/v1/cash-audit/pendencias", params={"unidade": 654}
    ).status_code == 403
    assert client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/aprovar", json={}
    ).status_code == 403
    assert client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/justificar",
        json={"justificativa": "   "},
    ).status_code == 422

    justificada = client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/justificar",
        json={"justificativa": "Conferido com o responsável da unidade."},
    )
    assert justificada.status_code == 200
    assert justificada.json()["status"] == "justificada"
    assert justificada.json()["responsavel"] == "gerente@example.invalid"
    assert len(justificada.json()["historico"]) == 2

    corrigida = client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/justificar",
        json={"justificativa": "Complemento da justificativa registrado."},
    )
    assert corrigida.status_code == 200
    assert [
        evento["justificativa"] for evento in corrigida.json()["historico"]
    ] == [
        None,
        "Conferido com o responsável da unidade.",
        "Complemento da justificativa registrado.",
    ]

    autenticar(client, "diretor", usuario="diretor@example.invalid")
    aprovada = client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/aprovar",
        json={"observacao": "A justificativa foi aceita."},
    )
    assert aprovada.status_code == 200
    assert aprovada.json()["status"] == "aprovada"
    assert [evento["acao"] for evento in aprovada.json()["historico"]] == [
        "criada", "justificada", "justificativa_corrigida", "aprovada",
    ]
    assert client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/recusar", json={}
    ).status_code == 409


def test_auditor_le_mas_nao_altera_e_anonimo_nao_lista(client):
    assert client.get("/api/v1/cash-audit/pendencias").status_code == 401
    autenticar(client, "auditor")
    assert client.get("/api/v1/cash-audit/pendencias").status_code == 200
