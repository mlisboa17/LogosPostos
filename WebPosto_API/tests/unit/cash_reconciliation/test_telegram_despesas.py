"""Testes unitários offline para aprovação inteligente de despesas pelo Telegram (EXPENSE-02).

22 cenários obrigatórios:
1. Comprovante válido com todos os campos reconhecidos.
2. Empresa não identificada.
3. Fornecedor desconhecido.
4. Conta financeira indefinida.
5. Despesa ainda não paga.
6. Despesa já paga com evidência.
7. Título correspondente encontrado no ERP.
8. Possível duplicidade.
9. Documento duplicado (SHA-256).
10. Aprovação por usuário autorizado.
11. Aprovação por usuário não autorizado.
12. Callback repetido (replay).
13. Callback de versão antiga.
14. Duas decisões simultâneas (concorrência).
15. Correção de valor.
16. Correção de empresa.
17. Correção de classificação.
18. Rejeição.
19. Reinicialização do serviço.
20. Compatibilidade com itens antigos da fila.
21. Confirmação de aprovação sem escrita ERP.
22. Ausência de qualquer chamada externa real.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.modules.cash_reconciliation.adapters.extrato_reader import (
    ExtratoBancario,
    LancamentoBancario,
)
from src.modules.cash_reconciliation.adapters.gemini_comprovantes import GeminiExtractor
from src.modules.cash_reconciliation.adapters.telegram_despesas import (
    DespesaTelegramErro,
    atender_callback_despesa,
    conectar_banco,
    criar_ticket_proposta,
    montar_mensagem_proposta_telegram,
    montar_teclado_correcao,
    montar_teclado_proposta,
    processar_callback_despesa,
)
from src.modules.cash_reconciliation.application.fila_despesas import (
    TransicaoInvalidaErro,
    adicionar_item_fila,
    buscar_item_por_id,
    carregar_fila,
    salvar_fila,
    transicionar_status,
)
from src.modules.cash_reconciliation.application.processar_comprovante import (
    processar_comprovante_recebido,
)
from src.modules.cash_reconciliation.domain.comprovante import (
    DadosComprovante,
    ItemFilaDespesa,
    OperacaoFinanceira,
    StatusDespesa,
)
from src.modules.cash_reconciliation.domain.models import (
    ContaExtratoConfig,
    Destino,
    TipoDestino,
    Unidade,
)


@pytest.fixture
def unidade_doze() -> Unidade:
    return Unidade(
        empresa_codigo=74014,
        nome="POSTO DOZE FILIAL II",
        chave_env="CHAVE_DOZE",
        destinos=(
            Destino(
                conta_codigo=1, tipo=TipoDestino.DEPOSITO_DIRETO, banco="BB", conta_sufixo="4068-X"
            ),
        ),
        apelido="Doze",
        contas_extrato=(
            ContaExtratoConfig(banco="PAGBANK", conta_sufixo="9048-8", cd_conta=10),
            ContaExtratoConfig(banco="BB", conta_sufixo="4068-X", cd_conta=20),
        ),
    )


@pytest.fixture
def extrato_doze_pagbank() -> ExtratoBancario:
    return ExtratoBancario(
        banco="PAGBANK",
        agencia=None,
        conta_sufixo="9048-8",
        inicio=date(2026, 9, 1),
        fim=date(2026, 9, 30),
        sha256="fake-sha-pagbank",
        lancamentos=(
            LancamentoBancario(
                fitid="FIT-OFICINA-350",
                data=date(2026, 10, 17),
                momento=None,
                valor=Decimal("-350.00"),
                tipo="DEBITO",
                tipo_original="OUT",
                descricao="PIX TRANSF OFICINA ABC",
            ),
        ),
    )


@pytest.fixture
def auth_diretor() -> tuple[set[str], set[str]]:
    return {"123", "123456"}, {"123", "123456"}


# ---------------------------------------------------------------------------
# 1. Comprovante válido com todos os campos reconhecidos
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_01_comprovante_valido_todos_os_campos(
    tmp_path: Path, unidade_doze: Unidade, extrato_doze_pagbank: ExtratoBancario
):
    caminho_fila = tmp_path / "fila.json"
    pasta_comp = tmp_path / "comp"

    def mock_gemini(*args, **kwargs):
        return {
            "valor": 350.00,
            "data": "2026-10-17",
            "favorecido": "Oficina ABC",
            "tipo_comprovante": "PIX",
            "banco_origem": "PagBank",
        }

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"comprovante_valido_bytes",
        nome_arquivo="comp.pdf",
        mime_type="application/pdf",
        texto="Posto Doze manutencao piso",
        extratos=[extrato_doze_pagbank],
        unidades=[unidade_doze],
        gemini_extractor=GeminiExtractor(mock_fn=mock_gemini),
        caminho_fila=caminho_fila,
        pasta_comprovantes=pasta_comp,
    )

    assert item.status == StatusDespesa.AGUARDANDO_APROVACAO.value
    assert item.operacao_financeira == OperacaoFinanceira.DESPESA_JA_PAGA.value
    assert item.unidade_codigo == 74014
    assert item.unidade_apelido == "Doze"
    assert item.pode_ser_aprovado is True
    assert item.hash_conteudo == item.calcular_hash_conteudo()

    msg_telegram = montar_mensagem_proposta_telegram(item)
    assert "LOGOS — Despesa reconhecida" in msg_telegram
    assert "Empresa: Doze" in msg_telegram
    assert "Valor: R$ 350,00" in msg_telegram
    assert "Oficina ABC" in msg_telegram
    assert "preparar lançamento de débito em conta" in msg_telegram


# ---------------------------------------------------------------------------
# 2. Empresa não identificada (Bloqueio)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_02_empresa_nao_identificada(tmp_path: Path):
    caminho_fila = tmp_path / "fila.json"

    def mock_gemini(*args, **kwargs):
        return {"valor": 120.00, "data": "2026-10-17", "favorecido": "Loja Tintas"}

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"doc_sem_empresa",
        nome_arquivo="tintas.jpg",
        mime_type="image/jpeg",
        texto="pedreiro tinta",
        extratos=[],
        unidades=[],
        gemini_extractor=GeminiExtractor(mock_fn=mock_gemini),
        caminho_fila=caminho_fila,
    )

    assert item.unidade_codigo is None
    assert item.unidade_nome == "EMPRESA_INDEFINIDA"
    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value
    assert item.pode_ser_aprovado is False
    bloqueios = item.verificar_bloqueios_aprovacao()
    assert any("Empresa não identificada" in b for b in bloqueios)

    # Teclado omite Aprovar
    ticket = criar_ticket_proposta(item, banco=tmp_path / "telegram.sqlite3")
    teclado = montar_teclado_proposta(item, ticket)
    botoes_texto = [b["text"] for linha in teclado["inline_keyboard"] for b in linha]
    assert "✅ Aprovar" not in botoes_texto
    assert "✏️ Corrigir" in botoes_texto


# ---------------------------------------------------------------------------
# 3. Fornecedor desconhecido
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_03_fornecedor_desconhecido(tmp_path: Path, unidade_doze: Unidade):
    caminho_fila = tmp_path / "fila.json"

    def mock_gemini(*args, **kwargs):
        return {"valor": 50.00, "data": "2026-10-17", "favorecido": ""}

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"doc_sem_favorecido",
        nome_arquivo="comp.jpg",
        mime_type="image/jpeg",
        texto="Posto Doze lanche frentista",
        unidades=[unidade_doze],
        gemini_extractor=GeminiExtractor(mock_fn=mock_gemini),
        caminho_fila=caminho_fila,
    )

    msg = montar_mensagem_proposta_telegram(item)
    assert "Fornecedor: Não informado / Desconhecido" in msg
    assert "Fornecedor não identificado no cadastro" in msg


# ---------------------------------------------------------------------------
# 4. Conta financeira indefinida para operação de débito
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_04_conta_financeira_indefinida(tmp_path: Path, unidade_doze: Unidade):
    item = ItemFilaDespesa(
        id="item-sem-conta",
        criado_em="2026-10-17T10:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE FILIAL II",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        comprovante=DadosComprovante(valor=Decimal("200.00"), data=date(2026, 10, 17)),
        operacao_financeira=OperacaoFinanceira.DESPESA_JA_PAGA.value,
        debito_casado_fitid=None,
        comprovante_banco_origem="",
    )
    bloqueios = item.verificar_bloqueios_aprovacao()
    assert any("Pagamento não comprovado para operação de débito" in b for b in bloqueios)
    assert item.pode_ser_aprovado is False


# ---------------------------------------------------------------------------
# 5. Despesa ainda não paga (Boleto/Fatura)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_05_despesa_ainda_nao_paga(tmp_path: Path, unidade_doze: Unidade):
    caminho_fila = tmp_path / "fila.json"

    def mock_gemini(*args, **kwargs):
        return {
            "valor": 800.00,
            "data": "2026-10-17",
            "favorecido": "Distribuidora Energia",
            "tipo_comprovante": "Boleto",
        }

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"boleto_bytes",
        nome_arquivo="boleto_luz.pdf",
        mime_type="application/pdf",
        texto="Posto Doze conta de energia",
        unidades=[unidade_doze],
        gemini_extractor=GeminiExtractor(mock_fn=mock_gemini),
        caminho_fila=caminho_fila,
    )

    assert item.operacao_financeira == OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value
    msg = montar_mensagem_proposta_telegram(item)
    assert "Conta a pagar — pagamento não identificado" in msg
    assert "preparar conta a pagar no webPosto" in msg


# ---------------------------------------------------------------------------
# 6. Despesa já paga com evidência (Extrato Bancário)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_06_despesa_ja_paga_com_evidencia(
    tmp_path: Path, unidade_doze: Unidade, extrato_doze_pagbank: ExtratoBancario
):
    caminho_fila = tmp_path / "fila.json"

    def mock_gemini(*args, **kwargs):
        return {
            "valor": 350.00,
            "data": "2026-10-17",
            "favorecido": "Oficina ABC",
            "tipo_comprovante": "PIX",
        }

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"recibo_pix",
        nome_arquivo="recibo.jpg",
        mime_type="image/jpeg",
        texto="Posto Doze pedreiro",
        extratos=[extrato_doze_pagbank],
        unidades=[unidade_doze],
        gemini_extractor=GeminiExtractor(mock_fn=mock_gemini),
        caminho_fila=caminho_fila,
    )

    assert item.operacao_financeira == OperacaoFinanceira.DESPESA_JA_PAGA.value
    assert item.debito_casado_fitid == "FIT-OFICINA-350"
    msg = montar_mensagem_proposta_telegram(item)
    assert "Despesa quitada no banco — débito confirmado" in msg


# ---------------------------------------------------------------------------
# 7. Título correspondente encontrado no ERP
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_07_titulo_correspondente_encontrado_erp(tmp_path: Path, unidade_doze: Unidade):
    caminho_fila = tmp_path / "fila.json"

    class TituloAberto:
        valor = Decimal("450.00")
        numero = "TIT-991"

    def mock_gemini(*args, **kwargs):
        return {"valor": 450.00, "data": "2026-10-17", "favorecido": "Distribuidora"}

    item = await processar_comprovante_recebido(
        arquivo_bytes=b"comprovante_titulo",
        nome_arquivo="comp.pdf",
        mime_type="application/pdf",
        texto="Posto Doze pedreiro",
        titulos_abertos=[TituloAberto()],
        unidades=[unidade_doze],
        gemini_extractor=GeminiExtractor(mock_fn=mock_gemini),
        caminho_fila=caminho_fila,
    )

    assert item.operacao_financeira == OperacaoFinanceira.TITULO_EXISTENTE.value
    msg = montar_mensagem_proposta_telegram(item)
    assert "Título existente no webPosto — candidato a baixa" in msg
    assert "preparar baixa de título a pagar existente" in msg


# ---------------------------------------------------------------------------
# 8. Possível duplicidade (Arquivos diferentes, mesma despesa)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_08_possivel_duplicidade(tmp_path: Path, unidade_doze: Unidade):
    caminho_fila = tmp_path / "fila.json"

    # Salva item prévio na fila
    item_previo = ItemFilaDespesa(
        id="item-original",
        criado_em="2026-10-17T10:00:00",
        arquivo_sha256="sha-original-111",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        comprovante=DadosComprovante(
            valor=Decimal("300.00"), data=date(2026, 10, 17), favorecido="Manoel Pedreiro"
        ),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    salvar_fila([item_previo], caminho_fila)

    def mock_gemini(*args, **kwargs):
        return {"valor": 300.00, "data": "2026-10-17", "favorecido": "Manoel Pedreiro"}

    item_novo = await processar_comprovante_recebido(
        arquivo_bytes=b"arquivo_diferente_222",
        nome_arquivo="foto_mesa.jpg",
        mime_type="image/jpeg",
        texto="Posto Doze pedreiro",
        unidades=[unidade_doze],
        gemini_extractor=GeminiExtractor(mock_fn=mock_gemini),
        caminho_fila=caminho_fila,
    )

    assert item_novo.alerta_duplicidade is not None
    assert item_novo.operacao_financeira == OperacaoFinanceira.POSSIVEL_DUPLICIDADE.value
    assert item_novo.status == StatusDespesa.AGUARDANDO_REVISAO.value
    assert item_novo.pode_ser_aprovado is False


# ---------------------------------------------------------------------------
# 9. Documento duplicado (SHA-256)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_09_documento_duplicado_sha256(tmp_path: Path, unidade_doze: Unidade):
    caminho_fila = tmp_path / "fila.json"
    conteudo = b"mesmo_arquivo_exato_bytes"

    item_1 = await processar_comprovante_recebido(
        arquivo_bytes=conteudo,
        nome_arquivo="doc.pdf",
        mime_type="application/pdf",
        texto="Posto Doze pedreiro",
        unidades=[unidade_doze],
        gemini_extractor=GeminiExtractor(
            mock_fn=lambda *a, **k: {"valor": 100.00, "data": "2026-10-17"}
        ),
        caminho_fila=caminho_fila,
    )

    item_2 = await processar_comprovante_recebido(
        arquivo_bytes=conteudo,
        nome_arquivo="doc_copia.pdf",
        mime_type="application/pdf",
        texto="Posto Doze pedreiro",
        unidades=[unidade_doze],
        gemini_extractor=GeminiExtractor(
            mock_fn=lambda *a, **k: {"valor": 100.00, "data": "2026-10-17"}
        ),
        caminho_fila=caminho_fila,
    )

    assert item_2.duplicado_de_id == item_1.id
    itens = carregar_fila(caminho_fila)
    assert len(itens) == 1


# ---------------------------------------------------------------------------
# 10. Aprovação por usuário autorizado (Um toque)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_aprovacao_usuario_autorizado(
    tmp_path: Path, auth_diretor: tuple[set[str], set[str]]
):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-aprovavel",
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("500.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    item.hash_conteudo = item.calcular_hash_conteudo()
    salvar_fila([item], caminho_fila)

    ticket = criar_ticket_proposta(item, banco=banco)

    callback = {
        "id": "cb1",
        "data": f"desp:a:{ticket}",
        "message": {"chat": {"id": "123456", "type": "private"}, "message_id": 99},
        "from": {"id": "123456"},
    }

    res = await processar_callback_despesa(
        callback,
        banco=banco,
        caminho_fila=caminho_fila,
        diretores_autorizados=auth_diretor,
        usuario_override="123456",
    )

    assert res["sucesso"] is True
    assert "✅ Despesa aprovada com sucesso" in res["mensagem"]

    item_atualizado = buscar_item_por_id("item-aprovavel", caminho_fila)
    assert item_atualizado.status == StatusDespesa.APROVADO.value
    assert item_atualizado.aprovado_por == "diretor:123456"
    assert item_atualizado.aprovado_versao == 1
    assert item_atualizado.aprovado_hash == item.hash_conteudo


# ---------------------------------------------------------------------------
# 11. Aprovação por usuário não autorizado (Bloqueio estrito)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_aprovacao_usuario_nao_autorizado(tmp_path: Path):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-aprovavel",
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("500.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    # Invasor com chat_id e user_id 111111
    callback = {
        "id": "cb2",
        "data": f"desp:a:{ticket}",
        "message": {"chat": {"id": "111111", "type": "private"}, "message_id": 99},
        "from": {"id": "111111"},
    }

    with pytest.raises(DespesaTelegramErro, match="Aprovação permitida somente"):
        await processar_callback_despesa(
            callback,
            banco=banco,
            caminho_fila=caminho_fila,
            diretores_autorizados=({"999999"}, {"999999"}),
        )

    item_nao_mexido = buscar_item_por_id("item-aprovavel", caminho_fila)
    assert item_nao_mexido.status == StatusDespesa.AGUARDANDO_APROVACAO.value


@pytest.mark.asyncio
async def test_11b_aprovacao_bloqueada_sem_diretor_configurado(tmp_path: Path):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"
    item = ItemFilaDespesa(
        id="item-sem-diretor",
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("100.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)
    callback = {
        "id": "cb-sem-diretor",
        "data": f"desp:a:{ticket}",
        "message": {"chat": {"id": "123456", "type": "private"}, "message_id": 99},
        "from": {"id": "123456"},
    }

    with pytest.raises(DespesaTelegramErro, match="diretor autorizado não configurado"):
        await processar_callback_despesa(
            callback,
            banco=banco,
            caminho_fila=caminho_fila,
            diretores_autorizados=(set(), set()),
        )

    item_nao_mexido = buscar_item_por_id("item-sem-diretor", caminho_fila)
    assert item_nao_mexido.status == StatusDespesa.AGUARDANDO_APROVACAO.value


# ---------------------------------------------------------------------------
# 12. Callback repetido (Replay)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_12_callback_repetido(tmp_path: Path, auth_diretor: tuple[set[str], set[str]]):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-replay",
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("100.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    cb = {
        "id": "cb12",
        "data": f"desp:a:{ticket}",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }

    # Primeira aprovação: Sucesso
    await processar_callback_despesa(
        cb,
        banco=banco,
        caminho_fila=caminho_fila,
        diretores_autorizados=auth_diretor,
        usuario_override="123",
    )

    # Segunda aprovação com mesmo ticket: Rejeitado
    with pytest.raises(DespesaTelegramErro, match="Esta proposta já foi decidida"):
        await processar_callback_despesa(
            cb,
            banco=banco,
            caminho_fila=caminho_fila,
            diretores_autorizados=auth_diretor,
            usuario_override="123",
        )


# ---------------------------------------------------------------------------
# 13. Callback de versão antiga
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_callback_versao_antiga(tmp_path: Path, auth_diretor: tuple[set[str], set[str]]):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-v1",
        versao=1,
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("100.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket_v1 = criar_ticket_proposta(item, banco=banco)

    # Item é alterado e versão incrementada para 2
    item.versao = 2
    item.comprovante.valor = Decimal("150.00")
    salvar_fila([item], caminho_fila)

    cb = {
        "id": "cb13",
        "data": f"desp:a:{ticket_v1}",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }

    with pytest.raises(
        DespesaTelegramErro, match="Esta proposta foi alterada e requer nova conferência"
    ):
        await processar_callback_despesa(
            cb,
            banco=banco,
            caminho_fila=caminho_fila,
            diretores_autorizados=auth_diretor,
            usuario_override="123",
        )


# ---------------------------------------------------------------------------
# 14. Duas decisões simultâneas (Concorrência atômica)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_duas_decisoes_simultaneas(
    tmp_path: Path, auth_diretor: tuple[set[str], set[str]]
):
    banco = tmp_path / "telegram.sqlite3"
    conectar_banco(banco)

    # Simula ticket que já entrou em execução em outra thread/processo
    with conectar_banco(banco) as con:
        con.execute(
            "INSERT INTO propostas_despesas VALUES ('t-race', 'item-x', 1, 'h1', '2099-01-01', 'executando', '2026-10-17')"
        )

    cb = {
        "id": "cb14",
        "data": "desp:a:t-race",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }

    with pytest.raises(DespesaTelegramErro, match="Esta proposta já foi decidida"):
        await processar_callback_despesa(
            cb,
            banco=banco,
            caminho_fila=tmp_path / "fila.json",
            diretores_autorizados=auth_diretor,
            usuario_override="123",
        )


# ---------------------------------------------------------------------------
# 15. Correção de valor
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_15_correcao_valor(tmp_path: Path):
    caminho_fila = tmp_path / "fila.json"
    item = ItemFilaDespesa(
        id="item-valor",
        versao=1,
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        comprovante=DadosComprovante(valor=Decimal("100.00"), data=date(2026, 10, 17)),
    )
    salvar_fila([item], caminho_fila)

    hash_v1 = item.calcular_hash_conteudo()
    item.comprovante.valor = Decimal("125.50")
    item.versao += 1
    hash_v2 = item.calcular_hash_conteudo()

    assert item.versao == 2
    assert hash_v1 != hash_v2


# ---------------------------------------------------------------------------
# 16. Correção de empresa
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_correcao_empresa(tmp_path: Path, auth_diretor: tuple[set[str], set[str]]):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-corr-emp",
        versao=1,
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=None,
        unidade_nome="EMPRESA_INDEFINIDA",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("200.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_REVISAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    # Diretor seleciona Posto VIP (11495)
    cb = {
        "id": "cb16",
        "data": f"desp:u:{ticket}:11495",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }

    res = await processar_callback_despesa(
        cb,
        banco=banco,
        caminho_fila=caminho_fila,
        diretores_autorizados=auth_diretor,
        usuario_override="123",
    )
    assert res["sucesso"] is True
    assert "Proposta atualizada" in res["mensagem"]

    item_up = buscar_item_por_id("item-corr-emp", caminho_fila)
    assert item_up.unidade_codigo == 11495
    assert item_up.unidade_apelido == "VIP"
    assert item_up.versao == 2
    assert item_up.status == StatusDespesa.AGUARDANDO_APROVACAO.value


# ---------------------------------------------------------------------------
# 17. Correção de classificação
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_17_correcao_classificacao(tmp_path: Path, auth_diretor: tuple[set[str], set[str]]):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-corr-plano",
        versao=1,
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=None,
        sugestao_plano_nome="A CLASSIFICAR",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("150.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_REVISAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    # Diretor seleciona Fardas (29057)
    cb = {
        "id": "cb17",
        "data": f"desp:p:{ticket}:29057",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }

    res = await processar_callback_despesa(
        cb,
        banco=banco,
        caminho_fila=caminho_fila,
        diretores_autorizados=auth_diretor,
        usuario_override="123",
    )
    assert res["sucesso"] is True

    item_up = buscar_item_por_id("item-corr-plano", caminho_fila)
    assert item_up.sugestao_plano_codigo == 29057
    assert item_up.sugestao_plano_nome == "FARDAS E UNIFORMES"
    assert item_up.versao == 2


# ---------------------------------------------------------------------------
# 18. Rejeição
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_18_rejeicao(tmp_path: Path, auth_diretor: tuple[set[str], set[str]]):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-rejeitar",
        criado_em="2026-10-17T12:00:00",
        arquivo_comprovante="caminho/doc_original.pdf",
        unidade_codigo=74014,
        comprovante=DadosComprovante(valor=Decimal("90.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_REVISAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    cb = {
        "id": "cb18",
        "data": f"desp:r:{ticket}",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }

    res = await processar_callback_despesa(
        cb,
        banco=banco,
        caminho_fila=caminho_fila,
        diretores_autorizados=auth_diretor,
        usuario_override="123",
    )
    assert res["sucesso"] is True

    item_up = buscar_item_por_id("item-rejeitar", caminho_fila)
    assert item_up.status == StatusDespesa.REJEITADO.value
    assert item_up.arquivo_comprovante == "caminho/doc_original.pdf"
    assert len(item_up.historico_transicoes) >= 1


# ---------------------------------------------------------------------------
# 19. Reinicialização do serviço
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_19_reinicializacao_servico(tmp_path: Path, auth_diretor: tuple[set[str], set[str]]):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-persistente",
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("123.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    # Simula novo início / processo
    fila_recarregada = carregar_fila(caminho_fila)
    assert len(fila_recarregada) == 1

    cb = {
        "id": "cb19",
        "data": f"desp:a:{ticket}",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }
    res = await processar_callback_despesa(
        cb,
        banco=banco,
        caminho_fila=caminho_fila,
        diretores_autorizados=auth_diretor,
        usuario_override="123",
    )
    assert res["sucesso"] is True


# ---------------------------------------------------------------------------
# 20. Compatibilidade com itens antigos da fila
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_20_compatibilidade_itens_antigos_fila(tmp_path: Path):
    caminho_fila = tmp_path / "fila_antiga.json"
    dados_legados = [
        {
            "id": "legado-01",
            "criado_em": "2026-10-01T10:00:00",
            "status": "pronto para lançar",
            "comprovante": {"valor": 150.0},
        }
    ]
    caminho_fila.write_text(json.dumps(dados_legados), encoding="utf-8")

    itens = carregar_fila(caminho_fila)
    assert len(itens) == 1
    leg = itens[0]
    assert leg.versao == 1
    assert leg.operacao_financeira == OperacaoFinanceira.INDETERMINADO.value
    # Registros antigos NUNCA nascem aprovados retroativamente
    assert leg.status_canonico == StatusDespesa.AGUARDANDO_APROVACAO.value
    assert leg.aprovado_por is None


# ---------------------------------------------------------------------------
# 21. Confirmação de aprovação sem escrita ERP
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_21_confirmacao_aprovacao_sem_escrita_erp(
    tmp_path: Path, auth_diretor: tuple[set[str], set[str]]
):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-sem-escrita",
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("300.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    cb = {
        "id": "cb21",
        "data": f"desp:a:{ticket}",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }
    await processar_callback_despesa(
        cb,
        banco=banco,
        caminho_fila=caminho_fila,
        diretores_autorizados=auth_diretor,
        usuario_override="123",
    )

    item_aprovado = buscar_item_por_id("item-sem-escrita", caminho_fila)
    # Status é estritamente 'aprovado' (aguardando integração futura), NUNCA 'lancado_erp'
    assert item_aprovado.status == StatusDespesa.APROVADO.value
    assert item_aprovado.status != StatusDespesa.LANCADO_ERP.value


# ---------------------------------------------------------------------------
# 22. Ausência de qualquer chamada externa real (100% Offline)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_22_ausencia_chamadas_externas_reais(
    tmp_path: Path, monkeypatch, auth_diretor: tuple[set[str], set[str]]
):
    chamadas_feitas = []

    def mock_http_request(*args, **kwargs):
        chamadas_feitas.append((args, kwargs))
        raise RuntimeError("Chamada HTTP externa não permitida!")

    monkeypatch.setattr("httpx.Client.request", mock_http_request)
    monkeypatch.setattr("httpx.AsyncClient.request", mock_http_request)

    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-offline",
        criado_em="2026-10-17T12:00:00",
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE",
        unidade_apelido="Doze",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("250.00"), data=date(2026, 10, 17)),
        status=StatusDespesa.AGUARDANDO_APROVACAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    cb = {
        "id": "cb22",
        "data": f"desp:a:{ticket}",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }

    res = await processar_callback_despesa(
        cb,
        banco=banco,
        caminho_fila=caminho_fila,
        diretores_autorizados=auth_diretor,
        usuario_override="123",
    )
    assert res["sucesso"] is True
    assert len(chamadas_feitas) == 0  # 0 chamadas externas reais


# ---------------------------------------------------------------------------
# 23. Bloqueio de Posto Real (5558 / 7) e unidades inválidas no Telegram
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_23_bloqueio_posto_real_e_unidades_invalidas(
    tmp_path: Path, auth_diretor: tuple[set[str], set[str]]
):
    caminho_fila = tmp_path / "fila.json"
    banco = tmp_path / "telegram.sqlite3"

    item = ItemFilaDespesa(
        id="item-corr-real",
        versao=1,
        criado_em="2026-10-18T10:00:00",
        unidade_codigo=None,
        unidade_nome="EMPRESA_INDEFINIDA",
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        operacao_financeira=OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value,
        comprovante=DadosComprovante(valor=Decimal("200.00"), data=date(2026, 10, 18)),
        status=StatusDespesa.AGUARDANDO_REVISAO.value,
    )
    salvar_fila([item], caminho_fila)
    ticket = criar_ticket_proposta(item, banco=banco)

    # 1. Teclado de correção não inclui Posto Real
    teclado_corr = montar_teclado_correcao(item, ticket)
    botoes_flat = [b for linha in teclado_corr["inline_keyboard"] for b in linha]
    for b in botoes_flat:
        assert "Real" not in b["text"]
        assert "5558" not in b["text"]
        partes_cb = b["callback_data"].split(":")
        if len(partes_cb) >= 4 and partes_cb[1] == "u":
            assert partes_cb[3] not in ("5558", "7")

    # 2. Tentativa direta de callback com Posto Real (5558 ou 7) é bloqueada
    cb_5558 = {
        "id": "cb_5558",
        "data": f"desp:u:{ticket}:5558",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }
    with pytest.raises(
        DespesaTelegramErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        await processar_callback_despesa(
            cb_5558,
            banco=banco,
            caminho_fila=caminho_fila,
            diretores_autorizados=auth_diretor,
            usuario_override="123",
        )

    # 3. Código legado 7 também é bloqueado
    cb_7 = {
        "id": "cb_7",
        "data": f"desp:u:{ticket}:7",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }
    with pytest.raises(
        DespesaTelegramErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        await processar_callback_despesa(
            cb_7,
            banco=banco,
            caminho_fila=caminho_fila,
            diretores_autorizados=auth_diretor,
            usuario_override="123",
        )

    # 4. Códigos espúrios 12607 e 12705 continuam bloqueados
    cb_12607 = {
        "id": "cb_12607",
        "data": f"desp:u:{ticket}:12607",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }
    with pytest.raises(
        DespesaTelegramErro, match="Empresa 12607 não existe no cadastro oficial do webPosto"
    ):
        await processar_callback_despesa(
            cb_12607,
            banco=banco,
            caminho_fila=caminho_fila,
            diretores_autorizados=auth_diretor,
            usuario_override="123",
        )

    cb_12705 = {
        "id": "cb_12705",
        "data": f"desp:u:{ticket}:12705",
        "message": {"chat": {"id": "123", "type": "private"}},
        "from": {"id": "123"},
    }
    with pytest.raises(
        DespesaTelegramErro, match="Empresa 12705 não existe no cadastro oficial do webPosto"
    ):
        await processar_callback_despesa(
            cb_12705,
            banco=banco,
            caminho_fila=caminho_fila,
            diretores_autorizados=auth_diretor,
            usuario_override="123",
        )

    # 5. Bloqueio de aprovação no domínio se unidade for 5558
    item.unidade_codigo = 5558
    bloqueios = item.verificar_bloqueios_aprovacao()
    assert any("Posto Real (5558 / 7) não faz parte do escopo" in b for b in bloqueios)
    assert item.pode_ser_aprovado is False
