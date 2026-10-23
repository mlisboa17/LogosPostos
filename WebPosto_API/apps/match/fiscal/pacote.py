"""Pacote do mês por empresa: zip com XMLs, PDFs e planilha resumo, dividido em partes de até 20 MB."""
from __future__ import annotations

import zlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from apps.match.fiscal import planilha, repositorio as repo
from src.modules.fiscal_docs import pdf
from src.modules.fiscal_docs.parser import ler

LIMITE_BYTES = 20 * 1024 * 1024
_FOLGA = 512  # cabeçalhos do zip por arquivo
ModoPdf = Literal["separados", "unificado", "ambos"]


def _documentos(con, empresa_id: int, competencia: str, desde: datetime | None) -> list:
    docs = [d for d in repo.documentos_da_competencia(con, empresa_id, competencia)
            if d["situacao"] != "so_resumo" and d["xml_path"]]
    if desde is not None:
        docs = [d for d in docs if datetime.fromisoformat(d["capturado_em"]) > desde]
    return docs


def _nome_base(con, empresa, competencia: str, complementar: bool) -> str:
    base = f"{empresa['cnpj']}_{competencia}"
    if not complementar:
        return base
    n = con.execute("SELECT COUNT(*) FROM pacote WHERE empresa_id=? AND competencia=? AND complementar=1",
                    (empresa["id"], competencia)).fetchone()[0]
    return f"{base}_complementar_{n + 1}"


def _entradas(con, empresa, competencia: str, docs: list, modo: ModoPdf, trabalho: Path) -> list[tuple[str, bytes]]:
    aaaa, mm = competencia.split("-")
    resumo = planilha.gerar_planilha(con, empresa["id"], competencia, trabalho / "resumo.xlsx")
    entradas = [(f"Resumo_{empresa['apelido'] or empresa['cnpj']}_{mm}-{aaaa}.xlsx", resumo.read_bytes())]
    pdfs: list[bytes] = []
    for d in docs:
        xml = Path(d["xml_path"]).read_bytes()
        entradas.append((f"xml/{d['chave']}.xml", xml))
        conteudo = pdf.gerar_pdf(xml, ler(xml))
        pdfs.append(conteudo)
        if modo in ("separados", "ambos"):
            entradas.append((f"pdf/{d['chave']}.pdf", conteudo))
    if modo in ("unificado", "ambos") and pdfs:
        entradas.append((f"pdf/{empresa['cnpj']}_{competencia}_notas.pdf", pdf.unir(pdfs)))
    return entradas


def _dividir(entradas: list[tuple[str, bytes]]) -> list[list[tuple[str, bytes]]]:
    partes: list[list[tuple[str, bytes]]] = [[]]
    tamanho = 0
    for nome, dados in entradas:
        estimado = len(zlib.compress(dados, 6)) + len(nome) * 2 + _FOLGA
        if partes[-1] and tamanho + estimado > LIMITE_BYTES:
            partes.append([])
            tamanho = 0
        partes[-1].append((nome, dados))
        tamanho += estimado
    return partes


def montar(con, empresa_id: int, competencia: str, pdf_modo: ModoPdf, destino: Path, *,
           complementar: bool = False, desde: datetime | None = None) -> list[Path]:
    """Gera o(s) zip(s) do pacote. Lista vazia quando não há documento com XML na competência."""
    docs = _documentos(con, empresa_id, competencia, desde)
    if not docs:
        return []
    empresa = repo.obter_empresa(con, empresa_id)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    partes = _dividir(_entradas(con, empresa, competencia, docs, pdf_modo, destino))
    base = _nome_base(con, empresa, competencia, complementar)
    saida = []
    for i, parte in enumerate(partes, 1):
        nome = f"{base}.zip" if len(partes) == 1 else f"{base}_parte{i}.zip"
        caminho = destino / nome
        with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
            for arq, dados in parte:
                z.writestr(arq, dados)
        saida.append(caminho)
    (destino / "resumo.xlsx").unlink(missing_ok=True)
    return saida
