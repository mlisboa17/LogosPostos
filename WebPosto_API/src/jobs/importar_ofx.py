"""CLI para importação de extratos OFX no webPosto com barreira de segurança.

Uso:
  python -m src.jobs.importar_ofx --unidade 74014 --arquivo <caminho.ofx> [--confirmar]
  python -m src.jobs.importar_ofx --unidade 74014 --arquivo <caminho.ofx> --data-inicial 2026-10-10 --data-final 2026-10-10 [--confirmar]
"""
from __future__ import annotations

import argparse
import asyncio
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

from src.modules.cash_reconciliation.adapters.webposto_escrita_ofx import (
    BarreiraOfxErro,
    confirmar_conferencia_historico,
    enviar_ofx_webposto,
    liberar_dia_historico,
    verificar_travas_ambiente,
)
from src.modules.cash_reconciliation.config import carregar_unidades
from src.modules.cash_reconciliation.domain.tempo import formatar_data


def parse_data_arg(val: str | None) -> date | None:
    if not val:
        return None
    val = val.strip()
    # Tenta YYYY-MM-DD ou DD/MM/YYYY
    if "/" in val:
        return datetime.strptime(val, "%d/%m/%Y").date()
    return datetime.strptime(val, "%Y-%m-%d").date()


def imprimir_relatorio_previa(resultado) -> None:
    p = resultado.previa
    print("\n" + "=" * 70)
    print("  LOGOS — IMPORTAÇÃO DE EXTRATO OFX NO WEBPOSTO (BARREIRA)")
    print("=" * 70)
    print(f"Unidade:        {p.unidade_nome} (Código {p.empresa_codigo})")
    print(f"Conta Destino:  cdConta {p.cd_conta} ({p.banco} - final {p.conta_sufixo})")
    print(f"Período:        {formatar_data(p.data_inicial)} até {formatar_data(p.data_final)}")
    print(f"Lançamentos:    {p.quantidade}")
    print(f"Total Créditos: R$ {p.total_creditos:,.2f}")
    print(f"Total Débitos:  R$ {p.total_debitos:,.2f}")
    print(f"Saldo Líquido:  R$ {p.saldo_liquido:,.2f}")
    print(f"Hash SHA-256:   {p.sha256[:16]}...{p.sha256[-8:]}")
    print("-" * 70)
    print("Amostra - Primeiros lançamentos (descrições mascaradas):")
    for trn in p.amostra_primeiros:
        print(f"  [{trn['data']}] {trn['tipo']:<6} R$ {trn['valor']:>10.2f} | {trn['descricao_mascarada']}")
    if p.amostra_ultimos:
        print("Amostra - Últimos lançamentos (descrições mascaradas):")
        for trn in p.amostra_ultimos:
            print(f"  [{trn['data']}] {trn['tipo']:<6} R$ {trn['valor']:>10.2f} | {trn['descricao_mascarada']}")
    print("-" * 70)
    if resultado.modo == "enviado":
        print("Modo:           ENVIADO — CONFERIR NA TELA")
        print("Aviso:          Lançamentos enviados ao webPosto. O sucesso definitivo depende de conferência na tela de conciliação bancária do ERP.")
        print(f"Total Esperado Créditos: R$ {p.total_creditos:,.2f}")
        print(f"Total Esperado Débitos:  R$ {p.total_debitos:,.2f}")
        print("Ação requerida:")
        print("  Conferir na tela de conciliação bancária do webPosto e registrar a confirmação com:")
        print(f"  python -m src.jobs.importar_ofx --unidade {p.empresa_codigo} --confirmar-conferencia --cd-conta {p.cd_conta} --dia {p.data_inicial}")
    else:
        print(f"Modo:           {resultado.modo.upper()}")
        print(f"Mensagem:       {resultado.mensagem}")

    if resultado.resposta_erp is not None and resultado.resposta_erp != "":
        print(f"Resposta ERP:   {resultado.resposta_erp}")
    print("=" * 70 + "\n")


