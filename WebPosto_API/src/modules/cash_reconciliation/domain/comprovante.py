"""Modelos de domínio para comprovantes recebidos e fila de despesas avulsas."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StatusDespesa(str, Enum):
    """Estados canônicos da fila de despesas (ADR-003 / EXPENSE-01)."""

    RECEBIDO = "recebido"
    AGUARDANDO_REVISAO = "aguardando_revisao"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"
    APROVADO = "aprovado"
    REJEITADO = "rejeitado"
    LANCAMENTO_SOLICITADO = "lancamento_solicitado"
    LANCADO_ERP = "lancado_erp"
    FALHA = "falha"
    RESULTADO_DESCONHECIDO = "resultado_desconhecido"


class OperacaoFinanceira(str, Enum):
    """Classificação conceitual da despesa para orientação da integração ERP (EXPENSE-02)."""

    NOVA_CONTA_A_PAGAR = "NOVA_CONTA_A_PAGAR"  # Despesa existente, sem pagamento comprovado
    DESPESA_JA_PAGA = "DESPESA_JA_PAGA"  # Pagamento confirmado, sem lançamento no ERP
    TITULO_EXISTENTE = "TITULO_EXISTENTE"  # Obrigação já cadastrada no webPosto (baixa)
    POSSIVEL_DUPLICIDADE = "POSSIVEL_DUPLICIDADE"  # Documento ou operação semelhante
    INDETERMINADO = "INDETERMINADO"  # Evidência insuficiente


LEGACY_STATUS_MAP: dict[str, str] = {
    "sem extrato ainda": StatusDespesa.AGUARDANDO_REVISAO.value,
    "a classificar": StatusDespesa.AGUARDANDO_REVISAO.value,
    "pronto para lançar": StatusDespesa.AGUARDANDO_APROVACAO.value,
    "lançado": StatusDespesa.LANCADO_ERP.value,
}


class TransicaoFila(BaseModel):
    """Registro de auditoria para transições de estado na fila."""

    de_status: str
    para_status: str
    motivo: str
    origem: str = "sistema"  # "sistema", "diretor_telegram", "revisao_manual"
    timestamp: str  # ISO 8601
    usuario: str | None = None


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
    arquivo_sha256: str | None = None

    comprovante: DadosComprovante = Field(default_factory=DadosComprovante)
    audio_ou_texto_complementar: str = ""

    # Dados do débito casado no extrato (Parte A / EXPENSE-01)
    debito_casado_fitid: str | None = None
    debito_casado_banco: str | None = None
    debito_casado_conta: str | None = None
    debito_casado_data: str | None = None
    debito_casado_valor: Decimal | None = None
    debito_casado_descricao: str | None = None

    # Unidade dona da conta bancária (sem fallback para Doze)
    unidade_codigo: int | None = None
    unidade_nome: str = "EMPRESA_INDEFINIDA"
    unidade_apelido: str = "INDEFINIDA"

    # Sugestões de classificação para o ERP
    sugestao_plano_codigo: int | None = None
    sugestao_plano_nome: str = ""
    sugestao_centro_codigo: int | None = None
    sugestao_centro_nome: str = ""
    sugestao_fornecedor_codigo: int | None = None
    sugestao_fornecedor_nome: str = ""
    origem_sugestao: str = ""

    # Classificação da despesa e operação pretendida (EXPENSE-02)
    operacao_financeira: str = OperacaoFinanceira.INDETERMINADO.value
    versao: int = 1
    hash_conteudo: str = ""

    # Dados adicionais da proposta para conferência (EXPENSE-02 e EXPENSE-03)
    numero_documento: str = ""
    data_vencimento: date | None = None
    conta_financeira_nome: str = ""
    conta_financeira_codigo: int | None = None
    titulo_casado_codigo: int | None = None
    conferencias: list[str] = Field(default_factory=list)
    acao_sugerida: str = ""

    # Registro de aprovação auditada (EXPENSE-02)
    aprovado_por: str | None = None
    aprovado_em: str | None = None
    aprovado_versao: int | None = None
    aprovado_hash: str | None = None
    aprovado_operacao: str | None = None
    motivo_bloqueio: str | None = None
    motivo_rejeicao: str | None = None

    # Resultado da integração com o ERP (EXPENSE-03)
    resultado_erp_id: str | None = None
    resultado_erp_detalhes: dict[str, Any] = Field(default_factory=dict)

    # Status: novo ciclo de vida
    status: str = StatusDespesa.RECEBIDO.value
    historico_transicoes: list[TransicaoFila] = Field(default_factory=list)

    # Detecção e controle de duplicidade
    duplicado_de_id: str | None = None
    motivo_duplicidade: str | None = None
    alerta_duplicidade: str | None = None

    # Resposta enviada ao bot Telegram
    resposta_bot: str = ""

    @property
    def status_canonico(self) -> str:
        """Retorna o status canônico, mapeando valores legados se existirem."""
        return LEGACY_STATUS_MAP.get(self.status, self.status)

    @property
    def chave_transacao_bancaria(self) -> tuple[str, str, str] | None:
        """Chave unívoca da transação bancária (banco, conta, fitid)."""
        if self.debito_casado_banco and self.debito_casado_conta and self.debito_casado_fitid:
            return (
                self.debito_casado_banco.upper().strip(),
                self.debito_casado_conta.strip(),
                self.debito_casado_fitid.strip(),
            )
        return None

    def calcular_hash_conteudo(self) -> str:
        """Calcula o hash canônico SHA-256 (16 chars) do conteúdo da proposta."""
        payload = (
            f"{self.id}|{self.versao}|{self.unidade_codigo}|"
            f"{self.comprovante.valor}|{self.comprovante.data}|"
            f"{self.sugestao_plano_codigo}|{self.sugestao_centro_codigo}|"
            f"{self.sugestao_fornecedor_codigo}|"
            f"{self.operacao_financeira}|{self.debito_casado_fitid}|"
            f"{self.conta_financeira_codigo}|{self.titulo_casado_codigo}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def verificar_bloqueios_aprovacao(self) -> list[str]:
        """Retorna lista de motivos que bloqueiam a aprovação financeira."""
        bloqueios = []
        if self.unidade_codigo is None or self.unidade_nome == "EMPRESA_INDEFINIDA":
            bloqueios.append("Empresa não identificada.")
        if self.unidade_codigo in (5558, 7):
            bloqueios.append("Posto Real (5558 / 7) não faz parte do escopo do Expense Hunter.")
        if self.comprovante.valor is None:
            bloqueios.append("Valor da despesa não informado.")
        if self.alerta_duplicidade:
            bloqueios.append(f"Alerta de duplicidade ativo: {self.alerta_duplicidade}")
        if self.operacao_financeira == OperacaoFinanceira.INDETERMINADO.value:
            bloqueios.append("Operação financeira indeterminada (evidência insuficiente).")
        if self.operacao_financeira == OperacaoFinanceira.POSSIVEL_DUPLICIDADE.value:
            bloqueios.append("Possível duplicidade de documento/despesa detectada.")
        if not self.sugestao_plano_codigo or self.sugestao_plano_nome == "A CLASSIFICAR":
            bloqueios.append("Plano de contas pendente de classificação.")
        if self.operacao_financeira == OperacaoFinanceira.DESPESA_JA_PAGA.value:
            if not self.debito_casado_fitid and not self.comprovante.banco_origem:
                bloqueios.append("Pagamento não comprovado para operação de débito em conta.")
        return bloqueios

    @property
    def pode_ser_aprovado(self) -> bool:
        """Indica se a proposta está 100% elegível para aprovação com um toque."""
        return len(self.verificar_bloqueios_aprovacao()) == 0
