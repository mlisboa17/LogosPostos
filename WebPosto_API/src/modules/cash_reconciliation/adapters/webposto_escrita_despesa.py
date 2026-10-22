"""Módulo de integração segura e lançamento de despesas no webPosto (EXPENSE-03).

Implementa:
1. Verificação rigorosa das travas de escrita físicas (.env): WEBPOSTO_WRITES=1 e LOGOS_ERP_ESCRITA=1;
2. Validação estrita de aprovação humana individual, versão e hash canônico da proposta;
3. Resolução e validação da empresa contra cadastro oficial (Casa Caiada é 5555, bloqueando códigos espúrios);
4. Modelagem e envio tipado das 3 operações da OpenAPI V1:
   - Operação A: POST /INTEGRACAO/V1/TITULOS_PAGAR (IncluirTituloDto)
   - Operação B: POST /INTEGRACAO/V1/MOVIMENTOS_CONTA (ParametrosIncluirMovimentoConta, contaMovimentoTipo="DEBITO")
   - Operação C: PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR (PagarTituloDto)
5. Vínculo de comprovantes: POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem} (IncluirArquivoFechamentoCaixaDto);
6. Idempotência local e prevenção contra reenvio concorrente via SQLite atômico;
7. Tratamento de timeout sem retry automático (registro de RESULTADO_DESCONHECIDO);
8. Confirmação pós-escrita e auditoria append-only em data/lancamentos_logos/<empresa>/.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import quote, quote_plus

import httpx
from dotenv import load_dotenv
from dotenv.main import DotEnv
from unittest.mock import patch

from ..domain.comprovante import (
    ItemFilaDespesa,
    OperacaoFinanceira,
    StatusDespesa,
)
from ..domain.models import Unidade
from ..domain.tempo import agora
from ..config import carregar_unidades
from .webposto_http import BASE_URL_PADRAO, WebPostoErro

logger = logging.getLogger(__name__)

# Spec oficial: docs/external/webposto/openapi_integracao_2026-10-06.json
CAMPOS_TITULO_PAGAR_SPEC: frozenset[str] = frozenset(
    {
        "descricao",
        "numeroTitulo",
        "fornecedorCodigo",
        "valorParcela",
        "numeroParcelas",
        "dataMovimento",
        "vencimento",
        "planoContaCodigo",
        "centroCustoCodigo",
        "empresaCodigo",
        "observacao",
        "dataValida",
    }
)

CAMPOS_MOVIMENTO_CONTA_SPEC: frozenset[str] = frozenset(
    {
        "descricao",
        "data",
        "valor",
        "conta",
        "documento",
        "centroCusto",
        "planoConta",
        "filial",
        "contaMovimentoTipo",
        "tipoPessoa",
        "pessoa",
    }
)

CAMPOS_BAIXA_TITULO_SPEC: frozenset[str] = frozenset(
    {
        "tituloPagarCodigo",
        "contaCodigo",
        "dataPagamento",
        "dataValida",
        "pagamentoDataPosterior",
    }
)

CAMPOS_ANEXO_SPEC: frozenset[str] = frozenset(
    {
        "nome",
        "conteudo",
    }
)

# Cadastro oficial e allowlist estritamente fechada para despesas operacionais
UNIDADES_AUTORIZADAS_DESPESA: dict[int, dict[str, str]] = {
    74014: {"nome": "POSTO DOZE FILIAL II", "apelido": "Doze"},
    11495: {"nome": "POSTO VIP LTDA", "apelido": "VIP"},
    5555: {"nome": "AP CASA CAIADA", "apelido": "Casa Caiada"},
    118508: {"nome": "CONVENIENCIA 24 HORAS", "apelido": "Conv 24h"},
}
EMPRESAS_AUTORIZADAS_SET: frozenset[int] = frozenset(UNIDADES_AUTORIZADAS_DESPESA.keys())

# Contas financeiras autorizadas por unidade (comprovadas no cadastro oficial units.json e sampleRow V1/CONTAS)
# Posto Doze (74014): BB Depósito Direto (86248), BB Cofre (86081), PagBank (86188)
# Posto VIP (11495): Bradesco Depósito Direto (65321), Itaú Cofre (55028)
# Casa Caiada (5555): BB Cofre "CAIXA(POSTO)" (17837)
# Conveniência 24h (118508): Não possui conta bancária própria (destinos.conta_codigo = null em units.json).
# A conta 17837 pertence à filial 5555; seu uso direto em 118508 é estritamente bloqueado por ambiguidade contábil.
CONTAS_AUTORIZADAS_POR_UNIDADE: dict[int, frozenset[int]] = {
    74014: frozenset({86248, 86081, 86188}),
    11495: frozenset({65321, 55028}),
    5555: frozenset({17837}),
    118508: frozenset(),
}

DIRETORIO_AUDITORIA_DESPESAS_PADRAO = Path("data/lancamentos_logos")
BANCO_IDEMPOTENCIA_PADRAO = Path("data/lancamentos_logos/despesas.sqlite3")

_leitura_env = threading.RLock()
_auditoria_lock = threading.RLock()


class BarreiraDespesaErro(ValueError):
    """Violação de segurança ou regra da barreira de lançamento de despesas."""

    pass


def mensagem_segura(mensagem: str) -> str:
    """Ofusca chaves, senhas e tokens de mensagens de log ou exceção."""
    for nome, valor in os.environ.items():
        if valor and any(
            p in nome.upper() for p in ("CHAVE", "TOKEN", "SECRET", "PASSWORD", "API_KEY", "SENHA")
        ):
            for segredo in {valor, quote(valor, safe=""), quote_plus(valor)}:
                mensagem = mensagem.replace(segredo, "[omitido]")
    mensagem = re.sub(r"(?i)\b(Bearer|Basic)\s+[^\s\"'<>]+", r"\1 [omitido]", mensagem)
    mensagem = re.sub(
        r"(?i)(\b(?:CHAVE|token|access_token|x-api-key|api_key|authorization)\b[\"']?\s*[:=]\s*[\"']?)[^\s&\"'<>]+",
        r"\1[omitido]",
        mensagem,
    )
    return " ".join(mensagem.split())[:500]


def resolver_caminho_env(caminho_env: Path | str | None = None) -> Path:
    """Resolve o arquivo .env físico a ser lido para conferência das travas."""
    if caminho_env is not None:
        return Path(caminho_env)
    p1 = Path(".env")
    if p1.is_file():
        return p1
    p2 = Path("WebPosto_API/.env")
    if p2.is_file():
        return p2
    return p1


def ler_travas_despesa(
    caminho_env: Path | str | None = None,
) -> dict[str, list[tuple[int, str | None]]]:
    """Observa somente as travas enquanto load_dotenv lê o arquivo físico."""
    nomes = {"WEBPOSTO_WRITES", "LOGOS_ERP_ESCRITA"}
    valores: dict[str, list[tuple[int, str | None]]] = {n: [] for n in nomes}
    thread = threading.get_ident()

    class DotEnvTravas(DotEnv):
        def set_as_environment_variables(self):
            if threading.get_ident() != thread:
                return super().set_as_environment_variables()
            for _ in self.parse():
                pass
            return True

        def parse(self):
            if threading.get_ident() != thread:
                yield from super().parse()
                return
            from dotenv.parser import parse_stream

            with self._get_stream() as stream:
                for binding in parse_stream(stream):
                    if binding.error:
                        raise BarreiraDespesaErro(
                            "Arquivo de configuração inválido; confira o .env sem expor credenciais."
                        )
                    if binding.key in nomes:
                        valores[binding.key].append((binding.original.line, binding.value))
                    if binding.key is not None:
                        yield binding.key, binding.value

    arquivo = resolver_caminho_env(caminho_env)
    if not arquivo.is_file():
        raise BarreiraDespesaErro("Arquivo .env não encontrado.")
    with _leitura_env, patch("dotenv.main.DotEnv", DotEnvTravas):
        load_dotenv(arquivo, override=False, interpolate=False)
    return valores


def verificar_travas_despesa(caminho_env: Path | str | None = None) -> tuple[bool, str]:
    """Valida as travas de ambiente LENDO EXCLUSIVAMENTE o arquivo .env físico.

    Regra ADR-003 / P0 Financeiro:
    - Lê exclusivamente o arquivo .env físico sem confiar em os.environ;
    - Se WEBPOSTO_WRITES ou LOGOS_ERP_ESCRITA aparecer duplicado, recusa com erro;
    - Ambas as travas devem ser estritamente '1' no arquivo .env.
    """
    try:
        valores = ler_travas_despesa(caminho_env)
    except (OSError, BarreiraDespesaErro) as exc:
        return False, f"Falha ao ler travas do arquivo .env: {mensagem_segura(str(exc))}"
    for k in ("WEBPOSTO_WRITES", "LOGOS_ERP_ESCRITA"):
        linhas = [n for n, _ in valores.get(k, [])]
        if len(linhas) > 1:
            return False, f"Trava {k} duplicada no .env, linhas {linhas[0]} e {linhas[1]}."
        if len(valores.get(k, [])) != 1 or valores[k][0][1] != "1":
            return False, f"Trava {k} != 1 no arquivo .env (escrita bloqueada no ERP)."
    return True, "Travas de escrita liberadas no arquivo .env."


def validar_conta_financeira_unidade(
    empresa_codigo: int,
    conta_codigo: int | None,
    mapa_contas_unidade: dict[int, set[int] | frozenset[int]] | None = None,
) -> int:
    """Valida se a conta financeira pertence de forma comprovada à empresa selecionada.

    Bloqueia:
    - Conta nula, booleana, zero ou não identificada;
    - Conta pertencente a outra empresa;
    - Contas não comprovadas no cadastro oficial da unidade (units.json).
    """
    cod_empresa = validar_unidade_autorizada(empresa_codigo)

    if isinstance(conta_codigo, bool):
        raise BarreiraDespesaErro("Código de conta financeira inválido (booleano não permitido).")

    if conta_codigo is None:
        raise BarreiraDespesaErro("Conta financeira não identificada para o lançamento.")

    try:
        cod_conta = int(conta_codigo)
    except (ValueError, TypeError):
        raise BarreiraDespesaErro(f"Código de conta financeira inválido: {conta_codigo}")

    if cod_conta <= 0:
        raise BarreiraDespesaErro(f"Código de conta financeira inválido: {cod_conta}")

    mapa = mapa_contas_unidade or CONTAS_AUTORIZADAS_POR_UNIDADE
    contas_permitidas = mapa.get(cod_empresa, frozenset())

    if cod_conta not in contas_permitidas:
        outras = [emp for emp, contas in mapa.items() if cod_conta in contas and emp != cod_empresa]
        if outras:
            raise BarreiraDespesaErro(
                f"Conta financeira {cod_conta} pertence a outra unidade ({outras[0]}), não à empresa {cod_empresa}. Lançamento bloqueado por segurança contábil."
            )
        raise BarreiraDespesaErro(
            f"Conta financeira {cod_conta} não pertence nem está cadastrada para a empresa {cod_empresa}."
        )

    return cod_conta


def validar_unidade_autorizada(
    empresa_codigo: int | None,
    unidades_cadastradas: dict[int, Any] | None = None,
) -> int:
    """Valida o código da empresa contra o cadastro oficial (Bloqueio P0 / Escopo).

    Garante que:
    1. Empresa não pode ser nula, booleana ou indefinida;
    2. Posto Real (empresaCodigo 5558 / codWeb 7) é expressamente excluído do escopo do Expense Hunter (CNPJ desativado);
    3. Casa Caiada é estritamente 5555;
    4. Códigos espúrios (como 12607 ou 12705) são rejeitados com erro explícito;
    5. Não ocorre fallback cego para o Doze;
    6. Allowlist FECHADA: Apenas Doze (74014), VIP (11495), Casa Caiada (5555) e Conv 24h (118508) são autorizadas.
    7. Cadastros externos (unidades_cadastradas) podem confirmar se a unidade está ativa, mas NUNCA expandir a allowlist.
    """
    if isinstance(empresa_codigo, bool):
        raise BarreiraDespesaErro("Código de empresa inválido (booleano não permitido).")

    if empresa_codigo is None:
        raise BarreiraDespesaErro("Empresa não identificada (empresaCodigo ausente).")

    if isinstance(empresa_codigo, str) and not empresa_codigo.strip():
        raise BarreiraDespesaErro("Código de empresa vazio.")

    try:
        cod = int(empresa_codigo)
    except (ValueError, TypeError):
        raise BarreiraDespesaErro(f"Código de empresa inválido: {empresa_codigo}")

    # Checagens explícitas de escopo e divergências investigadas
    if cod in (5558, 7):
        raise BarreiraDespesaErro(
            "Posto Real (empresaCodigo 5558 / codWeb 7) não faz parte do escopo do Expense Hunter (CNPJ desativado/inativo)."
        )
    if cod == 12607:
        raise BarreiraDespesaErro(
            "Empresa 12607 não existe no webPosto. O código oficial de Casa Caiada é 5555."
        )
    if cod == 12705:
        raise BarreiraDespesaErro("Empresa 12705 não existe no webPosto.")

    # Base de unidades autorizadas: allowlist ESTRITAMENTE FECHADA
    if cod not in EMPRESAS_AUTORIZADAS_SET:
        raise BarreiraDespesaErro(
            f"Empresa {cod} não é autorizada para lançamento operacional de despesas."
        )

    # Cadastros externos NUNCA ampliam a allowlist, apenas validam se fornecidos
    if unidades_cadastradas is not None and cod not in unidades_cadastradas:
        raise BarreiraDespesaErro(
            f"Empresa {cod} não encontrada no cadastro de unidades fornecido."
        )

    return cod


def validar_aprovacao_para_escrita(
    item: ItemFilaDespesa,
    unidades_cadastradas: dict[int, Any] | None = None,
    master_data_service: Any | None = None,
) -> None:
    """Verifica com estrita governança se a despesa está apta para integração ERP.

    Se houver divergência de versão, hash ou dados aprovados, a aprovação é
    automaticamente INVALIDADA e o item retorna para aguardando_revisao.
    Consome o MasterDataService para validação profunda de integridade cadastral.
    """
    if item.status != StatusDespesa.APROVADO.value:
        raise BarreiraDespesaErro(
            f"Lançamento recusado: status atual é '{item.status}' (exige '{StatusDespesa.APROVADO.value}')."
        )

    if not item.aprovado_por:
        raise BarreiraDespesaErro("Lançamento recusado: identificação do aprovador ausente.")

    # Validação de empresa
    cod_empresa = validar_unidade_autorizada(item.unidade_codigo, unidades_cadastradas)

    # Validação via MasterDataService (MASTER-DATA-02)
    if master_data_service is not None:
        res_emp = master_data_service.resolver_empresa(cod_empresa)
        if not res_emp.sucesso or res_emp.bloqueada:
            raise BarreiraDespesaErro(f"Empresa bloqueada pelo Master Data: {res_emp.mensagem}")

    # Validação de operação pretendida vs aprovada
    if item.operacao_financeira != item.aprovado_operacao:
        item.status = StatusDespesa.AGUARDANDO_REVISAO.value
        item.motivo_bloqueio = "Aprovação invalidada: operação pretendida diverge da aprovada."
        item.aprovado_por = None
        raise BarreiraDespesaErro(
            f"Operação financeira pretendida ({item.operacao_financeira}) difere da operação aprovada ({item.aprovado_operacao})."
        )

    # Validação de versão e hash canônico
    hash_atual = item.calcular_hash_conteudo()
    if item.versao != item.aprovado_versao or hash_atual != item.aprovado_hash:
        # Invalidação da aprovação defasada
        item.status = StatusDespesa.AGUARDANDO_REVISAO.value
        item.motivo_bloqueio = (
            "Aprovação invalidada: o conteúdo da proposta foi alterado após a aprovação."
        )
        item.aprovado_por = None
        item.aprovado_hash = None
        raise BarreiraDespesaErro(
            "Aprovação invalidada: o conteúdo da proposta foi alterado após a aprovação."
        )

    # Validações específicas por tipo de operação
    if item.operacao_financeira == OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value:
        if not item.sugestao_fornecedor_codigo or item.sugestao_fornecedor_codigo <= 0:
            raise BarreiraDespesaErro(
                "Fornecedor obrigatório não cadastrado ou não identificado para conta a pagar."
            )
        if not item.comprovante.valor or item.comprovante.valor <= Decimal(0):
            raise BarreiraDespesaErro("Valor da despesa inválido ou zerado.")
        if not item.sugestao_plano_codigo or item.sugestao_plano_codigo <= 0:
            raise BarreiraDespesaErro("Plano de contas obrigatório não informado.")

    elif item.operacao_financeira == OperacaoFinanceira.DESPESA_JA_PAGA.value:
        if not item.conta_financeira_codigo or item.conta_financeira_codigo <= 0:
            raise BarreiraDespesaErro(
                "Conta financeira de débito não identificada ou não autorizada."
            )
        validar_conta_financeira_unidade(cod_empresa, item.conta_financeira_codigo)
        if not item.debito_casado_fitid and not item.comprovante.banco_origem:
            raise BarreiraDespesaErro(
                "Pagamento não comprovado para operação de débito em conta (sem evidência de quitação)."
            )

    elif item.operacao_financeira == OperacaoFinanceira.TITULO_EXISTENTE.value:
        if not item.titulo_casado_codigo or item.titulo_casado_codigo <= 0:
            raise BarreiraDespesaErro(
                "Título a pagar correspondente não identificado no webPosto para baixa."
            )
        if not item.conta_financeira_codigo or item.conta_financeira_codigo <= 0:
            raise BarreiraDespesaErro(
                "Conta financeira de liquidação não identificada para baixa do título."
            )
        validar_conta_financeira_unidade(cod_empresa, item.conta_financeira_codigo)
        if not item.debito_casado_fitid and not item.comprovante.banco_origem:
            raise BarreiraDespesaErro("Pagamento não comprovado para baixa de título existente.")

    else:
        raise BarreiraDespesaErro(
            f"Operação financeira inválida para integração: {item.operacao_financeira}"
        )

    # Validação profunda com MasterDataService (Contas, Planos, Centros de Custo)
    if master_data_service is not None:
        if item.conta_financeira_codigo:
            res_conta = master_data_service.resolver_conta_financeira(
                item.conta_financeira_codigo, empresa_codigo=cod_empresa
            )
            if not res_conta.sucesso:
                raise BarreiraDespesaErro(
                    f"Conta financeira não identificada no Master Data: {res_conta.mensagem}"
                )
            if res_conta.bloqueada_debito:
                raise BarreiraDespesaErro(
                    f"Conta financeira não autorizada para débito no Master Data: {res_conta.mensagem}"
                )
            if item.operacao_financeira in (
                OperacaoFinanceira.DESPESA_JA_PAGA.value,
                OperacaoFinanceira.TITULO_EXISTENTE.value,
            ):
                if res_conta.conta and not res_conta.conta.permite_debito_despesa:
                    raise BarreiraDespesaErro(
                        f"Vínculo bancário não comprovado para a conta {item.conta_financeira_codigo} no Master Data."
                    )

        if item.sugestao_plano_codigo:
            res_plano = master_data_service.resolver_plano_contas(item.sugestao_plano_codigo)
            if not res_plano.sucesso:
                raise BarreiraDespesaErro(
                    f"Plano de contas inválido no Master Data: {res_plano.mensagem}"
                )

        if item.sugestao_centro_codigo:
            tipo_desp = "PRO_LABORE" if item.sugestao_plano_codigo == 29021 else "OPERACIONAL"
            res_cc = master_data_service.resolver_centro_custo(
                item.sugestao_centro_codigo,
                empresa_codigo=cod_empresa,
                tipo_despesa=tipo_desp,
            )
            if not res_cc.sucesso:
                raise BarreiraDespesaErro(
                    f"Centro de custo incompatível no Master Data: {res_cc.mensagem}"
                )


def calcular_chave_idempotencia(item: ItemFilaDespesa) -> str:
    """Calcula hash determinístico unívoco para a operação financeira."""
    raw = (
        f"{item.id}:{item.versao}:{item.aprovado_hash}:{item.operacao_financeira}:"
        f"{item.unidade_codigo}:{item.comprovante.valor}:{item.conta_financeira_codigo}:"
        f"{item.titulo_casado_codigo}:{item.sugestao_fornecedor_codigo}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AutorizacaoPilotoDespesa:
    """Escopo criptográfico estrito para autorização de uma única escrita em piloto controlado."""

    operacao_id: str
    empresa_codigo: int
    tipo_operacao: str
    valor: float
    hash_aprovado: str
    autorizador_id: str
    expira_em: str
    conta_codigo: int | None = None
    token_hash: str = ""
    consumida_em: str | None = None
    criada_em: str = ""


class GerenciadorAutorizacaoPiloto:
    """Gerenciador atômico de tokens de autorização fina para o piloto de despesas."""

    def __init__(self, caminho_banco: Path | str | None = None):
        self.caminho = (
            Path(caminho_banco) if caminho_banco is not None else BANCO_IDEMPOTENCIA_PADRAO
        )
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._inicializar()

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.caminho), timeout=30.0)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def _inicializar(self) -> None:
        with self._conectar() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS autorizacoes_piloto (
                    token_hash TEXT PRIMARY KEY,
                    operacao_id TEXT NOT NULL,
                    empresa_codigo INTEGER NOT NULL,
                    tipo_operacao TEXT NOT NULL,
                    conta_codigo INTEGER,
                    valor REAL NOT NULL,
                    hash_aprovado TEXT NOT NULL,
                    autorizador_id TEXT NOT NULL,
                    expira_em TEXT NOT NULL,
                    consumida_em TEXT,
                    criada_em TEXT NOT NULL
                )
            """)

    def criar_autorizacao(
        self,
        operacao_id: str,
        empresa_codigo: int,
        tipo_operacao: str,
        valor: float | Decimal,
        hash_aprovado: str,
        autorizador_id: str,
        conta_codigo: int | None = None,
        validade_minutos: int = 30,
    ) -> str:
        """Gera e armazena token único com prazo estrito para autorizar UMA escrita de piloto.

        Retorna o token em texto puro apenas para o chamador. Nunca persiste nem loga o token.
        """
        validar_unidade_autorizada(empresa_codigo)
        if conta_codigo is not None:
            validar_conta_financeira_unidade(empresa_codigo, conta_codigo)

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        agora_dt = agora()
        expira_em = (agora_dt + timedelta(minutes=validade_minutos)).isoformat()
        criada_em = agora_dt.isoformat()

        with self._conectar() as con:
            con.execute(
                """
                INSERT INTO autorizacoes_piloto (
                    token_hash, operacao_id, empresa_codigo, tipo_operacao,
                    conta_codigo, valor, hash_aprovado, autorizador_id,
                    expira_em, consumida_em, criada_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    token_hash,
                    str(operacao_id),
                    int(empresa_codigo),
                    str(tipo_operacao),
                    int(conta_codigo) if conta_codigo is not None else None,
                    float(valor),
                    str(hash_aprovado),
                    str(autorizador_id),
                    expira_em,
                    criada_em,
                ),
            )
        return token

    def consumir_autorizacao(
        self,
        token: str,
        item: ItemFilaDespesa,
        conta_codigo_execucao: int | None = None,
    ) -> AutorizacaoPilotoDespesa:
        """Valida identidade exata em 8 dimensões e consome atomicamente o token."""
        if not token or not isinstance(token, str):
            raise BarreiraDespesaErro("Token de autorização de piloto ausente ou inválido.")

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        agora_iso = agora().isoformat()

        with self._conectar() as con:
            con.execute("BEGIN IMMEDIATE")
            cur = con.execute(
                "SELECT token_hash, operacao_id, empresa_codigo, tipo_operacao, conta_codigo, valor, hash_aprovado, autorizador_id, expira_em, consumida_em, criada_em FROM autorizacoes_piloto WHERE token_hash = ?",
                (token_hash,),
            )
            linha = cur.fetchone()
            if not linha:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro("Autorização de piloto inexistente ou token inválido.")

            t_hash, op_id, emp_cod, tp_op, c_cod, val, h_apr, aut_id, exp_em, cons_em, cri_em = (
                linha
            )

            if cons_em is not None:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro(
                    f"Autorização de piloto já consumida em {cons_em}. Reutilização proibida."
                )

            if agora_iso > exp_em:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro(f"Autorização de piloto expirada em {exp_em}.")

            # Validação de escopo estrito
            if op_id != item.id:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro(
                    f"Autorização de piloto pertence à operação '{op_id}', não à despesa '{item.id}'."
                )

            if emp_cod != item.unidade_codigo:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro(
                    f"Autorização de piloto pertence à empresa {emp_cod}, não à {item.unidade_codigo}."
                )

            if tp_op != item.operacao_financeira:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro(
                    f"Autorização de piloto é para operação '{tp_op}', não '{item.operacao_financeira}'."
                )

            if abs(val - float(item.comprovante.valor or 0)) >= 0.001:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro(
                    f"Autorização de piloto vinculada ao valor R$ {val:.2f}, proposta tem R$ {float(item.comprovante.valor or 0):.2f}."
                )

            if h_apr != item.aprovado_hash:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro(
                    "Autorização de piloto vinculada a hash aprovado divergente."
                )

            conta_efetiva = conta_codigo_execucao or item.conta_financeira_codigo
            if c_cod is not None and c_cod != conta_efetiva:
                con.execute("ROLLBACK")
                raise BarreiraDespesaErro(
                    f"Autorização de piloto vinculada à conta {c_cod}, operação pretende usar conta {conta_efetiva}."
                )

            # Consome atomicamente
            con.execute(
                "UPDATE autorizacoes_piloto SET consumida_em = ? WHERE token_hash = ?",
                (agora_iso, token_hash),
            )
            con.execute("COMMIT")

            return AutorizacaoPilotoDespesa(
                operacao_id=op_id,
                empresa_codigo=emp_cod,
                tipo_operacao=tp_op,
                valor=val,
                hash_aprovado=h_apr,
                autorizador_id=aut_id,
                expira_em=exp_em,
                conta_codigo=c_cod,
                token_hash=t_hash,
                consumida_em=agora_iso,
                criada_em=cri_em,
            )


class IdempotenciaDespesas:
    """Controle atômico de idempotência e transições de estado pré/pós escrita."""

    def __init__(self, caminho_banco: Path | str | None = None):
        self.caminho = (
            Path(caminho_banco) if caminho_banco is not None else BANCO_IDEMPOTENCIA_PADRAO
        )
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._inicializar()

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.caminho), timeout=30.0)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def _inicializar(self) -> None:
        with self._conectar() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS operacoes_despesas (
                    chave_idempotencia TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    versao INTEGER NOT NULL,
                    hash_aprovado TEXT NOT NULL,
                    operacao TEXT NOT NULL,
                    empresa_codigo INTEGER NOT NULL,
                    valor REAL NOT NULL,
                    estado TEXT NOT NULL,
                    id_erp TEXT,
                    detalhes TEXT,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                )
            """)

    def iniciar_operacao(self, chave: str, item: ItemFilaDespesa) -> None:
        """Reserva atomicamente a execução da operação impedindo concorrência."""
        agora_iso = agora().isoformat()
        with self._conectar() as con:
            con.execute("BEGIN IMMEDIATE")
            cur = con.execute(
                "SELECT estado, id_erp FROM operacoes_despesas WHERE chave_idempotencia = ?",
                (chave,),
            )
            linha = cur.fetchone()
            if linha:
                estado_atual, id_erp = linha
                if estado_atual in ("CONFIRMADO", "EM_EXECUCAO", "RESULTADO_DESCONHECIDO"):
                    con.execute("ROLLBACK")
                    raise BarreiraDespesaErro(
                        f"Operação já em andamento ou concluída (estado: {estado_atual}, id ERP: {id_erp}). Reenvio bloqueado."
                    )
                # Se falhou sem envio anterior, permite nova tentativa
                con.execute(
                    "UPDATE operacoes_despesas SET estado = 'EM_EXECUCAO', atualizado_em = ? WHERE chave_idempotencia = ?",
                    (agora_iso, chave),
                )
            else:
                con.execute(
                    """
                    INSERT INTO operacoes_despesas (
                        chave_idempotencia, item_id, versao, hash_aprovado,
                        operacao, empresa_codigo, valor, estado, id_erp, detalhes,
                        criado_em, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'EM_EXECUCAO', NULL, NULL, ?, ?)
                    """,
                    (
                        chave,
                        item.id,
                        item.versao,
                        item.aprovado_hash or "",
                        item.operacao_financeira,
                        item.unidade_codigo or 0,
                        float(item.comprovante.valor or 0),
                        agora_iso,
                        agora_iso,
                    ),
                )
            con.execute("COMMIT")

    def confirmar_operacao(self, chave: str, id_erp: str | int | None, detalhes: str = "") -> None:
        """Marca a operação como confirmada com o identificador do ERP."""
        agora_iso = agora().isoformat()
        with self._conectar() as con:
            con.execute(
                "UPDATE operacoes_despesas SET estado = 'CONFIRMADO', id_erp = ?, detalhes = ?, atualizado_em = ? WHERE chave_idempotencia = ?",
                (str(id_erp) if id_erp is not None else None, detalhes, agora_iso, chave),
            )

    def marcar_resultado_desconhecido(self, chave: str, motivo: str) -> None:
        """Registra que o envio ocorreu mas a resposta é incerta (ex: timeout). Reenvio automático proibido."""
        agora_iso = agora().isoformat()
        with self._conectar() as con:
            con.execute(
                "UPDATE operacoes_despesas SET estado = 'RESULTADO_DESCONHECIDO', detalhes = ?, atualizado_em = ? WHERE chave_idempotencia = ?",
                (motivo, agora_iso, chave),
            )

    def marcar_falha_sem_envio(self, chave: str, motivo: str) -> None:
        """Registra falha antes do envio ou rejeição clara da API."""
        agora_iso = agora().isoformat()
        with self._conectar() as con:
            con.execute(
                "UPDATE operacoes_despesas SET estado = 'FALHOU_SEM_ENVIO', detalhes = ?, atualizado_em = ? WHERE chave_idempotencia = ?",
                (motivo, agora_iso, chave),
            )


