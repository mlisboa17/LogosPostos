"""Serviço de Aplicação para a Fila Local de Revisão e Aprendizagem (EXPENSE/CLASSIFICATION).

Regras de negócio:
1. REUSE > ADAPT > CREATE: Integração total com Master Data e trilha de auditoria SQLite.
2. Isolamento absoluto: Nenhuma pendência gera escrita no ERP (ERP WRITES = ZERO).
3. Conta 198966 (2.04.10): Mantida como temporária em revisão (`candidato_lancavel=0`, `permite_despesa=0`).
4. Confiança nunca supera uma trava: Mesmo confiança 1.0 vira BLOQUEADO se houver travas.
5. Baixa confiança: Envia estritamente para PENDENTE_REVISAO local.
6. Dados essenciais ausentes, divergência ou duplicidade: Resultam imediatamente em BLOQUEADO.
7. Aprendizagem contínua: Correção humana gera Exemplo Confirmado; Regras candidatas exigem >= 3 casos e aprovação explícita.
8. Idempotência e Concorrência: Locks pessimistas e versionamento otimista impedem colisões.
9. Segurança: Sanitização preventiva contra credenciais e dados confidenciais.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, List, Optional, Tuple

from ..adapters.sqlite_classification_review_repository import SqliteClassificationReviewRepository
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
    calcular_hash_idempotencia,
    sanitizar_evidencia,
)

logger = logging.getLogger(__name__)

# Limiar de confiança para sugestões da IA
LIMIAR_ALTA_CONFIANCA_IA = 0.85

# Conta temporária oficial de saídas pendentes de classificação
CONTA_TEMPORARIA_CLASSIFICACAO = 198966


class ClassificationReviewService:
    """Orquestrador da Fila de Revisão e Aprendizagem."""

    def __init__(
        self,
        repository: Optional[SqliteClassificationReviewRepository] = None,
        master_data_service: Optional[Any] = None,
    ):
        self.repository = repository or SqliteClassificationReviewRepository()
        self.master_data_service = master_data_service

    def registrar_movimento_para_revisao(
        self,
        empresa_codigo: int,
        conta_financeira_codigo: int,
        data_movimento: str,
        valor: Decimal | str | float,
        descricao: str,
        referencia_evidencias: Optional[str] = None,
        sugestao_plano_codigo: Optional[int] = None,
        sugestao_plano_descricao: Optional[str] = None,
        confianca_ia: float = 0.0,
        justificativa_ia: Optional[str] = None,
        travas_externas: Optional[list[str]] = None,
        duplicidade_detectada: bool = False,
        divergencia_detectada: bool = False,
    ) -> Tuple[ItemFilaRevisao, bool]:
        """Avalia e registra movimentação financeira na fila local de revisão.

        Garante idempotência estrita e aplicação irrevogável das travas de integridade.
        """
        travas: list[str] = list(travas_externas or [])

        # 1. Validação de dados essenciais
        if not empresa_codigo or empresa_codigo <= 0:
            travas.append("EMPRESA_NAO_IDENTIFICADA")
        if not conta_financeira_codigo or conta_financeira_codigo <= 0:
            travas.append("CONTA_FINANCEIRA_NAO_IDENTIFICADA")
        if not data_movimento or not data_movimento.strip():
            travas.append("DATA_MOVIMENTO_AUSENTE")

        valor_decimal: Decimal
        try:
            valor_decimal = Decimal(str(valor))
            if valor_decimal <= Decimal("0.00"):
                travas.append("VALOR_INVALIDO_OU_ZERO")
        except Exception:
            valor_decimal = Decimal("0.00")
            travas.append("VALOR_FORMATO_INVALIDO")

        if not descricao or not descricao.strip():
            travas.append("DESCRICAO_AUSENTE")

        # 2. Travas de integridade e escopo
        if duplicidade_detectada:
            travas.append("DUPLICIDADE_DETECTADA")
        if divergencia_detectada:
            travas.append("DIVERGENCIA_DETECTADA")

        # Posto Real fora do escopo
        if empresa_codigo in (5558, 7):
            travas.append("POSTO_REAL_FORA_DO_ESCOPO")

        # Conta bancária sem autorização para débito (ex: 27173)
        if conta_financeira_codigo == 27173:
            travas.append("CONTA_27173_BLOQUEADA_PARA_DEBITO")

        # Conta temporária 198966 não pode ser tratada como plano liberado
        if sugestao_plano_codigo == CONTA_TEMPORARIA_CLASSIFICACAO:
            travas.append("PLANO_198966_TEMPORARIO_SEM_LANCAMENTO")

        # 3. Decisão de estado:
        # REGRA CRÍTICA: Confiança NUNCA supera uma trava!
        # Se houver travas: status é BLOQUEADO.
        # Se não houver travas:
        #   - baixa confiança (< 0.85) envia apenas para a fila local (PENDENTE_REVISAO)
        #   - alta confiança permanece em PENDENTE_REVISAO até confirmação humana (ERP WRITES = ZERO).
        if len(travas) > 0:
            status = EstadoRevisao.BLOQUEADO
        else:
            status = EstadoRevisao.PENDENTE_REVISAO

        # 4. Cálculo de hash de idempotência
        hash_idempotencia = calcular_hash_idempotencia(
            empresa_codigo=empresa_codigo,
            conta_financeira_codigo=conta_financeira_codigo,
            data_movimento=data_movimento,
            valor=valor_decimal,
            descricao=descricao,
        )

        item = ItemFilaRevisao(
            id=None,
            hash_idempotencia=hash_idempotencia,
            empresa_codigo=empresa_codigo,
            conta_financeira_codigo=conta_financeira_codigo,
            data_movimento=data_movimento.strip(),
            valor=valor_decimal,
            descricao=descricao.strip(),
            referencia_evidencias=referencia_evidencias,
            sugestao_plano_codigo=sugestao_plano_codigo,
            sugestao_plano_descricao=sugestao_plano_descricao,
            confianca_ia=confianca_ia,
            justificativa_ia=justificativa_ia,
            travas_encontradas=travas,
            status=status,
        )

        return self.repository.registrar_pendencia(item)

    def revisar_e_classificar(
        self,
        pendencia_id: int,
        versao_esperada: int,
        plano_definitivo_codigo: int,
        plano_definitivo_descricao: str,
        revisor: str,
        centro_custo_definitivo_codigo: Optional[int] = None,
        justificativa: Optional[str] = None,
    ) -> ItemFilaRevisao:
        """Aplica classificação humana definitiva na pendência.

        A conta 198966 é temporária de revisão e não pode ser definida como plano definitivo.
        """
        if plano_definitivo_codigo == CONTA_TEMPORARIA_CLASSIFICACAO:
            raise ValueError(
                "A conta 198966 é temporária de trânsito e não pode ser escolhida como plano definitivo de lançamento."
            )

        self.validar_plano_folha_candidato(plano_definitivo_codigo)

        return self.repository.revisar_classificacao(
            pendencia_id=pendencia_id,
            versao_esperada=versao_esperada,
            decisao_humana="CLASSIFICADO_HUMANO",
            plano_definitivo_codigo=plano_definitivo_codigo,
            plano_definitivo_descricao=plano_definitivo_descricao,
            centro_custo_definitivo_codigo=centro_custo_definitivo_codigo,
            revisor=revisor,
            justificativa=justificativa,
        )

    def validar_plano_folha_candidato(self, plano_conta_codigo: int) -> None:
        """Valida que o plano definitivo é folha, ativo, observado na última sincronização e candidato lançável."""
        if plano_conta_codigo == CONTA_TEMPORARIA_CLASSIFICACAO:
            raise ValueError(
                "A conta 198966 é temporária de trânsito e não pode ser escolhida como plano definitivo de lançamento."
            )
        conn = self.repository._conectar()
        try:
            tem_tabela = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='master_planos_conta'"
            ).fetchone()
            if not tem_tabela:
                return

            row = conn.execute(
                "SELECT * FROM master_planos_conta WHERE plano_conta_codigo = ?",
                (plano_conta_codigo,),
            ).fetchone()
            if not row:
                raise ValueError(f"Plano de contas {plano_conta_codigo} não encontrado no catálogo oficial.")
            if not row["ativo"]:
                raise ValueError(f"Plano de contas {plano_conta_codigo} está inativo no catálogo oficial.")
            if not row["observado_ultima_sincronizacao"]:
                raise ValueError(f"Plano de contas {plano_conta_codigo} não foi observado na última sincronização oficial.")
            if not row["eh_folha"]:
                raise ValueError(f"Plano de contas {plano_conta_codigo} é conta-pai estrutural; lançamentos exigem conta-folha.")
            if not row["candidato_lancavel"]:
                raise ValueError(f"Plano de contas {plano_conta_codigo} não é candidato lançável válido.")
        finally:
            conn.close()

    def listar_planos_folha_validos(self) -> list[dict[str, Any]]:
        """Retorna apenas planos ativos, observados, folhas e candidatos válidos (excluindo 198966)."""
        conn = self.repository._conectar()
        try:
            tem_tabela = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='master_planos_conta'"
            ).fetchone()
            if not tem_tabela:
                return []
            rows = conn.execute(
                """
                SELECT plano_conta_codigo, descricao, hierarquia, grupo, natureza
                FROM master_planos_conta
                WHERE ativo = 1
                  AND observado_ultima_sincronizacao = 1
                  AND eh_folha = 1
                  AND candidato_lancavel = 1
                  AND plano_conta_codigo != ?
                ORDER BY hierarquia, plano_conta_codigo;
                """,
                (CONTA_TEMPORARIA_CLASSIFICACAO,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def bloquear_pendencia(
        self,
        pendencia_id: int,
        versao_esperada: int,
        travas: list[str],
        motivo: str,
        autor: str = "sistema",
    ) -> ItemFilaRevisao:
        return self.repository.bloquear_pendencia(
            pendencia_id=pendencia_id,
            versao_esperada=versao_esperada,
            travas=travas,
            motivo=motivo,
            autor=autor,
        )

    def cancelar_pendencia(
        self,
        pendencia_id: int,
        versao_esperada: int,
        motivo: str,
        autor: str,
    ) -> ItemFilaRevisao:
        return self.repository.cancelar_pendencia(
            pendencia_id=pendencia_id,
            versao_esperada=versao_esperada,
            motivo=motivo,
            autor=autor,
        )

    def obter_pendencia(self, pendencia_id: int) -> Optional[ItemFilaRevisao]:
        return self.repository.obter_pendencia(pendencia_id)

    def listar_pendencias(
        self,
        status: Optional[EstadoRevisao] = None,
        empresa_codigo: Optional[int] = None,
    ) -> List[ItemFilaRevisao]:
        return self.repository.listar_pendencias(status=status, empresa_codigo=empresa_codigo)

    def consultar_historico(self, pendencia_id: int) -> List[HistoricoRevisao]:
        return self.repository.consultar_historico(pendencia_id)

    def recuperar_casos_semelhantes(
        self, descricao: str, empresa_codigo: Optional[int] = None, limite: int = 5
    ) -> List[ExemploConfirmado]:
        return self.repository.recuperar_casos_semelhantes(
            descricao=descricao, empresa_codigo=empresa_codigo, limite=limite
        )

    def gerar_metricas_ia(self) -> MetricasAcertoIA:
        return self.repository.gerar_metricas_ia()

    def listar_regras_candidatas(
        self, status: Optional[StatusRegraCandidata] = None
    ) -> List[RegraCandidata]:
        return self.repository.listar_regras_candidatas(status=status)

    def promover_regra_candidata(self, regra_id: int, aprovado_por: str) -> RegraCandidata:
        return self.repository.promover_regra_candidata(regra_id=regra_id, aprovado_por=aprovado_por)
