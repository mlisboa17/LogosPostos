"""Testes unitários da porta de escrita de cartão (Sprint 18a).

Nenhum teste acessa o webPosto real.
Todas as validações de travas, schemas, resolução e auditoria são testadas isoladamente.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from src.modules.cash_reconciliation.adapters.webposto_escrita_cartao import (
    CAMPOS_PERMITIDOS_SPEC,
    BarreiraCartaoErro,
    excluir_cartao,
    gravar_auditoria,
    incluir_cartao,
    ler_auditoria,
    montar_payload_cartao,
    resolver_administradora_codigo,
    verificar_travas_cartao,
)
from src.modules.cash_reconciliation.domain.acoes_recebimentos import AcaoRecebimento
from src.modules.cash_reconciliation.domain.models import Unidade
from src.modules.cash_reconciliation.domain.tempo import agora
from src.jobs.lancar_cartao import executar_previa


@pytest.fixture
def fake_unidade() -> Unidade:
    return Unidade(
        empresa_codigo=5555,
        nome="AP CASA CAIADA",
        apelido="Casa Caiada",
        chave_env="WEBPOSTO_API_KEY_CASA_CAIADA",
        adquirentes=(),
        destinos=(),
    )


@pytest.fixture
def mock_administradoras() -> list[dict]:
    return [
        {"codigo": 46018, "descricao": "MASTERCARD", "tipo": "Crédito", "ativo": True},
        {"codigo": 46019, "descricao": "MAESTRO", "tipo": "Débito", "ativo": True},
        {"codigo": 46024, "descricao": "AMERICAN EXPRESS", "tipo": "Crédito", "ativo": True},
        {"codigo": 106902, "descricao": "VISA ELECTRON PAGSEGURO", "tipo": "Débito", "ativo": True},
        {"codigo": 106904, "descricao": "MASTERCARD PAGSEGURO", "tipo": "Crédito", "ativo": True},
        {"codigo": 106905, "descricao": "MAESTRO PAGSEGURO", "tipo": "Débito", "ativo": True},
        {"codigo": 106906, "descricao": "VISA CREDITO PAGSEGURO", "tipo": "Crédito", "ativo": True},
        {"codigo": 106907, "descricao": "ELO DEBITO PAGSEGURO", "tipo": "Débito", "ativo": True},
        {"codigo": 106908, "descricao": "ELO CREDITO PAGSEGURO", "tipo": "Crédito", "ativo": True},
    ]


# -----------------------------------------------------------------------------
# 1. TRAVAS DO ARQUIVO .ENV
# -----------------------------------------------------------------------------

def test_travas_leitura_exclusiva_arquivo_ignora_processo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prova que variáveis no processo NÃO liberam as travas se o arquivo .env estiver 0."""
    monkeypatch.setenv("WEBPOSTO_WRITES", "1")
    monkeypatch.setenv("LOGOS_ERP_ESCRITA", "1")

    env_file = tmp_path / ".env"
    env_file.write_text("WEBPOSTO_WRITES=0\nLOGOS_ERP_ESCRITA=0\n", encoding="utf-8")

    ok, motivo = verificar_travas_cartao(env_file)
    assert not ok
    assert "WEBPOSTO_WRITES != 1" in motivo