# ---------------------------------------------------------------------------
# Montagem de Payloads estritamente conformes à OpenAPI V1
# ---------------------------------------------------------------------------


def montar_payload_titulo_pagar(
    item: ItemFilaDespesa,
    unidade: Unidade,
    fornecedor_codigo: int | None = None,
    numero_titulo: str | None = None,
    data_movimento: date | str | None = None,
    vencimento: date | str | None = None,
) -> dict[str, Any]:
    """Monta payload para POST /INTEGRACAO/V1/TITULOS_PAGAR (IncluirTituloDto)."""
    cod_empresa = validar_unidade_autorizada(item.unidade_codigo)
    forn_cod = fornecedor_codigo or item.sugestao_fornecedor_codigo
    if not forn_cod or int(forn_cod) <= 0:
        raise BarreiraDespesaErro("Fornecedor obrigatório não cadastrado ou não informado.")

    if not item.comprovante.valor or item.comprovante.valor <= Decimal(0):
        raise BarreiraDespesaErro("Valor da despesa inválido.")

    # Determinação das datas (YYYY-MM-DD)
    data_mov_raw = data_movimento or item.comprovante.data or agora().date()
    data_mov_str = (
        data_mov_raw.isoformat() if hasattr(data_mov_raw, "isoformat") else str(data_mov_raw)
    )

    venc_raw = vencimento or item.data_vencimento or item.comprovante.data or agora().date()
    venc_str = venc_raw.isoformat() if hasattr(venc_raw, "isoformat") else str(venc_raw)

    num_doc = (numero_titulo or item.numero_documento or f"TIT-{item.id[:8]}").strip()
    descricao = (
        item.comprovante.descricao or f"Despesa {item.sugestao_plano_nome or 'Operacional'}"
    ).strip()[:100]

    payload: dict[str, Any] = {
        "descricao": descricao,
        "numeroTitulo": num_doc,
        "fornecedorCodigo": int(forn_cod),
        "valorParcela": float(item.comprovante.valor),
        "numeroParcelas": 1,
        "dataMovimento": data_mov_str,
        "vencimento": venc_str,
        "planoContaCodigo": int(item.sugestao_plano_codigo or 198595),
        "centroCustoCodigo": (
            int(item.sugestao_centro_codigo) if item.sugestao_centro_codigo else None
        ),
        "empresaCodigo": cod_empresa,  # Obrigatório para evitar fallback no ERP
        "observacao": (item.audio_ou_texto_complementar or "")[:255] or None,
        "dataValida": True,
    }

    chaves_invalidas = set(payload.keys()) - CAMPOS_TITULO_PAGAR_SPEC
    if chaves_invalidas:
        raise BarreiraDespesaErro(
            f"Payload de Título a Pagar contém campos fora da especificação: {chaves_invalidas}"
        )

    return payload


