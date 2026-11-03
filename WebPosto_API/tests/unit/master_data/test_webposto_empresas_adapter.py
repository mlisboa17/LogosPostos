from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

try:
    from src.core.company_scope import is_company_identity_validated
    from src.modules.master_data.adapters.sqlite_master_data_repository import (
        SqliteMasterDataRepository,
    )
    from src.modules.master_data.application.master_data_service import MasterDataService
    from src.modules.master_data.application.webposto_empresas_adapter import (
        parse_empresas_response,
    )
    from src.modules.master_data.domain.models import (
        ConfiabilidadeCadastro,
        MasterEmpresa,
    )
except ImportError:
    from WebPosto_API.src.core.company_scope import is_company_identity_validated
    from WebPosto_API.src.modules.master_data.adapters.sqlite_master_data_repository import (
        SqliteMasterDataRepository,
    )
    from WebPosto_API.src.modules.master_data.application.master_data_service import (
        MasterDataService,
    )
    from WebPosto_API.src.modules.master_data.application.webposto_empresas_adapter import (
        parse_empresas_response,
    )
    from WebPosto_API.src.modules.master_data.domain.models import (
        ConfiabilidadeCadastro,
        MasterEmpresa,
    )


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "empresas_response_sanitized.json"


@pytest.fixture
def service(tmp_path):
    repository = SqliteMasterDataRepository(db_path=tmp_path / "master_data.sqlite3")
    return MasterDataService(repository=repository)


def _resposta(*registros, ultimo_codigo=None):
    return {"resultados": list(registros), "ultimoCodigo": ultimo_codigo}


def _registro(
    codigo,
    *,
    cnpj="04.284.939/0001-86",
    razao="AUTO POSTO CASA CAIADA LTDA",
    fantasia="AP CASA CAIADA",
):
    return {
        "empresaCodigo": codigo,
        "codigo": codigo,
        "empresaCodigoExterno": None,
        "cnpj": cnpj,
        "razao": razao,
        "fantasia": fantasia,
        "tipoImposto": "R",
    }


def _fixture_response():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return fixture["response"]


def test_fixture_oficial_preserva_envelope_campos_e_tipos():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    response = parse_empresas_response(fixture["response"])

    assert response.ultimo_codigo == 11495
    assert [row.empresa_codigo for row in response.resultados] == [5555, 11495]
    assert response.resultados[0].empresa_codigo_externo is None
    assert (
        response.resultados[0].model_dump(by_alias=True, exclude_unset=True)["tipoImposto"] == "R"
    )
    assert (
        response.resultados[0].model_dump(by_alias=True, exclude_unset=True)["logradouro"]
        == "AVENIDA GOVERNADOR CARLOS DE LIMA"
    )
    assert response.model_dump(by_alias=True)["ultimoCodigo"] == 11495
    assert response.model_extra == {}


def test_importa_fixture_preservando_cod_web_e_flags_existentes(service):
    service.repository.upsert_empresa(
        MasterEmpresa(
            empresa_codigo=5555,
            cod_web=9090,
            razao_social="AUTO POSTO CASA CAIADA LTDA",
            nome_fantasia="AP Casa Caiada",
            cnpj="04.284.939/0001-86",
            ativo=True,
            autorizado_despesa=False,
            usa_mais_pagamentos=True,
            origem_dado="cadastro_existente",
        )
    )
    service.repository.upsert_empresa(
        MasterEmpresa(
            empresa_codigo=11495,
            cod_web=9191,
            razao_social="RIO DOCE COMERCIO E SERVICOS LTDA",
            nome_fantasia="Posto VIP",
            cnpj="03.008.754/0001-86",
            ativo=True,
            autorizado_despesa=False,
            origem_dado="cadastro_existente",
        )
    )

    first = service.importar_empresas_webposto(_fixture_response())
    audit_count = len(service.repository.listar_auditoria("EMPRESA"))
    second = service.importar_empresas_webposto(_fixture_response())

    assert first["recebidas"] == 2
    assert first["atualizadas"] == 2
    assert second["inalteradas"] == 2
    assert len(service.repository.listar_auditoria("EMPRESA")) == audit_count
    assert service.repository.obter_empresa(5555).cod_web == 9090
    assert service.repository.obter_empresa(11495).cod_web == 9191
    assert not service.repository.obter_empresa(5555).autorizado_despesa
    assert not service.repository.obter_empresa(11495).autorizado_despesa
    assert not hasattr(service.repository.obter_empresa(5555), "tipo_imposto")


def test_campos_nulos_ou_ausentes_nao_sobrescrevem_cadastro(service):
    service.repository.upsert_empresa(
        MasterEmpresa(
            empresa_codigo=5555,
            cod_web=5555,
            razao_social="AUTO POSTO CASA CAIADA LTDA",
            nome_fantasia="AP Casa Caiada",
            cnpj="04.284.939/0001-86",
            origem_dado="cadastro_existente",
        )
    )
    resposta = _resposta(
        {
            "empresaCodigo": 5555,
            "empresaCodigoExterno": None,
            "codigo": 9999,
        },
        ultimo_codigo=5555,
    )

    service.importar_empresas_webposto(resposta)
    empresa = service.repository.obter_empresa(5555)

    assert empresa.cnpj == "04.284.939/0001-86"
    assert empresa.razao_social == "AUTO POSTO CASA CAIADA LTDA"
    assert empresa.nome_fantasia == "AP Casa Caiada"
    assert empresa.cod_web == 5555


