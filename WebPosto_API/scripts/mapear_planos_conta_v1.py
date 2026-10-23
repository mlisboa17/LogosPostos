"""Mapeia o plano de contas gerencial compartilhado do webPosto (somente leitura).

Saídas versionáveis e sanitizadas:
- docs/validation/PLANOS_CONTA_MASTER_01.json
- docs/validation/PLANOS_CONTA_MASTER_01.md

O script executa exclusivamente GET, sem retries e sem qualquer mutação no ERP.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "WebPosto_API"
ENV_PATH = API_ROOT / ".env"
LOCAL_MAPPING = API_ROOT / "config" / "account_category_mapping.json"
OUT_JSON = ROOT / "docs" / "validation" / "PLANOS_CONTA_MASTER_01.json"
OUT_MD = ROOT / "docs" / "validation" / "PLANOS_CONTA_MASTER_01.md"
ENDPOINT = "/INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL"


def _hierarquia_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in str(value or "").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(10**9)
    return tuple(parts)


def _coletar(base_url: str, api_key: str) -> list[dict[str, Any]]:
    registros: list[dict[str, Any]] = []
    cursor: int | None = None
    cursores: set[int] = set()

    with httpx.Client(timeout=30.0, follow_redirects=False) as client:
        while True:
            params: dict[str, Any] = {"limite": 2000}
            if cursor is not None:
                params["ultimoCodigo"] = cursor
            response = client.get(
                f"{base_url}{ENDPOINT}",
                headers={
                    "x-api-key": api_key,
                    "Accept": "application/json",
                    "User-Agent": "Logos-ChartOfAccounts-Mapping/1.0",
                },
                params=params,
            )
            if response.status_code != 200:
                detail = response.text[:300].replace(api_key, "***")
                raise RuntimeError(f"GET {ENDPOINT} falhou: HTTP {response.status_code} — {detail}")

            body = response.json()
            page = body.get("resultados", []) if isinstance(body, dict) else body
            if not isinstance(page, list):
                raise RuntimeError("Resposta inesperada: resultados não é uma lista.")
            registros.extend(dict(item) for item in page)

            next_cursor = body.get("ultimoCodigo") if isinstance(body, dict) else None
            if not page or next_cursor is None or len(page) < 2000:
                break
            next_cursor = int(next_cursor)
            if next_cursor in cursores:
                raise RuntimeError(f"Cursor repetido detectado: {next_cursor}")
            cursores.add(next_cursor)
            cursor = next_cursor

    unicos: dict[int, dict[str, Any]] = {}
    for item in registros:
        codigo = int(item["planoContaCodigo"])
        if codigo in unicos and unicos[codigo] != item:
            raise RuntimeError(f"Código duplicado com conteúdo divergente: {codigo}")
        unicos[codigo] = item
    return list(unicos.values())


def _enriquecer(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    por_hierarquia = {str(item.get("hierarquia") or ""): int(item["planoContaCodigo"]) for item in registros}
    hierarquias = set(por_hierarquia)
    saida: list[dict[str, Any]] = []

    for item in registros:
        codigo = int(item["planoContaCodigo"])
        hierarquia = str(item.get("hierarquia") or "")
        prefix = f"{hierarquia}."
        filhos_diretos = []
        for candidato in registros:
            h = str(candidato.get("hierarquia") or "")
            if not h.startswith(prefix):
                continue
            restante = h[len(prefix):]
            if restante and "." not in restante:
                filhos_diretos.append(int(candidato["planoContaCodigo"]))

        parent_h = hierarquia.rsplit(".", 1)[0] if "." in hierarquia else None
        parent_code = por_hierarquia.get(parent_h or "")
        folha = not any(h.startswith(prefix) for h in hierarquias if h != hierarquia)
        saida.append(
            {
                "planoContaCodigo": codigo,
                "descricao": str(item.get("descricao") or ""),
                "hierarquia": hierarquia,
                "nivel": len(hierarquia.split(".")) if hierarquia else 0,
                "natureza": item.get("natureza"),
                "tipo": item.get("tipo"),
                "apuraDre": item.get("apuraDre"),
                "paiHierarquia": parent_h,
                "paiCodigo": parent_code,
                "filhosDiretos": sorted(filhos_diretos),
                "ehFolhaEstrutural": folha,
                "candidatoLancavel": folha,
                "observacaoLancamento": (
                    "Folha estrutural; candidato a lançamento, sujeito às demais regras do ERP."
                    if folha
                    else "Conta pai; não usar diretamente em lançamentos."
                ),
            }
        )
    return sorted(saida, key=lambda x: (_hierarquia_key(x["hierarquia"]), x["planoContaCodigo"]))


def _codigos_locais() -> set[int]:
    if not LOCAL_MAPPING.exists():
        return set()
    data = json.loads(LOCAL_MAPPING.read_text(encoding="utf-8"))
    return {
        int(item.get("planoContaId") or item.get("codigoGerencial"))
        for item in data.get("mappings", [])
        if item.get("planoContaId") or item.get("codigoGerencial")
    }


def main() -> None:
    load_dotenv(ENV_PATH, override=False)
    api_key = (os.getenv("WEBPOSTO_API_KEY_CASA_CAIADA") or "").strip()
    if not api_key:
        raise RuntimeError("WEBPOSTO_API_KEY_CASA_CAIADA não configurada.")
    base_url = (os.getenv("WEBPOSTO_BASE_URL") or "https://web.qualityautomacao.com.br").rstrip("/")

    oficiais = _enriquecer(_coletar(base_url, api_key))
    locais = _codigos_locais()
    oficiais_codigos = {item["planoContaCodigo"] for item in oficiais}
    pais = [item for item in oficiais if not item["ehFolhaEstrutural"]]
    folhas = [item for item in oficiais if item["ehFolhaEstrutural"]]
    pro_labore = [
        item
        for item in oficiais
        if item["planoContaCodigo"] == 29021
        or "PRO LABORE" in item["descricao"].upper()
        or "PRÓ-LABORE" in item["descricao"].upper()
    ]
    filhos_pro_labore: list[dict[str, Any]] = []
    for parent in pro_labore:
        filhos_pro_labore.extend(
            item for item in oficiais if item["paiCodigo"] == parent["planoContaCodigo"]
        )
    hierarquias_pro_labore = {
        item["hierarquia"] for item in pro_labore if item.get("hierarquia")
    }
    descendentes_pro_labore = [
        item
        for item in oficiais
        if any(
            item["hierarquia"].startswith(f"{hierarquia}.")
            for hierarquia in hierarquias_pro_labore
        )
    ]
    folhas_marcio = [
        item
        for item in oficiais
        if item.get("paiCodigo") == 148303 and item["ehFolhaEstrutural"]
    ]

    payload = {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "endpoint": ENDPOINT,
            "method": "GET",
            "sharedAcrossCompanies": True,
            "erpWrites": 0,
        },
        "summary": {
            "totalOfficial": len(oficiais),
            "totalParents": len(pais),
            "totalStructuralLeaves": len(folhas),
            "totalLocalBefore": len(locais),
            "officialMissingLocally": sorted(oficiais_codigos - locais),
            "localMissingOfficially": sorted(locais - oficiais_codigos),
        },
        "proLabore": {
            "matches": pro_labore,
            "directChildren": filhos_pro_labore,
            "allDescendants": descendentes_pro_labore,
            "marcioLeaves": folhas_marcio,
        },
        "plans": oficiais,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    OUT_JSON.write_bytes(text.encode("utf-8"))
    digest = hashlib.sha256(OUT_JSON.read_bytes()).hexdigest().upper()

    children_lines = "\n".join(
        f"- `{item['planoContaCodigo']}` — `{item['hierarquia']}` — {item['descricao']}"
        for item in filhos_pro_labore
    ) or "- Nenhum filho direto localizado."
    marcio_lines = "\n".join(
        f"- `{item['planoContaCodigo']}` — `{item['hierarquia']}` — {item['descricao']}"
        for item in folhas_marcio
    ) or "- Nenhuma folha localizada sob Márcio."
    md = f"""# PLANOS-CONTA-MASTER-01 — Catálogo Gerencial Compartilhado

