"""Monta o resumo do dia e envia por todos os canais ativos."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date

from apps.match import banco, relatorio_xlsx
from apps.match.canais import CanalErro, email_smtp, erro_envio_pt, telegram, toast

logger = logging.getLogger(__name__)

_ICONE = {"ok": "✅", "sem_movimento": "⚠️", "sem_comparacao": "⚠️",
          "erro": "❌", "verificacao_humana": "❌"}
_NOME_FONTE = {"premmia": "Premmia", "pagbank_edi": "PagBank"}
_MAX_DIVERGENCIAS = 10


def texto_resumo(resultados, posto, dia: date) -> str:
    nome = posto["apelido"] or posto["nome"]
    linhas = [f"Logos Match — {nome} — {dia:%d/%m/%Y}"]
    divergencias = []
    for r in resultados:
        fonte = _NOME_FONTE.get(r.fonte, r.fonte)
        linhas.append(f"{_ICONE.get(r.situacao, '⚠️')} {fonte}: {r.mensagem}")
        divergencias.extend(r.divergencias)
    for d in divergencias[:_MAX_DIVERGENCIAS]:
        linhas.append(f"• {d.get('explicacao_pt', '')}")
    resto = len(divergencias) - _MAX_DIVERGENCIAS
    if resto > 0:
        linhas.append(f"e mais {resto} na planilha")
    return "\n".join(linhas)


def _atende(canal, posto_id: int) -> bool:
    postos = json.loads(canal["config_json"]).get("postos") or []
    return not postos or posto_id in postos


def _despachar(canal, assunto: str, texto: str, anexo) -> None:
    if canal["tipo"] == "telegram":
        telegram.enviar(canal, texto, anexo)
    elif canal["tipo"] == "email":
        email_smtp.enviar(canal, assunto, texto, anexo)
    elif canal["tipo"] == "toast":
        toast.avisar(assunto, texto)
    else:
        raise CanalErro("Tipo de canal desconhecido.")


def enviar_dia(con, resultados, dia: date, execucao_id: int | None = None) -> None:
    por_posto = defaultdict(list)
    for r in resultados:
        por_posto[r.posto_id].append(r)
    canais = con.execute("SELECT * FROM canal WHERE ativo=1 ORDER BY id").fetchall()
    if not canais:
        return
    for posto_id, itens in por_posto.items():
        posto = con.execute("SELECT * FROM posto WHERE id=?", (posto_id,)).fetchone()
        if posto is None:
            continue
        texto = texto_resumo(itens, posto, dia)
        assunto = texto.splitlines()[0]
        try:
            anexo = relatorio_xlsx.gerar(con, posto_id, dia)
        except Exception as exc:  # noqa: BLE001 - segue só com o texto
            logger.warning("Planilha do posto %s falhou (%s)", posto_id, type(exc).__name__)
            anexo = None
        for canal in canais:
            try:
                if not _atende(canal, posto_id):
                    continue
                _despachar(canal, assunto, texto, anexo)
                banco.registrar_envio(con, canal["id"], dia, "ok", None, execucao_id)
            except Exception as exc:  # noqa: BLE001 - um canal não derruba os outros
                logger.warning("Envio pelo canal %s falhou (%s)", canal["id"], type(exc).__name__)
                banco.registrar_envio(con, canal["id"], dia, "erro", erro_envio_pt(exc),
                                      execucao_id)


def testar_canal(con, canal_id: int) -> str:
    canal = con.execute("SELECT * FROM canal WHERE id=?", (canal_id,)).fetchone()
    if canal is None:
        return "Canal não encontrado."
    try:
        _despachar(canal, "Teste do Logos Match", "Teste do Logos Match", None)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return erro_envio_pt(exc)