def test_cnpj_divergente_bloqueia_lote_sem_alteracoes(service):
    original = MasterEmpresa(
        empresa_codigo=5555,
        cod_web=5555,
        razao_social="AUTO POSTO CASA CAIADA LTDA",
        nome_fantasia="AP Casa Caiada",
        cnpj="04.284.939/0001-86",
        origem_dado="cadastro_existente",
    )
    service.repository.upsert_empresa(original)
    audits_before = len(service.repository.listar_auditoria("EMPRESA"))

    with pytest.raises(ValueError, match="diverge no campo cnpj"):
        service.importar_empresas_webposto(_resposta(_registro(5555, cnpj="03.008.754/0001-86")))

    assert service.repository.obter_empresa(5555) == original
    assert len(service.repository.listar_auditoria("EMPRESA")) == audits_before


def test_empresa_fora_do_escopo_nao_e_importada(service):
    with pytest.raises(ValueError, match="fora do escopo"):
        service.importar_empresas_webposto(_resposta(_registro(5558)))

    assert service.repository.obter_empresa(5558) is None
    assert service.repository.listar_auditoria("EMPRESA") == []


def test_empresa_ausente_do_master_nao_cria_flags_inventadas(service):
    source = _registro(
        74014,
        cnpj="52.308.604/0002-84",
        razao="POSTO DOZE COMERCIO DE COMBUSTIVEIS E DERIVADOS DE PETROLEO",
        fantasia="Posto Doze Filial II",
    )

    with pytest.raises(ValueError, match="não existe no Master Data"):
        service.importar_empresas_webposto(_resposta(source))

    assert service.repository.obter_empresa(74014) is None
    assert service.repository.listar_auditoria("EMPRESA") == []


def test_identidade_pendente_existente_nao_e_promovida(service):
    existente = MasterEmpresa(
        empresa_codigo=74014,
        cod_web=77,
        razao_social="POSTO DOZE COMERCIO DE COMBUSTIVEIS E DERIVADOS DE PETROLEO",
        nome_fantasia="Posto Doze Filial II",
        cnpj="52.308.604/0002-84",
        autorizado_despesa=False,
        confiabilidade=ConfiabilidadeCadastro.PENDENTE,
    )
    service.repository.upsert_empresa(existente)
    source = _registro(
        74014,
        cnpj=existente.cnpj,
        razao=existente.razao_social,
        fantasia=existente.nome_fantasia,
    )

    service.importar_empresas_webposto(_resposta(source))
    empresa = service.repository.obter_empresa(74014)

    assert empresa.confiabilidade == ConfiabilidadeCadastro.PENDENTE
    assert not empresa.autorizado_despesa
    assert empresa.cod_web == 77
    assert not is_company_identity_validated(
        74014, cadastro_confirmado=empresa.confiabilidade == ConfiabilidadeCadastro.CONFIRMADO
    )


def test_pagina_vazia_preserva_historico_e_nao_gera_auditoria(service):
    historica = MasterEmpresa(
        empresa_codigo=5558,
        cod_web=7,
        razao_social="REAL RECIFE LTDA",
        nome_fantasia="Posto Real",
        cnpj="24.156.978/0001-05",
        confiabilidade=ConfiabilidadeCadastro.HISTORICO,
        origem_dado="historico",
    )
    service.repository.upsert_empresa(historica, origem_auditoria="historico")
    audits_before = len(service.repository.listar_auditoria("EMPRESA"))

    resultado = service.importar_empresas_webposto({"resultados": [], "ultimoCodigo": None})

    assert resultado["recebidas"] == 0
    assert resultado["ultimoCodigo"] is None
    assert service.repository.obter_empresa(5558) == historica
    assert len(service.repository.listar_auditoria("EMPRESA")) == audits_before


def test_falha_no_meio_do_lote_faz_rollback_de_cadastro_e_auditoria(service, monkeypatch):
    rows = _fixture_response()["resultados"]
    empresas_antes = {}
    for row in rows:
        empresa = MasterEmpresa(
            empresa_codigo=row["empresaCodigo"],
            cod_web=None,
            razao_social=row["razao"],
            nome_fantasia=row["fantasia"],
            cnpj=row["cnpj"],
            origem_dado="fixture_seed",
        )
        service.repository.upsert_empresa(empresa)
        empresas_antes[empresa.empresa_codigo] = empresa
    auditorias_antes = len(service.repository.listar_auditoria("EMPRESA"))
    original_upsert = service.repository._upsert_empresa_conn
    calls = 0

    def falhar_no_segundo(conn, empresa, origem_auditoria, *, ignorar_inalterada=False):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.IntegrityError("falha controlada de teste")
        return original_upsert(
            conn,
            empresa,
            origem_auditoria,
            ignorar_inalterada=ignorar_inalterada,
        )

    monkeypatch.setattr(service.repository, "_upsert_empresa_conn", falhar_no_segundo)

    with pytest.raises(sqlite3.IntegrityError, match="falha controlada"):
        service.importar_empresas_webposto(_fixture_response())

    for codigo, empresa in empresas_antes.items():
        assert service.repository.obter_empresa(codigo) == empresa
    assert len(service.repository.listar_auditoria("EMPRESA")) == auditorias_antes
