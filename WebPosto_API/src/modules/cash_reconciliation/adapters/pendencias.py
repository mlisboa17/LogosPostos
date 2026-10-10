"""Repositorio SQLite append-only da fila de pendências."""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator, Literal

from ..domain.pendencias import EventoPendencia, NovaPendencia, Pendencia
from ..domain.tempo import agora

DIRETORIO_PENDENCIAS = Path(__file__).resolve().parents[4] / "data" / "pendencias"
BANCO_PENDENCIAS = DIRETORIO_PENDENCIAS / "pendencias.sqlite3"
logger = logging.getLogger(__name__)


class ErroPersistenciaPendencias(RuntimeError):
    pass


class TransicaoPendenciaInvalida(RuntimeError):
    pass


@contextmanager
def _conectar(banco: Path | None = None) -> Iterator[sqlite3.Connection]:
    caminho = banco or BANCO_PENDENCIAS
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Falha ao preparar banco de pendências tipo=%s", type(exc).__name__)
        raise ErroPersistenciaPendencias("Falha ao preparar a fila de pendências.") from None
    try:
        conexao = sqlite3.connect(caminho, timeout=10)
    except sqlite3.Error as exc:
        logger.error("Falha ao preparar banco de pendências tipo=%s", type(exc).__name__)
        raise ErroPersistenciaPendencias("Falha ao preparar a fila de pendências.") from None
    try:
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.executescript(
            """
            CREATE TABLE IF NOT EXISTS pendencias (
                id TEXT PRIMARY KEY,
                identidade TEXT NOT NULL UNIQUE,
                unidade INTEGER NOT NULL,
                dia TEXT NOT NULL,
                tipo TEXT NOT NULL,
                severidade TEXT NOT NULL CHECK (severidade IN ('vermelho', 'laranja')),
                valor TEXT,
                referencia TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('aberta', 'justificada', 'aprovada', 'recusada')),
                responsavel TEXT,
                criada_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pendencias_unidade_status_dia
                ON pendencias (unidade, status, dia DESC);
            CREATE TABLE IF NOT EXISTS historico_pendencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pendencia_id TEXT NOT NULL REFERENCES pendencias(id),
                acao TEXT NOT NULL,
                status_anterior TEXT,
                status_novo TEXT NOT NULL,
                usuario TEXT NOT NULL,
                justificativa TEXT,
                registrado_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_historico_pendencia_id
                ON historico_pendencias (pendencia_id, id);
            CREATE TRIGGER IF NOT EXISTS historico_pendencias_nao_atualiza
                BEFORE UPDATE ON historico_pendencias
                BEGIN SELECT RAISE(ABORT, 'historico imutavel'); END;
            CREATE TRIGGER IF NOT EXISTS historico_pendencias_nao_apaga
                BEFORE DELETE ON historico_pendencias
                BEGIN SELECT RAISE(ABORT, 'historico imutavel'); END;
            """
        )
    except sqlite3.Error as exc:
        conexao.close()
        logger.error("Falha ao preparar banco de pendências tipo=%s", type(exc).__name__)
        raise ErroPersistenciaPendencias("Falha ao preparar a fila de pendências.") from None
    try:
        with conexao:
            yield conexao
    finally:
        conexao.close()


def _evento(row: sqlite3.Row) -> EventoPendencia:
    return EventoPendencia(
        id=row["id"],
        acao=row["acao"],
        status_anterior=row["status_anterior"],
        status_novo=row["status_novo"],
        usuario=row["usuario"],
        justificativa=row["justificativa"],
        registrado_em=datetime.fromisoformat(row["registrado_em"]),
    )


def _pendencia(row: sqlite3.Row, eventos: tuple[EventoPendencia, ...] = ()) -> Pendencia:
    return Pendencia(
        id=row["id"],
        unidade=row["unidade"],
        dia=date.fromisoformat(row["dia"]),
        tipo=row["tipo"],
        severidade=row["severidade"],
        valor=Decimal(row["valor"]) if row["valor"] is not None else None,
        referencia=row["referencia"],
        mensagem=row["mensagem"],
        status=row["status"],
        responsavel=row["responsavel"],
        criada_em=datetime.fromisoformat(row["criada_em"]),
        historico=eventos,
    )


def registrar(
    novas: Iterable[NovaPendencia],
    *,
    banco: Path | None = None,
    usuario: str = "robô-noturno",
) -> int:
    inseridas = 0
    try:
        with _conectar(banco) as conexao:
            for nova in novas:
                identidade = nova.identidade or (
                    f"{nova.unidade}|{nova.dia.isoformat()}|{nova.tipo}|{nova.referencia}"
                )
                identidade = hashlib.sha256(identidade.encode("utf-8")).hexdigest()
                pendencia_id = uuid.uuid4().hex
                criada_em = agora().isoformat()
                cursor = conexao.execute(
                    """
                    INSERT OR IGNORE INTO pendencias
                        (id, identidade, unidade, dia, tipo, severidade, valor, referencia,
                         mensagem, status, responsavel, criada_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'aberta', NULL, ?)
                    """,
                    (
                        pendencia_id, identidade, nova.unidade, nova.dia.isoformat(), nova.tipo,
                        nova.severidade, str(nova.valor) if nova.valor is not None else None,
                        nova.referencia, nova.mensagem, criada_em,
                    ),
                )
                if cursor.rowcount != 1:
                    continue
                conexao.execute(
                    """
                    INSERT INTO historico_pendencias
                        (pendencia_id, acao, status_anterior, status_novo, usuario, registrado_em)
                    VALUES (?, 'criada', NULL, 'aberta', ?, ?)
                    """,
                    (pendencia_id, usuario, criada_em),
                )
                inseridas += 1
    except sqlite3.Error as exc:
        logger.error("Falha ao registrar pendências tipo=%s", type(exc).__name__)
        raise ErroPersistenciaPendencias("Falha ao registrar pendências.") from None
    return inseridas


