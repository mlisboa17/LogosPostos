"""Suíte de testes de validação do Cadastro Mestre Financeiro (MASTER-DATA-02).

Validação 100% offline cobrindo:
1. Identidades oficiais e CNPJs das quatro empresas autorizadas + Posto Real excluído;
2. Bloqueio de empresa 5558 (Posto Real / codWeb 7);
3. Preparação da consulta read-only da conta BB Casa Caiada (56816-3) sem execução de rede;
4. Bloqueio da conta 17837 (CAIXA POSTO) como substituta de conta bancária;
5. Bloqueio de uso cruzado de contas entre filiais;
6. Cobertura dos 200 planos de contas de account_category_mapping.json e preservação do 29021;
7. Validação de centros de custo (ADR-004: 7295 PISTA e 18713 FECHAMENTO);
8. Resolução de fornecedores e favorecidos (Posto Real, Sócios, FSIST);
9. Sincronização incremental e idempotência;
10. Rastreabilidade e trilha de auditoria append-only;
11. Backup a quente (VACUUM INTO) e restauração;
12. Integração real com o Expense Hunter (validar_aprovacao_para_escrita consumindo MasterDataService).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest

from src.modules.master_data.domain.models import (
    ConfiabilidadeCadastro,
    MasterCentroCusto,
    MasterContaFinanceira,
    MasterEmpresa,
    MasterFornecedor,
    MasterPlanoConta,
    PapelEntidade,
    TipoContaFinanceira,
)
from src.modules.master_data.adapters.sqlite_master_data_repository import (
    SqliteMasterDataRepository,
)
from src.modules.master_data.application.master_data_service import (
    MasterDataService,
)
from src.modules.cash_reconciliation.domain.comprovante import (
    DadosComprovante,
    ItemFilaDespesa,
    OperacaoFinanceira,
    StatusDespesa,
)
from src.modules.cash_reconciliation.adapters.webposto_escrita_despesa import (
    BarreiraDespesaErro,
    validar_aprovacao_para_escrita,
)


@pytest.fixture
def repo(tmp_path):
    """Repositório isolado para cada teste."""
    db_file = tmp_path / "master_data_test_02.sqlite3"
    return SqliteMasterDataRepository(db_path=db_file)


@pytest.fixture
def service(repo):
    """Serviço inicializado com bootstrap completo."""
    svc = MasterDataService(repository=repo)
    svc.bootstrap_catalogo()
    return svc


# ==============================================================================
# TESTES DE IDENTIDADE DE EMPRESAS E CNPJ
# ==============================================================================

def test_01_identidade_empresas_e_cnpjs_oficiais(service):
    """Valida que todas as empresas autorizadas possuem dados oficiais corretos."""
    # 74014 - Posto Doze
    res_doze = service.resolver_empresa(74014)
    assert res_doze.sucesso is True
    assert res_doze.empresa.cnpj == "52.308.604/0002-84"
    assert res_doze.empresa.confiabilidade == ConfiabilidadeCadastro.CONFIRMADO
    assert res_doze.empresa.autorizado_despesa is True

    # 11495 - Posto VIP
    res_vip = service.resolver_empresa(11495)
    assert res_vip.sucesso is True
    assert res_vip.empresa.cnpj == "03.008.754/0001-86"
    assert res_vip.empresa.confiabilidade == ConfiabilidadeCadastro.CONFIRMADO
    assert res_vip.empresa.autorizado_despesa is True

    # 5555 - Casa Caiada
    res_cc = service.resolver_empresa(5555)
    assert res_cc.sucesso is True
    assert res_cc.empresa.cnpj == "04.284.939/0001-86"
    assert res_cc.empresa.confiabilidade == ConfiabilidadeCadastro.CONFIRMADO
    assert res_cc.empresa.autorizado_despesa is True

    # 118508 - Conveniência 24h
    res_conv = service.resolver_empresa(118508)
    assert res_conv.sucesso is True
    assert res_conv.empresa.cnpj == "08.106.946/0003-70"
    # CNPJ pendente de consulta oficial /INTEGRACAO/EMPRESAS, não deve ser CONFIRMADO
    assert res_conv.empresa.confiabilidade == ConfiabilidadeCadastro.PENDENTE
    assert res_conv.empresa.usa_mais_pagamentos is False


def test_02_bloqueio_empresa_5558_posto_real(service):
    """Valida bloqueio P0 da empresa 5558 (Posto Real / codWeb 7) para lançamentos de despesa."""
    res_real = service.resolver_empresa(5558)
    assert res_real.sucesso is False
    assert res_real.bloqueada is True
    assert "excluída do escopo" in res_real.mensagem

    # No banco, a entidade está preservada com autorizado_despesa=False
    emp = service.repository.obter_empresa(5558)
    assert emp is not None
    assert emp.empresa_codigo == 5558
    assert emp.cod_web == 7
    assert emp.autorizado_despesa is False
    assert emp.cnpj == "24.156.978/0001-05"


# ==============================================================================
# TESTES DE CONTA BANCO DO BRASIL CASA CAIADA E CAIXA 17837
# ==============================================================================

def test_03_preparacao_consulta_conta_bb_casa_caiada(service):
    """Valida que a consulta read-only ao webPosto está preparada sem executar rede."""
    contrato = service.preparar_consulta_conta_bb_casa_caiada()

    assert contrato["metodo"] == "GET"
    assert contrato["endpoint"] == "/INTEGRACAO/V1/CONTAS"
    assert contrato["params"]["empresaCodigo"] == 5555
    assert contrato["necessita_autorizacao"] is True
    assert contrato["status_piloto"] == "BLOCKED"
    assert contrato["criterio_localizacao"]["conta"] == "56816-3"
    assert contrato["criterio_localizacao"]["agencia"] == "2365-5"
    assert contrato["criterio_localizacao"]["banco"] == "001"
    assert "17837" in contrato["bloqueio_atual"]


def test_04_bloqueio_conta_17837_para_pagamentos_bancarios(service):
    """Valida que a conta 17837 (CAIXA POSTO) não pode ser usada como substituta de conta bancária."""
    res = service.resolver_conta_financeira(17837, empresa_codigo=5555)
    assert res.conta is not None
    assert res.conta.conta_codigo == 17837
    assert res.bloqueada_debito is True
    assert "Caixa Físico da Pista" in res.mensagem


def test_05_bloqueio_uso_cruzado_de_contas(service):
    """Valida que conta pertencente a uma filial não pode ser usada por outra."""
    # Conta 86248 pertence ao Posto Doze (74014)
    res_cruzado = service.resolver_conta_financeira(86248, empresa_codigo=5555)
    assert res_cruzado.sucesso is False
    assert res_cruzado.bloqueada_debito is True
    assert "Bloqueio de uso cruzado" in res_cruzado.mensagem


# ==============================================================================
# TESTES DO PLANO DE CONTAS E CENTROS DE CUSTO
# ==============================================================================

def test_06_plano_de_contas_200_registros(service):
    """Valida que os 200 planos de conta do catálogo foram carregados com naturezas corretas."""
    planos = service.repository.listar_planos_conta()
    assert len(planos) >= 200

    # Validação do plano 29021 (PRO LABORE)
    res_pro_labore = service.resolver_plano_contas(29021)
    assert res_pro_labore.sucesso is True
    assert res_pro_labore.plano.plano_conta_codigo == 29021
    assert res_pro_labore.plano.natureza == "DESPESA"
    assert "PRO LABORE" in res_pro_labore.plano.descricao

    # Validação de plano inexistente
    res_inexistente = service.resolver_plano_contas(999999)
    assert res_inexistente.sucesso is False


def test_07_centros_de_custo_regras_adr004(service):
    """Valida as restrições semânticas dos centros de custo segundo a ADR-004."""
    # 7295 (01.0.1 PISTA) não aceita PRO_LABORE nem ADMINISTRATIVO
    res_pista = service.resolver_centro_custo(7295, tipo_despesa="PRO_LABORE")
    assert res_pista.sucesso is False
    assert "Incompatibilidade" in res_pista.mensagem

    res_pista_admin = service.resolver_centro_custo(7295, tipo_despesa="ADMINISTRATIVO")
    assert res_pista_admin.sucesso is False

    # 18713 (03.0.1 FECHAMENTO) reservado para ajuste de NF, bloqueado para despesas operacionais
    res_fechamento = service.resolver_centro_custo(18713, tipo_despesa="OPERACIONAL")
    assert res_fechamento.sucesso is False
    assert "estornos/ajustes de NF" in res_fechamento.mensagem

    # 21650 (04.0.1 LOJA) é válido
    res_loja = service.resolver_centro_custo(21650)
    assert res_loja.sucesso is True
    assert res_loja.centro_custo.centro_custo_codigo == 21650


# ==============================================================================
# TESTES DE FORNECEDORES E SINCRONIZAÇÃO INCREMENTAL
# ==============================================================================

def test_08_fornecedores_e_favorecidos(service):
    """Valida resolução de fornecedores e favorecidos por documento."""
    # Posto Real LTDA como recebedor bancário (CNPJ do comprovante BB 10/10/2026)
    res_forn = service.resolver_fornecedor(cnpj_cpf="08.106.946/0001-09")
    assert res_forn.sucesso is True
    assert res_forn.fornecedor.razao_social == "POSTO REAL LTDA"
    assert res_forn.fornecedor.papel == PapelEntidade.EMPRESA_RELACIONADA


def test_09_sincronizacao_incremental_idempotente(service):
    """Valida sincronização incremental sem duplicação e com histórico de auditoria."""
    dados_novos = {
        "contas_financeiras": [
            {
                "conta_codigo": 99901,
                "empresa_codigo": 5555,
                "descricao": "BANCO DO BRASIL PILOTO (56816-3)",
                "tipo_conta": "CONTA_CORRENTE",
                "banco_codigo": "001",
                "agencia": "2365-5",
                "conta_numero": "56816-3",
                "ativo": True,
                "permite_debito_despesa": True,
                "confiabilidade": "CONFIRMADO",
                "origem_dado": "sync_teste_piloto",
            }
        ]
    }

    # Sincronização 1
    contagens1 = service.sincronizar_dados_incremental(dados_novos, origem="teste_sync_1")
    assert contagens1["contas_financeiras"] == 1

    # Verificação da conta cadastrada
    res_conta = service.resolver_conta_financeira(99901, empresa_codigo=5555)
    assert res_conta.sucesso is True
    assert res_conta.bloqueada_debito is False

    # Sincronização 2 (idempotente)
    contagens2 = service.sincronizar_dados_incremental(dados_novos, origem="teste_sync_2")
    assert contagens2["contas_financeiras"] == 1

    # Audit log deve registrar ambas as operações
    logs = service.repository.listar_auditoria("CONTA_FINANCEIRA", "99901")
    assert len(logs) == 2
    assert logs[0].acao == "INSERCAO"
    assert logs[1].acao == "ATUALIZACAO"


# ==============================================================================
# TESTES DE BACKUP E RESTAURAÇÃO
# ==============================================================================

def test_10_backup_e_restauracao(service, tmp_path):
    """Valida backup a quente atômico (VACUUM INTO) e restauração."""
    backup_file = tmp_path / "backup_master_data.sqlite3"
    service.repository.executar_backup(backup_file)

    assert backup_file.is_file()
    assert backup_file.stat().st_size > 0

    # Restaura o backup em um novo repositório
    repo_restaurado = SqliteMasterDataRepository(db_path=backup_file)
    empresas = repo_restaurado.listar_empresas()
    assert len(empresas) >= 4


# ==============================================================================
# TESTES DE INTEGRAÇÃO COM O EXPENSE HUNTER
# ==============================================================================

def _criar_item_aprovado(
    unidade_codigo: int = 74014,
    conta_codigo: int = 86248,
    plano_codigo: int = 29018,
    centro_codigo: int = 21650,
    fornecedor_codigo: int = 10,
    operacao: str = OperacaoFinanceira.DESPESA_JA_PAGA.value,
) -> ItemFilaDespesa:
    agora_iso = datetime.now(timezone.utc).isoformat()
    comprovante = DadosComprovante(
        data=date(2026, 10, 10),
        valor=Decimal("150.00"),
        banco_origem="BANCO DO BRASIL",
    )
    item = ItemFilaDespesa(
        id="item-test-01",
        criado_em=agora_iso,
        comprovante=comprovante,
        unidade_codigo=unidade_codigo,
        conta_financeira_codigo=conta_codigo,
        sugestao_plano_codigo=plano_codigo,
        sugestao_centro_codigo=centro_codigo,
        sugestao_fornecedor_codigo=fornecedor_codigo,
        operacao_financeira=operacao,
        status=StatusDespesa.APROVADO.value,
        aprovado_por="auditor_test",
        aprovado_em=agora_iso,
        aprovado_versao=1,
        aprovado_operacao=operacao,
    )
    item.aprovado_hash = item.calcular_hash_conteudo()
    return item


def test_11_expense_hunter_validacao_com_master_data_sucesso(service):
    """Valida que o Expense Hunter aprova operação perfeitamente compatível no Master Data."""
    item = _criar_item_aprovado(
        unidade_codigo=74014,
        conta_codigo=86248,  # BB Depósito Direto do Doze (permitida para débito)
        plano_codigo=29018,  # Combustível (presente no catálogo)
        centro_codigo=21650,  # 04.0.1 Loja
    )
    # Não deve lançar exceção
    validar_aprovacao_para_escrita(item, master_data_service=service)


def test_12_expense_hunter_bloqueio_empresa_divergente(service):
    """Valida que o Expense Hunter bloqueia lançamento com empresa não autorizada."""
    item = _criar_item_aprovado(unidade_codigo=5558)  # Posto Real
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service)
    assert "Posto Real" in str(exc.value)


def test_13_expense_hunter_bloqueio_conta_17837_para_debito_bancario(service):
    """Valida que o Expense Hunter bloqueia o uso da conta 17837 para pagamento de despesa."""
    item = _criar_item_aprovado(
        unidade_codigo=5555,
        conta_codigo=17837,  # Caixa físico
    )
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service)
    assert "não autorizada para débito" in str(exc.value) or "Caixa Físico" in str(exc.value)


def test_14_expense_hunter_bloqueio_conta_cruzada(service):
    """Valida que o Expense Hunter bloqueia conta pertencente a outra empresa."""
    item = _criar_item_aprovado(
        unidade_codigo=5555,  # Casa Caiada
        conta_codigo=86248,  # Conta do Posto Doze
    )
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service)
    assert "pertence a outra unidade" in str(exc.value) or "pertence à empresa" in str(exc.value)


def test_15_expense_hunter_bloqueio_plano_contas_invalido(service):
    """Valida que o Expense Hunter bloqueia plano de contas inexistente no catálogo."""
    item = _criar_item_aprovado(
        unidade_codigo=74014,
        conta_codigo=86248,
        plano_codigo=999999,  # Inexistente
    )
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service)
    assert "Plano de contas" in str(exc.value)


def test_16_expense_hunter_bloqueio_centro_custo_incompativel(service):
    """Valida que o Expense Hunter bloqueia centro de custo incompatível (ex: 7295 com PRO_LABORE)."""
    item = _criar_item_aprovado(
        unidade_codigo=74014,
        conta_codigo=86248,
        centro_codigo=7295,  # PISTA
        plano_codigo=29021,  # PRO LABORE -> induz validação semântica de centro incompatível
    )
    # Quando o centro 7295 é usado com o plano 29021 (PRO_LABORE), deve ser bloqueado
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service)
    assert "Centro de custo" in str(exc.value)
