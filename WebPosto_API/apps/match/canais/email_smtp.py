"""Envio por e-mail (SMTP com STARTTLS ou SSL)."""
from __future__ import annotations

import json
import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from apps.match import credenciais
from apps.match.canais import CanalErro

_XLSX = ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
# Fixo: o registro do Windows devolve tipos não padrão (ex.: application/x-zip-compressed).
_TIPOS = {".zip": "application/zip", ".pdf": "application/pdf", ".xml": "application/xml", ".xlsx": "/".join(_XLSX)}


def _destinatarios(cfg: dict) -> list[str]:
    destinatarios = cfg.get("destinatarios") or []
    if isinstance(destinatarios, str):
        destinatarios = [d.strip() for d in destinatarios.replace(";", ",").split(",") if d.strip()]
    return destinatarios


def _mensagem(cfg: dict, destinatarios: list[str], assunto: str, texto: str) -> EmailMessage:
    if not cfg.get("servidor") or not cfg.get("usuario") or not destinatarios:
        raise CanalErro("E-mail sem servidor, usuário ou destinatário. Confira em Canais de envio.")
    msg = EmailMessage()
    msg["From"] = cfg["usuario"]
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg.set_content(texto)
    return msg


def _mandar(canal, cfg: dict, msg: EmailMessage) -> None:
    senha = credenciais.ler(f"canal/{canal['id']}/senha")
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


def enviar(canal, assunto: str, texto: str, anexo: Path | None) -> None:
    cfg = json.loads(canal["config_json"])
    msg = _mensagem(cfg, _destinatarios(cfg), assunto, texto)
    if anexo is not None:
        msg.add_attachment(Path(anexo).read_bytes(), maintype=_XLSX[0], subtype=_XLSX[1],
                           filename=Path(anexo).name)
    _mandar(canal, cfg, msg)


def enviar_arquivos(canal, destinatarios: list[str], assunto: str, texto: str, anexos: list[Path]) -> None:
    """Usa o servidor do canal de e-mail, mas para outros destinatários (ex.: contabilidade)."""
    cfg = json.loads(canal["config_json"])
    msg = _mensagem(cfg, destinatarios, assunto, texto)
    for anexo in anexos:
        tipo = (_TIPOS.get(Path(anexo).suffix.lower()) or mimetypes.guess_type(Path(anexo).name)[0]
                or "application/octet-stream")
        principal, sub = tipo.split("/", 1)
        msg.add_attachment(Path(anexo).read_bytes(), maintype=principal, subtype=sub,
                           filename=Path(anexo).name)
    _mandar(canal, cfg, msg)
