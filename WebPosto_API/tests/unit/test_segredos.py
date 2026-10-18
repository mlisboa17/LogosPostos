from datetime import date

import httpx
import pytest

from src.modules.cash_reconciliation.adapters import pagbank_edi
from src.modules.cash_reconciliation.adapters.pagbank_edi import PagBankCredencialInvalida
from src.modules.cash_reconciliation.config import carregar_unidades, definir_provedor_unidades
from src.modules.cash_reconciliation.domain.models import Unidade
from src.shared.segredos import definir_resolvedor, obter_segredo


def test_padrao_le_ambiente(monkeypatch):
    monkeypatch.setenv("X_TESTE", "  abc ")
    definir_resolvedor(None)
    assert obter_segredo("X_TESTE") == "abc"
    assert obter_segredo("NAO_EXISTE") == ""


def test_resolvedor_substitui_ambiente(monkeypatch):
    monkeypatch.setenv("X_TESTE", "do_env")
    definir_resolvedor(lambda n: "do_cofre" if n == "X_TESTE" else None)
    try:
        assert obter_segredo("X_TESTE") == "do_cofre"
        assert obter_segredo("OUTRO") == ""
    finally:
        definir_resolvedor(None)


def test_provedor_de_unidades():
    u = Unidade(empresa_codigo=-1, nome="TESTE", chave_env="LC_1_WEBPOSTO_CHAVE", destinos=())
    definir_provedor_unidades(lambda: {-1: u})
    try:
        assert carregar_unidades()[-1] is u
    finally:
        definir_provedor_unidades(None)
    assert 74014 in carregar_unidades()


async def test_pagbank_usa_resolvedor(monkeypatch):
    monkeypatch.setenv("PAGBANK_USER_74014", "u")
    monkeypatch.setenv("PAGBANK_TOKEN_74014", "t")
    definir_resolvedor(lambda n: None)
    try:
        with pytest.raises(PagBankCredencialInvalida):
            await pagbank_edi.buscar_transacoes(74014, date(2026, 10, 5), client=httpx.AsyncClient())
    finally:
        definir_resolvedor(None)
