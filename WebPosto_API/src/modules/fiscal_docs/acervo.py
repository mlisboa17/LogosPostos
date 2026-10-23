"""Acervo de XMLs por empresa: `<base>/<cnpj>/<AAAA-MM>/<tipo>/<chave>.xml` + `indice.jsonl`.

Escrita atômica; arquivo idêntico não é regravado nem reindexado.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .modelos import DocumentoFiscal

INDICE = "indice.jsonl"


def caminho_xml(base: Path, cnpj_empresa: str, doc: DocumentoFiscal) -> Path:
    return Path(base) / cnpj_empresa / doc.competencia / doc.tipo / f"{doc.chave}.xml"


def _sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def gravar(base: Path, cnpj_empresa: str, doc: DocumentoFiscal, xml: bytes, origem: str) -> Path:
    destino = caminho_xml(base, cnpj_empresa, doc)
    sha = _sha(xml)
    if destino.exists() and _sha(destino.read_bytes()) == sha:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(xml)
    os.replace(tmp, destino)
    linha = {
        "chave": doc.chave, "tipo": doc.tipo, "emissao_em": doc.emissao_em.isoformat(),
        "emitente_cnpj": doc.emitente_cnpj, "emitente_nome": doc.emitente_nome,
        "valor_total": str(doc.valor_total), "situacao": doc.situacao, "origem": origem, "sha256": sha,
    }
    with open(Path(base) / cnpj_empresa / INDICE, "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return destino


def ler_indice(base: Path, cnpj_empresa: str) -> list[dict]:
    arq = Path(base) / cnpj_empresa / INDICE
    if not arq.exists():
        return []
    return [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]
