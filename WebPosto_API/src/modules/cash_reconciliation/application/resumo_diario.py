"""Resumo do diretor por caixa, com detalhes operacionais e sem credenciais."""

from __future__ import annotations

import re
from html import escape
from datetime import date, datetime
from decimal import Decimal

from ..config import carregar_unidades
from ..domain.execucao import ResultadoDiario
from ..domain.fechamento import Caixa, MovimentoDespesa
from ..domain.models import Unidade
from ..domain.recebimentos import RecebimentoAdquirente, ResumoCasados, ResumoForma
from ..domain.tempo import para_local
from ..rules.fechamento import LIMITE_QUEBRA

MAPA_SETORES_CENTRO_CUSTO = {
    7295: "Pista",
    21650: "Loja",
    22310: "Conveniência",
    24423: "Food",
    18713: "Fechamento",
}

DIAS_DA_SEMANA = {
    0: "segunda-feira",
    1: "terça-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sábado",
    6: "domingo",
}


def moeda_br(valor: Decimal) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def obter_nome_setor(centro_custo: int | None) -> str:
    if centro_custo in MAPA_SETORES_CENTRO_CUSTO:
        return MAPA_SETORES_CENTRO_CUSTO[centro_custo]
    if centro_custo is not None:
        return f"cc {centro_custo}"
    return "setor não informado"


def obter_nome_posto(
    empresa_codigo: int,
    unidades_config: dict[int, Unidade] | None = None,
    curto: bool = False,
) -> str:
    if unidades_config is None:
        unidades_config = carregar_unidades()
    cfg = unidades_config.get(empresa_codigo)
    if not cfg:
        return "Posto não cadastrado"
    if cfg.empresa_codigo == 118508:
        return "Conv. 24h" if curto else "Conveniência 24h"
    return cfg.apelido or cfg.nome