**Fonte:** `GET {ENDPOINT}`  
**Modo:** somente leitura  
**Compartilhado entre empresas:** sim  
**Escritas ERP:** zero  
**SHA-256 do catálogo JSON:** `{digest}`

## Resumo

- Planos oficiais: **{len(oficiais)}**
- Contas pai: **{len(pais)}**
- Folhas estruturais candidatas a lançamento: **{len(folhas)}**
- Códigos no catálogo local anterior: **{len(locais)}**
- Códigos oficiais ausentes localmente: **{len(oficiais_codigos - locais)}**
- Códigos locais ausentes no retorno oficial: **{len(locais - oficiais_codigos)}**

`candidatoLancavel` significa apenas que o item é folha na árvore. A aceitação final continua dependente das demais validações do ERP.

## PRO LABORE

Filhos diretos encontrados sob a conta pai oficial:

{children_lines}

### Folhas sob `148303 — MARCIO LISBOA`

{marcio_lines}

Para o caso `PRÓ-LABORE — MÁRCIO`, a correspondência literal encontrada é `158764 — MARCIO-PROLABORE` (`2.02.05.005`). Ela é folha estrutural no retorno oficial. Nenhuma escrita foi realizada com esse código.

## Artefato completo

- [PLANOS_CONTA_MASTER_01.json](PLANOS_CONTA_MASTER_01.json)
"""
    OUT_MD.write_bytes(md.encode("utf-8"))
    print(json.dumps({
        "total": len(oficiais),
        "parents": len(pais),
        "leaves": len(folhas),
        "missing_local": len(oficiais_codigos - locais),
        "pro_labore_children": filhos_pro_labore,
        "marcio_leaves": folhas_marcio,
        "sha256": digest,
        "json": str(OUT_JSON),
        "report": str(OUT_MD),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
