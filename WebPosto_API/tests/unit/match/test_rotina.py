import asyncio
import sqlite3
import threading
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from apps.match import agendador, banco, coletas, rotina
from apps.match.canais import envio, toast
from src.modules.cash_reconciliation.domain.tempo import FUSO

DIA = date(2026, 10, 17)


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "t.db")
    yield c
    c.close()


def _agora(h, m=0):
    return datetime(2026, 10, 18, h, m, tzinfo=FUSO)


def _coleta(con, iniciada_em, dia=DIA):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    fid = banco.salvar_fonte(con, pid, "premmia", True, {})
    cid = banco.registrar_coleta(con, fid, dia, "ok", 1, Decimal("1"), None)
    con.execute("UPDATE coleta SET iniciada_em=? WHERE id=?", (iniciada_em, cid))
    con.commit()
    return pid, fid, cid


def test_recupera_quando_maquina_estava_desligada(con):
    assert rotina.precisa_recuperar(con, _agora(8, 30)) is True
    assert rotina.precisa_recuperar(con, _agora(5, 0)) is False
    # iniciada hoje 07:00 Recife = 10:00 UTC
    _coleta(con, datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc).isoformat())
    assert rotina.precisa_recuperar(con, _agora(8, 30)) is False


def test_coleta_iniciada_ontem_nao_conta(con):
    _coleta(con, datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc).isoformat())
    assert rotina.precisa_recuperar(con, _agora(8, 30)) is True


@pytest.fixture
def falsos(monkeypatch):
    f = {"toasts": [], "enviados": []}
    monkeypatch.setattr(rotina.unidades, "ativar", lambda c: None)
    monkeypatch.setattr(toast, "avisar", lambda t, x: f["toasts"].append((t, x)))
    monkeypatch.setattr(envio, "enviar_dia", lambda c, r, d: f["enviados"].append((list(r), d)))
    return f


def _res(pid, situacao, msg="msg"):
    return coletas.ResultadoFonte(pid, "premmia", DIA, situacao, 0, Decimal(0), msg, [])


def _fake_coleta(monkeypatch, resultados, chamadas=None):
    async def todos(c, dia, *, so_falhas=False):
        if chamadas is not None:
            chamadas.append((dia, so_falhas))
        return resultados
    monkeypatch.setattr(coletas, "coletar_todos", todos)


def test_repescagem_avisa_dia_sem_coleta(con, falsos, monkeypatch):
    pid = banco.inserir_posto(con, "Posto Doze", "Doze", None, 74014)
    chamadas = []
    _fake_coleta(monkeypatch, [_res(pid, "erro"), _res(pid, "ok")], chamadas)
    asyncio.run(rotina.executar(con, dia=DIA, so_falhas=True))
    esperado = "O dia 17/10/2026 ficou sem coleta de Premmia no Doze."
    assert chamadas == [(DIA, True)]
    assert any(esperado in x for _, x in falsos["toasts"])
    enviados = falsos["enviados"][0][0]
    assert esperado in enviados[0].mensagem and esperado not in enviados[1].mensagem


def test_erro_dispara_toast(con, falsos, monkeypatch):
    pid = banco.inserir_posto(con, "Posto Doze", "Doze", None, 74014)
    _fake_coleta(monkeypatch, [_res(pid, "verificacao_humana", "Abra o Premmia."), _res(pid, "ok")])
    asyncio.run(rotina.executar(con, dia=DIA))
    assert len(falsos["toasts"]) == 1 and "Abra o Premmia." in falsos["toasts"][0][1]
    assert "ficou sem coleta" not in falsos["toasts"][0][1]


def test_executar_dia_padrao_e_posto_unico(con, falsos, monkeypatch):
    visto = {}

    async def posto(c, pid, dia, *, visivel=False, so_falhas=False):
        visto.update(pid=pid, dia=dia, visivel=visivel)
        return []
    monkeypatch.setattr(coletas, "coletar_posto", posto)
    monkeypatch.setattr(rotina, "ontem", lambda: DIA)
    asyncio.run(rotina.executar(con, posto_id=5, visivel=True))
    assert visto == {"pid": 5, "dia": DIA, "visivel": True}


