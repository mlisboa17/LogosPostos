"""JSON local atomico; arquivos reais ficam somente no diretorio ignorado data."""
from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from ..domain.execucao import ResultadoDiario

DIRETORIO = Path(__file__).resolve().parents[4] / "data" / "cash_audit"
logger = logging.getLogger(__name__)


class PersistenciaErro(RuntimeError):
    pass


def caminho_dia(empresa_codigo: int, dia: date, diretorio: Path | None = None) -> Path:
    return (diretorio if diretorio is not None else DIRETORIO) / dia.isoformat() / f"{empresa_codigo}.json"


def carregar_dia(empresa_codigo: int, dia: date, *, diretorio: Path | None = None) -> ResultadoDiario | None:
    caminho = caminho_dia(empresa_codigo, dia, diretorio)
    try:
        conteudo = caminho.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        logger.error("Falha de leitura unidade=%s dia=%s", empresa_codigo, dia)
        raise PersistenciaErro("Falha ao ler auditoria persistida.") from None
    try:
        resultado = ResultadoDiario.model_validate_json(conteudo)
        if resultado.empresa_codigo != empresa_codigo or resultado.dia != dia:
            raise ValueError("Escopo incorreto.")
        return resultado
    except (ValidationError, ValueError):
        logger.error("Registro invalido unidade=%s dia=%s", empresa_codigo, dia)
        raise PersistenciaErro("Auditoria persistida inválida.") from None


def salvar_dia(resultado: ResultadoDiario, *, diretorio: Path | None = None) -> Path:
    caminho = caminho_dia(resultado.empresa_codigo, resultado.dia, diretorio)
    temporario: Path | None = None
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=caminho.parent, suffix=".tmp", delete=False) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(resultado.model_dump_json(indent=2))
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
        return caminho
    except OSError:
        logger.error("Falha de gravacao unidade=%s dia=%s", resultado.empresa_codigo, resultado.dia)
        raise PersistenciaErro("Falha ao persistir auditoria.") from None
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()
