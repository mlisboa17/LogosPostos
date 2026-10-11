"""Gera relatorios diarios usando exclusivamente persistencia local."""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from src.modules.cash_reconciliation.adapters import pendencias, persistencia, saude_robo
from src.modules.cash_reconciliation.application.relatorio_caixa_dia import (
    consultar_dados_atuais,
    limite_diferenca_alta,
    mudancas_desde_robo,
)
from src.modules.cash_reconciliation.application.relatorio_caixa_dia import (
    gerar_relatorio_caixa_dia,
    planilha_relatorio_caixa_dia,
)
from src.modules.cash_reconciliation.application.resumo_diario import conferencia_para_registro
from src.modules.cash_reconciliation.config import carregar_unidades, prazos_pendencia_dias
from src.modules.cash_reconciliation.domain.pendencias import calcular_prazo_pendencia
from src.modules.cash_reconciliation.domain.tempo import agora

DIRETORIO_RELATORIOS = Path(__file__).resolve().parents[2] / "data" / "relatorios"
ORDEM_UNIDADES = (74014, 5555, 11495, 118508)
ARQUIVO_ENV = Path(__file__).resolve().parents[2] / ".env"


def _dia(valor: str) -> date:
    try:
        return datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Informe o dia no formato dd/mm/aaaa.") from exc


def _situacao_robo(dia: date, codigo: int) -> str:
    estado = saude_robo.carregar_estado()
    if estado is None or estado.dia_processado != dia or codigo not in estado.unidades_processadas:
        return "não processado / estado não persistido"
    if codigo in estado.unidades_com_falha:
        return "falha"
    if codigo in estado.unidades_com_aviso:
        return "aviso"
    return "ok"


def _pendencias_dia(codigo: int, dia: date) -> list[tuple[object, bool]]:
    itens = []
    deslocamento = 0
    total = 0
    while deslocamento == 0 or deslocamento < total:
        pagina, total = pendencias.listar(
            unidade=codigo,
            status="aberta",
            limite=200,
            deslocamento=deslocamento,
        )
        if not pagina:
            break
        itens.extend(pagina)
        deslocamento += len(pagina)
    prazos = prazos_pendencia_dias()
    instante = agora()
    return [
        (item, calcular_prazo_pendencia(item, instante, prazos)["vencida"])
        for item in itens
        if item.dia == dia
    ]


def gerar_para_unidade(
    codigo: int, dia: date, *, gravado: bool = False
) -> tuple[str, bytes, Path, Path]:
    unidades = carregar_unidades()
    unidade = unidades.get(codigo)
    if unidade is None:
        raise ValueError(f"Unidade não configurada: {codigo}")
    abastecimentos, vales_fora_caixa, nomes, falhas, mudancas = (), (), {}, (), ()
    gravado_registro = persistencia.carregar_dia(codigo, dia)
    if gravado:
        registro = gravado_registro
        if registro is None:
            raise FileNotFoundError(f"Sem resultado persistido para {codigo} em {dia:%d/%m/%Y}.")
    else:
        registro, abastecimentos, vales_fora_caixa, nomes, falhas = asyncio.run(
            consultar_dados_atuais(unidade, dia)
        )
        mudancas = mudancas_desde_robo(gravado_registro, registro)
    try:
        conferencia = conferencia_para_registro(registro)
    except (OSError, ValueError, pendencias.ErroPersistenciaPendencias):
        conferencia = None
    markdown = gerar_relatorio_caixa_dia(
        registro,
        unidade,
        situacao_robo=_situacao_robo(dia, codigo),
        nomes_funcionarios=nomes,
        pendencias=_pendencias_dia(codigo, dia),
        conferencia=conferencia,
        abastecimentos=abastecimentos,
        vales_fora_caixa=vales_fora_caixa,
        mudou_desde_robo=mudancas,
        falhas_coleta=falhas,
        dados_consultados_em=registro.proveniencia.executado_em if not gravado else None,
        limite_diferenca_alta=limite_diferenca_alta(codigo, dia) if not gravado else Decimal("300.00"),
    )
    DIRETORIO_RELATORIOS.mkdir(parents=True, exist_ok=True)
    base = DIRETORIO_RELATORIOS / f"caixa_{dia.isoformat()}_{codigo}"
    caminho_md = base.with_suffix(".md")
    caminho_xlsx = base.with_suffix(".xlsx")
    caminho_md.write_text(markdown, encoding="utf-8")
    caminho_xlsx.write_bytes(planilha_relatorio_caixa_dia(markdown))
    return markdown, caminho_xlsx.read_bytes(), caminho_md, caminho_xlsx


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera relatório diário com dados atuais (ou snapshots com --gravado).")
    parser.add_argument("--dia", required=True, type=_dia, help="Dia no formato dd/mm/aaaa.")
    parser.add_argument("--unidade", type=int, help="Código da unidade; sem opção, gera todas.")
    parser.add_argument("--gravado", action="store_true", help="Usa somente o resultado salvo pelo robô.")
    argumentos = parser.parse_args()
    load_dotenv(ARQUIVO_ENV, override=False)
    unidades = carregar_unidades()
    codigos = [argumentos.unidade] if argumentos.unidade is not None else [
        codigo for codigo in ORDEM_UNIDADES if codigo in unidades
    ]
    if argumentos.unidade is not None and argumentos.unidade not in unidades:
        parser.error("Unidade não configurada.")
    if not codigos:
        parser.error("Nenhuma unidade disponível para gerar o relatório.")

    for codigo in codigos:
        try:
            markdown, _, caminho_md, caminho_xlsx = gerar_para_unidade(
                codigo, argumentos.dia, gravado=argumentos.gravado
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            parser.exit(1, f"{exc}\n")
        print(markdown, end="\n")
        print(f"Arquivos: {caminho_md} · {caminho_xlsx}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())