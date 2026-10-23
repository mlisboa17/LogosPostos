"""Porta de entrada: detecta o tipo do XML e devolve o documento."""
from __future__ import annotations

from ._xml import nome_local, raiz
from .modelos import DocumentoFiscal, XmlInvalido
from .parser_nfe import NS as NS_NFE, ler_nfe
from .parser_nfse import NS as NS_NFSE, ler_nfse

MSG_FORMATO = "Formato não reconhecido. Hoje o Logos Match lê NF-e e NFS-e do padrão nacional."


def ler(xml: bytes) -> DocumentoFiscal:
    r = raiz(xml)
    nome, ns = nome_local(r), r.tag[1:].split("}", 1)[0] if r.tag.startswith("{") else ""
    if ns == NS_NFE and nome in ("nfeProc", "NFe"):
        return ler_nfe(xml)
    if ns == NS_NFSE and nome == "NFSe":
        return ler_nfse(xml)
    raise XmlInvalido(MSG_FORMATO)
