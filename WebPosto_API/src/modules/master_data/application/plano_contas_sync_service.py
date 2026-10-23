"""Serviço de Sincronização do Plano de Contas Gerencial do webPosto (LOGOS).

Governança:
- O webPosto é a fonte oficial dos planos de contas.
- O catálogo gerencial é global e compartilhado entre todas as empresas do grupo.
- Modos de operação: 'dry-run' (consulta e compara sem alterar) e 'apply' (aplica atomicamente).
- Suporte a injeção de dados para testes offline isolados (zero requisições de rede).
- Proteção contra concorrência e falhas parciais (rollback atômico).
- Idempotência: execuções repetidas do mesmo catálogo não produzem auditorias espúrias.
- Planos ausentes no retorno oficial NUNCA são excluídos; são marcados como não observados e bloqueados.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from ..adapters.sqlite_master_data_repository import SqliteMasterDataRepository
from ..domain.models import (
    ConfiabilidadeCadastro,
    MasterPlanoConta,
    SyncPlanosResult,
)

logger = logging.getLogger(__name__)

ENDPOINT_GERENCIAL = "/INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL"
_SYNC_LOCK = threading.Lock()


def _hierarquia_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in str(value or "").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(10**9)
    return tuple(parts)


class PlanoContasSyncService:
    """Gerencia a sincronização segura e idempotente do plano de contas oficial."""

    def __init__(self, repository: Optional[SqliteMasterDataRepository] = None):
        self.repository = repository or SqliteMasterDataRepository()

    @staticmethod
    def validar_e_enriquecer_registros(registros_brutos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Valida unicidade, integridade de conteúdo e deriva a hierarquia oficial."""
        if not registros_brutos:
            raise ValueError("Resposta oficial vazia ou sem planos de conta.")

        unicos: dict[int, dict[str, Any]] = {}
        for item in registros_brutos:
            if not isinstance(item, dict) or "planoContaCodigo" not in item:
                raise ValueError("Item de plano de contas inválido ou sem planoContaCodigo.")
            codigo = int(item["planoContaCodigo"])
            if codigo in unicos:
                # Compara conteúdo sem chaves mutáveis secundárias
                atual = dict(item)
                existente = dict(unicos[codigo])
                if atual != existente:
                    raise ValueError(f"Código duplicado com conteúdo divergente detectado: {codigo}")
            unicos[codigo] = item

        registros = list(unicos.values())
        por_hierarquia = {str(item.get("hierarquia") or ""): int(item["planoContaCodigo"]) for item in registros}
        hierarquias = set(por_hierarquia)
        saida: list[dict[str, Any]] = []

        for item in registros:
            codigo = int(item["planoContaCodigo"])
            hierarquia = str(item.get("hierarquia") or "").strip()
            prefix = f"{hierarquia}." if hierarquia else ""
            parent_h = hierarquia.rsplit(".", 1)[0] if "." in hierarquia else None
            parent_code = por_hierarquia.get(parent_h or "") if parent_h else None

            # É folha se nenhuma outra hierarquia começar com `{hierarquia}.`
            folha = bool(hierarquia) and not any(h.startswith(prefix) for h in hierarquias if h != hierarquia)

            # Contas de classificação pendente/transitória têm candidato_lancavel bloqueado até a implementação da fila de revisão
            desc_upper = str(item.get("descricao") or "").strip().upper()
            bloqueado_transitorio = (
                hierarquia == "2.04.10"
                or "PENDENTES DE CLASSIFICAÇÃO" in desc_upper
                or "PENDENTES DE CLASSIFICACAO" in desc_upper
            )
            candidato_lancavel = bool(folha and not bloqueado_transitorio)

            saida.append({
                "planoContaCodigo": codigo,
                "descricao": str(item.get("descricao") or "").strip(),
                "hierarquia": hierarquia or None,
                "nivel": len(hierarquia.split(".")) if hierarquia else 0,
                "natureza": str(item.get("natureza") or "DESPESA"),
                "tipo": item.get("tipo"),
                "grupo": str(item.get("grupo") or "").strip() or None,
                "ativo": bool(item.get("ativo", True)),
                "paiHierarquia": parent_h,
                "paiCodigo": parent_code,
                "ehFolhaEstrutural": folha,
                "candidatoLancavel": candidato_lancavel,
            })

        return sorted(saida, key=lambda x: (_hierarquia_key(x["hierarquia"]), x["planoContaCodigo"]))

    @staticmethod
    def calcular_hash_catalogo(planos_enriquecidos: list[dict[str, Any]]) -> str:
        """Gera hash determinístico SHA-256 do catálogo normalizado."""
        canonical = json.dumps(planos_enriquecidos, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()

    def coletar_oficiais_api(
        self,
        base_url: str,
        api_key: str,
        client: Optional[httpx.Client] = None,
        limite_pagina: int = 2000,
    ) -> list[dict[str, Any]]:
        """Executa exclusivamente requisições GET com paginação estrita e detecção de loops."""
        if not api_key:
            raise ValueError("Chave de API do webPosto não configurada para leitura de planos.")
        url_base = base_url.rstrip("/")
        registros: list[dict[str, Any]] = []
        cursor: int | None = None
        cursores_visitados: set[int] = set()

        def _executar(c: httpx.Client) -> list[dict[str, Any]]:
            nonlocal cursor
            while True:
                params: dict[str, Any] = {"limite": limite_pagina}
                if cursor is not None:
                    params["ultimoCodigo"] = cursor

                response = c.get(
                    f"{url_base}{ENDPOINT_GERENCIAL}",
                    headers={
                        "x-api-key": api_key,
                        "Accept": "application/json",
                        "User-Agent": "Logos-PlanoContasSyncService/1.0",
                    },
                    params=params,
                )
                if response.status_code != 200:
                    detalhe = response.text[:300].replace(api_key, "***")
                    raise RuntimeError(f"GET {ENDPOINT_GERENCIAL} falhou: HTTP {response.status_code} — {detalhe}")

                body = response.json()
                page = body.get("resultados", []) if isinstance(body, dict) else body
                if not isinstance(page, list):
                    raise RuntimeError("Resposta inesperada do ERP: resultados não é uma lista.")

                registros.extend(dict(item) for item in page)

                next_cursor = body.get("ultimoCodigo") if isinstance(body, dict) else None
                if not page or next_cursor is None or len(page) < limite_pagina:
                    break
                next_cursor = int(next_cursor)
                if next_cursor in cursores_visitados:
                    raise RuntimeError(f"Cursor repetido detectado na paginação oficial: {next_cursor}")
                cursores_visitados.add(next_cursor)
                cursor = next_cursor

            return registros

        if client is not None:
            return _executar(client)

        with httpx.Client(timeout=30.0, follow_redirects=False) as c:
            return _executar(c)

    def sincronizar(
        self,
        *,
        modo: str = "apply",
        dados_oficiais: Optional[list[dict[str, Any]]] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        origem: str = "webposto_api_v1",
    ) -> SyncPlanosResult:
        """Executa o ciclo completo de sincronização nos modos 'dry-run' ou 'apply'.

        - Protegido por lock de concorrência.
        - Transação atômica com rollback automático em caso de exceção.
        - Idempotência absoluta para execuções repetidas.
        """
        modo_normalizado = modo.strip().upper().replace("-", "_")
        if modo_normalizado not in ("DRY_RUN", "APPLY"):
            raise ValueError(f"Modo de sincronização inválido: '{modo}'. Use 'dry-run' ou 'apply'.")

        if not _SYNC_LOCK.acquire(blocking=False):
            return SyncPlanosResult(
                sucesso=False,
                modo=modo_normalizado,
                origem=origem,
                iniciado_em=datetime.now(timezone.utc).isoformat(),
                finalizado_em=datetime.now(timezone.utc).isoformat(),
                mensagem="Sincronização bloqueada: outra execução já está em andamento.",
                erro="CONCURRENCY_LOCK_ACTIVE",
            )

        inicio_utc = datetime.now(timezone.utc)
        inicio_iso = inicio_utc.isoformat()

        try:
            # 1. Obtenção dos dados oficiais (injeção offline ou consulta GET)
            if dados_oficiais is not None:
                registros_brutos = dados_oficiais
            else:
                if not base_url or not api_key:
                    raise ValueError("base_url e api_key são obrigatórios quando dados_oficiais não for fornecido.")
                registros_brutos = self.coletar_oficiais_api(base_url, api_key, client=client)

            if not registros_brutos:
                raise ValueError("Retorno oficial vazio: nenhum plano recebido. Operação abortada para proteção da base local.")

            # 2. Validação, unicidade e reconstrução hierárquica
            oficiais_enriquecidos = self.validar_e_enriquecer_registros(registros_brutos)
            hash_catalogo = self.calcular_hash_catalogo(oficiais_enriquecidos)

            # 3. Comparação com o catálogo local atual
            locais_atuais = {p.plano_conta_codigo: p for p in self.repository.listar_planos_conta()}
            total_anterior = len(locais_atuais)
            oficiais_map = {item["planoContaCodigo"]: item for item in oficiais_enriquecidos}
            codigos_oficiais = set(oficiais_map.keys())

            inseridos: list[MasterPlanoConta] = []
            atualizados: list[MasterPlanoConta] = []
            inalterados: int = 0

            agora = datetime.now(timezone.utc)

            for item in oficiais_enriquecidos:
                cod = item["planoContaCodigo"]
                nat = "DESPESA" if str(item.get("natureza", "D")).upper() in ("D", "DESPESA") else "OUTRO"
                permite_desp = bool(item["candidatoLancavel"] and nat == "DESPESA")

                novo_obj = MasterPlanoConta(
                    plano_conta_codigo=cod,
                    descricao=item["descricao"],
                    hierarquia=item["hierarquia"],
                    pai_codigo=item["paiCodigo"],
                    pai_hierarquia=item["paiHierarquia"],
                    nivel=item["nivel"],
                    natureza=nat,
                    grupo=item.get("grupo"),
                    ativo=bool(item.get("ativo", True)),
                    permite_despesa=permite_desp,
                    eh_folha=bool(item["ehFolhaEstrutural"]),
                    candidato_lancavel=bool(item["candidatoLancavel"]),
                    observado_ultima_sincronizacao=True,
                    confiabilidade=ConfiabilidadeCadastro.CONFIRMADO,
                    origem_dado=origem,
                    hash_origem=hash_catalogo,
                    sincronizado_em=agora,
                    atualizado_em=agora,
                )

                if cod not in locais_atuais:
                    inseridos.append(novo_obj)
                else:
                    ant = locais_atuais[cod]
                    mudou = (
                        ant.descricao != novo_obj.descricao
                        or ant.hierarquia != novo_obj.hierarquia
                        or ant.pai_codigo != novo_obj.pai_codigo
                        or ant.pai_hierarquia != novo_obj.pai_hierarquia
                        or ant.nivel != novo_obj.nivel
                        or ant.natureza != novo_obj.natureza
                        or ant.ativo != novo_obj.ativo
                        or ant.eh_folha != novo_obj.eh_folha
                        or ant.candidato_lancavel != novo_obj.candidato_lancavel
                        or ant.observado_ultima_sincronizacao != novo_obj.observado_ultima_sincronizacao
                    )
                    if mudou:
                        atualizados.append(novo_obj)
                    else:
                        inalterados += 1

            # Planos locais ausentes no retorno oficial
            nao_observados_codigos = set(locais_atuais.keys()) - codigos_oficiais
            total_nao_observados = len(nao_observados_codigos)

            detalhes = {
                "totalOficial": len(oficiais_enriquecidos),
                "totalAnterior": total_anterior,
                "inseridosCodigos": [p.plano_conta_codigo for p in inseridos],
                "atualizadosCodigos": [p.plano_conta_codigo for p in atualizados],
                "naoObservadosCodigos": sorted(nao_observados_codigos),
                "inalterados": inalterados,
                "hashCatalogo": hash_catalogo,
            }

            # 4. Modo DRY_RUN: não toca no SQLite
            if modo_normalizado == "DRY_RUN":
                fim_iso = datetime.now(timezone.utc).isoformat()
                log_entry = {
                    "tipo_entidade": "PLANOS_CONTA",
                    "iniciado_em": inicio_iso,
                    "finalizado_em": fim_iso,
                    "sucesso": True,
                    "modo": "DRY_RUN",
                    "origem": origem,
                    "total_oficial": len(oficiais_enriquecidos),
                    "total_anterior": total_anterior,
                    "total_inseridos": len(inseridos),
                    "total_atualizados": len(atualizados),
                    "total_inalterados": inalterados,
                    "total_nao_observados": total_nao_observados,
                    "hash_catalogo": hash_catalogo,
                    "detalhes_json": detalhes,
                    "erro": None,
                }
                # Em dry-run registra o log de auditoria da simulação
                try:
                    self.repository.registrar_sincronizacao_log(log_entry)
                except Exception as log_err:
                    logger.warning("Não foi possível salvar log de dry-run: %s", log_err)

                return SyncPlanosResult(
                    sucesso=True,
                    modo="DRY_RUN",
                    origem=origem,
                    iniciado_em=inicio_iso,
                    finalizado_em=fim_iso,
                    total_oficial=len(oficiais_enriquecidos),
                    total_anterior=total_anterior,
                    total_inseridos=len(inseridos),
                    total_atualizados=len(atualizados),
                    total_inalterados=inalterados,
                    total_nao_observados=total_nao_observados,
                    hash_catalogo=hash_catalogo,
                    mensagem="Simulação concluída com sucesso. Nenhuma alteração gravada na base local.",
                    detalhes=detalhes,
                )

            # 5. Modo APPLY: transação atômica única com rollback integral
            planos_a_persistir = inseridos + atualizados
            with self.repository._transacao() as conn:
                if planos_a_persistir:
                    self.repository.upsert_planos_conta_bulk(
                        planos_a_persistir,
                        origem_auditoria=f"sincronizacao_{origem}",
                        conn=conn,
                    )

                if nao_observados_codigos:
                    self.repository.marcar_planos_nao_observados(
                        codigos_observados=codigos_oficiais,
                        timestamp_iso=agora.isoformat(),
                        hash_origem=hash_catalogo,
                        origem_auditoria=f"sincronizacao_{origem}",
                        conn=conn,
                    )

                fim_iso = datetime.now(timezone.utc).isoformat()
                log_entry = {
                    "tipo_entidade": "PLANOS_CONTA",
                    "iniciado_em": inicio_iso,
                    "finalizado_em": fim_iso,
                    "sucesso": True,
                    "modo": "APPLY",
                    "origem": origem,
                    "total_oficial": len(oficiais_enriquecidos),
                    "total_anterior": total_anterior,
                    "total_inseridos": len(inseridos),
                    "total_atualizados": len(atualizados),
                    "total_inalterados": inalterados,
                    "total_nao_observados": total_nao_observados,
                    "hash_catalogo": hash_catalogo,
                    "detalhes_json": detalhes,
                    "erro": None,
                }
                self.repository.registrar_sincronizacao_log(log_entry, conn=conn)

            return SyncPlanosResult(
                sucesso=True,
                modo="APPLY",
                origem=origem,
                iniciado_em=inicio_iso,
                finalizado_em=fim_iso,
                total_oficial=len(oficiais_enriquecidos),
                total_anterior=total_anterior,
                total_inseridos=len(inseridos),
                total_atualizados=len(atualizados),
                total_inalterados=inalterados,
                total_nao_observados=total_nao_observados,
                hash_catalogo=hash_catalogo,
                mensagem="Sincronização aplicada com sucesso na base local.",
                detalhes=detalhes,
            )

        except Exception as exc:
            fim_iso = datetime.now(timezone.utc).isoformat()
            erro_msg = str(exc)
            logger.error("Falha na sincronização do plano de contas: %s", erro_msg)
            try:
                self.repository.registrar_sincronizacao_log({
                    "tipo_entidade": "PLANOS_CONTA",
                    "iniciado_em": inicio_iso,
                    "finalizado_em": fim_iso,
                    "sucesso": False,
                    "modo": modo_normalizado,
                    "origem": origem,
                    "total_oficial": 0,
                    "total_anterior": 0,
                    "total_inseridos": 0,
                    "total_atualizados": 0,
                    "total_inalterados": 0,
                    "total_nao_observados": 0,
                    "hash_catalogo": None,
                    "detalhes_json": {"exception": erro_msg},
                    "erro": erro_msg,
                })
            except Exception:
                pass

            return SyncPlanosResult(
                sucesso=False,
                modo=modo_normalizado,
                origem=origem,
                iniciado_em=inicio_iso,
                finalizado_em=fim_iso,
                mensagem=f"Falha na sincronização: {erro_msg}",
                erro=erro_msg,
            )

        finally:
            _SYNC_LOCK.release()
