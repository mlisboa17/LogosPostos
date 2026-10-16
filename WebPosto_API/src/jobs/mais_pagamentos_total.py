"""Registra total do diretor localmente e compara por GET, sem lançar nem enviar."""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.modules.cash_reconciliation.application import mais_pagamentos as mais
from src.modules.cash_reconciliation.application.auditar_fechamento import auditar_unidade
from src.modules.cash_reconciliation.adapters.webposto_http import WebPostoErro
from src.modules.cash_reconciliation.config import carregar_unidades
from src.modules.cash_reconciliation.domain.tempo import agora
from types import SimpleNamespace


async def executar(unidade, dia, total):
    dado = mais.TotalMaisPagamentos(unidade=unidade, dia=dia, total=total, informado_em=agora())
    anterior = mais.carregar(unidade, dia)
    if anterior:
        dado = dado.model_copy(update={"pix": anterior.pix})
    mais.salvar(dado)
    print("Total Mais Pagamentos registrado localmente (fonte: diretor).")
    fechamento = await auditar_unidade(unidade, dia, dia)
    conf, partes = mais.comparar(SimpleNamespace(empresa_codigo=unidade, dia=dia, fechamento=fechamento),
                                carregar_unidades()[unidade], dado)
    from src.modules.cash_reconciliation.application.resumo_diario import moeda_br
    print(f"Portal informado: {moeda_br(conf.total)}; Transf. Crédito: "
          f"{moeda_br(conf.webposto) if conf.webposto is not None else 'indisponível'}; "
          f"diferença: {moeda_br(conf.diferenca) if conf.diferenca is not None else 'não calculada'}.")
    for parte in partes:
        print(parte.correcao)
    if conf.aviso:
        print(conf.aviso)
    print("Nenhum lançamento no webPosto; nenhuma mensagem enviada.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unidade", type=int, required=True, choices=carregar_unidades())
    parser.add_argument("--dia", required=True)
    parser.add_argument("--total", required=True)
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    try:
        dia = datetime.strptime(args.dia, "%d/%m/%Y").date()
        return asyncio.run(executar(args.unidade, dia, mais.ler_valor(args.total)))
    except (ValueError, OSError, TimeoutError, WebPostoErro):
        print("ERRO: não foi possível registrar/conferir o total Mais Pagamentos; confira os dados e a coleta. Nenhum lançamento.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
