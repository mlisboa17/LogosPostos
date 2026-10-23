"""Ajudantes de leitura de XML (ElementTree, sem dependências)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .modelos import XmlInvalido


def raiz(xml: bytes) -> ET.Element:
    # Documento fiscal nunca tem DOCTYPE: recusar fecha XXE e "billion laughs" sem depender de defusedxml.
    if b"<!DOCTYPE" in xml[:4096].upper() or b"<!ENTITY" in xml.upper():
        raise XmlInvalido("XML com DOCTYPE/ENTITY não é aceito.")
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise XmlInvalido("XML ilegível.") from exc


def nome_local(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


class Leitor:
    """Busca por caminhos relativos (`a/b/c`) com um namespace fixo."""

    def __init__(self, ns: str):
        self.ns = ns

    def _caminho(self, caminho: str) -> str:
        return "/".join(f"{{{self.ns}}}{p}" for p in caminho.split("/"))

    def no(self, el: ET.Element | None, caminho: str) -> ET.Element | None:
        return None if el is None else el.find(self._caminho(caminho))

    def nos(self, el: ET.Element | None, caminho: str) -> list[ET.Element]:
        return [] if el is None else el.findall(self._caminho(caminho))

    def txt(self, el: ET.Element | None, caminho: str) -> str | None:
        n = self.no(el, caminho)
        v = (n.text or "").strip() if n is not None else ""
        return v or None

    def dec(self, el: ET.Element | None, caminho: str) -> Decimal | None:
        v = self.txt(el, caminho)
        if v is None:
            return None
        try:
            return Decimal(v)
        except InvalidOperation as exc:
            raise XmlInvalido(f"Valor inválido em {caminho}.") from exc


def data_hora(valor: str | None, campo: str) -> datetime:
    if not valor:
        raise XmlInvalido(f"Campo {campo} ausente.")
    try:
        return datetime.fromisoformat(valor)
    except ValueError as exc:
        raise XmlInvalido(f"Data inválida em {campo}.") from exc
