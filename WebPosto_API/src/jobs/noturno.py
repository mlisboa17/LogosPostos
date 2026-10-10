"""Ponto de composição do robô noturno dos módulos de caixa e placar."""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.modules.cash_reconciliation.adapters import persistencia as persistencia_caixa
from src.modules.cash_reconciliation.domain.tempo import formatar_data, ontem
from src.modules.cash_reconciliation.jobs.noturno import (
    FormatoLogBrasil,
    _dia,
    executar,
)
from src.modules.commercial_performance.adapters.persistencia import salvar_placar
from src.modules.commercial_performance.application.placar import obter_placar
from src.modules.commercial_performance.config import POSTOS

logger = logging.getLogger("src.modules.cash_reconciliation.jobs.noturno")


async def _executar_placar(
    dia: date,
    timeout: float,
    diretorio: Path | None,
) -> tuple[int, set[int]]:
    falhas = 0
    unidades_com_falha: set[int] = set()
    for posto in POSTOS.values():
        try:
            placar = await asyncio.wait_for(
                obter_placar(posto.empresa_codigo, dia.strftime("%Y-%m"), dia),
                timeout=timeout,
            )
            salvar_placar(placar, diretorio=diretorio)
            logger.info(
                "Placar posto=%s mes=%s dia=%s litros=%s",
                posto.empresa_codigo, placar.mes, formatar_data(placar.dia), placar.acumulado,
            )
        except Exception as exc:
            logger.error(
                "Placar nao concluido posto=%s mes=%s tipo=%s",
                posto.empresa_codigo, dia.strftime("%Y-%m"), type(exc).__name__,
            )
            falhas += 1
            unidades_com_falha.add(posto.empresa_codigo)
    return falhas, unidades_com_falha


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoria noturna somente leitura.")
    parser.add_argument(
        "--dia",
        type=_dia,
        default=ontem(),
        help="Dia em dd/mm/aaaa ou aaaa-mm-dd; padrão: ontem em Recife.",
    )
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    diretorio = persistencia_caixa.DIRETORIO
    diretorio.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(diretorio / "noturno.log", encoding="utf-8")
    handler.setFormatter(FormatoLogBrasil("%(asctime)s %(levelname)s %(message)s"))
    modulo_logger = logging.getLogger("src.modules.cash_reconciliation")
    modulo_logger.setLevel(logging.INFO)
    modulo_logger.addHandler(handler)
    try:
        return asyncio.run(executar(args.dia, executar_placar=_executar_placar))
    finally:
        modulo_logger.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
