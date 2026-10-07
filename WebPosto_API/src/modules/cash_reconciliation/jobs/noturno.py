"""Coleta diaria somente leitura, isolada por unidade e adquirente."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from ..adapters.persistencia import DIRETORIO, salvar_dia
from ..application.auditar_fechamento import auditar_unidade
from ..application.recebimentos import TIMEOUT_ETAPA, conciliar_adquirente
from ..config import carregar_unidades
from ..domain.execucao import ResultadoDiario
from ..domain.models import Proveniencia, Unidade
from ..domain.recebimentos import ResultadoRecebimentos
from ..rules.cartoes import VERSAO as VERSAO_CARTOES
from ..rules.fechamento import VERSAO as VERSAO_FECHAMENTO

logger = logging.getLogger(__name__)
VERSAO_JOB = "CASH_AUDIT_NOTURNO_V1"


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
        logger.warning("Fechamento unidade=%s dia=%s tipo=%s", empresa, dia, type(exc).__name__)
        erro_fechamento = "falha ao consultar fechamento"
    if erro_fechamento:
        fechamento = None
    logger.info(
        "Fechamento unidade=%s dia=%s situacao=%s caixas=%s",
        empresa, dia, "erro" if erro_fechamento else "ok", len(fechamento.caixas) if fechamento else 0,
    )
    adquirentes = []
    for configurada in unidade.adquirentes:
        item = await conciliar_adquirente(empresa, dia, configurada, timeout=timeout)
        adquirentes.append(item)
        logger.info(
            "Recebimentos unidade=%s adquirente=%s situacao=%s casados=%s maior=%s menor=%s pares=%s",
            empresa, item.adquirente, item.situacao,
            item.casados.quantidade if item.casados else "-", len(item.a_maior), len(item.a_menor),
            len(item.pares_provaveis),
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
            execucao_id=execucao_id, executado_em=datetime.now(), versao_regra=VERSAO_JOB,
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
            logger.info("Persistido unidade=%s dia=%s execucao=%s", unidade.empresa_codigo, dia, execucao_id)
        except Exception as exc:
            logger.error(
                "Unidade nao concluida unidade=%s dia=%s tipo=%s",
                unidade.empresa_codigo, dia, type(exc).__name__,
            )
            falhas += 1
    logger.info("Execucao terminada dia=%s unidades_com_falha=%s execucao=%s", dia, falhas, execucao_id)
    return 1 if falhas else 0


def _dia(valor: str) -> date:
    try:
        dia = date.fromisoformat(valor)
        if dia.isoformat() != valor:
            raise ValueError
        return dia
    except ValueError:
        raise argparse.ArgumentTypeError("Informe o dia como AAAA-MM-DD.") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoria noturna somente leitura.")
    parser.add_argument("--dia", type=_dia, default=date.today() - timedelta(days=1))
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[4] / ".env")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    DIRETORIO.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(DIRETORIO / "noturno.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
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
