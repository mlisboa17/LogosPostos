"""Coleta diaria somente leitura, isolada por unidade e adquirente."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

from ..adapters.persistencia import DIRETORIO, salvar_dia
from ..application.auditar_fechamento import auditar_unidade
from ..application.recebimentos import TIMEOUT_ETAPA, conciliar_adquirente
from ..config import carregar_unidades
from ..domain.execucao import ResultadoDiario
from ..domain.models import Proveniencia, Unidade
from ..domain.recebimentos import ResultadoRecebimentos
from ..domain.tempo import FUSO, agora, formatar_data, formatar_data_hora, ler_data, ontem
from ..rules.cartoes import VERSAO as VERSAO_CARTOES
from ..rules.fechamento import VERSAO as VERSAO_FECHAMENTO

logger = logging.getLogger("src.modules.cash_reconciliation.jobs.noturno")
VERSAO_JOB = "CASH_AUDIT_NOTURNO_V1"


class FormatoLogBrasil(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return formatar_data_hora(datetime.fromtimestamp(record.created, FUSO))


async def coletar_unidade(
    unidade: Unidade, dia: date, execucao_id: str, *, timeout: float = TIMEOUT_ETAPA,
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
        versoes_regras=(VERSAO_FECHAMENTO, VERSAO_CARTOES),
    )


async def executar(
    dia: date, *, diretorio: Path | None = None, timeout: float = TIMEOUT_ETAPA,
) -> int:
    if os.getenv("WEBPOSTO_WRITES") != "0":
        logger.error("Execucao bloqueada: WEBPOSTO_WRITES deve ser 0.")
        return 1
    execucao_id = uuid.uuid4().hex
    falhas = 0
    for unidade in carregar_unidades().values():
        try:
            resultado = await coletar_unidade(unidade, dia, execucao_id, timeout=timeout)
            salvar_dia(resultado, diretorio=diretorio)
            if resultado.erro_fechamento or any(item.situacao == "erro" for item in resultado.recebimentos.adquirentes):
                falhas += 1
            logger.info("Persistido unidade=%s dia=%s execucao=%s", unidade.empresa_codigo, formatar_data(dia), execucao_id)
        except Exception as exc:
            logger.error(
                "Unidade nao concluida unidade=%s dia=%s tipo=%s",
                unidade.empresa_codigo, formatar_data(dia), type(exc).__name__,
            )
            falhas += 1
    logger.info("Execucao terminada dia=%s unidades_com_falha=%s execucao=%s", formatar_data(dia), falhas, execucao_id)
    return 1 if falhas else 0


def _dia(valor: str) -> date:
    try:
        return ler_data(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoria noturna somente leitura.")
    parser.add_argument("--dia", type=_dia, default=ontem(), help="Dia em dd/mm/aaaa ou aaaa-mm-dd; padrão: ontem em Recife.")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[4] / ".env")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    DIRETORIO.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(DIRETORIO / "noturno.log", encoding="utf-8")
    handler.setFormatter(FormatoLogBrasil("%(asctime)s %(levelname)s %(message)s"))
    modulo_logger = logging.getLogger("src.modules.cash_reconciliation")
    modulo_logger.setLevel(logging.INFO)
    modulo_logger.addHandler(handler)
    try:
        return asyncio.run(executar(args.dia))
    finally:
        modulo_logger.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
