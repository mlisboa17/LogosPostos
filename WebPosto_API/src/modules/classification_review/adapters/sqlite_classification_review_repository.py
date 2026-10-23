"""Repositório SQLite para persistência e auditoria da Fila de Revisão e Aprendizagem."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from ...master_data.adapters.migrations.migration_002_fila_revisao_classificacao import migrar as migrar_002
from ..domain.models import (
    DadoEssencialAusenteErro,
    EstadoRevisao,
    ExemploConfirmado,
    HistoricoRevisao,
    ItemFilaRevisao,
    MetricasAcertoIA,
    RegraCandidata,
    RevisaoConcorrenteErro,
    StatusRegraCandidata,
    TRANSICOES_VALIDAS,
    TransicaoInvalidaErro,
    agora_utc,
    calcular_hash_idempotencia,
    sanitizar_evidencia,
)

logger = logging.getLogger(__name__)

DEFAULT_MASTER_DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "master_data"
DEFAULT_MASTER_DATA_DB = DEFAULT_MASTER_DATA_DIR / "master_data.sqlite3"


class SqliteClassificationReviewRepository:
    """Implementação SQLite ACID da Fila de Revisão de Classificação."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_MASTER_DATA_DB
        self._inicializar_banco()

    def _conectar(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conexao = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            isolation_level=None,  # Controle manual via BEGIN IMMEDIATE
        )
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA journal_mode=WAL;")
        conexao.execute("PRAGMA foreign_keys=ON;")
        conexao.execute("PRAGMA busy_timeout=5000;")
        return conexao

    @contextmanager
    def _transacao(self) -> Generator[sqlite3.Connection, None, None]:
        conexao = self._conectar()
        try:
            conexao.execute("BEGIN IMMEDIATE;")
            yield conexao
            conexao.execute("COMMIT;")
        except Exception:
            try:
                conexao.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        finally:
            conexao.close()

    def _inicializar_banco(self) -> None:
        """Aplica migrações necessárias no banco SQLite."""
        with self._transacao() as conn:
            migrar_002(conn)

    def _row_to_item(self, row: sqlite3.Row) -> ItemFilaRevisao:
        travas = json.loads(row["travas_encontradas"]) if row["travas_encontradas"] else []
        return ItemFilaRevisao(
            id=row["id"],
            hash_idempotencia=row["hash_idempotencia"],
            empresa_codigo=row["empresa_codigo"],
            conta_financeira_codigo=row["conta_financeira_codigo"],
            data_movimento=row["data_movimento"],
            valor=Decimal(str(row["valor"])),
            descricao=row["descricao"],
            referencia_evidencias=row["referencia_evidencias"],
            sugestao_plano_codigo=row["sugestao_plano_codigo"],
            sugestao_plano_descricao=row["sugestao_plano_descricao"],
            confianca_ia=float(row["confianca_ia"] or 0.0),
            justificativa_ia=row["justificativa_ia"],
            travas_encontradas=travas,
            status=EstadoRevisao(row["status"]),
            decisao_humana=row["decisao_humana"],
            plano_definitivo_codigo=row["plano_definitivo_codigo"],
            plano_definitivo_descricao=row["plano_definitivo_descricao"],
            centro_custo_definitivo_codigo=row["centro_custo_definitivo_codigo"],
            revisor=row["revisor"],
            revisado_em=row["revisado_em"],
            versao=row["versao"],
            criado_em=row["criado_em"],
            atualizado_em=row["atualizado_em"],
        )

    # -------------------------------------------------------------
    # OPERAÇÕES DE REGISTRO E CONSULTA
    # -------------------------------------------------------------

    def registrar_pendencia(
        self, item: ItemFilaRevisao, acao_origem: str = "CRIACAO"
    ) -> Tuple[ItemFilaRevisao, bool]:
        """Registra uma pendência na fila de forma estritamente idempotente.

        Retorna (item_persistido, inserido_novo).
        """
        # Sanitizar referências de evidências antes de persistir
        ref_sanitizada = sanitizar_evidencia(item.referencia_evidencias)

        with self._transacao() as conn:
            # 1. Checagem de idempotência
            cursor = conn.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE hash_idempotencia = ?",
                (item.hash_idempotencia,),
            )
            existente = cursor.fetchone()
            if existente:
                return self._row_to_item(existente), False

            # 2. Inserção
            agora = agora_utc().isoformat()
            travas_json = json.dumps(item.travas_encontradas, ensure_ascii=False)
            cursor = conn.execute(
                """
                INSERT INTO fila_revisao_classificacao (
                    hash_idempotencia, empresa_codigo, conta_financeira_codigo,
                    data_movimento, valor, descricao, referencia_evidencias,
                    sugestao_plano_codigo, sugestao_plano_descricao,
                    confianca_ia, justificativa_ia, travas_encontradas,
                    status, versao, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?);
                """,
                (
                    item.hash_idempotencia,
                    item.empresa_codigo,
                    item.conta_financeira_codigo,
                    item.data_movimento,
                    str(item.valor),
                    item.descricao,
                    ref_sanitizada,
                    item.sugestao_plano_codigo,
                    item.sugestao_plano_descricao,
                    item.confianca_ia,
                    item.justificativa_ia,
                    travas_json,
                    item.status.value,
                    agora,
                    agora,
                ),
            )
            novo_id = cursor.lastrowid

            # 3. Trilha de auditoria append-only
            conn.execute(
                """
                INSERT INTO fila_revisao_historico (
                    pendencia_id, acao, status_anterior, status_novo,
                    usuario_ou_sistema, justificativa, detalhes_json, timestamp
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?);
                """,
                (
                    novo_id,
                    acao_origem,
                    item.status.value,
                    "sistema",
                    item.justificativa_ia or "Entrada na fila de revisão",
                    json.dumps(
                        {
                            "confianca_ia": item.confianca_ia,
                            "sugestao_plano": item.sugestao_plano_codigo,
                            "travas": item.travas_encontradas,
                        },
                        ensure_ascii=False,
                    ),
                    agora,
                ),
            )

            # 4. Ler registro gravado
            gravado = conn.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE id = ?", (novo_id,)
            ).fetchone()
            return self._row_to_item(gravado), True

    def obter_pendencia(self, pendencia_id: int) -> Optional[ItemFilaRevisao]:
        conexao = self._conectar()
        try:
            row = conexao.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE id = ?", (pendencia_id,)
            ).fetchone()
            return self._row_to_item(row) if row else None
        finally:
            conexao.close()

    def obter_por_hash(self, hash_idempotencia: str) -> Optional[ItemFilaRevisao]:
        conexao = self._conectar()
        try:
            row = conexao.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE hash_idempotencia = ?",
                (hash_idempotencia,),
            ).fetchone()
            return self._row_to_item(row) if row else None
        finally:
            conexao.close()

    def listar_pendencias(
        self,
        status: Optional[EstadoRevisao] = None,
        empresa_codigo: Optional[int] = None,
    ) -> List[ItemFilaRevisao]:
        conexao = self._conectar()
        try:
            query = "SELECT * FROM fila_revisao_classificacao WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status.value)
            if empresa_codigo:
                query += " AND empresa_codigo = ?"
                params.append(empresa_codigo)
            query += " ORDER BY id DESC"
            rows = conexao.execute(query, params).fetchall()
            return [self._row_to_item(r) for r in rows]
        finally:
            conexao.close()

    # -------------------------------------------------------------
    # REVISÃO HUMANA E APRENDIZAGEM (CONTROLE CONCORRENTE)
    # -------------------------------------------------------------

    def revisar_classificacao(
        self,
        pendencia_id: int,
        versao_esperada: int,
        decisao_humana: str,
        plano_definitivo_codigo: int,
        plano_definitivo_descricao: str,
        revisor: str,
        centro_custo_definitivo_codigo: Optional[int] = None,
        justificativa: Optional[str] = None,
    ) -> ItemFilaRevisao:
        """Aplica revisão humana com lock pessimista e controle de versão otimista."""
        with self._transacao() as conn:
            row = conn.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE id = ?", (pendencia_id,)
            ).fetchone()
            if not row:
                raise RevisaoConcorrenteErro(f"Pendência ID {pendencia_id} não encontrada.")

            status_atual = EstadoRevisao(row["status"])
            versao_atual = row["versao"]

            if versao_atual != versao_esperada:
                raise RevisaoConcorrenteErro(
                    f"Conflito de concorrência: versão esperada {versao_esperada}, mas atual é {versao_atual}."
                )

            if EstadoRevisao.CLASSIFICADO not in TRANSICOES_VALIDAS.get(status_atual, set()):
                raise TransicaoInvalidaErro(
                    f"Transição inválida de {status_atual.value} para {EstadoRevisao.CLASSIFICADO.value}."
                )

            agora = agora_utc().isoformat()
            nova_versao = versao_atual + 1

            # Atualizar item da fila
            conn.execute(
                """
                UPDATE fila_revisao_classificacao SET
                    status = ?,
                    decisao_humana = ?,
                    plano_definitivo_codigo = ?,
                    plano_definitivo_descricao = ?,
                    centro_custo_definitivo_codigo = ?,
                    revisor = ?,
                    revisado_em = ?,
                    versao = ?,
                    atualizado_em = ?
                WHERE id = ? AND versao = ?;
                """,
                (
                    EstadoRevisao.CLASSIFICADO.value,
                    decisao_humana,
                    plano_definitivo_codigo,
                    plano_definitivo_descricao,
                    centro_custo_definitivo_codigo,
                    revisor,
                    agora,
                    nova_versao,
                    agora,
                    pendencia_id,
                    versao_esperada,
                ),
            )

            # Histórico imutável append-only
            conn.execute(
                """
                INSERT INTO fila_revisao_historico (
                    pendencia_id, acao, status_anterior, status_novo,
                    usuario_ou_sistema, justificativa, detalhes_json, timestamp
                ) VALUES (?, 'REVISAO_HUMANA', ?, ?, ?, ?, ?, ?);
                """,
                (
                    pendencia_id,
                    status_atual.value,
                    EstadoRevisao.CLASSIFICADO.value,
                    revisor,
                    justificativa or "Classificação manual confirmada por humano",
                    json.dumps(
                        {
                            "plano_definitivo_codigo": plano_definitivo_codigo,
                            "plano_definitivo_descricao": plano_definitivo_descricao,
                            "centro_custo_codigo": centro_custo_definitivo_codigo,
                        },
                        ensure_ascii=False,
                    ),
                    agora,
                ),
            )

            # Aprendizado: correção humana vira exemplo confirmado, não regra automática
            desc_norm = " ".join(row["descricao"].strip().upper().split())
            hash_exemplo = hashlib.sha256(
                f"{row['empresa_codigo']}|{desc_norm}|{plano_definitivo_codigo}".encode()
            ).hexdigest()

            conn.execute(
                """
                INSERT OR IGNORE INTO classificacao_exemplos_confirmados (
                    pendencia_id, empresa_codigo, descricao_padronizada,
                    valor, plano_conta_codigo, plano_conta_descricao,
                    revisor, confirmado_em, hash_exemplo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    pendencia_id,
                    row["empresa_codigo"],
                    desc_norm,
                    str(row["valor"]),
                    plano_definitivo_codigo,
                    plano_definitivo_descricao,
                    revisor,
                    agora,
                    hash_exemplo,
                ),
            )

            # Atualizar ou registrar regra candidata (sem promoção automática)
            regra_existente = conn.execute(
                """
                SELECT id, total_casos_confirmados FROM classificacao_regras_candidatas
                WHERE padrao_descricao = ? AND plano_conta_sugerido = ?
                """,
                (desc_norm, plano_definitivo_codigo),
            ).fetchone()

            if regra_existente:
                conn.execute(
                    """
                    UPDATE classificacao_regras_candidatas SET
                        total_casos_confirmados = total_casos_confirmados + 1,
                        atualizado_em = ?
                    WHERE id = ?;
                    """,
                    (agora, regra_existente["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO classificacao_regras_candidatas (
                        padrao_descricao, empresa_codigo, plano_conta_sugerido,
                        total_casos_confirmados, casos_minimos_promocao,
                        status_regra, criado_em, atualizado_em
                    ) VALUES (?, ?, ?, 1, 3, 'CANDIDATA', ?, ?);
                    """,
                    (desc_norm, row["empresa_codigo"], plano_definitivo_codigo, agora, agora),
                )

            atualizado = conn.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE id = ?", (pendencia_id,)
            ).fetchone()
            return self._row_to_item(atualizado)

    def bloquear_pendencia(
        self,
        pendencia_id: int,
        versao_esperada: int,
        travas: list[str],
        motivo: str,
        autor: str = "sistema",
    ) -> ItemFilaRevisao:
        """Bloqueia a pendência devido a travas encontradas ou inconsistência."""
        with self._transacao() as conn:
            row = conn.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE id = ?", (pendencia_id,)
            ).fetchone()
            if not row:
                raise RevisaoConcorrenteErro(f"Pendência ID {pendencia_id} não encontrada.")

            versao_atual = row["versao"]
            if versao_atual != versao_esperada:
                raise RevisaoConcorrenteErro(
                    f"Conflito de concorrência: esperada versão {versao_esperada}, encontrada {versao_atual}."
                )

            status_atual = EstadoRevisao(row["status"])
            if EstadoRevisao.BLOQUEADO not in TRANSICOES_VALIDAS.get(status_atual, set()):
                raise TransicaoInvalidaErro(
                    f"Transição inválida de {status_atual.value} para {EstadoRevisao.BLOQUEADO.value}."
                )

            agora = agora_utc().isoformat()
            nova_versao = versao_atual + 1
            travas_json = json.dumps(travas, ensure_ascii=False)

            conn.execute(
                """
                UPDATE fila_revisao_classificacao SET
                    status = ?,
                    travas_encontradas = ?,
                    versao = ?,
                    atualizado_em = ?
                WHERE id = ? AND versao = ?;
                """,
                (EstadoRevisao.BLOQUEADO.value, travas_json, nova_versao, agora, pendencia_id, versao_esperada),
            )

            conn.execute(
                """
                INSERT INTO fila_revisao_historico (
                    pendencia_id, acao, status_anterior, status_novo,
                    usuario_ou_sistema, justificativa, detalhes_json, timestamp
                ) VALUES (?, 'BLOQUEIO', ?, ?, ?, ?, ?, ?);
                """,
                (
                    pendencia_id,
                    status_atual.value,
                    EstadoRevisao.BLOQUEADO.value,
                    autor,
                    motivo,
                    travas_json,
                    agora,
                ),
            )

            atualizado = conn.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE id = ?", (pendencia_id,)
            ).fetchone()
            return self._row_to_item(atualizado)

    def cancelar_pendencia(
        self,
        pendencia_id: int,
        versao_esperada: int,
        motivo: str,
        autor: str,
    ) -> ItemFilaRevisao:
        """Cancela uma pendência da fila."""
        with self._transacao() as conn:
            row = conn.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE id = ?", (pendencia_id,)
            ).fetchone()
            if not row:
                raise RevisaoConcorrenteErro(f"Pendência ID {pendencia_id} não encontrada.")

            versao_atual = row["versao"]
            if versao_atual != versao_esperada:
                raise RevisaoConcorrenteErro(
                    f"Conflito de concorrência: esperada versão {versao_esperada}, encontrada {versao_atual}."
                )

            status_atual = EstadoRevisao(row["status"])
            if EstadoRevisao.CANCELADO not in TRANSICOES_VALIDAS.get(status_atual, set()):
                raise TransicaoInvalidaErro(
                    f"Transição inválida de {status_atual.value} para {EstadoRevisao.CANCELADO.value}."
                )

            agora = agora_utc().isoformat()
            nova_versao = versao_atual + 1

            conn.execute(
                """
                UPDATE fila_revisao_classificacao SET
                    status = ?,
                    versao = ?,
                    atualizado_em = ?
                WHERE id = ? AND versao = ?;
                """,
                (EstadoRevisao.CANCELADO.value, nova_versao, agora, pendencia_id, versao_esperada),
            )

            conn.execute(
                """
                INSERT INTO fila_revisao_historico (
                    pendencia_id, acao, status_anterior, status_novo,
                    usuario_ou_sistema, justificativa, detalhes_json, timestamp
                ) VALUES (?, 'CANCELAMENTO', ?, ?, ?, ?, NULL, ?);
                """,
                (pendencia_id, status_atual.value, EstadoRevisao.CANCELADO.value, autor, motivo, agora),
            )

            atualizado = conn.execute(
                "SELECT * FROM fila_revisao_classificacao WHERE id = ?", (pendencia_id,)
            ).fetchone()
            return self._row_to_item(atualizado)

    # -------------------------------------------------------------
    # GESTÃO PROGRESSIVA DE REGRAS CANDIDATAS
    # -------------------------------------------------------------

    def listar_regras_candidatas(
        self, status: Optional[StatusRegraCandidata] = None
    ) -> List[RegraCandidata]:
        conexao = self._conectar()
        try:
            query = "SELECT * FROM classificacao_regras_candidatas WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status_regra = ?"
                params.append(status.value)
            rows = conexao.execute(query, params).fetchall()
            return [
                RegraCandidata(
                    id=r["id"],
                    padrao_descricao=r["padrao_descricao"],
                    empresa_codigo=r["empresa_codigo"],
                    plano_conta_sugerido=r["plano_conta_sugerido"],
                    total_casos_confirmados=r["total_casos_confirmados"],
                    casos_minimos_promocao=r["casos_minimos_promocao"],
                    status_regra=StatusRegraCandidata(r["status_regra"]),
                    aprovado_por=r["aprovado_por"],
                    aprovado_em=r["aprovado_em"],
                    criado_em=r["criado_em"],
                    atualizado_em=r["atualizado_em"],
                )
                for r in rows
            ]
        finally:
            conexao.close()

    def promover_regra_candidata(self, regra_id: int, aprovado_por: str) -> RegraCandidata:
        """Promove regra candidata após comprovação de múltiplos casos e aprovação humana."""
        with self._transacao() as conn:
            row = conn.execute(
                "SELECT * FROM classificacao_regras_candidatas WHERE id = ?", (regra_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Regra {regra_id} não encontrada.")

            total = row["total_casos_confirmados"]
            minimo = row["casos_minimos_promocao"]
            if total < minimo:
                raise ValueError(
                    f"Regra possui {total} casos confirmados; mínimo exigido para promoção é {minimo}."
                )

            agora = agora_utc().isoformat()
            conn.execute(
                """
                UPDATE classificacao_regras_candidatas SET
                    status_regra = 'PROMOVIDA',
                    aprovado_por = ?,
                    aprovado_em = ?,
                    atualizado_em = ?
                WHERE id = ?;
                """,
                (aprovado_por, agora, agora, regra_id),
            )

            atualizado = conn.execute(
                "SELECT * FROM classificacao_regras_candidatas WHERE id = ?", (regra_id,)
            ).fetchone()
            return RegraCandidata(
                id=atualizado["id"],
                padrao_descricao=atualizado["padrao_descricao"],
                empresa_codigo=atualizado["empresa_codigo"],
                plano_conta_sugerido=atualizado["plano_conta_sugerido"],
                total_casos_confirmados=atualizado["total_casos_confirmados"],
                casos_minimos_promocao=atualizado["casos_minimos_promocao"],
                status_regra=StatusRegraCandidata(atualizado["status_regra"]),
                aprovado_por=atualizado["aprovado_por"],
                aprovado_em=atualizado["aprovado_em"],
                criado_em=atualizado["criado_em"],
                atualizado_em=atualizado["atualizado_em"],
            )

    # -------------------------------------------------------------
    # HISTÓRICO E CASOS SEMELHANTES
    # -------------------------------------------------------------

    def consultar_historico(self, pendencia_id: int) -> List[HistoricoRevisao]:
        conexao = self._conectar()
        try:
            rows = conexao.execute(
                """
                SELECT * FROM fila_revisao_historico
                WHERE pendencia_id = ?
                ORDER BY id ASC;
                """,
                (pendencia_id,),
            ).fetchall()
            return [
                HistoricoRevisao(
                    id=r["id"],
                    pendencia_id=r["pendencia_id"],
                    acao=r["acao"],
                    status_anterior=r["status_anterior"],
                    status_novo=r["status_novo"],
                    usuario_ou_sistema=r["usuario_ou_sistema"],
                    justificativa=r["justificativa"],
                    detalhes_json=r["detalhes_json"],
                    timestamp=r["timestamp"],
                )
                for r in rows
            ]
        finally:
            conexao.close()

    def recuperar_casos_semelhantes(
        self, descricao: str, empresa_codigo: Optional[int] = None, limite: int = 5
    ) -> List[ExemploConfirmado]:
        """Recupera exemplos humanos confirmados com similaridade textual."""
        conexao = self._conectar()
        try:
            tokens = [t for t in descricao.strip().upper().split() if len(t) > 2]
            if not tokens:
                return []

            clausulas = []
            params: list[Any] = []
            for token in tokens[:3]:  # até 3 termos mais relevantes
                clausulas.append("descricao_padronizada LIKE ?")
                params.append(f"%{token}%")

            where_clause = " OR ".join(clausulas)
            query = f"SELECT * FROM classificacao_exemplos_confirmados WHERE ({where_clause})"
            if empresa_codigo:
                query += " AND empresa_codigo = ?"
                params.append(empresa_codigo)

            query += f" ORDER BY id DESC LIMIT {limite}"
            rows = conexao.execute(query, params).fetchall()

            return [
                ExemploConfirmado(
                    id=r["id"],
                    pendencia_id=r["pendencia_id"],
                    empresa_codigo=r["empresa_codigo"],
                    descricao_padronizada=r["descricao_padronizada"],
                    valor=Decimal(str(r["valor"])) if r["valor"] else None,
                    plano_conta_codigo=r["plano_conta_codigo"],
                    plano_conta_descricao=r["plano_conta_descricao"],
                    revisor=r["revisor"],
                    confirmado_em=r["confirmado_em"],
                    hash_exemplo=r["hash_exemplo"],
                )
                for r in rows
            ]
        finally:
            conexao.close()

    # -------------------------------------------------------------
    # MÉTRICAS DE ACERTO DA IA
    # -------------------------------------------------------------

    def gerar_metricas_ia(self) -> MetricasAcertoIA:
        conexao = self._conectar()
        try:
            # Contagens de status
            total_pendentes = conexao.execute(
                "SELECT COUNT(*) FROM fila_revisao_classificacao WHERE status = 'PENDENTE_REVISAO'"
            ).fetchone()[0]
            total_bloqueados = conexao.execute(
                "SELECT COUNT(*) FROM fila_revisao_classificacao WHERE status = 'BLOQUEADO'"
            ).fetchone()[0]
            total_classificados = conexao.execute(
                "SELECT COUNT(*) FROM fila_revisao_classificacao WHERE status = 'CLASSIFICADO'"
            ).fetchone()[0]
            total_cancelados = conexao.execute(
                "SELECT COUNT(*) FROM fila_revisao_classificacao WHERE status = 'CANCELADO'"
            ).fetchone()[0]

            # Casos avaliados (classificados com sugestão de IA preenchida)
            avaliados_rows = conexao.execute(
                """
                SELECT sugestao_plano_codigo, plano_definitivo_codigo
                FROM fila_revisao_classificacao
                WHERE status = 'CLASSIFICADO' AND sugestao_plano_codigo IS NOT NULL;
                """
            ).fetchall()

            total_avaliados = len(avaliados_rows)
            acertos_ia = sum(
                1 for r in avaliados_rows if r["sugestao_plano_codigo"] == r["plano_definitivo_codigo"]
            )
            taxa_acerto = (acertos_ia / total_avaliados * 100.0) if total_avaliados > 0 else 0.0

            return MetricasAcertoIA(
                total_avaliados=total_avaliados,
                acertos_ia=acertos_ia,
                taxa_acerto_ia=round(taxa_acerto, 2),
                total_pendentes=total_pendentes,
                total_bloqueados=total_bloqueados,
                total_classificados=total_classificados,
                total_cancelados=total_cancelados,
            )
        finally:
            conexao.close()
