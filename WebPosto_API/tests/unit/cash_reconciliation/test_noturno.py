import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.modules.cash_reconciliation.adapters import persistencia
from src.modules.cash_reconciliation.domain.execucao import ResultadoDiario
from src.modules.cash_reconciliation.domain.models import AdquirenteConfigurada, Proveniencia, Unidade
from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente, ResultadoRecebimentos, ResumoCasados
from src.modules.cash_reconciliation.interfaces import http
from src.modules.cash_reconciliation.jobs import noturno

from .test_http import resultado_sintetico

DIA = date(2026, 10, 1)
EMPRESA = 321


@pytest.fixture(autouse=True)
def sem_postos_comerciais_reais(monkeypatch):
    monkeypatch.setattr(noturno, "POSTOS", {})


def unidade(empresa=EMPRESA):
    return Unidade(
        empresa_codigo=empresa, nome="Sintetica", chave_env="CHAVE_SINTETICA", destinos=(),
        adquirentes=(
            AdquirenteConfigurada(nome="PAGBANK", situacao="ativo", modalidades=("pix",)),
            AdquirenteConfigurada(nome="MAIS_PAGAMENTOS", situacao="pendente", modalidades=("pix",)),
        ),
    )


def diario(empresa=EMPRESA, dia=DIA, erro=None):
    fechamento = resultado_sintetico().model_copy(update={
        "empresa_codigo": empresa, "inicio": dia, "fim": dia,
        "caixas": resultado_sintetico().caixas if empresa == EMPRESA and dia == DIA else (),
    })
    return ResultadoDiario(
        empresa_codigo=empresa, dia=dia, fechamento=fechamento if erro is None else None,
        erro_fechamento=erro,
        recebimentos=ResultadoRecebimentos(
            empresa_codigo=empresa, dia=dia,
            adquirentes=(RecebimentoAdquirente(
                adquirente="PAGBANK", situacao="ok",
                casados=ResumoCasados(quantidade=1, total="10.15"),
                proveniencia=Proveniencia(
                    execucao_id="recebimento-sintetico", executado_em=datetime(2026, 10, 2, 3),
                    versao_regra="CARTOES_V1", fonte_sangrias="", extratos=(), outras_fontes=("sintetica",),
                ),
            ),),
        ),
        proveniencia=Proveniencia(
            execucao_id="execucao-sintetica", executado_em=datetime(2026, 10, 2, 3),
            versao_regra=noturno.VERSAO_JOB, fonte_sangrias="sintetica",
            extratos=(), outras_fontes=("sintetica",),
        ),
        versoes_regras=("FECHAMENTO_V2", "CARTOES_V1"),
    )


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(persistencia, "DIRETORIO", tmp_path)
    monkeypatch.setattr(http, "carregar_unidades", lambda: {EMPRESA: unidade()})
    app = FastAPI()
    app.include_router(http.router)
    with TestClient(app) as client:
        yield client


def test_persistencia_idempotente_e_sem_temporarios(tmp_path):
    primeiro = diario()
    caminho = persistencia.salvar_dia(primeiro, diretorio=tmp_path)
    assert caminho == tmp_path / DIA.isoformat() / f"{EMPRESA}.json"
    assert persistencia.carregar_dia(EMPRESA, DIA, diretorio=tmp_path) == primeiro
    segundo = diario(erro="falha ao consultar fechamento")
    persistencia.salvar_dia(segundo, diretorio=tmp_path)
    assert persistencia.carregar_dia(EMPRESA, DIA, diretorio=tmp_path) == segundo
    assert list(caminho.parent.iterdir()) == [caminho]
    assert persistencia.carregar_dia(999, DIA, diretorio=tmp_path) is None


