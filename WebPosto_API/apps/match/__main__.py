"""Entrada do Logos Match: `python -m apps.match`."""
from __future__ import annotations

import asyncio
import ctypes
import logging
import logging.handlers
import os
import socket
import threading
import webbrowser
from datetime import datetime, timezone

import uvicorn

from apps.match import NOME, acesso, agendador, banco, bandeja, caminhos, rotina
from apps.match.canais import toast
from apps.match.painel import criar_app
from src.modules.cash_reconciliation.domain.tempo import FUSO

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
_ERROR_ALREADY_EXISTS = 183
_mutex = None  # mantém o handle vivo durante o processo


def configurar_log() -> None:
    h = logging.handlers.RotatingFileHandler(
        caminhos.logs() / "match.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(h)


def instancia_unica() -> bool:
    """True se esta é a primeira instância (mutex nomeado do Windows)."""
    global _mutex
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = k32.CreateMutexW(None, False, r"Global\LogosMatch")
    return k32.GetLastError() != _ERROR_ALREADY_EXISTS


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def gravar_porta(porta: int) -> None:
    (caminhos.raiz() / "porta.txt").write_text(str(porta), encoding="utf-8")


def url_painel(porta: int) -> str:
    return f"http://{HOST}:{porta}/"


def subir_servidor(app, porta: int) -> threading.Thread:
    servidor = uvicorn.Server(uvicorn.Config(app, host=HOST, port=porta, log_config=None))
    t = threading.Thread(target=servidor.run, daemon=True, name="painel")
    t.servidor = servidor
    t.start()
    return t


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
        return
    webbrowser.open(url_painel(porta))


def main() -> int:
    os.environ.setdefault("LOGOS_NAVEGADOR_CANAL", "msedge")
    configurar_log()
    if not instancia_unica():
        _abrir_instancia_viva()
        return 0
    porta = porta_livre()
    gravar_porta(porta)
    sched = agendador.iniciar(banco.conectar)
    subir_servidor(criar_app(banco.conectar, sched), porta)
    logger.info("Logos Match iniciado")
    try:
        bandeja.rodar(lambda: webbrowser.open(url_painel(porta)), dica,
                      _em_thread(False), _em_thread(True), lambda: sched.shutdown(wait=False))
    finally:
        (caminhos.raiz() / "porta.txt").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
