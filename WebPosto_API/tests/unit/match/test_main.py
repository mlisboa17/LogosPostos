import logging
import os
from unittest.mock import MagicMock

import pytest

from apps.match import __main__ as m
from apps.match import bandeja, banco, caminhos


@pytest.fixture(autouse=True)
def pasta(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _limpa_handlers():
    antes = list(logging.getLogger().handlers)
    yield
    for h in list(logging.getLogger().handlers):
        if h not in antes:
            logging.getLogger().removeHandler(h)
            h.close()


def test_url_painel():
    assert m.url_painel(8765) == "http://127.0.0.1:8765/"


def test_porta_txt_so_tem_a_porta(pasta):
    m.gravar_porta(5123)
    assert (caminhos.raiz() / "porta.txt").read_text(encoding="utf-8").strip() == "5123"


def test_porta_livre_e_inteira_valida():
    assert 1024 <= m.porta_livre() <= 65535


def test_servidor_so_em_loopback(monkeypatch):
    capturado = {}

    class _Server:
        def __init__(self, config):
            capturado["config"] = config
            self.started = True

        def run(self):
            pass

    monkeypatch.setattr(m.uvicorn, "Server", _Server)
    t = m.subir_servidor(object(), 5000)
    t.join(1)
    assert capturado["config"].host == "127.0.0.1"
    assert capturado["config"].port == 5000
    assert t.daemon


def test_segunda_instancia_nao_sobe_servidor(monkeypatch):
    (caminhos.raiz() / "porta.txt").write_text("4321", encoding="utf-8")
    monkeypatch.setattr(m, "instancia_unica", lambda: False)
    aberto = []
    monkeypatch.setattr(m.webbrowser, "open", aberto.append)
    sobe = MagicMock()
    monkeypatch.setattr(m, "subir_servidor", sobe)
    monkeypatch.setattr(m.bandeja, "rodar", sobe)
    assert m.main() == 0
    assert aberto == ["http://127.0.0.1:4321/"]
    sobe.assert_not_called()


def test_main_orquestra(monkeypatch):
    monkeypatch.setattr(m, "instancia_unica", lambda: True)
    monkeypatch.setattr(m, "porta_livre", lambda: 4999)
    monkeypatch.setattr(m, "subir_servidor", MagicMock())
    monkeypatch.setattr(m.agendador, "iniciar", MagicMock())
    monkeypatch.setattr(m, "criar_app", MagicMock())
    chamado = {}

    def _rodar(*a, **k):
        chamado["a"] = a
        chamado["porta"] = (caminhos.raiz() / "porta.txt").read_text()

    monkeypatch.setattr(m.bandeja, "rodar", _rodar)
    assert m.main() == 0
    assert chamado["porta"] == "4999"
    assert not (caminhos.raiz() / "porta.txt").exists()
    assert os.environ["LOGOS_NAVEGADOR_CANAL"]
    assert m.subir_servidor.call_args.args[1] == 4999
    assert chamado["a"]


def test_log_rotativo(pasta):
    m.configurar_log()
    h = [x for x in logging.getLogger().handlers
         if isinstance(x, logging.handlers.RotatingFileHandler)][-1]
    try:
        assert h.maxBytes == 1_000_000 and h.backupCount == 5
        assert h.baseFilename.endswith("match.log")
    finally:
        logging.getLogger().removeHandler(h)
        h.close()


def test_dica_sem_coleta_e_com_coleta():
    con = banco.conectar()
    assert m.dica(con) == "Logos Match — ainda sem coleta"
    pid = banco.inserir_posto(con, "P", None, None, 1)
    con.execute("INSERT INTO fonte(posto_id,tipo) VALUES (?,?)", (pid, "premmia"))
    con.execute("INSERT INTO coleta(fonte_id,dia,terminada_em,situacao)"
                " VALUES (1,'2026-10-17','2026-10-18T09:30:00+00:00','ok')")
    con.commit()
    assert m.dica(con) == "Logos Match — última coleta 18/10/2026 06:30"


def test_coletar_registra_acesso(monkeypatch):
    monkeypatch.setattr(m.rotina, "em_andamento", lambda: False)
    vistos = {}

    async def _exec(con, *, visivel=False, **_):
        vistos["visivel"] = visivel
        return []

    monkeypatch.setattr(m.rotina, "executar", _exec)
    m._coletar(visivel=True)
    con = banco.conectar()
    r = con.execute("SELECT usuario_id, acao, detalhe FROM log_acesso").fetchone()
    assert tuple(r) == (None, "coleta_bandeja", "visivel")
    assert vistos["visivel"] is True


def test_coletar_em_andamento_avisa(monkeypatch):
    monkeypatch.setattr(m.rotina, "em_andamento", lambda: True)
    avisos = []
    monkeypatch.setattr(m.toast, "avisar", lambda t, x: avisos.append(x))
    executar = MagicMock()
    monkeypatch.setattr(m.rotina, "executar", executar)
    m._coletar(visivel=False)
    assert avisos == ["Já existe uma coleta em andamento."]
    executar.assert_not_called()


def test_icone_existe_e_abre():
    from PIL import Image
    img = Image.open(bandeja.ICONE)
    assert img.size[0] >= 32
