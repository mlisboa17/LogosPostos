from __future__ import annotations

import asyncio
import calendar
import logging
import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..adapters.webposto_http import WebPostoErro
from ..adapters.persistencia import PersistenciaErro, carregar_dia
from ..adapters import pendencias as repositorio_pendencias
from ..application.auditar_fechamento import auditar_unidade
from ..application.reincidencia import agregar_reincidencia
from ..application.recebimentos import conciliar_recebimentos
from ..application.serializacao import serializar_fechamento
from ..config import carregar_unidades
from ..domain.fechamento import ResultadoAuditoria
from ..domain.models import Proveniencia
from ..domain.pendencias import Pendencia
from ..domain.recebimentos import ResultadoRecebimentos
from ..domain.tempo import agora
from ...webposto_integration.funcionarios import buscar_nomes_funcionarios
from src.interfaces.http.dependencies import get_current_user, require_unit_access

router = APIRouter(prefix="/api/v1/cash-audit", tags=["cash-audit"])
logger = logging.getLogger(__name__)
TIMEOUT_FECHAMENTO = 180


class JustificativaPayload(BaseModel):
    justificativa: str = Field(min_length=10, max_length=2000)

    @field_validator("justificativa")
    @classmethod
    def normalizar_justificativa(cls, valor: str) -> str:
        valor = valor.strip()
        if len(valor) < 10:
            raise ValueError("A justificativa deve ter ao menos 10 caracteres.")
        return valor


class DecisaoPayload(BaseModel):
    observacao: str | None = Field(default=None, max_length=2000)

    @field_validator("observacao")
    @classmethod
    def normalizar_observacao(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        if not valor:
            raise ValueError("A observação não pode ficar vazia.")
        return valor


def _escopo_pendencias(usuario: dict, unidade: int | None) -> int | None:
    papel = usuario.get("role")
    if papel == "gerente":
        propria = usuario.get("company_id")
        if isinstance(propria, bool) or not isinstance(propria, int):
            raise HTTPException(status_code=403, detail="Unidade do gerente inválida.")
        if unidade is not None and unidade != propria:
            raise HTTPException(status_code=403, detail="Acesso negado para esta unidade.")
        return propria
    if papel not in {"diretor", "auditor"}:
        raise HTTPException(status_code=403, detail="Perfil sem acesso à fila de pendências.")
    if unidade is not None and unidade not in carregar_unidades():
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")
    return unidade


def _serializar_pendencia(pendencia: Pendencia) -> dict:
    return pendencia.model_dump(mode="json")


def _ler_pendencia(pendencia_id: str) -> Pendencia:
    try:
        pendencia = repositorio_pendencias.obter(pendencia_id)
    except repositorio_pendencias.ErroPersistenciaPendencias:
        raise HTTPException(status_code=500, detail="Falha ao ler pendência.") from None
    if pendencia is None:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    return pendencia


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
    current_user: dict = Depends(get_current_user),
) -> ResultadoRecebimentos:
    if unidade not in carregar_unidades():
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")
    require_unit_access(current_user, unidade)
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
    current_user: dict = Depends(get_current_user),
) -> dict:
    if fim < inicio or (fim - inicio).days > 30:
        raise HTTPException(
            status_code=422,
            detail="O período deve ser válido e conter no máximo 31 dias.",
        )

    unidades = carregar_unidades()
    if unidade not in unidades:
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")
    require_unit_access(current_user, unidade)

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
    current_user: dict = Depends(get_current_user),
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
    require_unit_access(current_user, unidade)

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
def listar_unidades(current_user: dict = Depends(get_current_user)) -> list[dict[str, int | str]]:
    return [
        {"empresa_codigo": unidade.empresa_codigo, "nome": unidade.nome}
        for unidade in carregar_unidades().values()
        if current_user["role"] in {"diretor", "auditor"}
        or current_user.get("company_id") == unidade.empresa_codigo
    ]


@router.get("/pendencias/contagem-abertas")
def contar_pendencias_abertas(current_user: dict = Depends(get_current_user)) -> dict[str, int]:
    unidade = _escopo_pendencias(current_user, None)
    try:
        return {"abertas": repositorio_pendencias.contar_abertas(unidade=unidade)}
    except repositorio_pendencias.ErroPersistenciaPendencias:
        raise HTTPException(status_code=500, detail="Falha ao contar pendências abertas.") from None


