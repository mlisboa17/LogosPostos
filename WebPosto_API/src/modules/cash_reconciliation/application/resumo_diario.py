"""Gera resumo operacional agregado sem nomes de funcionários ou credenciais."""

from __future__ import annotations

import re
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
    partes: list[str] = []
    restante = texto
    while len(restante) > limite:
        corte = restante.rfind(" · ", 0, limite)
        if corte <= 0:
            corte = limite
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
) -> list[str]:
    """Gera mensagens simples para Telegram, dividindo em blocos de até 4.000 caracteres."""
    vencidas = pendencias_vencidas or {}
    unidades_config = carregar_unidades()
    por_unidade = {resultado.empresa_codigo: resultado for resultado in resultados}
    situacao_robo = "robô com falha" if unidades_com_falha else "robô ok"
    total_abertas = _total_mapeado(pendencias_abertas, unidades_processadas)
    total_vencidas = _total_mapeado(vencidas, unidades_processadas)
    prefixo = [
        f"LOGOS — Caixas de {formatar_data(dia)} ({situacao_robo})",
        (
            "Pendências: "
            f"{total_abertas if total_abertas is not None else 'indisponível'} "
            "abertas · "
            f"{total_vencidas if total_vencidas is not None else 'indisponível'} "
            "vencidas"
        ),
    ]
    avisos: list[str] = []
    for unidade in unidades_processadas:
        registro = por_unidade.get(unidade)
        configurada = unidades_config.get(unidade)
        apelido = (configurada.apelido or configurada.nome) if configurada else str(unidade)
        if unidade in unidades_com_falha:
            avisos.append(f"Falha em {apelido}")
        if registro is None:
            continue
        avisos.extend(
            f"{item.adquirente} da {apelido} com credencial inválida"
            for item in registro.recebimentos.adquirentes
            if item.situacao == "credencial inválida"
        )
    if avisos:
        prefixo.append("Aviso: " + " · ".join(avisos))

    blocos: list[list[str]] = []
    for unidade in unidades_processadas:
        registro = por_unidade.get(unidade)
        configurada = unidades_config.get(unidade)
        apelido = (configurada.apelido or configurada.nome) if configurada else str(unidade)
        if registro is None or registro.fechamento is None:
            linhas_unidade = [f"⚠ {apelido}: fechamento indisponível"]
        else:
            caixas = registro.fechamento.caixas
            alertas = [alerta for caixa in caixas for alerta in caixa.alertas]
            faltas = [alerta for alerta in alertas if alerta.codigo == "FALTA_SEM_DESCONTO"]
            quebras = [
                alerta
                for alerta in alertas
                if alerta.codigo == "QUEBRA" and abs(alerta.valor or Decimal(0)) > Decimal("100")
            ]
            referencia_nao_consolidado = {
                alerta.referencia for alerta in alertas if alerta.codigo == "NAO_CONSOLIDADO"
            }
            tem_caixa_nao_consolidado = any(
                alerta.referencia in referencia_nao_consolidado for alerta in faltas
            )
            partes: list[str] = []
            if faltas:
                total_faltas = sum((alerta.valor or Decimal(0) for alerta in faltas), Decimal(0))
                falta_rotulo = "falta" if len(faltas) == 1 else "faltas"
                partes.append(
                    f"{len(faltas)} {falta_rotulo}, {moeda_br(total_faltas)} sem desconto"
                )
            if quebras and not faltas:
                total_quebras = sum(
                    (abs(alerta.valor or Decimal(0)) for alerta in quebras),
                    Decimal(0),
                )
                partes.append(f"quebra {moeda_br(total_quebras)}")
            if tem_caixa_nao_consolidado:
                partes.append("(caixa ainda não consolidado)")
            linhas_unidade = [
                f"{'⚠' if partes else '✓'} {apelido}: {'; '.join(partes) if partes else 'sem falta'}"
            ]

            despesas = [despesa for caixa in caixas for despesa in caixa.despesas]
            if despesas:
                ordenadas = sorted(despesas, key=lambda item: (-item.valor, item.codigo))
                mostradas = ordenadas[:8]
                total_despesas = sum((item.valor for item in despesas), Decimal(0))
                linhas_unidade.append(
                    f"Despesas {apelido} ({len(despesas)} · {moeda_br(total_despesas)}):"
                )
                for despesa in mostradas:
                    descricao = _descricao_despesa_segura(despesa.descricao or "sem descrição")
                    if len(descricao) > 40:
                        descricao = descricao[:37] + "..."
                    plano = (
                        "SEM PLANO ⚠"
                        if not despesa.plano_conta_codigo
                        else despesa.plano_conta_nome or despesa.plano_conta_codigo
                    )
                    linhas_unidade.append(f"- {moeda_br(despesa.valor)} · {descricao} · {plano}")
                if len(ordenadas) > 8:
                    outras = ordenadas[8:]
                    total_outras = sum((item.valor for item in outras), Decimal(0))
                    linhas_unidade.append(f"+{len(outras)} outras ({moeda_br(total_outras)})")

            vales = [vale for caixa in caixas for vale in caixa.vales]
            if vales:
                total_vales = sum((vale.valor for vale in vales), Decimal(0))
                origem_nome = {"C": "sobra de caixa", "D": "falta de caixa", "V": "vale"}
                linhas_unidade.append(f"Vales {apelido} ({len(vales)} · {moeda_br(total_vales)}):")
                itens_vales = []
                for vale in vales:
                    origem = origem_nome.get(
                        vale.origem.upper(), vale.origem or "origem não informada"
                    )
                    funcionario = (
                        str(vale.funcionario_codigo)
                        if vale.funcionario_codigo is not None
                        else "código indisponível"
                    )
                    itens_vales.append(f"func. {funcionario} {moeda_br(vale.valor)} ({origem})")
                linhas_unidade.append(" · ".join(itens_vales))
        blocos.append(linhas_unidade)

    limite_corpo = 4000 - len("\n".join(prefixo)) - 1
    mensagens: list[str] = []
    atual = prefixo.copy()
    for bloco in blocos:
        for linha in bloco:
            for parte in _quebrar_linha(linha, limite_corpo):
                candidata = "\n".join((*atual, parte))
                if len(candidata) > 4000:
                    mensagens.append("\n".join(atual))
                    atual = prefixo.copy()
                atual.append(parte)
    mensagens.append("\n".join(atual))
    return mensagens
