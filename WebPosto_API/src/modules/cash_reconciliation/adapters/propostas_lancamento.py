"""Propostas locais da Fase 0; nunca escreve no webPosto."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..domain.acoes_recebimentos import AcaoRecebimento
from . import pendencias

DIRETORIO = Path(__file__).resolve().parents[4] / "data" / "propostas_lancamento"
logger = logging.getLogger(__name__)


def salvar_proposta(acao: AcaoRecebimento, *, diretorio: Path | None = None) -> Path:
    if acao.grupo != 2 or len(acao.id) != 64 or any(c not in "0123456789abcdef" for c in acao.id):
        raise ValueError("Proposta inválida.")
    caminho = (diretorio or DIRETORIO) / str(acao.unidade) / f"{acao.id}.json"
    temporario = None
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        anterior = json.loads(caminho.read_text(encoding="utf-8")) if caminho.is_file() else None
        dados = acao.model_dump(mode="json")
        dados["nsu"] = f"…{acao.nsu[-4:]}" if acao.nsu else None
        dados["status"] = anterior["status"] if anterior else "proposta"
        dados["historico"] = anterior["historico"] if anterior else []
        evento = pendencias.eventos_recebimentos(acao.unidade).get(acao.id)
        if evento and evento["tipo"] == "proposta":
            dados["status"] = evento["decisao"]
            if not any(h["registrado_em"] == evento["registrado_em"] for h in dados["historico"]):
                dados["historico"].append({k: evento[k] for k in ("decisao", "observacao", "usuario", "registrado_em")})
        if anterior and any(anterior.get(k) != dados[k] for k in ("valor", "de", "para", "lancamento")):
            raise pendencias.TransicaoPendenciaInvalida("Evidência da proposta mudou; exige revisão antes de sobrescrever.")
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=caminho.parent, suffix=".tmp", delete=False) as f:
            temporario = Path(f.name)
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, caminho)
        return caminho
    except (OSError, json.JSONDecodeError, KeyError):
        logger.exception("Falha ao salvar proposta unidade=%s", acao.unidade)
        raise pendencias.ErroPersistenciaPendencias("Falha ao salvar proposta de correção.") from None
    finally:
        if temporario:
            temporario.unlink(missing_ok=True)


def decidir_proposta(acao: AcaoRecebimento, decisao: str, observacao: str, usuario: str) -> None:
    if acao.grupo != 2 or decisao not in {"executada pelo gerente", "descartada"} or not observacao.strip():
        raise pendencias.TransicaoPendenciaInvalida("Decisão de proposta inválida.")
    caminho = DIRETORIO / str(acao.unidade) / f"{acao.id}.json"
    temporario = None
    try:
        with pendencias._conectar() as conexao:
            conexao.execute("BEGIN IMMEDIATE")
            evento = conexao.execute(
                "SELECT decisao FROM eventos_recebimentos WHERE unidade=? AND acao_id=? AND tipo='proposta' ORDER BY id DESC LIMIT 1",
                (acao.unidade, acao.id),
            ).fetchone()
            if evento:
                raise pendencias.TransicaoPendenciaInvalida("Proposta já decidida.")
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            if dados["status"] != "proposta":
                raise pendencias.TransicaoPendenciaInvalida("Proposta já decidida.")
            instante = pendencias.agora().isoformat()
            dados["status"] = decisao
            dados["historico"].append({"decisao": decisao, "observacao": observacao, "usuario": usuario, "registrado_em": instante})
            conexao.execute(
                "INSERT INTO eventos_recebimentos(unidade,acao_id,tipo,decisao,observacao,usuario,registrado_em) VALUES (?,?,'proposta',?,?,?,?)",
                (acao.unidade, acao.id, decisao, observacao, usuario, instante),
            )
            # O SQLite e a fonte auditavel; JSON e um espelho recuperavel.
            conexao.commit()
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=caminho.parent, delete=False) as f:
                temporario = Path(f.name)
                json.dump(dados, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporario, caminho)
    except (OSError, sqlite3.Error, json.JSONDecodeError, KeyError):
        logger.exception("Falha ao decidir proposta unidade=%s", acao.unidade)
        raise pendencias.ErroPersistenciaPendencias("Falha ao decidir proposta.") from None
    finally:
        if temporario:
            temporario.unlink(missing_ok=True)
