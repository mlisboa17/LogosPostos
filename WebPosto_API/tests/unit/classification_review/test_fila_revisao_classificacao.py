"""Testes de conformidade e segurança da Fila Local de Revisão e Aprendizagem."""

from __future__ import annotations

import sqlite3
import threading
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from WebPosto_API.src.modules.classification_review import (
    CONTA_TEMPORARIA_CLASSIFICACAO,
    ClassificationReviewService,
    DadoEssencialAusenteErro,
    EstadoRevisao,
    RevisaoConcorrenteErro,
    SqliteClassificationReviewRepository,
    StatusRegraCandidata,
    TransicaoInvalidaErro,
)
from WebPosto_API.src.modules.master_data.adapters.migrations.migration_002_fila_revisao_classificacao import (
    migrar as migrar_002,
    reverter as reverter_002,
)


@pytest.fixture
def repo_isolado(tmp_path: Path) -> SqliteClassificationReviewRepository:
    """Fixture com repositório isolado em banco temporário."""
    db_file = tmp_path / "test_revisao.sqlite3"
    return SqliteClassificationReviewRepository(db_path=db_file)


@pytest.fixture
def service_isolado(repo_isolado: SqliteClassificationReviewRepository) -> ClassificationReviewService:
    """Fixture do serviço de revisão."""
    return ClassificationReviewService(repository=repo_isolado)


# =====================================================================
# 1. MIGRAÇÃO REVERSÍVEL E IDEMPOTENTE
# =====================================================================

def test_01_migracao_reversivel_e_idempotente(tmp_path: Path):
    db_file = tmp_path / "test_migration.sqlite3"
    conn = sqlite3.connect(str(db_file))
    try:
        # 1. Aplicação inicial
        res1 = migrar_002(conn)
        assert res1["status"] == "APLICADA"
        assert len(res1["tabelas_criadas"]) == 4

        # 2. Idempotência da migração
        res2 = migrar_002(conn)
        assert res2["status"] == "APLICADA"

        # 3. Reversão segura
        res_rev = reverter_002(conn)
        assert res_rev["status"] == "REVERTIDA"
        assert len(res_rev["tabelas_removidas"]) == 4

        # Confirmar remoção
        tabelas = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fila_%' OR name LIKE 'classificacao_%';"
            ).fetchall()
        ]
        assert len(tabelas) == 0

        # 4. Reaplicação pós-reversão
        res3 = migrar_002(conn)
        assert res3["status"] == "APLICADA"
    finally:
        conn.close()


# =====================================================================
# 2. CRIAÇÃO IDEMPOTENTE
# =====================================================================

def test_02_criacao_idempotente(service_isolado: ClassificationReviewService):
    item1, inserido1 = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-10",
        valor="150.00",
        descricao="DESPESA COMBUSTIVEL TESTE",
        referencia_evidencias="fitid:123456",
        sugestao_plano_codigo=158764,
        sugestao_plano_descricao="MARCIO-PROLABORE",
        confianca_ia=0.92,
        justificativa_ia="Combustível recorrente",
    )
    assert inserido1 is True
    assert item1.id is not None
    assert item1.status == EstadoRevisao.PENDENTE_REVISAO

    # Segunda chamada com os exatos mesmos dados
    item2, inserido2 = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-10",
        valor="150.00",
        descricao="DESPESA COMBUSTIVEL TESTE",
        referencia_evidencias="fitid:123456",
        sugestao_plano_codigo=158764,
        sugestao_plano_descricao="MARCIO-PROLABORE",
        confianca_ia=0.92,
        justificativa_ia="Tentativa idêntica",
    )
    assert inserido2 is False
    assert item2.id == item1.id
    assert item2.hash_idempotencia == item1.hash_idempotencia


# =====================================================================
# 3. BAIXA CONFIANÇA VIRA PENDÊNCIA LOCAL
# =====================================================================

def test_03_baixa_confianca_vira_pendencia(service_isolado: ClassificationReviewService):
    item, inserido = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-11",
        valor=Decimal("75.50"),
        descricao="PAGAMENTO DIVERSO DESCONHECIDO",
        confianca_ia=0.35,  # Baixa confiança
        justificativa_ia="Termo genérico sem correspondência forte",
    )
    assert inserido is True
    assert item.status == EstadoRevisao.PENDENTE_REVISAO
    assert item.confianca_ia == 0.35
    assert len(item.travas_encontradas) == 0


# =====================================================================
# 4. TRAVA VIRA BLOQUEADO (DADOS ESSENCIAIS, CONTA 27173, DUPLICIDADE)
# =====================================================================

