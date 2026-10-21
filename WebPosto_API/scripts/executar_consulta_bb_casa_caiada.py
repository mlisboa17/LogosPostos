"""Script de execução pontual e autorizada para MASTER-DATA-04.

Executa exclusivamente:
    GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100

Regras estritas:
- 1 única requisição HTTP GET (zero retries, zero redirects).
- Avaliação determinística em 6 dimensões via MasterDataService.avaliar_resposta_contas_erp().
- Persistência exclusiva no SQLite local (master_data.sqlite3) se e somente se ACCOUNT_CONFIRMED.
- Zero escritas no ERP.
- Sanitização de credenciais/segredos no relatório.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Configura paths
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Carrega .env sem expor
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH, override=False)

from src.modules.master_data.application.master_data_service import MasterDataService
from src.modules.master_data.domain.models import (
    CriterioResolucaoConta,
    EstadoResolucaoConta,
)


def executar() -> dict[str, Any]:
    chave = (os.getenv("WEBPOSTO_API_KEY_CASA_CAIADA") or "").strip()
    if not chave:
        return {
            "sucesso": False,
            "erro": "WEBPOSTO_API_KEY_CASA_CAIADA não configurada no .env",
        }

    base_url = (os.getenv("WEBPOSTO_BASE_URL") or "https://web.qualityautomacao.com.br").rstrip("/")
    endpoint = "/INTEGRACAO/V1/CONTAS"
    params = {
        "CHAVE": chave,
        "empresaCodigo": 5555,
        "limite": 100,
    }
    headers = {
        "x-api-key": chave,
        "Accept": "application/json",
        "User-Agent": "Logos-MasterData/0.4",
    }

    url_chamada = f"{base_url}{endpoint}"
    data_hora_inicio = datetime.now().isoformat()
    t0 = time.perf_counter()

    # Execução única com redirects e retries desativados
    with httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=False) as client:
        try:
            resp = client.get(endpoint, params=params, headers=headers)
            tempo_resposta_ms = round((time.perf_counter() - t0) * 1000, 2)
            status_http = resp.status_code
            headers_resp = dict(resp.headers)
            correlation_id = headers_resp.get("x-correlation-id") or headers_resp.get("x-request-id")
        except Exception as exc:
            tempo_resposta_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                "sucesso": False,
                "data_hora": data_hora_inicio,
                "tempo_resposta_ms": tempo_resposta_ms,
                "erro": f"Exceção de rede: {type(exc).__name__}: {exc}",
            }

    if status_http != 200:
        texto_limpo = resp.text[:200].replace(chave, "***")
        return {
            "sucesso": False,
            "data_hora": data_hora_inicio,
            "status_http": status_http,
            "tempo_resposta_ms": tempo_resposta_ms,
            "correlation_id": correlation_id,
            "corpo_erro": texto_limpo,
        }

    try:
        dados_json = resp.json()
    except Exception as exc:
        return {
            "sucesso": False,
            "data_hora": data_hora_inicio,
            "status_http": status_http,
            "tempo_resposta_ms": tempo_resposta_ms,
            "correlation_id": correlation_id,
            "erro": f"Resposta não é JSON válido: {exc}",
        }

    # Extrai registros retornados
    if isinstance(dados_json, list):
        registros = dados_json
    elif isinstance(dados_json, dict) and "resultados" in dados_json:
        registros = dados_json["resultados"]
    elif isinstance(dados_json, dict) and "data" in dados_json:
        registros = dados_json["data"]
    elif isinstance(dados_json, dict):
        registros = [dados_json]
    else:
        registros = []

    # Sanitiza registros para evidência (remove chaves/tokens caso venham no body)
    registros_sanitizados = []
    for reg in registros:
        r_limpo = {}
        for k, v in reg.items():
            if any(termo in k.lower() for termo in ["chave", "token", "secret", "senha", "password"]):
                r_limpo[k] = "***"
            else:
                r_limpo[k] = v
        registros_sanitizados.append(r_limpo)

    # Avaliação em 6 Dimensões com MasterDataService
    service = MasterDataService()
    criterio = CriterioResolucaoConta(
        empresa_codigo=5555,
        banco="001",
        agencia="2365-5",
        conta="56816-3",
        titular="AUTO POSTO CASA CAIADA LTDA",
        cnpj="04.284.939/0001-86",
    )

    avaliacao = service.avaliar_resposta_contas_erp(criterio, registros)

    persistido = False
    detalhes_persistencia = None

    if avaliacao.estado == EstadoResolucaoConta.ACCOUNT_CONFIRMED and avaliacao.conta_financeira:
        # Etapa D: Persistência incremental local no master_data.sqlite3
        dados_sincronizacao = {
            "contas_financeiras": [avaliacao.conta_financeira.model_dump()],
        }
        res_sync = service.sincronizar_dados_incremental(
            dados_sincronizacao,
            origem="webposto_v1_contas_resolucao_oficial",
        )
        # Verificação pós-persistência
        conta_lida = service.obter_conta_financeira(5555, avaliacao.conta_codigo)
        persistido = bool(conta_lida and conta_lida.conta_codigo == avaliacao.conta_codigo)
        detalhes_persistencia = {
            "contagens_sync": res_sync,
            "conta_verificada_no_banco": conta_lida.model_dump() if conta_lida else None,
        }

    return {
        "sucesso": True,
        "data_hora": data_hora_inicio,
        "status_http": status_http,
        "tempo_resposta_ms": tempo_resposta_ms,
        "quantidade_registros": len(registros),
        "correlation_id": correlation_id,
        "registros_sanitizados": registros_sanitizados,
        "avaliacao": {
            "estado": avaliacao.estado.value,
            "sucesso": avaliacao.sucesso,
            "conta_codigo": avaliacao.conta_codigo,
            "mensagem": avaliacao.mensagem,
            "candidatos_analisados": avaliacao.candidatos_analisados,
            "detalhes": avaliacao.detalhes,
        },
        "persistido_local": persistido,
        "detalhes_persistencia": detalhes_persistencia,
    }


if __name__ == "__main__":
    resultado = executar()
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))
