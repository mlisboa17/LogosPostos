import ctypes
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime, timezone
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
    canal = os.environ.get("LOGOS_NAVEGADOR_CANAL")
    antes = list(logging.getLogger().handlers)
    yield
    if canal is None:
        os.environ.pop("LOGOS_NAVEGADOR_CANAL", None)
    for h in list(logging.getLogger().handlers):
        if h not in antes:
            logging.getLogger().removeHandler(h)
            h.close()


class _FakeSock:
    def __init__(self, porta):
        self.porta = porta

    def getsockname(self):
        return ("127.0.0.1", self.porta)


class _Srv:
    def __init__(self, ok):
        self.started = ok


def _prepara(monkeypatch, ok=True):
    monkeypatch.setattr(m, "instancia_unica", lambda: True)
    monkeypatch.setattr(m, "abrir_socket", lambda: _FakeSock(4999))
    monkeypatch.setattr(m, "subir_servidor", MagicMock(return_value=_Srv(ok)))
    monkeypatch.setattr(m, "aguardar_inicio", lambda s, timeout=10.0: s.started)
    monkeypatch.setattr(m.agendador, "iniciar", MagicMock())
    monkeypatch.setattr(m, "criar_app", MagicMock())
    avisos = []
    monkeypatch.setattr(m.toast, "avisar", lambda t, x: avisos.append(x))
    return avisos


def test_url_painel():
    assert m.url_painel(8765) == "http://127.0.0.1:8765/"


def test_porta_txt_so_tem_a_porta(pasta):
    m.gravar_porta(5123)
    assert (caminhos.raiz() / "porta.txt").read_text(encoding="utf-8").strip() == "5123"


def test_abrir_socket_em_loopback():
    s = m.abrir_socket()
    try:
        assert s.getsockname()[0] == "127.0.0.1"
        assert 1024 <= s.getsockname()[1] <= 65535
    finally:
        s.close()


def test_servidor_so_em_loopback(monkeypatch):
    capturado = {}

    class _Server:
        started = True

        def __init__(self, config):
            capturado["config"] = config

        def run(self, sockets=None):
            capturado["sockets"] = sockets

    monkeypatch.setattr(m.uvicorn, "Server", _Server)
    sock = m.abrir_socket()
    try:
        m.subir_servidor(object(), sock)
        time.sleep(0.2)
        assert capturado["config"].host == "127.0.0.1"
        assert capturado["config"].port == sock.getsockname()[1]
        assert capturado["sockets"] == [sock]
    finally:
        sock.close()


def test_segunda_instancia_viva_abre_painel(monkeypatch):
    (caminhos.raiz() / "porta.txt").write_text("4321", encoding="utf-8")
    monkeypatch.setattr(m, "instancia_unica", lambda: False)
    monkeypatch.setattr(m, "porta_viva", lambda p: True)
    aberto = []
    monkeypatch.setattr(m.webbrowser, "open", aberto.append)
    monkeypatch.setattr(m, "subir_servidor", MagicMock())
    monkeypatch.setattr(m, "criar_app", MagicMock())
    monkeypatch.setattr(m.agendador, "iniciar", MagicMock())
    monkeypatch.setattr(m.bandeja, "rodar", MagicMock())
    assert m.main() == 0
    assert aberto == ["http://127.0.0.1:4321/"]
    m.subir_servidor.assert_not_called()
    m.criar_app.assert_not_called()
    m.agendador.iniciar.assert_not_called()
    m.bandeja.rodar.assert_not_called()


@pytest.mark.parametrize("conteudo,viva", [(None, True), ("4321", False), ("lixo", True)])
def test_segunda_instancia_sem_porta_viva_avisa(monkeypatch, conteudo, viva):
    if conteudo is not None:
        (caminhos.raiz() / "porta.txt").write_text(conteudo, encoding="utf-8")
    monkeypatch.setattr(m, "instancia_unica", lambda: False)
    monkeypatch.setattr(m, "porta_viva", lambda p: viva)
    aberto = []
    monkeypatch.setattr(m.webbrowser, "open", aberto.append)
    avisos = []
    monkeypatch.setattr(m.toast, "avisar", lambda t, x: avisos.append(x))
    assert m.main() == 0
    assert aberto == []
    assert avisos == ["O Logos Match ainda está iniciando. Tente de novo em instantes."]


def test_porta_viva_real():
    s = m.abrir_socket()
    s.listen()
    porta = s.getsockname()[1]
    try:
        assert m.porta_viva(porta) is True
    finally:
        s.close()
    assert m.porta_viva(porta) is False