def montar_payload_movimento_conta(
    item: ItemFilaDespesa,
    unidade: Unidade,
    conta_codigo: int | None = None,
    data_movimento: date | str | None = None,
) -> dict[str, Any]:
    """Monta payload para POST /INTEGRACAO/V1/MOVIMENTOS_CONTA (ParametrosIncluirMovimentoConta)."""
    cod_empresa = validar_unidade_autorizada(item.unidade_codigo)
    conta_cod = conta_codigo or item.conta_financeira_codigo
    if not conta_cod or int(conta_cod) <= 0:
        raise BarreiraDespesaErro("Conta financeira de débito não informada ou inválida.")

    if not item.comprovante.valor or item.comprovante.valor <= Decimal(0):
        raise BarreiraDespesaErro("Valor da despesa inválido.")

    data_raw = data_movimento or item.comprovante.data or agora().date()
    data_str = data_raw.isoformat() if hasattr(data_raw, "isoformat") else str(data_raw)

    num_doc = (item.numero_documento or f"MOV-{item.id[:8]}").strip()
    descricao = (
        item.comprovante.descricao or f"Débito {item.sugestao_plano_nome or 'Operacional'}"
    ).strip()[:100]

    payload: dict[str, Any] = {
        "descricao": descricao,
        "data": data_str,
        "valor": float(item.comprovante.valor),
        "conta": int(conta_cod),
        "documento": num_doc,
        "centroCusto": int(item.sugestao_centro_codigo) if item.sugestao_centro_codigo else None,
        "planoConta": int(item.sugestao_plano_codigo) if item.sugestao_plano_codigo else None,
        "filial": cod_empresa,
        "contaMovimentoTipo": "DEBITO",  # Obrigatório ser débito
        "tipoPessoa": "FORNECEDOR" if item.sugestao_fornecedor_codigo else "NAO_IDENTIFICADO",
        "pessoa": int(item.sugestao_fornecedor_codigo) if item.sugestao_fornecedor_codigo else None,
    }

    chaves_invalidas = set(payload.keys()) - CAMPOS_MOVIMENTO_CONTA_SPEC
    if chaves_invalidas:
        raise BarreiraDespesaErro(
            f"Payload de Movimento de Conta contém campos fora da especificação: {chaves_invalidas}"
        )

    return payload


