"""Detecção, reconhecimento, deduplicação e arquivamento de arquivos OFX."""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from apps.match import caminhos, relatorio_xlsx
from apps.match.extratos import repositorio
from src.modules.cash_reconciliation.adapters.extrato_reader import (
    ExtratoBancario,
    LancamentoBancario,
    ler_ofx,
    validar_cabecalho_ofx,
)

logger = logging.getLogger(__name__)
MOTIVO_OFX_INVALIDO = "Arquivo não é um extrato OFX válido."


@dataclass(frozen=True)
class ResultadoArquivo:
    nome: str
    situacao: str
    novas_linhas: int
    mensagem: str


def _caminho_unico(destino: Path) -> Path:
    if not destino.exists():
        return destino
    versao = 2
    while True:
        candidato = destino.with_name(f"{destino.stem}_{versao}{destino.suffix}")
        if not candidato.exists():
            return candidato
        versao += 1


def _estavel(caminho: Path) -> bool:
    try:
        tamanho_inicial = caminho.stat().st_size
        time.sleep(1)
        return caminho.stat().st_size == tamanho_inicial
    except PermissionError:
        return False


def _mover(origem: Path, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino = _caminho_unico(destino)
    shutil.move(str(origem), str(destino))
    return destino


def _fitid_explicito(conteudo: bytes, fitid: str) -> bool:
    """O leitor usa TRN_n internamente quando a tag FITID não veio no arquivo."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252")
    return re.search(rf"<FITID>\s*{re.escape(fitid)}\s*(?:<|$)", texto, re.IGNORECASE) is not None


def _linha(
    lancamento: LancamentoBancario, conteudo: bytes, indice: int
) -> tuple[str, str | None, str | None]:
    fitid = lancamento.fitid.strip()
    sintetico = fitid == f"TRN_{indice}" and not _fitid_explicito(conteudo, fitid)
    documento = lancamento.documento
    if sintetico:
        fitid = ""
        if documento == lancamento.fitid:
            documento = None
    if fitid:
        return fitid, fitid, documento
    partes = (
        lancamento.data.isoformat(),
        format(lancamento.valor, "f"),
        lancamento.descricao,
        documento or "",
    )
    chave = "h:" + hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()
    return chave, None, documento


def _inserir_linhas(con, conta_id: int, arquivo_id: int, extrato: ExtratoBancario,
                    conteudo: bytes) -> int:
    novas = 0
    ocorrencias: dict[str, int] = {}
    for indice, lancamento in enumerate(extrato.lancamentos, 1):
        chave, fitid, documento = _linha(lancamento, conteudo, indice)
        if not fitid:
            ocorrencias[chave] = ocorrencias.get(chave, 0) + 1
            # A primeira ocorrência mantém a chave dos extratos já arquivados.
            if ocorrencias[chave] > 1:
                chave = f"{chave}:{ocorrencias[chave]}"
        cur = con.execute(
            """INSERT INTO extrato_linha
               (conta_bancaria_id, arquivo_id, chave, fitid, data, valor, tipo,
                descricao, documento, categoria)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(conta_bancaria_id, chave) DO NOTHING""",
            (conta_id, arquivo_id, chave, fitid, lancamento.data.isoformat(),
             format(lancamento.valor, "f"), lancamento.tipo, lancamento.descricao,
             documento, lancamento.categoria),
        )
        novas += cur.rowcount
    return novas


def _destino_posto(con, conta, fim, recebido_em: datetime, nome: str) -> Path:
    posto = con.execute("SELECT id, apelido FROM posto WHERE id=?", (conta["posto_id"],)).fetchone()
    apelido = relatorio_xlsx.nome_seguro(posto["apelido"], posto["id"])
    conta_pasta = relatorio_xlsx.nome_seguro(
        f"{conta['banco']}-{conta['conta_sufixo']}", posto["id"]
    )
    return (caminhos.extratos(con) / apelido / conta_pasta / fim.strftime("%Y-%m")
            / f"{recebido_em:%Y%m%d-%H%M}_{nome}")


def _registrar_invalido(con, arquivo: Path, conteudo: bytes, recebido_em: datetime) -> ResultadoArquivo:
    sha = hashlib.sha256(conteudo).hexdigest()
    con.execute(
        """INSERT INTO extrato_arquivo
           (sha256, nome_original, recebido_em, situacao, motivo)
           VALUES (?,?,?,?,?)""",
        (sha, arquivo.name, recebido_em.isoformat(), "recusado", MOTIVO_OFX_INVALIDO),
    )
    caminho = _mover(arquivo, caminhos.extratos(con) / "Recusados" / arquivo.name)
    con.execute("UPDATE extrato_arquivo SET caminho_arquivado=? WHERE sha256=?", (str(caminho), sha))
    con.commit()
    return ResultadoArquivo(arquivo.name, "recusado", 0, MOTIVO_OFX_INVALIDO)


def _processar_arquivo(con, arquivo: Path, recebido_em: datetime) -> ResultadoArquivo:
    if not _estavel(arquivo):
        return ResultadoArquivo(arquivo.name, "aguardando_gravacao", 0, "Arquivo ainda está sendo gravado.")
    conteudo = arquivo.read_bytes()
    sha = hashlib.sha256(conteudo).hexdigest()
    existente = con.execute("SELECT id FROM extrato_arquivo WHERE sha256=?", (sha,)).fetchone()
    if existente:
        _mover(arquivo, caminhos.extratos(con) / "Duplicados" / arquivo.name)
        return ResultadoArquivo(arquivo.name, "duplicado", 0, "Arquivo já recebido.")
    try:
        validar_cabecalho_ofx(conteudo)
        extrato = ler_ofx(conteudo)
        if not extrato.lancamentos:
            raise ValueError("extrato sem lançamentos")
    except Exception:
        con.rollback()
        return _registrar_invalido(con, arquivo, conteudo, recebido_em)

    conta = repositorio.conta_por_banco(con, extrato.banco, extrato.conta_sufixo)
    inicio = (extrato.inicio or min(l.data for l in extrato.lancamentos)).isoformat()
    fim_data = extrato.fim or max(l.data for l in extrato.lancamentos)
    fim = fim_data.isoformat()
    situacao = "lido" if conta else "aguardando_vinculo"
    pasta = (caminhos.extratos(con) / "Aguardando" / arquivo.name if conta is None
             else _destino_posto(con, conta, fim_data, recebido_em, arquivo.name))
    movido: Path | None = None
    try:
        cur = con.execute(
            """INSERT INTO extrato_arquivo
               (sha256, nome_original, recebido_em, banco, agencia, conta_sufixo,
                conta_bancaria_id, inicio, fim, situacao)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (sha, arquivo.name, recebido_em.isoformat(), extrato.banco, extrato.agencia,
             extrato.conta_sufixo, conta["id"] if conta else None, inicio, fim, situacao),
        )
        arquivo_id = cur.lastrowid
        novas = (_inserir_linhas(con, conta["id"], arquivo_id, extrato, conteudo) if conta else 0)
        movido = _mover(arquivo, pasta)
        con.execute("UPDATE extrato_arquivo SET caminho_arquivado=? WHERE id=?",
                    (str(movido), arquivo_id))
        con.commit()
    except Exception:
        con.rollback()
        if movido and movido.exists() and not arquivo.exists():
            _mover(movido, arquivo)
        raise
    mensagem = "Extrato reconhecido e arquivado." if conta else "Conta desconhecida; aguardando vínculo."
    return ResultadoArquivo(arquivo.name, situacao, novas, mensagem)


