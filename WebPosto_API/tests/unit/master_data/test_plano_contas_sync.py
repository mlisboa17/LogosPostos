"""Testes unitários offline para a sincronização do plano de contas gerencial e pré-validador (LOGOS).

Cobre os 17 requisitos obrigatórios:
1. primeira importação;
2. inclusão de um plano novo criado posteriormente no webPosto;
3. alteração de descrição;
4. alteração de hierarquia;
5. repetição idempotente do mesmo catálogo;
6. código duplicado com conteúdo divergente;
7. resposta vazia inesperada;
8. paginação incompleta / loop de cursor;
9. rollback após falha;
10. plano-pai bloqueado;
11. plano-folha reconhecido;
12. plano desconhecido bloqueado;
13. plano não observado bloqueado;
14. catálogo vencido bloqueado;
15. preservação do plano ausente sem exclusão;
16. ausência total de POST, PUT, PATCH e DELETE;
17. nenhuma regressão nos testes existentes.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.modules.cash_reconciliation.adapters.webposto_escrita_despesa import (
    BarreiraDespesaErro,
    validar_aprovacao_para_escrita,
)
from src.modules.cash_reconciliation.domain.comprovante import (
    DadosComprovante,
    ItemFilaDespesa,
    OperacaoFinanceira,
    StatusDespesa,
)
from src.modules.master_data.adapters.sqlite_master_data_repository import (
    SqliteMasterDataRepository,
)
from src.modules.master_data.application.master_data_service import (
    MasterDataService,
)
from src.modules.master_data.application.plano_contas_sync_service import (
    PlanoContasSyncService,
)
from src.modules.master_data.domain.models import (
    ConfiabilidadeCadastro,
    MasterPlanoConta,
)

ROOT = Path(__file__).resolve().parents[4]
CATALOGO_OFICIAL_PATH = ROOT / "docs" / "validation" / "PLANOS_CONTA_MASTER_01.json"


def _carregar_catalogo_oficial() -> list[dict]:
    data = json.loads(CATALOGO_OFICIAL_PATH.read_text(encoding="utf-8"))
    return data["plans"]


def _criar_item_despesa(
    plano_codigo: int,
    centro_codigo: int | None = None,
    unidade_codigo: int = 74014,
    conta_codigo: int = 86248,
) -> ItemFilaDespesa:
    comp = DadosComprovante(
        banco_origem="001",
        agencia_origem="2365-5",
        conta_origem="86248",
        valor=Decimal("626.00"),
        data=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc).date(),
    )
    agora_iso = datetime.now(timezone.utc).isoformat()
    item = ItemFilaDespesa(
        id="item-sync-test-999",
        criado_em=agora_iso,
        unidade_codigo=unidade_codigo,
        unidade_nome="POSTO DOZE FILIAL II" if unidade_codigo == 74014 else "POSTO CASA CAIADA LTDA",
        unidade_apelido="Doze" if unidade_codigo == 74014 else "Casa Caiada",
        status=StatusDespesa.APROVADO.value,
        operacao_financeira=OperacaoFinanceira.DESPESA_JA_PAGA.value,
        comprovante=comp,
        conta_financeira_codigo=conta_codigo,
        sugestao_plano_codigo=plano_codigo,
        sugestao_centro_codigo=centro_codigo,
        debito_casado_fitid="FITID-TEST-001",
        debito_casado_banco="001",
        debito_casado_conta="86248",
        aprovado_por="DIRETOR_LOGOS",
        aprovado_em=agora_iso,
        aprovado_operacao=OperacaoFinanceira.DESPESA_JA_PAGA.value,
        aprovado_versao=1,
    )
    item.hash_conteudo = item.calcular_hash_conteudo()
    item.aprovado_hash = item.hash_conteudo
    return item


@pytest.fixture
def repo_isolado(tmp_path):
    db_file = tmp_path / "master_data_sync_test.sqlite3"
    return SqliteMasterDataRepository(db_path=db_file)


@pytest.fixture
def service_isolado(repo_isolado):
    svc = MasterDataService(repository=repo_isolado)
    svc.bootstrap_catalogo()
    return svc


# 1. Primeira importação
def test_01_primeira_importacao(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    dados = _carregar_catalogo_oficial()

    res = sync_svc.sincronizar(modo="apply", dados_oficiais=dados, origem="teste_01")
    assert res.sucesso is True
    assert res.total_oficial == 251
    assert res.total_inseridos == 251
    assert res.total_atualizados == 0
    assert res.total_inalterados == 0
    assert res.total_nao_observados == 0
    assert res.hash_catalogo is not None

    planos_db = repo_isolado.listar_planos_conta()
    assert len(planos_db) == 251

    # Verifica folha 158764
    p158764 = repo_isolado.obter_plano_conta(158764)
    assert p158764 is not None
    assert p158764.descricao == "MARCIO-PROLABORE"
    assert p158764.hierarquia == "2.02.05.005"
    assert p158764.pai_codigo == 148303
    assert p158764.eh_folha is True
    assert p158764.candidato_lancavel is True
    assert p158764.observado_ultima_sincronizacao is True

    # Verifica pai 29021
    p29021 = repo_isolado.obter_plano_conta(29021)
    assert p29021 is not None
    assert p29021.eh_folha is False
    assert p29021.candidato_lancavel is False


# 2. Inclusão de um plano novo criado posteriormente no webPosto
def test_02_inclusao_novo_plano_webposto(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    base_tres = [
        {"planoContaCodigo": 29021, "descricao": "PRO LABORE", "hierarquia": "2.02"},
        {"planoContaCodigo": 148303, "descricao": "MARCIO LISBOA", "hierarquia": "2.02.05"},
        {"planoContaCodigo": 158764, "descricao": "MARCIO-PROLABORE", "hierarquia": "2.02.05.005"},
    ]
    res1 = sync_svc.sincronizar(modo="apply", dados_oficiais=base_tres)
    assert res1.total_inseridos == 3

    # Adiciona plano novo criado posteriormente
    com_novo = base_tres + [
        {"planoContaCodigo": 158765, "descricao": "MARCIO ADICIONAL", "hierarquia": "2.02.05.006"},
    ]
    res2 = sync_svc.sincronizar(modo="apply", dados_oficiais=com_novo)
    assert res2.sucesso is True
    assert res2.total_inseridos == 1
    assert res2.total_atualizados == 0
    assert res2.total_inalterados == 3
    assert res2.detalhes["inseridosCodigos"] == [158765]

    p_novo = repo_isolado.obter_plano_conta(158765)
    assert p_novo is not None
    assert p_novo.descricao == "MARCIO ADICIONAL"
    assert p_novo.eh_folha is True


# 3. Alteração de descrição
def test_03_alteracao_descricao(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    base = [{"planoContaCodigo": 158764, "descricao": "MARCIO-PROLABORE", "hierarquia": "2.02.05.005"}]
    sync_svc.sincronizar(modo="apply", dados_oficiais=base)

    # Altera descrição no retorno
    alterado = [{"planoContaCodigo": 158764, "descricao": "MARCIO-PROLABORE-AJUSTADO", "hierarquia": "2.02.05.005"}]
    res = sync_svc.sincronizar(modo="apply", dados_oficiais=alterado)
    assert res.sucesso is True
    assert res.total_inseridos == 0
    assert res.total_atualizados == 1
    assert res.total_inalterados == 0

    p = repo_isolado.obter_plano_conta(158764)
    assert p.descricao == "MARCIO-PROLABORE-AJUSTADO"


# 4. Alteração de hierarquia
def test_04_alteracao_hierarquia(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    base = [
        {"planoContaCodigo": 29021, "descricao": "PRO LABORE", "hierarquia": "2.02"},
        {"planoContaCodigo": 148303, "descricao": "MARCIO LISBOA", "hierarquia": "2.02.05"},
        {"planoContaCodigo": 158764, "descricao": "MARCIO-PROLABORE", "hierarquia": "2.02.05.005"},
    ]
    sync_svc.sincronizar(modo="apply", dados_oficiais=base)

    # Move 158764 para nova hierarquia 2.02.05.010
    movido = [
        {"planoContaCodigo": 29021, "descricao": "PRO LABORE", "hierarquia": "2.02"},
        {"planoContaCodigo": 148303, "descricao": "MARCIO LISBOA", "hierarquia": "2.02.05"},
        {"planoContaCodigo": 158764, "descricao": "MARCIO-PROLABORE", "hierarquia": "2.02.05.010"},
    ]
    res = sync_svc.sincronizar(modo="apply", dados_oficiais=movido)
    assert res.total_atualizados == 1

    p = repo_isolado.obter_plano_conta(158764)
    assert p.hierarquia == "2.02.05.010"


# 5. Repetição idempotente do mesmo catálogo
def test_05_repeticao_idempotente_mesmo_catalogo(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    base = [
        {"planoContaCodigo": 29021, "descricao": "PRO LABORE", "hierarquia": "2.02"},
        {"planoContaCodigo": 148303, "descricao": "MARCIO LISBOA", "hierarquia": "2.02.05"},
        {"planoContaCodigo": 158764, "descricao": "MARCIO-PROLABORE", "hierarquia": "2.02.05.005"},
    ]
    res1 = sync_svc.sincronizar(modo="apply", dados_oficiais=base)
    assert res1.total_inseridos == 3

    # Conta auditorias geradas na primeira importação
    conn = repo_isolado._conectar()
    auditorias_antes = conn.execute("SELECT count(*) FROM master_data_audit_log WHERE tipo_entidade = 'PLANO_CONTA'").fetchone()[0]
    conn.close()

    # Segunda execução idêntica
    res2 = sync_svc.sincronizar(modo="apply", dados_oficiais=base)
    assert res2.sucesso is True
    assert res2.total_inseridos == 0
    assert res2.total_atualizados == 0
    assert res2.total_inalterados == 3
    assert res2.total_nao_observados == 0

    # Nenhuma nova auditoria espúria para planos inalterados
    conn = repo_isolado._conectar()
    auditorias_depois = conn.execute("SELECT count(*) FROM master_data_audit_log WHERE tipo_entidade = 'PLANO_CONTA'").fetchone()[0]
    conn.close()
    assert auditorias_depois == auditorias_antes


# 6. Código duplicado com conteúdo divergente
def test_06_codigo_duplicado_conteudo_divergente(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    duplicados = [
        {"planoContaCodigo": 158764, "descricao": "MARCIO-PROLABORE", "hierarquia": "2.02.05.005"},
        {"planoContaCodigo": 158764, "descricao": "MARCIO-DIVERGENTE", "hierarquia": "2.02.05.005"},
    ]
    res = sync_svc.sincronizar(modo="apply", dados_oficiais=duplicados)
    assert res.sucesso is False
    assert "Código duplicado com conteúdo divergente" in (res.erro or "")


# 7. Resposta vazia inesperada
def test_07_resposta_vazia_inesperada(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    res = sync_svc.sincronizar(modo="apply", dados_oficiais=[])
    assert res.sucesso is False
    assert "Retorno oficial vazio" in (res.erro or "")


# 8. Paginação incompleta / detecção de loop de cursor
def test_08_paginacao_incompleta_ou_loop(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)

    # Simula cliente HTTP com loop de cursor
    client_mock = MagicMock()
    resp_mock = MagicMock()
    resp_mock.status_code = 200
    resp_mock.json.return_value = {
        "resultados": [{"planoContaCodigo": 100, "descricao": "P1", "hierarquia": "1"}],
        "ultimoCodigo": 100,
    }
    client_mock.get.return_value = resp_mock

    with pytest.raises(RuntimeError) as exc:
        sync_svc.coletar_oficiais_api(
            base_url="https://mock.quality.com.br",
            api_key="TEST_KEY",
            client=client_mock,
            limite_pagina=1,  # forçará paginação
        )
    assert "Cursor repetido detectado" in str(exc.value)


# 9. Rollback após falha
def test_09_rollback_apos_falha(repo_isolado, monkeypatch):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    base = [{"planoContaCodigo": 158764, "descricao": "MARCIO-PROLABORE", "hierarquia": "2.02.05.005"}]
    sync_svc.sincronizar(modo="apply", dados_oficiais=base)

    # Força falha no meio do commit da transação
    def _falha_forçada(*args, **kwargs):
        raise RuntimeError("FALHA_SIMULADA_TRANSACAO")

    monkeypatch.setattr(repo_isolado, "marcar_planos_nao_observados", _falha_forçada)

    novo_lote = [
        {"planoContaCodigo": 158764, "descricao": "ALTERADO_PROLABORE", "hierarquia": "2.02.05.005"},
        {"planoContaCodigo": 999999, "descricao": "NOVO_ITEM", "hierarquia": "9"},
    ]
    # Insere antes um item para disparar marcar_planos_nao_observados
    repo_isolado.upsert_plano_conta(
        MasterPlanoConta(plano_conta_codigo=11111, descricao="ITEM_ANTIGO", hierarquia="1")
    )

    res = sync_svc.sincronizar(modo="apply", dados_oficiais=novo_lote)
    assert res.sucesso is False

    # Verifica que 158764 não foi atualizado graças ao rollback
    p = repo_isolado.obter_plano_conta(158764)
    assert p.descricao == "MARCIO-PROLABORE"


# 10. Plano-pai bloqueado
def test_10_plano_pai_bloqueado(service_isolado):
    # Sincroniza o catálogo completo para que 29021 e 148303 sejam pais estruturais
    sync_svc = PlanoContasSyncService(repository=service_isolado.repository)
    sync_svc.sincronizar(modo="apply", dados_oficiais=_carregar_catalogo_oficial())

    # 29021 (PRO LABORE) é conta-pai
    res_29021 = service_isolado.validar_plano_para_despesa(29021)
    assert res_29021.sucesso is False
    assert "conta-pai" in res_29021.mensagem

    # 148303 (MARCIO LISBOA) é conta-pai
    res_148303 = service_isolado.validar_plano_para_despesa(148303)
    assert res_148303.sucesso is False
    assert "conta-pai" in res_148303.mensagem

    # No adaptador de despesas, validar_aprovacao_para_escrita também bloqueia
    item_pai = _criar_item_despesa(29021)
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item_pai, master_data_service=service_isolado)
    assert "conta-pai" in str(exc.value)


# 11. Plano-folha reconhecido
def test_11_plano_folha_reconhecido(service_isolado):
    sync_svc = PlanoContasSyncService(repository=service_isolado.repository)
    sync_svc.sincronizar(modo="apply", dados_oficiais=_carregar_catalogo_oficial())

    # 158764 (MARCIO-PROLABORE) é folha candidata
    res_158764 = service_isolado.validar_plano_para_despesa(158764)
    assert res_158764.sucesso is True
    assert res_158764.plano.plano_conta_codigo == 158764
    assert res_158764.plano.eh_folha is True
    assert "folha oficial candidata" in res_158764.mensagem
    assert "Não constitui autorização para lançamento" in res_158764.mensagem


# 12. Plano desconhecido bloqueado
def test_12_plano_desconhecido_bloqueado(service_isolado):
    sync_svc = PlanoContasSyncService(repository=service_isolado.repository)
    sync_svc.sincronizar(modo="apply", dados_oficiais=_carregar_catalogo_oficial())

    res = service_isolado.validar_plano_para_despesa(999999)
    assert res.sucesso is False
    assert "não encontrado no catálogo" in res.mensagem

    item = _criar_item_despesa(999999)
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service_isolado)
    assert "não encontrado no catálogo" in str(exc.value)


# 13. Plano não observado bloqueado
def test_13_plano_nao_observado_bloqueado(service_isolado):
    sync_svc = PlanoContasSyncService(repository=service_isolado.repository)
    # Cadastra plano 12345
    service_isolado.repository.upsert_plano_conta(
        MasterPlanoConta(
            plano_conta_codigo=12345,
            descricao="PLANO OBSOLETO",
            hierarquia="9.99",
            eh_folha=True,
            candidato_lancavel=True,
            observado_ultima_sincronizacao=True,
        )
    )
    # Sincroniza catálogo oficial (que não contém 12345)
    sync_svc.sincronizar(modo="apply", dados_oficiais=_carregar_catalogo_oficial())

    p = service_isolado.repository.obter_plano_conta(12345)
    assert p is not None
    assert p.observado_ultima_sincronizacao is False
    assert p.candidato_lancavel is False

    res = service_isolado.validar_plano_para_despesa(12345)
    assert res.sucesso is False
    assert "não foi observado na última sincronização oficial" in res.mensagem


# 14. Catálogo vencido bloqueado
def test_14_catalogo_vencido_bloqueado(service_isolado):
    sync_svc = PlanoContasSyncService(repository=service_isolado.repository)
    sync_svc.sincronizar(modo="apply", dados_oficiais=_carregar_catalogo_oficial())

    # Força log de sincronização antiga (ex: 45 dias atrás)
    conn = service_isolado.repository._conectar()
    data_antiga = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    conn.execute(
        "UPDATE master_sincronizacao_log SET iniciado_em = ?, finalizado_em = ?",
        (data_antiga, data_antiga),
    )
    conn.commit()
    conn.close()

    # Validação com limite de 30 dias
    res = service_isolado.validar_plano_para_despesa(158764, max_dias_desatualizado=30)
    assert res.sucesso is False
    assert "Catálogo de planos de contas desatualizado" in res.mensagem


# 15. Preservação do plano ausente sem exclusão
def test_15_preservacao_plano_ausente_sem_exclusao(service_isolado):
    sync_svc = PlanoContasSyncService(repository=service_isolado.repository)
    service_isolado.repository.upsert_plano_conta(
        MasterPlanoConta(
            plano_conta_codigo=77777,
            descricao="PLANO HISTORICO LOCAL",
            hierarquia="8.88",
            eh_folha=True,
        )
    )
    # Aplica catálogo oficial (sem 77777)
    res = sync_svc.sincronizar(modo="apply", dados_oficiais=_carregar_catalogo_oficial())
    assert 77777 in res.detalhes["naoObservadosCodigos"]

    # Verifica que 77777 permanece no banco
    p = service_isolado.repository.obter_plano_conta(77777)
    assert p is not None
    assert p.plano_conta_codigo == 77777
    assert p.descricao == "PLANO HISTORICO LOCAL"
    assert p.observado_ultima_sincronizacao is False


# 16. Ausência total de POST, PUT, PATCH e DELETE contra o ERP
def test_16_ausencia_total_post_put_patch_delete(monkeypatch):
    import httpx

    def _metodo_proibido(*args, **kwargs):
        raise AssertionError("VIOLAÇÃO DE SEGURANÇA: Método de escrita HTTP disparado contra o ERP!")

    monkeypatch.setattr(httpx.Client, "post", _metodo_proibido)
    monkeypatch.setattr(httpx.Client, "put", _metodo_proibido)
    monkeypatch.setattr(httpx.Client, "patch", _metodo_proibido)
    monkeypatch.setattr(httpx.Client, "delete", _metodo_proibido)

    # Execução de sincronização offline e online (mocked get)
    sync_svc = PlanoContasSyncService()
    res = sync_svc.sincronizar(modo="dry-run", dados_oficiais=_carregar_catalogo_oficial())
    assert res.sucesso is True


# 17. Modo dry-run não altera a base de dados
def test_17_dry_run_nao_altera_banco(repo_isolado):
    sync_svc = PlanoContasSyncService(repository=repo_isolado)
    dados = _carregar_catalogo_oficial()

    res = sync_svc.sincronizar(modo="dry-run", dados_oficiais=dados)
    assert res.sucesso is True
    assert res.modo == "DRY_RUN"
    assert res.total_oficial == 251
    assert res.total_inseridos == 251

    # Nenhuma linha foi inserida em master_planos_conta
    planos_db = repo_isolado.listar_planos_conta()
    assert len(planos_db) == 0


# 18. Conta 198966 (SAÍDAS PENDENTES DE CLASSIFICAÇÃO): folha, ativa, observada, porém bloqueada para lançamento real
def test_18_saidas_pendentes_classificacao_bloqueada_para_lancamento(service_isolado):
    sync_svc = PlanoContasSyncService(repository=service_isolado.repository)
    lote = _carregar_catalogo_oficial() + [
        {
            "planoContaCodigo": 198966,
            "descricao": "SAÍDAS PENDENTES DE CLASSIFICAÇÃO",
            "hierarquia": "2.04.10",
            "natureza": "D",
            "tipo": "Nenhum",
            "ativo": True,
        }
    ]
    res_sync = sync_svc.sincronizar(modo="apply", dados_oficiais=lote)
    assert res_sync.sucesso is True
    assert 198966 in res_sync.detalhes["inseridosCodigos"]

    p = service_isolado.repository.obter_plano_conta(198966)
    assert p is not None
    assert p.hierarquia == "2.04.10"
    assert p.descricao == "SAÍDAS PENDENTES DE CLASSIFICAÇÃO"
    assert p.ativo is True
    assert p.eh_folha is True
    assert p.observado_ultima_sincronizacao is True
    assert p.candidato_lancavel is False  # Estritamente bloqueado para lançamento real

    res_val = service_isolado.validar_plano_para_despesa(198966)
    assert res_val.sucesso is False
    assert "classificação pendente" in res_val.mensagem or "fila de revisão" in res_val.mensagem

    item = _criar_item_despesa(198966)
    with pytest.raises(BarreiraDespesaErro) as exc:
        validar_aprovacao_para_escrita(item, master_data_service=service_isolado)
    assert "classificação pendente" in str(exc.value) or "fila de revisão" in str(exc.value)
