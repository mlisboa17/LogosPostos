from datetime import date, datetime
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.security.jwt_utils import create_access_token
from src.modules.cash_reconciliation.application.reincidencia import agregar_reincidencia
from src.modules.cash_reconciliation.adapters.persistencia import PersistenciaErro
from src.modules.cash_reconciliation.domain.cartoes import (
    Abastecimento,
    Atribuicao,
    Candidato,
    Investigacao,
    TransacaoAdquirente,
)
from src.modules.cash_reconciliation.domain.execucao import ResultadoDiario
from src.modules.cash_reconciliation.domain.fechamento import (
    Alerta,
    AuditoriaCaixa,
    Caixa,
    LinhaModalidade,
    ResultadoAuditoria,
    Severidade,
)
from src.modules.cash_reconciliation.domain.models import Proveniencia, Sangria, Unidade
from src.modules.cash_reconciliation.domain.recebimentos import (
    RecebimentoAdquirente,
    ResultadoRecebimentos,
)
from src.modules.cash_reconciliation.domain.tempo import formatar_data
from src.modules.cash_reconciliation.interfaces import http


def make_client(monkeypatch):
    unit = Unidade(empresa_codigo=321, nome="Unidade sintética", chave_env="TESTE_CHAVE", destinos=())
    monkeypatch.setattr(http, "carregar_unidades", lambda: {321: unit})
    app = FastAPI()
    app.include_router(http.router)
    client = TestClient(app)
    client.cookies.set(
        "access_token",
        create_access_token("director@example.invalid", extra={"role": "diretor", "token_type": "access"}),
    )
    return client


