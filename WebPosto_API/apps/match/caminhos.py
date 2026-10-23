"""Caminhos locais do Logos Match (pasta de dados do usuario)."""
from __future__ import annotations

import os
from pathlib import Path


def _criar(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def raiz() -> Path:
    base = os.getenv("LOGOS_MATCH_DIR")
    if base:
        return _criar(Path(base))
    local = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return _criar(Path(local) / "LogosMatch")


def premmia(posto_id: int) -> Path:
    return _criar(raiz() / "premmia" / str(posto_id))


def planilhas() -> Path:
    return _criar(raiz() / "planilhas")


def logs() -> Path:
    return _criar(raiz() / "logs")


def fiscal(con) -> Path:
    """Acervo fiscal: `<pasta da rede>/fiscal` se configurada e acessível; senão local."""
    from apps.match import banco  # evita import circular (banco importa caminhos)
    pasta = banco.pasta_rede(con)
    if pasta is not None:
        try:
            if Path(pasta).is_dir():
                return _criar(Path(pasta) / "fiscal")
        except OSError:
            pass
    return _criar(raiz() / "fiscal")


def pacotes() -> Path:
    return _criar(raiz() / "pacotes")
