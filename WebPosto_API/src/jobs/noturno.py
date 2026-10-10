"""Ponto de composição do robô noturno dos módulos de caixa e placar."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Font

from src.modules.cash_reconciliation.adapters import pendencias as repositorio_pendencias
from src.modules.cash_reconciliation.adapters import persistencia as persistencia_caixa
from src.modules.cash_reconciliation.adapters import saude_robo
from src.modules.cash_reconciliation.application.resumo_diario import gerar_mensagem_curta
from src.modules.cash_reconciliation.config import carregar_unidades, prazos_pendencia_dias
from src.modules.cash_reconciliation.domain.tempo import agora, formatar_data, ontem, para_local
from src.modules.cash_reconciliation.jobs.noturno import (
    FormatoLogBrasil,
    _dia,
    executar,
)
from src.modules.commercial_performance.adapters.persistencia import salvar_placar
from src.modules.commercial_performance.application.placar import obter_placar
from src.modules.commercial_performance.config import POSTOS
from src.modules.webposto_integration.funcionarios import buscar_nomes_funcionarios
from src.modules.webposto_integration.http import WebPostoErro
from src.shared.notificacao.telegram import (
    ResultadoDestinatario,
    enviar_documento,
    enviar_mensagem,
)

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


def _coletar_dados_telegram(dia: date) -> dict:
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
    codigos_por_unidade = {}
    for codigo, resultado in ((item.empresa_codigo, item) for item in resultados):
        if resultado.fechamento is None:
            continue
        codigos = {
            caixa.caixa.funcionario_codigo
            for caixa in resultado.fechamento.caixas
            if caixa.caixa.funcionario_codigo is not None
        }
        codigos.update(
            vale.funcionario_codigo
            for caixa in resultado.fechamento.caixas
            for vale in caixa.vales
            if vale.funcionario_codigo is not None
        )
        codigos_por_unidade[codigo] = codigos

    async def consultar_nomes() -> dict[int, dict[int, str]]:
        async def consultar_unidade(codigo: int, codigos: set[int]) -> tuple[int, dict[int, str]]:
            if not codigos:
                return codigo, {}
            try:
                nomes = await buscar_nomes_funcionarios(unidades[codigo], dia, dia)
            except WebPostoErro as exc:
                logger.warning(
                    "Telegram nomes indisponiveis unidade=%s motivo=%s",
                    codigo,
                    type(exc).__name__,
                )
                return codigo, {}
            return codigo, {chave: nome for chave, nome in nomes.items() if chave in codigos}

        encontrados = await asyncio.gather(
            *(consultar_unidade(codigo, codigos) for codigo, codigos in codigos_por_unidade.items())
        )
        return dict(encontrados)

    nomes_funcionarios = asyncio.run(consultar_nomes())
    return {
        "unidades": unidades,
        "resultados": resultados,
        "unidades_com_falha": unidades_com_falha,
        "abertas": abertas,
        "vencidas": vencidas,
        "nomes_funcionarios": nomes_funcionarios,
    }


def _mensagens_telegram(dia: date, dados: dict | None = None) -> list[str]:
    dados = dados or _coletar_dados_telegram(dia)
    unidades = dados["unidades"]
    resultados = dados["resultados"]
    unidades_com_falha = dados["unidades_com_falha"]
    abertas = dados["abertas"]
    vencidas = dados["vencidas"]
    return gerar_mensagem_curta(
        dia,
        resultados,
        list(unidades),
        unidades_com_falha,
        abertas,
        vencidas,
        dados["nomes_funcionarios"],
    )


def _criar_planilha_telegram(dia: date, dados: dict, diretorio: Path | None = None) -> Path:
    destino = diretorio or DIRETORIO_RESUMOS
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"{dia.isoformat()}.xlsx"
    workbook = Workbook()
    resumo = workbook.active
    resumo.title = "Resumo"
    caixas_sheet = workbook.create_sheet("Caixas")
    despesas_sheet = workbook.create_sheet("Despesas")
    vales_sheet = workbook.create_sheet("Vales")

    cabecalhos = {
        "Resumo": [
            "Filial",
            "Caixas",
            "Quebra",
            "Faltas sem desconto (R$)",
            "Despesas (qtd)",
            "Despesas (R$)",
            "Vales (qtd)",
            "Vales (R$)",
            "Pendências abertas",
            "Pendências vencidas",
        ],
        "Caixas": [
            "Filial",
            "Caixa",
            "Operador",
            "Abertura",
            "Fechamento",
            "Consolidado",
            "Quebra",
            "Falta sem desconto",
        ],
        "Despesas": [
            "Filial",
            "Caixa",
            "Valor",
            "Descrição",
            "Plano de contas",
            "Alerta",
        ],
        "Vales": ["Filial", "Caixa", "Funcionário", "Valor", "Origem"],
    }
    for planilha, cabecalho in zip(
        (resumo, caixas_sheet, despesas_sheet, vales_sheet),
        cabecalhos.values(),
    ):
        planilha.append(cabecalho)

    por_unidade = {resultado.empresa_codigo: resultado for resultado in dados["resultados"]}
    for codigo, unidade in dados["unidades"].items():
        registro = por_unidade.get(codigo)
        fechamento = registro.fechamento if registro else None
        auditorias = list(fechamento.caixas) if fechamento else []
        apelido = unidade.apelido or unidade.nome
        faltas = [
            alerta
            for auditoria in auditorias
            for alerta in auditoria.alertas
            if alerta.codigo == "FALTA_SEM_DESCONTO"
        ]
        despesas = [despesa for auditoria in auditorias for despesa in auditoria.despesas]
        vales = [vale for auditoria in auditorias for vale in auditoria.vales]
        resumo.append(
            [
                apelido,
                len(auditorias),
                float(fechamento.quebra_total) if fechamento else 0,
                float(sum((abs(item.valor or Decimal(0)) for item in faltas), Decimal(0))),
                len(despesas),
                float(sum((item.valor for item in despesas), Decimal(0))),
                len(vales),
                float(sum((item.valor for item in vales), Decimal(0))),
                dados["abertas"].get(codigo),
                dados["vencidas"].get(codigo),
            ]
        )
        nomes = dados["nomes_funcionarios"].get(codigo, {})
        for auditoria in auditorias:
            caixa = auditoria.caixa
            falta_caixa = sum(
                (
                    abs(alerta.valor or Decimal(0))
                    for alerta in auditoria.alertas
                    if alerta.codigo == "FALTA_SEM_DESCONTO" and alerta.referencia == caixa.codigo
                ),
                Decimal(0),
            )
            abertura = para_local(caixa.abertura).replace(tzinfo=None)
            fechamento_caixa = (
                para_local(caixa.fechamento).replace(tzinfo=None)
                if caixa.fechamento is not None
                else None
            )
            caixas_sheet.append(
                [
                    apelido,
                    caixa.codigo,
                    nomes.get(caixa.funcionario_codigo, f"func. {caixa.funcionario_codigo}"),
                    abertura,
                    fechamento_caixa,
                    "sim" if caixa.consolidado else "não",
                    float(auditoria.quebra),
                    float(falta_caixa),
                ]
            )
            for despesa in auditoria.despesas:
                plano = " ".join(
                    parte
                    for parte in (despesa.plano_conta_codigo, despesa.plano_conta_nome)
                    if parte
                )
                despesas_sheet.append(
                    [
                        apelido,
                        caixa.codigo,
                        float(despesa.valor),
                        despesa.descricao or "",
                        plano,
                        "SEM PLANO" if not despesa.plano_conta_codigo else "",
                    ]
                )
            rotulos_origem = {"C": "sobra de caixa", "D": "falta de caixa"}
            for vale in auditoria.vales:
                codigo_funcionario = vale.funcionario_codigo
                vales_sheet.append(
                    [
                        apelido,
                        caixa.codigo,
                        nomes.get(
                            codigo_funcionario,
                            (
                                f"func. {codigo_funcionario}"
                                if codigo_funcionario is not None
                                else "indisponível"
                            ),
                        ),
                        float(vale.valor),
                        rotulos_origem.get(vale.origem.upper(), "vale"),
                    ]
                )

    formatos_monetarios = {
        "Resumo": ("C", "D", "F", "H"),
        "Caixas": ("G", "H"),
        "Despesas": ("C",),
        "Vales": ("D",),
    }
    for planilha in workbook.worksheets:
        planilha.freeze_panes = "A2"
        planilha.auto_filter.ref = planilha.dimensions
        for celula in planilha[1]:
            celula.font = Font(bold=True)
        for coluna in formatos_monetarios[planilha.title]:
            for linha in range(2, planilha.max_row + 1):
                planilha[f"{coluna}{linha}"].number_format = '"R$" #,##0.00'
        if planilha.title == "Caixas":
            for linha in range(2, planilha.max_row + 1):
                planilha[f"D{linha}"].number_format = "dd/mm/yyyy hh:mm"
                planilha[f"E{linha}"].number_format = "dd/mm/yyyy hh:mm"
        for coluna in planilha.columns:
            letra = coluna[0].column_letter
            largura = max((len(str(celula.value or "")) for celula in coluna), default=0)
            planilha.column_dimensions[letra].width = min(max(largura + 2, 12), 60)

    workbook.save(caminho)
    return caminho


def _artefatos_telegram(dia: date, diretorio: Path | None = None) -> tuple[list[str], Path]:
    dados = _coletar_dados_telegram(dia)
    mensagens = _mensagens_telegram(dia, dados)
    planilha = _criar_planilha_telegram(dia, dados, diretorio)
    return mensagens, planilha


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
        dados = _coletar_dados_telegram(dia)
        mensagens = _mensagens_telegram(dia, dados)
        try:
            planilha = _criar_planilha_telegram(dia, dados)
        except (OSError, ValueError) as exc:
            planilha = None
            logger.warning("Telegram planilha indisponivel motivo=%s", type(exc).__name__)
        resultados = [
            resultado
            for texto in mensagens
            for resultado in enviar_mensagem(
                texto,
                token=token,
                chat_ids=chat_ids,
                parse_mode="HTML",
            )
        ]
        resultados_documento = []
        if planilha is not None:
            resultados_documento = enviar_documento(
                planilha,
                f"Detalhe do dia {formatar_data(dia)}",
                token=token,
                chat_ids=chat_ids,
            )
            if not resultados_documento or any(not item.sucesso for item in resultados_documento):
                logger.warning("Telegram planilha envio=falhou")
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