def _carregar_historico(
    conexao: sqlite3.Connection,
    pendencia_id: str,
) -> tuple[EventoPendencia, ...]:
    rows = conexao.execute(
        "SELECT * FROM historico_pendencias WHERE pendencia_id = ? ORDER BY id",
        (pendencia_id,),
    ).fetchall()
    return tuple(_evento(row) for row in rows)


def listar(
    *,
    unidade: int | None = None,
    status: str | None = None,
    tipo: str | None = None,
    limite: int = 100,
    deslocamento: int = 0,
    banco: Path | None = None,
) -> tuple[list[Pendencia], int]:
    filtros = []
    valores: list[object] = []
    if unidade is not None:
        filtros.append("unidade = ?")
        valores.append(unidade)
    if status is not None:
        filtros.append("status = ?")
        valores.append(status)
    if tipo is not None:
        filtros.append("tipo = ?")
        valores.append(tipo)
    where = f" WHERE {' AND '.join(filtros)}" if filtros else ""
    try:
        with _conectar(banco) as conexao:
            total = conexao.execute(f"SELECT COUNT(*) FROM pendencias{where}", valores).fetchone()[0]
            rows = conexao.execute(
                f"SELECT * FROM pendencias{where} ORDER BY dia DESC, criada_em DESC LIMIT ? OFFSET ?",
                (*valores, limite, deslocamento),
            ).fetchall()
            itens = [
                _pendencia(row, _carregar_historico(conexao, row["id"]))
                for row in rows
            ]
            return itens, total
    except sqlite3.Error as exc:
        logger.error("Falha ao listar pendências tipo=%s", type(exc).__name__)
        raise ErroPersistenciaPendencias("Falha ao listar pendências.") from None


def obter(pendencia_id: str, *, banco: Path | None = None) -> Pendencia | None:
    try:
        with _conectar(banco) as conexao:
            row = conexao.execute("SELECT * FROM pendencias WHERE id = ?", (pendencia_id,)).fetchone()
            if row is None:
                return None
            return _pendencia(row, _carregar_historico(conexao, pendencia_id))
    except sqlite3.Error as exc:
        logger.error("Falha ao ler pendência tipo=%s", type(exc).__name__)
        raise ErroPersistenciaPendencias("Falha ao ler pendência.") from None


def contar_abertas(*, unidade: int | None = None, banco: Path | None = None) -> int:
    try:
        with _conectar(banco) as conexao:
            if unidade is None:
                row = conexao.execute("SELECT COUNT(*) FROM pendencias WHERE status = 'aberta'").fetchone()
            else:
                row = conexao.execute(
                    "SELECT COUNT(*) FROM pendencias WHERE status = 'aberta' AND unidade = ?",
                    (unidade,),
                ).fetchone()
            return int(row[0])
    except sqlite3.Error as exc:
        logger.error("Falha ao contar pendências tipo=%s", type(exc).__name__)
        raise ErroPersistenciaPendencias("Falha ao contar pendências abertas.") from None


def transicionar(
    pendencia_id: str,
    *,
    status_esperado: Literal["aberta", "justificada"],
    status_novo: Literal["justificada", "aprovada", "recusada"],
    acao: Literal["justificada", "aprovada", "recusada"],
    usuario: str,
    justificativa: str | None = None,
    banco: Path | None = None,
) -> Pendencia | None:
    try:
        with _conectar(banco) as conexao:
            row = conexao.execute(
                "SELECT * FROM pendencias WHERE id = ?", (pendencia_id,)
            ).fetchone()
            if row is None:
                return None
            responsavel = usuario if status_novo == "justificada" else row["responsavel"]
            cursor = conexao.execute(
                """
                UPDATE pendencias SET status = ?, responsavel = ?
                WHERE id = ? AND status = ?
                """,
                (status_novo, responsavel, pendencia_id, status_esperado),
            )
            if cursor.rowcount != 1:
                raise TransicaoPendenciaInvalida("Transição de pendência não permitida.")
            registrado_em = agora().isoformat()
            conexao.execute(
                """
                INSERT INTO historico_pendencias
                    (pendencia_id, acao, status_anterior, status_novo, usuario, justificativa, registrado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (pendencia_id, acao, status_esperado, status_novo, usuario, justificativa, registrado_em),
            )
            updated = conexao.execute(
                "SELECT * FROM pendencias WHERE id = ?", (pendencia_id,)
            ).fetchone()
            return _pendencia(updated, _carregar_historico(conexao, pendencia_id))
    except TransicaoPendenciaInvalida:
        raise
    except sqlite3.Error as exc:
        logger.error("Falha ao atualizar pendência tipo=%s", type(exc).__name__)
        raise ErroPersistenciaPendencias("Falha ao atualizar pendência.") from None
