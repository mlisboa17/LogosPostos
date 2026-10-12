"""Modelos de domínio para comprovantes recebidos e fila de despesas avulsas."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class DadosComprovante(BaseModel):
    """Dados extraídos de comprovante ou áudio do diretor."""

    valor: Decimal | None = None
    data: date | None = None
    data_hora_str: str = ""
    favorecido: str = ""
    cpf_cnpj: str = ""
    chave_pix: str = ""
    banco_origem: str = ""
    conta_origem: str = ""
    descricao: str = ""
    tipo_comprovante: str = ""  # "PIX", "Boleto", "TED", "Imposto", "Outros"
    observacao_diretor: str = ""


class ItemFilaDespesa(BaseModel):
    """Registro persistido na fila local data/despesas_avulsas/fila.json."""

    id: str
    telegram_message_id: int | None = None
    telegram_chat_id: str | None = None
    criado_em: str  # ISO timestamp
    arquivo_comprovante: str | None = None
    arquivo_tipo: str = "imagem"  # "imagem", "pdf", "audio", "texto"
    comprovante: DadosComprovante = Field(default_factory=DadosComprovante)
    audio_ou_texto_complementar: str = ""

    # Dados do débito casado no extrato (Parte A)
    debito_casado_fitid: str | None = None
    debito_casado_banco: str | None = None
    debito_casado_data: str | None = None
    debito_casado_valor: Decimal | None = None
    debito_casado_descricao: str | None = None

    # Unidade dona da conta bancária
    unidade_codigo: int | None = None
    unidade_nome: str = ""
    unidade_apelido: str = ""

    # Sugestões de classificação para o ERP
    sugestao_plano_codigo: int | None = None
    sugestao_plano_nome: str = ""
    sugestao_centro_codigo: int | None = None
    sugestao_centro_nome: str = ""
    sugestao_fornecedor_codigo: int | None = None
    sugestao_fornecedor_nome: str = ""
    origem_sugestao: str = ""

    # Status: "pronto para lançar", "a classificar", "sem extrato ainda"
    status: str = "sem extrato ainda"

    # Resposta enviada ao bot Telegram
    resposta_bot: str = ""
