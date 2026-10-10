from __future__ import annotations

import asyncio
import calendar
import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from ..adapters.webposto_http import WebPostoErro
from ..adapters.persistencia import PersistenciaErro, carregar_dia
from ..application.auditar_fechamento import auditar_unidade
from ..application.reincidencia import agregar_reincidencia
from ..application.recebimentos import conciliar_recebimentos
from ..application.serializacao import serializar_fechamento
from ..config import carregar_unidades
from ..domain.fechamento import ResultadoAuditoria
from ..domain.models import Proveniencia
from ..domain.recebimentos import ResultadoRecebimentos
from ..domain.tempo import agora
from ...webposto_integration.funcionarios import buscar_nomes_funcionarios

router = APIRouter(prefix="/api/v1/cash-audit", tags=["cash-audit"])
logger = logging.getLogger(__name__)
TIMEOUT_FECHAMENTO = 180


async def _auditar_com_limite(unidade: int, inicio: date, fim: date, prazo: float) -> ResultadoAuditoria:
    try:
        restante = max(0, prazo - asyncio.get_running_loop().time())
        return await asyncio.wait_for(auditar_unidade(unidade, inicio, fim), timeout=restante)
    except TimeoutError:
        logger.warning("Tempo limite do fechamento unidade=%s", unidade)
        raise HTTPException(status_code=504, detail="Tempo limite ao consultar fechamento. Reduza o período e tente novamente.") from None


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
        prazo = asyncio.get_running_loop().time() + TIMEOUT_FECHAMENTO
        dias = [inicio + timedelta(days=indice) for indice in range((fim - inicio).days + 1)]
        persistidos = {dia: carregar_dia(unidade, dia) for dia in dias}
        if not any(persistidos.values()):
            resultado = await _auditar_com_limite(unidade, inicio, fim, prazo)
            return serializar_fechamento(resultado)
        resultados = []
        bloco: list[date] = []  # dias seguidos sem resultado gravado: 1 consulta ao ERP por bloco, nao por dia

        async def consultar_bloco() -> None:
            if bloco:
                resultados.append(await _auditar_com_limite(unidade, bloco[0], bloco[-1], prazo))
                bloco.clear()

        for dia in dias:
            persistido = persistidos[dia]
            if persistido is None:
                bloco.append(dia)
                continue
            await consultar_bloco()
            if persistido.fechamento is None:
                raise HTTPException(status_code=502, detail="Fechamento persistido indisponível.")
            resultados.append(persistido.fechamento)
        await consultar_bloco()
        proveniencias = [resultado.proveniencia for resultado in resultados]
        regras = sorted({p.versao_regra for p in proveniencias})
        resultado = ResultadoAuditoria(
            empresa_codigo=unidade, inicio=inicio, fim=fim,
            caixas=tuple(sorted(
                (caixa for resultado in resultados for caixa in resultado.caixas),
                key=lambda c: (c.caixa.data, c.caixa.abertura),
            )),
            proveniencia=Proveniencia(
                execucao_id=uuid.uuid4().hex, executado_em=agora(),
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


@router.get("/reincidencia")
async def obter_reincidencia(
    unidade: int = Query(...),
    mes: str = Query(...),
) -> dict:
    try:
        inicio = date.fromisoformat(f"{mes}-01")
        if len(mes) != 7 or inicio.strftime("%Y-%m") != mes:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="O mês deve estar no formato AAAA-MM.") from None

    unidades = carregar_unidades()
    if unidade not in unidades:
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")

    quantidade_dias = calendar.monthrange(inicio.year, inicio.month)[1]
    fim_mes = inicio + timedelta(days=quantidade_dias - 1)
    fim = min(fim_mes, agora().date())
    dias = [inicio + timedelta(days=indice) for indice in range(max((fim - inicio).days + 1, 0))]
    try:
        registros = [carregar_dia(unidade, dia) for dia in dias]
        resultados = [registro for registro in registros if registro is not None]
        codigos = {
            auditoria.caixa.funcionario_codigo
            for resultado in resultados
            if resultado.fechamento is not None
            for auditoria in resultado.fechamento.caixas
        }
        codigos.update(
            candidato.abastecimento.frentista
            for resultado in resultados
            for adquirente in resultado.recebimentos.adquirentes
            if adquirente.adquirente.upper() == "PAGBANK"
            for investigacao in (
                *adquirente.a_maior,
                *(par.investigacao for par in adquirente.pares_provaveis),
            )
            for candidato in investigacao.candidatos
            if candidato.abastecimento.frentista is not None
        )
        codigos.update(
            investigacao.frentista
            for resultado in resultados
            for adquirente in resultado.recebimentos.adquirentes
            if adquirente.adquirente.upper() == "PAGBANK"
            for investigacao in (
                *adquirente.a_maior,
                *(par.investigacao for par in adquirente.pares_provaveis),
            )
            if investigacao.frentista is not None
        )
        nomes = (
            await buscar_nomes_funcionarios(unidades[unidade], inicio, fim)
            if codigos
            else {}
        )
        return agregar_reincidencia(
            unidade,
            mes,
            dias,
            resultados,
            {codigo: nome for codigo, nome in nomes.items() if codigo in codigos},
        ).model_dump(mode="json")
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