async def main_async(args: argparse.Namespace) -> int:
    unidades = carregar_unidades()
    unidade = unidades.get(args.unidade)
    if not unidade:
        print(f"[ERRO] Unidade {args.unidade} não encontrada na configuração.", file=sys.stderr)
        return 1

    # Operação 1: Liberação explícita de dia bloqueado
    if args.liberar_dia:
        if not args.cd_conta:
            print("[ERRO] --cd-conta é obrigatório para liberar um dia.", file=sys.stderr)
            return 1
        if not args.confirmar_liberacao:
            print("\n" + "=" * 70)
            print("  AVISO DE SEGURANÇA — LIBERAÇÃO DE DIA BLOQUEADO")
            print("=" * 70)
            print(f"Unidade:  {unidade.nome} ({unidade.empresa_codigo})")
            print(f"Conta:    {args.cd_conta}")
            print(f"Dia:      {args.liberar_dia}")
            print("Esta ação permite reimportar um dia que estava bloqueado no histórico.")
            print("Para executar, repita o comando adicionando --confirmar-liberacao --motivo 'seu motivo'.")
            print("=" * 70 + "\n")
            return 1

        dt_liberar = parse_data_arg(args.liberar_dia)
        if not dt_liberar:
            print("[ERRO] Data inválida para --liberar-dia.", file=sys.stderr)
            return 1
        motivo = args.motivo or "Liberação autorizada pelo diretor"
        liberar_dia_historico(
            diretorio=Path("data/importacoes_ofx"),
            empresa_codigo=unidade.empresa_codigo,
            cd_conta=args.cd_conta,
            dia=dt_liberar,
            motivo=motivo,
        )
        print(f"\n[SUCESSO] Dia {formatar_data(dt_liberar)} liberado para novo envio na conta {args.cd_conta} (registrado no histórico).\n")
        return 0

    # Operação 2: Confirmação de conferência na tela de conciliação do ERP
    if args.confirmar_conferencia:
        if not args.cd_conta or not args.dia:
            print("[ERRO] --cd-conta e --dia são obrigatórios para registrar a conferência.", file=sys.stderr)
            return 1
        dt_conf = parse_data_arg(args.dia)
        if not dt_conf:
            print("[ERRO] Data inválida para --dia.", file=sys.stderr)
            return 1
        confirmar_conferencia_historico(
            diretorio=Path("data/importacoes_ofx"),
            empresa_codigo=unidade.empresa_codigo,
            cd_conta=args.cd_conta,
            dia=dt_conf,
            usuario="diretor",
        )
        print(f"\n[SUCESSO] Conferência confirmada e registrada no histórico para a conta {args.cd_conta} no dia {formatar_data(dt_conf)}.\n")
        return 0

    # Operação 3: Importação / Prévia de OFX
    if not args.arquivo:
        print("[ERRO] --arquivo é obrigatório para importação/prévia de extrato.", file=sys.stderr)
        return 1

    dt_ini = parse_data_arg(args.data_inicial)
    dt_fim = parse_data_arg(args.data_final)

    try:
        resultado = await enviar_ofx_webposto(
            unidade=unidade,
            caminho_arquivo=args.arquivo,
            data_inicial=dt_ini,
            data_final=dt_fim,
            confirmar=args.confirmar,
        )
        imprimir_relatorio_previa(resultado)
        return 0 if resultado.sucesso else 1
    except BarreiraOfxErro as exc:
        print(f"\n[BLOQUEIO DA BARREIRA] {exc}\n", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"\n[ERRO NA IMPORTAÇÃO] {type(exc).__name__}: {exc}\n", file=sys.stderr)
        return 3


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa extrato OFX no webPosto com barreira de segurança estrita."
    )
    parser.add_argument(
        "--unidade",
        type=int,
        required=True,
        help="Código da unidade/filial (ex.: 74014 para Posto Doze)",
    )
    parser.add_argument(
        "--arquivo",
        type=str,
        default=None,
        help="Caminho do arquivo .ofx (somente leitura)",
    )
    parser.add_argument(
        "--data-inicial",
        type=str,
        default=None,
        help="Data inicial (AAAA-MM-DD ou DD/MM/AAAA) — opcional",
    )
    parser.add_argument(
        "--data-final",
        type=str,
        default=None,
        help="Data final (AAAA-MM-DD ou DD/MM/AAAA) — opcional",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        default=False,
        help="Autoriza a tentativa de envio (exige travas WEBPOSTO_WRITES=1 e LOGOS_OFX_IMPORTACAO=1 no arquivo .env)",
    )
    parser.add_argument(
        "--cd-conta",
        type=int,
        default=None,
        help="Código da conta (cdConta) para conferência ou liberação",
    )
    parser.add_argument(
        "--dia",
        type=str,
        default=None,
        help="Dia para conferência (AAAA-MM-DD ou DD/MM/AAAA)",
    )
    parser.add_argument(
        "--liberar-dia",
        type=str,
        default=None,
        help="Dia a ser liberado no histórico para novo envio (AAAA-MM-DD ou DD/MM/AAAA)",
    )
    parser.add_argument(
        "--motivo",
        type=str,
        default=None,
        help="Motivo da liberação do dia",
    )
    parser.add_argument(
        "--confirmar-liberacao",
        action="store_true",
        default=False,
        help="Confirmação explícita de liberação de dia bloqueado",
    )
    parser.add_argument(
        "--confirmar-conferencia",
        action="store_true",
        default=False,
        help="Registra que o diretor conferiu os lançamentos na tela de conciliação bancária",
    )

    args = parser.parse_args()
    code = asyncio.run(main_async(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
