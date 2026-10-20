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
    monkeypatch.setattr(envio, "enviar_dia", lambda c, r, d, e=None: f["enviados"].append((list(r), d)))
    return f


def _res(pid, situacao, msg="msg"):
    return coletas.ResultadoFonte(pid, "premmia", DIA, situacao, 0, Decimal(0), msg, [])


def _fake_coleta(monkeypatch, resultados, chamadas=None):
    async def todos(c, dia, *, so_falhas=False, **_):
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

    async def posto(c, pid, dia, *, visivel=False, so_falhas=False, **_):
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
    velha2 = pasta / "Logos_Casa-Caiada-2_17-09-2025.xlsx"
    nova = pasta / "Logos_Doze_18-09-2025.xlsx"
    outra = pasta / "notas.xlsx"
    for a in (velha, velha2, nova, outra):
        a.write_bytes(b"x")
    rotina.limpar_antigos(con, date(2026, 10, 18))  # limite 2025-09-18
    for t in ("coleta", "divergencia", "envio"):
        assert [r["dia"] for r in con.execute(f"SELECT dia FROM {t}")] == ["2025-09-18"]
    assert con.execute("SELECT COUNT(*) FROM transacao").fetchone()[0] == 0
    assert not velha.exists() and not velha2.exists() and nova.exists() and outra.exists()


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
    assert c.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4
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
        c.close()
        agendador.reagendar(sched, fabrica)
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


def test_horario_invalido_cai_no_padrao(con):
    con.execute("UPDATE instalacao SET hora_coleta='abc', hora_repescagem='25:99'")
    con.commit()
    assert rotina.horarios(con) == ("06:00", "10:00")


def test_lock_impede_execucao_simultanea(con, falsos, monkeypatch):
    dentro, soltar, chamadas = threading.Event(), threading.Event(), []

    async def todos(c, dia, *, so_falhas=False, **_):
        chamadas.append(dia)
        dentro.set()
        await asyncio.get_running_loop().run_in_executor(None, soltar.wait, 5)
        return []
    monkeypatch.setattr(coletas, "coletar_todos", todos)
    def _em_thread():
        c = banco.conectar(rotina.caminhos.raiz() / "thread.db")
        try:
            asyncio.run(rotina.executar(c, dia=DIA))
        finally:
            c.close()
    t = threading.Thread(target=_em_thread)
    t.start()
    assert dentro.wait(5)
    con2 = banco.conectar(rotina.caminhos.raiz() / "outra.db")
    try:
        assert asyncio.run(rotina.executar(con2, dia=DIA)) == []
    finally:
        con2.close()
        soltar.set()
        t.join()
    assert chamadas == [DIA]
    # liberado: nova execução volta a coletar
    asyncio.run(rotina.executar(con, dia=DIA))
    assert chamadas == [DIA, DIA]


class _ConFalsa:
    fechada = False

    def close(self):
        self.fechada = True


@pytest.fixture
def jobs(monkeypatch):
    f = {"calls": [], "toasts": [], "con": _ConFalsa(), "erro": None}

    async def executar(con, *, so_falhas=False, **kw):
        f["calls"].append(("executar", so_falhas))
        if f["erro"]:
            raise f["erro"]

    def limpar(con, hoje):
        f["calls"].append(("limpar",))
        if f.get("erro_limpar"):
            raise RuntimeError("x")
    monkeypatch.setattr(agendador.rotina, "executar", executar)
    monkeypatch.setattr(agendador.rotina, "limpar_antigos", limpar)
    monkeypatch.setattr(toast, "avisar", lambda t, x: f["toasts"].append((t, x)))
    monkeypatch.setattr(agendador, "ontem", lambda: DIA)
    return f


def test_job_coleta_executa_e_limpa(jobs):
    agendador._job_coleta(lambda: jobs["con"])
    assert jobs["calls"] == [("executar", False), ("limpar",)]
    assert jobs["con"].fechada and jobs["toasts"] == []


def test_job_repescagem_nao_limpa(jobs):
    agendador._job_repescagem(lambda: jobs["con"])
    assert jobs["calls"] == [("executar", True)] and jobs["con"].fechada


def test_job_contem_erro_avisa_e_ainda_limpa(jobs):
    jobs["erro"] = RuntimeError("segredo-xyz")
    agendador._job_coleta(lambda: jobs["con"])
    assert jobs["calls"] == [("executar", False), ("limpar",)]
    assert jobs["con"].fechada
    titulo, texto = jobs["toasts"][0]
    assert "17/10/2026" in texto and "Coletar agora" in texto and "segredo-xyz" not in texto


def test_job_erro_na_limpeza_nao_propaga(jobs):
    jobs["erro_limpar"] = True
    agendador._job_coleta(lambda: jobs["con"])
    assert jobs["con"].fechada


def test_coletar_agora_visivel_sem_posto_repassa_visivel(con, falsos, monkeypatch):
    visto = {}

    async def todos(c, dia, *, so_falhas=False, visivel=False, **_):
        visto.update(so_falhas=so_falhas, visivel=visivel)
        return []
    monkeypatch.setattr(coletas, "coletar_todos", todos)
    asyncio.run(rotina.executar(con, dia=DIA, visivel=True))
    assert visto == {"so_falhas": False, "visivel": True}


def test_limpar_antigos_apaga_versoes(con):
    pasta = rotina.caminhos.planilhas()
    velha = pasta / "Logos_X_17-09-2025_v2.xlsx"
    nova = pasta / "Logos_X_18-09-2025_v3.xlsx"
    for a in (velha, nova):
        a.write_bytes(b"x")
    rotina.limpar_antigos(con, date(2026, 10, 18))
    assert not velha.exists() and nova.exists()


