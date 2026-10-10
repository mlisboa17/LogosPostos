import hashlib
import json
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
from src.modules.cash_reconciliation.domain.pendencias import NovaPendencia
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


def test_sangrias_repassadas_aprovam_abertas_e_preservam_justificadas_recusadas(
    tmp_path, monkeypatch,
):
    banco = tmp_path / "pendencias.sqlite3"
    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", banco)
    monkeypatch.setattr(
        "src.modules.cash_reconciliation.application.gerar_pendencias.carregar_unidades",
        lambda: {
            118508: Unidade(
                empresa_codigo=118508,
                nome="CONVENIENCIA 24 HORAS",
                chave_env="CHAVE_TESTE",
                destinos=(),
                repasse_sangria_para=5555,
            ),
        },
    )
    antigas = [
        NovaPendencia(
            unidade=118508,
            dia=DIA,
            tipo="fechamento_sangria_sem_destino",
            severidade="vermelho",
            valor=Decimal("25.00"),
            referencia=f"caixa:1:sangria:{indice}",
            mensagem="Sangria sem conta de destino",
        )
        for indice in range(1, 4)
    ]
    repositorio.registrar(antigas, banco=banco)
    abertas, _ = repositorio.listar(unidade=118508, status="aberta", banco=banco)
    repositorio.transicionar(
        abertas[0].id,
        status_esperado="aberta",
        status_novo="justificada",
        acao="justificada",
        usuario="gerente",
        justificativa="Conferida.",
        banco=banco,
    )
    repositorio.transicionar(
        abertas[1].id,
        status_esperado="aberta",
        status_novo="recusada",
        acao="recusada",
        usuario="diretor",
        justificativa="Não procede.",
        banco=banco,
    )

    resultado = criar_diario(DIA, unidade=118508)
    assert all(
        pendencia.tipo != "fechamento_sangria_sem_destino"
        for pendencia in pendencias_do_dia(resultado)
    )
    itens, total = repositorio.listar(unidade=118508, tipo="fechamento_sangria_sem_destino", banco=banco)
    assert total == 3
    por_status = {item.status: item for item in itens}
    aprovada = por_status["aprovada"]
    assert aprovada.historico[-1].acao == "aprovada"
    assert aprovada.historico[-1].usuario == "robo"
    assert aprovada.historico[-1].justificativa == (
        "Regra FECHAMENTO_V4: sangria da Conveniência 24h repassada ao Casa Caiada "
        "(decisão do diretor em 10/10/2026)"
    )
    historico_final = len(aprovada.historico)

    pendencias_do_dia(resultado)
    novamente, _ = repositorio.listar(unidade=118508, tipo="fechamento_sangria_sem_destino", banco=banco)
    assert len(next(item for item in novamente if item.status == "aprovada").historico) == historico_final
    assert {item.status for item in novamente} == {"aprovada", "justificada", "recusada"}

def diario_com_alertas(alertas):
    resultado = criar_diario(DIA)
    auditoria = resultado.fechamento.caixas[0].model_copy(update={"alertas": tuple(alertas)})
    fechamento = resultado.fechamento.model_copy(update={"caixas": (auditoria,)})
    return resultado.model_copy(update={"fechamento": fechamento})


def alertas_laranja(sufixo=""):
    return (
        Alerta(
            codigo="SANGRIA_ALTERADA",
            severidade=Severidade.LARANJA,
            mensagem=f"Sangria alterada A{sufixo}",
            valor=Decimal("10.00"),
            referencia=1,
        ),
        Alerta(
            codigo="DESPESA_SEM_PLANO",
            severidade=Severidade.LARANJA,
            mensagem=f"Despesa sem plano B{sufixo}",
            valor=Decimal("12.50"),
            referencia=2,
        ),
        Alerta(
            codigo="VALE_DIVERGENTE",
            severidade=Severidade.LARANJA,
            mensagem=f"Vale divergente C{sufixo}",
            valor=Decimal("2.50"),
            referencia=3,
        ),
    )


def test_alertas_laranja_do_caixa_agrupados_e_vermelho_individual():
    resultado = diario_com_alertas((
        Alerta(
            codigo="QUEBRA",
            severidade=Severidade.VERMELHO,
            mensagem="Dinheiro: quebra",
            valor=Decimal("-25.00"),
            referencia=106,
        ),
        *alertas_laranja(),
    ))

    novas = pendencias_do_dia(resultado)
    assert [pendencia.tipo for pendencia in novas] == [
        "fechamento_quebra",
        "caixa_alertas_laranja",
    ]
    grupo = novas[1]
    assert grupo.valor == Decimal("25.00")
    assert grupo.referencia == "caixa:106:laranja"
    assert len(json.loads(grupo.mensagem)["alertas"]) == 3


