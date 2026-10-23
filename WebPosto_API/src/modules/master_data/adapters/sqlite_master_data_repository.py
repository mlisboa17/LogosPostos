"""Repositório SQLite para o Cadastro Mestre Financeiro do LOGOS (MASTER-DATA-01).

Características:
- Armazenamento local ACID com WAL mode (`PRAGMA journal_mode=WAL`).
- Constraints relacionais (`PRAGMA foreign_keys=ON`).
- Lock de escrita pessimista (`BEGIN IMMEDIATE`).
- Suporte a injeção de caminho customizado para testes unitários isolados.
- Trilha de auditoria append-only para qualquer modificação cadastral.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List, Optional

from ..domain.models import (
    ConfiabilidadeCadastro,
    MasterCentroCusto,
    MasterContaFinanceira,
    MasterDataAuditEntry,
    MasterEmpresa,
    MasterFornecedor,
    MasterPlanoConta,
    PapelEntidade,
    TipoContaFinanceira,
)
from .migrations.migration_001_planos_conta_hierarquia import migrar

logger = logging.getLogger(__name__)

DEFAULT_MASTER_DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "master_data"
DEFAULT_MASTER_DATA_DB = DEFAULT_MASTER_DATA_DIR / "master_data.sqlite3"


class SqliteMasterDataRepository:
    """Implementação concreta de persistência do catálogo mestre em SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_MASTER_DATA_DB
        self._inicializar_banco()

    def _conectar(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conexao = sqlite3.connect(
            str(self.db_path),
            timeout=5.0,
            isolation_level=None,  # Controle manual de transações via BEGIN IMMEDIATE
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
        """Cria o esquema inicial e índices caso não existam."""
        with self._transacao() as conn:
            # 1. Empresas
            conn.execute("""
                CREATE TABLE IF NOT EXISTS master_empresas (
                    empresa_codigo INTEGER PRIMARY KEY,
                    cod_web INTEGER,
                    razao_social TEXT NOT NULL,
                    nome_fantasia TEXT NOT NULL,
                    cnpj TEXT NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    autorizado_despesa INTEGER NOT NULL DEFAULT 1,
                    usa_mais_pagamentos INTEGER NOT NULL DEFAULT 1,
                    conta_cofre_padrao INTEGER,
                    confiabilidade TEXT NOT NULL,
                    origem_dado TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );
            """)

            # 2. Contas Financeiras
            conn.execute("""
                CREATE TABLE IF NOT EXISTS master_contas_financeiras (
                    conta_codigo INTEGER PRIMARY KEY,
                    empresa_codigo INTEGER,
                    descricao TEXT NOT NULL,
                    tipo_conta TEXT NOT NULL,
                    banco_codigo TEXT,
                    banco_nome TEXT,
                    agencia TEXT,
                    conta_numero TEXT,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    permite_debito_despesa INTEGER NOT NULL DEFAULT 0,
                    confiabilidade TEXT NOT NULL,
                    origem_dado TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    FOREIGN KEY(empresa_codigo) REFERENCES master_empresas(empresa_codigo)
                );
            """)

            # 3. Plano de Contas
            conn.execute("""
                CREATE TABLE IF NOT EXISTS master_planos_conta (
                    plano_conta_codigo INTEGER PRIMARY KEY,
                    descricao TEXT NOT NULL,
                    natureza TEXT NOT NULL DEFAULT 'DESPESA',
                    grupo TEXT,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    permite_despesa INTEGER NOT NULL DEFAULT 1,
                    confiabilidade TEXT NOT NULL,
                    origem_dado TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );
            """)

            # 4. Centros de Custo
            conn.execute("""
                CREATE TABLE IF NOT EXISTS master_centros_custo (
                    centro_custo_codigo INTEGER PRIMARY KEY,
                    empresa_codigo INTEGER,
                    descricao TEXT NOT NULL,
                    tipo_abrangencia TEXT NOT NULL DEFAULT 'GERAL',
                    ativo INTEGER NOT NULL DEFAULT 1,
                    confiabilidade TEXT NOT NULL,
                    origem_dado TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    FOREIGN KEY(empresa_codigo) REFERENCES master_empresas(empresa_codigo)
                );
            """)

            # 5. Fornecedores e Favorecidos
            conn.execute("""
                CREATE TABLE IF NOT EXISTS master_fornecedores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fornecedor_codigo INTEGER,
                    empresa_codigo INTEGER,
                    razao_social TEXT NOT NULL,
                    nome_fantasia TEXT,
                    cnpj_cpf TEXT,
                    papel TEXT NOT NULL DEFAULT 'FORNECEDOR',
                    ativo INTEGER NOT NULL DEFAULT 1,
                    confiabilidade TEXT NOT NULL,
                    origem_dado TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    FOREIGN KEY(empresa_codigo) REFERENCES master_empresas(empresa_codigo)
                );
            """)

            # 6. Trilha de Auditoria Append-Only
            conn.execute("""
                CREATE TABLE IF NOT EXISTS master_data_audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo_entidade TEXT NOT NULL,
                    identificador TEXT NOT NULL,
                    empresa_codigo INTEGER,
                    acao TEXT NOT NULL,
                    dados_anteriores_json TEXT,
                    dados_novos_json TEXT,
                    origem TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
            """)

            # Índices de Performance e Integridade
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contas_empresa ON master_contas_financeiras(empresa_codigo);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contas_banco ON master_contas_financeiras(banco_codigo, agencia, conta_numero);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_planos_desc ON master_planos_conta(descricao);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fornec_cnpj ON master_fornecedores(cnpj_cpf);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fornec_cod ON master_fornecedores(fornecedor_codigo);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ent ON master_data_audit_log(tipo_entidade, identificador);")
            migrar(conn)

    # ==========================================
    # AUDITORIA
    # ==========================================

    def registrar_auditoria(self, entry: MasterDataAuditEntry) -> None:
        with self._transacao() as conn:
            conn.execute(
                """
                INSERT INTO master_data_audit_log (
                    tipo_entidade, identificador, empresa_codigo, acao,
                    dados_anteriores_json, dados_novos_json, origem, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    entry.tipo_entidade,
                    entry.identificador,
                    entry.empresa_codigo,
                    entry.acao,
                    entry.dados_anteriores_json,
                    entry.dados_novos_json,
                    entry.origem,
                    entry.timestamp.isoformat(),
                ),
            )

    def listar_auditoria(
        self, tipo_entidade: Optional[str] = None, identificador: Optional[str] = None
    ) -> List[MasterDataAuditEntry]:
        conexao = self._conectar()
        try:
            query = "SELECT * FROM master_data_audit_log WHERE 1=1"
            params: list[Any] = []
            if tipo_entidade:
                query += " AND tipo_entidade = ?"
                params.append(tipo_entidade)
            if identificador:
                query += " AND identificador = ?"
                params.append(identificador)
            query += " ORDER BY audit_id ASC"
            cursor = conexao.execute(query, params)
            rows = cursor.fetchall()
            return [
                MasterDataAuditEntry(
                    audit_id=row["audit_id"],
                    tipo_entidade=row["tipo_entidade"],
                    identificador=row["identificador"],
                    empresa_codigo=row["empresa_codigo"],
                    acao=row["acao"],
                    dados_anteriores_json=row["dados_anteriores_json"],
                    dados_novos_json=row["dados_novos_json"],
                    origem=row["origem"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                )
                for row in rows
            ]
        finally:
            conexao.close()

    # ==========================================
    # EMPRESAS
    # ==========================================

    def upsert_empresa(self, empresa: MasterEmpresa, *, origem_auditoria: str = "sync") -> None:
        with self._transacao() as conn:
            anterior_row = conn.execute(
                "SELECT * FROM master_empresas WHERE empresa_codigo = ?", (empresa.empresa_codigo,)
            ).fetchone()
            anterior_json = json.dumps(dict(anterior_row)) if anterior_row else None
            acao = "ATUALIZACAO" if anterior_row else "INSERCAO"

            conn.execute(
                """
                INSERT INTO master_empresas (
                    empresa_codigo, cod_web, razao_social, nome_fantasia,
                    cnpj, ativo, autorizado_despesa, usa_mais_pagamentos,
                    conta_cofre_padrao, confiabilidade, origem_dado, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(empresa_codigo) DO UPDATE SET
                    cod_web = excluded.cod_web,
                    razao_social = excluded.razao_social,
                    nome_fantasia = excluded.nome_fantasia,
                    cnpj = excluded.cnpj,
                    ativo = excluded.ativo,
                    autorizado_despesa = excluded.autorizado_despesa,
                    usa_mais_pagamentos = excluded.usa_mais_pagamentos,
                    conta_cofre_padrao = excluded.conta_cofre_padrao,
                    confiabilidade = excluded.confiabilidade,
                    origem_dado = excluded.origem_dado,
                    atualizado_em = excluded.atualizado_em;
                """,
                (
                    empresa.empresa_codigo,
                    empresa.cod_web,
                    empresa.razao_social,
                    empresa.nome_fantasia,
                    empresa.cnpj,
                    1 if empresa.ativo else 0,
                    1 if empresa.autorizado_despesa else 0,
                    1 if empresa.usa_mais_pagamentos else 0,
                    empresa.conta_cofre_padrao,
                    empresa.confiabilidade.value,
                    empresa.origem_dado,
                    empresa.atualizado_em.isoformat(),
                ),
            )

            conn.execute(
                """
                INSERT INTO master_data_audit_log (
                    tipo_entidade, identificador, empresa_codigo, acao,
                    dados_anteriores_json, dados_novos_json, origem, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    "EMPRESA",
                    str(empresa.empresa_codigo),
                    empresa.empresa_codigo,
                    acao,
                    anterior_json,
                    empresa.model_dump_json(),
                    origem_auditoria,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def obter_empresa(self, empresa_codigo: int) -> Optional[MasterEmpresa]:
        conexao = self._conectar()
        try:
            row = conexao.execute(
                "SELECT * FROM master_empresas WHERE empresa_codigo = ?", (empresa_codigo,)
            ).fetchone()
            if not row:
                return None
            return MasterEmpresa(
                empresa_codigo=row["empresa_codigo"],
                cod_web=row["cod_web"],
                razao_social=row["razao_social"],
                nome_fantasia=row["nome_fantasia"],
                cnpj=row["cnpj"],
                ativo=bool(row["ativo"]),
                autorizado_despesa=bool(row["autorizado_despesa"]),
                usa_mais_pagamentos=bool(row["usa_mais_pagamentos"]),
                conta_cofre_padrao=row["conta_cofre_padrao"],
                confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                origem_dado=row["origem_dado"],
                atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
            )
        finally:
            conexao.close()

    def listar_empresas(self) -> List[MasterEmpresa]:
        conexao = self._conectar()
        try:
            rows = conexao.execute("SELECT * FROM master_empresas ORDER BY empresa_codigo").fetchall()
            return [
                MasterEmpresa(
                    empresa_codigo=row["empresa_codigo"],
                    cod_web=row["cod_web"],
                    razao_social=row["razao_social"],
                    nome_fantasia=row["nome_fantasia"],
                    cnpj=row["cnpj"],
                    ativo=bool(row["ativo"]),
                    autorizado_despesa=bool(row["autorizado_despesa"]),
                    usa_mais_pagamentos=bool(row["usa_mais_pagamentos"]),
                    conta_cofre_padrao=row["conta_cofre_padrao"],
                    confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                    origem_dado=row["origem_dado"],
                    atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
                )
                for row in rows
            ]
        finally:
            conexao.close()

    # ==========================================
    # CONTAS FINANCEIRAS
    # ==========================================

    def upsert_conta_financeira(self, conta: MasterContaFinanceira, *, origem_auditoria: str = "sync") -> None:
        with self._transacao() as conn:
            anterior_row = conn.execute(
                "SELECT * FROM master_contas_financeiras WHERE conta_codigo = ?", (conta.conta_codigo,)
            ).fetchone()
            anterior_json = json.dumps(dict(anterior_row)) if anterior_row else None
            acao = "ATUALIZACAO" if anterior_row else "INSERCAO"

            conn.execute(
                """
                INSERT INTO master_contas_financeiras (
                    conta_codigo, empresa_codigo, descricao, tipo_conta,
                    banco_codigo, banco_nome, agencia, conta_numero,
                    ativo, permite_debito_despesa, confiabilidade, origem_dado, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conta_codigo) DO UPDATE SET
                    empresa_codigo = excluded.empresa_codigo,
                    descricao = excluded.descricao,
                    tipo_conta = excluded.tipo_conta,
                    banco_codigo = excluded.banco_codigo,
                    banco_nome = excluded.banco_nome,
                    agencia = excluded.agencia,
                    conta_numero = excluded.conta_numero,
                    ativo = excluded.ativo,
                    permite_debito_despesa = excluded.permite_debito_despesa,
                    confiabilidade = excluded.confiabilidade,
                    origem_dado = excluded.origem_dado,
                    atualizado_em = excluded.atualizado_em;
                """,
                (
                    conta.conta_codigo,
                    conta.empresa_codigo,
                    conta.descricao,
                    conta.tipo_conta.value,
                    conta.banco_codigo,
                    conta.banco_nome,
                    conta.agencia,
                    conta.conta_numero,
                    1 if conta.ativo else 0,
                    1 if conta.permite_debito_despesa else 0,
                    conta.confiabilidade.value,
                    conta.origem_dado,
                    conta.atualizado_em.isoformat(),
                ),
            )

            conn.execute(
                """
                INSERT INTO master_data_audit_log (
                    tipo_entidade, identificador, empresa_codigo, acao,
                    dados_anteriores_json, dados_novos_json, origem, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    "CONTA_FINANCEIRA",
                    str(conta.conta_codigo),
                    conta.empresa_codigo,
                    acao,
                    anterior_json,
                    conta.model_dump_json(),
                    origem_auditoria,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def obter_conta_financeira(self, conta_codigo: int) -> Optional[MasterContaFinanceira]:
        conexao = self._conectar()
        try:
            row = conexao.execute(
                "SELECT * FROM master_contas_financeiras WHERE conta_codigo = ?", (conta_codigo,)
            ).fetchone()
            if not row:
                return None
            return MasterContaFinanceira(
                conta_codigo=row["conta_codigo"],
                empresa_codigo=row["empresa_codigo"],
                descricao=row["descricao"],
                tipo_conta=TipoContaFinanceira(row["tipo_conta"]),
                banco_codigo=row["banco_codigo"],
                banco_nome=row["banco_nome"],
                agencia=row["agencia"],
                conta_numero=row["conta_numero"],
                ativo=bool(row["ativo"]),
                permite_debito_despesa=bool(row["permite_debito_despesa"]),
                confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                origem_dado=row["origem_dado"],
                atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
            )
        finally:
            conexao.close()

    def listar_contas_financeiras(self, empresa_codigo: Optional[int] = None) -> List[MasterContaFinanceira]:
        conexao = self._conectar()
        try:
            if empresa_codigo is not None:
                rows = conexao.execute(
                    "SELECT * FROM master_contas_financeiras WHERE empresa_codigo = ? OR empresa_codigo IS NULL ORDER BY conta_codigo",
                    (empresa_codigo,),
                ).fetchall()
            else:
                rows = conexao.execute("SELECT * FROM master_contas_financeiras ORDER BY conta_codigo").fetchall()
            return [
                MasterContaFinanceira(
                    conta_codigo=row["conta_codigo"],
                    empresa_codigo=row["empresa_codigo"],
                    descricao=row["descricao"],
                    tipo_conta=TipoContaFinanceira(row["tipo_conta"]),
                    banco_codigo=row["banco_codigo"],
                    banco_nome=row["banco_nome"],
                    agencia=row["agencia"],
                    conta_numero=row["conta_numero"],
                    ativo=bool(row["ativo"]),
                    permite_debito_despesa=bool(row["permite_debito_despesa"]),
                    confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                    origem_dado=row["origem_dado"],
                    atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
                )
                for row in rows
            ]
        finally:
            conexao.close()

    # ==========================================
    # PLANO DE CONTAS
    # ==========================================

    def _row_para_plano(self, row: sqlite3.Row) -> MasterPlanoConta:
        keys = row.keys()
        sincronizado_em = (
            datetime.fromisoformat(row["sincronizado_em"])
            if "sincronizado_em" in keys and row["sincronizado_em"]
            else None
        )
        return MasterPlanoConta(
            plano_conta_codigo=row["plano_conta_codigo"],
            descricao=row["descricao"],
            hierarquia=row["hierarquia"] if "hierarquia" in keys else None,
            pai_codigo=row["pai_codigo"] if "pai_codigo" in keys else None,
            pai_hierarquia=row["pai_hierarquia"] if "pai_hierarquia" in keys else None,
            nivel=row["nivel"] if "nivel" in keys and row["nivel"] is not None else 0,
            natureza=row["natureza"],
            grupo=row["grupo"],
            ativo=bool(row["ativo"]),
            permite_despesa=bool(row["permite_despesa"]),
            eh_folha=bool(row["eh_folha"]) if "eh_folha" in keys and row["eh_folha"] is not None else True,
            candidato_lancavel=bool(row["candidato_lancavel"]) if "candidato_lancavel" in keys and row["candidato_lancavel"] is not None else True,
            observado_ultima_sincronizacao=bool(row["observado_ultima_sincronizacao"]) if "observado_ultima_sincronizacao" in keys and row["observado_ultima_sincronizacao"] is not None else True,
            confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
            origem_dado=row["origem_dado"],
            hash_origem=row["hash_origem"] if "hash_origem" in keys else None,
            sincronizado_em=sincronizado_em,
            atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
        )

    def upsert_plano_conta(self, plano: MasterPlanoConta, *, origem_auditoria: str = "sync") -> None:
        with self._transacao() as conn:
            anterior_row = conn.execute(
                "SELECT * FROM master_planos_conta WHERE plano_conta_codigo = ?", (plano.plano_conta_codigo,)
            ).fetchone()
            anterior_json = json.dumps(dict(anterior_row)) if anterior_row else None
            acao = "ATUALIZACAO" if anterior_row else "INSERCAO"

            mudou = True
            if anterior_row:
                ant_plano = self._row_para_plano(anterior_row)
                if (
                    ant_plano.descricao == plano.descricao
                    and ant_plano.hierarquia == plano.hierarquia
                    and ant_plano.pai_codigo == plano.pai_codigo
                    and ant_plano.pai_hierarquia == plano.pai_hierarquia
                    and ant_plano.nivel == plano.nivel
                    and ant_plano.natureza == plano.natureza
                    and ant_plano.grupo == plano.grupo
                    and ant_plano.ativo == plano.ativo
                    and ant_plano.permite_despesa == plano.permite_despesa
                    and ant_plano.eh_folha == plano.eh_folha
                    and ant_plano.candidato_lancavel == plano.candidato_lancavel
                    and ant_plano.observado_ultima_sincronizacao == plano.observado_ultima_sincronizacao
                ):
                    mudou = False

            conn.execute(
                """
                INSERT INTO master_planos_conta (
                    plano_conta_codigo, descricao, hierarquia, pai_codigo, pai_hierarquia, nivel,
                    natureza, grupo, ativo, permite_despesa, eh_folha, candidato_lancavel,
                    observado_ultima_sincronizacao, confiabilidade, origem_dado, hash_origem,
                    sincronizado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plano_conta_codigo) DO UPDATE SET
                    descricao = excluded.descricao,
                    hierarquia = excluded.hierarquia,
                    pai_codigo = excluded.pai_codigo,
                    pai_hierarquia = excluded.pai_hierarquia,
                    nivel = excluded.nivel,
                    natureza = excluded.natureza,
                    grupo = excluded.grupo,
                    ativo = excluded.ativo,
                    permite_despesa = excluded.permite_despesa,
                    eh_folha = excluded.eh_folha,
                    candidato_lancavel = excluded.candidato_lancavel,
                    observado_ultima_sincronizacao = excluded.observado_ultima_sincronizacao,
                    confiabilidade = excluded.confiabilidade,
                    origem_dado = excluded.origem_dado,
                    hash_origem = excluded.hash_origem,
                    sincronizado_em = excluded.sincronizado_em,
                    atualizado_em = excluded.atualizado_em;
                """,
                (
                    plano.plano_conta_codigo,
                    plano.descricao,
                    plano.hierarquia,
                    plano.pai_codigo,
                    plano.pai_hierarquia,
                    plano.nivel,
                    plano.natureza,
                    plano.grupo,
                    1 if plano.ativo else 0,
                    1 if plano.permite_despesa else 0,
                    1 if plano.eh_folha else 0,
                    1 if plano.candidato_lancavel else 0,
                    1 if plano.observado_ultima_sincronizacao else 0,
                    plano.confiabilidade.value,
                    plano.origem_dado,
                    plano.hash_origem,
                    plano.sincronizado_em.isoformat() if plano.sincronizado_em else None,
                    plano.atualizado_em.isoformat(),
                ),
            )

            if mudou:
                conn.execute(
                    """
                    INSERT INTO master_data_audit_log (
                        tipo_entidade, identificador, empresa_codigo, acao,
                        dados_anteriores_json, dados_novos_json, origem, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        "PLANO_CONTA",
                        str(plano.plano_conta_codigo),
                        None,
                        acao,
                        anterior_json,
                        plano.model_dump_json(),
                        origem_auditoria,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

    def upsert_planos_conta_bulk(
        self,
        planos: list[MasterPlanoConta],
        *,
        origem_auditoria: str = "sync_bulk",
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Upsert em lote de múltiplos planos de conta em uma única transação atômica."""
        if not planos:
            return 0
        if conn is not None:
            return self._executar_upsert_planos_bulk(conn, planos, origem_auditoria)
        with self._transacao() as c:
            return self._executar_upsert_planos_bulk(c, planos, origem_auditoria)

    def _executar_upsert_planos_bulk(
        self,
        conn: sqlite3.Connection,
        planos: list[MasterPlanoConta],
        origem_auditoria: str,
    ) -> int:
        agora_iso = datetime.now(timezone.utc).isoformat()
        for plano in planos:
            anterior_row = conn.execute(
                "SELECT * FROM master_planos_conta WHERE plano_conta_codigo = ?", (plano.plano_conta_codigo,)
            ).fetchone()
            anterior_json = json.dumps(dict(anterior_row)) if anterior_row else None
            acao = "ATUALIZACAO" if anterior_row else "INSERCAO"

            mudou = True
            if anterior_row:
                ant_plano = self._row_para_plano(anterior_row)
                if (
                    ant_plano.descricao == plano.descricao
                    and ant_plano.hierarquia == plano.hierarquia
                    and ant_plano.pai_codigo == plano.pai_codigo
                    and ant_plano.pai_hierarquia == plano.pai_hierarquia
                    and ant_plano.nivel == plano.nivel
                    and ant_plano.natureza == plano.natureza
                    and ant_plano.grupo == plano.grupo
                    and ant_plano.ativo == plano.ativo
                    and ant_plano.permite_despesa == plano.permite_despesa
                    and ant_plano.eh_folha == plano.eh_folha
                    and ant_plano.candidato_lancavel == plano.candidato_lancavel
                    and ant_plano.observado_ultima_sincronizacao == plano.observado_ultima_sincronizacao
                ):
                    mudou = False

            conn.execute(
                """
                INSERT INTO master_planos_conta (
                    plano_conta_codigo, descricao, hierarquia, pai_codigo, pai_hierarquia, nivel,
                    natureza, grupo, ativo, permite_despesa, eh_folha, candidato_lancavel,
                    observado_ultima_sincronizacao, confiabilidade, origem_dado, hash_origem,
                    sincronizado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plano_conta_codigo) DO UPDATE SET
                    descricao = excluded.descricao,
                    hierarquia = excluded.hierarquia,
                    pai_codigo = excluded.pai_codigo,
                    pai_hierarquia = excluded.pai_hierarquia,
                    nivel = excluded.nivel,
                    natureza = excluded.natureza,
                    grupo = excluded.grupo,
                    ativo = excluded.ativo,
                    permite_despesa = excluded.permite_despesa,
                    eh_folha = excluded.eh_folha,
                    candidato_lancavel = excluded.candidato_lancavel,
                    observado_ultima_sincronizacao = excluded.observado_ultima_sincronizacao,
                    confiabilidade = excluded.confiabilidade,
                    origem_dado = excluded.origem_dado,
                    hash_origem = excluded.hash_origem,
                    sincronizado_em = excluded.sincronizado_em,
                    atualizado_em = excluded.atualizado_em;
                """,
                (
                    plano.plano_conta_codigo,
                    plano.descricao,
                    plano.hierarquia,
                    plano.pai_codigo,
                    plano.pai_hierarquia,
                    plano.nivel,
                    plano.natureza,
                    plano.grupo,
                    1 if plano.ativo else 0,
                    1 if plano.permite_despesa else 0,
                    1 if plano.eh_folha else 0,
                    1 if plano.candidato_lancavel else 0,
                    1 if plano.observado_ultima_sincronizacao else 0,
                    plano.confiabilidade.value,
                    plano.origem_dado,
                    plano.hash_origem,
                    plano.sincronizado_em.isoformat() if plano.sincronizado_em else None,
                    plano.atualizado_em.isoformat(),
                ),
            )

            if mudou:
                conn.execute(
                    """
                    INSERT INTO master_data_audit_log (
                        tipo_entidade, identificador, empresa_codigo, acao,
                        dados_anteriores_json, dados_novos_json, origem, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        "PLANO_CONTA",
                        str(plano.plano_conta_codigo),
                        None,
                        acao,
                        anterior_json,
                        plano.model_dump_json(),
                        origem_auditoria,
                        agora_iso,
                    ),
                )
        return len(planos)

    def marcar_planos_nao_observados(
        self,
        codigos_observados: set[int],
        timestamp_iso: str,
        hash_origem: Optional[str] = None,
        *,
        origem_auditoria: str = "sincronizacao_webposto_v1",
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Marca planos locais ausentes no retorno oficial como não observados e não lançáveis.

        NUNCA exclui registros locais. Preserva integridade e trilha de auditoria.
        """
        if not codigos_observados:
            return 0
        if conn is not None:
            return self._executar_marcar_planos_nao_observados(
                conn, codigos_observados, timestamp_iso, hash_origem, origem_auditoria
            )
        with self._transacao() as c:
            return self._executar_marcar_planos_nao_observados(
                c, codigos_observados, timestamp_iso, hash_origem, origem_auditoria
            )

    def _executar_marcar_planos_nao_observados(
        self,
        conn: sqlite3.Connection,
        codigos_observados: set[int],
        timestamp_iso: str,
        hash_origem: Optional[str],
        origem_auditoria: str,
    ) -> int:
        todos = conn.execute("SELECT * FROM master_planos_conta").fetchall()
        afetados = 0
        for row in todos:
            cod = int(row["plano_conta_codigo"])
            if cod not in codigos_observados:
                ja_nao_observado = (
                    "observado_ultima_sincronizacao" in row.keys()
                    and row["observado_ultima_sincronizacao"] == 0
                    and row["candidato_lancavel"] == 0
                )
                if ja_nao_observado:
                    continue
                anterior_json = json.dumps(dict(row))
                conn.execute(
                    """
                    UPDATE master_planos_conta
                    SET observado_ultima_sincronizacao = 0,
                        candidato_lancavel = 0,
                        hash_origem = COALESCE(?, hash_origem),
                        atualizado_em = ?
                    WHERE plano_conta_codigo = ?;
                    """,
                    (hash_origem, timestamp_iso, cod),
                )
                novo_row = conn.execute(
                    "SELECT * FROM master_planos_conta WHERE plano_conta_codigo = ?", (cod,)
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO master_data_audit_log (
                        tipo_entidade, identificador, empresa_codigo, acao,
                        dados_anteriores_json, dados_novos_json, origem, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        "PLANO_CONTA",
                        str(cod),
                        None,
                        "ATUALIZACAO",
                        anterior_json,
                        json.dumps(dict(novo_row)) if novo_row else None,
                        origem_auditoria,
                        timestamp_iso,
                    ),
                )
                afetados += 1
        return afetados

    def registrar_sincronizacao_log(
        self,
        log_entry: dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        if conn is not None:
            return self._executar_registrar_sincronizacao_log(conn, log_entry)
        with self._transacao() as c:
            return self._executar_registrar_sincronizacao_log(c, log_entry)

    def _executar_registrar_sincronizacao_log(
        self,
        conn: sqlite3.Connection,
        log_entry: dict[str, Any],
    ) -> int:
        cur = conn.execute(
            """
            INSERT INTO master_sincronizacao_log (
                tipo_entidade, iniciado_em, finalizado_em, sucesso, modo, origem,
                total_oficial, total_anterior, total_inseridos, total_atualizados,
                total_inalterados, total_nao_observados, hash_catalogo, detalhes_json, erro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                log_entry.get("tipo_entidade", "PLANOS_CONTA"),
                log_entry["iniciado_em"],
                log_entry.get("finalizado_em"),
                1 if log_entry.get("sucesso") else 0,
                log_entry["modo"],
                log_entry["origem"],
                log_entry.get("total_oficial", 0),
                log_entry.get("total_anterior", 0),
                log_entry.get("total_inseridos", 0),
                log_entry.get("total_atualizados", 0),
                log_entry.get("total_inalterados", 0),
                log_entry.get("total_nao_observados", 0),
                log_entry.get("hash_catalogo"),
                json.dumps(log_entry.get("detalhes_json", {})),
                log_entry.get("erro"),
            ),
        )
        return cur.lastrowid

    def obter_ultima_sincronizacao(self, tipo_entidade: str = "PLANOS_CONTA") -> Optional[dict[str, Any]]:
        conexao = self._conectar()
        try:
            row = conexao.execute(
                """
                SELECT * FROM master_sincronizacao_log
                WHERE tipo_entidade = ? AND sucesso = 1
                ORDER BY id DESC LIMIT 1;
                """,
                (tipo_entidade,),
            ).fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("detalhes_json"):
                try:
                    res["detalhes_json"] = json.loads(res["detalhes_json"])
                except Exception:
                    pass
            return res
        finally:
            conexao.close()

    def obter_plano_conta(self, plano_codigo: int) -> Optional[MasterPlanoConta]:
        conexao = self._conectar()
        try:
            row = conexao.execute(
                "SELECT * FROM master_planos_conta WHERE plano_conta_codigo = ?", (plano_codigo,)
            ).fetchone()
            if not row:
                return None
            return self._row_para_plano(row)
        finally:
            conexao.close()

    def listar_planos_conta(self) -> List[MasterPlanoConta]:
        conexao = self._conectar()
        try:
            rows = conexao.execute("SELECT * FROM master_planos_conta ORDER BY plano_conta_codigo").fetchall()
            return [self._row_para_plano(row) for row in rows]
        finally:
            conexao.close()

    # ==========================================
    # CENTROS DE CUSTO
    # ==========================================

    def upsert_centro_custo(self, cc: MasterCentroCusto, *, origem_auditoria: str = "sync") -> None:
        with self._transacao() as conn:
            anterior_row = conn.execute(
                "SELECT * FROM master_centros_custo WHERE centro_custo_codigo = ?", (cc.centro_custo_codigo,)
            ).fetchone()
            anterior_json = json.dumps(dict(anterior_row)) if anterior_row else None
            acao = "ATUALIZACAO" if anterior_row else "INSERCAO"

            conn.execute(
                """
                INSERT INTO master_centros_custo (
                    centro_custo_codigo, empresa_codigo, descricao, tipo_abrangencia,
                    ativo, confiabilidade, origem_dado, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(centro_custo_codigo) DO UPDATE SET
                    empresa_codigo = excluded.empresa_codigo,
                    descricao = excluded.descricao,
                    tipo_abrangencia = excluded.tipo_abrangencia,
                    ativo = excluded.ativo,
                    confiabilidade = excluded.confiabilidade,
                    origem_dado = excluded.origem_dado,
                    atualizado_em = excluded.atualizado_em;
                """,
                (
                    cc.centro_custo_codigo,
                    cc.empresa_codigo,
                    cc.descricao,
                    cc.tipo_abrangencia,
                    1 if cc.ativo else 0,
                    cc.confiabilidade.value,
                    cc.origem_dado,
                    cc.atualizado_em.isoformat(),
                ),
            )

            conn.execute(
                """
                INSERT INTO master_data_audit_log (
                    tipo_entidade, identificador, empresa_codigo, acao,
                    dados_anteriores_json, dados_novos_json, origem, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    "CENTRO_CUSTO",
                    str(cc.centro_custo_codigo),
                    cc.empresa_codigo,
                    acao,
                    anterior_json,
                    cc.model_dump_json(),
                    origem_auditoria,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def obter_centro_custo(self, cc_codigo: int) -> Optional[MasterCentroCusto]:
        conexao = self._conectar()
        try:
            row = conexao.execute(
                "SELECT * FROM master_centros_custo WHERE centro_custo_codigo = ?", (cc_codigo,)
            ).fetchone()
            if not row:
                return None
            return MasterCentroCusto(
                centro_custo_codigo=row["centro_custo_codigo"],
                empresa_codigo=row["empresa_codigo"],
                descricao=row["descricao"],
                tipo_abrangencia=row["tipo_abrangencia"],
                ativo=bool(row["ativo"]),
                confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                origem_dado=row["origem_dado"],
                atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
            )
        finally:
            conexao.close()

    def listar_centros_custo(self, empresa_codigo: Optional[int] = None) -> List[MasterCentroCusto]:
        conexao = self._conectar()
        try:
            if empresa_codigo is not None:
                rows = conexao.execute(
                    "SELECT * FROM master_centros_custo WHERE empresa_codigo = ? OR empresa_codigo IS NULL ORDER BY centro_custo_codigo",
                    (empresa_codigo,),
                ).fetchall()
            else:
                rows = conexao.execute("SELECT * FROM master_centros_custo ORDER BY centro_custo_codigo").fetchall()
            return [
                MasterCentroCusto(
                    centro_custo_codigo=row["centro_custo_codigo"],
                    empresa_codigo=row["empresa_codigo"],
                    descricao=row["descricao"],
                    tipo_abrangencia=row["tipo_abrangencia"],
                    ativo=bool(row["ativo"]),
                    confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                    origem_dado=row["origem_dado"],
                    atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
                )
                for row in rows
            ]
        finally:
            conexao.close()

    # ==========================================
    # FORNECEDORES E FAVORECIDOS
    # ==========================================

    def upsert_fornecedor(self, fornecedor: MasterFornecedor, *, origem_auditoria: str = "sync") -> None:
        with self._transacao() as conn:
            # Busca anterior por código ou cnpj_cpf
            anterior_row = None
            if fornecedor.fornecedor_codigo:
                anterior_row = conn.execute(
                    "SELECT * FROM master_fornecedores WHERE fornecedor_codigo = ?", (fornecedor.fornecedor_codigo,)
                ).fetchone()
            elif fornecedor.cnpj_cpf:
                anterior_row = conn.execute(
                    "SELECT * FROM master_fornecedores WHERE cnpj_cpf = ?", (fornecedor.cnpj_cpf,)
                ).fetchone()

            anterior_json = json.dumps(dict(anterior_row)) if anterior_row else None
            acao = "ATUALIZACAO" if anterior_row else "INSERCAO"

            if anterior_row:
                conn.execute(
                    """
                    UPDATE master_fornecedores SET
                        fornecedor_codigo = COALESCE(?, fornecedor_codigo),
                        empresa_codigo = ?,
                        razao_social = ?,
                        nome_fantasia = ?,
                        cnpj_cpf = COALESCE(?, cnpj_cpf),
                        papel = ?,
                        ativo = ?,
                        confiabilidade = ?,
                        origem_dado = ?,
                        atualizado_em = ?
                    WHERE id = ?;
                    """,
                    (
                        fornecedor.fornecedor_codigo,
                        fornecedor.empresa_codigo,
                        fornecedor.razao_social,
                        fornecedor.nome_fantasia,
                        fornecedor.cnpj_cpf,
                        fornecedor.papel.value,
                        1 if fornecedor.ativo else 0,
                        fornecedor.confiabilidade.value,
                        fornecedor.origem_dado,
                        fornecedor.atualizado_em.isoformat(),
                        anterior_row["id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO master_fornecedores (
                        fornecedor_codigo, empresa_codigo, razao_social, nome_fantasia,
                        cnpj_cpf, papel, ativo, confiabilidade, origem_dado, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        fornecedor.fornecedor_codigo,
                        fornecedor.empresa_codigo,
                        fornecedor.razao_social,
                        fornecedor.nome_fantasia,
                        fornecedor.cnpj_cpf,
                        fornecedor.papel.value,
                        1 if fornecedor.ativo else 0,
                        fornecedor.confiabilidade.value,
                        fornecedor.origem_dado,
                        fornecedor.atualizado_em.isoformat(),
                    ),
                )

            identificador = str(fornecedor.fornecedor_codigo or fornecedor.cnpj_cpf or fornecedor.razao_social)
            conn.execute(
                """
                INSERT INTO master_data_audit_log (
                    tipo_entidade, identificador, empresa_codigo, acao,
                    dados_anteriores_json, dados_novos_json, origem, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    "FORNECEDOR",
                    identificador,
                    fornecedor.empresa_codigo,
                    acao,
                    anterior_json,
                    fornecedor.model_dump_json(),
                    origem_auditoria,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def obter_fornecedor(self, fornecedor_codigo: int) -> Optional[MasterFornecedor]:
        conexao = self._conectar()
        try:
            row = conexao.execute(
                "SELECT * FROM master_fornecedores WHERE fornecedor_codigo = ?", (fornecedor_codigo,)
            ).fetchone()
            if not row:
                return None
            return MasterFornecedor(
                fornecedor_codigo=row["fornecedor_codigo"],
                empresa_codigo=row["empresa_codigo"],
                razao_social=row["razao_social"],
                nome_fantasia=row["nome_fantasia"],
                cnpj_cpf=row["cnpj_cpf"],
                papel=PapelEntidade(row["papel"]),
                ativo=bool(row["ativo"]),
                confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                origem_dado=row["origem_dado"],
                atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
            )
        finally:
            conexao.close()

    def obter_fornecedor_por_documento(self, cnpj_cpf: str) -> Optional[MasterFornecedor]:
        conexao = self._conectar()
        try:
            # Limpa pontuação comum para busca
            doc_limpo = "".join(filter(str.isalnum, cnpj_cpf))
            rows = conexao.execute("SELECT * FROM master_fornecedores WHERE cnpj_cpf IS NOT NULL").fetchall()
            for row in rows:
                row_doc = "".join(filter(str.isalnum, row["cnpj_cpf"] or ""))
                if row_doc and row_doc == doc_limpo:
                    return MasterFornecedor(
                        fornecedor_codigo=row["fornecedor_codigo"],
                        empresa_codigo=row["empresa_codigo"],
                        razao_social=row["razao_social"],
                        nome_fantasia=row["nome_fantasia"],
                        cnpj_cpf=row["cnpj_cpf"],
                        papel=PapelEntidade(row["papel"]),
                        ativo=bool(row["ativo"]),
                        confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                        origem_dado=row["origem_dado"],
                        atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
                    )
            return None
        finally:
            conexao.close()

    def listar_fornecedores(self) -> List[MasterFornecedor]:
        conexao = self._conectar()
        try:
            rows = conexao.execute("SELECT * FROM master_fornecedores ORDER BY id").fetchall()
            return [
                MasterFornecedor(
                    fornecedor_codigo=row["fornecedor_codigo"],
                    empresa_codigo=row["empresa_codigo"],
                    razao_social=row["razao_social"],
                    nome_fantasia=row["nome_fantasia"],
                    cnpj_cpf=row["cnpj_cpf"],
                    papel=PapelEntidade(row["papel"]),
                    ativo=bool(row["ativo"]),
                    confiabilidade=ConfiabilidadeCadastro(row["confiabilidade"]),
                    origem_dado=row["origem_dado"],
                    atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
                )
                for row in rows
            ]
        finally:
            conexao.close()

    # ==========================================
    # BACKUP E RECUPERAÇÃO
    # ==========================================

    def executar_backup(self, caminho_destino: Path) -> Path:
        """Executa backup quente consistente do catálogo mestre via VACUUM INTO."""
        destino = Path(caminho_destino).resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            destino.unlink()
        conexao = self._conectar()
        try:
            destino_str = str(destino).replace("'", "''")
            conexao.execute(f"VACUUM INTO '{destino_str}';")
            return destino
        finally:
            conexao.close()

    def restaurar_backup(self, caminho_backup: Path) -> None:
        """Restaura o banco mestre a partir de um arquivo de backup consistente."""
        backup = Path(caminho_backup).resolve()
        if not backup.exists():
            raise FileNotFoundError(f"Arquivo de backup não encontrado: {backup}")

        # Fecha conexões existentes e copia arquivo
        origem = sqlite3.connect(str(backup))
        destino = self._conectar()
        try:
            origem.backup(destino)
        finally:
            origem.close()
            destino.close()
