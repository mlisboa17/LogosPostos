"""Persistencia atomica de snapshots mensais do placar."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from ..domain.models import Placar

logger = logging.getLogger(__name__)
DIRETORIO_PLACAR = Path(__file__).resolve().parents[4] / "data" / "placar"


class PersistenciaErro(RuntimeError):
    pass


def caminho_placar(posto: int, mes: str, diretorio: Path | None = None) -> Path:
    raiz = DIRETORIO_PLACAR if diretorio is None else diretorio
    return raiz / mes / f"{posto}.json"


def carregar_placar(posto: int, mes: str, *, diretorio: Path | None = None) -> Placar | None:
    caminho = caminho_placar(posto, mes, diretorio)
    try:
        conteudo = caminho.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        logger.error("Falha de leitura posto=%s mes=%s", posto, mes)
        raise PersistenciaErro("Falha ao ler placar persistido.") from None
    try:
        placar = Placar.model_validate_json(conteudo)
        if placar.posto != posto or placar.mes != mes:
            raise ValueError("Escopo incorreto.")
        return placar
    except (ValidationError, ValueError):
        logger.error("Registro de placar invalido posto=%s mes=%s", posto, mes)
        raise PersistenciaErro("Placar persistido inválido.") from None


def salvar_placar(placar: Placar, *, diretorio: Path | None = None) -> Path:
    caminho = caminho_placar(placar.posto, placar.mes, diretorio)
    anterior = carregar_placar(placar.posto, placar.mes, diretorio=diretorio)
    if anterior is not None and anterior.dia > placar.dia:
        logger.warning("Snapshot antigo ignorado posto=%s mes=%s", placar.posto, placar.mes)
        return caminho
    temporario: Path | None = None
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=caminho.parent,
            suffix=".tmp",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(placar.model_dump_json(indent=2))
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
        return caminho
    except OSError:
        logger.error("Falha de gravacao posto=%s mes=%s", placar.posto, placar.mes)
        raise PersistenciaErro("Falha ao persistir placar.") from None
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()