def processar_pasta(con, agora_: datetime) -> list[ResultadoArquivo]:
    entrada = caminhos.extratos(con) / "Entrada"
    entrada.mkdir(parents=True, exist_ok=True)
    resultados = []
    for arquivo in sorted(entrada.iterdir(), key=lambda p: p.name.casefold()):
        if not arquivo.is_file() or arquivo.suffix.casefold() != ".ofx":
            continue
        try:
            resultado = _processar_arquivo(con, arquivo, agora_)
            if resultado.situacao != "aguardando_gravacao":
                resultados.append(resultado)
        except Exception as exc:
            con.rollback()
            logger.warning("Processamento de extrato falhou tipo=%s", type(exc).__name__)
    return resultados


def vincular(con, arquivo_id: int, posto_id: int, cd_conta_webposto: int) -> int:
    selecionado = con.execute(
        """SELECT * FROM extrato_arquivo
           WHERE id=? AND situacao='aguardando_vinculo'""",
        (arquivo_id,),
    ).fetchone()
    if selecionado is None:
        raise ValueError("Extrato aguardando vínculo não encontrado.")
    if con.execute("SELECT 1 FROM posto WHERE id=?", (posto_id,)).fetchone() is None:
        raise ValueError("Posto não encontrado.")
    con.execute(
        """INSERT INTO conta_bancaria
           (posto_id, banco, agencia, conta_sufixo, cd_conta_webposto, ativo)
           VALUES (?,?,?,?,?,1)
           ON CONFLICT(banco, conta_sufixo) DO UPDATE SET
               posto_id=excluded.posto_id, agencia=excluded.agencia,
               cd_conta_webposto=excluded.cd_conta_webposto, ativo=1""",
        (posto_id, selecionado["banco"], selecionado["agencia"], selecionado["conta_sufixo"],
         cd_conta_webposto),
    )
    conta = repositorio.conta_por_banco(con, selecionado["banco"], selecionado["conta_sufixo"])
    con.commit()
    pendentes = con.execute(
        """SELECT * FROM extrato_arquivo
           WHERE situacao='aguardando_vinculo' AND banco=? AND conta_sufixo=?
           ORDER BY recebido_em, id""",
        (selecionado["banco"], selecionado["conta_sufixo"]),
    ).fetchall()
    novas = 0
    for pendente in pendentes:
        origem = Path(pendente["caminho_arquivado"])
        try:
            conteudo = origem.read_bytes()
            validar_cabecalho_ofx(conteudo)
            extrato = ler_ofx(conteudo)
            fim_data = extrato.fim or max(l.data for l in extrato.lancamentos)
            novas += _inserir_linhas(con, conta["id"], pendente["id"], extrato, conteudo)
            destino = _destino_posto(
                con, conta, fim_data, datetime.fromisoformat(pendente["recebido_em"]),
                pendente["nome_original"],
            )
            movido = _mover(origem, destino)
            con.execute(
                """UPDATE extrato_arquivo SET conta_bancaria_id=?, inicio=?, fim=?,
                   situacao='lido', caminho_arquivado=?, motivo=NULL WHERE id=?""",
                (conta["id"], (extrato.inicio or min(l.data for l in extrato.lancamentos)).isoformat(),
                 fim_data.isoformat(), str(movido), pendente["id"]),
            )
            con.commit()
        except Exception as exc:
            con.rollback()
            logger.warning("Vínculo de extrato falhou tipo=%s", type(exc).__name__)
            raise
    return novas
