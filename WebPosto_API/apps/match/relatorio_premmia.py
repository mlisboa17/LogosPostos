"""Relatório consolidado Premmia/PagBank x webPosto de um posto num período (tela e planilha)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font

from apps.match import banco, sugestoes
from apps.match.explicar import dinheiro

MAX_DIAS = 90
FONTES = {"premmia": "Premmia", "pagbank_edi": "PagBank"}  # tipo da fonte -> nome na tela


@dataclass
class Dia:
    dia: date
    situacao: str
    premmia: Decimal
    webposto: Decimal | None
    ocorrencias: int

    @property
    def diferenca(self) -> Decimal | None:
        return None if self.webposto is None else self.premmia - self.webposto


@dataclass
class Relatorio:
    posto: object
    inicio: date
    fim: date
    dias: list[Dia]
    ocorrencias: list[tuple[date, sugestoes.Ocorrencia]]
    consolidado: sugestoes.Consolidado
    dias_sem_comparacao: int
    dias_sem_coleta: list[date] = field(default_factory=list)
    fonte: str = "premmia"

    @property
    def nome_fonte(self) -> str:
        return FONTES.get(self.fonte, self.fonte)


def _ocorrencia(r) -> sugestoes.Ocorrencia:
    acao = r["acao"] or "analisar"  # divergências antigas (antes da v13) não tinham ação
    return sugestoes.Ocorrencia(
        acao=acao, tipo=r["tipo"], funcionario=r["responsavel"] or "funcionário não identificado",
        valor=abs(Decimal(r["valor_esperado"] or 0) - Decimal(r["valor_encontrado"] or 0))
        if r["tipo"] == "valor_diferente" else Decimal(r["valor_esperado"] or 0) or Decimal(r["valor_encontrado"] or 0),
        referencia=r["referencia"] or (f"NSU {r['nsu']}" if r["nsu"] else "—"),
        explicacao=r["explicacao_pt"] or "", correcao=r["correcao_pt"] or "",
        criterios=json.loads(r["criterios_json"]) if r["criterios_json"] else [],
        abastecimento=r["abastecimento"], nao_resolvida=acao == "analisar", nsu=r["nsu"],
        caixa_codigo=r["caixa_codigo"], valor_premmia=Decimal(r["valor_esperado"] or 0),
        valor_webposto=Decimal(r["valor_encontrado"] or 0))


def montar(con, posto_id: int, inicio: date, fim: date, fonte: str = "premmia") -> Relatorio | None:
    posto = banco.obter_posto(con, posto_id)
    tipo = fonte
    fonte = next((f for f in banco.fontes_do_posto(con, posto_id) if f["tipo"] == tipo), None)
    if posto is None or fonte is None:
        return None
    linhas = con.execute("SELECT dia, situacao, total, total_webposto FROM coleta WHERE fonte_id=? AND dia BETWEEN ? AND ?"
                         " ORDER BY dia", (fonte["id"], str(inicio), str(fim))).fetchall()
    divs = con.execute("SELECT * FROM divergencia WHERE posto_id=? AND fonte=? AND dia BETWEEN ? AND ?"
                       " ORDER BY dia, id", (posto_id, tipo, str(inicio), str(fim))).fetchall()
    por_dia: dict[str, int] = {}
    for d in divs:
        por_dia[d["dia"]] = por_dia.get(d["dia"], 0) + 1
    dias = [Dia(date.fromisoformat(r["dia"]), r["situacao"], Decimal(r["total"] or 0),
                Decimal(r["total_webposto"]) if r["total_webposto"] is not None else None, por_dia.get(r["dia"], 0))
            for r in linhas]
    comparados = [d for d in dias if d.webposto is not None and d.situacao in ("ok", "sem_movimento")]
    ocorrencias = [(date.fromisoformat(r["dia"]), _ocorrencia(r)) for r in divs]
    consolidado = sugestoes.consolidar([o for _, o in ocorrencias],
                                       sum((d.premmia for d in comparados), Decimal(0)),
                                       sum((d.webposto for d in comparados), Decimal(0)))
    coletados = {d.dia for d in dias if d.situacao in ("ok", "sem_movimento")}
    faltam = [date.fromordinal(n) for n in range(inicio.toordinal(), fim.toordinal() + 1)
              if date.fromordinal(n) not in coletados]
    return Relatorio(posto, inicio, fim, dias, ocorrencias, consolidado,
                     sum(1 for d in dias if d.webposto is None and d.situacao in ("ok", "sem_movimento")), faltam, tipo)


def planilha(rel: Relatorio) -> bytes:
    wb = Workbook()
    negrito = Font(bold=True)
    ws = wb.active
    ws.title = "Resumo"
    c = rel.consolidado
    nome = rel.posto["apelido"] or rel.posto["nome"]
    for linha in (("Posto", nome), ("Período", f"{rel.inicio:%d/%m/%Y} a {rel.fim:%d/%m/%Y}"),
                  (f"Total no {rel.nome_fonte}", float(c.total_premmia)), ("Total no webPosto", float(c.total_webposto)),
                  (f"Diferença ({rel.nome_fonte} − webPosto)", float(c.diferenca)),
                  ("Pendentes de lançar no webPosto", float(c.pendentes)),
                  ("Lançados a mais no webPosto", float(c.excedentes)),
                  ("Divergências não resolvidas", c.nao_resolvidas),
                  ("Dias sem coleta", len(rel.dias_sem_coleta)),
                  ("Aviso", "Sugestões para conferência: o Logos Match não altera o webPosto.")):
        ws.append(linha)
        ws.cell(ws.max_row, 1).font = negrito

    ws = wb.create_sheet("Por funcionário")
    ws.append(("Funcionário", f"A lançar ({rel.nome_fonte} sem webPosto)", "Lançado a mais", "Ocorrências"))
    for f in c.por_funcionario:
        ws.append((f.funcionario, float(f.a_lancar), float(f.lancado_a_mais), f.ocorrencias))

    ws = wb.create_sheet("Por dia")
    ws.append(("Dia", rel.nome_fonte, "webPosto", "Diferença", "Ocorrências", "Situação da coleta"))
    for d in rel.dias:
        ws.append((d.dia.strftime("%d/%m/%Y"), float(d.premmia), None if d.webposto is None else float(d.webposto),
                   None if d.diferenca is None else float(d.diferenca), d.ocorrencias, d.situacao))

    ws = wb.create_sheet("Ocorrências")
    ws.append(("Dia", "Ação sugerida", "Funcionário", "Valor", "Referência", "Abastecimento", "O que houve",
               "O que fazer", "Critérios usados"))
    for dia, o in rel.ocorrencias:
        ws.append((dia.strftime("%d/%m/%Y"), sugestoes.ACOES.get(o.acao, o.acao), o.funcionario, float(o.valor),
                   o.referencia, o.abastecimento or "", o.explicacao, o.correcao, "; ".join(o.criterios)))
    for folha in wb.worksheets:
        for cel in folha[1]:
            cel.font = negrito
        for col in folha.columns:
            folha.column_dimensions[col[0].column_letter].width = min(60, max(12, *(len(str(x.value or "")) for x in col)))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def texto_resumo(rel: Relatorio) -> str:
    c = rel.consolidado
    return (f"{rel.posto['apelido'] or rel.posto['nome']} · {rel.inicio:%d/%m} a {rel.fim:%d/%m}: {rel.nome_fonte} "
            f"{dinheiro(c.total_premmia)}, webPosto {dinheiro(c.total_webposto)}, diferença {dinheiro(c.diferenca)}.")
