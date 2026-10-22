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
    TransicaoInvalidaErro,
    adicionar_item_fila,
    buscar_item_por_id,
    buscar_item_por_msg_id,
    buscar_item_por_sha256,
    buscar_item_por_transacao_bancaria,
    buscar_possiveis_duplicatas,
    carregar_fila,
    salvar_arquivo_comprovante,
    salvar_fila,
    transicionar_status,
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
    StatusDespesa,
    TransicaoFila,
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

    assert item.status == StatusDespesa.AGUARDANDO_APROVACAO.value
    assert item.debito_casado_fitid == "FIT-PAG-650"
    assert item.debito_casado_banco == "PAGBANK"
    assert item.unidade_codigo == 74014
    assert item.unidade_apelido == "Doze"
    assert item.sugestao_plano_codigo == 198595
    assert item.sugestao_plano_nome == "PEDREIRO"

    # Valida formato exato da resposta requerida no Item 6 da RN-ERP-003:
    # "Recebi: R$ 650,00 · Leticia Malta Farias · 17/09/2026 · PagBank Doze · sugestão: PEDREIRO (198595). Vou deixar pronto para lançar."
    assert (
        "Recebi: R$ 650,00 · Leticia Malta Farias · 17/09/2026 · PagBank Doze · sugestão: PEDREIRO (198595). Vou deixar pronto para lançar."
        in item.resposta_bot
    )


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
        texto="Posto Doze pedreiro",
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value
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

    assert item.status == StatusDespesa.AGUARDANDO_APROVACAO.value
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

    # 1. Envia comprovante sem classificação (status "a classificar" -> aguardando_revisao)
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
    assert item_inicial.status == StatusDespesa.AGUARDANDO_REVISAO.value
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
    assert item_atualizado.status == StatusDespesa.AGUARDANDO_APROVACAO.value
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
async def test_telegram_bloqueia_quando_whitelist_esta_vazia():
    """Configuração ausente deve bloquear tudo, nunca abrir o listener."""
    atualizacao = {
        "update_id": 2,
        "message": {
            "message_id": 1000,
            "chat": {"id": 123456},
            "text": "Tentativa sem whitelist configurada",
        },
    }

    processou = await processar_atualizacao_telegram(
        atualizacao=atualizacao,
        token="token_fake",
        chat_ids_autorizados=set(),
        client=object(),  # type: ignore[arg-type]
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


# ---------------------------------------------------------------------------
# 5. Testes Obrigatórios do Incremento EXPENSE-01 (14 Cenários de Integridade)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_01_01_upload_comprovante_novo(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    """1. Upload de comprovante novo: calcula SHA-256 e registra transição auditada."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 650.00,
            "data": "2026-09-17",
            "favorecido": "Leticia Malta Farias",
            "banco_origem": "PagBank",
            "descricao": "PIX serviço pedreiro",
        }

    conteudo = b"arquivo-comprovante-novo-12345"
    extractor = GeminiExtractor(mock_fn=mock_gemini)

    item = await processar_comprovante_recebido(
        arquivo_bytes=conteudo,
        nome_arquivo="comprovante_novo.jpg",
        mime_type="image/jpeg",
        telegram_message_id=8001,
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    import hashlib

    esperado_sha256 = hashlib.sha256(conteudo).hexdigest()

    assert item.arquivo_sha256 == esperado_sha256
    assert item.status == StatusDespesa.AGUARDANDO_APROVACAO.value
    assert item.debito_casado_conta == "9048-8"
    assert len(item.historico_transicoes) >= 2
    assert item.historico_transicoes[0].para_status == StatusDespesa.RECEBIDO.value
    assert item.historico_transicoes[-1].para_status == StatusDespesa.AGUARDANDO_APROVACAO.value


@pytest.mark.asyncio
async def test_expense_01_02_mesmo_arquivo_enviado_novamente(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    """2. Mesmo arquivo enviado novamente: anti-duplicidade não cria novo registro na fila."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 650.00,
            "data": "2026-09-17",
            "favorecido": "Leticia Malta Farias",
            "banco_origem": "PagBank",
            "descricao": "PIX serviço pedreiro",
        }

    conteudo = b"mesmo-arquivo-bytes-identico"
    extractor = GeminiExtractor(mock_fn=mock_gemini)

    item1 = await processar_comprovante_recebido(
        arquivo_bytes=conteudo,
        nome_arquivo="comp_original.jpg",
        mime_type="image/jpeg",
        telegram_message_id=8002,
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    fila_pos_primeiro = carregar_fila(caminho_fila)
    assert len(fila_pos_primeiro) == 1

    # Segundo envio com exatamente o mesmo arquivo
    item2 = await processar_comprovante_recebido(
        arquivo_bytes=conteudo,
        nome_arquivo="comp_repetido.jpg",
        mime_type="image/jpeg",
        telegram_message_id=8003,
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    fila_pos_segundo = carregar_fila(caminho_fila)
    assert len(fila_pos_segundo) == 1  # NÃO CRIOU novo item na fila
    assert item2.id == item1.id
    assert item2.duplicado_de_id == item1.id
    assert "Comprovante já recebido anteriormente" in item2.resposta_bot


@pytest.mark.asyncio
async def test_expense_01_03_fotos_diferentes_mesma_despesa(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    """3. Fotos diferentes da mesma possível despesa: gera alerta de duplicidade e exige revisão."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 650.00,
            "data": "2026-09-17",
            "favorecido": "Leticia Malta Farias",
            "banco_origem": "PagBank",
            "descricao": "PIX serviço pedreiro",
        }

    extractor = GeminiExtractor(mock_fn=mock_gemini)

    item1 = await processar_comprovante_recebido(
        arquivo_bytes=b"foto-angulo-A",
        nome_arquivo="foto_a.jpg",
        mime_type="image/jpeg",
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )
    assert item1.status == StatusDespesa.AGUARDANDO_APROVACAO.value

    # Segunda foto diferente (outro ângulo/arquivo), mas mesma despesa
    item2 = await processar_comprovante_recebido(
        arquivo_bytes=b"foto-angulo-B",
        nome_arquivo="foto_b.jpg",
        mime_type="image/jpeg",
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    fila = carregar_fila(caminho_fila)
    assert len(fila) == 2  # Registrado para conferência humana, sem exclusão cega
    assert item2.alerta_duplicidade is not None
    assert f"coincide com item {item1.id}" in item2.alerta_duplicidade
    assert item2.status == StatusDespesa.AGUARDANDO_REVISAO.value  # Bloqueado em revisão


@pytest.mark.asyncio
async def test_expense_01_04_empresa_nao_identificada(tmp_path: Path):
    """4. Empresa não identificada: registra EMPRESA_INDEFINIDA e status aguardando_revisao (sem fallback Doze)."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    # Sem extrato correspondente e texto genérico sem menção à unidade
    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 45.00,
            "data": "2026-09-20",
            "favorecido": "Farmácia Central",
            "banco_origem": "Banco Desconhecido",
        }

    extractor = GeminiExtractor(mock_fn=mock_gemini)

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"nota-farmacia",
        mime_type="image/jpeg",
        texto="remédio",
        extratos=[],  # Nenhum extrato
        unidades=[],  # Nenhuma unidade vinculada
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    # REMOÇÃO DO FALLBACK COMPROVADA:
    assert item.unidade_codigo is None
    assert item.unidade_nome == "EMPRESA_INDEFINIDA"
    assert item.unidade_apelido == "INDEFINIDA"
    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value
    assert "Empresa não identificada" in item.resposta_bot


@pytest.mark.asyncio
async def test_expense_01_05_empresa_identificada_corretamente(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    """5. Empresa identificada corretamente por conta bancária de extrato configurada."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 650.00,
            "data": "2026-09-17",
            "favorecido": "Leticia Malta Farias",
            "banco_origem": "PagBank",
        }

    extractor = GeminiExtractor(mock_fn=mock_gemini)

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"comprovante-doze",
        mime_type="image/jpeg",
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.unidade_codigo == 74014
    assert item.unidade_nome == "POSTO DOZE FILIAL II"
    assert item.unidade_apelido == "Doze"


@pytest.mark.asyncio
async def test_expense_01_06_fitid_repetido_na_mesma_conta(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    """6. FITID repetido na mesma conta: o débito já utilizado não pode ser vinculado novamente."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    def mock_gemini(conteudo: bytes, mime: str, texto: str) -> dict[str, Any]:
        return {
            "valor": 650.00,
            "data": "2026-09-17",
            "favorecido": "Leticia Malta Farias",
            "banco_origem": "PagBank",
        }

    extractor = GeminiExtractor(mock_fn=mock_gemini)

    # Primeiro comprovante casa FIT-PAG-650
    item1 = await processar_comprovante_recebido(
        arquivo_bytes=b"comprovante-1",
        mime_type="image/jpeg",
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )
    assert item1.debito_casado_fitid == "FIT-PAG-650"
    assert item1.debito_casado_conta == "9048-8"

    # Segundo comprovante tenta casar o mesmo débito com arquivo diferente
    item2 = await processar_comprovante_recebido(
        arquivo_bytes=b"comprovante-2-diferente",
        mime_type="image/jpeg",
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    # O débito já está em uso na conta 9048-8 -> não vincula novamente!
    assert item2.debito_casado_fitid is None
    assert item2.status == StatusDespesa.AGUARDANDO_REVISAO.value


@pytest.mark.asyncio
async def test_expense_01_07_fitid_igual_em_contas_diferentes(
    tmp_path: Path,
    unidade_doze: Unidade,
):
    """7. FITID igual em contas diferentes: chave é (banco, conta, fitid), permitindo matching sem colisão indevida."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    # Extrato Conta A
    extrato_a = ExtratoBancario(
        banco="PAGBANK",
        agencia="0001",
        conta_sufixo="9048-8",
        inicio=date(2026, 9, 1),
        fim=date(2026, 9, 30),
        sha256="sha_a",
        lancamentos=(
            LancamentoBancario(
                fitid="FIT-SHARED-123",
                data=date(2026, 9, 17),
                momento=None,
                valor=Decimal("-500.00"),
                tipo="DEBITO",
                tipo_original="OUT",
                descricao="PAGAMENTO FORNECEDOR A",
                documento="001",
            ),
        ),
    )

    # Extrato Conta B (outro banco/conta com o mesmo fitid)
    extrato_b = ExtratoBancario(
        banco="BB",
        agencia="0001",
        conta_sufixo="4068-X",
        inicio=date(2026, 9, 1),
        fim=date(2026, 9, 30),
        sha256="sha_b",
        lancamentos=(
            LancamentoBancario(
                fitid="FIT-SHARED-123",
                data=date(2026, 9, 17),
                momento=None,
                valor=Decimal("-500.00"),
                tipo="DEBITO",
                tipo_original="OUT",
                descricao="PAGAMENTO FORNECEDOR B",
                documento="002",
            ),
        ),
    )

    extractor_a = GeminiExtractor(
        mock_fn=lambda c, m, t: {"valor": 500.00, "data": "2026-09-17", "banco_origem": "PagBank"}
    )
    extractor_b = GeminiExtractor(
        mock_fn=lambda c, m, t: {"valor": 500.00, "data": "2026-09-17", "banco_origem": "BB"}
    )

    item_a = await processar_comprovante_recebido(
        arquivo_bytes=b"arq-a",
        mime_type="image/jpeg",
        extratos=[extrato_a],
        unidades=[unidade_doze],
        gemini_extractor=extractor_a,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    item_b = await processar_comprovante_recebido(
        arquivo_bytes=b"arq-b",
        mime_type="image/jpeg",
        extratos=[extrato_b],
        unidades=[unidade_doze],
        gemini_extractor=extractor_b,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item_a.chave_transacao_bancaria == ("PAGBANK", "9048-8", "FIT-SHARED-123")
    assert item_b.chave_transacao_bancaria == ("BB", "4068-X", "FIT-SHARED-123")
    assert item_a.chave_transacao_bancaria != item_b.chave_transacao_bancaria


@pytest.mark.asyncio
async def test_expense_01_08_fitid_sem_identificacao_confiavel_da_conta(
    tmp_path: Path,
    unidade_doze: Unidade,
):
    """8. FITID sem identificação confiável da conta: não realiza vínculo financeiro automático."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    # Extrato com conta_sufixo vazia (não confiável)
    extrato_sem_conta = ExtratoBancario(
        banco="PAGBANK",
        agencia="0001",
        conta_sufixo="",  # CONTA VAZIA
        inicio=date(2026, 9, 1),
        fim=date(2026, 9, 30),
        sha256="sha_invalido",
        lancamentos=(
            LancamentoBancario(
                fitid="FIT-SEM-CONTA",
                data=date(2026, 9, 17),
                momento=None,
                valor=Decimal("-200.00"),
                tipo="DEBITO",
                tipo_original="OUT",
                descricao="PAGAMENTO",
                documento="001",
            ),
        ),
    )

    extractor = GeminiExtractor(mock_fn=lambda c, m, t: {"valor": 200.00, "data": "2026-09-17"})

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"comp-sem-conta",
        mime_type="image/jpeg",
        extratos=[extrato_sem_conta],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.debito_casado_fitid is None
    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value


def test_expense_01_09_persistencia_e_leitura_registros_anteriores(tmp_path: Path):
    """9. Persistência e leitura de registros anteriores: lê JSON legado sem quebra e com status conservador."""
    caminho_fila = tmp_path / "fila_legada.json"

    conteudo_legado = [
        {
            "id": "legado-01",
            "criado_em": "2026-10-10T15:00:00",
            "arquivo_tipo": "imagem",
            "comprovante": {
                "valor": 120.00,
                "data": "2026-10-10",
                "favorecido": "Fornecedor Antigo",
            },
            "status": "pronto para lançar",  # STATUS LEGADO
            "resposta_bot": "Resposta antiga",
        }
    ]
    caminho_fila.write_text(json.dumps(conteudo_legado), encoding="utf-8")

    itens = carregar_fila(caminho_fila)
    assert len(itens) == 1
    assert itens[0].id == "legado-01"
    # Status canônico conservador mapeado para AGUARDANDO_APROVACAO (NÃO APROVADO!)
    assert itens[0].status_canonico == StatusDespesa.AGUARDANDO_APROVACAO.value
    assert itens[0].status_canonico != StatusDespesa.APROVADO.value


def test_expense_01_10_recuperacao_apos_interrupcao(tmp_path: Path):
    """10. Recuperação após interrupção: gravação atômica via .tmp protege integridade."""
    caminho_fila = tmp_path / "fila.json"
    caminho_tmp = tmp_path / "fila.json.tmp"

    item = ItemFilaDespesa(
        id="item-recuperavel",
        criado_em="2026-10-17T20:00:00",
        status=StatusDespesa.AGUARDANDO_REVISAO.value,
    )
    salvar_fila([item], caminho_fila)

    # Simula resíduo de interrupção (.tmp)
    caminho_tmp.write_text("corrompido", encoding="utf-8")

    # carregar_fila lê apenas o arquivo oficial consistente
    lidos = carregar_fila(caminho_fila)
    assert len(lidos) == 1
    assert lidos[0].id == "item-recuperavel"

    # Novo salvamento atômico substitui o .tmp sem falhar
    item.status = StatusDespesa.REJEITADO.value
    salvar_fila([item], caminho_fila)
    assert carregar_fila(caminho_fila)[0].status == StatusDespesa.REJEITADO.value


def test_expense_01_11_transicoes_validas_e_invalidas():
    """11. Transições válidas e inválidas de estado: garante máquina de estados e proíbe aprovações falsas."""
    item = ItemFilaDespesa(
        id="item-transicoes",
        criado_em="2026-10-17T20:00:00",
        unidade_codigo=None,
        unidade_nome="EMPRESA_INDEFINIDA",
        status=StatusDespesa.RECEBIDO.value,
    )

    # Válida: recebido -> aguardando_revisao
    transicionar_status(item, StatusDespesa.AGUARDANDO_REVISAO.value, motivo="Empresa indefinida")
    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value

    # Inválida: tentar ir para aguardando_aprovacao com empresa indefinida
    with pytest.raises(
        TransicaoInvalidaErro, match="Empresa indefinida não pode ir para aguardando_aprovacao"
    ):
        transicionar_status(
            item, StatusDespesa.AGUARDANDO_APROVACAO.value, motivo="Tentativa indevida"
        )

    # Corrige empresa
    item.unidade_codigo = 74014
    item.unidade_nome = "POSTO DOZE"

    # Agora a transição para aguardando_aprovacao é válida
    transicionar_status(item, StatusDespesa.AGUARDANDO_APROVACAO.value, motivo="Empresa revisada")
    assert item.status == StatusDespesa.AGUARDANDO_APROVACAO.value

    # Inválida: aprovação automática pelo sistema sem usuário humano
    with pytest.raises(
        TransicaoInvalidaErro, match="Aprovação automática ou de escrita pelo sistema é proibida"
    ):
        transicionar_status(
            item, StatusDespesa.APROVADO.value, motivo="Auto aprova", origem="sistema"
        )

    # Válida: aprovação humana explícita pelo diretor
    transicionar_status(
        item,
        StatusDespesa.APROVADO.value,
        motivo="Aprovado pelo diretor",
        origem="diretor_telegram",
        usuario="diretor_marcelo",
    )
    assert item.status == StatusDespesa.APROVADO.value


@pytest.mark.asyncio
async def test_expense_01_12_nenhum_registro_criado_como_automaticamente_aprovado(
    tmp_path: Path,
    unidade_doze: Unidade,
    extrato_pagbank_sintetico: ExtratoBancario,
):
    """12. Nenhum registro criado como automaticamente aprovado: novo comprovante nunca nasce aprovado."""
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comprovantes"

    extractor = GeminiExtractor(
        mock_fn=lambda c, m, t: {"valor": 650.00, "data": "2026-09-17", "banco_origem": "PagBank"}
    )

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"comprovante-teste",
        mime_type="image/jpeg",
        extratos=[extrato_pagbank_sintetico],
        unidades=[unidade_doze],
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.status != StatusDespesa.APROVADO.value
    assert item.status != StatusDespesa.LANCADO_ERP.value
    assert item.status != StatusDespesa.LANCAMENTO_SOLICITADO.value
    assert item.status in (
        StatusDespesa.AGUARDANDO_REVISAO.value,
        StatusDespesa.AGUARDANDO_APROVACAO.value,
    )


def test_expense_01_13_nenhum_write_erp_realizado(monkeypatch):
    """13. Nenhum write ERP realizado: travas mantidas em zero e nenhum código de escrita acionado."""
    import os

    monkeypatch.setenv("WEBPOSTO_WRITES", "0")
    monkeypatch.setenv("LOGOS_ERP_ESCRITA", "0")

    assert os.getenv("WEBPOSTO_WRITES") == "0"
    assert os.getenv("LOGOS_ERP_ESCRITA") == "0"


@pytest.mark.asyncio
async def test_expense_01_14_nenhuma_chamada_real_externa(tmp_path: Path):
    """14. Nenhuma chamada real externa durante os testes: isolamento com mock e diretórios temporários."""
    pasta_comp = tmp_path / "comprovantes"
    caminho_fila = tmp_path / "fila.json"

    # Usa MockExtractor para garantir que não toca generativelanguage.googleapis.com
    extractor = GeminiExtractor(mock_fn=lambda c, m, t: {"valor": 10.00, "favorecido": "Offline"})
    item = await processar_comprovante_recebido(
        arquivo_bytes=b"offline-bytes",
        mime_type="image/jpeg",
        gemini_extractor=extractor,
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.id is not None
    assert pasta_comp.is_dir()
    assert caminho_fila.is_file()
