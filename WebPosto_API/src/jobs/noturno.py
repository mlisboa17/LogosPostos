"""Ponto de composição do robô noturno dos módulos de caixa e placar."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from dotenv import load_dotenv

from src.modules.cash_reconciliation.adapters import pendencias as repositorio_pendencias
from src.modules.cash_reconciliation.adapters import persistencia as persistencia_caixa
from src.modules.cash_reconciliation.adapters import saude_robo
from src.modules.cash_reconciliation.application.resumo_diario import gerar_mensagem_curta
from src.modules.cash_reconciliation.config import carregar_unidades, prazos_pendencia_dias
from src.modules.cash_reconciliation.domain.tempo import agora, formatar_data, ontem
from src.modules.cash_reconciliation.jobs.noturno import (
    FormatoLogBrasil,
    _dia,
    executar,
)
from src.modules.commercial_performance.adapters.persistencia import salvar_placar
from src.modules.commercial_performance.application.placar import obter_placar
from src.modules.commercial_performance.config import POSTOS
from src.shared.notificacao.telegram import ResultadoDestinatario, enviar_mensagem

logger = logging.getLogger("src.modules.cash_reconciliation.jobs.noturno")
DIRETORIO_RESUMOS = Path(__file__).resolve().parents[2] / "data" / "resumos"


def _ler_envios_telegram(caminho: Path) -> dict:
    try:
        conteudo = caminho.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise OSError(type(exc).__name__) from None
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError as exc:
        raise ValueError(type(exc).__name__) from None
    if not isinstance(dados, dict):
        raise ValueError("Registro de envios inválido.")
    return dados


def _registrar_envio_telegram(caminho: Path, dia: date, sucesso: bool) -> None:
    dados = _ler_envios_telegram(caminho)
    dados[dia.isoformat()] = {
        "registrado_em": agora().isoformat(),
        "situacao": "ok" if sucesso else "falhou",
    }
    temporario: Path | None = None
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=caminho.parent,
            suffix=".tmp",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


def _mensagens_telegram(dia: date) -> list[str]:
    unidades = carregar_unidades()
    resultados = [
        resultado
        for codigo in unidades
        if (resultado := persistencia_caixa.carregar_dia(codigo, dia)) is not None
    ]
    estado = saude_robo.carregar_estado()
    if estado is not None and estado.dia_processado == dia:
        unidades_com_falha = set(estado.unidades_com_falha)
    else:
        unidades_com_falha = {
            resultado.empresa_codigo
            for resultado in resultados
            if resultado.erro_fechamento
            or any(item.situacao == "erro" for item in resultado.recebimentos.adquirentes)
        }
    abertas = {
        unidade: repositorio_pendencias.contar_abertas_somente_leitura(unidade=unidade)
        for unidade in unidades
    }
    prazos = prazos_pendencia_dias()
    vencidas = {
        unidade: repositorio_pendencias.contar_vencidas_somente_leitura(
            unidade=unidade,
            prazos_dias=prazos,
        )
        for unidade in unidades
    }
    return gerar_mensagem_curta(
        dia,
        resultados,
        list(unidades),
        unidades_com_falha,
        abertas,
        vencidas,
    )


def _tentar_envio_telegram(
    dia: date,
    *,
    dia_manual: bool,
    enviar_manual: bool,
    reenviar: bool,
    caminho_registro: Path | None = None,
) -> None:
    if os.getenv("TELEGRAM_ENVIO", "0").strip() != "1":
        return
    if dia != ontem() and not (dia_manual and enviar_manual):
        return
    if dia_manual and not enviar_manual:
        return

    registro = caminho_registro or DIRETORIO_RESUMOS / "envios_telegram.json"
    try:
        envios = _ler_envios_telegram(registro)
        if dia.isoformat() in envios and not reenviar:
            logger.info("Telegram envio=ignorado motivo=ja_enviado")
            return
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_ids = list(
            dict.fromkeys(
                item.strip()
                for item in os.getenv("TELEGRAM_CHAT_IDS", "").split(",")
                if item.strip()
            )
        )
        if not token or not chat_ids:
            logger.warning("Telegram envio=falhou motivo=ConfiguracaoAusente")
            return
        mensagens = _mensagens_telegram(dia)
        resultados = [
            resultado
            for texto in mensagens
            for resultado in enviar_mensagem(texto, token=token, chat_ids=chat_ids)
        ]
        sucesso = bool(resultados) and all(resultado.sucesso for resultado in resultados)
        if sucesso:
            logger.info("Telegram envio=ok destinatarios=%s", len(chat_ids))
        else:
            falha = next(
                (resultado for resultado in resultados if not resultado.sucesso),
                ResultadoDestinatario(chat_id="", sucesso=False, tipo_erro="sem destinatário"),
            )
            motivo = (
                f"HTTP {falha.status_http}"
                if falha.status_http is not None
                else falha.tipo_erro or "erro desconhecido"
            )
            logger.warning("Telegram envio=falhou motivo=%s", motivo)
        _registrar_envio_telegram(registro, dia, sucesso)
    except Exception as exc:
        logger.warning("Telegram envio=falhou motivo=%s", type(exc).__name__)


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
                posto.empresa_codigo,
                placar.mes,
                formatar_data(placar.dia),
                placar.acumulado,
            )
        except Exception as exc:
            logger.error(
                "Placar nao concluido posto=%s mes=%s tipo=%s",
                posto.empresa_codigo,
                dia.strftime("%Y-%m"),
                type(exc).__name__,
            )
            falhas += 1
            unidades_com_falha.add(posto.empresa_codigo)
    return falhas, unidades_com_falha


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoria noturna somente leitura.")
    parser.add_argument(
        "--dia",
        type=_dia,
        default=None,
        help="Dia em dd/mm/aaaa ou aaaa-mm-dd; padrão: ontem em Recife.",
    )
    parser.add_argument("--enviar-telegram", action="store_true")
    parser.add_argument("--reenviar", action="store_true")
    args = parser.parse_args()
    dia = args.dia or ontem()
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
        codigo_saida = asyncio.run(executar(dia, executar_placar=_executar_placar))
        _tentar_envio_telegram(
            dia,
            dia_manual=args.dia is not None,
            enviar_manual=args.enviar_telegram,
            reenviar=args.reenviar,
        )
        return codigo_saida
    finally:
        modulo_logger.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