def test_reprocessar_atualiza_detalhe_aberto_sem_duplicar(tmp_path):
    banco = tmp_path / "pendencias.sqlite3"
    primeira = pendencias_do_dia(diario_com_alertas(alertas_laranja()))
    segunda = pendencias_do_dia(diario_com_alertas(alertas_laranja("-atualizado")))

    assert repositorio.registrar(primeira, banco=banco) == 1
    assert repositorio.registrar(segunda, banco=banco) == 0
    itens, total = repositorio.listar(unidade=EMPRESA, banco=banco)
    agrupada = next(item for item in itens if item.tipo == "caixa_alertas_laranja")
    assert total == 1
    assert agrupada.valor == Decimal("25.00")
    assert "atualizado" in agrupada.mensagem
    assert [evento.acao for evento in agrupada.historico] == ["criada", "detalhe_atualizado"]


def test_laranjas_individuais_abertas_sao_substituidas_com_historico(tmp_path):
    banco = tmp_path / "pendencias.sqlite3"
    resultado = diario_com_alertas(alertas_laranja())
    caixa = resultado.fechamento.caixas[0].caixa.codigo
    with sqlite3.connect(banco) as conexao:
        conexao.executescript(
            """
            CREATE TABLE pendencias (
                id TEXT PRIMARY KEY,
                identidade TEXT NOT NULL UNIQUE,
                unidade INTEGER NOT NULL,
                dia TEXT NOT NULL,
                tipo TEXT NOT NULL,
                severidade TEXT NOT NULL CHECK (severidade IN ('vermelho', 'laranja')),
                valor TEXT,
                referencia TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('aberta', 'justificada', 'aprovada', 'recusada')),
                responsavel TEXT,
                criada_em TEXT NOT NULL
            );
            CREATE TABLE historico_pendencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pendencia_id TEXT NOT NULL REFERENCES pendencias(id),
                acao TEXT NOT NULL,
                status_anterior TEXT,
                status_novo TEXT NOT NULL,
                usuario TEXT NOT NULL,
                justificativa TEXT,
                registrado_em TEXT NOT NULL
            );
            """
        )
    antigas = [
        NovaPendencia(
            unidade=EMPRESA,
            dia=DIA,
            tipo="fechamento_sangria_alterada",
            severidade="laranja",
            valor=Decimal("10.00"),
            referencia=f"caixa:{caixa}:sangria:{indice}",
            mensagem=f"Alerta individual {indice}",
        )
        for indice in range(1, 4)
    ]
    with sqlite3.connect(banco) as conexao:
        for indice, antiga in enumerate(antigas, start=1):
            identidade = hashlib.sha256(
                f"{antiga.unidade}|{antiga.dia.isoformat()}|{antiga.tipo}|{antiga.referencia}".encode()
            ).hexdigest()
            conexao.execute(
                """
                INSERT INTO pendencias
                    (id, identidade, unidade, dia, tipo, severidade, valor, referencia,
                     mensagem, status, responsavel, criada_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'aberta', NULL, ?)
                """,
                (
                    f"legada-{indice}", identidade, antiga.unidade, antiga.dia.isoformat(),
                    antiga.tipo, antiga.severidade, str(antiga.valor), antiga.referencia,
                    antiga.mensagem, datetime(2026, 10, 7).isoformat(),
                ),
            )
            conexao.execute(
                """
                INSERT INTO historico_pendencias
                    (pendencia_id, acao, status_anterior, status_novo, usuario, registrado_em)
                VALUES (?, 'criada', NULL, 'aberta', 'robô-noturno', ?)
                """,
                (f"legada-{indice}", datetime(2026, 10, 7).isoformat()),
            )

    agrupadas = pendencias_do_dia(resultado)
    assert repositorio.registrar(agrupadas, banco=banco) == 1
    itens, _ = repositorio.listar(unidade=EMPRESA, banco=banco)
    antiga_substituida = [item for item in itens if item.tipo == "fechamento_sangria_alterada"]
    agrupada = next(item for item in itens if item.tipo == "caixa_alertas_laranja")
    assert len(antiga_substituida) == 3
    assert all(item.status == "substituida" for item in antiga_substituida)
    assert all(item.referencia == agrupada.referencia for item in antiga_substituida)
    assert all(item.historico[-1].acao == "substituida" for item in antiga_substituida)
    assert all(agrupada.id in item.historico[-1].justificativa for item in antiga_substituida)
    with sqlite3.connect(banco) as conexao:
        assert conexao.execute("PRAGMA foreign_key_check").fetchall() == []


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