def gerar_resumo_diretor(
    dia: date,
    resultados: list[ResultadoDiario],
    unidades_processadas: list[int],
    unidades_com_falha: set[int],
    pendencias_abertas: dict[int, int | None],
    pendencias_vencidas: dict[int, int | None] | None = None,
    nomes_funcionarios: dict[int, dict[int, str]] | None = None,
    unidades_config: dict[int, Unidade] | None = None,
) -> str:
    if unidades_config is None:
        unidades_config = carregar_unidades()

    por_unidade = {r.empresa_codigo: r for r in resultados}
    itens_precisa: list[tuple[str, Decimal]] = []
    itens_abertos: list[str] = []
    itens_em_ordem: list[str] = []

    for unidade in unidades_processadas:
        registro = por_unidade.get(unidade)
        posto = escape(obter_nome_posto(unidade, unidades_config))

        if registro is None or registro.fechamento is None:
            motivo = "erro ao consultar o fechamento"
            if registro and registro.erro_fechamento:
                motivo = registro.erro_fechamento
                if "falha ao consultar fechamento" in motivo.lower():
                    motivo = "erro ao consultar o fechamento"
            itens_precisa.append((f"{posto} — conferência não rodou ({motivo})", Decimal(0)))

        elif unidade in unidades_com_falha:
            itens_precisa.append((f"{posto} — auditoria com falha; consultar detalhes", Decimal(0)))

        if registro is not None:
            for adq in registro.recebimentos.adquirentes:
                if adq.situacao == "credencial inválida":
                    banco = "PagBank" if "PAGBANK" in adq.adquirente.upper() else adq.adquirente.title()
                    itens_precisa.append((f"{posto} — senha do {banco} inválida", Decimal(0)))
                elif adq.erro or adq.situacao == "erro":
                    itens_precisa.append((f"{posto} — erro no {adq.adquirente} ({adq.erro or 'falha'})", Decimal(0)))

                for am in adq.a_menor:
                    if am.valor:
                        itens_precisa.append((
                            f"{posto} · {adq.adquirente.title()} — cartão/PIX a menor {moeda_br(am.valor)} — {escape(am.responsavel)}",
                            abs(am.valor),
                        ))
                for dv in adq.divergencias_valor:
                    if dv.diferenca:
                        tipo = "a menor" if dv.diferenca > 0 else "a maior"
                        itens_precisa.append((
                            f"{posto} · {adq.adquirente.title()} — cartão {tipo} {moeda_br(abs(dv.diferenca))} — {escape(dv.cartao.responsavel)}",
                            abs(dv.diferenca),
                        ))
                for alerta in adq.alertas:
                    if "DUPLIC" in alerta.codigo:
                        responsaveis = " · ".join(dict.fromkeys(c.responsavel for c in alerta.cartoes))
                        detalhe = f" — {escape(responsaveis)}" if responsaveis else ""
                        itens_precisa.append((
                            f"{posto} — {escape(alerta.mensagem)}{detalhe}",
                            abs(alerta.valor),
                        ))

            if registro.fechamento is not None:
                for ca in registro.fechamento.caixas:
                    cx = ca.caixa
                    setor = obter_nome_setor(cx.centro_custo)
                    turno = escape(cx.turno.strip().lower()) if cx.turno else "turno não informado"

                    if not cx.fechado or any(a.codigo == "CAIXA_ABERTO" for a in ca.alertas):
                        ab = para_local(cx.abertura).strftime("%H:%M")
                        itens_abertos.append(
                            f"• {posto} · {setor} (caixa {cx.codigo}, {turno}) — aberto desde {ab}; quebra só depois de fechar"
                        )
                        continue

                    q = ca.quebra
                    alertas = {a.codigo for a in ca.alertas}
                    sem_desc = "FALTA_SEM_DESCONTO" in alertas
                    nao_cons = (not cx.consolidado) or ("NAO_CONSOLIDADO" in alertas)

                    falta = abs(q) if q < Decimal(0) else Decimal(0)
                    sobra = q if q > Decimal(0) else Decimal(0)
                    falta_sem_desconto = max(
                        (abs(a.valor or Decimal(0)) for a in ca.alertas if a.codigo == "FALTA_SEM_DESCONTO"),
                        default=Decimal(0),
                    )
                    falta = max(falta, falta_sem_desconto)

                    # QUEBRA preserva o limite usado na auditoria daquela unidade/modalidade.
                    if falta > LIMITE_QUEBRA or sem_desc or nao_cons or "QUEBRA" in alertas:
                        detalhes = []
                        if falta:
                            detalhes.append(f"falta {moeda_br(falta)}")
                        elif sobra:
                            detalhes.append(f"sobra {moeda_br(sobra)}")
                        if sem_desc:
                            detalhes.append("sem desconto")
                        if nao_cons:
                            detalhes.append("não consolidado")
                        if not detalhes:
                            detalhes.append("divergência nas modalidades; conferir")
                        itens_precisa.append((
                            f"{posto} · {setor} (caixa {cx.codigo}, {turno}) — {', '.join(detalhes)}",
                            max(falta, sobra),
                        ))
                    else:
                        if falta > Decimal(0):
                            itens_em_ordem.append(f"• {posto} · {setor} — falta {moeda_br(falta)}")
                        elif sobra > Decimal(0):
                            itens_em_ordem.append(f"• {posto} · {setor} — sobra {moeda_br(sobra)}")
                        else:
                            itens_em_ordem.append(f"• {posto} · {setor} — sem falta")
                    for alerta in ca.alertas:
                        if alerta.codigo not in {"QUEBRA", "FALTA_SEM_DESCONTO", "NAO_CONSOLIDADO", "CAIXA_ABERTO", "SANGRIA_ALTERADA"}:
                            texto = escape(alerta.mensagem)
                            texto = texto.replace("R$ 0,00", "sem valor")
                            itens_precisa.append((f"{posto} · {setor} — {texto}", abs(alerta.valor or Decimal(0))))
                for ca in registro.fechamento.caixas:
                    alteradas = {
                        a.referencia: a for a in ca.alertas
                        if a.codigo == "SANGRIA_ALTERADA"
                    }
                    if alteradas:
                        total = sum((abs(a.valor or Decimal(0)) for a in alteradas.values()), Decimal(0))
                        setor = obter_nome_setor(ca.caixa.centro_custo)
                        descricao = "sangria alterada" if len(alteradas) == 1 else "sangrias alteradas"
                        itens_precisa.append((
                            f"{posto} · {setor} — {len(alteradas)} {descricao} após o lançamento ({moeda_br(total)})",
                            total,
                        ))

    itens_precisa.sort(key=lambda x: -x[1])

    dia_nome = DIAS_DA_SEMANA.get(dia.weekday(), "")
    cabecalho = f"🌙 LOGOS — Caixas de {dia_nome}, {dia.strftime('%d/%m/%Y')}"
    linhas = [cabecalho, ""]

    if itens_precisa:
        linhas.append("⚠️ PRECISA DE VOCÊ")
        for idx, (txt, _) in enumerate(itens_precisa, 1):
            linhas.append(f"{idx}. {txt}")
        linhas.append("")

    if itens_abertos:
        linhas.append("⏳ AINDA ABERTOS")
        linhas.extend(itens_abertos)
        linhas.append("")

    if itens_em_ordem:
        linhas.append("✅ EM ORDEM")
        linhas.extend(itens_em_ordem)
        linhas.append("")

    if pendencias_abertas:
        total_ab = _total_mapeado(pendencias_abertas, unidades_processadas)
        partes_pend = [
            f"{escape(obter_nome_posto(u, unidades_config, curto=True))} {pendencias_abertas[u]}"
            for u in unidades_processadas
            if pendencias_abertas.get(u) is not None
        ]
        indisponiveis = [escape(obter_nome_posto(u, unidades_config, curto=True)) for u in unidades_processadas if pendencias_abertas.get(u) is None]
        if indisponiveis:
            partes_pend.append("indisponível: " + ", ".join(indisponiveis))
        linhas.append(f"📋 Pendências abertas: {total_ab if total_ab is not None else 'indisponível'} — " + " · ".join(partes_pend))
    vencidas = _total_mapeado(pendencias_vencidas, unidades_processadas) if pendencias_vencidas is not None else None
    if vencidas:
        linhas.append(f"⏰ Pendências vencidas: {vencidas}")

    continuacao = []
    if len(linhas) > 25:
        continuacao = ["📌 CONTINUAÇÃO DOS CAIXAS", *linhas[23:]]
        linhas = [*linhas[:23], "↪ Mais caixas e pendências nos detalhes abaixo."]
    blocos = _blocos_detalhes_diretor(resultados, unidades_processadas, nomes_funcionarios or {}, unidades_config)
    return "\n\n".join(
        "\n".join(bloco).strip() for bloco in (linhas, continuacao, *blocos) if bloco
    ) + "\n"


