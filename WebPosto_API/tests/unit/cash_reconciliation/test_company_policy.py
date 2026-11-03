from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.interfaces.http.dependencies import get_current_user
from src.modules.cash_reconciliation.adapters import webposto_escrita_cartao as cartao
from src.modules.cash_reconciliation.adapters import webposto_escrita_despesa as despesa
from src.modules.cash_reconciliation.application import processar_comprovante as comprovantes
from src.modules.cash_reconciliation.application.classificar_recebimentos import montar_conferencia
from src.modules.cash_reconciliation.domain.comprovante import ItemFilaDespesa, StatusDespesa
from src.modules.cash_reconciliation.domain.fechamento import LinhaModalidade
from src.modules.cash_reconciliation.domain.models import Unidade
from src.modules.cash_reconciliation.interfaces import http
from .test_pendencias import criar_diario


@pytest.fixture(autouse=True)
def bloquear_rede(monkeypatch):
    def proibido(*args, **kwargs):
        pytest.fail("Acesso externo proibido neste teste.")

    monkeypatch.setattr(httpx.AsyncClient, "send", proibido)
    monkeypatch.setattr(http, "auditar_unidade", proibido)
    monkeypatch.setattr(http, "conciliar_recebimentos", proibido)


@pytest.mark.parametrize("codigo", [118508, 74014])
@pytest.mark.parametrize("com_master_data", [False, True])
def test_identidade_pendente_bloqueia_despesa_mesmo_sem_master_data(codigo, com_master_data):
    item = ItemFilaDespesa(
        id="pendente", criado_em="2026-11-02T10:00:00",
        unidade_codigo=codigo, status=StatusDespesa.APROVADO.value,
        aprovado_por="diretor",
    )
    service = Mock() if com_master_data else None
    with pytest.raises(despesa.BarreiraDespesaErro, match="identidade pendente"):
        despesa.validar_aprovacao_para_escrita(item, master_data_service=service)
    if service is not None:
        service.resolver_empresa.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("codigo", [118508, 74014, 46433, 5558])
@pytest.mark.parametrize("excluir", [False, True])
async def test_barreira_cartao_nao_usa_travas_como_autorizacao(codigo, excluir, monkeypatch):
    monkeypatch.setattr(cartao, "verificar_travas_cartao", lambda *args: (True, "teste"))
    unidade = Unidade(empresa_codigo=codigo, nome="Sintetica", chave_env="TESTE", destinos=())
    with pytest.raises(cartao.BarreiraCartaoErro, match="identidade pendente|fora do escopo"):
        if excluir:
            await cartao.excluir_cartao(unidade, 1)
        else:
            await cartao.incluir_cartao(
                unidade, {}, acao_id="teste", evidencias=(), autorizado_por="diretor",
            )


