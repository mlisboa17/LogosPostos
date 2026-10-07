from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..adapters.webposto_http import WebPostoErro
from ..application.auditar_fechamento import auditar_unidade
from ..config import carregar_unidades

router = APIRouter(prefix="/api/v1/cash-audit", tags=["cash-audit"])


@router.get("/fechamento")
async def obter_fechamento(
    unidade: int = Query(...),
    inicio: date = Query(...),
    fim: date = Query(...),
) -> dict:
    if fim < inicio or (fim - inicio).days > 30:
        raise HTTPException(
            status_code=422,
            detail="O período deve ser válido e conter no máximo 31 dias.",
        )

    unidades = carregar_unidades()
    if unidade not in unidades:
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")

    try:
        resultado = await auditar_unidade(unidade, inicio, fim)
    except WebPostoErro:
        raise HTTPException(
            status_code=502,
            detail="Falha ao consultar os dados operacionais.",
        ) from None

    payload = resultado.model_dump(mode="json")
    payload["quebra_total"] = resultado.quebra_total
    for auditoria, caixa_payload in zip(resultado.caixas, payload["caixas"]):
        caixa_payload["quebra"] = auditoria.quebra
        caixa_payload["severidade"] = (
            auditoria.severidade.value if auditoria.severidade is not None else None
        )
    return payload


@router.get("/unidades")
def listar_unidades() -> list[dict[str, int | str]]:
    return [
        {"empresa_codigo": unidade.empresa_codigo, "nome": unidade.nome}
        for unidade in carregar_unidades().values()
    ]