def gerar_resumo_diario(
    dia: date,
    resultados: list[ResultadoDiario],
    unidades_processadas: list[int],
    unidades_com_falha: set[int],
    pendencias_abertas: dict[int, int | None],
    pendencias_vencidas: dict[int, int | None] | None = None,
    nomes_funcionarios: dict[int, dict[int, str]] | None = None,
) -> str:
    return gerar_resumo_diretor(
        dia,
        resultados,
        unidades_processadas,
        unidades_com_falha,
        pendencias_abertas,
        pendencias_vencidas,
        nomes_funcionarios,
    )


def conferencia_para_registro(registro: ResultadoDiario):
    import calendar
    from datetime import timedelta
    from ..adapters.persistencia import carregar_dia
    from ..adapters.pendencias import eventos_recebimentos
    from .classificar_recebimentos import montar_conferencia

    primeiro = registro.dia.replace(day=1)
    registros = [
        r for indice in range(calendar.monthrange(primeiro.year, primeiro.month)[1])
        if primeiro + timedelta(days=indice) != registro.dia
        and (r := carregar_dia(registro.empresa_codigo, primeiro + timedelta(days=indice))) is not None
    ]
    return montar_conferencia(registro.empresa_codigo, registro.dia, registro.dia, [*registros, registro],
                             eventos_recebimentos(registro.empresa_codigo))


def linhas_acoes_recebimentos(conferencia) -> list[str]:
    linhas = []
    if conferencia.conferidos.total:
        linhas.append(f"Recebimentos: {conferencia.conferidos.quantidade} conferidos · {moeda_br(conferencia.conferidos.total)}")
    nomes = {1: "Lançar", 2: "Alterar", 3: "Apurar", 4: "Conferir à mão"}
    ativos = [i for i in conferencia.itens if i.conferencia != "conferido"]
    grupos = " · ".join(
        f"{g} {nome} {sum(i.grupo == g for i in ativos)} · {moeda_br(sum((i.valor for i in ativos if i.grupo == g), Decimal(0)))}"
        for g, nome in nomes.items() if any(i.grupo == g and i.valor for i in ativos)
    )
    if grupos:
        linhas.append(grupos)
    for i in ativos:
        if i.grupo == 3 and i.valor:
            linhas.append(f"3 Apurar: 1 · {moeda_br(i.valor)} · {i.momento:%H:%M} — {escape(i.responsavel)} · {i.regra}")
    reincidentes = {i.frentista: i for i in ativos if i.reincidente}
    for i in reincidentes.values():
        if i.reincidencia_total:
            linhas.append(f"REINCIDENTE: {escape(i.responsavel)} · {i.reincidencia_quantidade} · {moeda_br(i.reincidencia_total)}")
    for dia in conferencia.diario:
        if dia.compensacao != "sem compensacao":
            propostas = [i for i in ativos if i.grupo == 2 and i.momento.date() == dia.dia]
            diferenca = moeda_br(dia.diferenca) if dia.diferenca else "sem diferença" if dia.diferenca == 0 else "pendente"
            total = sum((i.valor for i in propostas), Decimal(0))
            valor = f" ({moeda_br(total)})" if total else ""
            linhas.append(f"Diferença do dia: {diferenca} · {len(propostas)} correções prontas{valor} · {dia.compensacao}")
    return linhas


