from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from ..adapters.webposto_http import WebPostoErro
from ..adapters.persistencia import PersistenciaErro, carregar_dia
from ..application.auditar_fechamento import auditar_unidade
from ..application.recebimentos import conciliar_recebimentos
from ..application.serializacao import serializar_fechamento
from ..config import carregar_unidades
from ..domain.fechamento import ResultadoAuditoria
from ..domain.models import Proveniencia
from ..domain.recebimentos import ResultadoRecebimentos

router = APIRouter(prefix="/api/v1/cash-audit", tags=["cash-audit"])


@router.get("/recebimentos", response_model=ResultadoRecebimentos)
async def obter_recebimentos(
    unidade: int = Query(...),
    dia: date = Query(...),
) -> ResultadoRecebimentos:
    if unidade not in carregar_unidades():
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")
    try:
        persistido = carregar_dia(unidade, dia)
    except PersistenciaErro:
        raise HTTPException(status_code=500, detail="Falha ao ler auditoria persistida.") from None
    if persistido is not None:
        return persistido.recebimentos
    return await conciliar_recebimentos(unidade, dia)


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
        dias = [inicio + timedelta(days=indice) for indice in range((fim - inicio).days + 1)]
        persistidos = {dia: carregar_dia(unidade, dia) for dia in dias}
        if not any(persistidos.values()):
            resultado = await auditar_unidade(unidade, inicio, fim)
            return serializar_fechamento(resultado)
        resultados = []
        for dia in dias:
            persistido = persistidos[dia]
            if persistido is None:
                resultados.append(await auditar_unidade(unidade, dia, dia))
            elif persistido.fechamento is not None:
                resultados.append(persistido.fechamento)
            else:
                raise HTTPException(status_code=502, detail="Fechamento persistido indisponível.")
        proveniencias = [resultado.proveniencia for resultado in resultados]
        regras = sorted({p.versao_regra for p in proveniencias})
        resultado = ResultadoAuditoria(
            empresa_codigo=unidade, inicio=inicio, fim=fim,
            caixas=tuple(sorted(
                (caixa for resultado in resultados for caixa in resultado.caixas),
                key=lambda c: (c.caixa.data, c.caixa.abertura),
            )),
            proveniencia=Proveniencia(
                execucao_id=uuid.uuid4().hex, executado_em=datetime.now(),
                versao_regra=" + ".join(regras),
                fonte_sangrias=" + ".join(sorted({p.fonte_sangrias for p in proveniencias})),
                extratos=(), outras_fontes=tuple(sorted({fonte for p in proveniencias for fonte in p.outras_fontes})),
            ),
        )
        payload = serializar_fechamento(resultado)
        payload["execucoes"] = [p.model_dump(mode="json") for p in proveniencias]
        return payload
    except PersistenciaErro:
        raise HTTPException(status_code=500, detail="Falha ao ler auditoria persistida.") from None
    except WebPostoErro:
        raise HTTPException(
            status_code=502,
            detail="Falha ao consultar os dados operacionais.",
        ) from None


@router.get("/unidades")
def listar_unidades() -> list[dict[str, int | str]]:
    return [
        {"empresa_codigo": unidade.empresa_codigo, "nome": unidade.nome}
        for unidade in carregar_unidades().values()
    ]