def test_falha_atomica_preserva_resultado_anterior(monkeypatch, tmp_path):
    anterior = diario()
    persistencia.salvar_dia(anterior, diretorio=tmp_path)

    def falhar(*args):
        raise OSError("segredo")

    monkeypatch.setattr(persistencia.os, "replace", falhar)
    with pytest.raises(persistencia.PersistenciaErro, match="persistir"):
        persistencia.salvar_dia(diario(erro="falha"), diretorio=tmp_path)
    assert persistencia.carregar_dia(EMPRESA, DIA, diretorio=tmp_path) == anterior
    assert len(list((tmp_path / str(DIA)).iterdir())) == 1


@pytest.mark.parametrize("conteudo", ["corrompido segredo", '{"empresa_codigo":999}'])
def test_corrompido_nao_expoe_conteudo(tmp_path, caplog, conteudo):
    caminho = persistencia.caminho_dia(EMPRESA, DIA, tmp_path)
    caminho.parent.mkdir()
    caminho.write_text(conteudo, encoding="utf-8")
    with pytest.raises(persistencia.PersistenciaErro) as exc:
        persistencia.carregar_dia(EMPRESA, DIA, diretorio=tmp_path)
    assert "segredo" not in str(exc.value) + caplog.text


def test_arquivo_de_outro_tenant_rejeitado(tmp_path):
    caminho = persistencia.caminho_dia(EMPRESA, DIA, tmp_path)
    caminho.parent.mkdir()
    caminho.write_text(diario(999).model_dump_json(), encoding="utf-8")
    with pytest.raises(persistencia.PersistenciaErro):
        persistencia.carregar_dia(EMPRESA, DIA, diretorio=tmp_path)


def test_modelo_rejeita_escopo_interno_e_resultado_com_erro():
    dados = diario().model_dump()
    dados["recebimentos"]["empresa_codigo"] = 999
    with pytest.raises(ValidationError):
        ResultadoDiario.model_validate(dados)
    dados = diario().model_dump()
    dados["erro_fechamento"] = "erro"
    with pytest.raises(ValidationError):
        ResultadoDiario.model_validate(dados)


def test_rotas_usam_persistido_sem_rede(client, monkeypatch, tmp_path):
    persistencia.salvar_dia(diario(), diretorio=tmp_path)

    async def proibido(*args):
        pytest.fail("Registro persistido nao pode consultar rede.")

    monkeypatch.setattr(http, "auditar_unidade", proibido)
    monkeypatch.setattr(http, "conciliar_recebimentos", proibido)
    receb = client.get("/api/v1/cash-audit/recebimentos", params={"unidade": EMPRESA, "dia": DIA})
    assert receb.status_code == 200
    assert receb.json()["adquirentes"][0]["casados"]["quantidade"] == 1
    fechamento = client.get("/api/v1/cash-audit/fechamento", params={"unidade": EMPRESA, "inicio": DIA, "fim": DIA})
    assert fechamento.status_code == 200
    assert fechamento.json()["quebra_total"] == "2.50"
    assert fechamento.json()["caixas"][0]["severidade"] == "vermelho"
    assert fechamento.json()["execucoes"][0]["execucao_id"] == "execucao-sintetica"


def test_periodo_misto_consulta_so_dia_ausente(client, monkeypatch, tmp_path):
    persistencia.salvar_dia(diario(), diretorio=tmp_path)
    chamadas = []
    depois = DIA + timedelta(days=1)

    async def buscar(empresa, inicio, fim):
        chamadas.append((empresa, inicio, fim))
        return diario(dia=inicio).fechamento

    monkeypatch.setattr(http, "auditar_unidade", buscar)
    response = client.get(
        "/api/v1/cash-audit/fechamento",
        params={"unidade": EMPRESA, "inicio": DIA, "fim": depois},
    )
    assert response.status_code == 200
    assert chamadas == [(EMPRESA, depois, depois)]
    assert len(response.json()["execucoes"]) == 2


def test_erro_persistido_nao_consulta_ao_vivo(client, tmp_path):
    persistencia.salvar_dia(diario(erro="falha ao consultar fechamento"), diretorio=tmp_path)
    response = client.get("/api/v1/cash-audit/fechamento", params={"unidade": EMPRESA, "inicio": DIA, "fim": DIA})
    assert response.status_code == 502


