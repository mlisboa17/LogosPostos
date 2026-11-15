"""Rotina diária do Logos Match: coleta, envio, repescagem, recuperação e retenção."""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date, datetime, time as hora_t, timedelta, timezone

from apps.match import banco, caminhos, unidades
from apps.match import coletas, relatorio_xlsx
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


def fechar_orfas(con) -> int:
    """Execuções que ficaram `em_andamento` por queda do app viram `falhou`."""
    cur = con.execute("UPDATE execucao SET situacao='falhou', terminada_em=?"
                      " WHERE situacao='em_andamento'", (datetime.now(timezone.utc).isoformat(),))
    con.commit()
    return cur.rowcount


def _listar_aguardando(con, execucao_id: int, posto_id: int | None) -> None:
    for posto in banco.listar_postos(con):
        if posto_id is not None and posto["id"] != posto_id:
            continue
        for fonte in banco.fontes_do_posto(con, posto["id"]):
            if fonte["ativo"] and fonte["tipo"] in coletas._FONTES:
                banco.item_execucao(con, execucao_id, posto["id"], fonte["tipo"], "aguardando")


async def executar(con, *, dia: date | None = None, so_falhas: bool = False,
                   visivel: bool = False, posto_id: int | None = None,
                   origem: str = "painel", usuario_id: int | None = None):
    if not _TRAVA.acquire(blocking=False):
        logger.info("coleta já em andamento")
        return []
    try:
        return await _executar_dia(con, dia=dia or ontem(), so_falhas=so_falhas, visivel=visivel,
                                   posto_id=posto_id, origem=origem, usuario_id=usuario_id)
    finally:
        _TRAVA.release()


MAX_DIAS_PERIODO = 31
PERIODO: dict = {}  # coleta de período em andamento (lido pela tela): posto, dia, feitos, total


async def executar_periodo(con, posto_id: int, inicio: date, fim: date, *, visivel: bool = False,
                           usuario_id: int | None = None) -> list:
    """Coleta e compara dia a dia um período passado de um posto, sem mandar avisos.
    No Premmia entra no portal uma vez só para todos os dias que faltam."""
    if fim < inicio:
        inicio, fim = fim, inicio
    fim = min(fim, ontem())
    dias = [inicio + timedelta(days=n) for n in range((fim - inicio).days + 1)][:MAX_DIAS_PERIODO]
    if not dias or not _TRAVA.acquire(blocking=False):
        return []
    posto = banco.obter_posto(con, posto_id)
    PERIODO.update(posto=(posto["apelido"] or posto["nome"]) if posto else "", dia=None, feitos=0, total=len(dias))
    try:
        unidades.ativar(con)
        await _premmia_do_periodo(con, posto_id, dias, visivel)
        resultados = []
        for dia in dias:
            PERIODO.update(dia=dia)
            resultados += await _executar_dia(con, dia=dia, so_falhas=False, visivel=visivel, posto_id=posto_id,
                                              origem="painel", usuario_id=usuario_id, avisar=False)
            PERIODO.update(feitos=PERIODO["feitos"] + 1)
        return resultados
    finally:
        PERIODO.clear()
        _TRAVA.release()


async def _premmia_do_periodo(con, posto_id: int, dias: list[date], visivel: bool) -> None:
    """Baixa de uma vez (um login) todos os dias do Premmia que faltam até o fim do período."""
    from src.modules.cash_reconciliation.adapters import premmia_portal
    fonte = next((f for f in banco.fontes_do_posto(con, posto_id) if f["tipo"] == "premmia" and f["ativo"]), None)
    posto = banco.obter_posto(con, posto_id)
    if fonte is None or posto is None or coletas.posto_com_mesmo_login(con, posto_id):
        return
    unidade = unidades.do_posto(con, posto)
    pasta = caminhos.premmia(posto_id)
    try:
        coletados = premmia_portal.dias_coletados(premmia_portal.caminho_mensal(unidade, dias[0], pasta)) | \
            premmia_portal.dias_coletados(premmia_portal.caminho_mensal(unidade, dias[-1], pasta))
        faltam = sorted(set(premmia_portal.dias_faltantes(unidade, dias[-1], pasta))
                        | {d for d in dias if d not in coletados})
        if not faltam:
            return
        if visivel:
            premmia_portal.liberar_nova_tentativa(unidade, pasta)
        await asyncio.to_thread(premmia_portal.coletar_sync, unidade, faltam, visivel=visivel, diretorio=pasta)
    except Exception as exc:  # noqa: BLE001 - cada dia registra o próprio erro na coleta seguinte
        logger.warning("Premmia do período falhou posto=%s tipo=%s", posto_id, type(exc).__name__)


async def _executar_dia(con, *, dia: date, so_falhas: bool, visivel: bool, posto_id: int | None,
                        origem: str, usuario_id: int | None, avisar: bool = True):
    """Uma execução (um dia). Quem chama segura a trava."""
    execucao_id = banco.abrir_execucao(con, origem, usuario_id, dia)
    try:
        unidades.ativar(con)
        _listar_aguardando(con, execucao_id, posto_id)

        def ao_progresso(pid: int, fonte: str, situacao: str, mensagem: str | None) -> None:
            banco.item_execucao(con, execucao_id, pid, fonte, situacao, mensagem)

        if posto_id is None:
            resultados = await coletas.coletar_todos(con, dia, so_falhas=so_falhas,
                                                     visivel=visivel, ao_progresso=ao_progresso)
        else:
            resultados = await coletas.coletar_posto(con, posto_id, dia, visivel=visivel,
                                                     so_falhas=so_falhas,
                                                     ao_progresso=ao_progresso)
        if avisar:
            _avisar_falhas(con, resultados, dia, so_falhas)
            if resultados:
                envio.enviar_dia(con, resultados, dia, execucao_id)
    except BaseException:
        banco.fechar_execucao(con, execucao_id, "falhou")
        raise
    banco.fechar_execucao(con, execucao_id, "concluida")
    return resultados


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
    con.execute("DELETE FROM execucao_item WHERE execucao_id IN"
                " (SELECT id FROM execucao WHERE dia < ?)", (limite,))
    con.execute("DELETE FROM execucao WHERE dia < ?", (limite,))
    con.commit()
    for arq in caminhos.planilhas().glob("Logos_*_*.xlsx"):
        m = relatorio_xlsx.PADRAO_ARQUIVO.match(arq.name)
        if not m:
            continue
        try:
            dia_arq = datetime.strptime(m.group(1)[-10:], "%d-%m-%Y").date()
        except ValueError:
            continue
        if dia_arq < _menos_meses(hoje, _MESES_RETENCAO):
            arq.unlink(missing_ok=True)


def em_andamento() -> bool:
    return _TRAVA.locked()
