import json
from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from src.jobs import lancar_cartao
from src.modules.cash_reconciliation.application import piloto_cartao as piloto
from src.modules.cash_reconciliation.adapters import webposto_escrita_cartao as escrita

from .test_cartoes import C, DIA
from .test_piloto_cartao import caso, erp, confirmar, proposta


def reservar_incerto(erp):
    piloto._registrar(erp.proposta, "reservado", "diretor", erp.diretorio, antes=["1000", "500"])
    piloto._registrar(erp.proposta, "incerto", "diretor", erp.diretorio)


async def resolver(erp):
    return await piloto.resolver(
        74014, DIA, erp.proposta.nsu, autor="diretor:comando", diretorio=erp.diretorio,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 500])
async def test_erro_http_preserva_status_etapa_resposta_sem_chave(erp, status):
    erp.erro_post = status
    with pytest.raises(piloto.PilotoErro) as exc:
        await confirmar(erp)
    h = piloto.historico(74014, DIA, diretorio=erp.diretorio)[-1]
    assert h["estado"] == "incerto" and h["tipo_erro"] == "WebPostoErro"
    assert h["status_http"] == status and h["etapa"] == "envio"
    assert "[omitido]" in h["mensagem_erro"]
    assert "CHAVE-NAO-REAL" not in json.dumps(h)
    assert str(status) in str(exc.value)
    if status in (401, 403):
        assert "Quality" in str(exc.value)
    with pytest.raises(piloto.PilotoErro, match="não conferida"):
        await confirmar(erp)
    assert erp.requests == ["POST"]


@pytest.mark.asyncio
@pytest.mark.parametrize("erro,etapa,texto", [
    (httpx.ReadTimeout("sem retorno"), "envio", "sem resposta do webPosto"),
    (httpx.ConnectError("rede"), "envio", "sem resposta do webPosto"),
    (escrita.BarreiraCartaoErro("Escrita bloqueada pelas travas"), "travas", "travas desligadas"),
    (OSError("disco indisponível"), "envio", "conferir na tela"),
])
async def test_motivo_falha_envio_ou_trava_tardia(erp, monkeypatch, erro, etapa, texto):
    monkeypatch.setattr(escrita, "incluir_cartao", AsyncMock(side_effect=erro))
    with pytest.raises(piloto.PilotoErro, match=texto):
        await confirmar(erp)
    h = piloto.historico(74014, DIA, diretorio=erp.diretorio)[-1]
    assert h["tipo_erro"] == type(erro).__name__
    assert h["status_http"] is None and h["etapa"] == etapa
    assert h["mensagem_erro"]
    assert not erp.requests


@pytest.mark.asyncio
async def test_falha_conferencia_http_registra_motivo_e_nao_exclui(erp, monkeypatch):
    consultar = AsyncMock(side_effect=[[], piloto.WebPostoErro("sem acesso", status_http=403)])
    monkeypatch.setattr(piloto, "_cartoes", consultar)
    with pytest.raises(piloto.PilotoErro, match="Quality"):
        await confirmar(erp)
    falhas = [e for e in piloto.historico(74014, DIA, diretorio=erp.diretorio)
              if e["estado"] in {"incerto", "falha_conferencia"}]
    assert len(falhas) == 2
    assert all(e["status_http"] == 403 and e["etapa"] == "conferência" for e in falhas)
    assert erp.requests == ["POST"]


@pytest.mark.asyncio
async def test_falha_conferencia_delta_e_desfazer_auditados(erp):
    erp.sem_delta = erp.erro_delete = True
    with pytest.raises(piloto.PilotoErro, match="NÃO CONSEGUI"):
        await confirmar(erp)
    eventos = piloto.historico(74014, DIA, diretorio=erp.diretorio)
    falha = next(e for e in eventos if e["estado"] == "falha_conferencia")
    assert falha["etapa"] == "conferência" and falha["mensagem_erro"]
    assert eventos[-1]["etapa"] == "desfazer" and eventos[-1]["status_http"] == 500


