"""Compoe o relatorio detalhado a partir de resultados locais ja persistidos."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from ..domain.execucao import ResultadoDiario
from ..domain.models import Unidade
from ..domain.tempo import formatar_data, formatar_data_hora
from .resumo_diario import _descricao_despesa_segura, moeda_br


GRUPOS_ACAO = {1: "Lançar", 2: "Alterar", 3: "Apurar", 4: "Conferir à mão"}


def _mapa_nomes(registro: ResultadoDiario, nomes: dict[int, str] | None) -> dict[int, str]:
    resultado = dict(nomes or {})

    def visitar(valor) -> None:
        if hasattr(valor, "model_dump"):
            visitar(valor.model_dump(mode="python"))
        elif isinstance(valor, dict):
            codigo = valor.get("frentista") or valor.get("funcionario_codigo")
            nome = valor.get("nome_frentista") or valor.get("nome")
            if codigo is not None and nome:
                resultado.setdefault(codigo, nome)
            for item in valor.values():
                visitar(item)
        elif isinstance(valor, (tuple, list)):
            for item in valor:
                visitar(item)

    visitar(registro)
    return resultado


def _funcionario(codigo: int | None, nomes: dict[int, str]) -> str:
    if codigo is None:
        return "frentista não identificado"
    return f"{nomes.get(codigo, 'nome indisponível')} ({codigo})"


def _setor(unidade: Unidade, centro_custo: int | None) -> str:
    if unidade.empresa_codigo == 11495:
        return {
            7295: "PISTA",
            21650: "CONVENIÊNCIA",
            22310: "CONVENIÊNCIA",
            24423: "FOOD",
            18713: "ajuste de NF",
        }.get(centro_custo, "setor não identificado")
    if unidade.empresa_codigo == 118508 and centro_custo == 24423:
        return "FOOD"
    return "setor único" if centro_custo is None else f"centro {centro_custo}"


def _data_hora(valor) -> str:
    return formatar_data_hora(valor) if valor else "não informado"


def _nsu_final(nsu: str | None) -> str:
    return f"…{nsu[-4:]}" if nsu else "—"


def _pendencia_info(item) -> tuple[object, bool]:
    if isinstance(item, tuple) and len(item) == 2:
        return item[0], bool(item[1])
    if isinstance(item, dict):
        return item, bool(item.get("vencida"))
    return item, False


def gerar_relatorio_caixa_dia(
    registro: ResultadoDiario,
    unidade: Unidade,
    *,
    situacao_robo: str = "não informada",
    nomes_funcionarios: dict[int, str] | None = None,
    pendencias: Iterable = (),
    conferencia=None,
) -> str:
    """Gera Markdown sem consultar ERP, portal ou serviço externo."""
    nomes = _mapa_nomes(registro, nomes_funcionarios)
    fechamento = registro.fechamento
    caixas = fechamento.caixas if fechamento else ()
    nome_unidade = unidade.apelido or unidade.nome
    pendencias = tuple(_pendencia_info(item) for item in pendencias)
    abertas = [(item, vencida) for item, vencida in pendencias if getattr(item, "status", item.get("status") if isinstance(item, dict) else None) == "aberta"]
    vencidas = [(item, vencida) for item, vencida in abertas if vencida]
    alertas = [alerta for caixa in caixas for alerta in caixa.alertas]
    adquirentes = registro.recebimentos.adquirentes
    adquirentes_com_falha = [item for item in adquirentes if item.situacao != "ok"]

    linhas = [
        f"# Relatório do caixa — {nome_unidade}",
        "",
        f"- Unidade: {nome_unidade} ({unidade.empresa_codigo})",
        f"- Dia: {formatar_data(registro.dia)}",
        f"- Situação do robô: {situacao_robo}",
        f"- Caixas: {len(caixas)}",
        "",
        "## Resumo",
        "",
        f"- Quebra total: {moeda_br(fechamento.quebra_total if fechamento else Decimal(0))}.",
        f"- Caixas não consolidados: {sum(not caixa.caixa.consolidado for caixa in caixas)}.",
        f"- Alertas de fechamento: {len(alertas)}.",
        f"- Pendências abertas: {len(abertas)}, sendo {len(vencidas)} vencidas.",
        f"- Adquirentes indisponíveis: {', '.join(item.adquirente for item in adquirentes_com_falha) or 'nenhuma'}.",
        "- Abastecimentos completos e litros não constam nos resultados diários persistidos.",
        "",
        "## Caixas",
        "",
        "| Código | Operador | Abertura | Fechamento | Consolidado | PDV | Setor |",
        "|---:|---|---|---|---|---:|---|",
    ]
    for auditoria in caixas:
        caixa = auditoria.caixa
        linhas.append(
            f"| {caixa.codigo} | {_funcionario(caixa.funcionario_codigo, nomes)} | "
            f"{_data_hora(caixa.abertura)} | {_data_hora(caixa.fechamento)} | "
            f"{'sim' if caixa.consolidado else 'não'} | {caixa.pdv_codigo} | "
            f"{_setor(unidade, caixa.centro_custo)} |"
        )

    linhas.extend([
        "",
        "## Formas de pagamento do caixa",
        "",
        "| Caixa | Forma | Apurado (sistema) | Apresentado (operador) | Diferença |",
        "|---:|---|---:|---:|---:|",
    ])
    for auditoria in caixas:
        for modalidade in auditoria.modalidades:
            linhas.append(
                f"| {auditoria.caixa.codigo} | {modalidade.rotulo} | {moeda_br(modalidade.apurado)} | "
                f"{moeda_br(modalidade.apresentado)} | {moeda_br(modalidade.diferenca)} |"
            )
    linhas.extend(["", f"Quebra total: **{moeda_br(fechamento.quebra_total if fechamento else Decimal(0))}**.", ""])
    linhas.extend(["| Caixa | Falta sem desconto | Situação |", "|---:|---:|---|"])
    for auditoria in caixas:
        desconto = auditoria.desconto_falta
        alertas_falta = [a for a in auditoria.alertas if a.codigo == "FALTA_SEM_DESCONTO"]
        if (desconto and desconto.situacao == "sem_desconto") or alertas_falta:
            valor = desconto.falta if desconto else abs(alertas_falta[0].valor or Decimal(0))
            situacao = "confirmada" if auditoria.caixa.consolidado else "provisória"
            linhas.append(f"| {auditoria.caixa.codigo} | {moeda_br(abs(valor))} | {situacao} |")
    if not any("FALTA_SEM_DESCONTO" == a.codigo for a in alertas) and not any(
        a.desconto_falta and a.desconto_falta.situacao == "sem_desconto" for a in caixas
    ):
        linhas.append("| — | R$ 0,00 | sem falta registrada |")

    linhas.extend(["", "## Sangrias", "", "| Caixa | Hora | Valor | Destino | Alterada |", "|---:|---|---:|---|---|"])
    for auditoria in caixas:
        for sangria in auditoria.sangrias:
            if sangria.conta_codigo is not None:
                destino = f"conta webPosto {sangria.conta_codigo}"
            elif unidade.empresa_codigo == 118508:
                destino = "repassada ao Casa Caiada (RN-SANGRIA-002)"
            elif unidade.empresa_codigo == 5555:
                destino = "assumida no cofre (RN-SANGRIA-003)"
            else:
                destino = "sem conta de destino"
            linhas.append(
                f"| {sangria.caixa_codigo} | {_data_hora(sangria.momento)} | {moeda_br(sangria.valor)} | "
                f"{destino} | {'sim' if sangria.alterada else 'não'} |"
            )
    if not any(a.sangrias for a in caixas):
        linhas.append("| — | — | R$ 0,00 | nenhuma sangria persistida | — |")

    linhas.extend(["", "## Despesas", "", "| Caixa | Hora | Valor | Descrição | Plano de contas | Centro de custo / setor | Alerta |", "|---:|---|---:|---|---|---|---|"])
    despesas_ajuste_nf = []
    for auditoria in caixas:
        for despesa in auditoria.despesas:
            plano = f"{despesa.plano_conta_codigo or '—'} — {despesa.plano_conta_nome or 'nome não persistido'}"
            if despesa.centro_custo == 18713:
                despesas_ajuste_nf.append(despesa)
                continue
            alerta = "SEM PLANO ⚠" if not despesa.plano_conta_codigo else "—"
            linhas.append(
                f"| {despesa.caixa_codigo} | não persistida | {moeda_br(despesa.valor)} | "
                f"{_descricao_despesa_segura(despesa.descricao or 'sem descrição')} | {plano} | "
                f"{_setor(unidade, despesa.centro_custo) if despesa.centro_custo is not None else 'centro de custo não persistido'} | {alerta} |"
            )
    if not any(d.centro_custo != 18713 for a in caixas for d in a.despesas):
        linhas.append("| — | — | R$ 0,00 | nenhuma despesa persistida | — | — | — |")
    linhas.append("\nDespesas sem centro de custo persistido não podem ser separadas por setor com segurança.")
    linhas.extend(["", "### Ajustes de NF (FECHAMENTO)", "", "| Caixa | Valor | Descrição | Plano de contas |", "|---:|---:|---|---|"])
    for despesa in despesas_ajuste_nf:
        plano = f"{despesa.plano_conta_codigo or '—'} — {despesa.plano_conta_nome or 'nome não persistido'}"
        linhas.append(
            f"| {despesa.caixa_codigo} | {moeda_br(despesa.valor)} | "
            f"{_descricao_despesa_segura(despesa.descricao or 'sem descrição')} | {plano} |"
        )
    if not despesas_ajuste_nf:
        linhas.append("| — | R$ 0,00 | nenhum ajuste FECHAMENTO identificado nos dados persistidos | — |")

    linhas.extend(["", "## Vales de funcionários", "", "| Caixa | Funcionário | Valor | Origem |", "|---:|---|---:|---|"])
    for auditoria in caixas:
        for vale in (*auditoria.vales_falta, *auditoria.vales):
            origem = "falta de caixa" if vale.origem.upper() == "D" else "vale comum"
            linhas.append(f"| {vale.caixa_codigo} | {_funcionario(vale.funcionario_codigo, nomes)} | {moeda_br(vale.valor)} | {origem} |")
    if not any(a.vales_falta or a.vales for a in caixas):
        linhas.append("| — | nenhum vale persistido | R$ 0,00 | — |")

    linhas.extend(["", "## Frentistas do dia", "", "| Frentista | Abastecimentos | Litros | Valor | Ocorrências ligadas |", "|---|---:|---:|---:|---|"])
    codigos = set(nomes)
    codigos.update(caixa.caixa.funcionario_codigo for caixa in caixas)
    if codigos:
        for codigo in sorted(codigos):
            linhas.append(f"| {_funcionario(codigo, nomes)} | não persistido | não persistido | não persistido | consultar caixas/recebimentos abaixo |")
    else:
        linhas.append("| Não identificados nos resultados gravados | não persistido | não persistido | não persistido | — |")
    linhas.append("\nA lista integral de V1/ABASTECIMENTOS, inclusive litros, não está gravada; nenhum total foi estimado.")

    recebimentos = [item for item in adquirentes if item.adquirente.upper() in {"PAGBANK", "PREMMIA"}]
    outros = [item for item in adquirentes if item.adquirente.upper() not in {"PAGBANK", "PREMMIA"}]
    conferidos_qtd = sum(item.casados.quantidade for item in recebimentos if item.casados)
    conferidos_total = sum((item.casados.total for item in recebimentos if item.casados), Decimal(0))
    linhas.extend([
        "", "## Recebimentos", "",
        f"Conferidos: **{conferidos_qtd} · {moeda_br(conferidos_total)}**.",
        "", "| Adquirente | Situação | Casados (N · R$) |", "|---|---|---:|",
    ])
    for item in (*recebimentos, *outros):
        situacao = item.situacao if item.adquirente.upper() in {"PAGBANK", "PREMMIA"} else "pendente"
        casados = f"{item.casados.quantidade} · {moeda_br(item.casados.total)}" if item.casados else "—"
        linhas.append(f"| {item.adquirente} | {situacao} | {casados} |")
    for grupo, rotulo in GRUPOS_ACAO.items():
        itens = [item for item in (conferencia.itens if conferencia else ()) if item.grupo == grupo]
        total = sum((item.valor for item in itens), Decimal(0))
        linhas.extend(["", f"### {rotulo}: {len(itens)} · {moeda_br(total)}"])
        if itens:
            linhas.extend(["", "| Hora | Valor | De → Para | Frentista provável | Caixa | NSU final |", "|---|---:|---|---|---:|---|"])
            for item in itens:
                responsavel = item.responsavel
                linhas.append(
                    f"| {_data_hora(item.momento)} | {moeda_br(item.valor)} | {item.de or '—'} → {item.para or '—'} | "
                    f"{responsavel} | {item.caixa or '—'} | {_nsu_final(item.nsu)} |"
                )
        else:
            linhas.append("\nNenhum item persistido neste grupo.")
    if not conferencia:
        linhas.append("\nClassificação de ações da Sprint 14 não persistida para este dia.")

    linhas.extend(["", "## Pendências do dia", "", "| Status | Tipo | Quantidade · R$ |", "|---|---|---:|"])
    agrupadas: dict[tuple[str, str], list] = {}
    for item, vencida in abertas:
        tipo = item.get("tipo", "não informado") if isinstance(item, dict) else item.tipo
        valor = item.get("valor") if isinstance(item, dict) else item.valor
        chave = ("vencida" if vencida else "aberta", tipo)
        agrupadas.setdefault(chave, []).append(Decimal(str(valor or 0)))
    for (status, tipo), valores in sorted(agrupadas.items()):
        linhas.append(f"| {status} | {tipo} | {len(valores)} · {moeda_br(sum(valores, Decimal(0)))} |")
    if not agrupadas:
        linhas.append("| — | nenhuma pendência aberta persistida para o dia | 0 · R$ 0,00 |")
    return "\n".join(linhas).rstrip() + "\n"


def planilha_relatorio_caixa_dia(markdown: str) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    workbook.remove(workbook.active)
    blocos: list[tuple[str, list[str]]] = [("Resumo", [])]
    for linha in markdown.splitlines():
        if linha.startswith("## "):
            titulo = linha[3:].strip()[:31] or "Bloco"
            blocos.append((titulo, []))
        else:
            blocos[-1][1].append(linha)

    for titulo, linhas_bloco in blocos:
        sheet = workbook.create_sheet(titulo)
        tabela = False
        for linha in linhas_bloco:
            if linha.startswith("|"):
                celulas = [celula.strip() for celula in linha.strip().strip("|").split("|")]
                if all(set(celula) <= {"-", ":"} for celula in celulas):
                    continue
                sheet.append(celulas)
                if not tabela:
                    for cell in sheet[sheet.max_row]:
                        cell.font = Font(bold=True)
                    tabela = True
            elif linha.strip():
                sheet.append([linha.strip()])
        sheet.freeze_panes = "A2" if tabela else "A1"
        for coluna in sheet.columns:
            largura = min(60, max(12, max(len(str(c.value or "")) for c in coluna) + 2))
            sheet.column_dimensions[coluna[0].column_letter].width = largura

    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()