"""Somente GET; descarta campos pessoais exceto nome para exibicao local."""
from __future__ import annotations

import asyncio
from datetime import date

from src.modules.webposto_integration.http import paginar
from src.modules.webposto_integration.tempo import ler_data_hora

from ..domain.models import Abastecimento, Posto, Produto

PATHS = {
    "abastecimentos": "/INTEGRACAO/V1/ABASTECIMENTOS",
    "funcionarios": "/INTEGRACAO/V1/FUNCIONARIOS",
    "produtos": "/INTEGRACAO/V1/PRODUTOS",
    "itens": "/INTEGRACAO/V1/VENDAS/ITENS",
}


def _afericao(valor: object) -> bool:
    if valor is None:
        raise ValueError("Afericao ausente na fonte.")
    marcador = str(valor).strip().upper()
    if marcador in {"TRUE", "S", "1"}:
        return True
    if marcador in {"FALSE", "N", "0"}:
        return False
    raise ValueError("Marcador de afericao invalido.")


async def buscar(
    posto: Posto, inicio: date, fim: date,
) -> tuple[list[Abastecimento], dict[int, Produto], dict[int, str]]:
    params = {"empresaCodigo": posto.empresa_codigo, "dataInicial": inicio.isoformat(), "dataFinal": fim.isoformat()}
    abastecimentos, funcionarios, produtos, itens = await asyncio.gather(*(
        paginar(posto, PATHS[nome], params) for nome in ("abastecimentos", "funcionarios", "produtos", "itens")
    ))
    vendas = {
        i["vendaItemCodigo"]: i["vendaCodigo"] for i in itens
        if i.get("empresaCodigo") == posto.empresa_codigo
    }
    catalogo = {
        p["produtoCodigo"]: Produto(codigo=p["produtoCodigo"], nome=p["nome"], aditivado="ADITIV" in p["nome"].upper())
        for p in produtos
    }
    nomes = {
        f["funcionarioCodigo"]: f["nome"] for f in funcionarios
        if f.get("empresaCodigo") == posto.empresa_codigo
    }
    linhas = []
    for a in abastecimentos:
        if a.get("empresaCodigo") != posto.empresa_codigo or _afericao(a.get("afericao")):
            continue
        momento = ler_data_hora(a["dataHoraAbastecimento"])
        if not inicio <= momento.date() <= fim:
            continue
        linhas.append(Abastecimento(
            codigo=a["abastecimentoCodigo"], empresa_codigo=a["empresaCodigo"], momento=momento,
            litros=a["quantidade"], produto=a["codigoProduto"], frentista=a.get("codigoFrentista"),
            venda=vendas.get(a.get("vendaItemCodigo")),
        ))
    return linhas, catalogo, nomes
