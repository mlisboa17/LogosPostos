import pytest
from fastapi import HTTPException

from src.presentation.security import require_admin_token, require_consumer_token


def test_sem_token_configurado_recusa(monkeypatch):
    monkeypatch.delenv("CONSUMER_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e:
        require_consumer_token("dev-consumer-token")  # valor antigo publico nao e mais aceito
    assert e.value.status_code == 503


def test_token_errado_e_certo(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "t-forte-123")
    with pytest.raises(HTTPException) as e:
        require_admin_token("outro")
    assert e.value.status_code == 401
    assert require_admin_token("t-forte-123") is None
