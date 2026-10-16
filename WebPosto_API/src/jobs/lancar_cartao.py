"""Prévia sem envio e confirmação explícita de um cartão (Sprint 18b).

Uso:
  python -m src.jobs.lancar_cartao --unidade <cod> --dia dd/mm/aaaa

Para enviar, exige --confirmar --nsu e aprovação do diretor.
Para resolver a auditoria sem lançar, use --resolver --nsu.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime

from dotenv import load_dotenv

from src.modules.cash_reconciliation.adapters.webposto_escrita_cartao import (
    BarreiraCartaoErro,
    resolver_caminho_env,
)
from src.modules.cash_reconciliation.adapters.webposto_http import WebPostoErro


async def executar_previa(
    empresa_codigo: int, dia: date, confirmar: bool = False, nsu: str | None = None,
    resolver: bool = False,
) -> int:
    """Prévia e confirmação usam as mesmas regras da tela e do Telegram."""
    from src.modules.cash_reconciliation.application import piloto_cartao

    if confirmar and resolver:
        print("ERRO: --resolver e --confirmar não podem ser usados juntos. Nenhum envio realizado.")
        return 1
    if (confirmar or resolver) and not nsu:
        modo = "--resolver" if resolver else "--confirmar"
        print(f"ERRO: {modo} exige --nsu de UM cartão. Nenhum envio realizado.")
        return 1
    load_dotenv(resolver_caminho_env())
    try:
        if resolver:
            resultado = await piloto_cartao.resolver(empresa_codigo, dia, nsu, autor="diretor:comando")
            print(resultado["mensagem"])
        elif confirmar:
            resultado = await piloto_cartao.confirmar(empresa_codigo, dia, nsu, autor="diretor:comando")
            print(resultado["mensagem"])
            if "antes" in resultado:
                print(f"Antes (dinheiro/cartão): {resultado['antes']}; depois: {resultado['depois']}")
        else:
            propostas = await piloto_cartao.preparar(empresa_codigo, dia)
            print(f"PRÉVIA — {dia:%d/%m/%Y}: {sum(p.elegivel for p in propostas)} elegíveis; sem lançar.")
            for proposta in propostas:
                print(proposta.texto)
            if not propostas:
                print("Nenhum cartão PagBank faltante encontrado.")
    except (piloto_cartao.PilotoErro, BarreiraCartaoErro, WebPostoErro, OSError) as exc:
        print(f"ERRO: {exc}")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Prévia e piloto de um cartão no webPosto (Sprint 18b)")
    parser.add_argument("--unidade", type=int, required=True, help="Código da unidade / filial (ex: 5555, 74014)")
    parser.add_argument("--dia", type=str, required=True, help="Data no formato dd/mm/aaaa (ex: 10/10/2026)")
    modos = parser.add_mutually_exclusive_group()
    modos.add_argument("--confirmar", action="store_true", help="Envia UM cartão após aprovação do diretor")
    modos.add_argument("--resolver", action="store_true", help="Reconsulta sem lançar e resolve a auditoria de UM cartão")
    parser.add_argument("--nsu", help="NSU completo de um único cartão; obrigatório com --confirmar ou --resolver")

    args = parser.parse_args()

    # Validação do formato do dia
    try:
        dia = datetime.strptime(args.dia.strip(), "%d/%m/%Y").date()
    except ValueError:
        print(f"ERRO: Data inválida '{args.dia}'. Utilize o formato dd/mm/aaaa.")
        sys.exit(1)

    codigo_retorno = asyncio.run(executar_previa(args.unidade, dia, args.confirmar, args.nsu, args.resolver))
    sys.exit(codigo_retorno)


if __name__ == "__main__":
    main()
