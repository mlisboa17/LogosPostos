"""Gera resumo operacional agregado sem nomes de funcionários ou credenciais."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..domain.execucao import ResultadoDiario
from ..domain.tempo import formatar_data


def moeda_br(valor: Decimal) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_resumo_diario(
    dia: date,
    resultados: list[ResultadoDiario],
    unidades_processadas: list[int],
    unidades_com_falha: set[int],
    pendencias_abertas: dict[int, int | None],
) -> str:
    linhas = [
        f"# Resumo do robô noturno — {formatar_data(dia)}",
        "",
        f"- Unidades processadas: {len(unidades_processadas)}",
        f"- Unidades com falha: {len(unidades_com_falha)}",
        "",
        "## Por unidade",
        "",
    ]
    por_unidade = {resultado.empresa_codigo: resultado for resultado in resultados}
    for unidade in unidades_processadas:
        linhas.extend([f"### Unidade {unidade}", ""])
        registro = por_unidade.get(unidade)
        if registro is None or registro.fechamento is None:
            linhas.append("- Fechamento: sem resultado persistido")
        else:
            caixas = registro.fechamento.caixas
            alertas = [alerta for caixa in caixas for alerta in caixa.alertas]
            faltas = [alerta for alerta in alertas if alerta.codigo == "FALTA_SEM_DESCONTO"]
            parados = [alerta for alerta in alertas if alerta.codigo == "NAO_CONSOLIDADO"]
            linhas.extend([
                f"- Caixas: {len(caixas)}",
                f"- Quebra total: {moeda_br(registro.fechamento.quebra_total)}",
                f"- Faltas sem desconto: {len(faltas)} ({moeda_br(sum((a.valor or Decimal(0) for a in faltas), Decimal(0)) )})",
                f"- Caixas parados: {len(parados)}",
            ])
        if registro is not None:
            adquirentes_ok = [
                item for item in registro.recebimentos.adquirentes if item.situacao == "ok"
            ]
            total_a_maior = sum(
                (transacao.transacao.valor for item in adquirentes_ok for transacao in item.a_maior),
                Decimal(0),
            )
            total_a_menor = sum(
                (cartao.valor for item in adquirentes_ok for cartao in item.a_menor),
                Decimal(0),
            )
            linhas.extend([
                f"- Recebimentos a maior: {moeda_br(total_a_maior)}",
                f"- Recebimentos a menor: {moeda_br(total_a_menor)}",
            ])
            for adquirente in registro.recebimentos.adquirentes:
                linhas.append(f"- {adquirente.adquirente}: {adquirente.situacao}")
        pendencias = pendencias_abertas.get(unidade)
        linhas.append(
            f"- Pendências abertas: {pendencias if pendencias is not None else 'indisponível'}"
        )
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"
