from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from src.infrastructure.security.jwt_utils import create_access_token
from src.modules.cash_reconciliation.application.relatorio_caixa_dia import gerar_relatorio_caixa_dia
from src.modules.cash_reconciliation.domain.fechamento import (
    DescontoFalta,
    MovimentoDespesa,
    ValeFuncionario,
)
from src.modules.cash_reconciliation.domain.models import Sangria, Unidade
from src.modules.cash_reconciliation.domain.recebimentos import ResultadoRecebimentos
from src.modules.cash_reconciliation.interfaces import http

from .test_http import resultado_sintetico
from .test_resumo_diario import _registro, DIA, EMPRESA


def test_relatorio_diario_sintetico_mascara_dados_e_exibe_setores():
    unidade = Unidade(
        empresa_codigo=11495,
        nome="Posto VIP",
        apelido="VIP",
        chave_env="NAO_USADA",
        destinos=(),
    )
    base = resultado_sintetico()
    primeiro = base.caixas[0].model_copy(update={
        "caixa": base.caixas[0].caixa.model_copy(update={
            "empresa_codigo": 11495,
            "data": date(2026, 10, 10),
            "codigo": 100,
            "centro_custo": 7295,
            "funcionario_codigo": 30,
            "consolidado": False,
        }),
        "despesas": (MovimentoDespesa(
            codigo=1,
            caixa_codigo=100,
            tipo="D",
            valor=Decimal("25.00"),
            plano_conta_codigo=None,
            descricao="Pagamento para Ana CPF 123.456.789-00",
            centro_custo=7295,
        ),),
        "vales": (ValeFuncionario(
            codigo=1,
            empresa_codigo=11495,
            caixa_codigo=100,
            funcionario_codigo=30,
            origem="C",
            valor=Decimal("20.00"),
        ),),
        "vales_falta": (ValeFuncionario(
            codigo=2,
            empresa_codigo=11495,
            caixa_codigo=100,
            funcionario_codigo=30,
            origem="D",
            valor=Decimal("5.00"),
        ),),
        "sangrias": (Sangria(
            codigo=3,
            empresa_codigo=11495,
            caixa_codigo=100,
            conta_codigo=None,
            funcionario_codigo=30,
            valor=Decimal("15.00"),
            momento=datetime(2026, 10, 10, 9),
            alterada=True,
        ),),
        "desconto_falta": DescontoFalta(
            situacao="sem_desconto",
            falta=Decimal("5.00"),
            total_vale=Decimal(0),
            diferenca=Decimal("5.00"),
        ),
    })
    segundo = primeiro.model_copy(update={
        "caixa": primeiro.caixa.model_copy(update={
            "codigo": 101,
            "centro_custo": 24423,
            "funcionario_codigo": 31,
            "consolidado": True,
        }),
        "despesas": (),
        "vales": (),
        "vales_falta": (),
        "sangrias": (),
        "desconto_falta": None,
    })
    segundo = segundo.model_copy(update={
        "despesas": (MovimentoDespesa(
            codigo=2,
            caixa_codigo=101,
            tipo="D",
            valor=Decimal("80.00"),
            plano_conta_codigo="NF-1",
            descricao="Ajuste nota fiscal",
            centro_custo=18713,
        ),),
    })
    fechamento = base.model_copy(update={
        "empresa_codigo": 11495,
        "inicio": date(2026, 10, 10),
        "fim": date(2026, 10, 10),
        "caixas": (primeiro, segundo),
    })
    registro = _registro(alertas=()).model_copy(update={
        "empresa_codigo": 11495,
        "dia": date(2026, 10, 10),
        "fechamento": fechamento,
        "recebimentos": ResultadoRecebimentos(
            empresa_codigo=11495,
            dia=date(2026, 10, 10),
            adquirentes=(),
        ),
    })

    relatorio = gerar_relatorio_caixa_dia(
        registro,
        unidade,
        nomes_funcionarios={30: "Operador Sintético", 31: "Frentista Sintético"},
        situacao_robo="aviso",
    )

    assert "## Caixas" in relatorio
    assert "Operador Sintético (30)" in relatorio
    assert "Frentista Sintético (31)" in relatorio
    assert "PISTA" in relatorio and "FOOD" in relatorio
    assert "SEM PLANO" in relatorio
    assert "R$ 5,00 | provisória" in relatorio
    assert "vale comum" in relatorio and "falta de caixa" in relatorio
    assert "10/10/2026 09:00" in relatorio
    assert "Ajustes de NF (FECHAMENTO)" in relatorio
    assert "Ajuste nota fiscal" in relatorio
    despesas = relatorio.split("## Despesas", 1)[1].split("### Ajustes de NF", 1)[0]
    assert "Ajuste nota fiscal" not in despesas
    from src.modules.cash_reconciliation.application.relatorio_caixa_dia import _setor
    assert _setor(unidade, 22310) == "CONVENIÊNCIA"
    assert "CPF [omitido]" in relatorio
    assert "123.456.789-00" not in relatorio
    assert "não persistido" in relatorio
    assert "## Recebimentos" in relatorio and "## Pendências do dia" in relatorio