@pytest.mark.asyncio
async def test_resolver_nao_entrou_com_travas_zero_sem_porta_escrita(erp, monkeypatch):
    reservar_incerto(erp)
    erp.env.write_text("WEBPOSTO_WRITES=0\nLOGOS_ERP_ESCRITA=0\n", encoding="utf-8")
    incluir = AsyncMock(side_effect=AssertionError("Resolver nunca inclui"))
    excluir = AsyncMock(side_effect=AssertionError("Resolver nunca exclui"))
    monkeypatch.setattr(escrita, "incluir_cartao", incluir)
    monkeypatch.setattr(escrita, "excluir_cartao", excluir)
    resultado = await resolver(erp)
    assert resultado["estado"] == "nao_entrou"
    assert "iguais aos de antes" in resultado["mensagem"]
    assert "Nenhum lançamento realizado" in resultado["mensagem"]
    historico = piloto.historico(74014, DIA, diretorio=erp.diretorio)
    assert [e["estado"] for e in historico] == ["reservado", "incerto", "nao_entrou"]
    assert historico[-1]["autorizado_por"] == "diretor:comando"
    assert historico[-1]["antes"] == historico[-1]["depois"] == ["1000", "500"]
    assert not erp.requests
    incluir.assert_not_called()
    excluir.assert_not_called()
    with pytest.raises(piloto.PilotoErro, match="única operação pendente"):
        await resolver(erp)


@pytest.mark.asyncio
async def test_resolver_libera_bloqueio_dia_mas_nao_reenvia_mesmo_nsu(erp):
    reservar_incerto(erp)
    with pytest.raises(piloto.PilotoErro, match="não conferida"):
        await confirmar(erp)
    await resolver(erp)
    with pytest.raises(piloto.PilotoErro, match="já foi decidido ou tentado"):
        await confirmar(erp)
    assert not erp.requests


@pytest.mark.asyncio
async def test_resolver_libera_outra_proposta_sem_enviar(erp, monkeypatch):
    reservar_incerto(erp)
    await resolver(erp)
    preparar = AsyncMock(side_effect=piloto.PilotoErro("prévia consultada"))
    monkeypatch.setattr(piloto, "preparar", preparar)
    with pytest.raises(piloto.PilotoErro, match="prévia consultada"):
        await piloto.confirmar(74014, DIA, "OUTRO-NSU", autor="diretor",
                               caminho_env=erp.env, diretorio=erp.diretorio)
    preparar.assert_awaited_once()
    assert not erp.requests


@pytest.mark.asyncio
async def test_resolver_uma_operacao_nao_libera_outra_incerta(erp):
    reservar_incerto(erp)
    outra = replace(erp.proposta, id="outra-acao", nsu="OUTRO-NSU",
                    payload={**erp.proposta.payload, "nsu": "OUTRO-NSU"})
    piloto._registrar(outra, "incerto", "diretor", erp.diretorio)
    await resolver(erp)
    with pytest.raises(piloto.PilotoErro, match="não conferida"):
        await confirmar(erp)
    assert not erp.requests


@pytest.mark.asyncio
async def test_resolver_entrou_nao_exclui_nem_libera_para_novo_envio(erp):
    reservar_incerto(erp)
    erp.cartoes = [C(901, "34.75", "11:26", nsu=erp.proposta.nsu)]
    erp.saldo = (Decimal("965.25"), Decimal("534.75"))
    resultado = await resolver(erp)
    assert resultado["estado"] == "entrou_sem_conferencia"
    assert "901" in resultado["mensagem"] and "diretor precisa conferir" in resultado["mensagem"]
    assert "Não excluí nem lancei nada" in resultado["mensagem"]
    assert not erp.requests
    with pytest.raises(piloto.PilotoErro, match="não conferida"):
        await confirmar(erp)


