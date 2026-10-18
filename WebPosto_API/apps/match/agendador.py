"""Agendador em segundo plano (APScheduler). Cada job usa conexão própria."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from apps.match import rotina
from src.modules.cash_reconciliation.domain.tempo import FUSO, agora, hoje

logger = logging.getLogger(__name__)

JOB_COLETA, JOB_REPESCAGEM, JOB_RECUPERACAO = "coleta", "repescagem", "recuperacao"
_OPCOES = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}


def _rodar(con_factory, *, so_falhas: bool, limpar: bool) -> None:
    con = con_factory()
    try:
        asyncio.run(rotina.executar(con, so_falhas=so_falhas))
        if limpar:
            rotina.limpar_antigos(con, hoje())
    except Exception as exc:  # noqa: BLE001 - job nunca derruba o agendador
        logger.warning("Rotina falhou (%s)", type(exc).__name__)
    finally:
        con.close()


def _job_coleta(con_factory) -> None:
    _rodar(con_factory, so_falhas=False, limpar=True)


def _job_repescagem(con_factory) -> None:
    _rodar(con_factory, so_falhas=True, limpar=False)


def _gatilho(hhmm: str) -> CronTrigger:
    h, m = hhmm.split(":")
    return CronTrigger(hour=int(h), minute=int(m), timezone=FUSO)


def reagendar(sched: BackgroundScheduler, con, con_factory=None) -> None:
    """Aplica os horários atuais da tabela `instalacao` aos jobs cron."""
    hora_coleta, hora_repescagem = rotina.horarios(con)
    fabrica = con_factory or sched._logos_con_factory  # noqa: SLF001
    sched.add_job(_job_coleta, _gatilho(hora_coleta), args=[fabrica], id=JOB_COLETA,
                  replace_existing=True, **_OPCOES)
    sched.add_job(_job_repescagem, _gatilho(hora_repescagem), args=[fabrica], id=JOB_REPESCAGEM,
                  replace_existing=True, **_OPCOES)


def iniciar(con_factory, *, pausado: bool = False) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=FUSO)
    sched._logos_con_factory = con_factory  # usado por reagendar(sched, con)
    con = con_factory()
    try:
        reagendar(sched, con, con_factory)
        recuperar = rotina.precisa_recuperar(con, agora())
    finally:
        con.close()
    if recuperar:
        sched.add_job(_job_coleta, "date", run_date=datetime.now(FUSO), args=[con_factory],
                      id=JOB_RECUPERACAO, replace_existing=True, **_OPCOES)
    sched.start(paused=pausado)
    return sched
