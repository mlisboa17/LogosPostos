"""Gera resumo operacional agregado sem nomes de funcionários ou credenciais."""

from __future__ import annotations

import re
from html import escape
from datetime import date
from decimal import Decimal

from ..config import carregar_unidades
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
            linhas.extend(
                [
                    f"- Caixas: {len(caixas)}",
                    f"- Quebra total: {moeda_br(registro.fechamento.quebra_total)}",
                    f"- Faltas sem desconto: {len(faltas)} ({moeda_br(sum((a.valor or Decimal(0) for a in faltas), Decimal(0)) )})",
                    f"- Caixas parados: {len(parados)}",
                ]
            )
        if registro is not None:
            adquirentes_ok = [
                item for item in registro.recebimentos.adquirentes if item.situacao == "ok"
            ]
            total_a_maior = sum(
                (
                    transacao.transacao.valor
                    for item in adquirentes_ok
                    for transacao in item.a_maior
                ),
                Decimal(0),
            )
            total_a_menor = sum(
                (cartao.valor for item in adquirentes_ok for cartao in item.a_menor),
                Decimal(0),
            )
            linhas.extend(
                [
                    f"- Recebimentos a maior: {moeda_br(total_a_maior)}",
                    f"- Recebimentos a menor: {moeda_br(total_a_menor)}",
                ]
            )
            for adquirente in registro.recebimentos.adquirentes:
                linhas.append(f"- {adquirente.adquirente}: {adquirente.situacao}")
        pendencias = pendencias_abertas.get(unidade)
        linhas.append(
            f"- Pendências abertas: {pendencias if pendencias is not None else 'indisponível'}"
        )
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"


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
    """Gera resumo HTML por filial para Telegram, sem persistir nomes consultados."""
    vencidas = pendencias_vencidas or {}
    nomes = nomes_funcionarios or {}
    unidades_config = carregar_unidades()
    por_unidade = {resultado.empresa_codigo: resultado for resultado in resultados}
    total_abertas = _total_mapeado(pendencias_abertas, unidades_processadas)
    total_vencidas = _total_mapeado(vencidas, unidades_processadas)
    prefixo = [
        f"<b>LOGOS — Caixas de {formatar_data(dia)}</b>",
        f"{'Robô com falha' if unidades_com_falha else 'Robô ok'} · Pendências: "
        f"{total_abertas if total_abertas is not None else 'indisponível'} abertas · "
        f"{total_vencidas if total_vencidas is not None else 'indisponível'} vencidas",
    ]
    avisos: list[str] = []
    for unidade in unidades_processadas:
        registro = por_unidade.get(unidade)
        configurada = unidades_config.get(unidade)
        apelido = (configurada.apelido or configurada.nome) if configurada else str(unidade)
        if unidade in unidades_com_falha:
            avisos.append(f"Falha em {escape(apelido)}")
        if registro is None:
            continue
        avisos.extend(
            f"{escape(item.adquirente)} da {escape(apelido)} com credencial inválida"
            for item in registro.recebimentos.adquirentes
            if item.situacao == "credencial inválida"
        )
    if avisos:
        prefixo.append("Aviso: " + " · ".join(avisos))

    blocos: list[tuple[bool, list[str]]] = []
    for unidade in unidades_processadas:
        registro = por_unidade.get(unidade)
        configurada = unidades_config.get(unidade)
        apelido = (configurada.apelido or configurada.nome) if configurada else str(unidade)
        apelido_html = escape(apelido.upper())
        if registro is None or registro.fechamento is None:
            linhas_unidade = [f"<b>⚠ {apelido_html}</b>", "Fechamento indisponível"]
            if registro:
                linhas_unidade.extend(
                    f"Premmia: {escape(item.erro)}"
                    for item in registro.recebimentos.adquirentes
                    if item.adquirente == "PREMMIA" and item.erro
                )
            blocos.append((True, linhas_unidade))
            continue

        caixas = registro.fechamento.caixas
        alertas = [alerta for caixa in caixas for alerta in caixa.alertas]
        faltas = [alerta for alerta in alertas if alerta.codigo == "FALTA_SEM_DESCONTO"]
        quebras = [
            alerta
            for alerta in alertas
            if alerta.codigo == "QUEBRA" and abs(alerta.valor or Decimal(0)) > Decimal("100")
        ]
        caixas_por_codigo = {auditoria.caixa.codigo: auditoria for auditoria in caixas}
        nao_consolidados = {
            alerta.referencia for alerta in alertas if alerta.codigo == "NAO_CONSOLIDADO"
        }
        problemas = bool(
            faltas
            or quebras
            or unidade in unidades_com_falha
            or any(
                item.alertas or item.a_menor or item.a_maior or item.erro
                for item in registro.recebimentos.adquirentes
            )
        )
        linhas_unidade = [f"<b>{'⚠' if problemas else '✓'} {apelido_html}</b>"]
        if faltas:
            for falta in faltas:
                caixa = caixas_por_codigo.get(falta.referencia)
                codigo_funcionario = caixa.caixa.funcionario_codigo if caixa else None
                nome = (
                    nomes.get(unidade, {}).get(codigo_funcionario) if codigo_funcionario else None
                )
                operador = escape(nome) if nome else f"func. {codigo_funcionario or 'indisponível'}"
                detalhe = (
                    f"Falta sem desconto: {moeda_br(abs(falta.valor or Decimal(0)))} — {operador}"
                )
                if falta.referencia in nao_consolidados:
                    detalhe += " (caixa ainda não consolidado)"
                linhas_unidade.append(detalhe)
        elif quebras:
            total_quebras = sum(
                (abs(alerta.valor or Decimal(0)) for alerta in quebras),
                Decimal(0),
            )
            linhas_unidade.append(f"Quebra acima de R$ 100: {moeda_br(total_quebras)}")
        else:
            linhas_unidade.append("Sem falta")

        divergencias = [
            casamento
            for adquirente in registro.recebimentos.adquirentes
            for casamento in adquirente.divergencias_valor
            if casamento.diferenca > 0
        ]
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
        if divergencias:
            total = sum((c.diferenca for c in divergencias), Decimal(0))
            linhas_unidade.append(
                f"Cartões: {len(divergencias)} com valor menor que o recebido (faltam {moeda_br(total)})"
            )
        if cancelados:
            linhas_unidade.append(f"{len(cancelados)} cancelados no PagBank")
        if outros_eventos:
            linhas_unidade.append(f"{outros_eventos} eventos não aprovados/ajustes no PagBank")
        for adquirente in registro.recebimentos.adquirentes:
            if adquirente.adquirente == "PREMMIA":
                if adquirente.situacao == "ok" and adquirente.casados:
                    divergencias_premmia = (
                        len(adquirente.a_menor)
                        + len(adquirente.a_maior)
                        + len(adquirente.divergencias_valor)
                        + sum(a.codigo == "CARTAO_NSU_REPETIDO" for a in adquirente.alertas)
                    )
                    linhas_unidade.append(
                        f"Premmia: {adquirente.casados.quantidade} conferidos · "
                        f"{moeda_br(adquirente.casados.total)} · {divergencias_premmia} divergências"
                    )
                elif adquirente.erro:
                    linhas_unidade.append(f"Premmia: {escape(adquirente.erro)}")
            linhas_unidade.extend(escape(alerta.mensagem) for alerta in adquirente.alertas)
            linhas_unidade.extend(
                f"A menor: {moeda_br(c.valor)} — {escape(c.responsavel)} — "
                f"{escape(c.motivo or 'sem confirmação na adquirente')} — "
                f"tipoInclusao={escape(c.tipo_inclusao or 'não informado')}"
                for c in adquirente.a_menor
            )
            for inv in adquirente.a_maior:
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
                linhas_unidade.append(
                    f"A maior: {moeda_br(inv.transacao.valor)} · {inv.transacao.momento:%H:%M} · "
                    f"{escape(inv.transacao.bandeira or 'forma não informada')} · "
                    f"NSU {escape(nsu[-4:] if nsu else 'não informado')} — {escape(responsavel)} — "
                    "tipoInclusao=não aplicável (sem lançamento ERP)"
                )

        despesas = [despesa for caixa in caixas for despesa in caixa.despesas]
        if despesas:
            ordenadas = sorted(despesas, key=lambda item: (-item.valor, item.codigo))
            linhas_unidade.append(
                f"Despesas: {len(despesas)} · {moeda_br(sum((item.valor for item in despesas), Decimal(0)))}"
            )
            for despesa in ordenadas[:8]:
                descricao = _descricao_despesa_segura(despesa.descricao or "sem descrição")
                if len(descricao) > 40:
                    descricao = descricao[:37] + "..."
                plano = (
                    "SEM PLANO ⚠"
                    if not despesa.plano_conta_codigo
                    else despesa.plano_conta_nome or despesa.plano_conta_codigo
                )
                plano_html = escape(plano)
                if despesa.plano_conta_codigo and despesa.plano_conta_nome:
                    plano_html = escape(f"{despesa.plano_conta_codigo} {despesa.plano_conta_nome}")
                linhas_unidade.append(
                    f"• {moeda_br(despesa.valor)} — {escape(descricao)} — {plano_html}"
                )
            if len(ordenadas) > 8:
                outras = ordenadas[8:]
                linhas_unidade.append(
                    f"+{len(outras)} outras ({moeda_br(sum((item.valor for item in outras), Decimal(0)))})"
                )

        vales = sorted(
            (vale for caixa in caixas for vale in caixa.vales),
            key=lambda item: (-item.valor, item.codigo),
        )
        if vales:
            linhas_unidade.append(
                f"Vales: {len(vales)} · {moeda_br(sum((vale.valor for vale in vales), Decimal(0)))}"
            )
            rotulos_origem = {"C": "sobra de caixa", "D": "falta de caixa"}
            itens_vales = []
            for vale in vales[:6]:
                codigo = vale.funcionario_codigo
                nome = nomes.get(unidade, {}).get(codigo) if codigo is not None else None
                funcionario = escape(nome) if nome else f"func. {codigo or 'indisponível'}"
                item = f"{funcionario} {moeda_br(vale.valor)}"
                origem = rotulos_origem.get(vale.origem.upper())
                if origem:
                    item += f" ({origem})"
                itens_vales.append(item)
            if len(vales) > 6:
                outros = vales[6:]
                itens_vales.append(
                    f"+{len(outros)} outros ({moeda_br(sum((vale.valor for vale in outros), Decimal(0)))})"
                )
            linhas_unidade.append("• " + " · ".join(itens_vales))
        blocos.append((problemas, linhas_unidade))

    blocos.sort(key=lambda bloco: not bloco[0])
    separador = "━━━━━━━━━━━━━━━━"
    cabecalho = "\n".join(prefixo)
    mensagem_completa = (
        cabecalho + "\n" + "\n".join(f"{separador}\n" + "\n".join(linhas) for _, linhas in blocos)
    )
    if len(mensagem_completa) <= 4000:
        return [mensagem_completa]

    mensagens: list[str] = []
    primeiro_bloco = True
    for _, linhas in blocos:
        bloco = f"{separador}\n" + "\n".join(linhas)
        if primeiro_bloco and len(cabecalho) + 1 + len(bloco) <= 4000:
            mensagens.append(cabecalho + "\n" + bloco)
            primeiro_bloco = False
            continue
        if primeiro_bloco:
            mensagens.append(cabecalho)
            primeiro_bloco = False
        if len(bloco) <= 4000:
            mensagens.append(bloco)
            continue
        mensagens.extend(_quebrar_linha(bloco, 4000))
    if not mensagens:
        mensagens.append(cabecalho)
    return mensagens
