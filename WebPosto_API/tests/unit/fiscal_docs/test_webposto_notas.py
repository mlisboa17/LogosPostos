import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx
import pytest

from src.modules.fiscal_docs import webposto_notas as wn
from src.modules.webposto_integration.http import WebPostoErro

SEGREDO = "segredo123"
BASE = "https://wp.teste"


@dataclass(frozen=True)
class _Unidade:
    empresa_codigo: int = 74014
    chave_env: str = "TESTE_CHAVE"


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setenv("TESTE_CHAVE", SEGREDO)


def _cliente(tratar):
    return httpx.AsyncClient(base_url=BASE, transport=httpx.MockTransport(tratar))


def _rodar(coro_fn):
    async def _env():
        return await coro_fn()
    return asyncio.run(_env())


def _nota(codigo, chave):
    return {"codigo": codigo, "chaveDocumento": chave, "cnpjFornecedor": "11111111000191",
            "razaoSocialFornecedor": "DISTRIBUIDORA", "dataEmissao": "2026-09-10",
            "valor": 100.5, "tipoProduto": "Combustível", "recebido": True}


def test_listar_notas_pagina_por_ultimo_codigo():
    vistos = []

    def tratar(req):
        assert req.url.path == "/INTEGRACAO/V1/NOTAS_MANIFESTACAO"
        assert req.url.params["empresaCodigo"] == "74014"
        cursor = req.url.params.get("ultimoCodigo")
        vistos.append(cursor)
        if cursor is None:
            return httpx.Response(200, json={"ultimoCodigo": 2, "resultados": [_nota(1, "1" * 44), _nota(2, None)]})
        if cursor == "2":
            return httpx.Response(200, json={"ultimoCodigo": 3, "resultados": [_nota(3, "3" * 44)]})
        return httpx.Response(200, json={"ultimoCodigo": None, "resultados": []})

    async def go():
        async with _cliente(tratar) as c:
            return await wn.listar_notas(_Unidade(), date(2026, 9, 1), date(2026, 9, 30), client=c)

    notas = _rodar(go)
    assert [n.chave for n in notas] == ["1" * 44, "3" * 44]
    assert notas[0].valor == Decimal("100.5")
    assert notas[0].emissao == date(2026, 9, 10)
    assert notas[0].recebido is True
    assert vistos[:2] == [None, "2"]


def test_baixar_xml_ok_e_404():
    def tratar(req):
        if req.url.path.endswith("1" * 44):
            return httpx.Response(200, content=b'<?xml version="1.0"?><nfeProc/>',
                                  headers={"content-type": "application/xml"})
        return httpx.Response(404, text="XML não encontrado.")

    async def go():
        async with _cliente(tratar) as c:
            return (await wn.baixar_xml(_Unidade(), "1" * 44, client=c),
                    await wn.baixar_xml(_Unidade(), "2" * 44, client=c))

    ok, faltando = _rodar(go)
    assert ok.startswith(b"<?xml")
    assert faltando is None


def test_erro_nao_vaza_chave():
    def tratar(req):
        return httpx.Response(500, text=f"falha interna CHAVE={SEGREDO}")

    async def go():
        async with _cliente(tratar) as c:
            await wn.baixar_xml(_Unidade(), "1" * 44, client=c)

    with pytest.raises(WebPostoErro) as exc:
        _rodar(go)
    assert SEGREDO not in str(exc.value)


def test_listar_entradas_mapeia_frete_e_cte():
    def tratar(req):
        assert req.url.path == "/INTEGRACAO/V1/NOTAS_ENTRADA"
        return httpx.Response(200, json={"ultimoCodigo": None, "resultados": [
            {"codigo": 9, "chaveDocumento": "1" * 44, "tipoFrete": "F", "valorFrete": 350.0,
             "placaVeiculo": "ABC1D23", "placaReboque": None, "cteNumero": "998",
             "cteDataEmissao": "2026-09-09"},
            {"codigo": 10, "chaveDocumento": None}]})

    async def go():
        async with _cliente(tratar) as c:
            return await wn.listar_entradas(_Unidade(), date(2026, 9, 1), date(2026, 9, 30), client=c)

    e = _rodar(go)
    assert list(e) == ["1" * 44]
    x = e["1" * 44]
    assert (x.tipo_frete, x.valor_frete, x.placa, x.cte_numero) == ("F", Decimal("350.0"), "ABC1D23", "998")
    assert x.cte_emissao == date(2026, 9, 9)
