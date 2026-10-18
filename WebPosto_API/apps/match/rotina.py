"""Rotina diária do Logos Match: coleta, envio, repescagem, recuperação e retenção."""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time as hora_t, timedelta, timezone

from apps.match import banco, caminhos, unidades
from apps.match import coletas
from apps.match.canais import envio, toast
from src.modules.cash_reconciliation.domain.tempo import FUSO, ontem

logger = logging.getLogger(__name__)

_NOME_FONTE = {"premmia": "Premmia", "pagbank_edi": "PagBank"}
_FALHAS = ("erro", "verificacao_humana")
_MESES_RETENCAO = 13
_PADRAO_COLETA, _PADRAO_REPESCAGEM = "06:00", "10:00"


_TRAVA = threading.Lock()  # uma coleta por vez (agendador, recuperação, "Coletar agora")


def _hhmm(valor: str) -> hora_t:
    h, m = valor.split(":")
    return hora_t(int(h), int(m))


def _valido(valor, padrao: str) -> str:
    try:
        _hhmm(valor)
        return valor
    except (TypeError, ValueError, AttributeError):
        if valor:
            logger.warning("Horário inválido na configuração; usando %s.", padrao)
        return padrao


def horarios(con) -> tuple[str, str]:
    banco.id_instalacao(con)
    row = con.execute("SELECT hora_coleta, hora_repescagem FROM instalacao LIMIT 1").fetchone()
    return (_valido(row["hora_coleta"], _PADRAO_COLETA),
            _valido(row["hora_repescagem"], _PADRAO_REPESCAGEM))


def _nome_posto(con, posto_id: int) -> str:
    posto = con.execute("SELECT nome, apelido FROM posto WHERE id=?", (posto_id,)).fetchone()
    return (posto["apelido"] or posto["nome"]) if posto else f"posto {posto_id}"


def _avisar_falhas(con, resultados, dia: date, so_falhas: bool) -> None:
    for r in resultados:
        if r.situacao not in _FALHAS:
            continue
        nome_posto = _nome_posto(con, r.posto_id)
        if so_falhas:
            aviso = (f"O dia {dia:%d/%m/%Y} ficou sem coleta de "
                     f"{_NOME_FONTE.get(r.fonte, r.fonte)} no {nome_posto}.")
            r.mensagem = f"{r.mensagem} {aviso}".strip()
            toast.avisar("Logos Match — coleta pendente", aviso)
        else:
            toast.avisar(f"Logos Match — {nome_posto}", r.mensagem)


async def executar(con, *, dia: date | None = None, so_falhas: bool = False,
                   visivel: bool = False, posto_id: int | None = None):
    if not _TRAVA.acquire(blocking=False):
        logger.info("coleta já em andamento")
        return []
    try:
        dia = dia or ontem()
        unidades.ativar(con)
        if posto_id is None:
            resultados = await coletas.coletar_todos(con, dia, so_falhas=so_falhas)
        else:
            resultados = await coletas.coletar_posto(con, posto_id, dia, visivel=visivel,
                                                     so_falhas=so_falhas)
        _avisar_falhas(con, resultados, dia, so_falhas)
        if resultados:
            envio.enviar_dia(con, resultados, dia)
        return resultados
    finally:
        _TRAVA.release()


def precisa_recuperar(con, agora_: datetime) -> bool:
    agora_ = agora_.astimezone(FUSO)
    hoje = agora_.date()
    if agora_.time() < _hhmm(horarios(con)[0]):
        return False
    alvo = str(hoje - timedelta(days=1))
    for row in con.execute("SELECT iniciada_em FROM coleta WHERE dia=?", (alvo,)):
        try:
            ini = datetime.fromisoformat(row["iniciada_em"])
        except (TypeError, ValueError):
            continue
        if ini.tzinfo is None:
            ini = ini.replace(tzinfo=timezone.utc)
        if ini.astimezone(FUSO).date() == hoje:
            return False
    return True


def _menos_meses(d: date, meses: int) -> date:
    idx = d.year * 12 + (d.month - 1) - meses
    ano, mes = divmod(idx, 12)
    mes += 1
    seguinte = date(ano + (mes == 12), mes % 12 + 1, 1)
    return d.replace(year=ano, month=mes, day=min(d.day, (seguinte - timedelta(days=1)).day))


def limpar_antigos(con, hoje: date) -> None:
    limite = str(_menos_meses(hoje, _MESES_RETENCAO))
    con.execute("DELETE FROM transacao WHERE coleta_id IN (SELECT id FROM coleta WHERE dia < ?)",
                (limite,))
    for tabela in ("coleta", "divergencia", "envio"):
        con.execute(f"DELETE FROM {tabela} WHERE dia < ?", (limite,))  # noqa: S608 - nomes fixos
    con.commit()
    for arq in caminhos.planilhas().glob("Logos_*_*.xlsx"):
        try:
            dia_arq = datetime.strptime(arq.stem.rsplit("_", 1)[1], "%d-%m-%Y").date()
        except (ValueError, IndexError):
            continue
        if dia_arq < _menos_meses(hoje, _MESES_RETENCAO):
            arq.unlink(missing_ok=True)
