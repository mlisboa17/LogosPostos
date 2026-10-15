"""Testes unitários para recepção de comprovantes, fila local e extração Gemini (Parte B).

Todos os testes são estritamente sintéticos:
- Nenhuma chamada à API real do Telegram;
- Nenhuma chamada à API real do Google Gemini;
- Nenhuma gravação ou chamada ao webPosto.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.jobs.receber_comprovantes import (
    _obter_chat_ids_diretor,
    processar_atualizacao_telegram,
)
from src.modules.cash_reconciliation.adapters.extrato_reader import (
    ExtratoBancario,
    LancamentoBancario,
)
from src.modules.cash_reconciliation.adapters.gemini_comprovantes import (
    GeminiExtractor,
    _parse_data_segura,
    _parse_valor_seguro,
)
from src.modules.cash_reconciliation.application.fila_despesas import (
    adicionar_item_fila,
    buscar_item_por_id,
    buscar_item_por_msg_id,
    carregar_fila,
    salvar_arquivo_comprovante,
    salvar_fila,
)
from src.modules.cash_reconciliation.application.processar_comprovante import (
    formatar_valor_br,
    montar_resposta_bot,
    processar_comprovante_recebido,
    sugerir_classificacao,
)
from src.modules.cash_reconciliation.domain.comprovante import (
    DadosComprovante,
    ItemFilaDespesa,
)
from src.modules.cash_reconciliation.domain.models import (
    ContaExtratoConfig,
    Destino,
    TipoDestino,
    Unidade,
)


# ---------------------------------------------------------------------------
# Fixtures e helpers sintéticos
# ---------------------------------------------------------------------------

@pytest.fixture
def unidade_doze() -> Unidade:
    return Unidade(
        empresa_codigo=74014,
        nome="POSTO DOZE FILIAL II",
        chave_env="CHAVE_DOZE",
        destinos=(
            Destino(
                conta_codigo=1,
                tipo=TipoDestino.DEPOSITO_DIRETO,
                banco="BB",
                conta_sufixo="4068-X",
            ),
        ),
        apelido="Doze",
        contas_extrato=(
            ContaExtratoConfig(banco="PAGBANK", conta_sufixo="9048-8", cd_conta=10),
            ContaExtratoConfig(banco="BB", conta_sufixo="4068-X", cd_conta=20),
        ),
    )


@pytest.fixture
def extrato_pagbank_sintetico() -> ExtratoBancario:
    lancamentos = [
        LancamentoBancario(
            fitid="FIT-PAG-650",
            data=date(2026, 9, 17),
            momento=None,
            valor=Decimal("-650.00"),
            tipo="DEBITO",
            tipo_original="OUT",
            descricao="PIX TRANSF LETICIA MALTA FARIAS",
            documento="0001",
        ),
        LancamentoBancario(
            fitid="FIT-PAG-350",
            data=date(2026, 9, 18),
            momento=None,
            valor=Decimal("-350.00"),
            tipo="DEBITO",
            tipo_original="OUT",
            descricao="PIX TRANSF ANTONIO PEDREIRO",
            documento="0002",
        ),
        LancamentoBancario(
            fitid="FIT-PAG-100",
            data=date(2026, 9, 19),
            momento=None,
            valor=Decimal("-100.00"),
            tipo="DEBITO",
            tipo_original="OUT",
            descricao="PAGAMENTO LOJA DESCONHECIDA",
            documento="0003",
        ),
    ]
    return ExtratoBancario(
        banco="PAGBANK",
        agencia="0001",
        conta_sufixo="9048-8",
        inicio=date(2026, 9, 1),
        fim=date(2026, 9, 30),
        sha256="sintetico_sha256",
        lancamentos=tuple(lancamentos),
    )


# ---------------------------------------------------------------------------
# 1. Testes de Parsing e Validação de Dados (Pydantic / Helpers)
# ---------------------------------------------------------------------------

def test_parse_valor_seguro():
    assert _parse_valor_seguro("650.00") == Decimal("650.00")
    assert _parse_valor_seguro("R$ 1.250,50") == Decimal("1250.50")
    assert _parse_valor_seguro("350,00") == Decimal("350.00")
    assert _parse_valor_seguro(450) == Decimal("450")
    assert _parse_valor_seguro(None) is None
    assert _parse_valor_seguro("invalido") is None


def test_parse_data_segura():
    assert _parse_data_segura("2026-09-17") == date(2026, 9, 17)
    assert _parse_data_segura("17/09/2026") == date(2026, 9, 17)
    assert _parse_data_segura("invalid") is None
    assert _parse_data_segura(None) is None


def test_formatar_valor_br():
    assert formatar_valor_br(Decimal("650.00")) == "R$ 650,00"
    assert formatar_valor_br(Decimal("1234567.89")) == "R$ 1.234.567,89"
    assert formatar_valor_br(None) == "Valor não informado"


def test_sugerir_classificacao():
    # Pedreiro
    cod, nome, _, _, _ = sugerir_classificacao("paguei ao pedreiro", "Antonio")
    assert cod == 198595
    assert nome == "PEDREIRO"

    # Manutenção de piso
    cod, nome, _, _, _ = sugerir_classificacao("reparo do piso da pista", "")
    assert cod == 194968
    assert "PISO" in nome

    # Desconhecido -> A CLASSIFICAR
    cod, nome, _, _, _ = sugerir_classificacao("compra aleatoria", "Loja X")
    assert cod is None
    assert nome == "A CLASSIFICAR"


# ---------------------------------------------------------------------------
# 2. Testes de Persistência na Fila Local (fila.json)
# ---------------------------------------------------------------------------

def test_fila_despesas_crud(tmp_path: Path):
    caminho_fila = tmp_path / "despesas_avulsas" / "fila.json"

    # Fila vazia
    assert carregar_fila(caminho_fila) == []

    # Criar item
    item1 = ItemFilaDespesa(
        id="item-001",
        telegram_message_id=101,
        telegram_chat_id="123456",
        criado_em="2026-10-11T20:00:00",
        comprovante=DadosComprovante(
            valor=Decimal("650.00"),
            data=date(2026, 9, 17),
            favorecido="Leticia Malta Farias",
            banco_origem="PagBank",
        ),
        status="pronto para lançar",
    )
    adicionar_item_fila(item1, caminho_fila)

    itens = carregar_fila(caminho_fila)
    assert len(itens) == 1
    assert itens[0].id == "item-001"
    assert itens[0].comprovante.valor == Decimal("650.00")

    # Buscar por id e msg_id
    assert buscar_item_por_id("item-001", caminho_fila) is not None
    assert buscar_item_por_id("inexistente", caminho_fila) is None
    assert buscar_item_por_msg_id(101, caminho_fila) is not None
    assert buscar_item_por_msg_id(999, caminho_fila) is None

    # Atualização de item existente
    item1.status = "lançado"
    adicionar_item_fila(item1, caminho_fila)
    itens_atualizados = carregar_fila(caminho_fila)
    assert len(itens_atualizados) == 1
    assert itens_atualizados[0].status == "lançado"


def test_salvar_arquivo_comprovante(tmp_path: Path):
    pasta = tmp_path / "comprovantes"
    conteudo = b"fake-image-bytes"
    salvo = salvar_arquivo_comprovante("comp_123", conteudo, ".jpg", pasta_dest=pasta)
    assert salvo.is_file()
    assert salvo.read_bytes() == conteudo


# ---------------------------------------------------------------------------
# 3. Testes do Orquestrador de Processamento (processar_comprovante_recebido)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_processar_comprovante_com_debito_casado_e_classificacao(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    # Mock do extrator Gemini
    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 650.00,
            "data": "2026-09-17",
            "favorecido": "Leticia Malta Farias",
            "banco_origem": "PagBank",
            "descricao": "PIX serviço pedreiro",
        }

    extractor = GeminiExtractor(mock_fn=mock_gemini)

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"fake-pix-image",
        nome_arquivo="pix_leticia.jpg",
        mime_type="image/jpeg",
        texto="pago pedreiro",
        telegram_message_id=5001,
        telegram_chat_id="998877",
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.status == "pronto para lançar"
    assert item.debito_casado_fitid == "FIT-PAG-650"
    assert item.debito_casado_banco == "PAGBANK"
    assert item.unidade_codigo == 74014
    assert item.unidade_apelido == "Doze"
    assert item.sugestao_plano_codigo == 198595
    assert item.sugestao_plano_nome == "PEDREIRO"

    # Valida formato exato da resposta requerida no Item 6 da RN-ERP-003:
    # "Recebi: R$ 650,00 · Leticia Malta Farias · 17/09/2026 · PagBank Doze · sugestão: PEDREIRO (198595). Vou deixar pronto para lançar."
    assert "Recebi: R$ 650,00 · Leticia Malta Farias · 17/09/2026 · PagBank Doze · sugestão: PEDREIRO (198595). Vou deixar pronto para lançar." in item.resposta_bot


@pytest.mark.asyncio
async def test_processar_comprovante_sem_extrato_ainda(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    # Valor 999.00 não existe no extrato
    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 999.00,
            "data": "2026-09-25",
            "favorecido": "Fornecedor Inexistente",
            "banco_origem": "PagBank",
        }

    extractor = GeminiExtractor(mock_fn=mock_gemini)

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"fake-pdf",
        nome_arquivo="comprovante.pdf",
        mime_type="application/pdf",
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.status == "sem extrato ainda"
    assert item.debito_casado_fitid is None
    assert "Aguardando extrato bancário para casar o débito" in item.resposta_bot


@pytest.mark.asyncio
async def test_processar_audio_diretor_sozinho(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    def mock_gemini_audio(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "transcricao": "paguei 350 ao seu Antonio pedreiro pelo conserto do piso",
            "valor": 350.00,
            "favorecido": "Antonio pedreiro",
            "palavras_chave": ["pedreiro", "piso"],
        }

    extractor = GeminiExtractor(mock_fn=mock_gemini_audio)

    item = await processar_comprovante_recebido(
        audio_bytes=b"fake-ogg-voice",
        telegram_message_id=6001,
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.status == "pronto para lançar"
    assert item.comprovante.valor == Decimal("350.00")
    assert item.debito_casado_fitid == "FIT-PAG-350"
    assert item.sugestao_plano_codigo == 198595
    assert "350,00" in item.resposta_bot


@pytest.mark.asyncio
async def test_diretor_responde_comprovante_anterior_com_classificacao(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    # 1. Envia comprovante sem classificação (status "a classificar")
    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 100.00,
            "data": "2026-09-19",
            "favorecido": "Loja Desconhecida",
            "banco_origem": "PagBank",
        }

    extractor = GeminiExtractor(mock_fn=mock_gemini)

    item_inicial = await processar_comprovante_recebido(
        arquivo_bytes=b"fake-image",
        nome_arquivo="comp_100.jpg",
        mime_type="image/jpeg",
        telegram_message_id=7001,
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )
    assert item_inicial.status == "a classificar"
    assert item_inicial.debito_casado_fitid == "FIT-PAG-100"

    # 2. Diretor responde a mensagem 7001 no Telegram dizendo: "isso foi farda dos frentistas"
    item_atualizado = await processar_comprovante_recebido(
        texto="isso foi farda dos frentistas",
        telegram_message_id=7002,
        telegram_reply_to_message_id=7001,
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
    )

    assert item_atualizado.id == item_inicial.id
    assert item_atualizado.status == "pronto para lançar"
    assert item_atualizado.sugestao_plano_codigo == 29057
    assert item_atualizado.sugestao_plano_nome == "FARDAS E UNIFORMES"
    assert "Vou deixar pronto para lançar" in item_atualizado.resposta_bot


# ---------------------------------------------------------------------------
# 4. Testes do Listener do Telegram (Whitelist de Chat ID e Handlers)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_rejeita_chat_id_nao_autorizado(monkeypatch):
    """Mensagens enviadas de chats não autorizados são ignoradas imediatamente."""
    chat_ids_autorizados = {"123456"}

    atualizacao_estranha = {
        "update_id": 1,
        "message": {
            "message_id": 999,
            "chat": {"id": 9999999},  # Chat não autorizado
            "text": "Tentativa de acesso",
        },
    }

    # Passa client mock
    class MockClient:
        pass

    processou = await processar_atualizacao_telegram(
        atualizacao=atualizacao_estranha,
        token="token_fake",
        chat_ids_autorizados=chat_ids_autorizados,
        client=MockClient(),  # type: ignore
    )
    assert processou is False


@pytest.mark.asyncio
async def test_gemini_extractor_sem_chave(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    ext = GeminiExtractor(api_key="")
    with pytest.raises(ValueError, match="GEMINI_API_KEY não configurada"):
        await ext.extrair_comprovante(b"bytes", "image/jpeg")

    with pytest.raises(ValueError, match="GEMINI_API_KEY não configurada"):
        await ext.extrair_audio(b"bytes", "audio/ogg")


def test_gemini_normalizar_dados_comprovante_robusto():
    ext = GeminiExtractor(api_key="fake")
    dados = ext._normalizar_dados_comprovante(
        {
            "valor": "1.234,56",
            "data": "17/09/2026",
            "favorecido": "Leticia Malta",
            "banco_origem": "PagBank",
        },
        observacao="nota diretor",
    )
    assert dados.valor == Decimal("1234.56")
    assert dados.data == date(2026, 9, 17)
    assert dados.favorecido == "Leticia Malta"
    assert dados.observacao_diretor == "nota diretor"


def test_listar_fila_stdout(capsys, tmp_path: Path, monkeypatch):
    from src.jobs.receber_comprovantes import listar_fila
    import src.jobs.receber_comprovantes as rc

    caminho = tmp_path / "fila.json"
    monkeypatch.setattr(rc, "carregar_fila", lambda: [])
    listar_fila()
    captured = capsys.readouterr().out
    assert "FILA LOCAL DE DESPESAS AVULSAS" in captured
    assert "A fila está vazia no momento" in captured


@pytest.mark.asyncio
async def test_processar_atualizacao_telegram_autorizado_com_foto(
    tmp_path: Path,
    monkeypatch,
):
    import src.jobs.receber_comprovantes as rc

    chat_id = "123456"
    chat_ids_autorizados = {chat_id}

    # Mock de download do arquivo do telegram
    async def mock_download(token, file_id, client):
        return b"fake-jpg-content", "comprovante.jpg"

    monkeypatch.setattr(rc, "_baixar_arquivo_telegram", mock_download)

    # Mock de envio de mensagem telegram
    mensagens_enviadas = []
    def mock_enviar(msg, token, chat_ids):
        mensagens_enviadas.append((msg, chat_ids))

    monkeypatch.setattr(rc, "enviar_mensagem", mock_enviar)

    # Mock do processador
    async def mock_proc(**kwargs):
        return ItemFilaDespesa(
            id="item-mock-1",
            criado_em="2026-10-11T20:00:00",
            status="pronto para lançar",
            resposta_bot="Recebi: R$ 650,00 · Leticia · 17/09/2026 · PagBank Doze",
        )

    monkeypatch.setattr(rc, "processar_comprovante_recebido", mock_proc)

    atualizacao = {
        "update_id": 2,
        "message": {
            "message_id": 888,
            "chat": {"id": 123456},
            "photo": [{"file_id": "small_id"}, {"file_id": "big_id"}],
            "caption": "paguei pedreiro",
        },
    }

    class MockClient:
        pass

    processou = await processar_atualizacao_telegram(
        atualizacao=atualizacao,
        token="fake-token",
        chat_ids_autorizados=chat_ids_autorizados,
        client=MockClient(),  # type: ignore
    )
    assert processou is True
    assert len(mensagens_enviadas) == 1
    assert "Recebi: R$ 650,00" in mensagens_enviadas[0][0]
    assert mensagens_enviadas[0][1] == ["123456"]

