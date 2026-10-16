from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.modules.cash_reconciliation.application import mais_pagamentos as mais
from src.modules.cash_reconciliation.adapters import telegram_cartoes
from src.modules.cash_reconciliation.domain.tempo import agora
from .test_resumo_diario import _registro, _unidade
from .test_piloto_cartao import caso


def registro():
    r = _registro(alertas=())
    a = r.fechamento.caixas[0]
    return r.model_copy(update={"empresa_codigo": 74014, "fechamento": r.fechamento.model_copy(update={
        "caixas": (a.model_copy(update={"modalidades": (
            a.modalidades[0].model_copy(update={"modalidade": "transfBanc", "apurado": Decimal("10241.86")}),
            a.modalidades[0].model_copy(update={"modalidade": "transfDeb", "apurado": Decimal("999")}),
        )}),),
    })})


def total(dia):
    return mais.TotalMaisPagamentos(unidade=74014, dia=dia, total=Decimal("10741.86"), informado_em=agora())


def test_total_local_diferenca_e_sem_frentista_inventado():
    r = registro()
    dado = total(r.dia)
    caminho = mais.salvar(dado)
    assert caminho.is_file() and mais.carregar(74014, r.dia) == dado
    conf, partes = mais.comparar(r, _unidade("Doze"), dado)
    assert conf.diferenca == Decimal("500")
    assert len(partes) == 1 and partes[0].valor == Decimal("500")
    assert partes[0].fonte == "total informado pelo diretor"
    assert "frentista não identificado" in partes[0].descricao
    assert "MAIS PAGAMENTOS" in partes[0].correcao


def test_nao_reparte_total_em_varios_caixas():
    r = registro()
    r = r.model_copy(update={"fechamento": r.fechamento.model_copy(update={
        "caixas": (*r.fechamento.caixas, *r.fechamento.caixas),
    })})
    conf, partes = mais.comparar(r, _unidade("Doze"), total(r.dia))
    assert not partes and "não identifica o caixa" in conf.aviso


@pytest.mark.parametrize("valor", ["nan", "NaN", "-1,00", "100", "1.2,00", "1,001", "Infinity", ""])
def test_dinheiro_invalido(valor):
    with pytest.raises(ValueError):
        mais.ler_valor(valor)


def test_total_corrompido_e_escopo_errado():
    r = total(date(2026, 10, 14))
    p = mais.salvar(r)
    p.write_text('{"unidade":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="local inválido"):
        mais.carregar(r.unidade, r.dia)


def test_texto_telegram_e_detalhe_em_resposta():
    t = mais.interpretar("Mais Pagamentos Doze 14/10 10741,86", hoje=date(2026, 10, 15))
    mais.salvar(t)
    d = mais.interpretar("14/10 14:35 500,00", hoje=date(2026, 10, 15), unidade_contexto=74014)
    assert d.total == Decimal("10741.86") and d.pix[0].valor == 500
    assert d.pix[0].momento.hour == 14
    with pytest.raises(ValueError, match="unidade"):
        mais.interpretar("14/10 14:35 500,00", hoje=date(2026, 10, 15))


def test_detalhe_encontra_nome_codigo_venda_dinheiro(caso):
    r = registro()
    a = caso.inv.candidatos[0].abastecimento
    a = a.model_copy(update={"caixa_codigo": r.fechamento.caixas[0].caixa.codigo,
                             "momento": a.momento.replace(day=r.dia.day)})
    dado = total(r.dia).model_copy(update={"pix": (mais.PixInformado(momento=a.momento, valor=a.valor),)})
    conf, partes = mais.comparar(r, _unidade("Doze"), dado, [a], {a.venda_item_codigo})
    assert "Frentista Sintético (7)" in partes[0].correcao
    assert "venda 101" in partes[0].correcao
    assert sum(p.valor for p in partes) == conf.diferenca


@pytest.mark.asyncio
async def test_so_diretor_privado_aceita_total(monkeypatch):
    monkeypatch.setattr(telegram_cartoes, "diretor", lambda _: ("123", "123"))
    msg = {"text": "Mais Pagamentos Doze 14/10 10741,86",
           "chat": {"id": 123, "type": "group"}, "from": {"id": 123}}
    http = AsyncMock()
    assert not await telegram_cartoes.atender_mais_pagamentos(msg, token="fake", client=http)
    http.post.assert_not_called()
    with pytest.raises(ValueError, match="privada"):
        await telegram_cartoes.processar_mais_pagamentos(msg)