def test_04_trava_vira_bloqueado_dados_essenciais(service_isolado: ClassificationReviewService):
    # Valor zero ou inválido
    item1, _ = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-12",
        valor="0.00",
        descricao="TESTE VALOR ZERO",
    )
    assert item1.status == EstadoRevisao.BLOQUEADO
    assert "VALOR_INVALIDO_OU_ZERO" in item1.travas_encontradas

    # Descrição vazia
    item2, _ = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-12",
        valor="50.00",
        descricao="   ",
    )
    assert item2.status == EstadoRevisao.BLOQUEADO
    assert "DESCRICAO_AUSENTE" in item2.travas_encontradas

    # Posto Real (5558) fora do escopo
    item3, _ = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5558,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-12",
        valor="100.00",
        descricao="DESPESA POSTO REAL",
    )
    assert item3.status == EstadoRevisao.BLOQUEADO
    assert "POSTO_REAL_FORA_DO_ESCOPO" in item3.travas_encontradas

    # Conta bancária 27173 sem liberação de débito
    item4, _ = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=27173,
        data_movimento="2026-10-12",
        valor="626.00",
        descricao="PRÓ-LABORE — MÁRCIO",
    )
    assert item4.status == EstadoRevisao.BLOQUEADO
    assert "CONTA_27173_BLOQUEADA_PARA_DEBITO" in item4.travas_encontradas


def test_04_trava_vira_bloqueado_duplicidade_e_divergencia(service_isolado: ClassificationReviewService):
    item, _ = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-12",
        valor="200.00",
        descricao="DESPESA COM DIVERGENCIA",
        duplicidade_detectada=True,
        divergencia_detectada=True,
    )
    assert item.status == EstadoRevisao.BLOQUEADO
    assert "DUPLICIDADE_DETECTADA" in item.travas_encontradas
    assert "DIVERGENCIA_DETECTADA" in item.travas_encontradas


# =====================================================================
# 5. CONFIANÇA ALTA NUNCA SUPERA UMA TRAVA
# =====================================================================

def test_05_confianca_alta_nao_ignora_trava(service_isolado: ClassificationReviewService):
    # Confiança máxima (1.0), mas conta 27173 está com trava
    item, _ = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=27173,
        data_movimento="2026-10-10",
        valor="626.00",
        descricao="PRÓ-LABORE — MÁRCIO",
        confianca_ia=1.0,  # 100% de confiança
        justificativa_ia="Histórico idêntico identificado com precisão absoluta",
    )
    assert item.status == EstadoRevisao.BLOQUEADO
    assert "CONTA_27173_BLOQUEADA_PARA_DEBITO" in item.travas_encontradas
    assert item.confianca_ia == 1.0


# =====================================================================
# 6. REVISÃO HUMANA PRESERVA HISTÓRICO AUDITÁVEL
# =====================================================================

def test_06_revisao_humana_preserva_historico(service_isolado: ClassificationReviewService):
    item, _ = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-13",
        valor="350.00",
        descricao="MANUTENCAO BOMBA 03",
        confianca_ia=0.50,
    )
    assert item.status == EstadoRevisao.PENDENTE_REVISAO
    assert item.versao == 1

    # Revisão humana
    revisado = service_isolado.revisar_e_classificar(
        pendencia_id=item.id,
        versao_esperada=1,
        plano_definitivo_codigo=29031,
        plano_definitivo_descricao="OUTRAS MOVIMENTACOES DE SAIDA",
        revisor="marcio.lisboa",
        centro_custo_definitivo_codigo=7295,
        justificativa="Classificação confirmada com base na NF-e de manutenção",
    )
    assert revisado.status == EstadoRevisao.CLASSIFICADO
    assert revisado.versao == 2
    assert revisado.revisor == "marcio.lisboa"
    assert revisado.plano_definitivo_codigo == 29031

    # Consultar histórico auditável
    historico = service_isolado.consultar_historico(item.id)
    assert len(historico) == 2
    assert historico[0].acao == "CRIACAO"
    assert historico[0].status_novo == "PENDENTE_REVISAO"
    assert historico[1].acao == "REVISAO_HUMANA"
    assert historico[1].status_anterior == "PENDENTE_REVISAO"
    assert historico[1].status_novo == "CLASSIFICADO"
    assert historico[1].usuario_ou_sistema == "marcio.lisboa"


# =====================================================================
# 7. CORREÇÃO VIRA EXEMPLO CONFIRMADO (NÃO REGRA AUTOMÁTICA)
# =====================================================================