def test_limpar_antigos_13_meses(con):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    fid = banco.salvar_fonte(con, pid, "premmia", True, {})
    for d in ("2025-09-17", "2025-09-18"):
        banco.registrar_coleta(con, fid, d, "ok", 0, Decimal(0), None)
        banco.gravar_divergencias(con, pid, d, "premmia", [{"tipo": "x"}])
    cid = con.execute("SELECT id FROM coleta WHERE dia='2025-09-17'").fetchone()["id"]
    con.execute("INSERT INTO transacao(coleta_id,posto_id,fonte,identificador,valor,momento)"
                " VALUES (?,?,?,?,?,?)", (cid, pid, "premmia", "a", "1", "x"))
    con.execute("INSERT INTO canal(tipo) VALUES ('toast')")
    con.execute("INSERT INTO envio(canal_id,dia) VALUES (1,'2025-09-17'),(1,'2025-09-18')")
    con.commit()
    pasta = rotina.caminhos.planilhas()
    velha = pasta / "Logos_Doze_17-09-2025.xlsx"
    nova = pasta / "Logos_Doze_18-09-2025.xlsx"
    outra = pasta / "notas.xlsx"
    for a in (velha, nova, outra):
        a.write_bytes(b"x")
    rotina.limpar_antigos(con, date(2026, 10, 18))  # limite 2025-09-18
    for t in ("coleta", "divergencia", "envio"):
        assert [r["dia"] for r in con.execute(f"SELECT dia FROM {t}")] == ["2025-09-18"]
    assert con.execute("SELECT COUNT(*) FROM transacao").fetchone()[0] == 0
    assert not velha.exists() and nova.exists() and outra.exists()


def test_menos_meses_ajusta_dia():
    assert rotina._menos_meses(date(2026, 3, 31), 13) == date(2025, 2, 28)
    assert rotina._menos_meses(date(2026, 1, 15), 13) == date(2024, 12, 15)


def test_migracao_2_atualiza_banco_v1(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    caminho = tmp_path / "v1.db"
    raw = sqlite3.connect(caminho)
    raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    raw.executescript(banco._SCHEMA_V1)
    raw.execute("INSERT INTO schema_version VALUES (1)")
    raw.execute("INSERT INTO instalacao VALUES ('abc','2026-01-01','0.1')")
    raw.commit()
    raw.close()
    c = banco.conectar(caminho)
    row = c.execute("SELECT * FROM instalacao").fetchone()
    assert (row["id_instalacao"], row["hora_coleta"], row["hora_repescagem"]) == ("abc", "06:00", "10:00")
    assert c.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 2
    c.close()
    novo = banco.conectar(tmp_path / "novo.db")
    assert novo.execute("SELECT COUNT(*) FROM instalacao").fetchone()[0] == 1
    novo.close()


def test_duas_threads_escrevem_sem_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    caminho = tmp_path / "w.db"
    banco.conectar(caminho).close()
    erros = []

    def trabalho(n):
        try:
            c = banco.conectar(caminho)
            for i in range(30):
                banco.inserir_posto(c, f"P{n}-{i}", None, None, n)
            c.close()
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    ts = [threading.Thread(target=trabalho, args=(n,)) for n in (1, 2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    c = banco.conectar(caminho)
    assert erros == [] and c.execute("SELECT COUNT(*) FROM posto").fetchone()[0] == 60
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c.close()


def _campos(job):
    return {f.name: str(f) for f in job.trigger.fields}


def test_agendador_jobs_e_horarios(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    caminho = tmp_path / "a.db"

    def fabrica():
        return banco.conectar(caminho)

    monkeypatch.setattr(agendador, "agora", lambda: _agora(5, 0))
    sched = agendador.iniciar(fabrica, pausado=True)
    try:
        jobs = {j.id: j for j in sched.get_jobs()}
        assert set(jobs) == {"coleta", "repescagem"}
        assert (_campos(jobs["coleta"])["hour"], _campos(jobs["coleta"])["minute"]) == ("6", "0")
        assert _campos(jobs["repescagem"])["hour"] == "10"
        assert jobs["coleta"].trigger.timezone == FUSO
        assert jobs["coleta"].coalesce and jobs["coleta"].max_instances == 1
        assert jobs["coleta"].misfire_grace_time == 3600
        c = fabrica()
        c.execute("UPDATE instalacao SET hora_coleta='07:30'")
        c.commit()
        agendador.reagendar(sched, c)
        c.close()
        assert _campos({j.id: j for j in sched.get_jobs()}["coleta"])["hour"] == "7"
    finally:
        sched.shutdown(wait=False)


def test_agendador_agenda_recuperacao(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    monkeypatch.setattr(agendador, "agora", lambda: _agora(8, 30))
    sched = agendador.iniciar(lambda: banco.conectar(tmp_path / "b.db"), pausado=True)
    try:
        assert "recuperacao" in {j.id for j in sched.get_jobs()}
    finally:
        sched.shutdown(wait=False)