def _data_hora_excel(momento: datetime) -> datetime:
    # Excel has no timezone support; serialize the Recife wall clock only at this boundary.
    from ..domain.tempo import para_local
    local = para_local(momento)
    return datetime.combine(local.date(), local.time())


def abas_conferencia_recebimentos(workbook, conferencias) -> None:
    acoes = workbook.create_sheet("Ações de recebimento")
    prontas = workbook.create_sheet("Correções prontas")
    detalhes = workbook.create_sheet("Detalhes por pagamento")
    detalhes.append(["Unidade", "Grupo", "Regra", "Data/hora pagamento", "Valor pagamento", "Adquirente", "Forma",
                     "NSU final", "Terminal final", "Lançamento", "Venda", "Caixa", "Data/hora lançada", "Valor lançado", "Inclusão",
                     "Abastecimento", "Data/hora abastecimento", "Valor abastecimento", "Bico", "Item", "Forma venda", "Responsável / nota / motivos"])
    acoes.append(["Unidade", "Grupo", "Data/hora", "Valor", "De", "Para", "Frentista", "Regra", "Reincidente", "Conferido (S/N)", "Observação"])
    prontas.append(["Unidade", "Lançamento", "Venda", "Caixa", "Data/hora", "Valor", "De", "Para", "Frentista", "Evidências", "Nota de certeza", "Status"])
    for conferencia in conferencias:
        diario = workbook.create_sheet(f"Dia {conferencia.unidade}")
        nomes = [t.adquirente for t in conferencia.totais_adquirentes]
        diario.append(["Data", *(v for n in nomes for v in (f"Webposto {n}", n, "Dif.")), "Diferença do dia"])
        for d in conferencia.diario:
            por_nome = {t.adquirente: t for t in d.adquirentes}
            valores = []
            for n in nomes:
                t = por_nome.get(n)
                valores.extend([float(t.webposto), float(t.recebido), float(t.diferenca)]
                               if t and t.diferenca is not None else ["pendente"] * 3)
            diario.append([d.dia, *valores, float(d.diferenca) if d.diferenca is not None else "pendente"])
            diario.cell(diario.max_row, 1).number_format = "dd/mm/yyyy"
        diario.append(["Total", *(v for t in conferencia.totais_adquirentes for v in (
            (float(t.webposto), float(t.recebido), float(t.diferenca)) if t.diferenca is not None else ("pendente",) * 3
        )), float(conferencia.diferenca_periodo) if conferencia.diferenca_periodo is not None else "pendente"])
        formas = workbook.create_sheet(f"Formas {conferencia.unidade}")
        formas.append(["Adquirente", "Forma", "Adquirente (qtd)", "Adquirente (R$)", "webPosto (qtd)", "webPosto (R$)", "Diferença"])
        por_adquirente: dict[str, list[ResumoForma]] = {}
        for f in conferencia.formas:
            por_adquirente.setdefault(f.adquirente, []).append(f.resumo)
        for adquirente, resumos in por_adquirente.items():
            for r in _agrupar_bandeiras_planilha(resumos):
                formas.append([adquirente, r.forma, r.portal.quantidade, float(r.portal.total),
                               r.webposto.quantidade, float(r.webposto.total), float(r.diferenca)])
        for i in conferencia.itens:
            acoes.append([i.unidade, i.grupo, _data_hora_excel(i.momento), float(i.valor), i.de, i.para, i.responsavel,
                          i.regra, "REINCIDENTE" if i.reincidente else "", "S" if i.conferencia == "conferido" else "N", i.observacao])
            if i.grupo == 2:
                prontas.append([i.unidade, i.lancamento, i.venda, i.caixa, _data_hora_excel(i.momento), float(i.valor),
                               i.de, i.para, i.responsavel, "; ".join(i.evidencias),
                               f"{i.nota_certeza}/100 (não é probabilidade). {i.certeza}", i.proposta_status])
            for p in i.pagamentos or (None,):
                a = p.abastecimento if p else None
                detalhes.append([i.unidade, i.grupo, i.regra, _data_hora_excel(p.momento) if p else None,
                    float(p.valor) if p else None, p.adquirente if p else None, p.forma if p else None,
                    p.nsu if p else None, p.terminal if p else None, i.lancamento, i.venda or (a.venda_codigo if a else None),
                    i.caixa, _data_hora_excel(i.momento_lancamento) if i.momento_lancamento else None,
                    float(i.valor_lancamento) if i.valor_lancamento is not None else None, i.tipo_inclusao,
                    a.codigo if a else None, _data_hora_excel(a.momento) if a else None,
                    float(a.valor) if a else None, a.bico if a else None, a.venda_item_codigo if a else None,
                    p.forma_venda if p else None, "; ".join(r.descricao for r in p.responsaveis) if p and p.responsaveis else i.responsavel])
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                elif isinstance(cell.value, datetime):
                    cell.number_format = "dd/mm/yyyy hh:mm"