def test_07_correcao_vira_exemplo_confirmado(service_isolado: ClassificationReviewService):
    item, _ = service_isolado.registrar_movimento_para_revisao(
        empresa_codigo=5555,
        conta_financeira_codigo=17837,
        data_movimento="2026-10-14",
        valor="120.00",
        descricao="MATERIAL ELETRICO REPARO LUMINARIAS",
        confianca_ia=0.40,
    )
    service_isolado.revisar_e_classificar(
        pendencia_id=item.id,
        versao_esperada=1,
        plano_definitivo_codigo=29031,
        plano_definitivo_descricao="OUTRAS MOVIMENTACOES DE SAIDA",
        revisor="auditor.financeiro",
    )

    # Recuperar casos semelhantes
    exemplos = service_isolado.recuperar_casos_semelhantes(
        descricao="COMPRA MATERIAL ELETRICO", empresa_codigo=5555
    )
    assert len(exemplos) >= 1
    assert exemplos[0].plano_conta_codigo == 29031
    assert "MATERIAL ELETRICO" in exemplos[0].descricao_padronizada


# =====================================================================
# 8. REGRA NÃO É PROMOVIDA AUTOMATICAMENTE (EXIGE >= 3 CASOS E APROVAÇÃO)
# =====================================================================

def test_08_regra_nao_e_promovida_automaticamente(service_isolado: ClassificationReviewService):
    # Caso 1
    it1, _ = service_isolado.registrar_movimento_para_revisao(
        5555, 17837, "2026-10-15", "10.00", "LAVAGEM DE PISO PISTA", confianca_ia=0.5
    )
    service_isolado.revisar_e_classificar(it1.id, 1, 29031, "OUTRAS MOVIMENTACOES", "revisor1")

    regras = service_isolado.listar_regras_candidatas(StatusRegraCandidata.CANDIDATA)
    assert len(regras) == 1
    assert regras[0].total_casos_confirmados == 1
    assert regras[0].status_regra == StatusRegraCandidata.CANDIDATA

    # Tentativa prematura de promoção deve falhar
    with pytest.raises(ValueError, match="mínimo exigido para promoção é 3"):
        service_isolado.promover_regra_candidata(regras[0].id, "diretoria")

    # Caso 2 (mesmo padrão)
    it2, _ = service_isolado.registrar_movimento_para_revisao(
        5555, 17837, "2026-10-16", "15.00", "LAVAGEM DE PISO PISTA", confianca_ia=0.5
    )
    service_isolado.revisar_e_classificar(it2.id, 1, 29031, "OUTRAS MOVIMENTACOES", "revisor1")

    regras = service_isolado.listar_regras_candidatas(StatusRegraCandidata.CANDIDATA)
    assert regras[0].total_casos_confirmados == 2
    assert regras[0].status_regra == StatusRegraCandidata.CANDIDATA  # Continua candidata!

    # Caso 3 (mesmo padrão)
    it3, _ = service_isolado.registrar_movimento_para_revisao(
        5555, 17837, "2026-10-17", "20.00", "LAVAGEM DE PISO PISTA", confianca_ia=0.5
    )
    service_isolado.revisar_e_classificar(it3.id, 1, 29031, "OUTRAS MOVIMENTACOES", "revisor1")

    regras = service_isolado.listar_regras_candidatas(StatusRegraCandidata.CANDIDATA)
    assert regras[0].total_casos_confirmados == 3
    assert regras[0].status_regra == StatusRegraCandidata.CANDIDATA  # NÃO é promovida automaticamente!

    # Promoção explícita com autorização humana
    promovida = service_isolado.promover_regra_candidata(regras[0].id, aprovado_por="diretoria")
    assert promovida.status_regra == StatusRegraCandidata.PROMOVIDA
    assert promovida.aprovado_por == "diretoria"


# =====================================================================
# 9. CONCORRÊNCIA IMPEDE REVISÃO CONFLITANTE
# =====================================================================

def test_09_concorrencia_impede_revisao_conflitante(service_isolado: ClassificationReviewService):
    item, _ = service_isolado.registrar_movimento_para_revisao(
        5555, 17837, "2026-10-18", "80.00", "TESTE CONCORRENCIA", confianca_ia=0.5
    )

    # Processo A classifica com sucesso (versao 1 -> 2)
    service_isolado.revisar_e_classificar(
        pendencia_id=item.id,
        versao_esperada=1,
        plano_definitivo_codigo=29031,
        plano_definitivo_descricao="OUTRAS MOVIMENTACOES",
        revisor="revisor_a",
    )

    # Processo B tenta classificar com a versão desatualizada 1
    with pytest.raises(RevisaoConcorrenteErro, match="Conflito de concorrência"):
        service_isolado.revisar_e_classificar(
            pendencia_id=item.id,
            versao_esperada=1,
            plano_definitivo_codigo=158764,
            plano_definitivo_descricao="MARCIO-PROLABORE",
            revisor="revisor_b",
        )


# =====================================================================
# 10. CONTA 198966 PERMANECE BLOQUEADA PARA LANÇAMENTO REAL
# =====================================================================

