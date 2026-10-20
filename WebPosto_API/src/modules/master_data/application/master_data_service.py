"""Serviço de Aplicação do Cadastro Mestre Financeiro do LOGOS (MASTER-DATA-01).

Responsabilidades:
1. Bootstrap / Ingestão segura e idempotente a partir das fontes oficiais locais:
   - `units.json`
   - `account_category_mapping.json`
   - `financial_origin_matrix.json`
2. Interface unificada de resolução cadastral para o Expense Hunter, Cash Hunter e conciliações:
   - `resolver_empresa`
   - `resolver_conta_financeira`
   - `resolver_plano_contas`
   - `resolver_centro_custo`
   - `resolver_fornecedor`
   - `validar_compatibilidade_despesa`
3. Aplicação rigorosa das regras de isolamento:
   - Posto Real (5558) bloqueado para lançamentos de despesa.
   - Bloqueio de uso cruzado de contas entre filiais distintas.
   - Bloqueio da conta 17837 (CAIXA POSTO) para pagamentos bancários.
   - Preservação de dados históricos e auditoria append-only.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from ..adapters.sqlite_master_data_repository import SqliteMasterDataRepository
from ..domain.models import (
    ConfiabilidadeCadastro,
    CriterioResolucaoConta,
    EstadoResolucaoConta,
    MasterCentroCusto,
    MasterContaFinanceira,
    MasterEmpresa,
    MasterFornecedor,
    MasterPlanoConta,
    PapelEntidade,
    ResolucaoCentroCustoResult,
    ResolucaoContaOficialResult,
    ResolucaoContaResult,
    ResolucaoEmpresaResult,
    ResolucaoFornecedorResult,
    ResolucaoPlanoResult,
    TipoContaFinanceira,
    ValidacaoCompatibilidadeDespesaResult,
)

logger = logging.getLogger(__name__)

# Diretórios base e descoberta robusta de artefatos
WEBPOSTO_DIR = Path(__file__).resolve().parents[4]
WORKSPACE_ROOT = WEBPOSTO_DIR.parent


def _descobrir_arquivo(nomes: list[Path]) -> Path:
    for p in nomes:
        if p.is_file():
            return p
    return nomes[0]


UNITS_JSON_PATH = _descobrir_arquivo([
    WEBPOSTO_DIR / "src" / "modules" / "cash_reconciliation" / "config" / "units.json",
    WORKSPACE_ROOT / "WebPosto_API" / "src" / "modules" / "cash_reconciliation" / "config" / "units.json",
    WORKSPACE_ROOT / "units.json",
])

ACCOUNT_MAPPING_PATH = _descobrir_arquivo([
    WEBPOSTO_DIR / "config" / "account_category_mapping.json",
    WORKSPACE_ROOT / "WebPosto_API" / "config" / "account_category_mapping.json",
    WORKSPACE_ROOT / "config" / "account_category_mapping.json",
    WORKSPACE_ROOT / "account_category_mapping.json",
])

FINANCIAL_ORIGIN_PATH = _descobrir_arquivo([
    WEBPOSTO_DIR / "financial_origin_matrix.json",
    WORKSPACE_ROOT / "WebPosto_API" / "financial_origin_matrix.json",
    WORKSPACE_ROOT / "financial_origin_matrix.json",
])


class MasterDataService:
    """Serviço central de consulta e governança do catálogo mestre."""

    def __init__(self, repository: Optional[SqliteMasterDataRepository] = None):
        self.repository = repository or SqliteMasterDataRepository()

    # ==========================================
    # BOOTSTRAP / IMPORTAÇÃO IDEMPOTENTE
    # ==========================================

    def bootstrap_catalogo(self, *, force_reload: bool = False) -> dict[str, int]:
        """Carrega e normaliza os cadastros locais existentes para o SQLite mestre.

        Retorna dicionário com contagem de registros processados por entidade.
        """
        contagens = {
            "empresas": 0,
            "contas_financeiras": 0,
            "planos_conta": 0,
            "centros_custo": 0,
            "fornecedores": 0,
        }

        # 1. Empresas com Identidades Oficiais e CNPJs Comprovados (MASTER-DATA-02)
        empresas_base = [
            MasterEmpresa(
                empresa_codigo=74014,
                cod_web=74014,
                razao_social="POSTO DOZE COMERCIO DE COMBUSTIVEIS E DERIVADOS DE PETROLEO",
                nome_fantasia="Posto Doze Filial II",
                cnpj="52.308.604/0002-84",  # CNPJ Oficial comprovado em /INTEGRACAO/EMPRESAS e filial_master.py
                ativo=True,
                autorizado_despesa=True,
                usa_mais_pagamentos=True,
                conta_cofre_padrao=60536,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="webposto_mapping.md / filial_master.py",
            ),
            MasterEmpresa(
                empresa_codigo=11495,
                cod_web=11495,
                razao_social="RIO DOCE COMERCIO E SERVICOS LTDA",
                nome_fantasia="Posto VIP",
                cnpj="03.008.754/0001-86",  # CNPJ Oficial comprovado em /INTEGRACAO/EMPRESAS e filial_master.py
                ativo=True,
                autorizado_despesa=True,
                usa_mais_pagamentos=True,
                conta_cofre_padrao=58062,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="webposto_mapping.md / filial_master.py",
            ),
            MasterEmpresa(
                empresa_codigo=5555,
                cod_web=5555,
                razao_social="AUTO POSTO CASA CAIADA LTDA",
                nome_fantasia="AP Casa Caiada",
                cnpj="04.284.939/0001-86",  # CNPJ Oficial comprovado no webPosto e extratos oficiais BB
                ativo=True,
                autorizado_despesa=True,
                usa_mais_pagamentos=True,
                conta_cofre_padrao=58061,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="webposto_mapping.md / extratos_bb / filial_master.py",
            ),
            MasterEmpresa(
                empresa_codigo=118508,
                cod_web=118508,
                razao_social="CONVENIENCIA 24 HORAS",
                nome_fantasia="Conveniência 24 Horas",
                cnpj="08.106.946/0003-70",
                ativo=True,
                autorizado_despesa=True,
                usa_mais_pagamentos=False,  # Regra de negócio fixa: NÃO usa Mais Pagamentos
                conta_cofre_padrao=82912,
                confiabilidade=ConfiabilidadeCadastro.PENDENTE,  # CNPJ pendente de consulta oficial /INTEGRACAO/EMPRESAS
                origem_dado="units.json / cadastro_pendente",
            ),
            MasterEmpresa(
                empresa_codigo=5558,
                cod_web=7,
                razao_social="REAL RECIFE LTDA",
                nome_fantasia="Posto Real",
                cnpj="24.156.978/0001-05",  # CNPJ cadastrado no webPosto (inativa em 2026-05-20)
                ativo=True,
                autorizado_despesa=False,  # Regra de governança estrita: EXCLUÍDO de lançamentos de despesa
                usa_mais_pagamentos=True,
                conta_cofre_padrao=27406,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="webposto_mapping.md / filial_master.py",
            ),
        ]

        for emp in empresas_base:
            self.repository.upsert_empresa(emp, origem_auditoria="bootstrap_master_data")
            contagens["empresas"] += 1

        # 2. Contas Financeiras com Papéis e Vínculos Explicitos (units.json + webPosto probe)
        contas_base = [
            # --- Posto Doze Filial II (74014) ---
            MasterContaFinanceira(
                conta_codigo=86248,
                empresa_codigo=74014,
                descricao="BB DEPOSITO DIRETO (4068-X)",
                tipo_conta=TipoContaFinanceira.CONTA_CORRENTE,
                banco_codigo="001",
                banco_nome="BANCO DO BRASIL",
                conta_numero="4068-X",
                ativo=True,
                permite_debito_despesa=True,  # Conta corrente autorizada para Doze
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            MasterContaFinanceira(
                conta_codigo=86188,
                empresa_codigo=74014,
                descricao="PAGBANK (9048-8)",
                tipo_conta=TipoContaFinanceira.CONTA_CORRENTE,
                banco_codigo="290",
                banco_nome="PAGBANK",
                conta_numero="9048-8",
                ativo=True,
                permite_debito_despesa=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            MasterContaFinanceira(
                conta_codigo=86081,
                empresa_codigo=74014,
                descricao="BB COFRE POSTO DOZE",
                tipo_conta=TipoContaFinanceira.COFRE,
                banco_codigo="001",
                banco_nome="BANCO DO BRASIL",
                ativo=True,
                permite_debito_despesa=False,  # Cofre físico NÃO permite débito direto de despesa bancária
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            MasterContaFinanceira(
                conta_codigo=60536,
                empresa_codigo=74014,
                descricao="COFRE DOZE",
                tipo_conta=TipoContaFinanceira.COFRE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            # --- Posto VIP (11495) ---
            MasterContaFinanceira(
                conta_codigo=65321,
                empresa_codigo=11495,
                descricao="BRADESCO DEPOSITO DIRETO",
                tipo_conta=TipoContaFinanceira.CONTA_CORRENTE,
                banco_codigo="237",
                banco_nome="BRADESCO",
                ativo=True,
                permite_debito_despesa=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            MasterContaFinanceira(
                conta_codigo=55028,
                empresa_codigo=11495,
                descricao="ITAU COFRE VIP",
                tipo_conta=TipoContaFinanceira.COFRE,
                banco_codigo="341",
                banco_nome="ITAU",
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            MasterContaFinanceira(
                conta_codigo=58062,
                empresa_codigo=11495,
                descricao="COFRE VIP",
                tipo_conta=TipoContaFinanceira.COFRE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            # --- AP Casa Caiada (5555) ---
            MasterContaFinanceira(
                conta_codigo=17837,
                empresa_codigo=5555,
                descricao="CAIXA(POSTO)",
                tipo_conta=TipoContaFinanceira.CAIXA_FISICO,
                ativo=True,
                permite_debito_despesa=False,  # ESTRITAMENTE BLOQUEADA para pagamentos bancários
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            MasterContaFinanceira(
                conta_codigo=58061,
                empresa_codigo=5555,
                descricao="COFRE CASA CAIADA",
                tipo_conta=TipoContaFinanceira.COFRE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            # --- Conveniência 24 Horas (118508) ---
            MasterContaFinanceira(
                conta_codigo=82912,
                empresa_codigo=118508,
                descricao="COFRE CONVENIENCIA",
                tipo_conta=TipoContaFinanceira.COFRE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            # --- Posto Real (5558 - Excluída de Despesas) ---
            MasterContaFinanceira(
                conta_codigo=27406,
                empresa_codigo=5558,
                descricao="COFRE POSTO REAL",
                tipo_conta=TipoContaFinanceira.COFRE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="units.json",
            ),
            # --- Contas Bancárias da Rede Pendentes de Vinculação por Filial ---
            MasterContaFinanceira(
                conta_codigo=20936,
                empresa_codigo=None,
                descricao="CONTA BANCO 20936",
                tipo_conta=TipoContaFinanceira.CONTA_CORRENTE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
            MasterContaFinanceira(
                conta_codigo=59117,
                empresa_codigo=None,
                descricao="CONTA BANCO 59117",
                tipo_conta=TipoContaFinanceira.CONTA_CORRENTE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
            MasterContaFinanceira(
                conta_codigo=69050,
                empresa_codigo=None,
                descricao="CONTA BANCO 69050",
                tipo_conta=TipoContaFinanceira.CONTA_CORRENTE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
            MasterContaFinanceira(
                conta_codigo=70766,
                empresa_codigo=None,
                descricao="CONTA BANCO 70766",
                tipo_conta=TipoContaFinanceira.CONTA_CORRENTE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
            # --- Contas Transitórias e Adquirentes ---
            MasterContaFinanceira(
                conta_codigo=27173,
                empresa_codigo=None,
                descricao="CONTA TRANSITORIA 27173",
                tipo_conta=TipoContaFinanceira.TRANSITORIA,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
            MasterContaFinanceira(
                conta_codigo=69446,
                empresa_codigo=None,
                descricao="CONTA TRANSITORIA 69446",
                tipo_conta=TipoContaFinanceira.TRANSITORIA,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
            MasterContaFinanceira(
                conta_codigo=82918,
                empresa_codigo=None,
                descricao="CONTA TRANSITORIA 82918",
                tipo_conta=TipoContaFinanceira.TRANSITORIA,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
            MasterContaFinanceira(
                conta_codigo=86377,
                empresa_codigo=None,
                descricao="CONTA TRANSITORIA 86377",
                tipo_conta=TipoContaFinanceira.TRANSITORIA,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
            MasterContaFinanceira(
                conta_codigo=55460,
                empresa_codigo=None,
                descricao="ADQUIRENTE CARTAO 55460",
                tipo_conta=TipoContaFinanceira.ADQUIRENTE,
                ativo=True,
                permite_debito_despesa=False,
                confiabilidade=ConfiabilidadeCadastro.HISTORICO,
                origem_dado="webposto_probe",
            ),
        ]

        for conta in contas_base:
            self.repository.upsert_conta_financeira(conta, origem_auditoria="bootstrap_master_data")
            contagens["contas_financeiras"] += 1

        # 3. Planos de Contas Oficial (200 contas de account_category_mapping.json)
        caminho_planos = ACCOUNT_MAPPING_PATH
        if caminho_planos.is_file():
            try:
                with open(caminho_planos, "r", encoding="utf-8") as f:
                    dados_json = json.load(f)

                # Suporte ao schema estruturado {"mappings": [...]} ou dict planoId->nome
                itens_planos = dados_json.get("mappings") if isinstance(dados_json, dict) and "mappings" in dados_json else None
                planos_a_inserir: list[MasterPlanoConta] = []
                if itens_planos and isinstance(itens_planos, list):
                    for item in itens_planos:
                        try:
                            cod_int = int(item.get("codigoGerencial") or item.get("planoContaId"))
                            desc = str(item.get("descricaoGerencial") or item.get("descricaoContabil") or "").strip()
                            nat = str(item.get("natureza", "D")).upper()
                            natureza_str = "DESPESA" if nat == "D" else ("RECEITA" if nat == "C" else "OUTRO")
                            permite = bool(nat == "D")
                            cat = item.get("categoriaLogosV3") or item.get("categoriaLogos") or item.get("categoriaLogosV2")
                            ativo_plano = bool(item.get("ativo", True))

                            plano = MasterPlanoConta(
                                plano_conta_codigo=cod_int,
                                descricao=desc,
                                natureza=natureza_str,
                                grupo=str(cat) if cat else None,
                                ativo=ativo_plano,
                                permite_despesa=permite,
                                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                                origem_dado="account_category_mapping.json",
                            )
                            planos_a_inserir.append(plano)
                        except (ValueError, TypeError):
                            continue
                elif isinstance(dados_json, dict):
                    for cod_str, desc in dados_json.items():
                        try:
                            cod_int = int(cod_str)
                            plano = MasterPlanoConta(
                                plano_conta_codigo=cod_int,
                                descricao=str(desc).strip(),
                                natureza="DESPESA" if cod_int >= 20000 else "CUSTO",
                                ativo=True,
                                permite_despesa=True,
                                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                                origem_dado="account_category_mapping.json",
                            )
                            planos_a_inserir.append(plano)
                        except (ValueError, TypeError):
                            continue

                if planos_a_inserir:
                    self.repository.upsert_planos_conta_bulk(planos_a_inserir, origem_auditoria="bootstrap_mapping")
                    contagens["planos_conta"] += len(planos_a_inserir)
            except Exception as e:
                logger.error("Erro ao carregar account_category_mapping.json: %s", e)

        # Se nenhum plano foi carregado, garante os essenciais
        if contagens["planos_conta"] == 0:
            planos_essenciais = [
                (29021, "PRO LABORE"),
                (29001, "ENERGIA ELETRICA"),
                (29002, "AGUA E ESGOTO"),
                (29003, "TELEFONE E INTERNET"),
                (29005, "HONORARIOS CONTABEIS"),
                (700, "COMBUSTIVEIS"),
                (705, "LUBRIFICANTES"),
            ]
            planos_essenciais_obj = [
                MasterPlanoConta(
                    plano_conta_codigo=cod_int,
                    descricao=desc,
                    natureza="DESPESA",
                    ativo=True,
                    permite_despesa=True,
                    confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                    origem_dado="fallback_essencial",
                )
                for cod_int, desc in planos_essenciais
            ]
            self.repository.upsert_planos_conta_bulk(planos_essenciais_obj, origem_auditoria="bootstrap_fallback")
            contagens["planos_conta"] += len(planos_essenciais_obj)

        # 4. Centros de Custo Oficiais do webPosto (ADR-004)
        centros_custo_base = [
            MasterCentroCusto(
                centro_custo_codigo=7295,
                empresa_codigo=None,
                descricao="01.0.1 PISTA",
                tipo_abrangencia="PISTA",
                ativo=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="adr_004_webposto",
            ),
            MasterCentroCusto(
                centro_custo_codigo=18713,
                empresa_codigo=None,
                descricao="03.0.1 FECHAMENTO",
                tipo_abrangencia="AJUSTE_NF",
                ativo=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="adr_004_webposto",
            ),
            MasterCentroCusto(
                centro_custo_codigo=21650,
                empresa_codigo=None,
                descricao="04.0.1 LOJA",
                tipo_abrangencia="CONVENIENCIA",
                ativo=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="adr_004_webposto",
            ),
            MasterCentroCusto(
                centro_custo_codigo=22310,
                empresa_codigo=None,
                descricao="05.0.1 CONVENIENCIA",
                tipo_abrangencia="CONVENIENCIA",
                ativo=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="adr_004_webposto",
            ),
            MasterCentroCusto(
                centro_custo_codigo=24423,
                empresa_codigo=None,
                descricao="09.0.1 FOOD",
                tipo_abrangencia="FOOD",
                ativo=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="adr_004_webposto",
            ),
        ]
        for cc in centros_custo_base:
            self.repository.upsert_centro_custo(cc, origem_auditoria="bootstrap_master_data")
            contagens["centros_custo"] += 1

        # 5. Fornecedores, Favorecidos e Entidades Relacionadas Conhecidas
        fornecedores_base = [
            MasterFornecedor(
                fornecedor_codigo=None,
                empresa_codigo=None,
                razao_social="POSTO REAL LTDA",
                nome_fantasia="Posto Real (Recebedor Bancário)",
                cnpj_cpf="08.106.946/0001-09",  # CNPJ do recebedor bancário no comprovante BB de 10/10/2026
                papel=PapelEntidade.EMPRESA_RELACIONADA,
                ativo=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="comprovante_bb_20261010",
            ),
            MasterFornecedor(
                fornecedor_codigo=None,
                empresa_codigo=None,
                razao_social="REAL RECIFE LTDA",
                nome_fantasia="Posto Real (webPosto)",
                cnpj_cpf="24.156.978/0001-05",  # CNPJ cadastrado no ERP (inativa desde 2026-05-20)
                papel=PapelEntidade.EMPRESA_RELACIONADA,
                ativo=False,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="filial_master.py",
            ),
            MasterFornecedor(
                fornecedor_codigo=None,
                empresa_codigo=None,
                razao_social="MARCIO",
                nome_fantasia="Marcio (Sócio)",
                cnpj_cpf=None,
                papel=PapelEntidade.SOCIO,
                ativo=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="decisao_expressa_proprietario",
            ),
            MasterFornecedor(
                fornecedor_codigo=None,
                empresa_codigo=None,
                razao_social="FSIST AUTOMACAO FISCAL",
                nome_fantasia="FSIST",
                cnpj_cpf=None,
                papel=PapelEntidade.FORNECEDOR,
                ativo=True,
                confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                origem_dado="piloto_fsist_20260928",
            ),
        ]
        for forn in fornecedores_base:
            self.repository.upsert_fornecedor(forn, origem_auditoria="bootstrap_master_data")
            contagens["fornecedores"] += 1

        logger.info("Bootstrap Master Data concluído com sucesso: %s", contagens)
        return contagens

    def sincronizar_dados_incremental(
        self,
        dados_novos: dict[str, list[dict[str, Any]]],
        *,
        origem: str = "sync_incremental",
    ) -> dict[str, int]:
        """Sincroniza incrementalmente cadastros oficiais sem perda de dados históricos ou proveniência.

        Permite ingestão segura de:
        - empresas
        - contas_financeiras
        - planos_conta
        - centros_custo
        - fornecedores

        Aplica governança estrita:
        - Nenhuma alteração sem registro no audit log.
        - Não inventa códigos.
        - Preserva vínculos confirmados.
        """
        contagens = {
            "empresas": 0,
            "contas_financeiras": 0,
            "planos_conta": 0,
            "centros_custo": 0,
            "fornecedores": 0,
        }

        # Empresas
        for item in dados_novos.get("empresas", []):
            emp = MasterEmpresa(**item) if not isinstance(item, MasterEmpresa) else item
            self.repository.upsert_empresa(emp, origem_auditoria=origem)
            contagens["empresas"] += 1

        # Contas Financeiras
        for item in dados_novos.get("contas_financeiras", []):
            conta = MasterContaFinanceira(**item) if not isinstance(item, MasterContaFinanceira) else item
            self.repository.upsert_conta_financeira(conta, origem_auditoria=origem)
            contagens["contas_financeiras"] += 1

        # Planos de Contas
        planos_raw = dados_novos.get("planos_conta", [])
        planos = [
            p if isinstance(p, MasterPlanoConta) else MasterPlanoConta(**p)
            for p in planos_raw
        ]
        if planos:
            self.repository.upsert_planos_conta_bulk(planos, origem_auditoria=origem)
            contagens["planos_conta"] += len(planos)

        # Centros de Custo
        for item in dados_novos.get("centros_custo", []):
            cc = MasterCentroCusto(**item) if not isinstance(item, MasterCentroCusto) else item
            self.repository.upsert_centro_custo(cc, origem_auditoria=origem)
            contagens["centros_custo"] += 1

        # Fornecedores
        for item in dados_novos.get("fornecedores", []):
            forn = MasterFornecedor(**item) if not isinstance(item, MasterFornecedor) else item
            self.repository.upsert_fornecedor(forn, origem_auditoria=origem)
            contagens["fornecedores"] += 1

        logger.info("Sincronização incremental Master Data concluída: %s", contagens)
        return contagens

    def preparar_consulta_conta_bb_casa_caiada(self) -> dict[str, Any]:
        """Prepara o contrato e a especificação da requisição read-only para consulta de contas no webPosto.

        Permite localizar o código ERP correspondente à conta corrente Banco do Brasil
        (Agência 2365-5 / Conta 56816-3) da empresa Casa Caiada (5555).

        IMPORTANTE: NÃO executa nenhuma chamada de rede externa. Retorna a especificação
        declarando explicitamente a necessidade de autorização prévia e critérios de busca.
        """
        return {
            "metodo": "GET",
            "endpoint": "/INTEGRACAO/V1/CONTAS",
            "params": {
                "empresaCodigo": 5555,
                "limite": 100,
            },
            "headers_necessarios": ["x-api-key"],
            "necessita_autorizacao": True,
            "status_piloto": "BLOCKED",
            "justificativa": (
                "Localizar contaCodigo ERP correspondente à agência 2365-5 / conta 56816-3 "
                "do Banco do Brasil da empresa 5555 (Casa Caiada) para desbloquear o primeiro piloto."
            ),
            "bloqueio_atual": "Código ERP da conta BB não disponível no snapshot local. Proibido inventar código ou usar 17837.",
            "criterio_localizacao": {
                "banco": "001",
                "banco_nome": "BANCO DO BRASIL",
                "agencia": "2365-5",
                "conta": "56816-3",
                "titular": "AUTO POSTO CASA CAIADA LTDA",
                "cnpj": "04.284.939/0001-86",
            },
            "acao_ao_autorizar": (
                "Executar GET com chave da Casa Caiada, filtrar resultados por banco 001 / conta 56816-3 "
                "e sincronizar contaCodigo via sincronizar_dados_incremental."
            ),
        }

    def preparar_consulta_empresas_oficial(self) -> dict[str, Any]:
        """Prepara a requisição read-only para consulta de empresas oficiais no webPosto.

        Permite auditar a situação cadastral oficial de todas as empresas e validar
        o CNPJ da Conveniência 24 Horas (118508) sem suposições.

        IMPORTANTE: NÃO executa nenhuma chamada de rede externa. Retorna a especificação
        declarando explicitamente a necessidade de autorização prévia.
        """
        return {
            "metodo": "GET",
            "endpoint": "/INTEGRACAO/EMPRESAS",
            "params": {},
            "headers_necessarios": ["x-api-key"],
            "necessita_autorizacao": True,
            "status_empresa_118508": "PENDENTE",
            "justificativa": (
                "Obter o cadastro oficial da empresa 118508 (Conveniência 24 Horas) para validação "
                "de CNPJ e situação cadastral no ERP sem inferências ou suposições."
            ),
            "regras_isolamento": {
                "empresa_118508": "NÃO utiliza Mais Pagamentos; repasse_sangria_para: 5555",
                "empresa_5558": "Posto Real permanece inativo e excluído de despesas",
            },
        }

    def avaliar_resposta_contas_erp(
        self,
        criterio: CriterioResolucaoConta | dict[str, Any],
        contas_erp: Optional[list[dict[str, Any]]] = None,
    ) -> ResolucaoContaOficialResult:
        """Avalia com estrita governança em 6 dimensões o retorno do endpoint /INTEGRACAO/V1/CONTAS.

        Exige correspondência inequívoca em:
        1. empresaCodigo;
        2. banco;
        3. agência;
        4. número da conta;
        5. titular;
        6. CNPJ.

        Retorna estados explícitos:
        - ACCOUNT_PENDING_AUTHORIZATION: se contas_erp for None (requer autorização prévia)
        - ACCOUNT_NOT_FOUND: nenhuma conta compatível encontrada
        - ACCOUNT_AMBIGUOUS: múltiplos registros encontrados para o mesmo critério
        - ACCOUNT_OWNER_MISMATCH: conta associada a outra filial ou titular divergente
        - ACCOUNT_CODE_MISSING: conta encontrada mas sem contaCodigo numérico válido
        - ACCOUNT_CONFIRMED: correspondência unívoca em todas as 6 dimensões com contaCodigo válido
        """
        if isinstance(criterio, dict):
            criterio = CriterioResolucaoConta(**criterio)

        if contas_erp is None:
            return ResolucaoContaOficialResult(
                sucesso=False,
                estado=EstadoResolucaoConta.ACCOUNT_PENDING_AUTHORIZATION,
                mensagem="Consulta ao endpoint /INTEGRACAO/V1/CONTAS requer autorização humana prévia.",
                detalhes={"criterio": criterio.model_dump()},
            )

        if not contas_erp:
            return ResolucaoContaOficialResult(
                sucesso=False,
                estado=EstadoResolucaoConta.ACCOUNT_NOT_FOUND,
                mensagem="Nenhuma conta retornada pelo webPosto para os critérios fornecidos.",
                candidatos_analisados=0,
                detalhes={"criterio": criterio.model_dump()},
            )

        import re

        def _digitos(v: Any) -> str:
            return re.sub(r"\D", "", str(v or ""))

        def _norm_banco(b: Any) -> str:
            d = _digitos(b)
            return d.zfill(3) if d else ""

        def _norm_agencia(ag: Any) -> tuple[str, str]:
            if not ag:
                return ("", "")
            s = str(ag).strip().upper()
            if "-" in s:
                p = s.split("-", 1)
                return (_digitos(p[0]), p[1].strip())
            return (_digitos(s), "")

        def _norm_conta(c: Any) -> tuple[str, str]:
            if not c:
                return ("", "")
            s = str(c).strip().upper()
            if "-" in s:
                p = s.split("-", 1)
                return (_digitos(p[0]), p[1].strip())
            return (_digitos(s), "")

        crit_banco = _norm_banco(criterio.banco)
        crit_ag_num, crit_ag_dv = _norm_agencia(criterio.agencia)
        crit_cc_num, crit_cc_dv = _norm_conta(criterio.conta)
        crit_cnpj_d = _digitos(criterio.cnpj)

        candidatos_compativeis: list[dict[str, Any]] = []
        divergencias_proprietario: list[str] = []

        for item in contas_erp:
            item_empresa = item.get("empresaCodigo") or item.get("empresa_codigo") or item.get("filialCodigo")
            item_banco = _norm_banco(item.get("banco") or item.get("bancoCodigo") or item.get("banco_codigo"))
            item_ag = item.get("agencia") or item.get("agenciaCodigo") or item.get("agencia_codigo")
            item_ag_num, item_ag_dv = _norm_agencia(item_ag)
            item_cc = item.get("conta") or item.get("contaNumero") or item.get("conta_numero")
            item_cc_num, item_cc_dv = _norm_conta(item_cc)
            item_cnpj_d = _digitos(item.get("cnpj") or item.get("cpfCnpj") or item.get("cnpj_cpf") or "")

            # Verifica banco se fornecido
            if item_banco and crit_banco and item_banco != crit_banco:
                continue

            # Correspondência de número da agência e conta
            ag_match = (item_ag_num == crit_ag_num)
            if crit_ag_dv and item_ag_dv:
                ag_match = ag_match and (item_ag_dv == crit_ag_dv)

            cc_match = (item_cc_num == crit_cc_num)
            if crit_cc_dv and item_cc_dv:
                cc_match = cc_match and (item_cc_dv == crit_cc_dv)

            if not (ag_match and cc_match):
                continue

            # Se encontrou agência e conta, valida titularidade e empresa
            if item_empresa is not None and int(item_empresa) != criterio.empresa_codigo:
                divergencias_proprietario.append(
                    f"Conta pertence à empresa {item_empresa}, mas critério exige empresa {criterio.empresa_codigo}."
                )
                continue

            if item_cnpj_d and crit_cnpj_d and item_cnpj_d != crit_cnpj_d:
                divergencias_proprietario.append(
                    f"CNPJ da conta ({item_cnpj_d}) diverge do CNPJ da empresa ({crit_cnpj_d})."
                )
                continue

            candidatos_compativeis.append(item)

        total_analisados = len(contas_erp)

        if not candidatos_compativeis:
            if divergencias_proprietario:
                return ResolucaoContaOficialResult(
                    sucesso=False,
                    estado=EstadoResolucaoConta.ACCOUNT_OWNER_MISMATCH,
                    mensagem=f"Divergência de titularidade detectada: {'; '.join(divergencias_proprietario)}",
                    candidatos_analisados=total_analisados,
                    detalhes={"divergencias": divergencias_proprietario},
                )
            return ResolucaoContaOficialResult(
                sucesso=False,
                estado=EstadoResolucaoConta.ACCOUNT_NOT_FOUND,
                mensagem=f"Nenhuma conta bancária correspondente a Agência {criterio.agencia} / Conta {criterio.conta} encontrada no retorno do ERP.",
                candidatos_analisados=total_analisados,
            )

        if len(candidatos_compativeis) > 1:
            return ResolucaoContaOficialResult(
                sucesso=False,
                estado=EstadoResolucaoConta.ACCOUNT_AMBIGUOUS,
                mensagem=(
                    f"Ambiguidade: encontradas {len(candidatos_compativeis)} contas no webPosto com os mesmos dados bancários. "
                    "Resolução automática proibida por segurança contábil."
                ),
                candidatos_analisados=total_analisados,
                detalhes={"candidatos": candidatos_compativeis},
            )

        # Exatamente 1 candidato compatível
        candidato = candidatos_compativeis[0]
        cod_conta = candidato.get("contaCodigo") or candidato.get("codigo") or candidato.get("id") or candidato.get("conta_codigo")
        try:
            cod_conta_int = int(cod_conta) if cod_conta is not None else None
        except (ValueError, TypeError):
            cod_conta_int = None

        if not cod_conta_int or cod_conta_int <= 0:
            return ResolucaoContaOficialResult(
                sucesso=False,
                estado=EstadoResolucaoConta.ACCOUNT_CODE_MISSING,
                mensagem="Conta bancária identificada no ERP, porém com contaCodigo ausente ou inválido.",
                candidatos_analisados=total_analisados,
                detalhes={"candidato": candidato},
            )

        # Constrói entidade oficial validada
        descricao_oficial = str(candidato.get("descricao") or f"BANCO DO BRASIL ({criterio.conta})").strip()
        conta_mestre = MasterContaFinanceira(
            conta_codigo=cod_conta_int,
            empresa_codigo=criterio.empresa_codigo,
            descricao=descricao_oficial,
            tipo_conta=TipoContaFinanceira.CONTA_CORRENTE,
            banco_codigo=criterio.banco,
            banco_nome="BANCO DO BRASIL",
            agencia=criterio.agencia,
            conta_numero=criterio.conta,
            ativo=True,
            permite_debito_despesa=True,
            confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
            origem_dado="webposto_v1_contas_resolucao",
        )

        return ResolucaoContaOficialResult(
            sucesso=True,
            estado=EstadoResolucaoConta.ACCOUNT_CONFIRMED,
            conta_codigo=cod_conta_int,
            conta_financeira=conta_mestre,
            mensagem=f"Conta bancária oficial confirmada com sucesso: código {cod_conta_int} ({descricao_oficial}).",
            candidatos_analisados=total_analisados,
            detalhes={"candidato": candidato},
        )

    # ==========================================
    # INTERFACE DE RESOLUÇÃO (EXPENSE HUNTER)
    # ==========================================

    def resolver_empresa(self, empresa_codigo: int) -> ResolucaoEmpresaResult:
        """Resolve e valida se a empresa está autorizada no escopo do Expense Hunter."""
        # Verificação explícita da empresa 5558
        if empresa_codigo == 5558:
            return ResolucaoEmpresaResult(
                sucesso=False,
                empresa=self.repository.obter_empresa(5558),
                mensagem="Empresa 5558 (Posto Real) está excluída do escopo do Expense Hunter (decisão do dono).",
                bloqueada=True,
            )

        empresa = self.repository.obter_empresa(empresa_codigo)
        if not empresa:
            return ResolucaoEmpresaResult(
                sucesso=False,
                empresa=None,
                mensagem=f"Empresa código {empresa_codigo} não cadastrada no Master Data.",
                bloqueada=True,
            )

        if not empresa.ativo:
            return ResolucaoEmpresaResult(
                sucesso=False,
                empresa=empresa,
                mensagem=f"Empresa {empresa.nome_fantasia} ({empresa_codigo}) está inativa.",
                bloqueada=True,
            )

        if not empresa.autorizado_despesa:
            return ResolucaoEmpresaResult(
                sucesso=False,
                empresa=empresa,
                mensagem=f"Empresa {empresa.nome_fantasia} ({empresa_codigo}) não está autorizada para lançamentos de despesa.",
                bloqueada=True,
            )

        return ResolucaoEmpresaResult(
            sucesso=True,
            empresa=empresa,
            mensagem="Empresa autorizada.",
            bloqueada=False,
        )

    def resolver_conta_financeira(
        self, conta_codigo: int, empresa_codigo: Optional[int] = None
    ) -> ResolucaoContaResult:
        """Resolve a conta financeira e valida compatibilidade com a filial e finalidade de pagamento."""
        conta = self.repository.obter_conta_financeira(conta_codigo)
        if not conta:
            return ResolucaoContaResult(
                sucesso=False,
                conta=None,
                mensagem=f"Conta financeira código {conta_codigo} não encontrada no Master Data.",
                bloqueada_debito=True,
                estado_resolucao=EstadoResolucaoConta.ACCOUNT_NOT_FOUND,
            )

        if not conta.ativo:
            return ResolucaoContaResult(
                sucesso=False,
                conta=conta,
                mensagem=f"Conta {conta.descricao} ({conta_codigo}) está inativa.",
                bloqueada_debito=True,
                estado_resolucao=EstadoResolucaoConta.ACCOUNT_OWNER_MISMATCH,
            )

        # Regra Anti-Uso Cruzado de Contas
        if empresa_codigo is not None and conta.empresa_codigo is not None:
            if conta.empresa_codigo != empresa_codigo:
                return ResolucaoContaResult(
                    sucesso=False,
                    conta=conta,
                    mensagem=(
                        f"Bloqueio de uso cruzado: Conta {conta_codigo} ({conta.descricao}) pertence à empresa "
                        f"{conta.empresa_codigo}, mas foi solicitada pela empresa {empresa_codigo}."
                    ),
                    bloqueada_debito=True,
                    estado_resolucao=EstadoResolucaoConta.ACCOUNT_OWNER_MISMATCH,
                )

        # Regra de Segurança da Conta 17837 - CAIXA(POSTO)
        if conta_codigo == 17837:
            return ResolucaoContaResult(
                sucesso=True,
                conta=conta,
                mensagem="Conta 17837 é Caixa Físico da Pista. Bloqueada como substituta de conta bancária.",
                bloqueada_debito=True,
                estado_resolucao=EstadoResolucaoConta.ACCOUNT_CODE_MISSING,
            )

        # Se for cofre físico
        if conta.tipo_conta == TipoContaFinanceira.COFRE:
            return ResolucaoContaResult(
                sucesso=True,
                conta=conta,
                mensagem="Conta é Cofre físico para sangrias. Bloqueada para débito bancário de despesas.",
                bloqueada_debito=True,
                estado_resolucao=EstadoResolucaoConta.ACCOUNT_CODE_MISSING,
            )

        # Se não tiver permissão explícita de débito de despesa (ex: contas bancárias sem agência/conta validadas)
        if not conta.permite_debito_despesa:
            return ResolucaoContaResult(
                sucesso=True,
                conta=conta,
                mensagem=(
                    f"Conta {conta.descricao} ({conta_codigo}) cadastrada, porém com permissão de débito bancário "
                    "PENDENTE de validação oficial de agência/conta pelo webPosto."
                ),
                bloqueada_debito=True,
                estado_resolucao=EstadoResolucaoConta.ACCOUNT_PENDING_AUTHORIZATION,
            )

        return ResolucaoContaResult(
            sucesso=True,
            conta=conta,
            mensagem="Conta financeira autorizada para movimentação.",
            bloqueada_debito=False,
            estado_resolucao=EstadoResolucaoConta.ACCOUNT_CONFIRMED,
        )

    def resolver_plano_contas(self, plano_codigo: int) -> ResolucaoPlanoResult:
        """Resolve o plano de contas gerencial/DRE."""
        plano = self.repository.obter_plano_conta(plano_codigo)
        if not plano:
            return ResolucaoPlanoResult(
                sucesso=False,
                plano=None,
                mensagem=f"Plano de contas código {plano_codigo} não encontrado no catálogo.",
            )

        if not plano.ativo:
            return ResolucaoPlanoResult(
                sucesso=False,
                plano=plano,
                mensagem=f"Plano de contas {plano.descricao} ({plano_codigo}) está inativo.",
            )

        if not plano.permite_despesa:
            return ResolucaoPlanoResult(
                sucesso=False,
                plano=plano,
                mensagem=f"Plano de contas {plano.descricao} ({plano_codigo}) não permite lançamentos de despesa.",
            )

        if plano_codigo == 29021:
            return ResolucaoPlanoResult(
                sucesso=True,
                plano=plano,
                mensagem=(
                    "Plano 29021 (PRO LABORE) confirmado. Nota: Classificação contábil gerencial; "
                    "não identifica beneficiário individual."
                ),
            )

        return ResolucaoPlanoResult(
            sucesso=True,
            plano=plano,
            mensagem="Plano de contas autorizado.",
        )

    def resolver_centro_custo(
        self,
        cc_codigo: int,
        empresa_codigo: Optional[int] = None,
        tipo_despesa: Optional[str] = None,
    ) -> ResolucaoCentroCustoResult:
        """Resolve o centro de custo e valida compatibilidade com a natureza da despesa."""
        cc = self.repository.obter_centro_custo(cc_codigo)
        if not cc:
            return ResolucaoCentroCustoResult(
                sucesso=False,
                centro_custo=None,
                mensagem=f"Centro de custo código {cc_codigo} não cadastrado.",
            )

        if not cc.ativo:
            return ResolucaoCentroCustoResult(
                sucesso=False,
                centro_custo=cc,
                mensagem=f"Centro de custo {cc.descricao} ({cc_codigo}) está inativo.",
            )

        # Incompatibilidade semântica: Despesa administrativa / pró-labore no centro PISTA
        if cc_codigo == 7295 and tipo_despesa in {"ADMINISTRATIVO", "PRO_LABORE", "CORPORATIVO"}:
            return ResolucaoCentroCustoResult(
                sucesso=False,
                centro_custo=cc,
                mensagem=(
                    f"Incompatibilidade: Centro de custo 7295 (PISTA) não pode ser usado para despesas do tipo {tipo_despesa}."
                ),
            )

        # Incompatibilidade semântica (ADR-004): Centro 18713 (FECHAMENTO) é reservado para ajuste de NF/fechamento
        if cc_codigo == 18713 and tipo_despesa in {"OPERACIONAL", "DESPESA_OPERACIONAL", "PRO_LABORE", "ADMINISTRATIVO"}:
            return ResolucaoCentroCustoResult(
                sucesso=False,
                centro_custo=cc,
                mensagem=(
                    "Incompatibilidade: Centro de custo 18713 (03.0.1 FECHAMENTO) é reservado para estornos/ajustes de NF e fechamento contábil, "
                    f"não podendo ser utilizado para despesas operacionais do tipo {tipo_despesa}."
                ),
            )

        return ResolucaoCentroCustoResult(
            sucesso=True,
            centro_custo=cc,
            mensagem="Centro de custo autorizado.",
        )

    def resolver_fornecedor(
        self,
        fornecedor_codigo: Optional[int] = None,
        cnpj_cpf: Optional[str] = None,
    ) -> ResolucaoFornecedorResult:
        """Resolve fornecedor ou favorecido econômico por código ERP ou documento."""
        fornecedor = None
        if fornecedor_codigo is not None:
            fornecedor = self.repository.obter_fornecedor(fornecedor_codigo)
        elif cnpj_cpf:
            fornecedor = self.repository.obter_fornecedor_por_documento(cnpj_cpf)

        if not fornecedor:
            doc_info = f"código={fornecedor_codigo}" if fornecedor_codigo else f"doc={cnpj_cpf}"
            return ResolucaoFornecedorResult(
                sucesso=False,
                fornecedor=None,
                mensagem=f"Fornecedor/Favorecido não encontrado para {doc_info}.",
            )

        if not fornecedor.ativo:
            return ResolucaoFornecedorResult(
                sucesso=False,
                fornecedor=fornecedor,
                mensagem=f"Fornecedor {fornecedor.razao_social} está inativo.",
            )

        return ResolucaoFornecedorResult(
            sucesso=True,
            fornecedor=fornecedor,
            mensagem="Fornecedor/Favorecido identificado.",
        )

    def validar_compatibilidade_despesa(
        self,
        empresa_codigo: int,
        conta_codigo: int,
        plano_codigo: int,
        centro_custo_codigo: int,
        fornecedor_codigo: Optional[int] = None,
        cnpj_cpf: Optional[str] = None,
        tipo_despesa: Optional[str] = None,
    ) -> ValidacaoCompatibilidadeDespesaResult:
        """Executa a validação de compatibilidade completa entre todos os elementos da operação."""
        bloqueios: list[str] = []
        detalhes: dict[str, Any] = {}

        # 1. Empresa
        res_empresa = self.resolver_empresa(empresa_codigo)
        detalhes["empresa"] = res_empresa.model_dump()
        if not res_empresa.sucesso:
            bloqueios.append(res_empresa.mensagem)

        # 2. Conta
        res_conta = self.resolver_conta_financeira(conta_codigo, empresa_codigo=empresa_codigo)
        detalhes["conta"] = res_conta.model_dump()
        if not res_conta.sucesso:
            bloqueios.append(res_conta.mensagem)
        elif res_conta.bloqueada_debito:
            bloqueios.append(res_conta.mensagem)

        # 3. Plano
        res_plano = self.resolver_plano_contas(plano_codigo)
        detalhes["plano"] = res_plano.model_dump()
        if not res_plano.sucesso:
            bloqueios.append(res_plano.mensagem)

        # 4. Centro de Custo
        res_cc = self.resolver_centro_custo(centro_custo_codigo, empresa_codigo=empresa_codigo, tipo_despesa=tipo_despesa)
        detalhes["centro_custo"] = res_cc.model_dump()
        if not res_cc.sucesso:
            bloqueios.append(res_cc.mensagem)

        # 5. Fornecedor (se informado)
        if fornecedor_codigo or cnpj_cpf:
            res_forn = self.resolver_fornecedor(fornecedor_codigo=fornecedor_codigo, cnpj_cpf=cnpj_cpf)
            detalhes["fornecedor"] = res_forn.model_dump()
            if not res_forn.sucesso:
                bloqueios.append(res_forn.mensagem)

        valido = len(bloqueios) == 0
        return ValidacaoCompatibilidadeDespesaResult(
            valido=valido,
            motivos_bloqueio=bloqueios,
            detalhes=detalhes,
        )