def test_travas_recusa_chave_duplicada(tmp_path: Path):
    """Prova que chaves duplicadas no .env recusam com as linhas exatas."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "WEBPOSTO_WRITES=1\nOUTRA_VAR=abc\nWEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n",
        encoding="utf-8",
    )

    ok, motivo = verificar_travas_cartao(env_file)
    assert not ok
    assert "trava duplicada no .env, linha 1 e 3" in motivo


def test_travas_liberadas_quando_ambas_1_no_arquivo(tmp_path: Path):
    """Travas liberadas apenas quando ambas forem estritamente '1' no arquivo."""
    env_file = tmp_path / ".env"
    env_file.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n", encoding="utf-8")

    ok, motivo = verificar_travas_cartao(env_file)
    assert ok
    assert "liberadas" in motivo


# -----------------------------------------------------------------------------
# 2. NENHUMA ESCRITA COM TRAVAS DESLIGADAS
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nenhuma_escrita_com_travas_desligadas(tmp_path: Path, fake_unidade: Unidade):
    """Nenhum HTTP request é emitido se as travas estiverem desligadas."""
    env_file = tmp_path / ".env"
    env_file.write_text("WEBPOSTO_WRITES=0\nLOGOS_ERP_ESCRITA=0\n", encoding="utf-8")

    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        return httpx.Response(200, json={"cartaoCodigo": 123})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    payload = {
        "vendaCodigo": 100,
        "clienteCodigo": None,
        "administradoraCodigo": 106904,
        "caixaCodigo": 200,
        "dataMovimento": "2026-10-10",
        "dataFiscal": "2026-10-10",
        "vencimento": "2026-10-10",
        "autorizacao": "AUTH123",
        "centroCustoCodigo": None,
        "valor": 50.0,
        "parcela": 1,
        "funcionarioCodigo": 300,
        "nsu": "12345678",
        "taxaPercentual": None,
        "valorTransacao": 50.0,
    }

    with pytest.raises(BarreiraCartaoErro) as exc:
        await incluir_cartao(
            fake_unidade,
            payload,
            acao_id="test_acao_1",
            evidencias=["evidencia_1"],
            autorizado_por="teste",
            caminho_env=env_file,
            client=mock_client,
        )

    assert "Escrita bloqueada pelas travas" in str(exc.value)
    assert len(chamadas) == 0, "Nenhuma chamada HTTP deveria ter sido disparada!"


@pytest.mark.asyncio
async def test_nenhuma_exclusao_com_travas_desligadas(tmp_path: Path, fake_unidade: Unidade):
    """Nenhum HTTP request de DELETE é emitido se as travas estiverem desligadas."""
    env_file = tmp_path / ".env"
    env_file.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=0\n", encoding="utf-8")

    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        return httpx.Response(204)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(BarreiraCartaoErro) as exc:
        await excluir_cartao(
            fake_unidade,
            cartao_id=999,
            caminho_env=env_file,
            client=mock_client,
        )

    assert "Exclusão bloqueada pelas travas" in str(exc.value)
    assert len(chamadas) == 0


# -----------------------------------------------------------------------------
# 3. SCHEMA ESTREITO DA SPEC OFICIAL (OPENAPI)
# -----------------------------------------------------------------------------

def test_montar_payload_estrito_campos_oficiais_openapi():
    """Monta payload contendo estritamente os campos de IncluirAlterarCartaoDto."""
    dados_proposta = {
        "nsu": "987654321",
        "autorizacao": "AUT_7788",
        "venda": 376701111,
        "caixa": 4462031,
        "frentista": 277311,
        "valor": "45.90",
        "momento": "2026-10-10T14:30:00-03:00",
    }

    payload = montar_payload_cartao(dados_proposta, administradora_codigo=106904)

    assert set(payload.keys()) == CAMPOS_PERMITIDOS_SPEC
    assert payload["vendaCodigo"] == 376701111
    assert payload["administradoraCodigo"] == 106904
    assert payload["caixaCodigo"] == 4462031
    assert payload["funcionarioCodigo"] == 277311
    assert payload["nsu"] == "987654321"
    assert payload["autorizacao"] == "AUT_7788"
    assert payload["valor"] == 45.90
    assert payload["valorTransacao"] == 45.90
    assert payload["dataMovimento"] == "2026-10-10"
    assert payload["dataFiscal"] == "2026-10-10"
    assert payload["vencimento"] == "2026-10-10"
    assert payload["parcela"] == 1
    assert payload["clienteCodigo"] is None
    assert payload["centroCustoCodigo"] is None
    assert payload["taxaPercentual"] is None


def test_montar_payload_com_objeto_acao_recebimento():
    """Funciona perfeitamente com instância de AcaoRecebimento."""
    acao = AcaoRecebimento(
        id="a" * 64,
        unidade=5555,
        grupo=2,
        motivo="Venda em dinheiro com pagamento eletrônico",
        valor=Decimal("34.75"),
        momento=agora(),
        adquirente="PAGBANK",
        forma="AMEX",
        nsu="12345678",
        autorizacao="998877",
        venda=123456,
        caixa=999888,
        frentista=555,
    )

    payload = montar_payload_cartao(acao, administradora_codigo=46024)
    assert payload["valor"] == 34.75
    assert payload["autorizacao"] == "998877"
    assert payload["nsu"] == "12345678"
    assert payload["vendaCodigo"] == 123456


# -----------------------------------------------------------------------------
# 4. PROPOSTA INCOMPLETA NÃO MONTA (RECUSA COM MOTIVO CLARO)
# -----------------------------------------------------------------------------

def test_montar_payload_recusa_nsu_mascarado_ou_ausente():
    """Recusa montar se NSU estiver mascarado (ex: …7008) ou ausente."""
    dados = {
        "nsu": "…7008",
        "autorizacao": "AUT_1",
        "venda": 1,
        "caixa": 1,
        "frentista": 1,
        "valor": 10,
        "momento": "2026-10-10",
    }
    with pytest.raises(BarreiraCartaoErro, match="NSU ausente ou mascarado"):
        montar_payload_cartao(dados, administradora_codigo=106904)


def test_montar_payload_recusa_autorizacao_ausente():
    """Recusa se código de autorização estiver ausente."""
    dados = {
        "nsu": "123456",
        "autorizacao": None,
        "venda": 1,
        "caixa": 1,
        "frentista": 1,
        "valor": 10,
        "momento": "2026-10-10",
    }
    with pytest.raises(BarreiraCartaoErro, match="Código de autorização ausente"):
        montar_payload_cartao(dados, administradora_codigo=106904)


def test_montar_payload_recusa_venda_ausente():
    """Recusa se código da venda estiver ausente."""
    dados = {
        "nsu": "123456",
        "autorizacao": "AUT",
        "venda": None,
        "caixa": 1,
        "frentista": 1,
        "valor": 10,
        "momento": "2026-10-10",
    }
    with pytest.raises(BarreiraCartaoErro, match="Código da venda ausente"):
        montar_payload_cartao(dados, administradora_codigo=106904)


def test_montar_payload_recusa_caixa_ausente():
    """Recusa se código do caixa estiver ausente."""
    dados = {
        "nsu": "123456",
        "autorizacao": "AUT",
        "venda": 100,
        "caixa": None,
        "frentista": 1,
        "valor": 10,
        "momento": "2026-10-10",
    }
    with pytest.raises(BarreiraCartaoErro, match="Código do caixa ausente"):
        montar_payload_cartao(dados, administradora_codigo=106904)


def test_montar_payload_recusa_frentista_ausente():
    """Recusa se frentista estiver ausente."""
    dados = {
        "nsu": "123456",
        "autorizacao": "AUT",
        "venda": 100,
        "caixa": 200,
        "frentista": None,
        "valor": 10,
        "momento": "2026-10-10",
    }
    with pytest.raises(BarreiraCartaoErro, match="Código do frentista ausente"):
        montar_payload_cartao(dados, administradora_codigo=106904)


def test_montar_payload_recusa_valor_invalido():
    """Recusa se valor for zero ou negativo."""
    dados = {
        "nsu": "123456",
        "autorizacao": "AUT",
        "venda": 100,
        "caixa": 200,
        "frentista": 300,
        "valor": 0,
        "momento": "2026-10-10",
    }
    with pytest.raises(BarreiraCartaoErro, match="Valor do lançamento deve ser maior que zero"):
        montar_payload_cartao(dados, administradora_codigo=106904)


# -----------------------------------------------------------------------------
# 5. RESOLUÇÃO DE ADMINISTRADORA E CASO AMEX
# -----------------------------------------------------------------------------

def test_resolver_administradora_amex_pagbank(mock_administradoras: list[dict]):
    """Em Casa Caiada (5555) e Doze (74014), Amex PagBank resolve para 'AMERICAN EXPRESS'."""
    cod = resolver_administradora_codigo(
        5555,
        "PAGBANK",
        "AMERICAN EXPRESS",
        mock_administradoras,
    )
    assert cod == 46024

    cod_amex = resolver_administradora_codigo(
        74014,
        "PAGBANK",
        "AMEX",
        mock_administradoras,
    )
    assert cod_amex == 46024


def test_resolver_administradora_pagbank_bandeiras(mock_administradoras: list[dict]):
    """Resolve corretamente Mastercard Crédito, Maestro, Elo Débito para PagBank."""
    cod_master = resolver_administradora_codigo(
        5555,
        "PAGBANK",
        "MASTERCARD CRÉDITO",
        mock_administradoras,
    )
    assert cod_master == 106904

    cod_maestro = resolver_administradora_codigo(
        5555,
        "PAGBANK",
        "MAESTRO",
        mock_administradoras,
    )
    assert cod_maestro == 106905

    cod_elo_deb = resolver_administradora_codigo(
        5555,
        "PAGBANK",
        "ELO DÉBITO",
        mock_administradoras,
    )
    assert cod_elo_deb == 106907


def test_resolver_administradora_ambigua_recusa():
    """Se mais de uma administradora coincidir, recusa sem adivinhar."""
    adms_ambiguas = [
        {"codigo": 101, "descricao": "MASTERCARD PAGSEGURO 1", "tipo": "Crédito", "ativo": True},
        {"codigo": 102, "descricao": "MASTERCARD PAGSEGURO 2", "tipo": "Crédito", "ativo": True},
    ]
    with pytest.raises(BarreiraCartaoErro, match="Administradora ambígua"):
        resolver_administradora_codigo(5555, "PAGBANK", "MASTERCARD CRÉDITO", adms_ambiguas)


def test_resolver_administradora_inexistente_recusa(mock_administradoras: list[dict]):
    """Se nenhuma administradora coincidir, recusa com erro explícito."""
    with pytest.raises(BarreiraCartaoErro, match="Nenhuma administradora encontrada"):
        resolver_administradora_codigo(5555, "CIELO", "BANDEIRA_INEXISTENTE", mock_administradoras)


# -----------------------------------------------------------------------------
# 6. AUDITORIA APPEND-ONLY
# -----------------------------------------------------------------------------

def test_auditoria_append_only_grava_e_le(tmp_path: Path):
    """Grava e lê múltiplos registros sintéticos na auditoria fora do Git."""
    registro1 = {
        "instante": agora().isoformat(),
        "o_que": "INCLUSAO_CARTAO",
        "acao_id": "acao_abc1",
        "motivo_inclusao": "Lançamento teste 1",
        "evidencias": ["ev1", "ev2"],
        "autorizado_por": "diretor",
        "payload": {"vendaCodigo": 101, "valor": 50.0},
        "resposta_erp": {"cartaoCodigo": 8001},
        "id_criado": 8001,
        "como_desfazer": "DELETE /INTEGRACAO/V1/CARTOES/8001",
    }
    registro2 = {
        "instante": agora().isoformat(),
        "o_que": "EXCLUSAO_CARTAO",
        "acao_id": "acao_abc1",
        "motivo_inclusao": "Desfazer teste 1",
        "evidencias": ["Desfazer exclusão"],
        "autorizado_por": "diretor",
        "payload": {"id": 8001},
        "resposta_erp": {"status_code": 204},
        "id_criado": None,
        "como_desfazer": "Exclusão já executada",
    }

    gravar_auditoria(5555, registro1, diretorio_base=tmp_path)
    gravar_auditoria(5555, registro2, diretorio_base=tmp_path)

    historico = ler_auditoria(5555, diretorio_base=tmp_path)
    assert len(historico) == 2
    assert historico[0]["id_criado"] == 8001
    assert historico[0]["o_que"] == "INCLUSAO_CARTAO"
    assert historico[1]["o_que"] == "EXCLUSAO_CARTAO"


# -----------------------------------------------------------------------------
# 7. PRÉVIA CLI E RECUSA DE --CONFIRMAR
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cli_lancar_cartao_recusa_confirmar(capsys: pytest.CaptureFixture):
    """Confirmar sem selecionar um único NSU não pode consultar ou escrever."""
    codigo = await executar_previa(5555, date(2026, 10, 10), confirmar=True)
    captured = capsys.readouterr()
    assert codigo == 1
    assert "--confirmar exige --nsu de UM cartão" in captured.out