def _agrupar_bandeiras_planilha(resumos: list[ResumoForma]) -> list[ResumoForma]:
    aliases = {
        "MASTERCARD": "Mastercard", "MAESTRO": "Maestro",
        "VISA": "Visa", "VISA ELECTRON": "Visa Electron",
        "ELO": "Elo", "ELO DEBITO": "Elo", "ELO DÉBITO": "Elo",
        "AMEX": "American Express", "AMERICAN EXPRESS": "American Express",
    }
    agrupados: dict[str, list[ResumoForma]] = {}
    for resumo in resumos:
        nome = re.sub(r"\s+PAGSEGURO$", "", resumo.forma.strip().upper())
        forma = aliases.get(nome, resumo.forma)
        if nome == "CARTÃO APP":
            forma = "Cartão APP (crédito sem bandeira discriminada)"
        agrupados.setdefault(forma, []).append(resumo)
    return [
        ResumoForma(
            forma=forma,
            portal=ResumoCasados(quantidade=sum(r.portal.quantidade for r in itens),
                                total=sum((r.portal.total for r in itens), Decimal(0))),
            webposto=ResumoCasados(quantidade=sum(r.webposto.quantidade for r in itens),
                                  total=sum((r.webposto.total for r in itens), Decimal(0))),
            diferenca=sum((r.portal.total - r.webposto.total for r in itens), Decimal(0)),
        )
        for forma, itens in sorted(agrupados.items())
    ]


def _totais_conciliados(adquirente: RecebimentoAdquirente) -> tuple[Decimal, Decimal] | None:
    if adquirente.situacao != "ok" or adquirente.casados is None:
        return None
    base = adquirente.casados.total
    # Na conciliação, diferença do casamento = ERP - portal; não é a diferença da bandeira.
    divergencia = sum((c.diferenca for c in adquirente.divergencias_valor), Decimal(0))
    if not adquirente.divergencias_valor:
        divergencia = adquirente.casados_valor_divergente.total
    portal = base
    erp = base + divergencia
    transacoes = [
        *(i.transacao for i in adquirente.a_maior),
        *(p.investigacao.transacao for p in adquirente.pares_provaveis),
        *(i.transacao for g in adquirente.grupos_provaveis for i in g.investigacoes),
        *(t for a in adquirente.alertas if a.codigo == "CARTAO_POS_SEM_DETALHE" for t in a.transacoes),
    ]
    ids = {c.transacao.identificador for c in adquirente.detalhes_casados}
    nsus = {c.transacao.nsu.strip().upper() for c in adquirente.detalhes_casados if c.transacao.nsu}
    for t in transacoes:
        nsu = t.nsu.strip().upper() if t.nsu else None
        if t.situacao is None and t.identificador not in ids and (not nsu or nsu not in nsus):
            portal += t.valor
            ids.add(t.identificador)
            if nsu:
                nsus.add(nsu)
    duplicadas = set()
    for alerta in adquirente.alertas:
        if alerta.codigo != "CARTAO_COBRANCA_DUPLICADA":
            continue
        chave = tuple(sorted(t.identificador for t in alerta.transacoes)) or alerta.mensagem
        if chave not in duplicadas:
            portal += alerta.valor
            duplicadas.add(chave)
    cartoes = {
        c.codigo: c for c in (
            *adquirente.a_menor,
            *(p.cartao for p in adquirente.pares_provaveis),
            *(g.cartao for g in adquirente.grupos_provaveis),
            *(c for a in adquirente.alertas if a.codigo == "CARTAO_POS_SEM_DETALHE" for c in a.cartoes),
        )
    }
    casados = {c.cartao.codigo for c in adquirente.detalhes_casados}
    erp += sum((c.valor for codigo, c in cartoes.items() if codigo not in casados), Decimal(0))
    return portal, erp


