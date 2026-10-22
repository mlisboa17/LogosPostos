"""Envio por e-mail (SMTP com STARTTLS ou SSL)."""
from __future__ import annotations

import json
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from apps.match import credenciais
from apps.match.canais import CanalErro

_XLSX = ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def enviar(canal, assunto: str, texto: str, anexo: Path | None) -> None:
    cfg = json.loads(canal["config_json"])
    destinatarios = cfg.get("destinatarios") or []
    if isinstance(destinatarios, str):
        destinatarios = [d.strip() for d in destinatarios.replace(";", ",").split(",") if d.strip()]
    if not cfg.get("servidor") or not cfg.get("usuario") or not destinatarios:
        raise CanalErro("E-mail sem servidor, usuário ou destinatário. Confira em Canais de envio.")
    senha = credenciais.ler(f"canal/{canal['id']}/senha")
    msg = EmailMessage()
    msg["From"] = cfg["usuario"]
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg.set_content(texto)
    if anexo is not None:
        msg.add_attachment(Path(anexo).read_bytes(), maintype=_XLSX[0], subtype=_XLSX[1],
                           filename=Path(anexo).name)
    porta = int(cfg.get("porta") or 587)
    ctx = ssl.create_default_context()
    if porta == 465:
        servidor = smtplib.SMTP_SSL(cfg["servidor"], porta, timeout=30, context=ctx)
    else:
        servidor = smtplib.SMTP(cfg["servidor"], porta, timeout=30)
    with servidor as s:
        if porta != 465:
            s.starttls(context=ctx)
        if senha:
            s.login(cfg["usuario"], senha)
        s.send_message(msg)
