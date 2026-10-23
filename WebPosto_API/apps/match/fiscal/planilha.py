"""Planilha resumo do mês por empresa (spec §7)."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from apps.match.fiscal import repositorio as repo
from src.modules.fiscal_docs.modelos import FUSO

CAB_NOTAS = ["Data emissão", "Tipo", "Número", "Série", "Chave", "Emitente CNPJ", "Emitente", "Valor total",
             "ICMS", "ICMS-ST", "IPI", "ISS", "Retenções", "Situação", "Origem"]
CAB_COMBUSTIVEL = ["Data emissão", "Nota", "Distribuidora", "Produto", "Código ANP", "Litros", "Preço/litro",
                   "Valor", "ICMS monofásico", "Frete CIF/FOB", "Transportadora CNPJ", "Transportadora",
                   "Placa", "UF placa", "CT-e número", "Valor frete"]
CAB_FRETES = ["CT-e número", "Data CT-e", "Nota", "Distribuidora", "Valor frete", "Tipo frete", "Observação"]
CAB_PENDENCIAS = ["Tipo", "Documento", "Emitente", "Data", "O que fazer"]
OBS_CTE = "XML do CT-e chega na próxima versão"
_TIPO = {"nfe": "NF-e", "nfse": "NFS-e", "cte": "CT-e"}
_SITUACAO = {"autorizada": "Autorizada", "cancelada": "Cancelada", "so_resumo": "Só resumo"}
_MOEDA, _LITROS = "#,##0.00", "#,##0.000"


def _dec(v) -> Decimal | None:
    return None if v in (None, "") else Decimal(str(v))


def _data(iso: str | None) -> str:
    if not iso:
        return ""
    if len(iso) == 10:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    dt = datetime.fromisoformat(iso)
    return (dt.astimezone(FUSO) if dt.tzinfo else dt).strftime("%d/%m/%Y")


def _aba(wb, titulo: str, cabecalho: list[str], primeira: bool = False):
    ws = wb.active if primeira else wb.create_sheet()
    ws.title = titulo
    ws.append(cabecalho)
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    return ws


def _formatar(ws, colunas: dict[int, str]) -> None:
    for linha in ws.iter_rows(min_row=2):
        for idx, fmt in colunas.items():
            linha[idx - 1].number_format = fmt


def gerar_planilha(con, empresa_id: int, competencia: str, destino: Path) -> Path:
    docs = repo.documentos_da_competencia(con, empresa_id, competencia)
    wb = Workbook()

    ws = _aba(wb, "Notas", CAB_NOTAS, primeira=True)
    for d in docs:
        imp = json.loads(d["impostos_json"] or "{}")
        ws.append([_data(d["emissao_em"]), _TIPO[d["tipo"]], d["numero"], d["serie"], d["chave"],
                   d["emitente_cnpj"], d["emitente_nome"], _dec(d["valor_total"]), _dec(imp.get("icms")),
                   _dec(imp.get("icms_st")), _dec(imp.get("ipi")), _dec(imp.get("iss")),
                   _dec(imp.get("retencoes")), _SITUACAO[d["situacao"]], d["origem"]])
    _formatar(ws, {i: _MOEDA for i in range(8, 14)})

    wc = _aba(wb, "Combustível", CAB_COMBUSTIVEL)
    wf = _aba(wb, "Fretes (CT-e)", CAB_FRETES)
    litros: dict[tuple[str, str], list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    fornecedores: dict[tuple[str, str], list] = defaultdict(lambda: [0, Decimal(0)])
    por_tipo: dict[str, list] = defaultdict(lambda: [0, Decimal(0)])
    frete_total, canceladas, pendencias = Decimal(0), 0, []
    for d in docs:
        valor = _dec(d["valor_total"]) or Decimal(0)
        fornecedores[(d["emitente_cnpj"] or "", d["emitente_nome"] or "")][0] += 1
        fornecedores[(d["emitente_cnpj"] or "", d["emitente_nome"] or "")][1] += valor
        por_tipo[_TIPO[d["tipo"]]][0] += 1
        por_tipo[_TIPO[d["tipo"]]][1] += valor
        canceladas += d["situacao"] == "cancelada"
        if d["situacao"] == "so_resumo":
            pendencias.append(["Só resumo", d["chave"], d["emitente_nome"], _data(d["emissao_em"]),
                               "O webPosto ainda não tem o XML; o Logos Match tenta de novo sozinho."])
        frete = json.loads(d["frete_json"]) if d["frete_json"] else {}
        vfrete = _dec(frete.get("valor_frete"))
        if d["cte_numero"]:
            frete_total += vfrete or Decimal(0)
            wf.append([d["cte_numero"], _data(frete.get("cte_emissao")), d["numero"], d["emitente_nome"],
                       vfrete, frete.get("tipo_frete"), OBS_CTE])
            pendencias.append(["CT-e sem XML", d["cte_numero"], d["emitente_nome"], _data(frete.get("cte_emissao")),
                               OBS_CTE + "."])
        if not d["combustivel"]:
            continue
        t = repo.transporte_do_documento(con, d["id"])
        for i in repo.itens_do_documento(con, d["id"]):
            if not i["cprod_anp"]:
                continue
            q, v = _dec(i["quantidade"]) or Decimal(0), _dec(i["valor_total"]) or Decimal(0)
            litros[(i["descricao"], i["cprod_anp"])][0] += q
            litros[(i["descricao"], i["cprod_anp"])][1] += v
            wc.append([_data(d["emissao_em"]), d["numero"], d["emitente_nome"], i["descricao"], i["cprod_anp"],
                       q, _dec(i["valor_unitario"]), v, _dec(i["icms_mono"]),
                       t["mod_frete_texto"] if t else None, t["transportadora_cnpj"] if t else None,
                       t["transportadora_nome"] if t else None, t["placa"] if t else None,
                       t["uf_placa"] if t else None, d["cte_numero"], vfrete])
    _formatar(wc, {6: _LITROS, 7: "#,##0.0000", 8: _MOEDA, 9: _MOEDA, 16: _MOEDA})
    _formatar(wf, {5: _MOEDA})

    wt = _aba(wb, "Totais", ["Por fornecedor", "", "Notas", "Valor"])
    for (cnpj, nome), (n, v) in sorted(fornecedores.items(), key=lambda x: -x[1][1]):
        wt.append([nome, cnpj, n, v])
    wt.append([])
    wt.append(["Por tipo", "", "Notas", "Valor"])
    for tipo, (n, v) in sorted(por_tipo.items()):
        wt.append([tipo, "", n, v])
    wt.append([])
    wt.append(["Combustível por produto", "Código ANP", "Litros", "Valor"])
    for (produto, anp), (q, v) in sorted(litros.items()):
        wt.append([produto, anp, q, v])
    wt.append([])
    wt.append(["Frete total (CT-e)", "", "", frete_total])
    wt.append(["Notas canceladas", "", canceladas, None])

    wp = _aba(wb, "Pendências", CAB_PENDENCIAS)
    for p in pendencias:
        wp.append(p)

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino
