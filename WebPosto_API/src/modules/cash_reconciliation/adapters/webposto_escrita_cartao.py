"""Módulo isolado de escrita de cartão no webPosto (POST e DELETE /INTEGRACAO/V1/CARTOES).

A BARREIRA (obrigatória — ADR-003, RN-ERP-001 e SPRINT 18a):
1. Porta isolada: apenas incluir_cartao e excluir_cartao (desfazer); sem PATCH nesta sprint;
2. Spec oficial: apenas campos de IncluirAlterarCartaoDto da OpenAPI de 2026-10-06;
3. Duas travas no .env físico: WEBPOSTO_WRITES=1 e LOGOS_ERP_ESCRITA=1 (recusa duplicadas e ignora os.environ);
4. Montagem estrita a partir de proposta: NSU, autorização, administradora, venda, caixa, frentista, valor, data;
5. Mapa de administradora unívoco: sem ambiguidade; Amex Doze/Casa Caiada = PagBank;
6. Auditoria append-only em data/lancamentos_logos/<empresa>/ (fora do Git).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from urllib.parse import quote, quote_plus
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import httpx
from dotenv import load_dotenv
from dotenv.main import DotEnv
from unittest.mock import patch

from ..domain.acoes_recebimentos import AcaoRecebimento
from ..domain.models import Unidade
from ..domain.tempo import agora, formatar_data
from .webposto_http import BASE_URL_PADRAO, WebPostoErro

logger = logging.getLogger(__name__)

# Spec oficial: docs/external/webposto/openapi_integracao_2026-10-06.json
# Schema: components/schemas/IncluirAlterarCartaoDto
CAMPOS_PERMITIDOS_SPEC: frozenset[str] = frozenset({
    "vendaCodigo",
    "clienteCodigo",
    "administradoraCodigo",
    "caixaCodigo",
    "dataMovimento",
    "dataFiscal",
    "vencimento",
    "autorizacao",
    "centroCustoCodigo",
    "valor",
    "parcela",
    "funcionarioCodigo",
    "nsu",
    "taxaPercentual",
    "valorTransacao",
})

DIRETORIO_AUDITORIA_PADRAO = Path("data/lancamentos_logos")
_leitura_env = threading.RLock()
_auditoria_lock = threading.RLock()


class BarreiraCartaoErro(ValueError):
    """Violação de segurança da barreira de escrita de cartão no webPosto."""
    pass


def mensagem_segura(mensagem: str) -> str:
    for nome, valor in os.environ.items():
        if valor and any(p in nome.upper() for p in ("CHAVE", "TOKEN", "SECRET", "PASSWORD", "API_KEY", "SENHA")):
            for segredo in {valor, quote(valor, safe=""), quote_plus(valor)}:
                mensagem = mensagem.replace(segredo, "[omitido]")
    mensagem = re.sub(r"(?i)\b(Bearer|Basic)\s+[^\s\"'<>]+", r"\1 [omitido]", mensagem)
    mensagem = re.sub(
        r"(?i)(\b(?:CHAVE|token|access_token|x-api-key|api_key|authorization)\b[\"']?\s*[:=]\s*[\"']?)[^\s&\"'<>]+",
        r"\1[omitido]", mensagem,
    )
    return " ".join(mensagem.split())[:500]


def erro_resposta(resposta: httpx.Response, operacao: str) -> WebPostoErro:
    detalhe = mensagem_segura(resposta.text)
    return WebPostoErro(
        f"webPosto recusou {operacao}: HTTP {resposta.status_code}"
        + (f" — {detalhe}" if detalhe else ""),
        status_http=resposta.status_code,
    )


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


def ler_travas(caminho_env: Path | str | None = None) -> dict[str, list[tuple[int, str | None]]]:
    """Observa somente as travas enquanto load_dotenv lê o arquivo físico.

    A subclasse mantém a semântica do dotenv e retém duplicidades antes de virarem
    um dicionário; interpolação e os.environ não podem liberar uma trava.
    """
    nomes = {"WEBPOSTO_WRITES", "LOGOS_ERP_ESCRITA", "LOGOS_CARTAO_AUTOMATICO",
             "TELEGRAM_DIRETOR_CHAT_ID", "TELEGRAM_DIRETOR_USER_ID"}
    valores: dict[str, list[tuple[int, str | None]]] = {n: [] for n in nomes}
    thread = threading.get_ident()

    class DotEnvTravas(DotEnv):
        def set_as_environment_variables(self):
            if threading.get_ident() != thread:
                return super().set_as_environment_variables()
            # A leitura das travas não exporta nem retém outras configurações.
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
                        raise BarreiraCartaoErro("Arquivo de configuração inválido; confira o .env sem expor credenciais.")
                    if binding.key in nomes:
                        valores[binding.key].append((binding.original.line, binding.value))
                    if binding.key is not None:
                        yield binding.key, binding.value

    arquivo = resolver_caminho_env(caminho_env)
    if not arquivo.is_file():
        raise BarreiraCartaoErro("Arquivo .env não encontrado.")
    with _leitura_env, patch("dotenv.main.DotEnv", DotEnvTravas):
        load_dotenv(arquivo, override=False, interpolate=False)
    return valores


def verificar_travas_cartao(caminho_env: Path | str | None = None) -> tuple[bool, str]:
    """Valida as travas de ambiente LENDO EXCLUSIVAMENTE o arquivo .env físico.

    Regra SPRINT 18a / ADR-003:
    - Lê exclusivamente o arquivo .env via load_dotenv, sem exportar variáveis.
    - Ignora variáveis de ambiente de processo (os.environ).
    - Se WEBPOSTO_WRITES ou LOGOS_ERP_ESCRITA aparecer duplicado no arquivo,
      recusa indicando as linhas exatas.
    - Ambas as travas devem ser estritamente '1' no arquivo .env.
    """
    try:
        valores = ler_travas(caminho_env)
    except (OSError, BarreiraCartaoErro):
        return False, "Falha ao ler as travas do arquivo .env."
    for k in ("WEBPOSTO_WRITES", "LOGOS_ERP_ESCRITA"):
        linhas = [n for n, _ in valores[k]]
        if len(linhas) > 1:
            return False, f"trava duplicada no .env, linha {linhas[0]} e {linhas[1]}"
        if len(valores[k]) != 1 or valores[k][0][1] != "1":
            return False, f"Trava {k} != 1 no arquivo .env (escrita bloqueada no ERP)."
    return True, "Travas de escrita de cartão liberadas no arquivo .env."


def resolver_administradora_codigo(
    unidade: Unidade | int,
    adquirente: str,
    forma: str,
    administradoras_cadastradas: list[dict[str, Any]],
) -> int:
    """Resolve o administradoraCodigo unívoco no webPosto.

    Regras SPRINT 18a:
    1. Lê a lista de administradoras cadastradas da unidade (GET /INTEGRACAO/V1/ADMINISTRADORAS).
    2. Amex nas unidades Doze (74014) e Casa Caiada (5555) = PagBank (descrição "AMERICAN EXPRESS").
    3. Para PagBank geral: associa bandeira + modalidade (Crédito/Débito) com "PAGSEGURO" ou "PAGBANK".
    4. Sem correspondência única ou ambígua -> recusa montagem.
    """
    empresa_codigo = unidade.empresa_codigo if hasattr(unidade, "empresa_codigo") else int(unidade)
    adq_norm = (adquirente or "").strip().upper()
    forma_norm = (forma or "").strip().upper()

    if not forma_norm:
        raise BarreiraCartaoErro("Forma de pagamento não informada para resolução de administradora.")

    # Filtra apenas ativas se o campo existir
    ativas = [
        a for a in administradoras_cadastradas
        if a.get("ativo") is not False
    ]
    if adq_norm in ("PAGBANK", "PAGSEGURO") and any(t in forma_norm for t in ("PIX", "BACEN")):
        pix = [a for a in ativas
               if a.get("ativo") not in (0, "N", "0", "false")
               and any(n in str(a.get("descricao") or "").upper() for n in ("PAGBANK", "PAGSEGURO"))
               and any(n in str(a.get("descricao") or "").upper() for n in ("PIX", "BACEN"))]
        if not pix:
            raise BarreiraCartaoErro("não há administradora de PIX PagBank cadastrada — lançar à mão")
        if len(pix) != 1:
            raise BarreiraCartaoErro("há mais de uma administradora de PIX PagBank cadastrada — lançar à mão")
        codigo = pix[0].get("administradoraCodigo") or pix[0].get("codigo")
        if not isinstance(codigo, (int, str)) or not str(codigo).isdigit() or int(codigo) <= 0:
            raise BarreiraCartaoErro("administradora de PIX PagBank sem código válido — lançar à mão")
        return int(codigo)
    # Regra 2: Amex em Doze (74014) e Casa Caiada (5555) é PagBank
    eh_amex = "AMERICAN EXPRESS" in forma_norm or "AMEX" in forma_norm
    if empresa_codigo in (5555, 74014) and adq_norm in ("PAGBANK", "PAGSEGURO") and eh_amex:
        candidatos_amex = [
            a for a in ativas
            if (a.get("descricao") or "").strip().upper() == "AMERICAN EXPRESS"
        ]
        if len(candidatos_amex) == 1:
            cod = candidatos_amex[0].get("administradoraCodigo") or candidatos_amex[0].get("codigo")
            return int(cod)
        elif len(candidatos_amex) > 1:
            raise BarreiraCartaoErro(
                f"Administradora ambígua no webPosto para American Express PagBank na unidade {empresa_codigo}: "
                f"{[c.get('descricao') for c in candidatos_amex]}"
            )

    # Identifica modalidade da forma
    eh_debito = any(t in forma_norm for t in ("DÉBITO", "DEBITO", "ELECTRON", "MAESTRO"))
    eh_credito = "CRÉDITO" in forma_norm or "CREDITO" in forma_norm
    eh_pix = "PIX" in forma_norm

    # Identifica bandeira principal
    bandeira_alvo = None
    if "MAESTRO" in forma_norm or "MASTERCARD" in forma_norm or "MASTER" in forma_norm:
        bandeira_alvo = "MAESTRO" if eh_debito else "MASTERCARD"
    elif "VISA ELECTRON" in forma_norm or ("VISA" in forma_norm and eh_debito):
        bandeira_alvo = "VISA ELECTRON"
    elif "VISA" in forma_norm:
        bandeira_alvo = "VISA CREDITO" if eh_credito else "VISA"
    elif "ELO" in forma_norm:
        bandeira_alvo = "ELO DEBITO" if eh_debito else "ELO CREDITO" if eh_credito else "ELO"
    elif "HIPERCARD" in forma_norm:
        bandeira_alvo = "HIPERCARD"
    elif eh_amex:
        bandeira_alvo = "AMERICAN EXPRESS"
    elif eh_pix:
        bandeira_alvo = "PIX"

    candidatos = []
    if adq_norm in ("PAGBANK", "PAGSEGURO"):
        # Administradoras PagBank no webPosto geralmente contêm PAGSEGURO ou PAGBANK na descrição
        for a in ativas:
            desc = (a.get("descricao") or "").upper().strip()
            tipo = (a.get("tipo") or "").upper().strip()

            if not ("PAGSEGURO" in desc or "PAGBANK" in desc):
                continue

            # Confere modalidade
            if eh_pix and ("PIX" in desc or "PIX" in tipo):
                candidatos.append(a)
                continue

            if eh_debito and not ("DEBITO" in desc or "DÉBITO" in desc or "DÉBITO" in tipo or "DEBITO" in tipo):
                continue
            if eh_credito and not ("CREDITO" in desc or "CRÉDITO" in desc or "CRÉDITO" in tipo or "CREDITO" in tipo):
                continue

            # Confere bandeira
            if bandeira_alvo == "VISA ELECTRON" and ("VISA ELECTRON" in desc or "VISA" in desc):
                candidatos.append(a)
            elif bandeira_alvo == "VISA CREDITO" and "VISA CREDITO" in desc:
                candidatos.append(a)
            elif bandeira_alvo == "MAESTRO" and "MAESTRO" in desc:
                candidatos.append(a)
            elif bandeira_alvo == "MASTERCARD" and "MASTERCARD" in desc:
                candidatos.append(a)
            elif bandeira_alvo == "ELO DEBITO" and ("ELO DEBITO" in desc or "ELO DÉBITO" in desc):
                candidatos.append(a)
            elif bandeira_alvo == "ELO CREDITO" and ("ELO CREDITO" in desc or "ELO CRÉDITO" in desc):
                candidatos.append(a)
            elif bandeira_alvo == "HIPERCARD" and "HIPERCARD" in desc:
                candidatos.append(a)
    elif adq_norm == "PREMMIA":
        for a in ativas:
            desc = (a.get("descricao") or "").upper().strip()
            if "PREMMIA" in desc:
                candidatos.append(a)
    else:
        # Busca genérica direta por descrição exata
        for a in ativas:
            desc = (a.get("descricao") or "").upper().strip()
            if desc == forma_norm:
                candidatos.append(a)

    if not candidatos:
        raise BarreiraCartaoErro(
            f"Nenhuma administradora encontrada no webPosto para adquirente '{adquirente}' "
            f"e forma '{forma}' na unidade {empresa_codigo}."
        )

    if len(candidatos) > 1:
        nomes = [c.get("descricao") for c in candidatos]
        raise BarreiraCartaoErro(
            f"Administradora ambígua no webPosto para adquirente '{adquirente}' "
            f"e forma '{forma}' na unidade {empresa_codigo}: {nomes}."
        )

    cod = candidatos[0].get("administradoraCodigo") or candidatos[0].get("codigo")
    if cod is None:
        raise BarreiraCartaoErro(
            f"Administradora encontrada sem código válido para '{forma}': {candidatos[0]}"
        )
    return int(cod)


def montar_payload_cartao(
    acao_ou_dados: AcaoRecebimento | dict[str, Any],
    administradora_codigo: int,
    *,
    nsu: str | None = None,
    autorizacao: str | None = None,
    venda: int | None = None,
    caixa: int | None = None,
    frentista: int | None = None,
    valor: Decimal | float | int | str | None = None,
    data_movimento: date | str | None = None,
) -> dict[str, Any]:
    """Monta o payload estrito para POST /INTEGRACAO/V1/CARTOES a partir de uma proposta.

    Regra SPRINT 18a:
    - Exige: NSU, autorização, administradora, venda, caixa, frentista, valor, data.
    - Se faltar qualquer um -> recusa com motivo explícito.
    - Campos estritamente os de IncluirAlterarCartaoDto da OpenAPI oficial.
    """
    dados = acao_ou_dados if isinstance(acao_ou_dados, dict) else acao_ou_dados.model_dump(mode="python")

    # 1. NSU
    final_nsu = nsu if nsu is not None else dados.get("nsu")
    if not final_nsu or str(final_nsu).strip().startswith("…"):
        # Tenta buscar em pagamentos se existir
        pagamentos = dados.get("pagamentos") or ()
        for p in pagamentos:
            p_nsu = p.get("nsu") if isinstance(p, dict) else getattr(p, "nsu", None)
            if p_nsu and not str(p_nsu).strip().startswith("…"):
                final_nsu = p_nsu
                break
    if not final_nsu or str(final_nsu).strip().startswith("…"):
        raise BarreiraCartaoErro("NSU ausente ou mascarado na proposta — lançamento exige NSU completo.")
    final_nsu = str(final_nsu).strip()

    # 2. Autorização
    final_autorizacao = autorizacao if autorizacao is not None else dados.get("autorizacao")
    if not final_autorizacao:
        raise BarreiraCartaoErro("Código de autorização ausente na proposta.")
    final_autorizacao = str(final_autorizacao).strip()

    # 3. Administradora
    if not administradora_codigo or int(administradora_codigo) <= 0:
        raise BarreiraCartaoErro("Código da administradora ausente ou inválido.")
    final_administradora = int(administradora_codigo)

    # 4. Venda
    final_venda = venda if venda is not None else dados.get("venda")
    if final_venda is None or int(final_venda) <= 0:
        raise BarreiraCartaoErro("Código da venda ausente na proposta.")
    final_venda = int(final_venda)

    # 5. Caixa
    final_caixa = caixa if caixa is not None else dados.get("caixa")
    if final_caixa is None or int(final_caixa) <= 0:
        raise BarreiraCartaoErro("Código do caixa ausente na proposta.")
    final_caixa = int(final_caixa)

    # 6. Frentista
    final_frentista = frentista if frentista is not None else dados.get("frentista")
    if final_frentista is None or int(final_frentista) <= 0:
        raise BarreiraCartaoErro("Código do frentista ausente na proposta.")
    final_frentista = int(final_frentista)

    # 7. Valor
    final_valor_raw = valor if valor is not None else dados.get("valor")
    try:
        final_valor = Decimal(str(final_valor_raw or 0))
    except Exception:
        raise BarreiraCartaoErro(f"Valor inválido na proposta: {final_valor_raw}")
    if final_valor <= Decimal(0):
        raise BarreiraCartaoErro("Valor do lançamento deve ser maior que zero.")

    # 8. Data de movimento
    final_data_raw = data_movimento if data_movimento is not None else dados.get("momento")
    if isinstance(final_data_raw, datetime):
        data_str = final_data_raw.date().isoformat()
    elif isinstance(final_data_raw, date):
        data_str = final_data_raw.isoformat()
    elif isinstance(final_data_raw, str):
        # Trunca caso contenha hora ISO
        data_str = final_data_raw.split("T")[0]
    else:
        raise BarreiraCartaoErro("Data de movimento ausente na proposta.")

    # Monta payload com estrita aderência ao schema IncluirAlterarCartaoDto
    payload: dict[str, Any] = {
        "vendaCodigo": final_venda,
        "clienteCodigo": None,
        "administradoraCodigo": final_administradora,
        "caixaCodigo": final_caixa,
        "dataMovimento": data_str,
        "dataFiscal": data_str,
        "vencimento": data_str,
        "autorizacao": final_autorizacao,
        "centroCustoCodigo": None,
        "valor": float(final_valor),
        "parcela": 1,
        "funcionarioCodigo": final_frentista,
        "nsu": final_nsu,
        "taxaPercentual": None,
        "valorTransacao": float(final_valor),
    }

    # Validação rigorosa: nenhum campo fora da spec oficial pode existir
    chaves_invalidas = set(payload.keys()) - CAMPOS_PERMITIDOS_SPEC
    if chaves_invalidas:
        raise BarreiraCartaoErro(f"Payload contém campos fora da especificação oficial: {chaves_invalidas}")

    return payload


def resolver_diretorio_auditoria(empresa_codigo: int, diretorio_base: Path | str | None = None) -> Path:
    """Resolve o diretório append-only para registro de lançamentos de uma empresa."""
    base = Path(diretorio_base) if diretorio_base is not None else DIRETORIO_AUDITORIA_PADRAO
    return base / str(empresa_codigo)


def gravar_auditoria(
    empresa_codigo: int,
    registro: dict[str, Any],
    diretorio_base: Path | str | None = None,
) -> Path:
    """Grava um registro de auditoria append-only em historico.json (fora do Git)."""
    with _auditoria_lock:
        return _gravar_auditoria(empresa_codigo, registro, diretorio_base)


def _gravar_auditoria(empresa_codigo, registro, diretorio_base):
    dir_empresa = resolver_diretorio_auditoria(empresa_codigo, diretorio_base)
    dir_empresa.mkdir(parents=True, exist_ok=True)
    arquivo = dir_empresa / "historico.json"

    historico: list[dict[str, Any]] = []
    if arquivo.is_file():
        try:
            historico = json.loads(arquivo.read_text(encoding="utf-8"))
            if not isinstance(historico, list):
                raise BarreiraCartaoErro("Auditoria inválida; escrita bloqueada.")
        except (OSError, ValueError) as exc:
            raise BarreiraCartaoErro("Falha ao ler auditoria; escrita bloqueada.") from exc

    historico.append(registro)

    temporario: Path | None = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=dir_empresa, suffix=".tmp", delete=False) as f:
            temporario = Path(f.name)
            json.dump(historico, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, arquivo)
        return arquivo
    finally:
        if temporario and temporario.exists():
            temporario.unlink(missing_ok=True)


def ler_auditoria(
    empresa_codigo: int,
    diretorio_base: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Lê o histórico de auditoria gravado para a empresa."""
    arquivo = resolver_diretorio_auditoria(empresa_codigo, diretorio_base) / "historico.json"
    if not arquivo.is_file():
        return []
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        if not isinstance(dados, list) or not all(isinstance(h, dict) for h in dados):
            raise BarreiraCartaoErro("Auditoria inválida; escrita bloqueada.")
        return dados
    except (OSError, ValueError) as exc:
        raise BarreiraCartaoErro("Falha ao ler auditoria; escrita bloqueada.") from exc


async def incluir_cartao(
    unidade: Unidade,
    payload: dict[str, Any],
    *,
    acao_id: str,
    evidencias: tuple[str, ...] | list[str],
    autorizado_por: str,
    motivo: str = "Lançamento de cartão",
    caminho_env: Path | str | None = None,
    diretorio_auditoria: Path | str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Inclui cartão no webPosto via POST /INTEGRACAO/V1/CARTOES (isolada e protegida por travas).

    Exige WEBPOSTO_WRITES=1 e LOGOS_ERP_ESCRITA=1 no arquivo .env físico.
    """
    travas_ok, motivo_travas = verificar_travas_cartao(caminho_env)
    if not travas_ok:
        raise BarreiraCartaoErro(f"Escrita bloqueada pelas travas: {motivo_travas}")

    chaves_invalidas = set(payload.keys()) - CAMPOS_PERMITIDOS_SPEC
    if chaves_invalidas:
        raise BarreiraCartaoErro(f"Payload contém campos proibidos: {chaves_invalidas}")

    chave = os.getenv(unidade.chave_env)
    if not chave:
        raise WebPostoErro(f"Chave {unidade.chave_env} ausente no ambiente.")

    url = f"{BASE_URL_PADRAO}/INTEGRACAO/V1/CARTOES"
    headers = {"x-api-key": chave, "Content-Type": "application/json"}

    gerenciador = client if client is not None else httpx.AsyncClient(timeout=30.0)
    async with (httpx.AsyncClient(timeout=30.0) if client is None else gerenciador) as http:
        resposta = await http.post(url, headers=headers, json=payload)
        if resposta.status_code not in (200, 201):
            raise erro_resposta(resposta, "inclusão do cartão")
        try:
            resposta_json = resposta.json()
        except ValueError:
            resposta_json = {}
        if not isinstance(resposta_json, dict):
            resposta_json = {}

    id_criado = (
        resposta_json.get("cartaoCodigo")
        or resposta_json.get("codigo")
        or resposta_json.get("id")
    )

    # Registra na auditoria append-only
    registro_auditoria = {
        "instante": agora().isoformat(),
        "o_que": "INCLUSAO_CARTAO",
        "acao_id": acao_id,
        "motivo_inclusao": motivo,
        "evidencias": list(evidencias),
        "autorizado_por": autorizado_por,
        "payload": payload,
        "resposta_erp": resposta_json,
        "id_criado": id_criado,
        "como_desfazer": f"DELETE /INTEGRACAO/V1/CARTOES/{id_criado}" if id_criado else "DELETE não disponível sem id",
    }
    gravar_auditoria(unidade.empresa_codigo, registro_auditoria, diretorio_auditoria)

    return {
        "sucesso": True,
        "id_criado": id_criado,
        "resposta_erp": resposta_json,
    }


async def excluir_cartao(
    unidade: Unidade,
    cartao_id: int,
    *,
    acao_id: str | None = None,
    motivo: str = "Desfazer lançamento de cartão",
    autorizado_por: str = "diretor",
    caminho_env: Path | str | None = None,
    diretorio_auditoria: Path | str | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Exclui cartão do webPosto via DELETE /INTEGRACAO/V1/CARTOES/{id} (para desfazer).

    Exige WEBPOSTO_WRITES=1 e LOGOS_ERP_ESCRITA=1 no arquivo .env físico.
    """
    travas_ok, motivo_travas = verificar_travas_cartao(caminho_env)
    if not travas_ok:
        raise BarreiraCartaoErro(f"Exclusão bloqueada pelas travas: {motivo_travas}")

    if not cartao_id or int(cartao_id) <= 0:
        raise BarreiraCartaoErro(f"ID de cartão inválido para exclusão: {cartao_id}")

    chave = os.getenv(unidade.chave_env)
    if not chave:
        raise WebPostoErro(f"Chave {unidade.chave_env} ausente no ambiente.")

    url = f"{BASE_URL_PADRAO}/INTEGRACAO/V1/CARTOES/{cartao_id}"
    headers = {"x-api-key": chave}

    gerenciador = client if client is not None else httpx.AsyncClient(timeout=30.0)
    async with (httpx.AsyncClient(timeout=30.0) if client is None else gerenciador) as http:
        resposta = await http.delete(url, headers=headers)
        if resposta.status_code not in (200, 204):
            raise erro_resposta(resposta, "exclusão do cartão")

    # Registra na auditoria append-only
    registro_auditoria = {
        "instante": agora().isoformat(),
        "o_que": "EXCLUSAO_CARTAO",
        "acao_id": acao_id,
        "motivo_inclusao": motivo,
        "evidencias": [f"Desfazer exclusão do cartão {cartao_id}"],
        "autorizado_por": autorizado_por,
        "payload": {"id": cartao_id},
        "resposta_erp": {"status_code": resposta.status_code},
        "id_criado": None,
        "como_desfazer": "Exclusão já executada (desfeita)",
    }
    gravar_auditoria(unidade.empresa_codigo, registro_auditoria, diretorio_auditoria)

    return True
