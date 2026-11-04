"""Certificado A1 por empresa: validação no envio, guarda cifrada e leitura para as consultas.

O arquivo .pfx é cifrado com a DPAPI do usuário Windows (só esse usuário, nesta máquina, decifra)
e gravado em `caminhos.certificados()`. A senha fica no Credential Manager. O banco guarda só
os dados públicos do certificado. Nada disso vai para log, planilha ou pasta da rede.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from apps.match import caminhos, credenciais
from apps.match.banco import _agora
from apps.match.fiscal import repositorio as repo

MAX_BYTES = 64 * 1024
MSG_SENHA = "Senha errada ou arquivo que não é certificado A1 (.pfx/.p12)."


class CertificadoInvalido(ValueError):
    """Mensagem em português simples, pronta para a tela."""


@dataclass(frozen=True)
class InfoCertificado:
    titular: str
    cnpj: str
    da_matriz: bool
    valido_ate: datetime

    @property
    def dias_restantes(self) -> int:
        return (self.valido_ate - datetime.now(timezone.utc)).days


# ---------------------------------------------------------------- DPAPI (Windows)

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(dados: bytes, cifrar: bool) -> bytes:
    if sys.platform != "win32":  # o app só roda no Windows; aqui só para não quebrar import
        raise RuntimeError("DPAPI só existe no Windows")
    entrada = _Blob(len(dados), ctypes.cast(ctypes.create_string_buffer(dados, len(dados)),
                                            ctypes.POINTER(ctypes.c_char)))
    saida = _Blob()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    funcao = crypt32.CryptProtectData if cifrar else crypt32.CryptUnprotectData
    ok = funcao(ctypes.byref(entrada), None, None, None, None, 0x1, ctypes.byref(saida))  # UI_FORBIDDEN
    if not ok:
        raise OSError("Não foi possível proteger/ler o certificado neste usuário do Windows.")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        kernel32.LocalFree(saida.pbData)


# ---------------------------------------------------------------- validação

def _fmt(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}" if len(cnpj) == 14 else cnpj


def validar(pfx: bytes, senha: str, cnpj_empresa: str) -> tuple[InfoCertificado, str, datetime]:
    """Confere senha, tipo (e-CNPJ), titular e validade. Devolve info, impressão digital e início."""
    if not pfx or len(pfx) > MAX_BYTES:
        raise CertificadoInvalido("Arquivo vazio ou grande demais para um certificado A1.")
    try:
        _, cert, _ = pkcs12.load_key_and_certificates(pfx, senha.encode())
    except Exception:  # noqa: BLE001 - qualquer falha aqui é senha errada ou arquivo errado
        raise CertificadoInvalido(MSG_SENHA) from None
    if cert is None:
        raise CertificadoInvalido(MSG_SENHA)
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    texto = cn[0].value if cn else ""
    m = re.search(r":(\d{11}|\d{14})\s*$", texto)
    if not m:
        raise CertificadoInvalido("Não encontrei o CNPJ no certificado. Use o certificado A1 da empresa (e-CNPJ).")
    documento, titular = m.group(1), texto[:m.start()].strip()
    if len(documento) == 11:
        raise CertificadoInvalido("Este é um certificado de pessoa (e-CPF). Para buscar as notas da empresa "
                                  "é preciso o certificado da empresa (e-CNPJ).")
    if documento != cnpj_empresa and documento[:8] != cnpj_empresa[:8]:
        raise CertificadoInvalido(f"Este certificado é do CNPJ {_fmt(documento)}, mas a empresa é "
                                  f"{_fmt(cnpj_empresa)}. Escolha o arquivo certo.")
    fim = cert.not_valid_after_utc
    if fim <= datetime.now(timezone.utc):
        raise CertificadoInvalido(f"Este certificado venceu em {fim:%d/%m/%Y}. Envie o certificado renovado.")
    info = InfoCertificado(titular, documento, documento != cnpj_empresa, fim)
    return info, cert.fingerprint(hashes.SHA256()).hex(), cert.not_valid_before_utc


# ---------------------------------------------------------------- guarda e leitura

def _chave_senha(empresa_id: int) -> str:
    return f"empresa/{empresa_id}/a1"


def salvar(con, empresa_id: int, pfx: bytes, senha: str) -> InfoCertificado:
    empresa = repo.obter_empresa(con, empresa_id)
    info, digital, inicio = validar(pfx, senha, empresa["cnpj"])
    arquivo = caminhos.certificados() / f"{empresa_id}-{uuid.uuid4().hex}.bin"
    arquivo.write_bytes(_dpapi(pfx, cifrar=True))
    credenciais.salvar(_chave_senha(empresa_id), senha)
    anteriores = [r["arquivo"] for r in con.execute(
        "SELECT arquivo FROM certificado WHERE empresa_id=? AND ativo=1", (empresa_id,))]
    con.execute("UPDATE certificado SET ativo=0 WHERE empresa_id=?", (empresa_id,))
    con.execute("INSERT INTO certificado(empresa_id, arquivo, titular, titular_cnpj, da_matriz, valido_de,"
                " valido_ate, impressao_digital, ativo, enviado_em) VALUES (?,?,?,?,?,?,?,?,1,?)",
                (empresa_id, arquivo.name, info.titular, info.cnpj, int(info.da_matriz), inicio.isoformat(),
                 info.valido_ate.isoformat(), digital, _agora()))
    con.commit()
    for nome in anteriores:  # o histórico fica no banco; o arquivo antigo não serve mais
        (caminhos.certificados() / nome).unlink(missing_ok=True)
    return info


def situacao(con, empresa_id: int) -> InfoCertificado | None:
    r = con.execute("SELECT * FROM certificado WHERE empresa_id=? AND ativo=1", (empresa_id,)).fetchone()
    if r is None:
        return None
    return InfoCertificado(r["titular"], r["titular_cnpj"], bool(r["da_matriz"]),
                           datetime.fromisoformat(r["valido_ate"]))


def carregar(con, empresa_id: int) -> tuple[bytes, str] | None:
    """(pfx, senha) do certificado ativo, só em memória, para as consultas ao ADN e à SEFAZ."""
    r = con.execute("SELECT arquivo FROM certificado WHERE empresa_id=? AND ativo=1", (empresa_id,)).fetchone()
    senha = credenciais.ler(_chave_senha(empresa_id))
    if r is None or not senha:
        return None
    arquivo: Path = caminhos.certificados() / r["arquivo"]
    if not arquivo.exists():
        return None
    return _dpapi(arquivo.read_bytes(), cifrar=False), senha

