"""Notificação do Windows (windows-toasts). Falha só é registrada no log."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def avisar(titulo: str, texto: str) -> None:
    try:
        from windows_toasts import Toast, WindowsToaster

        toaster = WindowsToaster("Logos Match")
        toast = Toast()
        toast.text_fields = [titulo, texto]
        toaster.show_toast(toast)
    except Exception as exc:  # noqa: BLE001 - aviso é opcional
        logger.warning("Notificação do Windows falhou (%s)", type(exc).__name__)