def test_relatorio_mascara_nsu_e_formata_data_hora():
    unidade = Unidade(
        empresa_codigo=EMPRESA,
        nome="Unidade sintética",
        chave_env="NAO_USADA",
        destinos=(),
    )
    registro = _registro(alertas=())
    item = SimpleNamespace(
        grupo=4,
        momento=datetime.fromisoformat("2026-10-09T13:45:00-03:00"),
        valor=Decimal("12.34"),
        de=None,
        para=None,
        responsavel="Nome Sintético (7)",
        caixa=10,
        nsu="NSU-987654321234",
    )
    troca = SimpleNamespace(
        grupo=2,
        momento=datetime.fromisoformat("2026-10-09T14:00:00-03:00"),
        valor=Decimal("12.34"),
        de="Dinheiro",
        para="Cartão",
        responsavel="Nome Sintético (7)",
        caixa=10,
        nsu=None,
    )
    relatorio = gerar_relatorio_caixa_dia(
        registro,
        unidade,
        conferencia=SimpleNamespace(itens=(item, troca)),
    )

    assert "09/10/2026 13:45" in relatorio
    assert "…1234" in relatorio
    assert "NSU-987654321234" not in relatorio
    assert "Dinheiro → Cartão" in relatorio
    assert all(f"### {grupo}:" in relatorio for grupo in ("Lançar", "Alterar", "Apurar", "Conferir à mão"))


def _cliente_api(monkeypatch, *, role: str, company_id: int | None = None):
    unidade = Unidade(
        empresa_codigo=EMPRESA,
        nome="Unidade Sintética",
        chave_env="NAO_USADA",
        destinos=(),
    )
    outra = Unidade(
        empresa_codigo=654,
        nome="Outra Unidade",
        chave_env="NAO_USADA",
        destinos=(),
    )
    monkeypatch.setattr(http, "carregar_unidades", lambda: {EMPRESA: unidade, 654: outra})
    monkeypatch.setattr(http, "carregar_dia", lambda codigo, dia: _registro(alertas=()))
    monkeypatch.setattr(http.saude_robo, "carregar_estado", lambda: None)
    monkeypatch.setattr(http, "conferencia_para_registro", lambda registro: SimpleNamespace(itens=()))
    monkeypatch.setattr(http, "_listar_pendencias_com_prazo", lambda **kwargs: [])
    monkeypatch.setattr(http, "_carregar_prazos_pendencia", lambda: {"vermelho": 3, "laranja": 5})
    app = FastAPI()
    app.include_router(http.router)
    client = TestClient(app)
    client.cookies.set(
        "access_token",
        create_access_token(
            "relatorio@example.invalid",
            extra={"role": role, "company_id": company_id, "token_type": "access"},
        ),
    )
    return client


def test_api_relatorio_usa_somente_persistencia_e_aplica_escopo_do_gerente(monkeypatch):
    client = _cliente_api(monkeypatch, role="gerente", company_id=EMPRESA)

    response = client.get("/api/v1/cash-audit/relatorio-caixa?dia=2026-10-09")
    proibido = client.get(
        "/api/v1/cash-audit/relatorio-caixa",
        params={"dia": "2026-10-09", "unidade": 654},
    )

    assert response.status_code == 200
    assert len(response.json()["relatorios"]) == 1
    assert "Relatório do caixa" in response.json()["relatorios"][0]["markdown"]
    assert proibido.status_code == 403


def test_api_relatorio_baixa_xlsx_com_abas_por_bloco(monkeypatch):
    client = _cliente_api(monkeypatch, role="diretor")

    response = client.get(
        "/api/v1/cash-audit/relatorio-caixa.xlsx",
        params={"dia": "2026-10-09", "unidade": EMPRESA},
    )

    workbook = load_workbook(BytesIO(response.content), read_only=True)
    assert response.status_code == 200
    assert {"Resumo", "Caixas", "Recebimentos", "Pendências do dia"}.issubset(workbook.sheetnames)
    workbook.close()