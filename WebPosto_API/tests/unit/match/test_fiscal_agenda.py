from datetime import datetime

from apps.match import agendador, banco
from src.modules.cash_reconciliation.domain.tempo import FUSO


def _campos(job):
    return {f.name: str(f) for f in job.trigger.fields}


def test_jobs_fiscais(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    fabrica = lambda: banco.conectar(tmp_path / "a.db")
    monkeypatch.setattr(agendador, "agora", lambda: datetime(2026, 11, 5, 5, 0, tzinfo=FUSO))
    sched = agendador.iniciar(fabrica, pausado=True)
    try:
        jobs = {j.id: j for j in sched.get_jobs()}
        assert {"fiscal_captura", "fiscal_pendentes", "fiscal_mensal"} <= set(jobs)
        assert (_campos(jobs["fiscal_captura"])["hour"], _campos(jobs["fiscal_captura"])["minute"]) == ("7", "0")
        assert (_campos(jobs["fiscal_pendentes"])["hour"], _campos(jobs["fiscal_pendentes"])["minute"]) == ("8-20", "30")
        assert (_campos(jobs["fiscal_mensal"])["hour"], _campos(jobs["fiscal_mensal"])["minute"]) == ("8", "0")
        assert "fiscal_mensal_recuperacao" not in jobs
    finally:
        sched.shutdown(wait=False)


def test_recupera_mensal_se_subir_depois_das_8(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    fabrica = lambda: banco.conectar(tmp_path / "a.db")
    monkeypatch.setattr(agendador, "agora", lambda: datetime(2026, 11, 5, 9, 0, tzinfo=FUSO))
    sched = agendador.iniciar(fabrica, pausado=True)
    try:
        assert "fiscal_mensal_recuperacao" in {j.id for j in sched.get_jobs()}
    finally:
        sched.shutdown(wait=False)


def test_erro_em_job_fiscal_nao_propaga(tmp_path, monkeypatch):
    from apps.match.fiscal import captura, envio_mensal

    def explode(*a, **k):
        raise RuntimeError("falhou")

    monkeypatch.setattr(captura, "capturar_todas", explode)
    monkeypatch.setattr(envio_mensal, "rodar", explode)
    fabrica = lambda: banco.conectar(tmp_path / "a.db")
    agendador._job_fiscal_captura(fabrica)
    agendador._job_fiscal_pendentes(fabrica)
    agendador._job_fiscal_mensal(fabrica)