def montar_payload_baixa_titulo(
    item: ItemFilaDespesa,
    unidade: Unidade,
    titulo_pagar_codigos: list[int] | None = None,
    conta_codigo: int | None = None,
    data_pagamento: date | str | None = None,
) -> dict[str, Any]:
    """Monta payload para PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR (PagarTituloDto)."""
    validar_unidade_autorizada(item.unidade_codigo)
    titulos = titulo_pagar_codigos or (
        [item.titulo_casado_codigo] if item.titulo_casado_codigo else []
    )
    if not titulos or any(not isinstance(t, int) or t <= 0 for t in titulos):
        raise BarreiraDespesaErro("Nenhum título a pagar válido informado para liquidação.")

    conta_cod = conta_codigo or item.conta_financeira_codigo
    if not conta_cod or int(conta_cod) <= 0:
        raise BarreiraDespesaErro("Conta financeira de liquidação não informada ou inválida.")

    data_raw = data_pagamento or item.comprovante.data or agora().date()
    data_str = data_raw.isoformat() if hasattr(data_raw, "isoformat") else str(data_raw)

    payload: dict[str, Any] = {
        "tituloPagarCodigo": titulos,  # Array de int32 conforme OpenAPI
        "contaCodigo": int(conta_cod),
        "dataPagamento": data_str,
        "dataValida": True,
        "pagamentoDataPosterior": False,
    }

    chaves_invalidas = set(payload.keys()) - CAMPOS_BAIXA_TITULO_SPEC
    if chaves_invalidas:
        raise BarreiraDespesaErro(
            f"Payload de Baixa de Título contém campos fora da especificação: {chaves_invalidas}"
        )

    return payload


