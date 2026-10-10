from datetime import date
from decimal import Decimal

import httpx

from src.modules.cash_reconciliation.adapters.webposto_detalhes import (
    buscar_despesas,
    buscar_vales,
)
from src.modules.cash_reconciliation.domain.models import Unidade


def unidade():
    return Unidade(empresa_codigo=321, nome="Unidade sintética", chave_env="TESTE_CHAVE", destinos=())


async def test_busca_vales_filtra_empresa_e_mapeia_campos(monkeypatch):
    monkeypatch.setenv("TESTE_CHAVE", "chave-sintetica")
    linhas = [
        {
            "codigo": 1, "empresaCodigo": 321, "caixaCodigo": 10, "funcionarioCodigo": 7,
            "origem": "D", "valor": "25.50", "data": "2026-10-06",
        },
        {
            "codigo": 2, "empresaCodigo": 999, "caixaCodigo": 11, "funcionarioCodigo": 8,
            "origem": "D", "valor": "50.00", "data": "2026-10-06",
        },
    ]

    async def responder(request):
        assert request.url.path == "/INTEGRACAO/V1/VALES_FUNCIONARIO"
        return httpx.Response(200, json={"ultimoCodigo": None, "resultados": linhas})

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder), base_url="https://teste") as client:
        vales = await buscar_vales(unidade(), date(2026, 10, 6), date(2026, 10, 7), client=client)
    assert [(vale.codigo, vale.caixa_codigo, vale.funcionario_codigo, vale.valor) for vale in vales] == [
        (1, 10, 7, Decimal("25.50")),
    ]


async def test_busca_somente_despesas_d_do_caixa(monkeypatch):
    monkeypatch.setenv("TESTE_CHAVE", "chave-sintetica")
    linhas = [
        {
            "empresaCodigo": 321, "caixaMovimentoCodigo": 1, "tipo": "D",
            "valorCaixaMovimento": "12.30", "valorDinheiro": "12.30", "planoContaCodigo": "",
            "descricaoHistorico": "Lanche",
        },
        {
            "empresaCodigo": 321, "caixaMovimentoCodigo": 2, "tipo": "C",
            "valorCaixaMovimento": "50.00", "valorDinheiro": "50.00", "planoContaCodigo": 4,
            "descricaoHistorico": "Estorno",
        },
        {
            "empresaCodigo": 321, "caixaMovimentoCodigo": 4, "tipo": "D",
            "valorCaixaMovimento": "50.00", "valorDinheiro": "0", "valorCartao": "50.00",
            "planoContaCodigo": 5, "descricaoHistorico": "Pago sem dinheiro do caixa",
        },
        {
            "empresaCodigo": 999, "caixaMovimentoCodigo": 3, "tipo": "D",
            "valorCaixaMovimento": "5.00", "valorDinheiro": "5.00", "planoContaCodigo": 5,
            "descricaoHistorico": "Outro",
        },
    ]

    async def responder(request):
        assert request.url.path == "/INTEGRACAO/V1/MOVIMENTACOES_CAIXA"
        assert request.url.params["caixaCodigo"] == "10"
        assert request.url.params.get_list("tipo") == ["D"]
        return httpx.Response(200, json={"ultimoCodigo": None, "resultados": linhas})

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder), base_url="https://teste") as client:
        despesas = await buscar_despesas(unidade(), {10}, client=client)
    assert len(despesas) == 1
    assert despesas[0].codigo == 1
    assert despesas[0].plano_conta_codigo is None
    assert despesas[0].descricao == "Lanche"