@pytest.mark.parametrize("codigo", [46433, 5558])
@pytest.mark.parametrize("papel,propria,status", [
    ("diretor", None, 200), ("auditor", None, 200),
    ("gerente", "mesma", 200), ("gerente", 5555, 403), ("invalido", None, 403),
])
@pytest.mark.parametrize("endpoint", [
    "fechamento", "recebimentos", "relatorio-caixa", "relatorio-caixa.xlsx",
    "reincidencia", "conferencia-recebimentos",
])
def test_historico_preserva_rbac_sem_configuracao_operacional(
    codigo, papel, propria, status, endpoint, monkeypatch,
):
    dia = date(2026, 10, 1)
    registro = criar_diario(dia, codigo)
    caixa = registro.fechamento.caixas[0].model_copy(update={"modalidades": (
        LinhaModalidade(
            modalidade="dinheiro", rotulo="Dinheiro",
            apresentado=Decimal("100"), apurado=Decimal("75"), diferenca=Decimal("-25"),
        ),
    )})
    registro = registro.model_copy(update={
        "fechamento": registro.fechamento.model_copy(update={"caixas": (caixa,)}),
    })
    monkeypatch.setattr(http, "carregar_dia", lambda *args: registro)
    monkeypatch.setattr(
        http, "conferencia_gravada",
        lambda *args: montar_conferencia(codigo, dia, dia, [registro]),
    )
    monkeypatch.setattr(http, "carregar_unidades_historicas", lambda: {})
    monkeypatch.setattr(http.saude_robo, "carregar_estado", lambda: None)
    monkeypatch.setattr(http, "conferencia_para_registro", lambda *args: None)
    monkeypatch.setattr(http, "_listar_pendencias_com_prazo", lambda **kwargs: [])
    monkeypatch.setattr(http, "_carregar_prazos_pendencia", lambda: {})
    monkeypatch.setattr(http, "planilha_relatorio_caixa_dia", lambda _: b"planilha-historica")

    def proibido():
        pytest.fail("Consulta historica tentou carregar escopo operacional.")

    monkeypatch.setattr(http, "carregar_unidades", proibido)
    app = FastAPI()
    app.include_router(http.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "teste", "role": papel,
        "company_id": codigo if propria == "mesma" else propria,
    }
    with TestClient(app) as client:
        response = client.get(f"/api/v1/cash-audit/{endpoint}", params={
            "unidade": codigo, "dia": dia.isoformat(),
            "inicio": dia.isoformat(), "fim": dia.isoformat(), "mes": "2026-10", "gravado": True,
        })
    assert response.status_code == status
    if status == 200:
        if endpoint == "relatorio-caixa.xlsx":
            assert response.content == b"planilha-historica"
        else:
            assert str(codigo) in response.text


@pytest.mark.parametrize("codigo", [46433, 5558])
def test_historico_ausente_nao_dispara_novo_processamento(codigo, monkeypatch):
    monkeypatch.setattr(http, "carregar_dia", lambda *args: None)
    app = FastAPI()
    app.include_router(http.router)
    app.dependency_overrides[get_current_user] = lambda: {"role": "diretor"}
    with TestClient(app) as client:
        response = client.get("/api/v1/cash-audit/fechamento", params={
            "unidade": codigo, "inicio": "2026-10-01", "fim": "2026-10-01",
            "gravado": True,
        })
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("codigo", [46433, 5558])
async def test_comprovante_rejeita_unidade_injetada_fora_do_escopo(codigo, tmp_path):
    unidade = Unidade(empresa_codigo=codigo, nome="Historica", chave_env="TESTE", destinos=())
    with pytest.raises(ValueError, match="fora do escopo"):
        await comprovantes.processar_comprovante_recebido(
            texto="teste", extratos=[], unidades=[unidade],
            caminho_fila=tmp_path / "fila.json", gemini_extractor=Mock(),
        )
    assert not (tmp_path / "fila.json").exists()


@pytest.mark.asyncio
async def test_falha_configuracao_comprovante_propaga_e_registra(tmp_path, monkeypatch, caplog):
    def falhar():
        raise ValueError("Configuracao invalida")

    monkeypatch.setattr(comprovantes, "carregar_unidades", falhar)
    with pytest.raises(ValueError, match="Configuracao invalida"):
        await comprovantes.processar_comprovante_recebido(
            texto="teste", extratos=[], caminho_fila=tmp_path / "fila.json",
            gemini_extractor=Mock(),
        )
    assert "Falha ao carregar" in caplog.text
    assert not (tmp_path / "fila.json").exists()


@pytest.mark.asyncio
async def test_comprovante_aceita_unidade_no_escopo_sem_apelido(tmp_path):
    unidade = Unidade(
        empresa_codigo=5555, nome="EMPRESA SINTETICA", chave_env="TESTE", destinos=(),
    )
    item = await comprovantes.processar_comprovante_recebido(
        texto="EMPRESA SINTETICA", extratos=[], unidades=[unidade],
        caminho_fila=tmp_path / "fila.json", gemini_extractor=Mock(),
    )
    assert item.unidade_codigo == 5555
    assert item.unidade_apelido == unidade.nome
    assert item.status != StatusDespesa.APROVADO.value