@router.get("/pendencias")
def listar_pendencias(
    unidade: int | None = Query(default=None),
    status: Literal["aberta", "justificada", "aprovada", "recusada", "todas"] = Query(default="aberta"),
    tipo: str | None = Query(default=None, min_length=1, max_length=64),
    limite: int = Query(default=100, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> dict[str, object]:
    escopo = _escopo_pendencias(current_user, unidade)
    try:
        itens, total = repositorio_pendencias.listar(
            unidade=escopo,
            status=None if status == "todas" else status,
            tipo=tipo,
            limite=limite,
            deslocamento=deslocamento,
        )
    except repositorio_pendencias.ErroPersistenciaPendencias:
        raise HTTPException(status_code=500, detail="Falha ao listar pendências.") from None
    return {
        "items": [_serializar_pendencia(item) for item in itens],
        "total": total,
        "limite": limite,
        "deslocamento": deslocamento,
    }


@router.post("/pendencias/{pendencia_id}/justificar")
def justificar_pendencia(
    pendencia_id: str,
    payload: JustificativaPayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] != "gerente":
        raise HTTPException(status_code=403, detail="Somente gerente pode justificar pendências.")
    pendencia = _ler_pendencia(pendencia_id)
    require_unit_access(current_user, pendencia.unidade)
    if pendencia.status not in {"aberta", "justificada"}:
        raise HTTPException(status_code=409, detail="A pendência não aceita justificativa.")
    corrigindo = pendencia.status == "justificada"
    status_esperado: Literal["aberta", "justificada"] = (
        "justificada" if corrigindo else "aberta"
    )
    try:
        atualizada = repositorio_pendencias.transicionar(
            pendencia_id,
            status_esperado=status_esperado,
            status_novo="justificada",
            acao="justificativa_corrigida" if corrigindo else "justificada",
            usuario=str(current_user["sub"]),
            justificativa=payload.justificativa,
        )
    except repositorio_pendencias.TransicaoPendenciaInvalida:
        raise HTTPException(status_code=409, detail="A pendência já foi alterada.") from None
    except repositorio_pendencias.ErroPersistenciaPendencias:
        raise HTTPException(status_code=500, detail="Falha ao justificar pendência.") from None
    if atualizada is None:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    return _serializar_pendencia(atualizada)


def _decidir_pendencia(
    pendencia_id: str,
    acao: Literal["aprovada", "recusada"],
    usuario: dict,
    observacao: str | None,
) -> dict:
    if usuario["role"] != "diretor":
        raise HTTPException(status_code=403, detail="Somente diretor pode aprovar ou recusar pendências.")
    pendencia = _ler_pendencia(pendencia_id)
    require_unit_access(usuario, pendencia.unidade)
    if pendencia.status != "justificada":
        raise HTTPException(status_code=409, detail="Somente pendências justificadas podem ser decididas.")
    try:
        atualizada = repositorio_pendencias.transicionar(
            pendencia_id,
            status_esperado="justificada",
            status_novo=acao,
            acao=acao,
            usuario=str(usuario["sub"]),
            justificativa=observacao,
        )
    except repositorio_pendencias.TransicaoPendenciaInvalida:
        raise HTTPException(status_code=409, detail="A pendência já foi alterada.") from None
    except repositorio_pendencias.ErroPersistenciaPendencias:
        raise HTTPException(status_code=500, detail="Falha ao decidir pendência.") from None
    if atualizada is None:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    return _serializar_pendencia(atualizada)


@router.post("/pendencias/{pendencia_id}/aprovar")
def aprovar_pendencia(
    pendencia_id: str,
    payload: DecisaoPayload = Body(default=DecisaoPayload()),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return _decidir_pendencia(pendencia_id, "aprovada", current_user, payload.observacao)


@router.post("/pendencias/{pendencia_id}/recusar")
def recusar_pendencia(
    pendencia_id: str,
    payload: DecisaoPayload = Body(default=DecisaoPayload()),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return _decidir_pendencia(pendencia_id, "recusada", current_user, payload.observacao)
