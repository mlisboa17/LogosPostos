"""Registro de postos em pasta de rede compartilhada: um posto, uma máquina coletora."""
from __future__ import annotations

import getpass
import json
import os
import re
import socket
import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

from src.modules.cash_reconciliation.domain.tempo import formatar_data_hora, ler_data_hora

MSG_INDISPONIVEL = "A pasta da rede não está acessível agora. Tente de novo quando ela estiver disponível."


class PastaIndisponivel(Exception):
    pass


@dataclass
class Dono:
    id_instalacao: str
    maquina: str
    usuario_windows: str
    posto_nome: str
    registrado_em: str


class PostoDeOutraMaquina(Exception):
    def __init__(self, dono: Dono):
        super().__init__("posto de outra máquina")
        self.dono = dono


def chave_posto(posto) -> str | None:
    """empresaCodigo do webPosto ou, sem ele, o CNPJ só com dígitos. None: não dá para proteger."""
    codigo = posto["empresa_codigo_webposto"]
    if codigo is not None and re.fullmatch(r"[0-9]+", str(codigo)):
        return str(codigo)
    digitos = re.sub(r"[^0-9]", "", posto["cnpj"] or "")
    return digitos or None


def pasta_postos(pasta: Path) -> Path:
    return Path(pasta) / "LogosMatch" / "postos"


def _validar_chave(chave: str) -> str:
    if not isinstance(chave, str) or not re.fullmatch(r"[0-9]+", chave):
        raise ValueError("chave do posto deve ter só dígitos")
    return chave


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checar(pasta: Path) -> None:
    try:
        if not Path(pasta).is_dir():
            raise PastaIndisponivel(MSG_INDISPONIVEL)
    except OSError:
        raise PastaIndisponivel(MSG_INDISPONIVEL) from None


def _arquivos(pasta: Path, chave: str) -> list[Path]:
    _validar_chave(chave)
    alvo = pasta_postos(pasta)
    try:
        if not alvo.is_dir():
            return []
        return [p for p in alvo.iterdir()
                if p.is_file() and p.suffix == ".json"
                and (p.stem == chave or p.stem.startswith(chave + "-"))]
    except OSError:
        raise PastaIndisponivel(MSG_INDISPONIVEL) from None


def _ler(arq: Path) -> Dono | None:
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
        nomes = [f.name for f in fields(Dono)]
        if not isinstance(dados, dict) or any(not isinstance(dados.get(n), str) for n in nomes):
            return None
        ler_data_hora(dados["registrado_em"])
        return Dono(**{n: dados[n] for n in nomes})
    except (OSError, ValueError, TypeError):
        return None


def dono(pasta: Path, chave: str) -> Dono | None:
    _validar_chave(chave)
    _checar(pasta)
    donos = [d for d in (_ler(a) for a in _arquivos(pasta, chave)) if d]
    if not donos:
        return None
    return min(donos, key=lambda d: (ler_data_hora(d.registrado_em), d.id_instalacao))


def _gravar(pasta: Path, chave: str, d: Dono) -> None:
    _validar_chave(chave)
    alvo = pasta_postos(pasta)
    tmp = None
    try:
        alvo.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=alvo, prefix=f".{chave}-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(d), f, ensure_ascii=False)
        os.replace(tmp, alvo / f"{chave}.json")
        tmp = None
    except OSError:
        raise PastaIndisponivel(MSG_INDISPONIVEL) from None
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _novo(id_instalacao: str, posto_nome: str, registrado_em: str) -> Dono:
    return Dono(id_instalacao, socket.gethostname(), getpass.getuser(), posto_nome, registrado_em)


def registrar(pasta: Path, chave: str, id_instalacao: str, posto_nome: str) -> Dono:
    atual = dono(pasta, chave)
    if atual and atual.id_instalacao != id_instalacao:
        raise PostoDeOutraMaquina(atual)
    novo = _novo(id_instalacao, posto_nome, atual.registrado_em if atual else _agora())
    _gravar(pasta, chave, novo)
    return novo


def assumir(pasta: Path, chave: str, id_instalacao: str, posto_nome: str) -> Dono:
    _validar_chave(chave)
    _checar(pasta)
    copias = _arquivos(pasta, chave)
    novo = _novo(id_instalacao, posto_nome, _agora())
    _gravar(pasta, chave, novo)
    principal = pasta_postos(pasta) / f"{chave}.json"
    for c in copias:
        if c != principal:
            try:
                c.unlink()
            except OSError:
                pass
    return novo


def liberar(pasta: Path, chave: str, id_instalacao: str) -> bool:
    atual = dono(pasta, chave)
    if not atual or atual.id_instalacao != id_instalacao:
        return False
    try:
        for a in _arquivos(pasta, chave):
            d = _ler(a)
            if d and d.id_instalacao == id_instalacao:
                a.unlink(missing_ok=True)
    except OSError:
        raise PastaIndisponivel(MSG_INDISPONIVEL) from None
    return True


def _ja_cadastrado(dono: Dono) -> str:
    return (f"Este posto já está cadastrado na máquina {dono.maquina} desde "
            f"{formatar_data_hora(ler_data_hora(dono.registrado_em))}.")


def mensagem_bloqueio(dono: Dono) -> str:
    return f"{_ja_cadastrado(dono)} Desative lá ou use 'Assumir posto'."


def mensagem_salvo_desativado(dono: Dono) -> str:
    """Posto novo (cadastro ou importação) que pertence a outra máquina: gravado desativado aqui."""
    return (f"{_ja_cadastrado(dono)} Ele foi salvo desativado aqui; use 'Assumir posto' se a outra"
            " máquina não coleta mais.")
