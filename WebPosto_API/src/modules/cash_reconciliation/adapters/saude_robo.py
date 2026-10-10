"""Persistencia local do estado do job e dos resumos diarios."""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from ..domain.tempo import para_local

logger = logging.getLogger(__name__)
DIRETORIO_RESUMOS = Path(__file__).resolve().parents[4] / "data" / "resumos"
CAMINHO_ESTADO = DIRETORIO_RESUMOS / "estado_robo.json"


class EstadoRobo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ultima_execucao: datetime
    dia_processado: date
    unidades_processadas: tuple[int, ...]
    unidades_com_falha: tuple[int, ...]
    resumo_gerado: bool
    unidades_com_aviso: tuple[int, ...] = ()

    @field_validator("ultima_execucao")
    @classmethod
    def normalizar_fuso(cls, valor: datetime) -> datetime:
        return para_local(valor)

    @model_validator(mode="after")
    def validar_unidades(self) -> EstadoRobo:
        if any(codigo <= 0 for codigo in (
            *self.unidades_processadas,
            *self.unidades_com_falha,
            *self.unidades_com_aviso,
        )):
            raise ValueError("Codigo de unidade invalido.")
        if len(set(self.unidades_processadas)) != len(self.unidades_processadas):
            raise ValueError("Unidade processada duplicada.")
        if not set(self.unidades_com_falha).issubset(self.unidades_processadas):
            raise ValueError("Falha fora das unidades processadas.")
        if not set(self.unidades_com_aviso).issubset(self.unidades_processadas):
            raise ValueError("Aviso fora das unidades processadas.")
        return self


class PersistenciaEstadoErro(RuntimeError):
    pass


def caminho_resumo(dia: date, diretorio: Path | None = None) -> Path:
    raiz = DIRETORIO_RESUMOS if diretorio is None else diretorio
    return raiz / f"{dia.isoformat()}.md"


def _gravar_atomico(caminho: Path, conteudo: str) -> None:
    temporario: Path | None = None
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=caminho.parent, suffix=".tmp", delete=False
        ) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except OSError as exc:
        logger.error("Falha ao persistir estado do robo tipo=%s", type(exc).__name__)
        raise PersistenciaEstadoErro("Falha ao persistir estado do robô.") from None
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


def salvar_estado(estado: EstadoRobo, *, caminho: Path | None = None) -> None:
    destino = CAMINHO_ESTADO if caminho is None else caminho
    _gravar_atomico(destino, estado.model_dump_json(indent=2))


def carregar_estado(*, caminho: Path | None = None) -> EstadoRobo | None:
    origem = CAMINHO_ESTADO if caminho is None else caminho
    try:
        conteudo = origem.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        logger.error("Falha ao ler estado do robo tipo=%s", type(exc).__name__)
        raise PersistenciaEstadoErro("Falha ao ler estado do robô.") from None
    try:
        return EstadoRobo.model_validate_json(conteudo)
    except (ValidationError, ValueError):
        logger.error("Estado persistido do robo invalido")
        raise PersistenciaEstadoErro("Estado persistido do robô inválido.") from None


def salvar_resumo(dia: date, conteudo: str, *, diretorio: Path | None = None) -> Path:
    destino = caminho_resumo(dia, diretorio)
    _gravar_atomico(destino, conteudo)
    return destino
