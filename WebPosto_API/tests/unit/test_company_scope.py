import json

import pytest

from src.core.company_scope import (
    NEW_PROCESS_COMPANY_CODES,
    is_company_identity_validated,
    is_new_process_company,
    validate_new_process_company_codes,
    validate_sensitive_company_restrictions,
)
from src.modules.cash_reconciliation.config import carregar_unidades, carregar_unidades_historicas


def test_new_process_scope_contains_only_authorized_company_codes():
    assert NEW_PROCESS_COMPANY_CODES == frozenset({5555, 11495, 118508, 74014})
    assert all(is_new_process_company(code) for code in NEW_PROCESS_COMPANY_CODES)
    assert not is_new_process_company(46433)
    assert not is_new_process_company(5558)
    assert not is_new_process_company(7)


def test_new_process_scope_rejects_out_of_scope_codes():
    with pytest.raises(ValueError, match="46433"):
        validate_new_process_company_codes([5555, 46433])


def test_cash_reconciliation_config_rejects_out_of_scope_company(tmp_path):
    config_path = tmp_path / "units.json"
    config_path.write_text(json.dumps({"unidades": [{
        "empresa_codigo": 5558, "nome": "Historica", "chave_env": "TESTE", "destinos": [],
    }]}), encoding="utf-8")

    with pytest.raises(ValueError, match="5558"):
        carregar_unidades(config_path)
    assert 5558 in carregar_unidades_historicas(config_path)


@pytest.mark.parametrize("codigo", [118508, 74014])
def test_in_scope_does_not_validate_pending_identity(codigo):
    assert is_new_process_company(codigo)
    assert not is_company_identity_validated(codigo, cadastro_confirmado=True)
    with pytest.raises(ValueError, match="identidade pendente"):
        validate_sensitive_company_restrictions(codigo)


def test_cadastro_pendente_is_not_validated():
    assert not is_company_identity_validated(5555, cadastro_confirmado=False)
    assert is_company_identity_validated(5555, cadastro_confirmado=True)


@pytest.mark.parametrize("dados", [{}, {"unidades": None}, {"unidades": [{}]}])
def test_invalid_config_fails_closed(tmp_path, dados):
    caminho = tmp_path / "units.json"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(ValueError, match="Configuração inválida"):
        carregar_unidades(caminho)


@pytest.mark.parametrize("codigo", ["5555", 5555.0, True])
def test_new_process_config_does_not_coerce_company_codes(tmp_path, codigo):
    caminho = tmp_path / "units.json"
    caminho.write_text(json.dumps({"unidades": [{"empresa_codigo": codigo}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="fora do escopo"):
        carregar_unidades(caminho)
