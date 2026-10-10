"""Agregação mensal dos alertas persistidos, sem consultar adquirentes."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable

from ..domain.execucao import ResultadoDiario
from ..domain.reincidencia import FuncionarioReincidencia, ResultadoReincidencia
from ..domain.recebimentos import ResultadoRecebimentos
from ..domain.tempo import formatar_data
from ..domain.cartoes import Atribuicao


def _novo_total() -> dict[str, int | Decimal]:
    return {
        "quebras": 0,
        "faltas_total": Decimal(0),
        "sangrias_alteradas": 0,
        "recebimentos_a_maior_atribuidos": 0,
        "valor_recebimentos_a_maior_atribuidos": Decimal(0),
        "recebimentos_a_maior_sugeridos": 0,
        "valor_recebimentos_a_maior_sugeridos": Decimal(0),
    }


def agregar_reincidencia(
    empresa_codigo: int,
    mes: str,
    dias: Iterable[date],
    resultados: Iterable[ResultadoDiario],
    nomes: dict[int, str],
) -> ResultadoReincidencia:
    dias = tuple(dias)
    registros = {registro.dia: registro for registro in resultados}
    totais: dict[int, dict[str, int | Decimal]] = defaultdict(_novo_total)

    for dia in dias:
        registro = registros.get(dia)
        if registro is None:
            continue
        fechamento = registro.fechamento
        if fechamento is not None:
            for auditoria in fechamento.caixas:
                codigo = auditoria.caixa.funcionario_codigo
                total = totais[codigo]
                if any(alerta.codigo == "QUEBRA" for alerta in auditoria.alertas):
                    total["quebras"] += 1
                total["faltas_total"] += sum(
                    (-linha.diferenca for linha in auditoria.modalidades if linha.diferenca < 0),
                    Decimal(0),
                )
                total["sangrias_alteradas"] += sum(1 for sangria in auditoria.sangrias if sangria.alterada)
        _agregar_recebimentos(registro.recebimentos, totais)

    funcionarios = tuple(
        FuncionarioReincidencia(
            funcionario_codigo=codigo,
            nome=nomes.get(codigo),
            **dados,
        )
        for codigo, dados in sorted(totais.items())
    )
    return ResultadoReincidencia(
        empresa_codigo=empresa_codigo,
        mes=mes,
        dias_com_dados=tuple(formatar_data(dia) for dia in dias if dia in registros),
        dias_sem_dados=tuple(formatar_data(dia) for dia in dias if dia not in registros),
        dias_sem_fechamento=tuple(
            formatar_data(dia)
            for dia in dias
            if dia not in registros or registros[dia].fechamento is None
        ),
        dias_sem_recebimentos=tuple(
            formatar_data(dia)
            for dia in dias
            if dia not in registros
            or not any(
                item.adquirente.upper() == "PAGBANK" and item.situacao == "ok"
                for item in registros[dia].recebimentos.adquirentes
            )
        ),
        funcionarios=funcionarios,
    )


def _agregar_recebimentos(
    recebimentos: ResultadoRecebimentos,
    totais: dict[int, dict[str, int | Decimal]],
) -> None:
    for adquirente in recebimentos.adquirentes:
        if adquirente.adquirente.upper() != "PAGBANK":
            continue
        investigacoes = (
            *adquirente.a_maior,
            *(par.investigacao for par in adquirente.pares_provaveis),
        )
        for investigacao in investigacoes:
            if investigacao.atribuicao == Atribuicao.ATRIBUIDO and investigacao.frentista is not None:
                total = totais[investigacao.frentista]
                total["recebimentos_a_maior_atribuidos"] += 1
                total["valor_recebimentos_a_maior_atribuidos"] += investigacao.transacao.valor
            elif investigacao.atribuicao == Atribuicao.SUGESTAO:
                candidatos = {
                    candidato.abastecimento.frentista
                    for candidato in investigacao.candidatos
                    if candidato.abastecimento.frentista is not None
                }
                for codigo in candidatos:
                    total = totais[codigo]
                    total["recebimentos_a_maior_sugeridos"] += 1
                    total["valor_recebimentos_a_maior_sugeridos"] += investigacao.transacao.valor
