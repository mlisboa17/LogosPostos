"""Sondagem read-only de GET /INTEGRACAO/V1/SANGRIAS_CAIXA.

Objetivo: validar em producao o contrato publicado na spec oficial
(docs/external/webposto/openapi_integracao_2026-10-06.json) SEM expor dados.

Saida: apenas estrutura — status HTTP, contagens, campos observados, tipos,
nulos e divergencias contra a spec. Nenhum valor monetario, texto livre ou
identificador e impresso. A CHAVE nunca aparece (ARCH01).

Uso (chave por unidade, lida do .env sem imprimir):
    python scripts/probe_sangrias_caixa_v1.py --empresa 11495 --data 2026-10-05 \
        --env-file <caminho>/.env --key-var WEBPOSTO_API_KEY_POSTO_VIP
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.gateway.webposto_client import WebPostoClient  # noqa: E402

PATH = "/INTEGRACAO/V1/SANGRIAS_CAIXA"
SPEC = ROOT.parent / "docs" / "external" / "webposto" / "openapi_integracao_2026-10-06.json"

# httpx loga a URL completa (com CHAVE) em nivel INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def spec_fields() -> dict[str, str]:
    schemas = json.loads(SPEC.read_text(encoding="utf-8"))["components"]["schemas"]
    props = schemas["SangriaCaixa"]["properties"]
    return {k: str(v.get("type")) for k, v in props.items()}


def scrub(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def type_name(v: Any) -> str:
    return "null" if v is None else type(v).__name__


async def probe(empresa: int, dia: str, limite: int, max_pages: int) -> dict[str, Any]:
    client = WebPostoClient()
    secret = client.config.webposto_api_key or ""
    base = {"dataInicial": dia, "dataFinal": dia, "empresaCodigo": empresa, "limite": limite}

    pages: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    cursor: int | None = None
    async with httpx.AsyncClient(base_url=client.config.webposto_base_url, timeout=30.0) as http:
        for _ in range(max_pages):
            params = client._with_key({**base, "ultimoCodigo": cursor})
            try:
                resp = await http.get(PATH, params=params)
            except Exception as exc:  # mensagem pode conter a URL com CHAVE
                pages.append({"erro": scrub(f"{type(exc).__name__}: {exc}", secret)[:200]})
                break
            page: dict[str, Any] = {"status": resp.status_code}
            if resp.status_code != 200:
                page["corpo_inicio"] = scrub(resp.text, secret)[:200]
                pages.append(page)
                break
            payload = resp.json()
            envelope = sorted(payload) if isinstance(payload, dict) else type_name(payload)
            batch = client._extract_rows(payload)
            next_cursor = payload.get("ultimoCodigo") if isinstance(payload, dict) else None
            page.update({"envelope": envelope, "linhas": len(batch), "tem_cursor": next_cursor is not None})
            pages.append(page)
            rows.extend(r for r in batch if isinstance(r, dict))
            if not batch or next_cursor is None or next_cursor == cursor:
                break
            cursor = next_cursor

    expected = spec_fields()
    types: dict[str, set[str]] = defaultdict(set)
    nulls: dict[str, int] = defaultdict(int)
    nonzero: dict[str, int] = defaultdict(int)
    for r in rows:
        for k, v in r.items():
            types[k].add(type_name(v))
            if v is None:
                nulls[k] += 1
            elif isinstance(v, (int, float)) and not isinstance(v, bool) and v != 0:
                nonzero[k] += 1

    observed = set(types)
    return {
        "rota": PATH,
        "filtro": {"empresaCodigo": empresa, "data": dia, "limite": limite},
        "paginas": pages,
        "total_linhas": len(rows),
        "campos": {
            k: {
                "tipos": sorted(types[k]),
                "spec": expected.get(k, "-"),
                "nulos": nulls[k],
                "nao_zero": nonzero[k],
            }
            for k in sorted(observed)
        },
        "faltando_vs_spec": sorted(set(expected) - observed) if rows else "sem linhas para comparar",
        "extras_vs_spec": sorted(observed - set(expected)),
        "alteradas": sum(1 for r in rows if r.get("alterada") is True),
        "caixas_distintos": len({r.get("caixaCodigo") for r in rows}),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--empresa", type=int, required=True, help="empresaCodigo (filial)")
    ap.add_argument("--data", default=(date.today() - timedelta(days=1)).isoformat(), help="AAAA-MM-DD (padrao: ontem)")
    ap.add_argument("--limite", type=int, default=50)
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--out", type=Path, help="salvar relatorio JSON (somente estrutura)")
    ap.add_argument("--env-file", type=Path, help=".env com as chaves por unidade")
    ap.add_argument("--key-var", help="nome da variavel com a CHAVE da unidade (ex.: WEBPOSTO_API_KEY_POSTO_VIP)")
    args = ap.parse_args()

    if args.key_var:
        import os
        from dotenv import dotenv_values

        value = (dotenv_values(args.env_file) if args.env_file else os.environ).get(args.key_var)
        if not value:
            sys.exit(f"variavel {args.key_var} ausente ou vazia")
        os.environ["WEBPOSTO_API_KEY"] = value.strip()

    report = asyncio.run(probe(args.empresa, args.data, args.limite, args.max_pages))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