def test_limpar_antigos_apaga_execucoes(con):
    pid = banco.inserir_posto(con, "Doze", "Doze", None, 74014)
    ids = {}
    for d in ("2025-09-17", "2025-09-18"):
        eid = banco.abrir_execucao(con, "agendada", None, date.fromisoformat(d))
        banco.item_execucao(con, eid, pid, "premmia", "ok")
        banco.fechar_execucao(con, eid, "concluida")
        ids[d] = eid
    rotina.limpar_antigos(con, date(2026, 10, 18))  # limite 2025-09-18
    assert [r["dia"] for r in con.execute("SELECT dia FROM execucao")] == ["2025-09-18"]
    assert [r["execucao_id"] for r in con.execute("SELECT execucao_id FROM execucao_item")] == [
        ids["2025-09-18"]]


# ---- Task 2: registro de execuções ----
def _posto_com_fontes(con):
    pid = banco.inserir_posto(con, "Posto Doze", "Doze", None, 74014)
    banco.salvar_fonte(con, pid, "premmia", True, {})
    banco.salvar_fonte(con, pid, "pagbank_edi", True, {})
    banco.salvar_fonte(con, pid, "webposto", True, {})
    return pid


def test_execucao_registra_itens_e_fecha(con, falsos, monkeypatch):
    pid = _posto_com_fontes(con)
    visto = {}

    async def todos(c, dia, *, ao_progresso=None, **_):
        visto["aguardando"] = {r["fonte"]: r["situacao"] for r in
                               banco.itens_execucao(c, banco.execucao_atual(c)["id"])}
        ao_progresso(pid, "premmia", "coletando", None)
        ao_progresso(pid, "premmia", "ok", "Premmia ok")
        ao_progresso(pid, "pagbank_edi", "erro", "falhou")
        return [_res(pid, "ok")]
    monkeypatch.setattr(coletas, "coletar_todos", todos)
    asyncio.run(rotina.executar(con, dia=DIA, origem="painel", usuario_id=None))
    assert visto["aguardando"] == {"premmia": "aguardando", "pagbank_edi": "aguardando"}
    ex = banco.ultimas_execucoes(con)[0]
    assert (ex["origem"], ex["dia"], ex["situacao"]) == ("painel", str(DIA), "concluida")
    assert ex["terminada_em"] and banco.execucao_atual(con) is None
    itens = {i["fonte"]: i for i in banco.itens_execucao(con, ex["id"])}
    assert itens["premmia"]["situacao"] == "ok" and itens["premmia"]["mensagem"] == "Premmia ok"
    assert itens["premmia"]["iniciada_em"] and itens["premmia"]["terminada_em"]
    assert itens["pagbank_edi"]["situacao"] == "erro" and itens["pagbank_edi"]["iniciada_em"] is None


def test_execucao_falha_fica_falhou(con, falsos, monkeypatch):
    _posto_com_fontes(con)

    async def todos(c, dia, **_):
        raise RuntimeError("x")
    monkeypatch.setattr(coletas, "coletar_todos", todos)
    with pytest.raises(RuntimeError):
        asyncio.run(rotina.executar(con, dia=DIA, origem="bandeja"))
    ex = banco.ultimas_execucoes(con)[0]
    assert ex["situacao"] == "falhou" and ex["terminada_em"] and ex["origem"] == "bandeja"
    assert not rotina.em_andamento()


def test_execucao_so_abre_com_trava_livre(con, falsos):
    assert rotina._TRAVA.acquire(blocking=False)
    try:
        assert asyncio.run(rotina.executar(con, dia=DIA)) == []
    finally:
        rotina._TRAVA.release()
    assert banco.ultimas_execucoes(con) == []


def test_fechar_orfas(con):
    ativa = banco.abrir_execucao(con, "agendada", None, DIA)
    feita = banco.abrir_execucao(con, "painel", None, DIA)
    banco.fechar_execucao(con, feita, "concluida")
    assert rotina.fechar_orfas(con) == 1
    ex = {e["id"]: e for e in banco.ultimas_execucoes(con)}
    assert ex[ativa]["situacao"] == "falhou" and ex[ativa]["terminada_em"]
    assert ex[feita]["situacao"] == "concluida"
    assert rotina.fechar_orfas(con) == 0


def test_origem_agendada_e_repescagem(jobs, monkeypatch):
    origens = []

    async def executar(con, *, so_falhas=False, origem=None, **kw):
        origens.append((so_falhas, origem))
    monkeypatch.setattr(agendador.rotina, "executar", executar)
    agendador._job_coleta(lambda: jobs["con"])
    agendador._job_repescagem(lambda: jobs["con"])
    agendador._job_recuperacao(lambda: jobs["con"])
    assert origens == [(False, "agendada"), (True, "repescagem"), (False, "recuperacao")]


def test_envio_grava_execucao_id(con, monkeypatch):
    pid = _posto_com_fontes(con)
    banco.inserir_canal(con, "toast", {})
    monkeypatch.setattr(toast, "avisar", lambda t, x: None)
    monkeypatch.setattr(envio.relatorio_xlsx, "gerar", lambda *a: None)
    ex = banco.abrir_execucao(con, "painel", None, DIA)
    envio.enviar_dia(con, [_res(pid, "ok")], DIA, ex)
    envio.enviar_dia(con, [_res(pid, "ok")], DIA)
    assert [e["execucao_id"] for e in con.execute("SELECT execucao_id FROM envio ORDER BY id")] == [ex, None]
    assert len(banco.envios_da_execucao(con, ex)) == 1
