from datetime import date
from decimal import Decimal

import httpx
import pytest

from src.modules.cash_reconciliation.adapters.webposto_sangrias import WebPostoErro, buscar_sangrias
from src.modules.cash_reconciliation.domain.models import Unidade

UNIDADE = Unidade(empresa_codigo=74014, nome="T", chave_env="TEST_CHAVE_UNIDADE", destinos=())


def _linha(cod, empresa=74014):
    return {"sangriaCodigo": cod, "empresaCodigo": empresa, "caixaCodigo": 1, "contaCodigo": None,
            "funcionarioCodigo": 2, "dinheiro": 10.5, "dataSangria": "2026-09-01", "horaSangria": "06:01:25",
            "alterada": False}


async def test_pagina_por_cursor_e_filtra_unidade(monkeypatch):
    monkeypatch.setenv("TEST_CHAVE_UNIDADE", "segredo")
    chamadas = []

    def handler(req: httpx.Request) -> httpx.Response:
        chamadas.append(dict(req.url.params))
        if "ultimoCodigo" not in req.url.params:
            return httpx.Response(200, json={"ultimoCodigo": 2, "resultados": [_linha(1), _linha(2, empresa=118508)]})
        return httpx.Response(200, json={"ultimoCodigo": None, "resultados": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t") as c:
        r = await buscar_sangrias(UNIDADE, date(2026, 9, 1), date(2026, 9, 1), client=c)

    assert [s.codigo for s in r] == [1] and r[0].valor == Decimal("10.5")
    assert chamadas[0]["empresaCodigo"] == "74014" and chamadas[1]["ultimoCodigo"] == "2"


async def test_erro_nao_vaza_chave(monkeypatch):
    monkeypatch.setenv("TEST_CHAVE_UNIDADE", "segredo")
    handler = lambda req: httpx.Response(400, text=f"chave segredo invalida")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t") as c:
        with pytest.raises(WebPostoErro) as exc:
            await buscar_sangrias(UNIDADE, date(2026, 9, 1), date(2026, 9, 1), client=c)
    assert "segredo" not in str(exc.value)


async def test_sem_chave(monkeypatch):
    monkeypatch.delenv("TEST_CHAVE_UNIDADE", raising=False)
    with pytest.raises(WebPostoErro, match="TEST_CHAVE_UNIDADE"):
        await buscar_sangrias(UNIDADE, date(2026, 9, 1), date(2026, 9, 1))
