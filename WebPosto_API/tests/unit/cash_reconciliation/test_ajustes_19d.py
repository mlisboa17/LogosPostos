from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.jobs import lancar_cartao
from src.modules.cash_reconciliation.application import piloto_cartao as piloto
from src.modules.cash_reconciliation.adapters import webposto_escrita_cartao as escrita
from .test_cartoes import DIA
from .test_piloto_cartao import caso, erp, confirmar, proposta
from .test_resolver_incerto import reservar_incerto, resolver


@pytest.mark.asyncio
async def test_retentativa_so_explicita_apos_resolver_preserva_limite_bruto(erp):
    reservar_incerto(erp)
    with pytest.raises(piloto.PilotoErro, match="não conferida"):
        await confirmar(erp, nova_tentativa=True)
    await resolver(erp)
    with pytest.raises(piloto.PilotoErro, match="não vou repetir"):
        await confirmar(erp)
    r = await confirmar(erp, nova_tentativa=True)
    assert r["estado"] == "confirmado" and erp.requests == ["POST"]
    h = piloto.historico(74014, DIA, diretorio=erp.diretorio)
    reservas = [e for e in h if e["estado"] == "reservado"]
    assert len(reservas) == 2 and reservas[0]["acao_id"] != reservas[1]["acao_id"]
    assert reservas[-1]["nova_tentativa"] is True
    assert reservas[-1]["tentativa_anterior"] == reservas[0]["acao_id"]
    assert piloto._total_dia(74014, DIA, erp.diretorio) == Decimal("69.50")
    with pytest.raises(piloto.PilotoErro, match="nao_entrou"):
        await confirmar(erp, nova_tentativa=True)
    assert erp.requests == ["POST"]


@pytest.mark.asyncio
async def test_flag_nao_pode_criar_primeira_tentativa(erp):
    with pytest.raises(piloto.PilotoErro, match="nao_entrou"):
        await confirmar(erp, nova_tentativa=True)
    assert not erp.requests


@pytest.mark.asyncio
async def test_retentativa_nao_burla_limite_nem_nsu_existente(erp):
    reservar_incerto(erp)
    await resolver(erp)
    from .test_cartoes import C
    erp.cartoes = [C(9, "34.75", "11:26", nsu=erp.proposta.nsu)]
    with pytest.raises(piloto.PilotoErro, match="já existe"):
        await confirmar(erp, nova_tentativa=True)
    assert not erp.requests


@pytest.mark.parametrize("bandeira", ["BACEN", "PIX"])
def test_pix_unico_pagbank_usa_mesma_venda_e_travas(caso, bandeira):
    caso.inv = caso.inv.model_copy(update={"transacao": caso.inv.transacao.model_copy(update={"bandeira": bandeira})})
    p = proposta(caso)
    assert not p.elegivel and "não há administradora de PIX PagBank cadastrada" in p.motivo
    caso.admins.append({"codigo": 302, "descricao": "PIX PAGBANK", "ativo": True})
    p = proposta(caso)
    assert p.elegivel and p.payload["administradoraCodigo"] == 302
    assert p.payload["vendaCodigo"] == 101
    assert "PIX da maquininha" in p.texto
    caso.admins.append({"codigo": 303, "descricao": "BACEN PAGSEGURO", "ativo": True})
    assert not proposta(caso).elegivel and "mais de uma" in proposta(caso).motivo


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmar_flag,resolver_flag,nsu", [(False, False, "teste"), (True, True, "teste"), (True, False, None)])
async def test_cli_flag_incompativel_nunca_chega_a_escrita(monkeypatch, confirmar_flag, resolver_flag, nsu):
    escrever = AsyncMock()
    monkeypatch.setattr(piloto, "confirmar", escrever)
    assert await lancar_cartao.executar_previa(74014, DIA, confirmar_flag, nsu, resolver_flag, True) == 1
    escrever.assert_not_called()
