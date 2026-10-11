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
from ..domain.cartoes import Atribuicao, Investigacao
from ..domain.execucao import ResultadoDiario
from ..domain.pendencias import NovaPendencia
from ..domain.tempo import formatar_data
from .reincidencia import agregar_reincidencia

VERSAO_PENDENCIAS = "PENDENCIAS_V1"
LIMITE_REINCIDENCIA = 2


def _caixa_recebimento(resultado: ResultadoDiario, investigacao: Investigacao) -> int | None:
    if resultado.fechamento is None:
        return None
    momento = investigacao.transacao.momento
    caixas = {
        auditoria.caixa.codigo
        for auditoria in resultado.fechamento.caixas
        if auditoria.caixa.abertura <= momento
        and (auditoria.caixa.fechamento is None or momento <= auditoria.caixa.fechamento)
    }
    return next(iter(caixas)) if len(caixas) == 1 else None


def _detalhe_a_maior(adquirente: str, investigacao: Investigacao) -> dict:
    transacao = investigacao.transacao
    identificador = transacao.identificador or transacao.nsu or transacao.autorizacao or "sem-identificador"
    candidatos = [
        {
            "frentista": candidato.abastecimento.frentista,
            "nome": candidato.abastecimento.nome_frentista,
            "pontos": candidato.pontos,
            "motivos": list(candidato.motivos),
        }
        for candidato in investigacao.candidatos
    ]
    sugeridos = "; ".join(
        f"{c['nome'] or 'nome indisponível'} ({c['frentista']})"
        for c in candidatos if c["frentista"] is not None
    )
    responsavel = (
        f"Sugestão: {sugeridos}"
        if investigacao.atribuicao == Atribuicao.SUGESTAO and sugeridos
        else investigacao.responsavel
    )
    return {
        "codigo": "RECEBIMENTO_A_MAIOR",
        "adquirente": adquirente,
        "referencia": f"{adquirente}:transacao:{identificador}",
        "valor": str(transacao.valor),
        "hora": transacao.momento.strftime("%H:%M:%S"),
        "forma": transacao.bandeira,
        "nsu": transacao.nsu,
        "atribuicao": investigacao.atribuicao.value,
        "frentista": investigacao.frentista,
        "nome_frentista": investigacao.nome_frentista,
        "candidatos": candidatos,
        "mensagem": (
            "Recebimento na adquirente sem lançamento correspondente no webPosto. "
            f"{responsavel}; tipoInclusao=não aplicável (sem lançamento ERP)"
        ),
    }


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
    referencias_legadas = set()
    detalhes_legados = {}
    caixas_legadas = {}
    if repositorio_pendencias.contar_abertas_somente_leitura(
        unidade=resultado.empresa_codigo,
    ) is not None:
        for tipo in ("recebimento_a_maior", "caixa_alertas_laranja"):
            deslocamento = 0
            while True:
                itens, total = repositorio_pendencias.listar(
                    unidade=resultado.empresa_codigo, tipo=tipo,
                    limite=100, deslocamento=deslocamento,
                )
                for p in itens:
                    if p.dia != resultado.dia:
                        continue
                    if tipo == "recebimento_a_maior" and p.status in {"aberta", "substituida"}:
                        referencias_legadas.add(p.referencia)
                        if p.status == "aberta":
                            detalhes_legados[p.referencia] = {
                                "codigo": "RECEBIMENTO_A_MAIOR_HISTORICO",
                                "adquirente": p.referencia.partition(":")[0],
                                "referencia": p.referencia,
                                "valor": str(p.valor) if p.valor is not None else None,
                                "hora": None, "forma": None, "nsu": None,
                                "mensagem": p.mensagem + (
                                    " Hora, forma e NSU indisponíveis no registro legado; "
                                    "não consta na conciliação atual."
                                ),
                                "classificacao_atual": "não consta na conciliação atual",
                            }
                    elif tipo == "caixa_alertas_laranja":
                        caixa = p.referencia.split(":")[1]
                        for h in json.loads(p.mensagem).get("historicos", []):
                            referencias_legadas.add(h["referencia"])
                            detalhes_legados[h["referencia"]] = h
                            caixas_legadas[h["referencia"]] = int(caixa) if caixa.isdigit() else None
                deslocamento += len(itens)
                if not itens or deslocamento >= total:
                    break
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
        if adquirente.situacao != "ok" and not adquirente.alertas:
            continue
        laranja = defaultdict(list)
        historicos = defaultdict(list)
        for alerta in adquirente.alertas:
            referencia = ":".join(str(c.codigo) for c in alerta.cartoes)
            if alerta.severidade == "laranja":
                caixa = alerta.cartoes[0].caixa_codigo if alerta.cartoes else None
                laranja[caixa].append(
                    {
                        "codigo": alerta.codigo,
                        "mensagem": alerta.mensagem,
                        "valor": str(alerta.valor),
                    }
                )
                continue
            novas.append(
                _entrada(
                    unidade=resultado.empresa_codigo,
                    dia=resultado.dia,
                    tipo=(
                        "recebimento_valor_a_menor"
                        if alerta.codigo == "CARTAO_VALOR_A_MENOR"
                        else "recebimento_nsu_repetido"
                    ),
                    severidade="vermelho",
                    valor=alerta.valor,
                    referencia=f"{adquirente.adquirente}:{alerta.codigo}:{referencia}",
                    mensagem=alerta.mensagem,
                )
            )
        for investigacao in adquirente.a_maior:
            caixa = _caixa_recebimento(resultado, investigacao)
            laranja[caixa].append(_detalhe_a_maior(adquirente.adquirente, investigacao))
        provaveis = [
            (par.investigacao, "par provável") for par in adquirente.pares_provaveis
        ] + [
            (inv, "grupo provável")
            for grupo in adquirente.grupos_provaveis for inv in grupo.investigacoes
        ]
        for investigacao, classificacao in provaveis:
            detalhe = _detalhe_a_maior(adquirente.adquirente, investigacao)
            if detalhe["referencia"] in referencias_legadas:
                detalhe["codigo"] = "RECEBIMENTO_A_MAIOR_HISTORICO"
                detalhe["classificacao_atual"] = classificacao
                caixa = _caixa_recebimento(resultado, investigacao)
                historicos[caixa].append(detalhe)
        referencias_atuais = {
            _detalhe_a_maior(adquirente.adquirente, inv)["referencia"]
            for inv in (*adquirente.a_maior, *(i for i, _ in provaveis))
        }
        for referencia, detalhe in detalhes_legados.items():
            if (
                detalhe["adquirente"] == adquirente.adquirente
                and referencia not in referencias_atuais
            ):
                historicos[caixas_legadas.get(referencia)].append(detalhe)
        for caixa in dict.fromkeys((*laranja, *historicos)):
            itens_laranja = laranja[caixa]
            itens_historicos = historicos[caixa]
            caixa_grupo = caixa if caixa is not None else "sem caixa"
            referencia = f"caixa:{caixa_grupo}:laranja"
            existente = next(
                (
                    entrada
                    for entrada in novas
                    if entrada.tipo == "caixa_alertas_laranja" and entrada.referencia == referencia
                ),
                None,
            )
            if existente is not None:
                detalhes = json.loads(existente.mensagem)
                itens_laranja = detalhes["alertas"] + itens_laranja
                itens_historicos = detalhes.get("historicos", []) + itens_historicos
                novas.remove(existente)
            valores = [Decimal(a["valor"]) for a in itens_laranja if a["valor"] is not None]
            novas.append(
                _entrada(
                    unidade=resultado.empresa_codigo,
                    dia=resultado.dia,
                    tipo="caixa_alertas_laranja",
                    severidade="laranja",
                    valor=sum(valores, Decimal(0)) if valores else None,
                    referencia=referencia,
                    identidade=f"{resultado.empresa_codigo}|{resultado.dia.isoformat()}|caixa:{caixa_grupo}|laranja",
                    mensagem=json.dumps(
                        {"alertas": itens_laranja, "historicos": itens_historicos},
                        ensure_ascii=False,
                    ),
                )
            )
        for cartao in adquirente.a_menor:
            novas.append(
                _entrada(
                    unidade=resultado.empresa_codigo,
                    dia=resultado.dia,
                    tipo="recebimento_a_menor",
                    severidade="vermelho",
                    valor=cartao.valor,
                    referencia=f"{adquirente.adquirente}:cartao:{cartao.codigo}",
                    mensagem=(
                        f"{cartao.motivo or 'Lançamento de recebimento sem confirmação correspondente na adquirente.'}"
                        f" — {cartao.responsavel}; tipoInclusao={cartao.tipo_inclusao or 'não informado'}"
                    ),
                )
            )
    adquirentes_verificados = {
        item.adquirente
        for item in resultado.recebimentos.adquirentes
        if item.proveniencia
        and item.proveniencia.versao_regra in {"CARTOES_V3_1", "CARTOES_V3_2"}
        and item.situacao in {"ok", "pendente"}
    }
    if adquirentes_verificados and repositorio_pendencias.contar_abertas_somente_leitura(
        unidade=resultado.empresa_codigo,
    ):
        referencias_validas = {
            entrada.referencia for entrada in novas if entrada.tipo == "recebimento_nsu_repetido"
        }
        antigas = []
        deslocamento = 0
        while True:
            itens, total = repositorio_pendencias.listar(
                unidade=resultado.empresa_codigo,
                status="aberta",
                tipo="recebimento_nsu_repetido",
                limite=100,
                deslocamento=deslocamento,
            )
            antigas.extend(itens)
            deslocamento += len(itens)
            if not itens or deslocamento >= total:
                break
        for pendencia in antigas:
            if (
                pendencia.dia == resultado.dia
                and pendencia.referencia.partition(":")[0] in adquirentes_verificados
                and pendencia.referencia not in referencias_validas
            ):
                repositorio_pendencias.transicionar(
                    pendencia.id,
                    status_esperado="aberta",
                    status_novo="aprovada",
                    acao="aprovada",
                    usuario="robo",
                    justificativa=(
                        "Regra CARTOES_V3_1: autorização repetida com valor/dia "
                        "diferentes não indica duplicidade"
                    ),
                )
    verificados_v32 = [
        a for a in resultado.recebimentos.adquirentes
        if a.situacao == "ok" and a.proveniencia
        and a.proveniencia.versao_regra == "CARTOES_V3_2"
    ]
    if verificados_v32:
        referencias_conferidas = {
            f"{a.adquirente}:cartao:{codigo}"
            for a in verificados_v32 for codigo in a.codigos_conferidos
        }
        grupos_ativos = {
            p.referencia for p in novas
            if p.tipo == "caixa_alertas_laranja" and json.loads(p.mensagem)["alertas"]
        }
        # Grupos podem incluir fechamento e outros adquirentes: so encerrar com coleta completa.
        grupos_verificados = (
            resultado.fechamento is not None
            and all(a.situacao == "ok" for a in resultado.recebimentos.adquirentes)
        )
        for tipo in ("recebimento_a_menor", "caixa_alertas_laranja"):
            if tipo == "caixa_alertas_laranja" and not grupos_verificados:
                continue
            deslocamento = 0
            antigas = []
            while True:
                itens, total = repositorio_pendencias.listar(
                    unidade=resultado.empresa_codigo, status="aberta",
                    tipo=tipo, limite=100, deslocamento=deslocamento,
                )
                antigas.extend(itens)
                deslocamento += len(itens)
                if not itens or deslocamento >= total:
                    break
            for p in antigas:
                if p.dia != resultado.dia:
                    continue
                resolvida = (
                    p.referencia in referencias_conferidas
                    if tipo == "recebimento_a_menor"
                    else p.referencia not in grupos_ativos
                )
                if resolvida:
                    repositorio_pendencias.transicionar(
                        p.id, status_esperado="aberta", status_novo="aprovada",
                        acao="aprovada", usuario="robo",
                        justificativa=(
                            "Regra CARTOES_V3_2: lançamento conferido por NSU/cupom/POS."
                            if tipo == "recebimento_a_menor"
                            else "Regra CARTOES_V3_2: grupo sem alertas laranja ativos no reprocessamento completo."
                        ),
                    )
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
