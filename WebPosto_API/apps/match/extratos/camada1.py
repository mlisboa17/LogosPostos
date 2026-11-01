"""Prévia, aprovação e importação segura de extratos no webPosto."""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import tempfile
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from apps.match import banco, caminhos, explicar, unidades
from apps.match.canais import envio
from apps.match.extratos import aprovacoes, autonomia, repositorio
from src.modules.cash_reconciliation.adapters.webposto_escrita_ofx import (
    BarreiraOfxErro,
    enviar_ofx_webposto,
    verificar_duplicidade_historico,
)
from src.modules.cash_reconciliation.adapters.extrato_reader import BANCOS_CONHECIDOS
from src.modules.cash_reconciliation.domain.tempo import hoje

logger = logging.getLogger(__name__)
_TRAVA_EXECUCAO = threading.Lock()
AVISO_DIAS_IGNORADOS = "Dias que o webPosto já tiver serão ignorados por ele na importação."
AVISO_DEBITO = (
    "Extrato com débitos aguardando a Quality confirmar o formato de débito do webPosto. "
    "Nada foi enviado."
)
_BANCO_ID = {
    nome: codigo for codigo, nome in BANCOS_CONHECIDOS.items()
    if len(codigo) == 3
}


def _autorizado(con: sqlite3.Connection, posto_id: int) -> tuple[bool, str]:
    posto = con.execute(
        "SELECT enviar_extratos_webposto FROM posto WHERE id=?", (posto_id,)
    ).fetchone()
    if posto is not None and posto["enviar_extratos_webposto"] == 1:
        return True, ""
    return False, "Envio de extratos ao webPosto está desligado para este posto."


def _janelas(linhas: list, data_limite: date) -> list[list]:
    agrupadas: list[list] = []
    janela: list = []
    anterior: date | None = None
    for linha in linhas:
        dia = date.fromisoformat(linha["data"])
        if dia >= data_limite:
            continue
        if janela and (dia - anterior).days > 1:
            agrupadas.append(janela)
            janela = []
        if janela and (dia - date.fromisoformat(janela[0]["data"])).days >= 7:
            agrupadas.append(janela)
            janela = []
        janela.append(linha)
        anterior = dia
    if janela:
        agrupadas.append(janela)
    return agrupadas


def _ofx(conta, linhas: list[sqlite3.Row]) -> bytes:
    banco_id = _BANCO_ID.get(conta["banco"].upper())
    if banco_id is None:
        raise ValueError("Banco do extrato não possui código OFX conhecido.")
    conta_ofx = _texto_ofx(conta["conta_sufixo"])
    transacoes = []
    for linha in linhas:
        dia = date.fromisoformat(linha["data"])
        valor = Decimal(linha["valor"])
        tipo = "CREDIT" if valor >= 0 else "DEBIT"
        fitid = _texto_ofx(linha["fitid"] or linha["chave"])
        memo = _texto_ofx(linha["descricao"] or "")
        transacoes.append(
            f"<STMTTRN><TRNTYPE>{tipo}</TRNTYPE>"
            f"<DTPOSTED>{dia:%Y%m%d}000000</DTPOSTED>"
            f"<TRNAMT>{valor:f}</TRNAMT><FITID>{fitid}</FITID>"
            f"<MEMO>{memo}</MEMO></STMTTRN>"
        )
    inicio = min(date.fromisoformat(l["data"]) for l in linhas)
    fim = max(date.fromisoformat(l["data"]) for l in linhas)
    return (
        "OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nSECURITY:NONE\n"
        "ENCODING:UTF-8\nCHARSET:NONE\nCOMPRESSION:NONE\nOLDFILEUID:NONE\n"
        "NEWFILEUID:NONE\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>"
        f"<BANKACCTFROM><BANKID>{banco_id}</BANKID><ACCTID>{conta_ofx}</ACCTID></BANKACCTFROM>"
        f"<BANKTRANLIST><DTSTART>{inicio:%Y%m%d}000000</DTSTART>"
        f"<DTEND>{fim:%Y%m%d}235959</DTEND>{''.join(transacoes)}"
        "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
    ).encode("utf-8")


def _texto_ofx(texto: str) -> str:
    return texto.translate(str.maketrans("", "", "<>&"))