def montar_payload_anexo(
    nome_arquivo: str,
    conteudo_bytes: bytes,
) -> dict[str, Any]:
    """Monta payload para POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}."""
    if not nome_arquivo:
        raise BarreiraDespesaErro("Nome do arquivo de comprovante ausente.")
    if not conteudo_bytes:
        raise BarreiraDespesaErro("Conteúdo do arquivo de comprovante vazio.")

    payload = {
        "nome": Path(nome_arquivo).name,
        "conteudo": base64.b64encode(conteudo_bytes).decode("ascii"),
    }

    chaves_invalidas = set(payload.keys()) - CAMPOS_ANEXO_SPEC
    if chaves_invalidas:
        raise BarreiraDespesaErro(
            f"Payload de Anexo contém campos fora da especificação: {chaves_invalidas}"
        )

    return payload


# ---------------------------------------------------------------------------
# Confirmação Pós-Escrita via Consulta
# ---------------------------------------------------------------------------


async def confirmar_titulo_pagar(
    http: httpx.AsyncClient,
    unidade: Unidade,
    titulo_id: int,
) -> bool:
    """Verifica se o título incluído existe ativamente no webPosto."""
    chave = os.getenv(unidade.chave_env, "")
    headers = {"x-api-key": chave}
    url = f"{BASE_URL_PADRAO}/INTEGRACAO/V1/TITULOS_PAGAR"
    params = {
        "empresaCodigo": unidade.empresa_codigo,
        "tituloPagarCodigo": titulo_id,
        "limite": 1,
    }
    try:
        resp = await http.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            dados = resp.json()
            itens = dados.get("resultados", [])
            return len(itens) > 0
        return False
    except Exception as exc:
        logger.warning("Falha ao confirmar título a pagar: %s", mensagem_segura(str(exc)))
        return False