def test_reincidencia_explicita_cobertura_e_formata_datas_brasileiras(monkeypatch):
    monkeypatch.setattr(http, "agora", lambda: datetime(2026, 10, 3, 12))
    monkeypatch.setattr(http, "carregar_dia", lambda *_: None)
    client = make_client(monkeypatch)

    response = client.get(
        "/api/v1/cash-audit/reincidencia",
        params={"unidade": 321, "mes": "2026-10"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "empresa_codigo": 321,
        "mes": "2026-10",
        "dias_com_dados": [],
        "dias_sem_dados": ["01/10/2026", "02/10/2026", "03/10/2026"],
        "dias_sem_fechamento": ["01/10/2026", "02/10/2026", "03/10/2026"],
        "dias_sem_recebimentos": ["01/10/2026", "02/10/2026", "03/10/2026"],
        "funcionarios": [],
    }


def test_reincidencia_rejeita_mes_invalido_ou_unidade_desconhecida(monkeypatch):
    monkeypatch.setattr(http, "agora", lambda: datetime(2026, 10, 3, 12))
    client = make_client(monkeypatch)
    invalido = client.get("/api/v1/cash-audit/reincidencia", params={"unidade": 321, "mes": "2026-13"})
    desconhecido = client.get("/api/v1/cash-audit/reincidencia", params={"unidade": 999, "mes": "2026-10"})
    assert invalido.status_code == 422
    assert desconhecido.status_code == 404


def test_reincidencia_nao_oculta_falha_de_persistencia(monkeypatch):
    def falhar(*_):
        raise PersistenciaErro("registro indisponível")

    monkeypatch.setattr(http, "agora", lambda: datetime(2026, 10, 1, 12))
    monkeypatch.setattr(http, "carregar_dia", falhar)
    client = make_client(monkeypatch)

    response = client.get(
        "/api/v1/cash-audit/reincidencia",
        params={"unidade": 321, "mes": "2026-10"},
    )
    assert response.status_code == 500
    assert "registro indisponível" not in response.text


def test_agregacao_mensal_usa_avisos_pagbank_e_nao_duplica_candidatos():
    dia = date(2026, 10, 1)
    caixa = Caixa(
        codigo=10, empresa_codigo=321, data=dia, turno="1", pdv_codigo=1, funcionario_codigo=7,
        abertura=datetime(2026, 10, 1, 8), fechamento=datetime(2026, 10, 1, 16),
        fechado=True, consolidado=True, bloqueado=False,
    )
    sangria = Sangria(
        codigo=1, empresa_codigo=321, caixa_codigo=10, conta_codigo=1, funcionario_codigo=7,
        valor=Decimal("20"), momento=datetime(2026, 10, 1, 12), alterada=True,
    )
    auditoria = AuditoriaCaixa(
        caixa=caixa,
        modalidades=(LinhaModalidade(
            modalidade="dinheiro", rotulo="Dinheiro", apresentado=0, apurado=50, diferenca=-50,
        ),),
        sangrias=(sangria,),
        alertas=(Alerta(
            codigo="QUEBRA", severidade=Severidade.VERMELHO, mensagem="Quebra",
        ),),
    )
    proveniencia = Proveniencia(
        execucao_id="sintetica", executado_em=datetime(2026, 10, 2, 3),
        versao_regra="CASH_AUDIT_NOTURNO_V2", fonte_sangrias="sintetica", extratos=(),
    )
    investigacoes = []
    for atribuicao, frentista, candidatos in (
        (Atribuicao.ATRIBUIDO, 7, ()),
        (Atribuicao.SUGESTAO, None, (7, 7, 8)),
    ):
        transacao = TransacaoAdquirente(
            adquirente="PAGBANK", identificador="sintetico", nsu=None, autorizacao=None,
            valor=Decimal("12.30"), momento=datetime(2026, 10, 1, 13),
        )
        abastecimentos = tuple(
            Abastecimento(
                codigo=index, empresa_codigo=321, momento=datetime(2026, 10, 1, 12), bico=1,
                valor=Decimal("12.30"), frentista=codigo, venda_item_codigo=index,
            )
            for index, codigo in enumerate(candidatos, start=1)
        )
        investigacoes.append(Investigacao(
            transacao=transacao,
            atribuicao=atribuicao,
            frentista=frentista,
            candidatos=tuple(Candidato(
                abastecimento=item, pontos=60, motivos=("sugestão sintética",), venda_em_dinheiro=False,
            ) for item in abastecimentos),
            troca_de_forma=False,
        ))
    registro = ResultadoDiario(
        empresa_codigo=321,
        dia=dia,
        fechamento=ResultadoAuditoria(
            empresa_codigo=321, inicio=dia, fim=dia, caixas=(auditoria,), proveniencia=proveniencia,
        ),
        recebimentos=ResultadoRecebimentos(
            empresa_codigo=321,
            dia=dia,
            adquirentes=(RecebimentoAdquirente(
                adquirente="PAGBANK", situacao="ok", a_maior=tuple(investigacoes),
            ),),
        ),
        proveniencia=proveniencia,
        versoes_regras=("FECHAMENTO_V3", "CARTOES_V1"),
    )

    resultado = agregar_reincidencia(
        321,
        "2026-10",
        (dia, date(2026, 10, 2)),
        (registro,),
        {7: "Nome sintético", 8: "Outro nome sintético"},
    )
    por_codigo = {item.funcionario_codigo: item for item in resultado.funcionarios}
    assert resultado.dias_com_dados == (formatar_data(dia),)
    assert resultado.dias_sem_dados == (formatar_data(date(2026, 10, 2)),)
    assert resultado.dias_sem_fechamento == (formatar_data(date(2026, 10, 2)),)
    assert resultado.dias_sem_recebimentos == (formatar_data(date(2026, 10, 2)),)
    assert por_codigo[7].nome == "Nome sintético"
    assert por_codigo[7].quebras == 1
    assert por_codigo[7].faltas_total == Decimal("50")
    assert por_codigo[7].sangrias_alteradas == 1
    assert por_codigo[7].recebimentos_a_maior_atribuidos == 1
    assert por_codigo[7].recebimentos_a_maior_sugeridos == 1
    assert por_codigo[8].recebimentos_a_maior_sugeridos == 1