def _gerar_temporario(conta, linhas: list[sqlite3.Row]) -> Path:
    conteudo = _ofx(conta, linhas)
    with tempfile.NamedTemporaryFile(suffix=".ofx", delete=False) as arquivo:
        arquivo.write(conteudo)
        return Path(arquivo.name)


def _dias_ja_enviados(posto, conta, linhas: list[sqlite3.Row]) -> set[str]:
    diretorio = caminhos.raiz() / "importacoes_ofx"
    dias: set[str] = set()
    for valor in {linha["data"] for linha in linhas}:
        dia = date.fromisoformat(valor)
        try:
            verificar_duplicidade_historico(
                diretorio,
                unidades.codigo_empresa(posto),
                conta["cd_conta_webposto"],
                dia,
                dia,
            )
        except BarreiraOfxErro:
            dias.add(valor)
    return dias


async def _chamar_writer(unidade, arquivo: Path, *, inicio: date, fim: date,
                         confirmar: bool, autorizacao: Callable[[], tuple[bool, str]]):
    return await enviar_ofx_webposto(
        unidade, arquivo, data_inicial=inicio, data_final=fim, confirmar=confirmar,
        autorizacao=autorizacao, diretorio_historico=caminhos.raiz() / "importacoes_ofx",
    )


def _executar_writer(unidade, arquivo: Path, *, inicio: date, fim: date,
                     confirmar: bool, autorizacao: Callable[[], tuple[bool, str]]):
    return asyncio.run(_chamar_writer(
        unidade, arquivo, inicio=inicio, fim=fim, confirmar=confirmar,
        autorizacao=autorizacao,
    ))


def bloqueio_previa(con: sqlite3.Connection, conta_id: int) -> str | None:
    conta = repositorio.conta_por_id(con, conta_id)
    if conta is None:
        raise ValueError("Conta bancária não encontrada.")
    if not _autorizado(con, conta["posto_id"])[0]:
        return "Envio ao webPosto desligado para este posto."
    linhas = con.execute(
        """SELECT valor FROM extrato_linha WHERE conta_bancaria_id=?
           AND importada_webposto=0 AND data<?""",
        (conta_id, hoje().isoformat()),
    ).fetchall()
    if banco.formato_debito(con) is None and _tem_debitos(linhas):
        return AVISO_DEBITO
    return None


def _tem_debitos(linhas: list) -> bool:
    return any(Decimal(linha["valor"]) < 0 for linha in linhas)


def propor_de_novo(con: sqlite3.Connection, ticket: str) -> bool:
    cur = con.execute(
        """UPDATE aprovacao SET reproposta_em=?
           WHERE ticket=? AND tipo='importar_extrato' AND situacao IN ('recusada','falhou')
           AND reproposta_em IS NULL""",
        (datetime.now(timezone.utc).isoformat(), ticket),
    )
    con.commit()
    return cur.rowcount == 1


def _aprovacao_ativa(con: sqlite3.Connection, conta_id: int):
    return con.execute(
        """SELECT * FROM aprovacao WHERE tipo='importar_extrato'
           AND conta_bancaria_id=? AND (situacao IN ('pendente','aprovada')
              OR (situacao='automatica' AND decidida_em IS NULL))
           ORDER BY id DESC LIMIT 1""",
        (conta_id,),
    ).fetchone()


