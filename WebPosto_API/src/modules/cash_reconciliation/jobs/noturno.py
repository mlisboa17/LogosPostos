"""Coleta diaria somente leitura, isolada por unidade e adquirente."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from pathlib import Path

from ..adapters.persistencia import carregar_dia, salvar_dia
from ..adapters import pendencias as repositorio_pendencias
from ..adapters import saude_robo
from ..adapters import premmia_portal
from ..application.auditar_fechamento import auditar_unidade
from ..application.gerar_pendencias import (
    executar_reincidencia_mes,
    pendencias_do_dia,
)
from ..application.resumo_diario import gerar_resumo_diario
from ..application.recebimentos import TIMEOUT_ETAPA, conciliar_adquirente
from ..config import carregar_unidades
from ..domain.execucao import ResultadoDiario
from ..domain.models import Proveniencia, Unidade
from ..domain.recebimentos import ResultadoRecebimentos
from ..domain.tempo import FUSO, agora, formatar_data, formatar_data_hora, ler_data
from ..rules.cartoes import VERSAO as VERSAO_CARTOES
from ..rules.fechamento import VERSAO as VERSAO_FECHAMENTO

logger = logging.getLogger("src.modules.cash_reconciliation.jobs.noturno")
VERSAO_JOB = "CASH_AUDIT_NOTURNO_V2"
ExecutarPlacar = Callable[[date, float, Path | None], Awaitable[tuple[int, set[int]]]]


class FormatoLogBrasil(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return formatar_data_hora(datetime.fromtimestamp(record.created, FUSO))


async def coletar_unidade(
    unidade: Unidade,
    dia: date,
    execucao_id: str,
    *,
    timeout: float = TIMEOUT_ETAPA,
    aviso_premmia: str | None = None,
) -> ResultadoDiario:
    empresa = unidade.empresa_codigo
    fechamento = None
    erro_fechamento = None
    try:
        fechamento = await asyncio.wait_for(auditar_unidade(empresa, dia, dia), timeout=timeout)
        if fechamento.empresa_codigo != empresa or fechamento.inicio != dia or fechamento.fim != dia:
            raise ValueError("Resultado fora do escopo.")
    except TimeoutError:
        erro_fechamento = "tempo limite excedido"
    except Exception as exc:
        # Fronteira do job: isola erros sem registrar corpo, URL ou mensagem do fornecedor.
        logger.warning("Fechamento unidade=%s dia=%s tipo=%s", empresa, formatar_data(dia), type(exc).__name__)
        erro_fechamento = "falha ao consultar fechamento"
    if erro_fechamento:
        fechamento = None
    logger.info(
        "Fechamento unidade=%s dia=%s situacao=%s caixas=%s",
        empresa, formatar_data(dia), "erro" if erro_fechamento else "ok", len(fechamento.caixas) if fechamento else 0,
    )
    adquirentes = []
    for configurada in unidade.adquirentes:
        if configurada.nome == "PREMMIA" and aviso_premmia:
            item = await conciliar_adquirente(
                empresa,
                dia,
                configurada,
                timeout=timeout,
                aviso_premmia=aviso_premmia,
            )
        else:
            item = await conciliar_adquirente(empresa, dia, configurada, timeout=timeout)
        adquirentes.append(item)
        logger.info(
            "Recebimentos unidade=%s adquirente=%s situacao=%s casados=%s maior=%s menor=%s pares=%s",
            empresa, item.adquirente, item.situacao,
            item.casados.quantidade if item.casados else "-",
            len(item.a_maior) if item.casados else "-", len(item.a_menor) if item.casados else "-",
            len(item.pares_provaveis) if item.casados else "-",
        )
    fontes = set(fechamento.proveniencia.outras_fontes if fechamento else ())
    if fechamento and fechamento.proveniencia.fonte_sangrias:
        fontes.add(fechamento.proveniencia.fonte_sangrias)
    for item in adquirentes:
        if item.proveniencia:
            fontes.update(item.proveniencia.outras_fontes)
    return ResultadoDiario(
        empresa_codigo=empresa, dia=dia, fechamento=fechamento, erro_fechamento=erro_fechamento,
        recebimentos=ResultadoRecebimentos(empresa_codigo=empresa, dia=dia, adquirentes=tuple(adquirentes)),
        proveniencia=Proveniencia(
            execucao_id=execucao_id, executado_em=agora(), versao_regra=VERSAO_JOB,
            fonte_sangrias=fechamento.proveniencia.fonte_sangrias if fechamento else "",
            extratos=(), outras_fontes=tuple(sorted(fontes)),
        ),
        versoes_regras=(VERSAO_FECHAMENTO, VERSAO_CARTOES, "RN-CARTAO-010"),
        conferencia_recebimentos=True,
    )


async def executar(
    dia: date, *, diretorio: Path | None = None, diretorio_placar: Path | None = None,
    diretorio_pendencias: Path | None = None, timeout: float = TIMEOUT_ETAPA,
    executar_placar: ExecutarPlacar | None = None,
) -> int:
    if os.getenv("WEBPOSTO_WRITES") != "0":
        logger.error("Execucao bloqueada: WEBPOSTO_WRITES deve ser 0.")
        return 1
    execucao_id = uuid.uuid4().hex
    falhas = 0
    unidades = carregar_unidades()
    unidades_processadas = [unidade.empresa_codigo for unidade in unidades.values()]
    unidades_com_falha: set[int] = set()
    unidades_com_aviso: set[int] = set()
    resultados = []
    for unidade in unidades.values():
        try:
            aviso_premmia = None
            if unidade.premmia_ativo:
                try:
                    await premmia_portal.coletar(unidade)
                except premmia_portal.PremmiaVerificacaoHumana:
                    aviso_premmia = premmia_portal.AVISO_HUMANO
                    unidades_com_aviso.add(unidade.empresa_codigo)
                except premmia_portal.PremmiaIntegridadeAviso as exc:
                    aviso_premmia = str(exc)
                    unidades_com_aviso.add(unidade.empresa_codigo)
                except (premmia_portal.PremmiaErro, OSError) as exc:
                    logger.error(
                        "Premmia coleta unidade=%s tipo=%s",
                        unidade.empresa_codigo,
                        type(exc).__name__,
                    )
                    aviso_premmia = "Premmia: falha na coleta; consultar log da etapa."
                    falhas += 1
                    unidades_com_falha.add(unidade.empresa_codigo)
            if aviso_premmia:
                resultado = await coletar_unidade(
                    unidade,
                    dia,
                    execucao_id,
                    timeout=timeout,
                    aviso_premmia=aviso_premmia,
                )
            else:
                resultado = await coletar_unidade(unidade, dia, execucao_id, timeout=timeout)
            salvar_dia(resultado, diretorio=diretorio)
            resultados.append(resultado)
            novas = pendencias_do_dia(resultado)
            novas.extend(executar_reincidencia_mes(
                unidade.empresa_codigo,
                dia,
                carregar=lambda empresa, data: carregar_dia(empresa, data, diretorio=diretorio),
            ))
            if novas:
                repositorio_pendencias.registrar(novas, banco=diretorio_pendencias)
            if resultado.erro_fechamento or any(
                item.situacao == "erro" for item in resultado.recebimentos.adquirentes
            ):
                falhas += 1
                unidades_com_falha.add(unidade.empresa_codigo)
            if any(
                item.situacao == "credencial inválida"
                for item in resultado.recebimentos.adquirentes
            ):
                unidades_com_aviso.add(unidade.empresa_codigo)
            logger.info("Persistido unidade=%s dia=%s execucao=%s", unidade.empresa_codigo, formatar_data(dia), execucao_id)
        except Exception as exc:
            logger.error(
                "Unidade nao concluida unidade=%s dia=%s tipo=%s",
                unidade.empresa_codigo, formatar_data(dia), type(exc).__name__,
            )
            falhas += 1
            unidades_com_falha.add(unidade.empresa_codigo)
    if executar_placar is not None:
        try:
            falhas_placar, unidades_com_falha_placar = await executar_placar(
                dia, timeout, diretorio_placar,
            )
            falhas += falhas_placar
            unidades_com_falha.update(unidades_com_falha_placar)
        except Exception as exc:
            logger.error("Placar nao concluido tipo=%s", type(exc).__name__)
            falhas += 1

    resumo_gerado = False
    try:
        pendencias_abertas = {
            unidade: repositorio_pendencias.contar_abertas_somente_leitura(
                unidade=unidade,
                banco=diretorio_pendencias,
            )
            for unidade in unidades_processadas
        }
        resumo = gerar_resumo_diario(
            dia,
            resultados,
            unidades_processadas,
            unidades_com_falha,
            pendencias_abertas,
        )
        saude_robo.salvar_resumo(dia, resumo)
        resumo_gerado = True
    except (OSError, repositorio_pendencias.ErroPersistenciaPendencias, saude_robo.PersistenciaEstadoErro) as exc:
        logger.error(
            "Resumo diario nao concluido dia=%s tipo=%s",
            formatar_data(dia), type(exc).__name__,
        )
        falhas += 1
    try:
        saude_robo.salvar_estado(saude_robo.EstadoRobo(
            ultima_execucao=agora(),
            dia_processado=dia,
            unidades_processadas=tuple(unidades_processadas),
            unidades_com_falha=tuple(sorted(unidades_com_falha)),
            unidades_com_aviso=tuple(sorted(unidades_com_aviso)),
            resumo_gerado=resumo_gerado,
        ))
    except saude_robo.PersistenciaEstadoErro as exc:
        logger.error("Estado do robo nao concluido tipo=%s", type(exc).__name__)
        falhas += 1
    logger.info(
        "Execucao terminada dia=%s unidades_com_falha=%s unidades_com_aviso=%s execucao=%s",
        formatar_data(dia),
        len(unidades_com_falha),
        len(unidades_com_aviso),
        execucao_id,
    )
    return 1 if falhas else 0


def _dia(valor: str) -> date:
    try:
        return ler_data(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def main() -> int:
    from src.jobs.noturno import main as executar_composicao

    return executar_composicao()


if __name__ == "__main__":
    raise SystemExit(main())
