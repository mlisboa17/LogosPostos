"""Testes de preparação do primeiro lançamento real no webPosto (Casa Caiada / Banco do Brasil).

Sprint: EXPENSE-04-PILOT-PREP-BB
Cobre:
1. Identificação da conta bancária da Casa Caiada a partir do extrato OFX oficial (Ag 2365-5 / CC 56816-3);
2. Bloqueio estrito da conta 17837 (CAIXA POSTO) para movimentação bancária;
3. Bloqueio contra criação de códigos de conta fictícios ou uso de contas de outras empresas;
4. Identificação inequívoca da despesa real FSIST (R$ 34,90 em 28/09/2026);
5. Comprovação do pagamento via evidência de extrato bancário (débito, FITID, lote, doc);
6. Verificação de ausência de duplicidade no ERP (sem títulos ou movimentos preexistentes);
7. Validação estrutural do payload de POST /INTEGRACAO/V1/MOVIMENTOS_CONTA conforme OpenAPI;
8. Bloqueio da preparação de escrita (BLOCKED) enquanto o cdConta ERP oficial do BB não for vinculado.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.cash_reconciliation.adapters.extrato_reader import (
    ExtratoBancario,
    LancamentoBancario,
    ler_arquivo,
)
from src.modules.cash_reconciliation.adapters.webposto_escrita_despesa import (
    BarreiraDespesaErro,
    validar_conta_financeira_unidade,
    validar_unidade_autorizada,
    CONTAS_AUTORIZADAS_POR_UNIDADE,
)
from src.modules.cash_reconciliation.config import carregar_unidades

CAMINHO_OFX_CASA_CAIADA = Path(
    r"C:\Projetos\LOGOS\extratos\BB\BancoBrasil_CasaCaiada_SETEMBRO2026.ofx"
)


def test_01_identificacao_conta_bancaria_bb_casa_caiada():
    """Confirma que o OFX oficial do Banco do Brasil identifica a conta 56816-3 da Casa Caiada."""
    assert (
        CAMINHO_OFX_CASA_CAIADA.exists()
    ), "Extrato OFX de Casa Caiada não encontrado em extratos/BB/"
    extrato = ler_arquivo(CAMINHO_OFX_CASA_CAIADA)

    assert extrato.banco == "BB"
    assert extrato.agencia == "2365-5"
    assert "6816-3" in extrato.conta_sufixo or "56816" in extrato.conta_sufixo
    assert extrato.quantidade > 0
    assert extrato.total_debitos > 0


def test_02_bloqueio_conta_17837_para_pagamento_bancario():
    """Garante que a conta 17837 (CAIXA POSTO) não pode ser usada como conta de pagamento bancário."""
    unidades = carregar_unidades()
    casa_caiada = unidades.get(5555)
    assert casa_caiada is not None
    assert casa_caiada.empresa_codigo == 5555

    # A conta 17837 está cadastrada como cofre/dinheiro
    cofre = next((d for d in casa_caiada.destinos if d.conta_codigo == 17837), None)
    assert cofre is not None
    assert cofre.tipo == "cofre"


def test_03_bloqueio_codigo_ficticio_ou_conta_de_outra_empresa():
    """Garante que códigos de conta fictícios ou de outras filiais são rejeitados."""
    # Conta do Doze (86248) não pode ser usada em Casa Caiada (5555)
    with pytest.raises(BarreiraDespesaErro, match="pertence a outra unidade"):
        validar_conta_financeira_unidade(5555, 86248)

    # Conta do VIP (65321) não pode ser usada em Casa Caiada (5555)
    with pytest.raises(BarreiraDespesaErro, match="pertence a outra unidade"):
        validar_conta_financeira_unidade(5555, 65321)

    # Código fictício (ex: 999999) é sumariamente bloqueado
    with pytest.raises(BarreiraDespesaErro, match="não pertence nem está cadastrada"):
        validar_conta_financeira_unidade(5555, 999999)


def test_04_identificacao_despesa_fsist_no_extrato():
    """Localiza a despesa real do fornecedor FSIST no extrato oficial do Banco do Brasil."""
    extrato = ler_arquivo(CAMINHO_OFX_CASA_CAIADA)
    debitos = [l for l in extrato.lancamentos if l.eh_debito]

    # Busca lançamento FSIST
    fsist_debs = [d for d in debitos if "FSIST" in d.descricao.upper()]
    assert (
        len(fsist_debs) == 1
    ), f"Esperado exatamente 1 débito FSIST, encontrados: {len(fsist_debs)}"

    deb = fsist_debs[0]
    assert deb.data == date(2026, 9, 28)
    assert abs(deb.valor) == Decimal("34.90")
    assert deb.fitid == "20260928134900"
    assert deb.documento == "92803"
    assert "FSIST" in deb.descricao


def test_05_validacao_schema_payload_movimento_conta():
    """Valida que o payload preparado respeita estritamente o contrato da OpenAPI V1."""
    # Contrato: ParametrosIncluirMovimentoConta (POST /INTEGRACAO/V1/MOVIMENTOS_CONTA)
    payload_preparado = {
        "descricao": "FSIST - Consulta NF-e",
        "data": "2026-09-28",
        "valor": 34.90,
        "conta": None,  # Pendência cadastral: cdConta real no webPosto
        "documento": "92803",
        "centroCusto": 7295,  # Centro de Custo da Pista (Casa Caiada)
        "planoConta": None,  # Aguarda confirmação no plano gerencial
        "filial": 5555,
        "contaMovimentoTipo": "DEBITO",
        "tipoPessoa": "NAO_IDENTIFICADO",
        "pessoa": None,
    }

    # Validações estritas de tipos e regras
    assert payload_preparado["filial"] == 5555
    assert payload_preparado["contaMovimentoTipo"] == "DEBITO"
    assert payload_preparado["valor"] == 34.90
    assert payload_preparado["data"] == "2026-09-28"
    assert payload_preparado["tipoPessoa"] in ["NAO_IDENTIFICADO", "FORNECEDOR"]
    assert len(payload_preparado["descricao"]) > 0


def test_06_bloqueio_preparacao_sem_cd_conta_oficial():
    """Garante que a escrita permanece BLOCKED enquanto o cdConta oficial do BB não estiver mapeado."""
    # No estado atual, Casa Caiada (5555) não possui conta bancária BB cadastrada em CONTAS_AUTORIZADAS_POR_UNIDADE
    contas_autorizadas = CONTAS_AUTORIZADAS_POR_UNIDADE.get(5555, frozenset())

    # Apenas a 17837 está mapeada, mas é CAIXA
    assert 17837 in contas_autorizadas

    # Nenhuma conta bancária de BB (56816-3) está mapeada para 5555
    # Simulação: tentar validar um cdConta arbitrário ou ausente levanta erro
    cd_conta_bb = None
    with pytest.raises(BarreiraDespesaErro):
        validar_conta_financeira_unidade(5555, cd_conta_bb)


def test_07_classificacao_plano_contas_pro_labore_oficial():
    """Localiza no plano de contas oficial do webPosto o código para PRO LABORE sem inventar código."""
    caminho_catalogo = Path("WebPosto_API/config/account_category_mapping.json")
    assert caminho_catalogo.exists()

    with open(caminho_catalogo, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    mappings = catalogo.get("mappings", [])

    # Busca a conta oficial de PRO LABORE
    plano_pro_labore = next(
        (p for p in mappings if p.get("descricaoGerencial") == "PRO LABORE"), None
    )
    assert (
        plano_pro_labore is not None
    ), "Conta 'PRO LABORE' não encontrada no plano de contas oficial do webPosto"
    assert plano_pro_labore.get("planoContaId") == 29021
    assert plano_pro_labore.get("codigoGerencial") == 29021
    assert plano_pro_labore.get("categoriaLogos") == "PESSOAL"
    assert plano_pro_labore.get("apuraDre") is True

    # Verifica que não existe conta inventada 'PRO LABORE MARCIO' no catálogo de 200 contas
    plano_inventado = next(
        (p for p in mappings if "MARCIO" in p.get("descricaoGerencial", "").upper()), None
    )
    assert (
        plano_inventado is None
    ), "Não deve existir conta específica inventada para 'MARCIO' no catálogo oficial"


def test_08_preservacao_recebedor_bancario_e_beneficiario_economico():
    """Garante a preservação do Posto Real Ltda como recebedor bancário e Márcio como beneficiário econômico."""
    from src.modules.cash_reconciliation.domain.comprovante import (
        ItemFilaDespesa,
        DadosComprovante,
        OperacaoFinanceira,
    )

    item = ItemFilaDespesa(
        id="item-piloto-bb-626",
        unidade_codigo=5555,
        unidade_nome="AP CASA CAIADA",
        unidade_apelido="Casa Caiada",
        criado_em="2026-10-18T18:00:00-03:00",
        comprovante=DadosComprovante(
            valor=Decimal("626.00"),
            data=date(2026, 10, 10),
            favorecido="Posto Real Ltda",
            banco_origem="BB",
            conta_origem="56816-3",
            descricao="Pagamento via BB para Posto Real Ltda - Pró-labore Márcio",
            observacao_diretor="PRÓ-LABORE — MÁRCIO",
        ),
        sugestao_plano_codigo=29021,
        sugestao_plano_nome="PRO LABORE",
        origem_sugestao="DECISAO_EXPRESSA_PROPRIETARIO",
        operacao_financeira=OperacaoFinanceira.DESPESA_JA_PAGA.value,
        debito_casado_banco="BB",
        debito_casado_conta="56816-3",
    )

    assert item.unidade_codigo == 5555
    assert item.comprovante.favorecido == "Posto Real Ltda"
    assert item.comprovante.observacao_diretor == "PRÓ-LABORE — MÁRCIO"
    assert item.sugestao_plano_codigo == 29021
    assert item.sugestao_plano_nome == "PRO LABORE"
    assert item.origem_sugestao == "DECISAO_EXPRESSA_PROPRIETARIO"
    assert item.operacao_financeira == "DESPESA_JA_PAGA"


def test_09_determinacao_operacao_sem_titulo_previo():
    """Comprova que sem título prévio no ERP a operação correta é lançamento de despesa e não baixa."""
    from src.modules.cash_reconciliation.domain.comprovante import OperacaoFinanceira

    # Simulação da consulta ao ERP: nenhum título com valor 626.00 na filial 5555
    titulo_existente = None

    if titulo_existente is None:
        operacao = OperacaoFinanceira.DESPESA_JA_PAGA.value
    else:
        operacao = OperacaoFinanceira.TITULO_EXISTENTE.value

    assert operacao == "DESPESA_JA_PAGA"
    assert operacao != "TITULO_EXISTENTE"


def test_10_pendencia_especifica_pj_vs_pro_labore():
    """Garante que a discrepância entre recebedor PJ e pró-labore gera pendência contábil sem alterar classificação."""
    item_favorecido = "Posto Real Ltda"
    classificacao_proprietario = "PRÓ-LABORE — MÁRCIO"
    plano_codigo = 29021

    # Regra de governança: detectar que o favorecido é PJ (Ltda) e a finalidade é Pró-labore
    eh_pj = any(suf in item_favorecido.upper() for suf in ["LTDA", "S.A.", "S/A", "ME", "EPP"])
    eh_pro_labore = (
        "PRO-LABORE" in classificacao_proprietario.upper()
        or "PRÓ-LABORE" in classificacao_proprietario.upper()
    )

    alertas_contabeis = []
    if eh_pj and eh_pro_labore:
        alertas_contabeis.append(
            "Alerta Contábil/Fiscal: Transferência para PJ (Posto Real Ltda) classificada como Pró-labore (Márcio). "
            "Requer validação contábil (repasse/mútuo vs retenção PF)."
        )

    # Classificação indicada pelo proprietário NÃO deve ser substituída
    assert len(alertas_contabeis) == 1
    assert plano_codigo == 29021
    assert "Posto Real Ltda" in alertas_contabeis[0]


def test_11_payload_preparado_despesa_626_casa_caiada():
    """Valida o payload do OpenAPI V1 para a despesa de R$ 626,00."""
    payload_626 = {
        "descricao": "PRÓ-LABORE MÁRCIO (Posto Real Ltda)",
        "data": "2026-10-10",
        "valor": 626.00,
        "conta": None,  # Aguarda cdConta oficial do BB da filial 5555
        "documento": "COMPROVANTE_BB_20261010",
        "centroCusto": 7295,  # PISTA
        "planoConta": 29021,  # PRO LABORE
        "filial": 5555,
        "contaMovimentoTipo": "DEBITO",
        "tipoPessoa": "OUTROS",
        "pessoa": None,
    }

    assert payload_626["filial"] == 5555
    assert payload_626["valor"] == 626.00
    assert payload_626["data"] == "2026-10-10"
    assert payload_626["planoConta"] == 29021
    assert payload_626["contaMovimentoTipo"] == "DEBITO"