def montar_previa(con: sqlite3.Connection, conta_id: int) -> dict | None:
    conta = repositorio.conta_por_id(con, conta_id)
    if conta is None:
        return None
    if not _autorizado(con, conta["posto_id"])[0]:
        return None
    existente = _aprovacao_ativa(con, conta_id)
    if existente is not None:
        if existente["situacao"] != "pendente":
            return None
        return {**json.loads(existente["resumo_json"]), "aprovacao_id": existente["id"],
                "ticket": existente["ticket"]}

    linhas = repositorio.linhas_pendentes(con, conta_id)
    janelas = _janelas(linhas, hoje())
    if not janelas:
        return None
    posto = banco.obter_posto(con, conta["posto_id"])
    if posto is None:
        return None
    periodos = []
    for janela in janelas:
        if banco.formato_debito(con) is None and _tem_debitos(janela):
            continue
        dias_ja_enviados = sorted(_dias_ja_enviados(posto, conta, janela))
        dias_ja_enviados_set = set(dias_ja_enviados)
        linhas_novas = [l for l in janela if l["data"] not in dias_ja_enviados_set]
        if not linhas_novas:
            continue
        inicio = min(date.fromisoformat(l["data"]) for l in janela)
        fim = max(date.fromisoformat(l["data"]) for l in janela)
        entradas = sum((Decimal(l["valor"]) for l in linhas_novas if Decimal(l["valor"]) > 0),
                       Decimal("0"))
        saidas = sum((abs(Decimal(l["valor"])) for l in linhas_novas
                      if Decimal(l["valor"]) < 0), Decimal("0"))
        periodos.append({
            "de": inicio.isoformat(), "ate": fim.isoformat(),
            "linhas": len(linhas_novas), "linha_ids": [l["id"] for l in linhas_novas],
            "quantidade": len(linhas_novas), "entradas": format(entradas, "f"),
            "saidas": format(saidas, "f"),
            "dias_ja_enviados": dias_ja_enviados,
        })

    if not periodos:
        return None

    automatico = autonomia.pode_automatico(
        con, autonomia.chave_importacao(conta_id), None, conta_id
    )
    resumo = {
        "conta": {
            "id": conta["id"], "banco": conta["banco"],
            "agencia": conta["agencia"], "conta_sufixo": conta["conta_sufixo"],
            "cd_conta_webposto": conta["cd_conta_webposto"],
        },
        "posto": {"id": posto["id"], "nome": posto["nome"], "apelido": posto["apelido"]},
        "periodos": periodos,
        "total_linhas": sum(p["quantidade"] for p in periodos),
        "aviso": AVISO_DIAS_IGNORADOS,
    }
    con.execute("BEGIN IMMEDIATE")
    try:
        existente = _aprovacao_ativa(con, conta_id)
        if existente is not None:
            con.rollback()
            if existente["situacao"] != "pendente":
                return None
            return {**json.loads(existente["resumo_json"]),
                    "aprovacao_id": existente["id"], "ticket": existente["ticket"]}
        criada = aprovacoes.criar(
            con, "importar_extrato", conta["posto_id"], conta_id, resumo,
            commit=False, situacao="automatica" if automatico else "pendente",
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    if automatico:
        executar(con, criada["id"])
        return None
    from apps.match.canais.telegram_aprovacoes import notificar_aprovacao

    notificar_aprovacao(con, resumo, criada["ticket"])
    return {**resumo, "aprovacao_id": criada["id"], "ticket": criada["ticket"]}


def _notificar(con: sqlite3.Connection, posto_id: int, texto: str) -> None:
    canais = con.execute("SELECT * FROM canal WHERE ativo=1 ORDER BY id").fetchall()
    for canal in canais:
        try:
            if envio._atende(canal, posto_id):
                envio._despachar(canal, "Logos Match — extrato OFX", texto, None)
        except Exception as exc:
            logger.warning("Aviso de extrato pelo canal falhou tipo=%s", type(exc).__name__)


def _falhar(con: sqlite3.Connection, aprovacao_id: int, mensagem: str) -> tuple[bool, str]:
    cur = con.execute(
        """UPDATE aprovacao SET situacao='falhou', resultado=?, decidida_em=?
           WHERE id=? AND (situacao='aprovada'
              OR (situacao='automatica' AND decidida_em IS NULL))""",
        (mensagem, datetime.now(timezone.utc).isoformat(), aprovacao_id),
    )
    con.commit()
    if not cur.rowcount:
        return False, aprovacoes.JA_RESOLVIDO
    row = con.execute(
        "SELECT posto_id, conta_bancaria_id FROM aprovacao WHERE id=?", (aprovacao_id,)
    ).fetchone()
    if row and row["conta_bancaria_id"] is not None:
        autonomia.registrar_decisao(
            con, autonomia.chave_importacao(row["conta_bancaria_id"]),
            aprovada=False, corrigida=False,
        )
    if row:
        _notificar(con, row["posto_id"], f"Falha ao importar extrato: {mensagem}")
    return False, mensagem


def executar(con: sqlite3.Connection, aprovacao_id: int) -> tuple[bool, str]:
    if not _TRAVA_EXECUCAO.acquire(blocking=False):
        return False, aprovacoes.JA_RESOLVIDO
    try:
        return _executar(con, aprovacao_id)
    finally:
        _TRAVA_EXECUCAO.release()


def _executar(con: sqlite3.Connection, aprovacao_id: int) -> tuple[bool, str]:
    aprovacao = con.execute("SELECT * FROM aprovacao WHERE id=?", (aprovacao_id,)).fetchone()
    if aprovacao is None or aprovacao["situacao"] not in ("aprovada", "automatica"):
        return False, aprovacoes.JA_RESOLVIDO
    if aprovacao["situacao"] == "automatica" and aprovacao["decidida_em"] is not None:
        return False, aprovacoes.JA_RESOLVIDO
    resumo = json.loads(aprovacao["resumo_json"])
    automatico = aprovacao["situacao"] == "automatica"
    conta = con.execute(
        "SELECT * FROM conta_bancaria WHERE id=?", (aprovacao["conta_bancaria_id"],)
    ).fetchone()
    if conta is None:
        return _falhar(con, aprovacao_id, explicar.erro_pt(ValueError()))
    unidade = unidades.do_posto(con, banco.obter_posto(con, aprovacao["posto_id"]))
    autorizacao = lambda: _autorizado(con, aprovacao["posto_id"])
    try:
        for periodo in resumo["periodos"]:
            ids = periodo["linha_ids"] if "linha_ids" in periodo else periodo["linhas"]
            if not ids:
                continue
            placeholders = ",".join("?" for _ in ids)
            linhas = con.execute(
                f"""SELECT * FROM extrato_linha WHERE conta_bancaria_id=?
                    AND id IN ({placeholders}) ORDER BY data, id""",
                (conta["id"], *ids),
            ).fetchall()
            if len(linhas) != len(ids):
                raise ValueError("Lançamentos da prévia não estão disponíveis.")
            for janela in _janelas(linhas, date.max):
                if banco.formato_debito(con) is None and _tem_debitos(janela):
                    return _falhar(con, aprovacao_id, AVISO_DEBITO)
                arquivo = _gerar_temporario(conta, janela)
                try:
                    resultado = _executar_writer(
                        unidade, arquivo,
                        inicio=min(date.fromisoformat(l["data"]) for l in janela),
                        fim=max(date.fromisoformat(l["data"]) for l in janela),
                        confirmar=True, autorizacao=autorizacao,
                    )
                finally:
                    arquivo.unlink(missing_ok=True)
                if not resultado.sucesso:
                    autorizado, motivo = autorizacao()
                    mensagem = motivo if not autorizado else explicar.erro_pt(RuntimeError())
                    return _falhar(con, aprovacao_id, mensagem)
                repositorio.marcar_importadas(con, [linha["id"] for linha in janela])
                con.commit()
    except Exception as exc:
        mensagem = explicar.erro_pt(exc)
        logger.warning("Importação de extrato falhou tipo=%s", type(exc).__name__)
        return _falhar(con, aprovacao_id, mensagem)
    mensagem = (
        "Importado automaticamente."
        if automatico
        else "Enviado ao webPosto; dias já existentes foram ignorados por ele."
    )
    con.execute(
        """UPDATE aprovacao SET situacao='executada', decidida_em=?, resultado=?
           WHERE id=? AND situacao='aprovada'""",
        (datetime.now(timezone.utc).isoformat(), mensagem, aprovacao_id),
    )
    if automatico:
        con.execute(
            """UPDATE aprovacao SET decidida_em=?, resultado=?
               WHERE id=? AND situacao='automatica' AND decidida_em IS NULL""",
            (datetime.now(timezone.utc).isoformat(), mensagem, aprovacao_id),
        )
    con.commit()
    _notificar(con, aprovacao["posto_id"], f"{mensagem}\n{AVISO_DIAS_IGNORADOS}")
    from apps.match.extratos import camada2

    for periodo in resumo["periodos"]:
        try:
            camada2.analisar(
                con, conta["id"], date.fromisoformat(periodo["de"]),
                date.fromisoformat(periodo["ate"]),
            )
        except Exception as exc:
            con.execute(
                "UPDATE aprovacao SET resultado=? WHERE id=?",
                (f"{mensagem}\nFalha na conferência financeira: {explicar.erro_pt(exc)}",
                 aprovacao_id),
            )
            con.commit()
            logger.warning("Conferência financeira após importação falhou tipo=%s",
                           type(exc).__name__)
    return True, mensagem
