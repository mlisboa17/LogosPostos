"""Suíte de testes de validação do Cadastro Mestre Financeiro (MASTER-DATA-03).

Cobre integralmente os requisitos de prontidão técnica do piloto e governança:
Agente A: Resolução oficial da conta bancária em 6 dimensões, estados explícitos e sem inferências;
Agente B: Segurança financeira, barreira pré-escrita, idempotência atômica, tokens de piloto e timeouts;
Agente C: Governança corporativa, isolamento da Conveniência 24h e bloqueio do Posto Real;
Agente D: Matriz de prontidão do piloto e garantias de zero rede e zero escrita ERP.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from src.modules.master_data.domain.models import (
    ConfiabilidadeCadastro,
    CriterioResolucaoConta,
    EstadoResolucaoConta,
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
from src.modules.cash_reconciliation.domain.models import Unidade
from src.modules.cash_reconciliation.adapters.webposto_escrita_despesa import (
    BarreiraDespesaErro,
    GerenciadorAutorizacaoPiloto,
    IdempotenciaDespesas,
    WebPostoErro,
    calcular_chave_idempotencia,
    executar_lancamento_despesa,
    validar_aprovacao_para_escrita,
    validar_unidade_autorizada,
)


@pytest.fixture
def repo(tmp_path):
    db_file = tmp_path / "master_data_test_03.sqlite3"
    return SqliteMasterDataRepository(db_path=db_file)


@pytest.fixture
def service(repo):
    svc = MasterDataService(repository=repo)
    svc.bootstrap_catalogo()
    return svc


@pytest.fixture
def criterio_bb_casa_caiada() -> CriterioResolucaoConta:
    return CriterioResolucaoConta(
        empresa_codigo=5555,
        banco="001",
        agencia="2365-5",
        conta="56816-3",
        titular="AUTO POSTO CASA CAIADA LTDA",
        cnpj="04.284.939/0001-86",
    )


# ==============================================================================
# AGENTE A — ACCOUNT RESOLUTION EM 6 DIMENSÕES & ESTADOS EXPLÍCITOS
# ==============================================================================

def test_01_avaliar_contas_erp_pendente_autorizacao(service, criterio_bb_casa_caiada):
    """Quando contas_erp é None, o retorno deve ser ACCOUNT_PENDING_AUTHORIZATION."""
    res = service.avaliar_resposta_contas_erp(criterio_bb_casa_caiada, contas_erp=None)
    assert res.sucesso is False
    assert res.estado == EstadoResolucaoConta.ACCOUNT_PENDING_AUTHORIZATION
    assert "requer autorização" in res.mensagem


def test_02_avaliar_contas_erp_nao_encontrada(service, criterio_bb_casa_caiada):
    """Quando o retorno da API não contém nenhuma conta para os dados bancários."""
    contas_vazias: list[dict] = []
    res = service.avaliar_resposta_contas_erp(criterio_bb_casa_caiada, contas_erp=contas_vazias)
    assert res.sucesso is False
    assert res.estado == EstadoResolucaoConta.ACCOUNT_NOT_FOUND

    contas_outras = [
        {"banco": "237", "agencia": "1111", "conta": "22222", "empresaCodigo": 5555}
    ]
    res2 = service.avaliar_resposta_contas_erp(criterio_bb_casa_caiada, contas_erp=contas_outras)
    assert res2.sucesso is False
    assert res2.estado == EstadoResolucaoConta.ACCOUNT_NOT_FOUND


def test_03_avaliar_contas_erp_ambigua(service, criterio_bb_casa_caiada):
    """Quando existem múltiplos registros com a mesma agência/conta para a filial."""
    contas_duplicadas = [
        {
            "contaCodigo": 99001,
            "banco": "001",
            "agencia": "2365-5",
            "conta": "56816-3",
            "empresaCodigo": 5555,
            "descricao": "BB CONTA 1",
            "cnpj": "04284939000186",
        },
        {
            "contaCodigo": 99002,
            "banco": "001",
            "agencia": "2365",
            "conta": "56816-3",
            "empresaCodigo": 5555,
            "descricao": "BB CONTA 2",
            "cnpj": "04284939000186",
        },
    ]
    res = service.avaliar_resposta_contas_erp(criterio_bb_casa_caiada, contas_erp=contas_duplicadas)
    assert res.sucesso is False
    assert res.estado == EstadoResolucaoConta.ACCOUNT_AMBIGUOUS
    assert "Ambiguidade" in res.mensagem
    assert res.conta_codigo is None


def test_04_avaliar_contas_erp_divergencia_titularidade_empresa(service, criterio_bb_casa_caiada):
    """Quando a conta bancária existe mas pertence a outra filial (ex: Posto VIP 11495)."""
    contas_outra_filial = [
        {
            "contaCodigo": 99003,
            "banco": "001",
            "agencia": "2365-5",
            "conta": "56816-3",
            "empresaCodigo": 11495,  # Diverge de 5555
            "descricao": "BB VIP",
            "cnpj": "03008754000186",
        }
    ]
    res = service.avaliar_resposta_contas_erp(criterio_bb_casa_caiada, contas_erp=contas_outra_filial)
    assert res.sucesso is False
    assert res.estado == EstadoResolucaoConta.ACCOUNT_OWNER_MISMATCH
    assert "titularidade" in res.mensagem.lower()


def test_05_avaliar_contas_erp_codigo_ausente(service, criterio_bb_casa_caiada):
    """Quando a conta bancária é localizada mas sem identificador numérico oficial."""
    contas_sem_id = [
        {
            "contaCodigo": None,
            "banco": "001",
            "agencia": "2365-5",
            "conta": "56816-3",
            "empresaCodigo": 5555,
            "descricao": "BB CASA CAIADA",
            "cnpj": "04284939000186",
        }
    ]
    res = service.avaliar_resposta_contas_erp(criterio_bb_casa_caiada, contas_erp=contas_sem_id)
    assert res.sucesso is False
    assert res.estado == EstadoResolucaoConta.ACCOUNT_CODE_MISSING
    assert "contaCodigo ausente" in res.mensagem


def test_06_avaliar_contas_erp_confirmada_com_sucesso(service, criterio_bb_casa_caiada):
    """Correspondência exata em todas as 6 dimensões com contaCodigo oficial válido."""
    contas_oficiais_fixture = [
        {
            "contaCodigo": 99123,
            "banco": "1",  # Testa normalização 1 -> 001
            "agencia": "2365-5",
            "conta": "56816-3",
            "empresaCodigo": 5555,
            "descricao": "BANCO DO BRASIL - CASA CAIADA",
            "cnpj": "04.284.939/0001-86",
        }
    ]
    res = service.avaliar_resposta_contas_erp(criterio_bb_casa_caiada, contas_erp=contas_oficiais_fixture)
    assert res.sucesso is True
    assert res.estado == EstadoResolucaoConta.ACCOUNT_CONFIRMED
    assert res.conta_codigo == 99123
    assert res.conta_financeira is not None
    assert res.conta_financeira.conta_codigo == 99123
    assert res.conta_financeira.permite_debito_despesa is True


def test_07_ingestao_incremental_e_desbloqueio_conta(service, criterio_bb_casa_caiada):
    """Valida o fluxo completo de resolução e ingestão incremental da conta localizada."""
    contas_fixture = [
        {
            "contaCodigo": 99123,
            "banco": "001",
            "agencia": "2365-5",
            "conta": "56816-3",
            "empresaCodigo": 5555,
            "descricao": "BANCO DO BRASIL CASA CAIADA (56816-3)",
            "cnpj": "04.284.939/0001-86",
        }
    ]
    res_avaliacao = service.avaliar_resposta_contas_erp(criterio_bb_casa_caiada, contas_erp=contas_fixture)
    assert res_avaliacao.sucesso is True

    # Sincroniza incrementalmente no banco mestre
    service.sincronizar_dados_incremental(
        {"contas_financeiras": [res_avaliacao.conta_financeira]},
        origem="teste_resolucao_oficial",
    )

    # Agora a conta deve estar plenamente autorizada no catálogo
    res_resolucao = service.resolver_conta_financeira(99123, empresa_codigo=5555)
    assert res_resolucao.sucesso is True
    assert res_resolucao.bloqueada_debito is False
    assert res_resolucao.estado_resolucao == EstadoResolucaoConta.ACCOUNT_CONFIRMED


def test_08_bloqueio_estrito_permanente_conta_17837(service):
    """Garante que a conta 17837 permaneça terminantemente bloqueada para despesas bancárias."""
    res = service.resolver_conta_financeira(17837, empresa_codigo=5555)
    assert res.bloqueada_debito is True
    assert res.estado_resolucao == EstadoResolucaoConta.ACCOUNT_CODE_MISSING
    assert "Caixa Físico da Pista" in res.mensagem


# ==============================================================================
# AGENTE B — FINANCIAL SECURITY & EXPENSE HUNTER
# ==============================================================================

def _gerar_item_base(
    unidade_codigo: int = 74014,
    conta_codigo: int = 86248,
    plano_codigo: int = 29018,
    centro_codigo: int = 21650,
    valor: Decimal = Decimal("626.00"),
    status: str = StatusDespesa.APROVADO.value,
) -> ItemFilaDespesa:
    agora_iso = datetime.now(timezone.utc).isoformat()
    comprovante = DadosComprovante(
        data=date(2026, 10, 10),
        valor=valor,
        banco_origem="BANCO DO BRASIL",
    )
    item = ItemFilaDespesa(
        id="item-pilot-sec-01",
        criado_em=agora_iso,
        comprovante=comprovante,
        unidade_codigo=unidade_codigo,
        conta_financeira_codigo=conta_codigo,
        sugestao_plano_codigo=plano_codigo,
        sugestao_centro_codigo=centro_codigo,
        operacao_financeira=OperacaoFinanceira.DESPESA_JA_PAGA.value,
        status=status,
        aprovado_por="diretor_audit",
        aprovado_em=agora_iso,
        aprovado_versao=1,
        aprovado_operacao=OperacaoFinanceira.DESPESA_JA_PAGA.value,
    )
    item.aprovado_hash = item.calcular_hash_conteudo()
    return item


def test_09_mesmo_comprovante_duplicado_bloqueado(tmp_path):
    """Idempotência atômica local: reenvio da mesma operação é rejeitado."""
    banco_idemp = tmp_path / "idemp_test.sqlite3"
    idemp = IdempotenciaDespesas(caminho_banco=banco_idemp)
    item = _gerar_item_base()
    chave = calcular_chave_idempotencia(item)

    # Primeira execução
    idemp.iniciar_operacao(chave, item)
    idemp.confirmar_operacao(chave, id_erp="ERP-12345")

    # Segunda tentativa idêntica
    with pytest.raises(BarreiraDespesaErro) as exc:
        idemp.iniciar_operacao(chave, item)
    assert "já em andamento ou concluída" in str(exc.value)


def test_10_comprovante_com_valor_alterado_invalida_aprovacao():
    """Alteração de valor pós-aprovação quebra o hash canônico e invalida aprovação."""
    item = _gerar_item_base(valor=Decimal("626.00"))
    # Modificação do valor sem re-aprovação
    item.comprovante.valor = Decimal("700.00")

    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item)
    assert "conteúdo da proposta foi alterado" in str(exc.value)
    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value


def test_11_conta_bancaria_alterada_invalida_aprovacao():
    """Alteração da conta financeira pós-aprovação invalida aprovação."""
    item = _gerar_item_base(conta_codigo=86248)
    item.conta_financeira_codigo = 86188  # PagBank

    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item)
    assert "conteúdo da proposta foi alterado" in str(exc.value)


def test_12_empresa_modificada_invalida_aprovacao():
    """Alteração da empresa pós-aprovação invalida aprovação."""
    item = _gerar_item_base(unidade_codigo=74014)
    item.unidade_codigo = 5555

    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item)
    assert "conteúdo da proposta foi alterado" in str(exc.value)


def test_13_token_piloto_invalido_expirado_reutilizado(tmp_path):
    """GerenciadorAutorizacaoPiloto rejeita token inválido, expirado ou já consumido."""
    banco_piloto = tmp_path / "piloto_sec.sqlite3"
    gerenciador = GerenciadorAutorizacaoPiloto(caminho_banco=banco_piloto)
    item = _gerar_item_base()

    # Criação do token oficial
    token = gerenciador.criar_autorizacao(
        operacao_id=item.id,
        empresa_codigo=item.unidade_codigo,
        tipo_operacao=item.operacao_financeira,
        valor=item.comprovante.valor,
        hash_aprovado=item.aprovado_hash,
        autorizador_id="diretor_01",
        conta_codigo=item.conta_financeira_codigo,
        validade_minutos=30,
    )

    # 1. Token inválido
    with pytest.raises(BarreiraDespesaErro) as exc_inv:
        gerenciador.consumir_autorizacao("token_falso_invalido", item)
    assert "inexistente ou token inválido" in str(exc_inv.value)

    # 2. Consumo legítimo
    auth = gerenciador.consumir_autorizacao(token, item)
    assert auth.operacao_id == item.id

    # 3. Reutilização do mesmo token (deve ser rejeitada)
    with pytest.raises(BarreiraDespesaErro) as exc_reuso:
        gerenciador.consumir_autorizacao(token, item)
    assert "já consumida" in str(exc_reuso.value)


def test_14_tentativa_debito_17837_na_barreira_escrita(service):
    """Barreira pré-escrita bloqueia lançamento com conta 17837."""
    item = _gerar_item_base(unidade_codigo=5555, conta_codigo=17837)
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service)
    assert "não autorizada para débito" in str(exc.value) or "Caixa Físico" in str(exc.value)


def test_15_tentativa_debito_conta_outra_empresa(service):
    """Barreira pré-escrita bloqueia uso cruzado de contas."""
    # Conta 86248 (Doze) solicitada pela Casa Caiada (5555)
    item = _gerar_item_base(unidade_codigo=5555, conta_codigo=86248)
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service)
    assert "pertence a outra unidade" in str(exc.value) or "pertence à empresa" in str(exc.value)


@pytest.mark.asyncio
async def test_16_tratamento_timeout_resultado_desconhecido(tmp_path):
    """Em caso de timeout de rede, a operação transiciona para RESULTADO_DESCONHECIDO sem retry."""
    banco_idemp = tmp_path / "idemp_timeout.sqlite3"
    dir_audit = tmp_path / "audit_timeout"
    caminho_env = tmp_path / ".env.test"
    caminho_env.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n", encoding="utf-8")

    item = _gerar_item_base()
    unidade = Unidade(
        empresa_codigo=74014,
        nome="POSTO DOZE FILIAL II",
        chave_env="WEBPOSTO_TEST_KEY",
        destinos=(),
        apelido="Doze",
    )

    client_mock = AsyncMock()
    import httpx
    client_mock.post.side_effect = httpx.TimeoutException("Connection timed out")

    with pytest.raises(WebPostoErro) as exc:
        await executar_lancamento_despesa(
            item,
            unidade,
            caminho_env=caminho_env,
            banco_idempotencia=banco_idemp,
            diretorio_auditoria=dir_audit,
            client=client_mock,
        )
    assert "Reenvio automático proibido" in str(exc.value)
    assert item.status == StatusDespesa.RESULTADO_DESCONHECIDO.value

    # Verifica persistência no banco de idempotência
    idemp = IdempotenciaDespesas(caminho_banco=banco_idemp)
    chave = calcular_chave_idempotencia(item)
    with pytest.raises(BarreiraDespesaErro) as exc_reuso:
        idemp.iniciar_operacao(chave, item)
    assert "RESULTADO_DESCONHECIDO" in str(exc_reuso.value)


# ==============================================================================
# AGENTE C — OFFICIAL IDENTITY & COMPANY GOVERNANCE
# ==============================================================================

def test_17_preparar_consulta_empresas_oficial(service):
    """Valida preparação do contrato read-only para /INTEGRACAO/EMPRESAS sem chamada de rede."""
    contrato = service.preparar_consulta_empresas_oficial()
    assert contrato["metodo"] == "GET"
    assert contrato["endpoint"] == "/INTEGRACAO/EMPRESAS"
    assert contrato["necessita_autorizacao"] is True
    assert contrato["status_empresa_118508"] == "PENDENTE"
    assert "NÃO utiliza Mais Pagamentos" in contrato["regras_isolamento"]["empresa_118508"]


def test_18_conveniencia_24h_nao_usa_mais_pagamentos(service):
    """Garante que Conveniência 24h não use Mais Pagamentos e CNPJ continue PENDENTE."""
    emp = service.repository.obter_empresa(118508)
    assert emp is not None
    assert emp.usa_mais_pagamentos is False
    assert emp.confiabilidade == ConfiabilidadeCadastro.PENDENTE


def test_19_posto_real_bloqueado_para_despesas_e_piloto(service):
    """Garante que o Posto Real (5558 / codWeb 7) seja rejeitado pela barreira pré-escrita."""
    res = service.resolver_empresa(5558)
    assert res.sucesso is False
    assert res.bloqueada is True

    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_unidade_autorizada(5558)
    assert "não faz parte do escopo" in str(exc.value)


def test_20_distincao_entre_empresa_operacional_e_recebedor_bancario(service):
    """Preserva distinção entre entidade ERP inativa e contraparte bancária do PIX."""
    emp_erp = service.repository.obter_empresa(5558)
    assert emp_erp.cnpj == "24.156.978/0001-05"  # REAL RECIFE LTDA
    assert emp_erp.autorizado_despesa is False

    forn_pix = service.repository.obter_fornecedor_por_documento("08.106.946/0001-09")
    assert forn_pix is not None
    assert forn_pix.razao_social == "POSTO REAL LTDA"
    assert forn_pix.papel == PapelEntidade.EMPRESA_RELACIONADA
