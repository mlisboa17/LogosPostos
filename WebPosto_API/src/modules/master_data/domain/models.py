"""Modelos de domínio do Cadastro Mestre Financeiro do LOGOS (MASTER-DATA-01).

Princípios:
- Tipagem estrita com Pydantic v2.
- Rastreabilidade de origem e nível de confiabilidade em todos os registros.
- Distinção explícita entre empresa, conta bancária, conta caixa/cofre e favorecido.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ConfiabilidadeCadastro(str, Enum):
    """Níveis de confiabilidade cadastral para auditoria e autorização."""
    CONFIRMADO = "CONFIRMADO"  # Comprovado por fonte oficial/contrato
    HISTORICO = "HISTORICO"    # Snapshot prévio do ERP
    INFERIDO = "INFERIDO"      # Sugestão derivada; NUNCA autoriza escrita
    PENDENTE = "PENDENTE"      # Dado ausente ou ambíguo; requer consulta/input


class TipoContaFinanceira(str, Enum):
    """Tipologia rigorosa de contas financeiras do grupo."""
    CONTA_CORRENTE = "CONTA_CORRENTE"  # Conta bancária movimentável
    CAIXA_FISICO = "CAIXA_FISICO"      # Caixa da pista / frente de caixa
    COFRE = "COFRE"                    # Cofre físico para sangrias
    ADQUIRENTE = "ADQUIRENTE"          # Conta transitória de cartões
    TRANSITORIA = "TRANSITORIA"        # Conta de repasse / ajuste interno
    OUTRO = "OUTRO"


class PapelEntidade(str, Enum):
    """Papel funcional da entidade nos lançamentos financeiros."""
    FORNECEDOR = "FORNECEDOR"                    # Titular de fornecimento cadastrado
    RECEBEDOR_BANCARIO = "RECEBEDOR_BANCARIO"    # Destinatário do pagamento PIX/TED
    BENEFICIARIO_ECONOMICO = "BENEFICIARIO_ECONOMICO"  # Quem usufruiu economicamente (ex: sócio)
    SOCIO = "SOCIO"                              # Titular societário / pró-labore
    EMPRESA_RELACIONADA = "EMPRESA_RELACIONADA"  # Outra empresa do grupo


class EstadoResolucaoConta(str, Enum):
    """Estados explícitos de resolução oficial de contas financeiras (MASTER-DATA-03)."""
    ACCOUNT_CONFIRMED = "ACCOUNT_CONFIRMED"
    ACCOUNT_NOT_FOUND = "ACCOUNT_NOT_FOUND"
    ACCOUNT_AMBIGUOUS = "ACCOUNT_AMBIGUOUS"
    ACCOUNT_OWNER_MISMATCH = "ACCOUNT_OWNER_MISMATCH"
    ACCOUNT_CODE_MISSING = "ACCOUNT_CODE_MISSING"
    ACCOUNT_PENDING_AUTHORIZATION = "ACCOUNT_PENDING_AUTHORIZATION"


class MasterEmpresa(BaseModel):
    """Cadastro mestre de empresa/filial do grupo LOGOS."""
    model_config = ConfigDict(frozen=True)

    empresa_codigo: int
    cod_web: Optional[int] = None
    razao_social: str
    nome_fantasia: str
    cnpj: str
    ativo: bool = True
    autorizado_despesa: bool = True
    usa_mais_pagamentos: bool = True
    conta_cofre_padrao: Optional[int] = None
    confiabilidade: ConfiabilidadeCadastro = ConfiabilidadeCadastro.CONFIRMADO
    origem_dado: str = "units.json"
    atualizado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MasterContaFinanceira(BaseModel):
    """Cadastro mestre de conta financeira do webPosto."""
    model_config = ConfigDict(frozen=True)

    conta_codigo: int
    empresa_codigo: Optional[int] = None  # None se for conta de uso compartilhado
    descricao: str
    tipo_conta: TipoContaFinanceira
    banco_codigo: Optional[str] = None
    banco_nome: Optional[str] = None
    agencia: Optional[str] = None
    conta_numero: Optional[str] = None
    ativo: bool = True
    permite_debito_despesa: bool = False  # True APENAS para conta corrente bancária validada
    confiabilidade: ConfiabilidadeCadastro = ConfiabilidadeCadastro.CONFIRMADO
    origem_dado: str = "webposto_network_probe"
    atualizado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MasterPlanoConta(BaseModel):
    """Cadastro mestre de plano de contas (DRE/Gerencial)."""
    model_config = ConfigDict(frozen=True)

    plano_conta_codigo: int
    descricao: str
    natureza: str = "DESPESA"  # DESPESA, CUSTO, RECEITA, etc.
    grupo: Optional[str] = None
    ativo: bool = True
    permite_despesa: bool = True
    confiabilidade: ConfiabilidadeCadastro = ConfiabilidadeCadastro.CONFIRMADO
    origem_dado: str = "account_category_mapping.json"
    atualizado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MasterCentroCusto(BaseModel):
    """Cadastro mestre de centro de custo do webPosto."""
    model_config = ConfigDict(frozen=True)

    centro_custo_codigo: int
    empresa_codigo: Optional[int] = None
    descricao: str
    tipo_abrangencia: str = "GERAL"  # PISTA, CONVENIENCIA, ADMINISTRATIVO, GERAL
    ativo: bool = True
    confiabilidade: ConfiabilidadeCadastro = ConfiabilidadeCadastro.CONFIRMADO
    origem_dado: str = "config_sistema"
    atualizado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MasterFornecedor(BaseModel):
    """Cadastro mestre de fornecedores e favorecidos."""
    model_config = ConfigDict(frozen=True)

    fornecedor_codigo: Optional[int] = None  # Código no webPosto, se existente
    empresa_codigo: Optional[int] = None
    razao_social: str
    nome_fantasia: Optional[str] = None
    cnpj_cpf: Optional[str] = None
    papel: PapelEntidade = PapelEntidade.FORNECEDOR
    ativo: bool = True
    confiabilidade: ConfiabilidadeCadastro = ConfiabilidadeCadastro.CONFIRMADO
    origem_dado: str = "cadastro_local"
    atualizado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MasterDataAuditEntry(BaseModel):
    """Entrada de auditoria append-only para qualquer alteração no catálogo mestre."""
    model_config = ConfigDict(frozen=True)

    audit_id: Optional[int] = None
    tipo_entidade: str
    identificador: str
    empresa_codigo: Optional[int] = None
    acao: str  # INSERCAO, ATUALIZACAO, BLOQUEIO, VALIDACAO
    dados_anteriores_json: Optional[str] = None
    dados_novos_json: Optional[str] = None
    origem: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# DTOs de Resolução para o Expense Hunter e outros módulos

class ResolucaoEmpresaResult(BaseModel):
    sucesso: bool
    empresa: Optional[MasterEmpresa] = None
    mensagem: str
    bloqueada: bool = False


class ResolucaoContaResult(BaseModel):
    sucesso: bool
    conta: Optional[MasterContaFinanceira] = None
    mensagem: str
    bloqueada_debito: bool = False
    estado_resolucao: Optional[EstadoResolucaoConta] = None


class CriterioResolucaoConta(BaseModel):
    """Critério estrito em 6 dimensões para localização de conta bancária oficial."""
    model_config = ConfigDict(frozen=True)

    empresa_codigo: int
    banco: str
    agencia: str
    conta: str
    titular: str
    cnpj: str


class ResolucaoContaOficialResult(BaseModel):
    """Resultado da resolução oficial de conta no webPosto com estados explícitos."""
    model_config = ConfigDict(frozen=True)

    sucesso: bool
    estado: EstadoResolucaoConta
    conta_codigo: Optional[int] = None
    conta_financeira: Optional[MasterContaFinanceira] = None
    mensagem: str
    candidatos_analisados: int = 0
    detalhes: dict[str, Any] = Field(default_factory=dict)


class ResolucaoPlanoResult(BaseModel):
    sucesso: bool
    plano: Optional[MasterPlanoConta] = None
    mensagem: str


class ResolucaoCentroCustoResult(BaseModel):
    sucesso: bool
    centro_custo: Optional[MasterCentroCusto] = None
    mensagem: str


class ResolucaoFornecedorResult(BaseModel):
    sucesso: bool
    fornecedor: Optional[MasterFornecedor] = None
    mensagem: str


class ValidacaoCompatibilidadeDespesaResult(BaseModel):
    valido: bool
    motivos_bloqueio: list[str] = Field(default_factory=list)
    detalhes: dict[str, Any] = Field(default_factory=dict)