def _total_mapeado(valores: dict[int, int | None], unidades: list[int]) -> int | None:
    contagens = [valores.get(unidade) for unidade in unidades]
    if any(valor is None for valor in contagens):
        return None
    return sum(valor for valor in contagens if valor is not None)


def _quebrar_linha(texto: str, limite: int) -> list[str]:
    if len(texto) <= limite:
        return [texto]
    if texto.startswith("<b>"):
        fechamento = texto.find("</b>")
        if fechamento >= 0 and fechamento < limite:
            inicio = texto[: fechamento + 4]
            return [inicio, *_quebrar_linha(texto[fechamento + 4 :].lstrip(), limite)]
    partes: list[str] = []
    restante = texto
    while len(restante) > limite:
        corte = restante.rfind(" · ", 0, limite)
        if corte <= 0:
            corte = limite
        entidade = restante.rfind("&", 0, corte)
        if entidade > restante.rfind(";", 0, corte) and entidade > 0:
            corte = entidade
        partes.append(restante[:corte])
        restante = restante[corte:].lstrip(" ·")
    if restante:
        partes.append(restante)
    return partes


def _descricao_despesa_segura(descricao: str) -> str:
    descricao = re.sub(
        r"\b(extra|gasolina|uber)\s+(?:(?:de|do|da)\s+)?[\wÀ-ÿ'-]+",
        r"\1 [omitido]",
        descricao,
        flags=re.IGNORECASE,
    )
    descricao = re.sub(
        r"\b(pagamento|diária|diaria|reembolso)\s+(?:para|de|do|da)\s+(?!uber\b)[\wÀ-ÿ'-]+",
        r"\1 [omitido]",
        descricao,
        flags=re.IGNORECASE,
    )
    descricao = re.sub(
        r"\b(cpf|nsu|conta|chave|token)\s*(?:n[ºo.]*)?\s*[:#=]?\s*[\w-]*\d[\w./-]*",
        r"\1 [omitido]",
        descricao,
        flags=re.IGNORECASE,
    )
    descricao = re.sub(r"\b\d{3}[.]?\d{3}[.]?\d{3}-?\d{2}\b", "[omitido]", descricao)
    return re.sub(r"(?<!\d)\d{5,}(?!\d)", "[omitido]", descricao)


def gerar_mensagem_curta(
    dia: date,
    resultados: list[ResultadoDiario],
    unidades_processadas: list[int],
    unidades_com_falha: set[int],
    pendencias_abertas: dict[int, int | None],
    pendencias_vencidas: dict[int, int | None] | None = None,
    nomes_funcionarios: dict[int, dict[int, str]] | None = None,
) -> list[str]:
    """Gera resumo curto para o Telegram, usando formato do diretor por padrão."""
    resumo = gerar_resumo_diretor(
        dia, resultados, unidades_processadas, unidades_com_falha,
        pendencias_abertas, pendencias_vencidas, nomes_funcionarios,
    )
    return dividir_resumo(resumo)


def dividir_resumo(resumo: str) -> list[str]:
    """Divide nos limites de linha/entidade, considerando o UTF-16 do Telegram."""
    mensagens: list[str] = []
    atual = ""
    for linha in resumo.strip().splitlines():
        # 2000 caracteres também comportam 4000 unidades UTF-16 no pior caso.
        for parte in _quebrar_linha(linha, 2000):
            candidata = f"{atual}\n{parte}" if atual else parte
            if len(candidata.encode("utf-16-le")) // 2 > 4000:
                mensagens.append(atual)
                atual = parte
            else:
                atual = candidata
    if atual:
        mensagens.append(atual)
    return mensagens


