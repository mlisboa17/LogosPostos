"""PDFs a partir do XML: DANFE (NF-e), DANFSe (NFS-e) e união de vários PDFs.

DANFE e DANFSe vêm do `brazilfiscalreport`. Se o DANFSe da biblioteca não aceitar o XML,
gera um DANFSe simples próprio (o governo deixou de gerar o PDF pela API em 01/07/2026).
"""
from __future__ import annotations

import io
import logging
from decimal import Decimal

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter

from .modelos import FUSO, DocumentoFiscal

logger = logging.getLogger(__name__)


def _brl(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _latin(s: str | None) -> str:
    return (s or "").encode("latin-1", "replace").decode("latin-1")


def _cnpj(c: str | None) -> str:
    c = c or ""
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


def danfse_simples(doc: DocumentoFiscal) -> bytes:
    p = FPDF(unit="mm", format="A4")
    p.add_page()
    p.set_font("helvetica", "B", 14)
    p.cell(0, 10, "DANFSe - Documento auxiliar da NFS-e", new_x="LMARGIN", new_y="NEXT")
    p.set_font("helvetica", size=10)
    emissao = doc.emissao_em.astimezone(FUSO).strftime("%d/%m/%Y %H:%M")
    linhas = [
        ("Número", doc.numero), ("Emissão", emissao), ("Competência", doc.competencia),
        ("Prestador", f"{doc.emitente_nome} - CNPJ {_cnpj(doc.emitente_cnpj)}"),
        ("Tomador", f"CNPJ {_cnpj(doc.destinatario_cnpj)}"),
        ("Serviço", doc.descricao_servico or ""),
        ("Valor do serviço", f"R$ {_brl(doc.valor_total)}"),
        ("ISS", f"R$ {_brl(doc.impostos.iss)}"),
        ("Retenções", f"R$ {_brl(doc.impostos.retencoes)}"),
        ("Chave", doc.chave),
    ]
    for rotulo, valor in linhas:
        p.set_font("helvetica", "B", 10)
        p.cell(40, 7, _latin(rotulo))
        p.set_font("helvetica", size=10)
        p.multi_cell(0, 7, _latin(valor), new_x="LMARGIN", new_y="NEXT")
    return bytes(p.output())


def gerar_pdf(xml: bytes, doc: DocumentoFiscal) -> bytes:
    if doc.tipo == "nfe":
        from brazilfiscalreport.danfe import Danfe
        return bytes(Danfe(xml=xml).output())
    if doc.tipo == "nfse":
        try:
            from brazilfiscalreport.danfse import Danfse
            return bytes(Danfse(xml=xml).output())
        except Exception:  # leiaute fora do que a biblioteca entende
            logger.info("DANFSe da biblioteca recusou o XML; usando o simples")
            return danfse_simples(doc)
    raise ValueError(f"PDF não disponível para {doc.tipo}")


def unir(pdfs: list[bytes]) -> bytes:
    w = PdfWriter()
    for b in pdfs:
        for pagina in PdfReader(io.BytesIO(b)).pages:
            w.add_page(pagina)
    saida = io.BytesIO()
    w.write(saida)
    return saida.getvalue()