def test_main_orquestra_e_porta_so_apos_started(monkeypatch):
    _prepara(monkeypatch)
    (caminhos.raiz() / "porta.txt").write_text("velha", encoding="utf-8")
    existia = []
    monkeypatch.setattr(m, "aguardar_inicio",
                        lambda s, timeout=10.0: existia.append(
                            (caminhos.raiz() / "porta.txt").exists()) or True)
    chamado = {}

    def _rodar(*a, **k):
        chamado["porta"] = (caminhos.raiz() / "porta.txt").read_text()

    monkeypatch.setattr(m.bandeja, "rodar", _rodar)
    monkeypatch.delenv("LOGOS_NAVEGADOR_CANAL", raising=False)
    assert m.main() == 0
    assert existia == [False]  # porta.txt velho apagado e ainda não gravado antes do started
    assert chamado["porta"] == "4999"
    assert not (caminhos.raiz() / "porta.txt").exists()
    assert os.environ["LOGOS_NAVEGADOR_CANAL"] == "msedge"


def test_servidor_que_nao_inicia_sai_com_erro(monkeypatch):
    avisos = _prepara(monkeypatch, ok=False)
    rodar = MagicMock()
    monkeypatch.setattr(m.bandeja, "rodar", rodar)
    assert m.main() != 0
    assert avisos == ["O Logos Match não conseguiu abrir o painel."]
    assert not (caminhos.raiz() / "porta.txt").exists()
    rodar.assert_not_called()


def test_falha_na_partida_remove_porta(monkeypatch):
    _prepara(monkeypatch)
    m.agendador.iniciar.side_effect = RuntimeError("x")
    (caminhos.raiz() / "porta.txt").write_text("velha", encoding="utf-8")
    with pytest.raises(RuntimeError):
        m.main()
    assert not (caminhos.raiz() / "porta.txt").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="mutex do Windows")
def test_mutex_real(monkeypatch):
    nome = f"Global\\LogosMatchTeste{os.getpid()}"
    monkeypatch.setattr(m, "MUTEX", nome)
    assert m.instancia_unica() is True
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    ctypes.set_last_error(0)
    h = k32.CreateMutexW(None, False, nome)
    try:
        assert h
        assert ctypes.get_last_error() == 183
        assert m.instancia_unica() is False
    finally:
        k32.CloseHandle(h)
        k32.CloseHandle(m._mutex)


def test_dica_com_falha_cai_para_nome(monkeypatch):
    def _quebra(con=None):
        raise OSError("x")

    monkeypatch.setattr(m, "dica", _quebra)
    assert m._dica_segura() == "Logos Match"


def test_log_rotativo(pasta):
    m.configurar_log()
    h = [x for x in logging.getLogger().handlers
         if isinstance(x, logging.handlers.RotatingFileHandler)][-1]
    assert h.maxBytes == 1_000_000 and h.backupCount == 5
    assert h.baseFilename.endswith("match.log")


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


def test_redefinir_admin_pela_linha_de_comando(monkeypatch, capsys):
    from apps.match import acesso
    senhas = iter(["nova-senha-123", "nova-senha-123"])
    monkeypatch.setattr(m.getpass, "getpass", lambda prompt="": next(senhas))
    assert m.main(["--redefinir-admin"]) == 0
    assert "Senha do administrador redefinida. Login: admin" in capsys.readouterr().out
    con = banco.conectar()
    try:
        assert con.execute("SELECT 1 FROM usuario WHERE login='admin'").fetchone()
        assert acesso.autenticar(con, "admin", "nova-senha-123", datetime.now(timezone.utc)) is not None
    finally:
        con.close()


def test_redefinir_admin_senhas_diferentes(monkeypatch, capsys):
    senhas = iter(["nova-senha-123", "outra-senha-456"])
    monkeypatch.setattr(m.getpass, "getpass", lambda prompt="": next(senhas))
    assert m.main(["--redefinir-admin"]) == 1
    saida = capsys.readouterr().out
    assert "não conferem" in saida
    assert "nova-senha-123" not in saida


def test_redefinir_admin_senha_curta(monkeypatch, capsys):
    monkeypatch.setattr(m.getpass, "getpass", lambda prompt="": "curta")
    assert m.main(["--redefinir-admin"]) == 1
    assert "curta" not in capsys.readouterr().out


def test_apagar_credenciais_remove_todas(keyring_falso, monkeypatch, capsys):
    from apps.match import credenciais
    con = banco.conectar()
    try:
        p1 = banco.inserir_posto(con, "Posto A", "A", "1", 1)
        p2 = banco.inserir_posto(con, "Posto B", "B", "2", 2)
        con.execute("UPDATE posto SET ativo=0 WHERE id=?", (p2,))
        con.commit()
        c1 = banco.inserir_canal(con, "telegram", {})
    finally:
        con.close()
    chaves = [f"{p1}/premmia/usuario", f"{p1}/premmia/senha", f"{p1}/webposto/chave",
              f"{p2}/pagbank/usuario", f"{p2}/pagbank/token", f"canal/{c1}/token"]
    for c in chaves:
        credenciais.salvar(c, "x")
    credenciais.salvar("outra/coisa", "y")
    # mutex/servidor não podem ser tocados
    monkeypatch.setattr(m, "instancia_unica", lambda: pytest.fail("não deve tomar o mutex"))
    assert m.main(["--apagar-credenciais"]) == 0
    assert all(credenciais.ler(c) is None for c in chaves)
    assert credenciais.ler("outra/coisa") == "y"
    assert "6 credencial" in capsys.readouterr().out


