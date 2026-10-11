"""CLI para identificação de despesas bancárias sem lançamento no ERP (somente leitura).

Exemplo:
    python -m src.jobs.despesas_avulsas --unidade 74014 --de 01/08/2026 --ate 30/09/2026
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

# Carrega .env exclusivamente via load_dotenv (nunca imprimir nem editar)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.modules.cash_reconciliation.application.despesas_sem_lancamento import (
    formatar_resumo_terminal,
    gerar_planilha_despesas_xlsx,
    identificar_despesas_sem_lancamento,
    resolver_caminhos_extratos_padrao,
)
from src.modules.cash_reconciliation.config import carregar_unidades


def _parse_data_br(val: str) -> date:
    """Converte dd/mm/aaaa ou aaaa-mm-dd em objeto date."""
    val = val.strip()
    if "/" in val:
        return datetime.strptime(val, "%d/%m/%Y").date()
    return date.fromisoformat(val)


async def _executar(
    empresa_codigo: int,
    data_de: date,
    data_ate: date,
    caminhos_extratos: list[str] | None = None,
    top_n: int = 20,
) -> int:
    unidades = carregar_unidades()
    unidade = unidades.get(empresa_codigo)
    if not unidade:
        print(f"Erro: unidade {empresa_codigo} não encontrada no cadastro.", file=sys.stderr)
        return 1

    rotas = caminhos_extratos
    if not rotas:
        rotas_p = resolver_caminhos_extratos_padrao(empresa_codigo)
        rotas = [str(p) for p in rotas_p]
        if not rotas:
            print(
                f"Aviso: nenhum extrato padrão encontrado para a unidade {empresa_codigo} "
                "em C:/Projetos/LOGOS/extratos/.",
                file=sys.stderr,
            )

    print(
        f"Analisando despesas sem lançamento para {unidade.nome} ({empresa_codigo}) "
        f"de {data_de.strftime('%d/%m/%Y')} a {data_ate.strftime('%d/%m/%Y')}...\n"
    )

    resumo = await identificar_despesas_sem_lancamento(
        unidade=unidade,
        data_de=data_de,
        data_ate=data_ate,
        caminhos_extratos=rotas,
    )

    # 1. Imprime relatório no terminal
    relatorio_txt = formatar_resumo_terminal(resumo, top_n=top_n)
    print(relatorio_txt)

    # 2. Salva planilha XLSX em data/despesas_avulsas/
    de_str = data_de.strftime("%Y%m%d")
    ate_str = data_ate.strftime("%Y%m%d")
    caminho_xlsx = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "despesas_avulsas"
        / f"despesas_avulsas_{empresa_codigo}_{de_str}_{ate_str}.xlsx"
    )
    salvo = gerar_planilha_despesas_xlsx(resumo, caminho_xlsx)
    print(f"\nPlanilha Excel gerada com sucesso em: {salvo}\n")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identifica débitos no extrato bancário sem lançamento no webPosto (somente leitura)."
    )
    parser.add_argument(
        "--unidade",
        type=int,
        default=74014,
        help="Código da empresa no webPosto (padrão: 74014 - Doze)",
    )
    parser.add_argument(
        "--de",
        type=str,
        required=True,
        help="Data inicial no formato dd/mm/aaaa",
    )
    parser.add_argument(
        "--ate",
        type=str,
        required=True,
        help="Data final no formato dd/mm/aaaa",
    )
    parser.add_argument(
        "--extrato",
        action="append",
        dest="extratos",
        help="Caminho de arquivo OFX (pode ser passado múltiplas vezes; se omitido, busca padrão da unidade)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Quantidade de maiores despesas a exibir no terminal (padrão: 20)",
    )

    args = parser.parse_args()

    try:
        data_de = _parse_data_br(args.de)
        data_ate = _parse_data_br(args.ate)
    except Exception as exc:
        print(f"Erro ao interpretar datas: {exc}. Utilize o formato dd/mm/aaaa.", file=sys.stderr)
        sys.exit(1)

    if data_de > data_ate:
        print("Erro: data inicial (--de) não pode ser posterior à data final (--ate).", file=sys.stderr)
        sys.exit(1)

    ret = asyncio.run(
        _executar(
            empresa_codigo=args.unidade,
            data_de=data_de,
            data_ate=data_ate,
            caminhos_extratos=args.extratos,
            top_n=args.top,
        )
    )
    sys.exit(ret)


if __name__ == "__main__":
    main()
