"""Distribuição de NFS-e do Ambiente de Dados Nacional (ADN), somente leitura.

`GET /DFe/{NSU}?lote=true` com certificado A1 (mTLS) devolve os documentos depois do NSU.
Campos conforme o manual dos contribuintes e implementações públicas; validar na 1ª consulta real.
"""
from __future__ import annotations

import base64
import binascii
import gzip
import logging
import secrets
import ssl
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

logger = logging.getLogger(__name__)
URL_PRODUCAO = "https://adn.nfse.gov.br/contribuintes"
FILA_VAZIA = "NENHUM_DOCUMENTO_LOCALIZADO"


class AdnErro(RuntimeError):
    def __init__(self, tipo: Literal["certificado", "indisponivel", "resposta"]):
        super().__init__(tipo)
        self.tipo = tipo


@dataclass
class DocumentoAdn:
    nsu: int
    chave: str
    tipo: str
    xml: bytes | None  # None: arquivo ilegível, o lote segue


@dataclass
class LoteAdn:
    documentos: list[DocumentoAdn] = field(default_factory=list)
    vazio: bool = False


def contexto_ssl(pfx: bytes, senha: str) -> ssl.SSLContext:
    """Contexto mTLS. O ssl só lê arquivos: a chave passa por disco cifrada e sai em seguida."""
    chave, cert, cadeia = pkcs12.load_key_and_certificates(pfx, senha.encode())
    temporaria = secrets.token_urlsafe(32)
    ctx = ssl.create_default_context()
    with tempfile.TemporaryDirectory() as pasta:
        arq_cert, arq_chave = Path(pasta) / "c.pem", Path(pasta) / "k.pem"
        arq_cert.write_bytes(b"".join(c.public_bytes(serialization.Encoding.PEM) for c in [cert, *(cadeia or [])]))
        arq_chave.write_bytes(chave.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(temporaria.encode())))
        ctx.load_cert_chain(str(arq_cert), str(arq_chave), password=temporaria)
    return ctx


def cliente(pfx: bytes, senha: str, base_url: str = URL_PRODUCAO) -> httpx.Client:
    return httpx.Client(base_url=base_url, verify=contexto_ssl(pfx, senha), timeout=60.0)


def _xml(arquivo) -> bytes | None:
    try:
        return gzip.decompress(base64.b64decode(arquivo, validate=True))
    except (binascii.Error, OSError, EOFError, TypeError, ValueError):
        return None


def distribuir(client: httpx.Client, nsu: int, cnpj_consulta: str | None = None) -> LoteAdn:
    """Até 50 documentos depois de `nsu`. Fila vazia devolve `LoteAdn(vazio=True)`."""
    params: dict[str, str] = {"lote": "true"}
    if cnpj_consulta:
        params["cnpjConsulta"] = cnpj_consulta
    try:
        resp = client.get(f"/DFe/{int(nsu)}", params=params)
    except httpx.HTTPError as exc:
        logger.warning("ADN sem resposta tipo=%s", type(exc).__name__)
        raise AdnErro("indisponivel") from None
    if resp.status_code in (401, 403, 495, 496):
        raise AdnErro("certificado")
    if resp.status_code >= 500:
        raise AdnErro("indisponivel")
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    if not isinstance(corpo, dict):
        corpo = {}
    if resp.status_code == 404 or corpo.get("StatusProcessamento") == FILA_VAZIA:
        return LoteAdn(vazio=True)
    if resp.status_code != 200 or corpo.get("StatusProcessamento") == "REJEICAO":
        logger.warning("ADN recusou http=%s", resp.status_code)
        raise AdnErro("resposta")
    documentos = []
    for d in corpo.get("LoteDFe") or []:
        try:
            documentos.append(DocumentoAdn(int(d["NSU"]), str(d.get("ChaveAcesso") or ""),
                                           str(d.get("TipoDocumento") or "").upper(), _xml(d.get("ArquivoXml"))))
        except (KeyError, TypeError, ValueError):
            logger.warning("Item do lote ADN ignorado (formato inesperado)")
    return LoteAdn(documentos, vazio=not documentos)