def test_apagar_credenciais_falha_parcial(keyring_falso, monkeypatch, capsys):
    from apps.match import credenciais
    con = banco.conectar()
    try:
        p1 = banco.inserir_posto(con, "Posto A", "A", "1", 1)
    finally:
        con.close()
    credenciais.salvar(f"{p1}/premmia/usuario", "x")
    credenciais.salvar(f"{p1}/premmia/senha", "x")

    def apagar(chave):
        if chave.endswith("usuario"):
            raise OSError("negado")
        keyring_falso.delete_password("LogosMatch", chave)
    monkeypatch.setattr(m.credenciais, "apagar", apagar)
    assert m.main(["--apagar-credenciais"]) == 1
    saida = capsys.readouterr().out
    assert "1 credencial(is) não puderam ser removidas." in saida


def test_verificar_ok_na_arvore_de_fontes(capsys):
    assert m.main(["--verificar"]) == 0
    saida = capsys.readouterr().out
    for item in ("templates", "static", "assets", "units.json", "playwright", "keyring"):
        assert f"ok {item}" in saida


def test_verificar_falha_quando_falta_recurso(monkeypatch, capsys):
    monkeypatch.setattr(m, "_recursos", lambda: [("templates", False, "ausente")])
    assert m.main(["--verificar"]) == 1
    assert "FALHA templates" in capsys.readouterr().out


def test_requirements_match_fixado_e_com_multipart():
    import re
    from pathlib import Path
    arq = Path(m.__file__).resolve().parents[2] / "requirements-match.txt"
    linhas = [x.strip() for x in arq.read_text(encoding="utf-8").splitlines()
              if x.strip() and not x.startswith("#")]
    nomes = {x.split("==")[0].lower() for x in linhas}
    assert {"python-multipart", "tzdata", "fastapi", "keyring", "windows-toasts"} <= nomes
    assert all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][\w.]*", x) for x in linhas), linhas


def test_verificar_confere_imports_e_fuso(capsys):
    assert m.main(["--verificar"]) == 0
    saida = capsys.readouterr().out
    for item in ("python_multipart", "windows_toasts", "pystray", "keyring", "apscheduler",
                 "fuso America/Recife"):
        assert f"ok {item}" in saida, item


def test_verificar_falha_quando_import_falta(monkeypatch, capsys):
    import importlib
    original = importlib.import_module

    def falso(nome, *a, **k):
        if nome == "python_multipart":
            raise ImportError("ausente")
        return original(nome, *a, **k)

    monkeypatch.setattr(importlib, "import_module", falso)
    assert m.main(["--verificar"]) == 1
    assert "FALHA python_multipart: ImportError" in capsys.readouterr().out


def test_configurar_log_silencia_urls_do_httpx(pasta):
    for nome in ("httpx", "httpcore"):
        logging.getLogger(nome).setLevel(logging.NOTSET)
    m.configurar_log()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_readme_cita_cli_para_redefinir_admin():
    from pathlib import Path
    texto = (Path(m.__file__).resolve().parent / "README.md").read_text(encoding="utf-8")
    assert "LogosMatch.exe --redefinir-admin" not in texto
    assert "LogosMatchCLI.exe --redefinir-admin" in texto


def test_cli_liberar_postos(monkeypatch, capsys, tmp_path):
    from apps.match import registro_rede as rr
    monkeypatch.setattr(m, "instancia_unica", lambda: pytest.fail("não deve tomar o mutex"))
    con = banco.conectar()
    try:
        assert m.main(["--liberar-postos"]) == 0
        assert capsys.readouterr().out.strip() == "Pasta da rede não configurada."
        rede = tmp_path / "rede"
        rede.mkdir()
        banco.salvar_pasta_rede(con, str(rede))
        meu = banco.id_instalacao(con)
        for nome, codigo in (("A", 1), ("B", 2), ("C", 3)):
            banco.inserir_posto(con, nome, nome, None, codigo)
        rr.registrar(rede, "1", meu, "A")
        rr.registrar(rede, "2", meu, "B")
        rr.registrar(rede, "3", "OUTRA", "C")
        assert m.main(["--liberar-postos"]) == 0
        assert capsys.readouterr().out.strip() == "2 posto(s) liberado(s) na pasta da rede."
        assert rr.dono(rede, "1") is None and rr.dono(rede, "2") is None
        assert rr.dono(rede, "3").id_instalacao == "OUTRA"
        banco.salvar_pasta_rede(con, str(tmp_path / "offline"))
        assert m.main(["--liberar-postos"]) == 1
        assert capsys.readouterr().out.strip() == rr.MSG_INDISPONIVEL
    finally:
        con.close()
