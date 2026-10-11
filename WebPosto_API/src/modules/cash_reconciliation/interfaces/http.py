from __future__ import annotations

import asyncio
import calendar
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from ..adapters.webposto_http import WebPostoErro
from ..adapters.persistencia import PersistenciaErro, carregar_dia
from ..adapters import pendencias as repositorio_pendencias
from ..adapters import saude_robo
from ..application.auditar_fechamento import auditar_unidade
from ..application.reincidencia import agregar_reincidencia
from ..application.recebimentos import conciliar_recebimentos
from ..application.recebimentos import conferencia_gravada
from ..application.relatorio_caixa_dia import gerar_relatorio_caixa_dia, planilha_relatorio_caixa_dia
from ..application.painel_diretor import PainelDiretorErro, obter_unidades_painel
from ..application.resumo_diario import conferencia_para_registro
from ..application.serializacao import serializar_fechamento
from ..config import ARQUIVO as ARQUIVO_CONFIG_UNIDADES, carregar_unidades
from ..domain.fechamento import ResultadoAuditoria
from ..domain.models import Proveniencia
from ..domain.pendencias import Pendencia, calcular_prazo_pendencia
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


class ConferenciaPayload(BaseModel):
    unidade: int
    dia: date
    decisao: Literal["conferido", "nao_encontrado", "executada pelo gerente", "descartada"]
    observacao: str = Field(min_length=1, max_length=2000)

    @field_validator("observacao")
    @classmethod
    def validar_observacao(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("Informe uma observação.")
        return valor.strip()


def _conferencia(unidade: int, inicio: date, fim: date, usuario: dict):
    if unidade not in carregar_unidades():
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")
    require_unit_access(usuario, unidade)
    if fim > agora().date() - timedelta(days=2):
        raise HTTPException(status_code=422, detail="A data final deve ser até anteontem (hoje − 2 dias, Recife).")
    if fim < inicio or (fim-inicio).days > 6:
        raise HTTPException(status_code=422, detail="O período deve conter de 1 a 7 dias.")
    try:
        return conferencia_gravada(unidade, inicio, fim)
    except (PersistenciaErro, repositorio_pendencias.ErroPersistenciaPendencias, ValueError, OSError):
        logger.exception("Falha ao ler conferencia unidade=%s", unidade)
        raise HTTPException(status_code=500, detail="Falha ao ler conferência gravada.") from None


@router.get("/conferencia-recebimentos")
async def obter_conferencia_recebimentos(
    unidade: int, inicio: date, fim: date, current_user: dict = Depends(get_current_user),
) -> dict:
    conferencia = _conferencia(unidade, inicio, fim, current_user)
    dados = conferencia.model_dump(mode="json")
    dados["itens"] = [
        {**i.model_dump(mode="json"), "nsu": f"…{i.nsu[-4:]}" if i.nsu else None, "responsavel": i.responsavel}
        for i in conferencia.itens
    ]
    return dados


@router.get("/conferencia-recebimentos.xlsx")
async def exportar_conferencia_recebimentos(
    unidade: int, inicio: date, fim: date, current_user: dict = Depends(get_current_user),
) -> Response:
    from io import BytesIO
    from openpyxl import Workbook
    from ..application.resumo_diario import abas_conferencia_recebimentos

    conferencia = _conferencia(unidade, inicio, fim, current_user)
    workbook = Workbook()
    workbook.remove(workbook.active)
    abas_conferencia_recebimentos(workbook, [conferencia])
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return Response(
        stream.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="recebimentos_{unidade}_{inicio}_{fim}.xlsx"'},
    )


@router.post("/conferencia-recebimentos/{acao_id}")
async def marcar_conferencia_recebimentos(
    acao_id: str, payload: ConferenciaPayload, current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user.get("role") not in {"diretor", "gerente"}:
        raise HTTPException(status_code=403, detail="Somente diretor/gerente pode conferir recebimentos.")
    conferencia = _conferencia(payload.unidade, payload.dia, payload.dia, current_user)
    acao = next((i for i in conferencia.itens if i.id == acao_id), None)
    if acao is None:
        raise HTTPException(status_code=404, detail="Ação não encontrada neste escopo.")
    try:
        if payload.decisao in {"conferido", "nao_encontrado"}:
            repositorio_pendencias.registrar_conferencia(acao, payload.decisao, payload.observacao, current_user["sub"])
        else:
            from ..adapters.propostas_lancamento import decidir_proposta
            decidir_proposta(acao, payload.decisao, payload.observacao, current_user["sub"])
    except repositorio_pendencias.TransicaoPendenciaInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except repositorio_pendencias.ErroPersistenciaPendencias:
        raise HTTPException(status_code=500, detail="Falha ao registrar decisão local.") from None
    return {"situacao": "registrada", "erp_alterado": False}


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


def _carregar_prazos_pendencia() -> dict[str, int]:
    try:
        dados = json.loads(ARQUIVO_CONFIG_UNIDADES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Falha ao ler prazos das pendências.")
        raise HTTPException(status_code=500, detail="Falha ao ler a configuração dos prazos.") from None
    if not isinstance(dados, dict):
        logger.error("Configuração inválida para prazos das pendências.")
        raise HTTPException(status_code=500, detail="Configuração inválida para os prazos das pendências.")
    prazos = dados.get("prazo_pendencia_dias")
    if not isinstance(prazos, dict) or any(
        isinstance(prazos.get(severidade), bool)
        or not isinstance(prazos.get(severidade), int)
        or prazos[severidade] < 0
        for severidade in ("vermelho", "laranja")
    ):
        logger.error("Configuração inválida para prazo_pendencia_dias.")
        raise HTTPException(status_code=500, detail="Configuração inválida para os prazos das pendências.")
    return {"vermelho": prazos["vermelho"], "laranja": prazos["laranja"]}


def _serializar_pendencia(
    pendencia: Pendencia,
    *,
    instante: datetime | None = None,
    prazos: dict[str, int] | None = None,
) -> dict:
    prazo = prazos if prazos is not None else _carregar_prazos_pendencia()
    idade = calcular_prazo_pendencia(pendencia, instante or agora(), prazo)
    return {**pendencia.model_dump(mode="json"), **idade}


def _listar_pendencias_com_prazo(
    *,
    unidade: int | None,
    status: str | None,
    tipo: str | None,
    instante: datetime,
    prazos: dict[str, int],
) -> list[dict]:
    itens: list[Pendencia] = []
    deslocamento = 0
    total = 0
    while deslocamento == 0 or deslocamento < total:
        pagina, total = repositorio_pendencias.listar(
            unidade=unidade,
            status=status,
            tipo=tipo,
            limite=200,
            deslocamento=deslocamento,
        )
        if not pagina:
            break
        itens.extend(pagina)
        deslocamento += len(pagina)
    serializados = [
        _serializar_pendencia(item, instante=instante, prazos=prazos)
        for item in itens
    ]
    return sorted(serializados, key=lambda item: not item["vencida"])


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


def _compor_relatorio_caixa_dia(unidade: int, dia: date) -> tuple[str, str]:
    try:
        registro = carregar_dia(unidade, dia)
    except PersistenciaErro:
        raise HTTPException(status_code=500, detail="Falha ao ler auditoria persistida.") from None
    if registro is None:
        raise HTTPException(status_code=404, detail="Não há resultado persistido para a unidade e o dia.")
    configuracao = carregar_unidades()[unidade]
    estado = saude_robo.carregar_estado()
    if estado is None or estado.dia_processado != dia or unidade not in estado.unidades_processadas:
        situacao = "não processado / estado não persistido"
    elif unidade in estado.unidades_com_falha:
        situacao = "falha"
    elif unidade in estado.unidades_com_aviso:
        situacao = "aviso"
    else:
        situacao = "ok"
    try:
        conferencia = conferencia_para_registro(registro)
    except (PersistenciaErro, repositorio_pendencias.ErroPersistenciaPendencias):
        conferencia = None
    pendencias = _listar_pendencias_com_prazo(
        unidade=unidade,
        status="aberta",
        tipo=None,
        instante=agora(),
        prazos=_carregar_prazos_pendencia(),
    )
    texto = gerar_relatorio_caixa_dia(
        registro,
        configuracao,
        situacao_robo=situacao,
        pendencias=[item for item in pendencias if item["dia"] == dia.isoformat()],
        conferencia=conferencia,
    )
    return texto, configuracao.apelido or configuracao.nome


@router.get("/relatorio-caixa")
def obter_relatorio_caixa_dia(
    dia: date,
    unidade: int | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> dict:
    unidades = carregar_unidades()
    papel = current_user.get("role")
    if unidade is not None:
        if unidade not in unidades:
            raise HTTPException(status_code=404, detail="Unidade não encontrada.")
        require_unit_access(current_user, unidade)
        codigos = [unidade]
    elif papel == "gerente":
        propria = current_user.get("company_id")
        if isinstance(propria, bool) or not isinstance(propria, int) or propria not in unidades:
            raise HTTPException(status_code=403, detail="Unidade do gerente inválida.")
        codigos = [propria]
    elif papel in {"diretor", "auditor"}:
        codigos = sorted(unidades)
    else:
        raise HTTPException(status_code=403, detail="Perfil sem acesso ao relatório.")

    relatorios = []
    for codigo in codigos:
        markdown, nome = _compor_relatorio_caixa_dia(codigo, dia)
        relatorios.append({"unidade": codigo, "nome": nome, "markdown": markdown})
    return {"dia": dia.isoformat(), "relatorios": relatorios}


@router.get("/relatorio-caixa.xlsx")
def exportar_relatorio_caixa_dia(
    unidade: int,
    dia: date,
    current_user: dict = Depends(get_current_user),
) -> Response:
    unidades = carregar_unidades()
    if unidade not in unidades:
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")
    require_unit_access(current_user, unidade)
    markdown, _ = _compor_relatorio_caixa_dia(unidade, dia)
    return Response(
        planilha_relatorio_caixa_dia(markdown),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="caixa_{dia.isoformat()}_{unidade}.xlsx"'
        },
    )


@router.get("/recebimentos", response_model=ResultadoRecebimentos,
            response_model_exclude={"adquirentes": {"__all__": {"detalhes_casados"}}})
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


@router.get("/painel-diretor")
def obter_painel_diretor(current_user: dict = Depends(get_current_user)) -> dict[str, object]:
    papel = current_user.get("role")
    if papel not in {"diretor", "gerente"}:
        raise HTTPException(status_code=403, detail="Perfil sem acesso ao painel.")
    unidades = carregar_unidades()
    escopo = None
    if papel == "gerente":
        propria = current_user.get("company_id")
        if isinstance(propria, bool) or not isinstance(propria, int) or propria not in unidades:
            raise HTTPException(status_code=403, detail="Unidade do gerente inválida.")
        escopo = {propria}
    try:
        estado = saude_robo.carregar_estado()
        cards = obter_unidades_painel(
            unidades,
            escopo=escopo,
            hoje=agora().date(),
        )
        prazos = _carregar_prazos_pendencia()
        instante = agora()
        for card in cards:
            itens = _listar_pendencias_com_prazo(
                unidade=card["empresa_codigo"],
                status="aberta",
                tipo=None,
                instante=instante,
                prazos=prazos,
            )
            card["pendencias_vencidas"] = sum(item["vencida"] for item in itens)
    except (
        saude_robo.PersistenciaEstadoErro,
        PainelDiretorErro,
        PersistenciaErro,
        repositorio_pendencias.ErroPersistenciaPendencias,
    ):
        logger.exception("Falha ao compor painel persistido.")
        raise HTTPException(status_code=500, detail="Falha ao ler dados persistidos do painel.") from None
    instante = agora()
    limite = timedelta(hours=26)
    idade = instante - estado.ultima_execucao if estado is not None else None
    alerta_atraso = idade is None or idade < timedelta(0) or idade > limite
    execucao_sem_unidades = estado is not None and not estado.unidades_processadas
    unidades_processadas = estado.unidades_processadas if estado is not None else ()
    unidades_com_falha = estado.unidades_com_falha if estado is not None else ()
    unidades_com_aviso = estado.unidades_com_aviso if estado is not None else ()
    if escopo is not None:
        unidades_processadas = tuple(codigo for codigo in unidades_processadas if codigo in escopo)
        unidades_com_falha = tuple(codigo for codigo in unidades_com_falha if codigo in escopo)
        unidades_com_aviso = tuple(codigo for codigo in unidades_com_aviso if codigo in escopo)
    avisos = [
        {
            "unidade_codigo": card["empresa_codigo"],
            "unidade_nome": card["nome"],
            "adquirente": adquirente["nome"],
            "mensagem": "credencial inválida",
        }
        for card in cards
        if card["empresa_codigo"] in unidades_com_aviso
        for adquirente in card["adquirentes"]
        if adquirente["situacao"] == "credencial inválida"
    ]
    estado_saude = (
        "falha"
        if alerta_atraso or execucao_sem_unidades or unidades_com_falha
        else "atencao" if avisos
        else "ok"
    )
    return {
        "saude_robo": {
            "ultima_execucao": estado.ultima_execucao if estado is not None else None,
            "dia_processado": estado.dia_processado if estado is not None else None,
            "unidades_processadas": list(unidades_processadas),
            "unidades_com_falha": list(unidades_com_falha),
            "unidades_com_aviso": list(unidades_com_aviso),
            "avisos": avisos,
            "estado": estado_saude,
            "resumo_gerado": estado.resumo_gerado if estado is not None else None,
            "alerta_atraso": alerta_atraso,
            "execucao_sem_unidades": execucao_sem_unidades,
            "alerta_operacional": estado_saude != "ok",
            "limite_horas": 26,
        },
        "unidades": cards,
    }


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
    vencidas: bool = Query(default=False),
    limite: int = Query(default=100, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> dict[str, object]:
    escopo = _escopo_pendencias(current_user, unidade)
    try:
        prazos = _carregar_prazos_pendencia()
        instante = agora()
        itens = _listar_pendencias_com_prazo(
            unidade=escopo,
            status=None if status == "todas" else status,
            tipo=tipo,
            instante=instante,
            prazos=prazos,
        )
        if vencidas:
            itens = [item for item in itens if item["vencida"]]
    except repositorio_pendencias.ErroPersistenciaPendencias:
        raise HTTPException(status_code=500, detail="Falha ao listar pendências.") from None
    total = len(itens)
    itens = itens[deslocamento:deslocamento + limite]
    return {
        "items": itens,
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