async def confirmar_movimento_conta(
    http: httpx.AsyncClient,
    unidade: Unidade,
    item: ItemFilaDespesa,
) -> dict[str, Any] | None:
    """Localiza o movimento de conta recém-lançado via GET /INTEGRACAO/V1/MOVIMENTOS_CONTA.

    Regra P0:
    - Se encontrar exatamente 1 movimento correspondente: confirma com segurança;
    - Se encontrar múltiplos movimentos com o mesmo valor/data/conta (ambiguidade):
      recusa a confirmação e retorna None para evitar vincular ao registro errado;
    - Se não encontrar nenhum: retorna None.
    """
    chave = os.getenv(unidade.chave_env, "")
    headers = {"x-api-key": chave}
    url = f"{BASE_URL_PADRAO}/INTEGRACAO/V1/MOVIMENTOS_CONTA"
    data_iso = (
        item.comprovante.data.isoformat() if item.comprovante.data else agora().date().isoformat()
    )
    params = {
        "empresaCodigo": unidade.empresa_codigo,
        "dataInicial": data_iso,
        "dataFinal": data_iso,
        "contaCodigo": item.conta_financeira_codigo or 0,
        "limite": 100,
    }
    try:
        resp = await http.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            dados = resp.json()
            resultados = dados.get("resultados", [])
            candidatos = []
            for r in resultados:
                val = r.get("valor")
                tipo = str(r.get("tipo") or r.get("contaMovimentoTipo") or "").upper()
                if val is not None and abs(float(val) - float(item.comprovante.valor or 0)) < 0.01:
                    if tipo in ("DEBITO", "D"):
                        candidatos.append(r)
            if len(candidatos) == 1:
                return candidatos[0]
            if len(candidatos) > 1:
                logger.warning(
                    "Confirmação ambígua: encontrados %d movimentos com mesmo valor %s na conta %s em %s. Lançamento não pode ser confirmado unívocamente.",
                    len(candidatos),
                    item.comprovante.valor,
                    item.conta_financeira_codigo,
                    data_iso,
                )
                return None
        return None
    except Exception as exc:
        logger.warning("Falha ao confirmar movimento de conta: %s", mensagem_segura(str(exc)))
        return None


