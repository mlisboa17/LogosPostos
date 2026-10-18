"""Entrada do Logos Match: `python -m apps.match`."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import getpass
import importlib
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone

import uvicorn

from apps.match import NOME, acesso, agendador, banco, bandeja, caminhos, credenciais, rotina
from apps.match.canais import toast
from apps.match.painel import criar_app
from src.modules.cash_reconciliation.domain.tempo import FUSO
from src.shared.logger import silenciar_urls_http

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
MUTEX = r"Global\LogosMatch"
_ERROR_ALREADY_EXISTS = 183
_mutex = None  # mantém o handle vivo durante o processo


def configurar_log() -> None:
    h = logging.handlers.RotatingFileHandler(
        caminhos.logs() / "match.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(h)
    silenciar_urls_http()  # httpx registraria a URL com a CHAVE do webPosto em INFO


def instancia_unica() -> bool:
    """False só se já existe outra instância (mutex nomeado do Windows)."""
    global _mutex
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    ctypes.set_last_error(0)
    _mutex = k32.CreateMutexW(None, False, MUTEX)
    erro = ctypes.get_last_error()
    if not _mutex:
        logger.warning("Mutex de instância única indisponível erro=%s; seguindo sem trava", erro)
        return True
    return erro != _ERROR_ALREADY_EXISTS


def abrir_socket() -> socket.socket:
    """Reserva uma porta livre em 127.0.0.1 e a mantém ligada (sem corrida)."""
    s = socket.socket()
    s.bind((HOST, 0))
    return s


def gravar_porta(porta: int) -> None:
    (caminhos.raiz() / "porta.txt").write_text(str(porta), encoding="utf-8")


def apagar_porta() -> None:
    (caminhos.raiz() / "porta.txt").unlink(missing_ok=True)


def url_painel(porta: int) -> str:
    return f"http://{HOST}:{porta}/"


def subir_servidor(app, sock: socket.socket):
    """Sobe o Uvicorn num thread daemon usando o socket já ligado. Devolve o Server."""
    porta = sock.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(app, host=HOST, port=porta, log_config=None))
    threading.Thread(target=servidor.run, kwargs={"sockets": [sock]}, daemon=True,
                     name="painel").start()
    return servidor


def aguardar_inicio(servidor, timeout: float = 10.0) -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if servidor.started:
            return True
        time.sleep(0.05)
    return bool(servidor.started)


def porta_viva(porta: int) -> bool:
    try:
        with socket.create_connection((HOST, porta), timeout=1):
            return True
    except OSError:
        return False


def dica(con=None) -> str:
    propria = con is None
    con = con or banco.conectar()
    try:
        ultima = banco.ultima_coleta_em(con)
    finally:
        if propria:
            con.close()
    if not ultima:
        return f"{NOME} — ainda sem coleta"
    momento = datetime.fromisoformat(ultima)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return f"{NOME} — última coleta {momento.astimezone(FUSO):%d/%m/%Y %H:%M}"


def _dica_segura() -> str:
    try:
        return dica()
    except Exception as exc:  # noqa: BLE001 - tooltip nunca derruba a bandeja
        logger.warning("Dica da bandeja falhou tipo=%s", type(exc).__name__)
        return NOME


def _coletar(visivel: bool) -> None:
    if rotina.em_andamento():
        toast.avisar(NOME, "Já existe uma coleta em andamento.")
        return
    con = banco.conectar()
    try:
        acesso.registrar(con, None, "coleta_bandeja", "visivel" if visivel else "")
        asyncio.run(rotina.executar(con, visivel=visivel))
    except Exception as exc:  # noqa: BLE001 - nunca derruba a bandeja
        logger.warning("Coleta da bandeja falhou tipo=%s", type(exc).__name__)
    finally:
        con.close()


def _em_thread(visivel: bool):
    return lambda: threading.Thread(target=_coletar, args=(visivel,), daemon=True).start()


def _abrir_instancia_viva() -> None:
    try:
        porta = int((caminhos.raiz() / "porta.txt").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        porta = None
    if porta and porta_viva(porta):
        webbrowser.open(url_painel(porta))
    else:
        toast.avisar(NOME, "O Logos Match ainda está iniciando. Tente de novo em instantes.")


_CHAVES_POSTO = ("premmia/usuario", "premmia/senha", "pagbank/usuario", "pagbank/token",
                 "webposto/chave")
_CHAVES_CANAL = ("token", "senha")


def chaves_conhecidas(con) -> list[str]:
    chaves = [f"{p['id']}/{k}" for p in banco.listar_postos(con, so_ativos=False)
              for k in _CHAVES_POSTO]
    chaves += [f"canal/{c['id']}/{k}" for c in banco.listar_canais(con) for k in _CHAVES_CANAL]
    return chaves


def apagar_credenciais() -> int:
    """Remove do Credential Manager toda chave conhecida do banco. Ignora as ausentes."""
    con = banco.conectar()
    try:
        chaves = chaves_conhecidas(con)
    finally:
        con.close()
    removidas = falhas = 0
    for chave in chaves:
        try:
            if credenciais.tem(chave):
                credenciais.apagar(chave)
                removidas += 1
        except Exception as exc:  # noqa: BLE001 - segue apagando as demais
            logger.warning("Falha ao apagar credencial tipo=%s", type(exc).__name__)
            falhas += 1
    print(f"{removidas} credencial(is) removida(s) do Windows.")
    if falhas:
        print(f"{falhas} credencial(is) não puderam ser removidas.")
        return 1
    return 0


def redefinir_admin() -> int:
    nova = getpass.getpass("Nova senha do administrador: ")
    if nova != getpass.getpass("Repita a senha: "):
        print("As senhas não conferem. Nada foi alterado.")
        return 1
    con = banco.conectar()
    try:
        acesso.redefinir_admin(con, nova)
    except ValueError as exc:
        print(str(exc))
        return 1
    finally:
        con.close()
    print("Senha do administrador redefinida. Login: admin")
    return 0


# o PyInstaller pode deixar de fora: sem python_multipart todo POST do painel dá 500
_IMPORTS = ("python_multipart", "windows_toasts", "pystray", "apscheduler")


def _recursos() -> list[tuple[str, bool, str]]:
    """Recursos que o exe empacotado precisa achar. (nome, ok, detalhe)"""
    from pathlib import Path

    import keyring
    from playwright._impl._driver import compute_driver_executable

    from src.modules.cash_reconciliation import config as config_cr

    base = Path(bandeja.__file__).resolve().parent  # pasta apps/match (o __file__ do script de entrada muda no exe)
    itens = [("templates", base / "painel" / "templates"), ("static", base / "painel" / "static"),
             ("assets", base / "assets" / "icone.ico"),
             ("units.json", Path(config_cr.__file__).parent / "units.json")]
    res = [(n, p.exists(), str(p)) for n, p in itens]
    try:
        driver = [Path(x) for x in compute_driver_executable()]
        res.append(("playwright", all(d.exists() for d in driver), str(driver[0])))
    except Exception as exc:  # noqa: BLE001
        res.append(("playwright", False, type(exc).__name__))
    res.append(("keyring", True, type(keyring.get_keyring()).__name__))
    for modulo in _IMPORTS:
        try:
            importlib.import_module(modulo)
            res.append((modulo, True, "importado"))
        except Exception as exc:  # noqa: BLE001
            res.append((modulo, False, type(exc).__name__))
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("America/Recife")
        res.append(("fuso America/Recife", True, "tzdata"))
    except Exception as exc:  # noqa: BLE001
        res.append(("fuso America/Recife", False, type(exc).__name__))
    return res


def verificar() -> int:
    ok_geral = True
    for nome, ok, detalhe in _recursos():
        print(f"{'ok' if ok else 'FALHA'} {nome}: {detalhe}")
        ok_geral = ok_geral and ok
    return 0 if ok_geral else 1


def _argumentos(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="LogosMatch", description=NOME)
    p.add_argument("--apagar-credenciais", action="store_true",
                   help="remove do Windows todas as credenciais guardadas e sai")
    p.add_argument("--verificar", action="store_true",
                   help="confere se os recursos empacotados estão presentes e sai")
    p.add_argument("--redefinir-admin", action="store_true",
                   help="define uma nova senha para o administrador e sai")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv or [])
    if args.verificar:
        return verificar()
    if args.apagar_credenciais:
        return apagar_credenciais()
    if args.redefinir_admin:
        return redefinir_admin()
    os.environ.setdefault("LOGOS_NAVEGADOR_CANAL", "msedge")
    if not instancia_unica():
        _abrir_instancia_viva()
        return 0
    configurar_log()
    try:
        apagar_porta()
        sock = abrir_socket()
        porta = sock.getsockname()[1]
        sched = agendador.iniciar(banco.conectar)
        servidor = subir_servidor(criar_app(banco.conectar, sched), sock)
        if not aguardar_inicio(servidor):
            logger.warning("Servidor do painel não iniciou")
            sched.shutdown(wait=False)
            toast.avisar(NOME, "O Logos Match não conseguiu abrir o painel.")
            return 1
        gravar_porta(porta)
        logger.info("Logos Match iniciado")
        bandeja.rodar(lambda: webbrowser.open(url_painel(porta)), _dica_segura,
                      _em_thread(False), _em_thread(True), lambda: sched.shutdown(wait=False))
        return 0
    finally:
        apagar_porta()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
