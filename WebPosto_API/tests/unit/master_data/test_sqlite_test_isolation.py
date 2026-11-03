from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from sqlite3 import connect as conectar_sqlite

import aiosqlite
import pytest
from sqlalchemy import create_engine

from src.modules.classification_review.adapters.sqlite_classification_review_repository import (
    SqliteClassificationReviewRepository,
)
from src.modules.master_data.adapters.sqlite_master_data_repository import (
    DEFAULT_MASTER_DATA_DB,
    SqliteMasterDataRepository,
)
from src.modules.master_data.application.master_data_service import MasterDataService
from src.modules.master_data.application.plano_contas_sync_service import PlanoContasSyncService


@pytest.mark.parametrize(
    "database",
    [
        DEFAULT_MASTER_DATA_DB,
        str(DEFAULT_MASTER_DATA_DB),
        os.fsencode(DEFAULT_MASTER_DATA_DB),
        DEFAULT_MASTER_DATA_DB.parent / ".." / "master_data" / DEFAULT_MASTER_DATA_DB.name,
        DEFAULT_MASTER_DATA_DB.as_uri() + "?mode=ro&immutable=1",
        DEFAULT_MASTER_DATA_DB.as_uri().replace("master_data", "master%5Fdata"),
        DEFAULT_MASTER_DATA_DB.parent / "banco_acidental.sqlite3",
    ],
)
def test_conexao_persistente_falha_antes_da_abertura(database):
    with pytest.raises(pytest.fail.Exception, match="SQLite persistente"):
        conectar_sqlite(database, uri=isinstance(database, str) and database.startswith("file:"))


def test_caminho_relativo_persistente_bloqueado(monkeypatch):
    app_dir = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(app_dir)
    with pytest.raises(pytest.fail.Exception, match="SQLite persistente"):
        sqlite3.connect(os.path.relpath(DEFAULT_MASTER_DATA_DB, app_dir))


@pytest.mark.parametrize(
    "factory",
    [
        SqliteMasterDataRepository,
        SqliteClassificationReviewRepository,
        MasterDataService,
        PlanoContasSyncService,
    ],
)
def test_repositorio_padrao_nao_pode_ser_usado_em_testes(factory):
    with pytest.raises(pytest.fail.Exception, match="Injete um banco em tmp_path"):
        factory()


def test_sqlalchemy_nao_contorna_protecao():
    engine = create_engine("sqlite:///" + str(DEFAULT_MASTER_DATA_DB))
    try:
        with pytest.raises(pytest.fail.Exception, match="SQLite persistente"):
            engine.connect()
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_aiosqlite_nao_contorna_protecao(monkeypatch):
    connection = aiosqlite.connect(DEFAULT_MASTER_DATA_DB)
    stop = connection.stop
    paradas = []

    def capturar_parada():
        future = stop()
        if future is not None:
            paradas.append(future)
        return future

    monkeypatch.setattr(connection, "stop", capturar_parada)
    try:
        with pytest.raises(pytest.fail.Exception, match="SQLite persistente"):
            async with connection:
                pytest.fail("Conexão persistente não deveria ter sido aberta.")
    finally:
        for future in paradas:
            await future


@pytest.mark.parametrize("database", ["", ":memory:", "file:teste_isolado?mode=memory&cache=shared"])
def test_bancos_em_memoria_permitidos(database):
    conn = conectar_sqlite(database, uri=database.startswith("file:"))
    try:
        assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        conn.close()


def test_banco_temporario_permitido(tmp_path):
    path = tmp_path / "master_data.sqlite3"
    conn = conectar_sqlite(path)
    try:
        conn.execute("CREATE TABLE teste (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO teste VALUES (1)")
        conn.commit()
        assert conn.execute("SELECT id FROM teste").fetchone() == (1,)
    finally:
        conn.close()


def test_protecao_ativa_durante_coleta(tmp_path):
    test_file = tmp_path / "test_abertura_na_coleta.py"
    test_file.write_text(
        "import sqlite3\n"
        f"sqlite3.connect({str(DEFAULT_MASTER_DATA_DB)!r})\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "--collect-only", "-q",
            "-o", "addopts=", str(test_file),
        ],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "SQLite persistente" in result.stdout + result.stderr
