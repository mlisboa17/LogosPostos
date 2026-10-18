"""Ícone da bandeja do Windows (pystray)."""
from __future__ import annotations

from pathlib import Path

import pystray
from PIL import Image

from apps.match import NOME

ICONE = Path(__file__).parent / "assets" / "icone.ico"


def rodar(abrir_painel, dica, ao_coletar, ao_coletar_visivel, ao_sair) -> None:
    """Bloqueia no thread principal até "Sair". `dica()` devolve o texto do tooltip."""
    def _sair(icone, _item):
        icone.stop()
        ao_sair()

    def _acao(fn):
        def _f(icone, _item):
            fn()
            icone.title = dica()
        return _f

    menu = pystray.Menu(
        pystray.MenuItem("Abrir painel", _acao(abrir_painel), default=True),
        pystray.MenuItem("Coletar agora", _acao(ao_coletar)),
        pystray.MenuItem("Coletar agora (visível)", _acao(ao_coletar_visivel)),
        pystray.MenuItem("Sair", _sair),
    )
    pystray.Icon(NOME, Image.open(ICONE), dica(), menu).run()