@pytest.mark.parametrize("rota", ["recebimentos", "fechamento"])
def test_rota_cache_corrompido_retorna_500(client, tmp_path, rota):
    caminho = persistencia.caminho_dia(EMPRESA, DIA, tmp_path)
    caminho.parent.mkdir()
    caminho.write_text("segredo arquivo corrompido", encoding="utf-8")
    params = {"unidade": EMPRESA, "dia": DIA} if rota == "recebimentos" else {"unidade": EMPRESA, "inicio": DIA, "fim": DIA}
    response = client.get(f"/api/v1/cash-audit/{rota}", params=params)
    assert response.status_code == 500 and "segredo" not in response.text


async def test_job_isola_fechamento_e_persiste_demais_etapas(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("WEBPOSTO_WRITES", "0")
    monkeypatch.setattr(noturno, "carregar_unidades", lambda: {EMPRESA: unidade()})

    async def falhar(*args):
        raise RuntimeError("segredo CPF URL")

    async def recebimento(empresa, dia, conf, *, timeout):
        return RecebimentoAdquirente(adquirente=conf.nome, situacao="pendente")

    monkeypatch.setattr(noturno, "auditar_unidade", falhar)
    monkeypatch.setattr(noturno, "conciliar_adquirente", recebimento)
    assert await noturno.executar(DIA, diretorio=tmp_path) == 1
    registro = persistencia.carregar_dia(EMPRESA, DIA, diretorio=tmp_path)
    assert registro.erro_fechamento == "falha ao consultar fechamento"
    assert len(registro.recebimentos.adquirentes) == 2
    assert "segredo" not in registro.model_dump_json() + caplog.text


async def test_job_timeout_nao_impede_recebimentos(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBPOSTO_WRITES", "0")
    monkeypatch.setattr(noturno, "carregar_unidades", lambda: {EMPRESA: unidade()})

    async def lento(*args):
        await asyncio.sleep(1)

    async def recebimento(empresa, dia, conf, *, timeout):
        return RecebimentoAdquirente(adquirente=conf.nome, situacao="credencial inválida", erro="credencial inválida")

    monkeypatch.setattr(noturno, "auditar_unidade", lento)
    monkeypatch.setattr(noturno, "conciliar_adquirente", recebimento)
    assert await noturno.executar(DIA, diretorio=tmp_path, timeout=0.001) == 1
    registro = persistencia.carregar_dia(EMPRESA, DIA, diretorio=tmp_path)
    assert registro.erro_fechamento == "tempo limite excedido"
    assert len(registro.recebimentos.adquirentes) == 2


async def test_job_falha_de_unidade_nao_interrompe_outra(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBPOSTO_WRITES", "0")
    monkeypatch.setattr(noturno, "carregar_unidades", lambda: {321: unidade(321), 999: unidade(999)})

    async def coletar(unit, dia, execucao_id, *, timeout):
        if unit.empresa_codigo == 321:
            raise RuntimeError("segredo")
        return diario(999)

    monkeypatch.setattr(noturno, "coletar_unidade", coletar)
    assert await noturno.executar(DIA, diretorio=tmp_path) == 1
    assert persistencia.carregar_dia(999, DIA, diretorio=tmp_path) is not None


async def test_job_sem_somente_leitura_bloqueia(monkeypatch, tmp_path):
    monkeypatch.delenv("WEBPOSTO_WRITES", raising=False)
    assert await noturno.executar(DIA, diretorio=tmp_path) == 1
    assert not list(tmp_path.iterdir())


def test_dia_cli_formato_estrito():
    import argparse

    assert noturno._dia("2026-10-01") == DIA
    for valor in ("invalido", "20261001", "2026-02-30"):
        with pytest.raises(argparse.ArgumentTypeError):
            noturno._dia(valor)
