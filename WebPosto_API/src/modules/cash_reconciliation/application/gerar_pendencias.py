"""Converte alertas verificados em pendências idempotentes."""
from __future__ import annotations

import calendar
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable

from ..adapters import pendencias as repositorio_pendencias
from ..config import carregar_unidades
from ..domain.cartoes import Atribuicao
from ..domain.execucao import ResultadoDiario
from ..domain.pendencias import NovaPendencia
from ..domain.tempo import formatar_data
from .reincidencia import agregar_reincidencia

VERSAO_PENDENCIAS = "PENDENCIAS_V1"
LIMITE_REINCIDENCIA = 2


def _slug(valor: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", valor.casefold()).strip("_")


def _entrada(
    *,
    unidade: int,
    dia: date,
    tipo: str,
    severidade: str,
    valor: Decimal | None,
    referencia: str,
    mensagem: str,
    identidade: str | None = None,
) -> NovaPendencia:
    return NovaPendencia(
        unidade=unidade,
        dia=dia,
        tipo=tipo,
        severidade=severidade,
        valor=valor,
        referencia=referencia,
        mensagem=mensagem,
        identidade=identidade,
    )


def pendencias_do_dia(resultado: ResultadoDiario) -> list[NovaPendencia]:
    novas: list[NovaPendencia] = []
    if resultado.fechamento is not None:
        for auditoria in resultado.fechamento.caixas:
            alertas_laranja = []
            for alerta in auditoria.alertas:
                severidade = alerta.severidade.value
                if severidade not in {"vermelho", "laranja"}:
                    continue
                if severidade == "laranja":
                    alertas_laranja.append(alerta)
                    continue
                caixa = auditoria.caixa.codigo
                referencia = f"caixa:{caixa}"
                if alerta.codigo == "QUEBRA":
                    modalidade = _slug(alerta.mensagem.partition(":")[0])
                    referencia = f"{referencia}:modalidade:{modalidade}"
                elif alerta.codigo.startswith("SANGRIA_"):
                    referencia = f"{referencia}:sangria:{alerta.referencia}"
                elif alerta.codigo.startswith("DESPESA_"):
                    referencia = f"{referencia}:despesa:{alerta.referencia}"
                novas.append(_entrada(
                    unidade=resultado.empresa_codigo,
                    dia=resultado.dia,
                    tipo=f"fechamento_{_slug(alerta.codigo)}",
                    severidade=severidade,
                    valor=alerta.valor,
                    referencia=referencia,
                    mensagem=alerta.mensagem,
                ))
            if alertas_laranja:
                caixa = auditoria.caixa.codigo
                detalhes = {
                    "alertas": [
                        {
                            "codigo": alerta.codigo,
                            "mensagem": alerta.mensagem,
                            "valor": str(alerta.valor) if alerta.valor is not None else None,
                        }
                        for alerta in alertas_laranja
                    ],
                }
                valores = [alerta.valor for alerta in alertas_laranja if alerta.valor is not None]
                novas.append(_entrada(
                    unidade=resultado.empresa_codigo,
                    dia=resultado.dia,
                    tipo="caixa_alertas_laranja",
                    severidade="laranja",
                    valor=sum(valores, Decimal(0)) if valores else None,
                    referencia=f"caixa:{caixa}:laranja",
                    mensagem=json.dumps(detalhes, ensure_ascii=False, separators=(",", ":")),
                    identidade=f"{resultado.empresa_codigo}|{resultado.dia.isoformat()}|caixa:{caixa}|laranja",
                ))
    unidade = carregar_unidades().get(resultado.empresa_codigo)
    if unidade is not None and (
        unidade.repasse_sangria_para is not None or unidade.destino_padrao is not None
    ):
        abertas = repositorio_pendencias.contar_abertas_somente_leitura(
            unidade=resultado.empresa_codigo,
        )
        if abertas:
            antigas = []
            deslocamento = 0
            while True:
                itens, total = repositorio_pendencias.listar(
                    unidade=resultado.empresa_codigo,
                    status="aberta",
                    tipo="fechamento_sangria_sem_destino",
                    limite=100,
                    deslocamento=deslocamento,
                )
                antigas.extend(itens)
                deslocamento += len(itens)
                if not itens or deslocamento >= total:
                    break
            for pendencia in antigas:
                if pendencia.dia <= resultado.dia:
                    repositorio_pendencias.transicionar(
                        pendencia.id,
                        status_esperado="aberta",
                        status_novo="aprovada",
                        acao="aprovada",
                        usuario="robo",
                        justificativa=(
                            "Regra FECHAMENTO_V4: sangria da Conveniência 24h "
                            "repassada ao Casa Caiada (decisão do diretor em 10/10/2026)"
                            if unidade.repasse_sangria_para is not None
                            else (
                                "Regra FECHAMENTO_V4: sangria assumida no cofre "
                                f"(destino padrão {unidade.destino_padrao}), conforme decisão "
                                "do diretor em 10/10/2026"
                            )
                        ),
                    )
    for adquirente in resultado.recebimentos.adquirentes:
        if adquirente.situacao != "ok":
            continue
        for investigacao in adquirente.a_maior:
            transacao = investigacao.transacao
            referencia = transacao.identificador or transacao.nsu or transacao.autorizacao or "sem-identificador"
            novas.append(_entrada(
                unidade=resultado.empresa_codigo,
                dia=resultado.dia,
                tipo="recebimento_a_maior",
                severidade="laranja",
                valor=transacao.valor,
                referencia=f"{adquirente.adquirente}:transacao:{referencia}",
                mensagem="Recebimento na adquirente sem lançamento correspondente no webPosto.",
            ))
        for cartao in adquirente.a_menor:
            novas.append(_entrada(
                unidade=resultado.empresa_codigo,
                dia=resultado.dia,
                tipo="recebimento_a_menor",
                severidade="vermelho",
                valor=cartao.valor,
                referencia=f"{adquirente.adquirente}:cartao:{cartao.codigo}",
                mensagem="Lançamento de recebimento sem confirmação correspondente na adquirente.",
            ))
    return novas


def _ocorrencias_reincidentes(
    resultados: tuple[ResultadoDiario, ...],
) -> dict[int, dict[str, list[tuple[date, Decimal]]]]:
    ocorrencias: dict[int, dict[str, list[tuple[date, Decimal]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for resultado in resultados:
        if resultado.fechamento is not None:
            for auditoria in resultado.fechamento.caixas:
                codigo = auditoria.caixa.funcionario_codigo
                for alerta in auditoria.alertas:
                    if alerta.codigo == "QUEBRA":
                        valor = abs(alerta.valor or Decimal(0))
                        ocorrencias[codigo]["quebra"].append((resultado.dia, valor))
                for sangria in auditoria.sangrias:
                    if sangria.alterada:
                        ocorrencias[sangria.funcionario_codigo]["sangria"].append(
                            (resultado.dia, sangria.valor)
                        )
        for adquirente in resultado.recebimentos.adquirentes:
            if adquirente.adquirente.upper() != "PAGBANK":
                continue
            investigacoes = (
                *adquirente.a_maior,
                *(par.investigacao for par in adquirente.pares_provaveis),
                *(inv for grupo in getattr(adquirente, "grupos_provaveis", ()) for inv in grupo.investigacoes),
            )
            for investigacao in investigacoes:
                if investigacao.atribuicao == Atribuicao.ATRIBUIDO and investigacao.frentista is not None:
                    ocorrencias[investigacao.frentista]["recebimento"].append(
                        (resultado.dia, investigacao.transacao.valor)
                    )
    return ocorrencias


def pendencias_de_reincidencia(
    unidade: int,
    mes: str,
    resultados: Iterable[ResultadoDiario],
) -> list[NovaPendencia]:
    registros = tuple(sorted(
        (registro for registro in resultados if registro.empresa_codigo == unidade and registro.dia.strftime("%Y-%m") == mes),
        key=lambda registro: registro.dia,
    ))
    if not registros:
        return []
    inicio = date.fromisoformat(f"{mes}-01")
    ultimo_dia = calendar.monthrange(inicio.year, inicio.month)[1]
    dias = tuple(
        date.fromordinal(inicio.toordinal() + indice)
        for indice in range(min((registros[-1].dia - inicio).days + 1, ultimo_dia))
    )
    agregado = agregar_reincidencia(unidade, mes, dias, registros, {})
    ocorrencias = _ocorrencias_reincidentes(registros)
    novas = []
    for funcionario in agregado.funcionarios:
        codigo = funcionario.funcionario_codigo
        tipos = (
            (
                "quebra",
                funcionario.quebras,
                funcionario.faltas_total,
                "reincidencia_quebra",
                "vermelho",
                "quebras",
            ),
            (
                "sangria",
                funcionario.sangrias_alteradas,
                sum((valor for _, valor in ocorrencias[codigo]["sangria"]), Decimal(0)),
                "reincidencia_sangria_alterada",
                "laranja",
                "sangrias alteradas",
            ),
            (
                "recebimento",
                funcionario.recebimentos_a_maior_atribuidos,
                funcionario.valor_recebimentos_a_maior_atribuidos,
                "reincidencia_recebimento_a_maior",
                "laranja",
                "recebimentos a maior atribuídos",
            ),
        )
        for chave, quantidade, valor, tipo, severidade, rotulo in tipos:
            ocorrencias_tipo = ocorrencias[codigo][chave]
            if quantidade < LIMITE_REINCIDENCIA or len(ocorrencias_tipo) < LIMITE_REINCIDENCIA:
                continue
            dia_ocorrencia = max(dia for dia, _ in ocorrencias_tipo)
            novas.append(_entrada(
                unidade=unidade,
                dia=dia_ocorrencia,
                tipo=tipo,
                severidade=severidade,
                valor=valor,
                referencia=f"funcionario:{codigo}",
                mensagem=(
                    f"Funcionário #{codigo}: {quantidade} {rotulo} no mês "
                    f"{mes}, conforme regra {VERSAO_PENDENCIAS}."
                ),
                identidade=f"{unidade}|{mes}|{tipo}|funcionario:{codigo}",
            ))
    return novas


def executar_reincidencia_mes(
    unidade: int,
    dia: date,
    *,
    carregar,
) -> list[NovaPendencia]:
    primeiro = dia.replace(day=1)
    resultados = []
    atual = primeiro
    while atual <= dia:
        registro = carregar(unidade, atual)
        if registro is not None:
            resultados.append(registro)
        atual = date.fromordinal(atual.toordinal() + 1)
    return pendencias_de_reincidencia(unidade, dia.strftime("%Y-%m"), resultados)
