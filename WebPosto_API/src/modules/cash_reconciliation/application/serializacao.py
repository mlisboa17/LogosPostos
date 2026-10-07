"""Campos calculados de fechamento no contrato externo, sem alterar o dominio."""
from __future__ import annotations

from ..domain.fechamento import ResultadoAuditoria


def serializar_fechamento(resultado: ResultadoAuditoria) -> dict:
    payload = resultado.model_dump(mode="json")
    payload["quebra_total"] = str(resultado.quebra_total)
    for auditoria, caixa_payload in zip(resultado.caixas, payload["caixas"]):
        caixa_payload["quebra"] = str(auditoria.quebra)
        caixa_payload["severidade"] = auditoria.severidade.value if auditoria.severidade is not None else None
    return payload
