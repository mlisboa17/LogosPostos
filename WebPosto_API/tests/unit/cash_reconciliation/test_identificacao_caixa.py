from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.modules.cash_reconciliation.adapters.webposto_caixas import para_caixa
from src.modules.cash_reconciliation.application import piloto_cartao
from src.modules.cash_reconciliation.application.resumo_diario import identificar_caixa
from src.modules.cash_reconciliation.domain.fechamento import Caixa

from .test_piloto_cartao import caso, proposta


@pytest.fixture
def caixa():
    return Caixa(
        codigo=9876543, empresa_codigo=74014, data=date(2026, 10, 14),
        turno="1º TURNO", pdv_codigo=1, centro_custo=7295, funcionario_codigo=299246,
        abertura=datetime(2026, 10, 14, 3, 1, tzinfo=timezone.utc),
        fechamento=datetime(2026, 10, 15, 3, 2, tzinfo=timezone.utc),
        fechado=True, consolidado=False, bloqueado=False, apurado=Decimal("50016.49"),
    )


def test_formato_longo_exato_recife_sem_codigo(caixa):
    texto = identificar_caixa("Doze", caixa, [caixa], {299246: "WANDERSON DA SILVA"})
    assert texto == (
        "Doze · Pista — caixa de 14/10/2026, 1º turno, aberto por WANDERSON DA SILVA às 00:01 "
        "(fechado 00:02 de 15/10), apurado R$ 50.016,49 (único caixa do dia)"
    )
    assert str(caixa.codigo) not in texto and "caixaCodigo" not in texto


def test_formato_curto_exato(caixa):
    assert identificar_caixa("Doze", caixa, [caixa], {299246: "WANDERSON DA SILVA"}, curto=True) == (
        "Doze · Pista — 14/10, 1º turno (Wanderson, 00:01) (único caixa do dia)"
    )


@pytest.mark.parametrize("nome", [None, "", "   "])
@pytest.mark.parametrize("curto", [False, True])
def test_fallback_nome_ausente_ou_vazio(caixa, nome, curto):
    nomes = {299246: nome} if nome is not None else {}
    texto = identificar_caixa("Doze", caixa, [caixa], nomes, curto=curto)
    assert "funcionário 299246" in texto
    assert str(caixa.codigo) not in texto


def test_unico_considera_dia_setor_e_unidade(caixa):
    outros = [
        caixa.model_copy(update={"codigo": 2, "centro_custo": 21650}),
        caixa.model_copy(update={"codigo": 3, "data": date(2026, 10, 13)}),
        caixa.model_copy(update={"codigo": 4, "empresa_codigo": 5555}),
    ]
    assert "(único caixa do dia)" in identificar_caixa("Doze", caixa, [caixa, *outros])
    outro_turno = caixa.model_copy(update={"codigo": 5, "turno": "2"})
    assert "(único caixa do dia)" not in identificar_caixa("Doze", caixa, [caixa, outro_turno])
    assert "2º turno" in identificar_caixa("Doze", outro_turno, [caixa, outro_turno])


def test_caixa_aberto_apurado_ausente_nao_inventa_zero(caixa):
    aberto = caixa.model_copy(update={"fechamento": None, "fechado": False, "apurado": None})
    texto = identificar_caixa("Doze", aberto, [aberto])
    assert "(ainda aberto)" in texto and "apurado não informado" in texto
    assert "R$ 0,00" not in texto


def test_adapter_preserva_apurado_sem_confundir_ausencia_com_zero(caixa):
    linha = {
        "caixaCodigo": caixa.codigo, "empresaCodigo": caixa.empresa_codigo,
        "dataMovimento": "2026-10-14", "turno": "1", "pdvCodigo": 1,
        "centroCusto": 7295, "funcionarioCodigo": 299246,
        "abertura": "2026-10-14T00:01:00", "fechamento": "2026-10-15T00:02:00",
        "apurado": "50016.49",
    }
    assert para_caixa(linha).apurado == Decimal("50016.49")
    assert para_caixa({**linha, "apurado": 0}).apurado == 0
    linha.pop("apurado")
    assert para_caixa(linha).apurado is None


def test_saldos_ausentes_bloqueiam_proposta_sem_inventar_antes_depois(caso):
    p = piloto_cartao.avaliar(
        caso.unidade, caso.inv.transacao.momento.date(), caso.inv, venda=caso.venda,
        caixas=[caso.caixa], administradoras=caso.admins, total_dia=Decimal(0),
    )
    assert not p.elegivel and p.payload is None
    assert "não consegui consultar o dinheiro" in p.texto
    assert "Antes:" not in p.texto


def test_saldos_nao_alteram_identidade_da_proposta(caso):
    p = proposta(caso)
    q = piloto_cartao.avaliar(
        caso.unidade, p.dia, caso.inv, venda=caso.venda, caixas=[caso.caixa],
        administradoras=caso.admins, total_dia=Decimal(0),
        saldos=(Decimal("1000"), Decimal("500")),
    )
    assert p.id == q.id
    assert "Depois de lançar: dinheiro R$ 965,25 · cartão R$ 534,75." in q.texto


@pytest.mark.asyncio
async def test_historico_legado_sem_regravar_auditoria(caso, monkeypatch):
    monkeypatch.setattr(piloto_cartao, "carregar_unidades", lambda: {74014: caso.unidade})
    monkeypatch.setattr(piloto_cartao, "buscar_caixas", AsyncMock(return_value=[caso.caixa]))
    monkeypatch.setattr(piloto_cartao, "buscar_nomes_funcionarios", AsyncMock(return_value={7: "WANDERSON DA SILVA"}))
    antigo = "Doze · Pista (caixa 201)"
    evento = {
        "caixa": antigo, "texto": f"{antigo}, texto antigo.",
        "payload": {"caixaCodigo": 201}, "nsu": "NSU-INTEIRO",
    }
    publico = (await piloto_cartao.historico_publico(74014, caso.caixa.data, [evento]))[0]
    assert "201" not in publico["texto"] and "201" not in publico["caixa"]
    assert "WANDERSON DA SILVA" in publico["texto"]
    assert "payload" not in publico and "nsu" not in publico
    assert "Wanderson" in publico["caixa_curto"]
    assert evento["caixa"] == antigo and evento["payload"]["caixaCodigo"] == 201