@pytest.mark.asyncio
async def test_resolver_sem_cartao_saldo_alterado_mantem_bloqueio(erp):
    reservar_incerto(erp)
    erp.saldo = (Decimal("999"), Decimal("500"))
    with pytest.raises(piloto.PilotoErro, match="saldos mudaram"):
        await resolver(erp)
    h = piloto.historico(74014, DIA, diretorio=erp.diretorio)[-1]
    assert h["estado"] == "incerto" and h["etapa"] == "conferência"
    with pytest.raises(piloto.PilotoErro, match="não conferida"):
        await confirmar(erp)
    assert not erp.requests


@pytest.mark.asyncio
async def test_resolver_sem_antes_nao_resolve_por_supor_zero(erp):
    piloto._registrar(erp.proposta, "incerto", "diretor", erp.diretorio)
    with pytest.raises(piloto.PilotoErro, match="sem saldos anteriores"):
        await resolver(erp)
    assert piloto.historico(74014, DIA, diretorio=erp.diretorio)[-1]["estado"] == "incerto"
    assert not erp.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("saldo", ["nao-numerico", "NaN", "Infinity"])
async def test_resolver_saldo_anterior_invalido_mantem_incerto(erp, saldo):
    piloto._registrar(erp.proposta, "incerto", "diretor", erp.diretorio, antes=[saldo, "500"])
    with pytest.raises(piloto.PilotoErro, match="bloqueio continua"):
        await resolver(erp)
    assert piloto.historico(74014, DIA, diretorio=erp.diretorio)[-1]["estado"] == "incerto"
    assert not erp.requests


@pytest.mark.asyncio
async def test_resolver_falha_get_registra_erro_sem_resolver(erp, monkeypatch):
    reservar_incerto(erp)
    monkeypatch.setattr(piloto, "_cartoes", AsyncMock(side_effect=httpx.ConnectTimeout("sem rede")))
    with pytest.raises(piloto.PilotoErro, match="sem resposta do webPosto"):
        await resolver(erp)
    h = piloto.historico(74014, DIA, diretorio=erp.diretorio)[-1]
    assert h["estado"] == "incerto" and h["tipo_erro"] == "ConnectTimeout"
    assert h["etapa"] == "conferência"
    assert not erp.requests


@pytest.mark.asyncio
async def test_cli_resolver_sem_lancar(erp, monkeypatch, capsys):
    reservar_incerto(erp)
    original = piloto.resolver
    async def resolver_local(unidade, dia, nsu, *, autor):
        return await original(unidade, dia, nsu, autor=autor, diretorio=erp.diretorio)
    monkeypatch.setattr(piloto, "resolver", resolver_local)
    monkeypatch.setattr(lancar_cartao, "load_dotenv", lambda *a: None)
    assert await lancar_cartao.executar_previa(74014, DIA, nsu=erp.proposta.nsu, resolver=True) == 0
    assert "não entrou no webPosto" in capsys.readouterr().out
    assert not erp.requests


@pytest.mark.asyncio
async def test_cli_modificadores_invalidos_nao_consultam(erp, monkeypatch):
    conferir = AsyncMock(side_effect=AssertionError("Não deve consultar"))
    monkeypatch.setattr(piloto, "resolver", conferir)
    assert await lancar_cartao.executar_previa(74014, DIA, resolver=True) == 1
    assert await lancar_cartao.executar_previa(74014, DIA, True, erp.proposta.nsu, True) == 1
    conferir.assert_not_called()


def test_sanitiza_credencial_url_encoded_e_chave_na_mensagem(monkeypatch):
    monkeypatch.setenv("WEBPOSTO_API_KEY_TESTE", "CHAVE SINTETICA")
    texto = escrita.mensagem_segura(
        "url?CHAVE=CHAVE+SINTETICA&token=valor-oculto x-api-key: outra-chave CHAVE%20SINTETICA "
        "Authorization: Bearer credencial-nao-carregada"
    )
    assert all(segredo not in texto for segredo in ("SINTETICA", "valor-oculto", "outra-chave", "credencial-nao-carregada"))
