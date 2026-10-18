"""Planilha do dia: um .xlsx por posto/dia, montado a partir do banco local."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from apps.match import caminhos
from src.modules.cash_reconciliation.domain.tempo import FUSO

FORMATO_REAIS = "R$ #,##0.00"
_ROTULO_FONTE = {"premmia": "Premmia", "pagbank_edi": "PagBank"}
_MSG_SITUACAO = {"ok": "Coleta concluída", "sem_movimento": "Sem vendas registradas no dia"}


def _valor(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(Decimal(str(v)))
    except InvalidOperation:
        return None


def _local(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    return dt.astimezone(FUSO) if dt.tzinfo else dt.replace(tzinfo=FUSO)


def _cabecalho(ws, titulos: list[str]) -> None:
    ws.append(titulos)
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"


def _ajustar(ws) -> None:
    for i, col in enumerate(ws.columns, 1):
        largura = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(i)].width = min(max(largura + 2, 10), 60)


def _moeda(ws, coluna: int) -> None:
    for row in ws.iter_rows(min_row=2, min_col=coluna, max_col=coluna):
        for c in row:
            if c.value is not None:
                c.number_format = FORMATO_REAIS


def _resumo(con, wb, posto_id: int, dia: date) -> None:
    ws = wb.active
    ws.title = "Resumo"
    _cabecalho(ws, ["Fonte", "Situação", "Quantidade", "Total", "Mensagem"])
    rows = con.execute(
        "SELECT f.tipo, c.situacao, c.qtd, c.total, c.erro_texto FROM coleta c"
        " JOIN fonte f ON f.id=c.fonte_id WHERE f.posto_id=? AND c.dia=? ORDER BY f.id",
        (posto_id, str(dia))).fetchall()
    for r in rows:
        msg = r["erro_texto"] or _MSG_SITUACAO.get(r["situacao"], "")
        ws.append([_ROTULO_FONTE.get(r["tipo"], r["tipo"]), r["situacao"], r["qtd"],
                   _valor(r["total"]), msg])
    _moeda(ws, 4)
    _ajustar(ws)


def _transacoes(con, wb, nome: str, fonte: str, posto_id: int, dia: date) -> None:
    ws = wb.create_sheet(nome)
    _cabecalho(ws, ["Data/hora", "NSU", "Autorização", "Valor", "Bandeira/forma", "Situação"])
    rows = con.execute(
        "SELECT * FROM transacao WHERE posto_id=? AND fonte=? ORDER BY momento, id",
        (posto_id, fonte)).fetchall()
    for r in rows:
        local = _local(r["momento"])
        if local.date() != dia:
            continue
        ws.append([local.strftime("%d/%m/%Y %H:%M"), r["nsu"], r["autorizacao"],
                   _valor(r["valor"]), r["bandeira"] or r["forma"], r["situacao"]])
    _moeda(ws, 4)
    _ajustar(ws)


def _divergencias(con, wb, posto_id: int, dia: date) -> None:
    ws = wb.create_sheet("Divergências")
    _cabecalho(ws, ["Tipo", "Valor esperado", "Valor encontrado", "NSU", "Caixa",
                    "Responsável", "O que houve", "O que fazer"])
    for r in con.execute("SELECT * FROM divergencia WHERE posto_id=? AND dia=? ORDER BY id",
                         (posto_id, str(dia))).fetchall():
        ws.append([r["tipo"], _valor(r["valor_esperado"]), _valor(r["valor_encontrado"]),
                   r["nsu"], r["caixa_codigo"], r["responsavel"], r["explicacao_pt"],
                   r["correcao_pt"]])
    _moeda(ws, 2)
    _moeda(ws, 3)
    _ajustar(ws)


def gerar(con, posto_id: int, dia: date, destino: Path | None = None) -> Path:
    posto = con.execute("SELECT apelido FROM posto WHERE id=?", (posto_id,)).fetchone()
    apelido = (posto["apelido"] if posto and posto["apelido"] else f"P{posto_id}")
    destino = destino or caminhos.planilhas() / f"Logos_{apelido}_{dia.strftime('%d-%m-%Y')}.xlsx"
    wb = Workbook()
    _resumo(con, wb, posto_id, dia)
    _transacoes(con, wb, "Premmia", "premmia", posto_id, dia)
    _transacoes(con, wb, "PagBank", "pagbank_edi", posto_id, dia)
    _divergencias(con, wb, posto_id, dia)
    wb.save(destino)
    return destino
