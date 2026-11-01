"""Agendador em segundo plano (APScheduler). Cada job usa conexão própria."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from apps.match import rotina
from apps.match.canais import toast
from src.modules.cash_reconciliation.domain.tempo import FUSO, agora, hoje, ontem

logger = logging.getLogger(__name__)

JOB_COLETA, JOB_REPESCAGEM, JOB_RECUPERACAO = "coleta", "repescagem", "recuperacao"
JOB_FISCAL_CAPTURA, JOB_FISCAL_PENDENTES, JOB_FISCAL_MENSAL = "fiscal_captura", "fiscal_pendentes", "fiscal_mensal"
JOB_FISCAL_RECUPERACAO = "fiscal_mensal_recuperacao"
JOB_EXTRATOS, JOB_EXTRATOS_INICIO = "extratos", "extratos_inicio"
HORA_ENVIO_FISCAL = 8
_OPCOES = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}


def _rodar(con_factory, *, so_falhas: bool, limpar: bool, origem: str = "agendada") -> None:
    con = con_factory()
    try:
        try:
            asyncio.run(rotina.executar(con, so_falhas=so_falhas, origem=origem))
        except Exception as exc:  # noqa: BLE001 - job nunca derruba o agendador
            logger.warning("Rotina de coleta falhou tipo=%s", type(exc).__name__)  # nunca a mensagem
            try:
                toast.avisar("Logos Match — a rotina falhou",
                             f"A coleta de {ontem():%d/%m/%Y} não terminou. "
                             "Abra o Logos Match e clique em Coletar agora.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Aviso de falha da rotina não pôde ser exibido tipo=%s",
                               type(exc).__name__)
        if limpar:
            try:
                rotina.limpar_antigos(con, hoje())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Limpeza de dados antigos falhou tipo=%s", type(exc).__name__)
    finally:
        con.close()


def _job_coleta(con_factory) -> None:
    _rodar(con_factory, so_falhas=False, limpar=True)


def _job_repescagem(con_factory) -> None:
    _rodar(con_factory, so_falhas=True, limpar=False, origem="repescagem")


def _job_recuperacao(con_factory) -> None:
    _rodar(con_factory, so_falhas=False, limpar=True, origem="recuperacao")


def _fiscal(nome: str, funcao) -> None:
    """Job fiscal isolado: erro nunca derruba a coleta nem o agendador."""
    try:
        funcao()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Job fiscal %s falhou tipo=%s", nome, type(exc).__name__)


def _job_fiscal_captura(con_factory) -> None:
    from apps.match.fiscal import captura
    _fiscal("captura", lambda: captura.capturar_todas(con_factory, hoje()))


def _job_fiscal_pendentes(con_factory) -> None:
    from apps.match.fiscal import captura, envio_mensal

    def rodar():
        captura.capturar_todas(con_factory, hoje(), so_pendentes=True)
        con = con_factory()
        try:
            envio_mensal.enviar_complementares(con, agora())
        finally:
            con.close()
    _fiscal("pendentes", rodar)


def _job_fiscal_mensal(con_factory) -> None:
    from apps.match.fiscal import envio_mensal

    def rodar():
        con = con_factory()
        try:
            envio_mensal.rodar(con, hoje())
        finally:
            con.close()
    _fiscal("mensal", rodar)


def _job_extratos(con_factory) -> None:
    from apps.match.extratos import entrada

    def rodar():
        con = con_factory()
        try:
            entrada.processar_pasta(con, agora())
        finally:
            con.close()

    _fiscal("extratos", rodar)


def _gatilho(hhmm: str) -> CronTrigger:
    h, m = hhmm.split(":")
    return CronTrigger(hour=int(h), minute=int(m), timezone=FUSO)


def reagendar(sched: BackgroundScheduler, con_factory) -> None:
    """Aplica os horários atuais da tabela `instalacao` aos jobs cron."""
    con = con_factory()
    try:
        hora_coleta, hora_repescagem = rotina.horarios(con)
    finally:
        con.close()
    sched.add_job(_job_coleta, _gatilho(hora_coleta), args=[con_factory], id=JOB_COLETA,
                  replace_existing=True, **_OPCOES)
    sched.add_job(_job_repescagem, _gatilho(hora_repescagem), args=[con_factory],
                  id=JOB_REPESCAGEM, replace_existing=True, **_OPCOES)
    sched.add_job(_job_fiscal_captura, _gatilho("07:00"), args=[con_factory], id=JOB_FISCAL_CAPTURA,
                  replace_existing=True, **_OPCOES)
    sched.add_job(_job_fiscal_pendentes, CronTrigger(hour="8-20", minute=30, timezone=FUSO),
                  args=[con_factory], id=JOB_FISCAL_PENDENTES, replace_existing=True, **_OPCOES)
    sched.add_job(_job_fiscal_mensal, _gatilho(f"{HORA_ENVIO_FISCAL:02d}:00"), args=[con_factory],
                  id=JOB_FISCAL_MENSAL, replace_existing=True, **_OPCOES)
    sched.add_job(_job_extratos, IntervalTrigger(seconds=60, timezone=FUSO), args=[con_factory],
                  id=JOB_EXTRATOS, replace_existing=True, **_OPCOES)


def iniciar(con_factory, *, pausado: bool = False) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=FUSO)
    reagendar(sched, con_factory)
    con = con_factory()
    try:
        rotina.fechar_orfas(con)
        recuperar = rotina.precisa_recuperar(con, agora())
    finally:
        con.close()
    if recuperar:
        sched.add_job(_job_recuperacao, "date", run_date=datetime.now(FUSO), args=[con_factory],
                      id=JOB_RECUPERACAO, replace_existing=True, **_OPCOES)
    if agora().hour >= HORA_ENVIO_FISCAL:  # subiu depois do horário: confere o envio do mês uma vez
        sched.add_job(_job_fiscal_mensal, "date", run_date=datetime.now(FUSO), args=[con_factory],
                      id=JOB_FISCAL_RECUPERACAO, replace_existing=True, **_OPCOES)
    sched.add_job(_job_extratos, "date", run_date=datetime.now(FUSO), args=[con_factory],
                  id=JOB_EXTRATOS_INICIO, replace_existing=True, **_OPCOES)
    sched.start(paused=pausado)
    return sched