async def confirmar_baixa_titulo(
    http: httpx.AsyncClient,
    unidade: Unidade,
    titulo_id: int,
) -> bool:
    """Confirma que o título a pagar foi liquidado no ERP."""
    chave = os.getenv(unidade.chave_env, "")
    headers = {"x-api-key": chave}
    url = f"{BASE_URL_PADRAO}/INTEGRACAO/V1/TITULOS_PAGAR"
    params = {
        "empresaCodigo": unidade.empresa_codigo,
        "tituloPagarCodigo": titulo_id,
        "limite": 1,
    }
    try:
        resp = await http.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            dados = resp.json()
            itens = dados.get("resultados", [])
            if itens:
                tit = itens[0]
                situacao = str(tit.get("situacao") or "").upper()
                data_pgto = tit.get("dataPagamento")
                return bool(data_pgto or situacao in ("PAGO", "QUITADO", "BAIXADO"))
        return False
    except Exception as exc:
        logger.warning("Falha ao confirmar baixa de título: %s", mensagem_segura(str(exc)))
        return False


# ---------------------------------------------------------------------------
# Envio de Anexo de Comprovante
# ---------------------------------------------------------------------------


async def anexar_comprovante_despesa(
    unidade: Unidade,
    tipo_origem: str,
    origem_id: int,
    caminho_arquivo: Path | str,
    *,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Anexa o arquivo de comprovante digital via POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}.

    Tipos de origem permitidos na OpenAPI: 'MOVIMENTO_CONTA_MANUAL' ou 'TITULO_PAGAR'.
    Falha no envio de anexo NÃO reverte nem repete o lançamento financeiro original.
    """
    if tipo_origem not in ("MOVIMENTO_CONTA_MANUAL", "TITULO_PAGAR"):
        raise BarreiraDespesaErro(f"tipoOrigem de anexo inválido: {tipo_origem}")

    arq = Path(caminho_arquivo)
    if not arq.is_file():
        return {"sucesso": False, "motivo": f"Arquivo não encontrado: {arq}"}

    conteudo = arq.read_bytes()
    payload = montar_payload_anexo(arq.name, conteudo)

    chave = os.getenv(unidade.chave_env, "")
    url = f"{BASE_URL_PADRAO}/INTEGRACAO/V1/ARQUIVOS/{tipo_origem}/{origem_id}"
    headers = {"x-api-key": chave, "Content-Type": "application/json"}

    try:
        resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
        if resp.status_code in (200, 201):
            return {"sucesso": True, "resposta": resp.json() if resp.text else {}}
        return {
            "sucesso": False,
            "status_code": resp.status_code,
            "detalhe": mensagem_segura(resp.text),
        }
    except Exception as exc:
        logger.error("Falha ao enviar anexo de comprovante: %s", mensagem_segura(str(exc)))
        return {"sucesso": False, "erro": mensagem_segura(str(exc))}


# ---------------------------------------------------------------------------
# Auditoria Append-Only
# ---------------------------------------------------------------------------


def gravar_auditoria_despesa(
    empresa_codigo: int,
    registro: dict[str, Any],
    diretorio_base: Path | str | None = None,
) -> Path:
    """Grava um registro de auditoria append-only em historico_despesas.json."""
    with _auditoria_lock:
        base = (
            Path(diretorio_base)
            if diretorio_base is not None
            else DIRETORIO_AUDITORIA_DESPESAS_PADRAO
        )
        dir_empresa = base / str(empresa_codigo)
        dir_empresa.mkdir(parents=True, exist_ok=True)
        arquivo = dir_empresa / "historico_despesas.json"

        historico: list[dict[str, Any]] = []
        if arquivo.is_file():
            try:
                historico = json.loads(arquivo.read_text(encoding="utf-8"))
                if not isinstance(historico, list):
                    historico = []
            except (OSError, ValueError):
                historico = []

        historico.append(registro)
        temporario = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=dir_empresa, suffix=".tmp", delete=False
            ) as f:
                temporario = Path(f.name)
                json.dump(historico, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporario, arquivo)
            return arquivo
        finally:
            if temporario and temporario.exists():
                temporario.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Executor Principal de Lançamento de Despesa
# ---------------------------------------------------------------------------


async def executar_lancamento_despesa(
    item: ItemFilaDespesa,
    unidade: Unidade,
    *,
    fornecedor_codigo: int | None = None,
    conta_codigo: int | None = None,
    titulo_pagar_codigos: list[int] | None = None,
    caminho_env: Path | str | None = None,
    banco_idempotencia: Path | str | None = None,
    diretorio_auditoria: Path | str | None = None,
    client: httpx.AsyncClient | None = None,
    anexar_arquivo: bool = True,
    autorizacao_piloto_token: str | None = None,
    exigir_autorizacao_piloto: bool = False,
    master_data_service: Any | None = None,
) -> dict[str, Any]:
    """Executa com segurança P0 o lançamento de despesa previamente aprovada.

    Passos:
    1. Verifica travas físicas (.env);
    2. Valida aprovação, hash, empresa e conta autorizada via MasterDataService;
    3. Valida autorização de piloto (se fornecida ou exigida);
    4. Monta payload estritamente conforme a OpenAPI V1;
    5. Adquire lock de idempotência atômica via SQLite (iniciar_operacao);
    6. Despacha chamada HTTP (sem retry automático em timeout);
    7. Confirma o resultado via consulta;
    8. Anexa comprovante se habilitado;
    9. Transiciona item para LANCADO_ERP e persiste auditoria append-only.
    """
    # 1. Conferência das travas físicas
    travas_ok, motivo_travas = verificar_travas_despesa(caminho_env)
    if not travas_ok:
        raise BarreiraDespesaErro(f"Lançamento bloqueado pelas travas de escrita: {motivo_travas}")

    # 2. Validação da aprovação e governança
    validar_aprovacao_para_escrita(item, master_data_service=master_data_service)

    # 3. Validação de autorização fina para piloto controlado
    if exigir_autorizacao_piloto or autorizacao_piloto_token is not None:
        if not autorizacao_piloto_token:
            raise BarreiraDespesaErro(
                "Execução em piloto requer token de autorização individual de operação."
            )
        gerenciador_piloto = GerenciadorAutorizacaoPiloto(banco_idempotencia)
        gerenciador_piloto.consumir_autorizacao(
            autorizacao_piloto_token,
            item,
            conta_codigo_execucao=conta_codigo,
        )

    # 4. Montagem do payload conforme operação aprovada
    operacao = item.operacao_financeira
    if operacao == OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value:
        payload = montar_payload_titulo_pagar(item, unidade, fornecedor_codigo=fornecedor_codigo)
        metodo = "POST"
        path = "/INTEGRACAO/V1/TITULOS_PAGAR"
        tipo_origem_anexo = "TITULO_PAGAR"
    elif operacao == OperacaoFinanceira.DESPESA_JA_PAGA.value:
        payload = montar_payload_movimento_conta(item, unidade, conta_codigo=conta_codigo)
        metodo = "POST"
        path = "/INTEGRACAO/V1/MOVIMENTOS_CONTA"
        tipo_origem_anexo = "MOVIMENTO_CONTA_MANUAL"
    elif operacao == OperacaoFinanceira.TITULO_EXISTENTE.value:
        payload = montar_payload_baixa_titulo(
            item, unidade, titulo_pagar_codigos=titulo_pagar_codigos, conta_codigo=conta_codigo
        )
        metodo = "PATCH"
        path = "/INTEGRACAO/V1/TITULOS_PAGAR/PAGAR"
        tipo_origem_anexo = "TITULO_PAGAR"
    else:
        raise BarreiraDespesaErro(f"Operação não suportada para lançamento: {operacao}")

    # 5. Idempotência local atômica
    chave_idemp = calcular_chave_idempotencia(item)
    idemp_store = IdempotenciaDespesas(banco_idempotencia)
    idemp_store.iniciar_operacao(chave_idemp, item)

    chave_api = os.getenv(unidade.chave_env, "")
    headers = {"x-api-key": chave_api, "Content-Type": "application/json"}
    url = f"{BASE_URL_PADRAO}{path}"

    proprio = client is None
    http = client or httpx.AsyncClient(timeout=30.0)

    try:
        try:
            if metodo == "POST":
                resp = await http.post(url, headers=headers, json=payload)
            else:
                resp = await http.patch(url, headers=headers, json=payload)

        except (httpx.TimeoutException, httpx.ConnectTimeout) as exc:
            # Tratamento seguro de timeout: NUNCA repetir automaticamente!
            motivo = f"Timeout na comunicação com webPosto ({type(exc).__name__}). Reenvio automático proibido."
            idemp_store.marcar_resultado_desconhecido(chave_idemp, motivo)
            item.status = StatusDespesa.RESULTADO_DESCONHECIDO.value
            item.motivo_bloqueio = motivo
            raise WebPostoErro(motivo) from exc

        except httpx.HTTPError as exc:
            idemp_store.marcar_falha_sem_envio(chave_idemp, str(exc))
            raise WebPostoErro(f"Erro de transporte HTTP: {type(exc).__name__}") from exc

        # Validação do código de resposta HTTP
        status_esperados = (201,) if metodo == "POST" else (204, 200)
        if resp.status_code not in status_esperados:
            detalhe = mensagem_segura(resp.text)
            motivo = f"webPosto recusou {operacao}: HTTP {resp.status_code} — {detalhe}"
            idemp_store.marcar_falha_sem_envio(chave_idemp, motivo)
            raise WebPostoErro(motivo, status_http=resp.status_code)

        resp_json = {}
        if resp.text:
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = {}

        # 6. Confirmação pós-escrita e extração do identificador ERP
        id_erp = None
        confirmado = False

        if operacao == OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value:
            id_erp = (
                resp_json.get("tituloPagarCodigo") or resp_json.get("codigo") or resp_json.get("id")
            )
            if id_erp:
                confirmado = True
            else:
                # HTTP 201 sem ID no corpo
                idemp_store.marcar_resultado_desconhecido(
                    chave_idemp,
                    "HTTP 201 recebido sem identificador retornado no corpo da resposta.",
                )
                item.status = StatusDespesa.RESULTADO_DESCONHECIDO.value
                return {
                    "sucesso": False,
                    "resultado_desconhecido": True,
                    "motivo": "HTTP 201 sem identificador no corpo",
                    "resposta_erp": resp_json,
                }

        elif operacao == OperacaoFinanceira.DESPESA_JA_PAGA.value:
            # OpenAPI não documenta ID no retorno de POST /MOVIMENTOS_CONTA
            # Consulta posterior para localizar o registro inequívoco (rejeitando ambiguidades)
            mov_encontrado = await confirmar_movimento_conta(http, unidade, item)
            if mov_encontrado:
                id_erp = mov_encontrado.get("movimentoContaCodigo") or mov_encontrado.get("codigo")
                confirmado = True
            else:
                idemp_store.marcar_resultado_desconhecido(
                    chave_idemp,
                    "Movimento lançado com HTTP 201 mas não localizado de forma unívoca na consulta de conferência.",
                )
                item.status = StatusDespesa.RESULTADO_DESCONHECIDO.value
                return {
                    "sucesso": False,
                    "resultado_desconhecido": True,
                    "motivo": "Movimento de conta não localizado na consulta pós-escrita.",
                    "resposta_erp": resp_json,
                }

        elif operacao == OperacaoFinanceira.TITULO_EXISTENTE.value:
            # PATCH retorna 204 No Content
            tit_id = item.titulo_casado_codigo or (
                titulo_pagar_codigos[0] if titulo_pagar_codigos else None
            )
            if tit_id:
                baixa_ok = await confirmar_baixa_titulo(http, unidade, tit_id)
                if baixa_ok:
                    id_erp = tit_id
                    confirmado = True
                else:
                    idemp_store.marcar_resultado_desconhecido(
                        chave_idemp,
                        f"PATCH retornado mas título {tit_id} ainda não consta como liquidado na consulta.",
                    )
                    item.status = StatusDespesa.RESULTADO_DESCONHECIDO.value
                    return {
                        "sucesso": False,
                        "resultado_desconhecido": True,
                        "motivo": f"Título {tit_id} não confirmado como liquidado após baixa.",
                    }
            else:
                id_erp = tit_id
                confirmado = True

        # 7. Gravação da confirmação
        idemp_store.confirmar_operacao(chave_idemp, id_erp, f"Confirmado via {metodo} {path}")
        item.resultado_erp_id = str(id_erp) if id_erp is not None else None
        item.status = StatusDespesa.LANCADO_ERP.value

        # 8. Vínculo do anexo digital se disponível
        anexo_resultado = None
        if anexar_arquivo and item.arquivo_comprovante and id_erp:
            try:
                anexo_resultado = await anexar_comprovante_despesa(
                    unidade,
                    tipo_origem=tipo_origem_anexo,
                    origem_id=int(id_erp),
                    caminho_arquivo=item.arquivo_comprovante,
                    client=http,
                )
            except Exception as exc:
                logger.warning(
                    "Falha ao anexar comprovante (não afeta lançamento financeiro): %s", str(exc)
                )
                anexo_resultado = {"sucesso": False, "erro": str(exc)}

        # 9. Auditoria append-only
        reg_auditoria = {
            "instante": agora().isoformat(),
            "operacao": operacao,
            "item_id": item.id,
            "versao": item.versao,
            "hash_aprovado": item.aprovado_hash,
            "aprovado_por": item.aprovado_por,
            "empresa_codigo": unidade.empresa_codigo,
            "payload": payload,
            "id_erp": id_erp,
            "resposta_erp": resp_json,
            "anexo": anexo_resultado,
            "chave_idempotencia": chave_idemp,
        }
        gravar_auditoria_despesa(unidade.empresa_codigo, reg_auditoria, diretorio_auditoria)

        return {
            "sucesso": True,
            "operacao": operacao,
            "id_erp": id_erp,
            "resposta_erp": resp_json,
            "anexo": anexo_resultado,
        }

    finally:
        if proprio:
            await http.aclose()