def _blocos_detalhes_diretor(
    resultados: list[ResultadoDiario],
    unidades_processadas: list[int],
    nomes: dict[int, dict[int, str]],
    unidades_config: dict[int, Unidade],
) -> list[list[str]]:
    por_unidade = {resultado.empresa_codigo: resultado for resultado in resultados}
    blocos: list[list[str]] = []
    despesas: list[tuple[MovimentoDespesa, Caixa, str]] = []
    for unidade in unidades_processadas:
        registro = por_unidade.get(unidade)
        if registro is None:
            continue
        apelido = escape(obter_nome_posto(unidade, unidades_config))
        caixas = registro.fechamento.caixas if registro.fechamento else ()
        linhas_unidade = [f"💳 RECEBIMENTOS · {apelido}"]
        itens_recebimentos: list[tuple[Decimal, str]] = []
        cancelados = [
            transacao
            for adquirente in registro.recebimentos.adquirentes
            if adquirente.adquirente == "PAGBANK"
            for transacao in adquirente.transacoes_canceladas
            if transacao.situacao in {"cancelada", "estornada"}
        ]
        outros_eventos = sum(
            transacao.situacao not in {"cancelada", "estornada"}
            for adquirente in registro.recebimentos.adquirentes
            if adquirente.adquirente == "PAGBANK"
            for transacao in adquirente.transacoes_canceladas
        )
        if cancelados:
            linhas_unidade.append(f"{len(cancelados)} cancelados no PagBank · {moeda_br(sum((t.valor for t in cancelados), Decimal(0)))}")
        if outros_eventos:
            total_eventos = sum(
                (t.valor for a in registro.recebimentos.adquirentes if a.adquirente == "PAGBANK"
                 for t in a.transacoes_canceladas if t.situacao not in {"cancelada", "estornada"}),
                Decimal(0),
            )
            linhas_unidade.append(f"{outros_eventos} eventos não aprovados/ajustes no PagBank · {moeda_br(total_eventos)}")
        for adquirente in registro.recebimentos.adquirentes:
            fonte = "PagBank" if adquirente.adquirente == "PAGBANK" else adquirente.adquirente.title()
            if adquirente.erro or adquirente.situacao in {"erro", "credencial inválida"}:
                erro = adquirente.erro or adquirente.situacao
                if "dados até" not in erro:
                    erro += " — dados até indisponíveis"
                linhas_unidade.append(f"{fonte}: {escape(erro)}")
            totais = _totais_conciliados(adquirente)
            if totais is not None and not adquirente.erro and any(totais):
                portal, erp = totais
                diferenca = portal - erp
                estado = f"❌ diferença {moeda_br(diferenca)}" if diferenca else "✅ conferido"
                if not diferenca and (
                    adquirente.a_maior or adquirente.a_menor or adquirente.divergencias_valor
                    or adquirente.pares_provaveis or adquirente.grupos_provaveis or adquirente.sem_fonte
                    or any(a.codigo == "CARTAO_POS_SEM_DETALHE" for a in adquirente.alertas)
                ):
                    estado = "⚠️ totais iguais; itens a conferir"
                portal_txt = moeda_br(portal) if portal else "sem recebimentos"
                erp_txt = moeda_br(erp) if erp else "sem lançamentos"
                quantidade = adquirente.casados.quantidade if adquirente.casados else 0
                linhas_unidade.append(f"{fonte}: portal {portal_txt} · webPosto {erp_txt} · {estado} ({quantidade} casados)")
            elif adquirente.situacao == "ok" and totais is None and not adquirente.erro:
                linhas_unidade.append(f"{fonte}: totais da conciliação indisponíveis; conferir planilha")
            for c in adquirente.a_menor:
                if not c.valor:
                    continue
                itens_recebimentos.append((abs(c.valor),
                f"A menor: {moeda_br(c.valor)} · {c.momento:%H:%M} — {escape(c.responsavel)} — "
                f"{escape(c.motivo or 'sem confirmação na adquirente')} — "
                f"tipoInclusao={escape(c.tipo_inclusao or 'não informado')}"
                ))
            for casamento in adquirente.divergencias_valor:
                if casamento.diferenca:
                    c = casamento.cartao
                    tipo = "A menor" if casamento.diferenca > 0 else "A maior"
                    itens_recebimentos.append((abs(casamento.diferenca),
                        f"{tipo}: {moeda_br(abs(casamento.diferenca))} · {c.momento:%H:%M} — "
                        f"{escape(c.responsavel)} · tipoInclusao={escape(c.tipo_inclusao or 'não informado')}"
                    ))
            for alerta in adquirente.alertas:
                if "DUPLIC" in alerta.codigo:
                    horarios = " / ".join(dict.fromkeys(
                        t.momento.strftime("%H:%M") for t in alerta.transacoes
                    )) or " / ".join(dict.fromkeys(c.momento.strftime("%H:%M") for c in alerta.cartoes))
                    responsaveis = " · ".join(dict.fromkeys(c.responsavel for c in alerta.cartoes))
                    itens_recebimentos.append((abs(alerta.valor),
                        f"Duplicidade: {moeda_br(alerta.valor)} · {horarios or 'hora indisponível'} — {escape(alerta.mensagem)}"
                        + (f" — {escape(responsaveis)}" if responsaveis else "")
                    ))
            for inv in adquirente.a_maior:
                if not inv.transacao.valor:
                    continue
                sugeridos = "; ".join(
                    f"{c.abastecimento.nome_frentista or 'nome indisponível'} ({c.abastecimento.frentista})"
                    for c in inv.candidatos if c.abastecimento.frentista is not None
                )
                responsavel = (
                    f"Sugestão: {sugeridos}"
                    if inv.atribuicao.value == "sugestao" and sugeridos
                    else inv.responsavel
                )
                nsu = inv.transacao.nsu
                itens_recebimentos.append((abs(inv.transacao.valor),
                    f"A maior: {moeda_br(inv.transacao.valor)} · {inv.transacao.momento:%H:%M} · "
                    f"{escape(inv.transacao.bandeira or 'forma não informada')} · "
                    f"NSU {escape(nsu[-4:] if nsu else 'não informado')} — {escape(responsavel)} — "
                    "tipoInclusao=não aplicável (sem lançamento ERP)"
                ))
        itens_recebimentos.sort(key=lambda item: -item[0])
        linhas_unidade.extend("• " + texto for _, texto in itens_recebimentos[:5])
        if len(itens_recebimentos) > 5:
            linhas_unidade.append(f"+{len(itens_recebimentos) - 5} itens — detalhe na planilha")
        if len(linhas_unidade) > 1:
            blocos.append(linhas_unidade)
        despesas.extend(
            (despesa, caixa.caixa, apelido)
            for caixa in caixas for despesa in caixa.despesas if despesa.valor
        )

        vales = sorted(
            (vale for caixa in caixas for vale in caixa.vales if vale.valor),
            key=lambda item: (-item.valor, item.codigo),
        )
        if vales:
            linhas_unidade = [f"🧾 VALES · {apelido}"]
            rotulos_origem = {"C": "sobra de caixa", "D": "falta de caixa"}
            itens_vales = []
            for vale in vales:
                codigo = vale.funcionario_codigo
                nome = nomes.get(unidade, {}).get(codigo) if codigo is not None else None
                funcionario = f"{escape(nome or 'nome indisponível')} ({codigo})" if codigo is not None else "funcionário não identificado"
                item = f"{funcionario} {moeda_br(vale.valor)}"
                origem = rotulos_origem.get(vale.origem.upper())
                if origem:
                    item += f" ({origem})"
                itens_vales.append(item)
            linhas_unidade.extend("• " + item for item in itens_vales)
            blocos.append(linhas_unidade)
    if despesas:
        ordenadas = sorted(despesas, key=lambda item: (-item[0].valor, item[0].codigo))
        linhas_despesas = ["💸 DESPESAS DO CAIXA"]
        for despesa, caixa, posto in ordenadas[:8]:
            descricao = _descricao_despesa_segura(despesa.descricao or "sem descrição")
            if len(descricao) > 40:
                descricao = descricao[:37] + "..."
            plano = (
                " ".join(p for p in (despesa.plano_conta_codigo, despesa.plano_conta_nome) if p)
                if despesa.plano_conta_codigo else "SEM PLANO ⚠"
            )
            setor = obter_nome_setor(despesa.centro_custo if despesa.centro_custo is not None else caixa.centro_custo)
            linhas_despesas.append(f"• {posto} · {setor} — {escape(descricao)} — {escape(plano)} — {moeda_br(despesa.valor)}")
        if len(ordenadas) > 8:
            outras = ordenadas[8:]
            linhas_despesas.append(
                f"+{len(outras)} outras ({moeda_br(sum((item.valor for item, _, _ in outras), Decimal(0)))}) — detalhe na planilha"
            )
        blocos.insert(0, linhas_despesas)
    return blocos