def test_10_conta_198966_permanece_bloqueada(service_isolado: ClassificationReviewService):
    # 1. Sugestão de 198966 na entrada gera trava e bloqueio
    item, _ = service_isolado.registrar_movimento_para_revisao(
        5555,
        17837,
        "2026-10-19",
        "99.00",
        "SAIDA INDEFINIDA",
        sugestao_plano_codigo=CONTA_TEMPORARIA_CLASSIFICACAO,
    )
    assert item.status == EstadoRevisao.BLOQUEADO
    assert "PLANO_198966_TEMPORARIO_SEM_LANCAMENTO" in item.travas_encontradas

    # 2. Tentativa humana de definir 198966 como plano definitivo é categoricamente rejeitada
    item_pendente, _ = service_isolado.registrar_movimento_para_revisao(
        5555, 17837, "2026-10-19", "50.00", "PENDENTE NORMAL", confianca_ia=0.5
    )
    with pytest.raises(ValueError, match="A conta 198966 é temporária de trânsito"):
        service_isolado.revisar_e_classificar(
            pendencia_id=item_pendente.id,
            versao_esperada=1,
            plano_definitivo_codigo=CONTA_TEMPORARIA_CLASSIFICACAO,
            plano_definitivo_descricao="SAÍDAS PENDENTES DE CLASSIFICAÇÃO",
            revisor="auditor",
        )


# =====================================================================
# 11. ZERO CHAMADAS DE ESCRITA AO ERP (POST, PUT, PATCH, DELETE)
# =====================================================================

def test_11_zero_chamadas_escrita_erp(service_isolado: ClassificationReviewService):
    with patch("httpx.Client.post") as mock_post, \
         patch("httpx.Client.put") as mock_put, \
         patch("httpx.Client.patch") as mock_patch, \
         patch("httpx.Client.delete") as mock_delete:

        # Registrar movimento
        it, _ = service_isolado.registrar_movimento_para_revisao(
            5555, 17837, "2026-10-20", "110.00", "DESPESA PURAMENTE LOCAL", confianca_ia=0.9
        )
        # Revisar movimento
        service_isolado.revisar_e_classificar(it.id, 1, 29031, "OUTRAS MOVIMENTACOES", "auditor")
        # Listar e métricas
        service_isolado.listar_pendencias()
        service_isolado.gerar_metricas_ia()

        # Comprovar 0 chamadas a qualquer método de mutação do ERP
        mock_post.assert_not_called()
        mock_put.assert_not_called()
        mock_patch.assert_not_called()
        mock_delete.assert_not_called()


# =====================================================================
# 12. MÉTRICAS DE ACERTO DA IA
# =====================================================================

def test_12_metricas_acerto_ia(service_isolado: ClassificationReviewService):
    # Caso com acerto da IA
    it1, _ = service_isolado.registrar_movimento_para_revisao(
        5555, 17837, "2026-10-21", "100.00", "DESPESA A",
        sugestao_plano_codigo=158764, confianca_ia=0.8,
    )
    service_isolado.revisar_e_classificar(it1.id, 1, 158764, "MARCIO-PROLABORE", "rev")

    # Caso com erro da IA (humano corrigiu para outro plano)
    it2, _ = service_isolado.registrar_movimento_para_revisao(
        5555, 17837, "2026-10-21", "200.00", "DESPESA B",
        sugestao_plano_codigo=148303, confianca_ia=0.7,
    )
    service_isolado.revisar_e_classificar(it2.id, 1, 29031, "OUTRAS MOVIMENTACOES", "rev")

    metricas = service_isolado.gerar_metricas_ia()
    assert metricas.total_avaliados == 2
    assert metricas.acertos_ia == 1
    assert metricas.taxa_acerto_ia == 50.0
    assert metricas.total_classificados == 2


# =====================================================================
# 13. SANITIZAÇÃO DE DADOS SENSÍVEIS NAS EVIDÊNCIAS
# =====================================================================

def test_13_sanitizacao_evidencias_sensiveis(service_isolado: ClassificationReviewService):
    evidencia_sensivel = "fitid:987654 api_key='secret12345678' cartao: 1234 5678 9012 3456 bearer abcdefgh123456"
    it, _ = service_isolado.registrar_movimento_para_revisao(
        5555, 17837, "2026-10-22", "60.00", "TESTE SANITIZACAO",
        referencia_evidencias=evidencia_sensivel,
        confianca_ia=0.6,
    )
    salvo = service_isolado.obter_pendencia(it.id)
    assert "secret12345678" not in salvo.referencia_evidencias
    assert "abcdefgh123456" not in salvo.referencia_evidencias
    assert "1234 5678 9012 3456" not in salvo.referencia_evidencias
    assert "[REDACTED]" in salvo.referencia_evidencias
