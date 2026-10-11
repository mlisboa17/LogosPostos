"""CLI para identificação e prévia de títulos a pagar já quitados no extrato bancário.

Regras da SPRINT BAIXA_00 (PARTE A):
- Padrão: SOMENTE LEITURA / PRÉVIA;
- Nenhum envio ou escrita para o webPosto nesta etapa;
- Lê .env exclusivamente via load_dotenv (nunca imprime nem edita).

Uso:
  python -m src.jobs.baixar_titulos --unidade 74014
  python -m src.jobs.baixar_titulos --unidade 74014 --extrato <caminho.ofx> ...
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

# Carrega ambiente sem exibir variáveis
_env_path = Path(".env")
if not _env_path.exists():
    _env_path = Path("WebPosto_API/.env")
if _env_path.exists():
    load_dotenv(_env_path, override=False)

from src.modules.cash_reconciliation.application.titulos_pagos_sem_baixa import (
    encontrar_candidatos_baixa,
    formatar_relatorio_previa,
)
from src.modules.cash_reconciliation.config import carregar_unidades


def parse_data_arg(val: str | None) -> date | None:
    if not val:
        return None
    val = val.strip()
    if "/" in val:
        return datetime.strptime(val, "%d/%m/%Y").date()
    return datetime.strptime(val, "%Y-%m-%d").date()


def resolver_extratos_padrao_unidade(empresa_codigo: int) -> list[Path]:
    """Resolve os extratos conhecidos da unidade em C:\\Projetos\\LOGOS\\extratos\\."""
    extratos: list[Path] = []
    base_extratos = Path(r"C:\Projetos\LOGOS\extratos")
    if not base_extratos.is_dir():
        return extratos

    if empresa_codigo == 74014:
        # Doze: 3 extratos do BB + todos os extratos da pasta PAGBANK
        bb_arqs = [
            base_extratos / "BB" / "BB_Doze_Agosto_2026.ofx",
            base_extratos / "BB" / "bancoBrasil_DozeFilial_Setembro_2026.ofx",
            base_extratos / "BB" / "BB_Doze_Outubro2026.ofx.ofx",
        ]
        for b in bb_arqs:
            if b.is_file():
                extratos.append(b)

        pasta_pagbank = base_extratos / "PAGBANK"
        if pasta_pagbank.is_dir():
            for p in pasta_pagbank.iterdir():
                if p.is_file() and (p.name.lower().endswith(".ofx") or p.name.lower().endswith(".ofx.ofx")):
                    extratos.append(p)

    return extratos


async def main_async(args: argparse.Namespace) -> int:
    unidades = carregar_unidades()
    unidade = unidades.get(args.unidade)
    if not unidade:
        print(f"[ERRO] Unidade {args.unidade} não encontrada na configuração.", file=sys.stderr)
        return 1

    # Resolve caminhos de extrato
    caminhos_extratos: list[Path] = []
    if args.extrato:
        for item in args.extrato:
            # Pode ser glob ou arquivo direto
            matches = glob.glob(str(item))
            if matches:
                for m in matches:
                    p = Path(m)
                    if p.is_file():
                        caminhos_extratos.append(p)
            else:
                p = Path(item)
                if p.is_file():
                    caminhos_extratos.append(p)
    else:
        caminhos_extratos = resolver_extratos_padrao_unidade(unidade.empresa_codigo)

    if not caminhos_extratos:
        print(
            f"[ERRO] Nenhum arquivo de extrato OFX foi informado ou encontrado para a unidade {unidade.empresa_codigo}.",
            file=sys.stderr,
        )
        return 1

    dt_ref = parse_data_arg(args.data_referencia)

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=caminhos_extratos,
        data_referencia=dt_ref,
        dias_historico=args.dias_historico,
    )

    texto_relatorio = formatar_relatorio_previa(previa)
    print(texto_relatorio)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LOGOS — Identificar candidatos a baixa de títulos já pagos no banco (PARTE A - Somente Leitura)"
    )
    parser.add_argument(
        "--unidade",
        type=int,
        required=True,
        help="Código da empresa/filial (ex.: 74014)",
    )
    parser.add_argument(
        "--extrato",
        nargs="+",
        help="Caminho(s) do(s) arquivo(s) de extrato OFX",
    )
    parser.add_argument(
        "--data-referencia",
        type=str,
        help="Data de referência para conferência de vencimento (YYYY-MM-DD ou DD/MM/YYYY)",
    )
    parser.add_argument(
        "--dias-historico",
        type=int,
        default=120,
        help="Janela em dias para busca de títulos (padrão: 120 dias)",
    )

    args = parser.parse_args()
    code = asyncio.run(main_async(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
