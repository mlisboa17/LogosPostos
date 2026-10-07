"""
Entrypoint FastAPI unificado — proxy WebPosto, cache Valkey, rotas legadas e UI Lionda.

Uso:
  python src/presentation/app.py
  # ou: uvicorn src.presentation.app:app --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.application.usecases.build_adelaide_metrics import build_adelaide_metrics
from src.application.usecases.dashboard_filtros_meta import build_filtros_meta
from src.application.usecases.fetch_produto_grupos import fetch_produto_grupos
from src.application.usecases.fetch_produtos_catalog import (
    fetch_produtos_catalog,
    fetch_produtos_catalog_completo,
)
from src.application.usecases.produto_crud import (
    atualizar_produto,
    criar_produto,
    obter_produto,
)
from src.domain.catalog.grupo_schema import GruposProdutoResponse
from src.domain.catalog.produto_crud_schema import (
    ProdutoCreateRequest,
    ProdutoCrudResponse,
    ProdutoUpdateRequest,
)
from src.domain.catalog.product_schema import PaginatedProdutosResponse, WebPostoProdutoSchema
from src.application.usecases.fetch_executive_kpis import (
    FetchExecutiveKpisRequest,
    fetch_executive_kpis,
    periodo_preset,
)
from src.domain.adelaide.metrics_schema import AdelaideDashboardMetrics, PeriodoMetricas
from src.infrastructure.cache.valkey_manager import get_cache
from src.infrastructure.config.settings import settings
from src.infrastructure.health.checks import run_health_checks
from src.infrastructure.services.cache_service import get_cache_service
from src.presentation.background_jobs import create_job, get_job, run_job
from src.shared.log_buffer import install_log_buffer, recent_logs
from src.shared.logger import setup_logging

ROOT = _ROOT
THEME_DIR = ROOT / "theme"
ENV_PATH = ROOT / ".env"


def _load_dotenv() -> None:
    if not ENV_PATH.is_file():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line.strip())
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


_load_dotenv()


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or getattr(settings, key.lower(), None) or default).strip()


def normalize_base(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if "qualityautomacao.com.br" in u.lower() and u.lower().startswith("http://"):
        return "https://web.qualityautomacao.com.br"
    return u or "https://web.qualityautomacao.com.br"


_INVALID_CHAVES = frozenset(
    {"", "sua_chave_api_rest_aqui", "SEU_TOKEN_AQUI", "__from_env__"}
)


def _resolve_chave(override: Optional[str] = None) -> str:
    """Chave do body/query ou fallback .env — ignora placeholders inválidos."""
    c = (override or "").strip()
    if c in _INVALID_CHAVES or (c.startswith("__") and c.endswith("__")):
        c = ""
    if c:
        return c
    return (
        _env("WEBPOSTO_API_KEY")
        or _env("WEBPOSTO_CHAVE")
        or (settings.webposto_api_key or "")
    ).strip()


_POSTO_ALIASES = {
    "riodoce": "rio_doce",
    "casacaiada": "casa_caiada",
    "grupo_lisboa": "consolidado",
    "grupolisboa": "consolidado",
    "todas": "consolidado",
    "todos": "consolidado",
    "all": "consolidado",
}

_PRODUCTION_POSTO_IDS = ("rio_doce", "casa_caiada")


def _rede_nome() -> str:
    return (_env("WEBPOSTO_REDE_NOME") or "LISBÔA").strip() or "LISBÔA"


def _parse_posto_sel(posto: Optional[str]) -> List[str]:
    """Aceita um ou vários IDs separados por vírgula (ex: rio_doce,casa_caiada)."""
    if not posto or not str(posto).strip():
        return ["consolidado"]
    ids: List[str] = []
    for part in str(posto).split(","):
        p = part.strip().lower()
        if not p:
            continue
        p = _POSTO_ALIASES.get(p, p)
        if p not in ids:
            ids.append(p)
    return ids or ["consolidado"]


def _dedupe_postos_by_chave(postos: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for p in postos:
        chave = p.get("chave", "")
        if not chave or chave in seen:
            continue
        seen.add(chave)
        out.append(p)
    return out


def _resolve_posto_keys(posto: Optional[str] = None, api_key: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Retorna postos a consultar. Cada item: {"chave", "id", "nome"}.
    Parâmetro posto: consolidado | rio_doce | casa_caiada | rio_doce,casa_caiada
    """
    if api_key:
        api_key_clean = api_key.strip()
        if api_key_clean and api_key_clean not in _INVALID_CHAVES:
            return [{"chave": api_key_clean, "id": "custom", "nome": "Chave customizada"}]

    key_rio_doce = (
        _env("WEBPOSTO_API_KEY_POSTO_VIP_RIO_DOCE")
        or _env("WEBPOSTO_API_KEY_POSTO_VIP_01")
        or _env("WEBPOSTO_API_KEY")
    )
    key_casa_caiada = (
        _env("WEBPOSTO_API_KEY_POSTO_CASA_CAIADA")
        or _env("WEBPOSTO_API_KEY_POSTO_VIP_CASA_CAIADA")
        or _env("WEBPOSTO_API_KEY_POSTO_VIP_02")
    )
    postos_map: Dict[str, Dict[str, str]] = {}
    if key_rio_doce:
        postos_map["rio_doce"] = {
            "chave": key_rio_doce,
            "id": "rio_doce",
            "nome": "POSTO VIP RIO DOCE",
        }
    if key_casa_caiada:
        postos_map["casa_caiada"] = {
            "chave": key_casa_caiada,
            "id": "casa_caiada",
            "nome": "POSTO CASA CAIADA",
        }
    postos_sel = _parse_posto_sel(posto)
    res: List[Dict[str, str]] = []

    if "consolidado" in postos_sel:
        for pid in _PRODUCTION_POSTO_IDS:
            if pid in postos_map:
                res.append(postos_map[pid])
    else:
        for pid in postos_sel:
            if pid in postos_map:
                res.append(postos_map[pid])

    if not res:
        default_key = (
            _env("WEBPOSTO_API_KEY")
            or _env("WEBPOSTO_CHAVE")
            or (settings.webposto_api_key or "")
        ).strip()
        if default_key:
            res.append(
                {
                    "chave": default_key,
                    "id": "default",
                    "nome": _rede_nome(),
                }
            )

    return _dedupe_postos_by_chave(res)


def _parse_grupos_csv(valor: Optional[str]) -> Optional[List[int]]:
    if not valor or not str(valor).strip():
        return None
    out: List[int] = []
    for part in str(valor).split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out or None


def _parse_filial_csv(valor: Optional[str]) -> Optional[List[int]]:
    if not valor or not str(valor).strip():
        return None
    out: List[int] = []
    for part in str(valor).split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out or None


def _parse_tipo_produto(
    tipo: Optional[str],
) -> tuple[Optional[List[str]], bool]:
    """
    tipo_produto: todos | combustivel | codigo:1257884
    Retorna (codigos_produto, apenas_combustivel).
    """
    t = (tipo or "todos").strip().lower()
    if t in ("todos", "all", ""):
        return None, False
    if t in ("combustivel", "combustível", "fuel"):
        return None, True
    if t.startswith("codigo:") or t.startswith("código:"):
        cod = t.split(":", 1)[-1].strip()
        return ([cod] if cod else None), False
    if t.isdigit():
        return [t], False
    return None, False


def _make_webposto_client(chave: str):
    from src.webposto import WebPostoClient, WebPostoConfig

    return WebPostoClient(
        WebPostoConfig(
            chave=chave,
            base_url=normalize_base(
                _env("WEBPOSTO_BASE_URL", settings.webposto_base_url)
            ),
            max_retries=0,
        )
    )


def merge_query(chave: str, query: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    params: Dict[str, Any] = {"CHAVE": chave}
    if not query:
        return params
    for k, v in query.items():
        if v is None or v == "":
            continue
        if isinstance(v, str) and k in ("filial", "produto") and "," in v:
            params[k] = [x.strip() for x in v.split(",") if x.strip()]
        else:
            params[k] = v
    return params


class ProxyBody(BaseModel):
    chave: Optional[str] = None
    path: str
    query: Dict[str, Any] = Field(default_factory=dict)
    method: str = "GET"
    json_body: Optional[Any] = None
    use_cache: bool = True


ExecutiveSummary = AdelaideDashboardMetrics  # alias retrocompatível


def _wp_http_timeout(total: float | None = None) -> httpx.Timeout:
    """Timeout padrão para chamadas à API Quality (5s connect, total configurável)."""
    t = float(total or min(5.0, settings.webposto_timeout_seconds or 5))
    return httpx.Timeout(t, connect=min(2.0, t))


def create_unified_app() -> FastAPI:
    setup_logging(settings.log_level, settings.log_format)
    install_log_buffer()
    app = FastAPI(
        title="Logos WebPosto Gateway",
        version="2026.1",
        description="Proxy Quality · Adelaide · dashboards executivos",
        response_model_by_alias=False,
    )
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for mod_name in ("auth", "metrics", "clientes", "sync", "expenses"):
        try:
            mod = __import__(
                f"src.interfaces.http.routes.{mod_name}",
                fromlist=["router"],
            )
            app.include_router(mod.router)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Rota %s não carregada: %s", mod_name, exc
            )

    try:
        from src.routes_crud import router as crud_router

        app.include_router(crud_router)
    except Exception:
        pass

    try:
        from src.presentation.routes.audit_routes import router as audit_router

        app.include_router(audit_router)
        # Alias /api/v1/audit/* (mesmo router; evita 404 se o front usar prefixo /api)
        app.include_router(audit_router, prefix="/api")
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Rotas audit não carregadas: %s", exc)

    try:
        from src.modules.cash_reconciliation.interfaces.http import router as cash_audit_router

        app.include_router(cash_audit_router)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Rotas cash-audit não carregadas: %s", exc)

    # Auditoria (Mongo) — opcional
    try:
        from src.interfaces.http.routes import auditoria

        app.include_router(auditoria.router)
    except Exception:
        pass

    cache = get_cache()
    cache_svc = get_cache_service()

    async def _adelaide_overview_impl(
        periodo: str,
        api_key: Optional[str],
        role: str = "director",
        *,
        data_inicial: Optional[date] = None,
        data_final: Optional[date] = None,
        filial: Optional[str] = None,
        tipo_produto: Optional[str] = None,
        grupos: Optional[str] = None,
        excluir_afericao: bool = True,
        posto: Optional[str] = "consolidado",
    ) -> AdelaideDashboardMetrics:
        import asyncio
        # Obter a lista de postos para consultar
        postos_to_query = _resolve_posto_keys(posto, api_key)
        if not postos_to_query:
            raise HTTPException(
                status_code=401,
                detail="Nenhuma chave WebPosto encontrada para o posto especificado ou .env desconfigurado.",
            )

        filiais = _parse_filial_csv(filial)
        grupos_ids = _parse_grupos_csv(grupos)
        codigos, apenas_comb = _parse_tipo_produto(tipo_produto)

        # Chave de cache unificada para o conjunto de postos
        postos_str = ",".join(sorted([p["id"] for p in postos_to_query]))
        ck = cache.cache_key(
            "adelaide_consolidated",
            "metrics",
            {
                "p": periodo,
                "postos": postos_str,
                "r": role,
                "di": data_inicial.isoformat() if data_inicial else "",
                "df": data_final.isoformat() if data_final else "",
                "f": filiais,
                "tp": tipo_produto or "",
                "gp": grupos or "",
                "af": excluir_afericao,
            },
        )
        cached = cache.get_json(ck)
        if cached is not None:
            return AdelaideDashboardMetrics.model_validate(cached)

        t0 = time.perf_counter()

        # Função auxiliar para consultar um posto individual (usa cache individual interno se houver)
        async def _query_single_posto_metrics(p_info: Dict[str, str]) -> AdelaideDashboardMetrics:
            p_chave = p_info["chave"]
            
            # Cache do posto individual
            p_ck = cache.cache_key(
                "adelaide_single",
                "metrics",
                {
                    "p": periodo,
                    "k": p_chave[-8:],
                    "r": role,
                    "di": data_inicial.isoformat() if data_inicial else "",
                    "df": data_final.isoformat() if data_final else "",
                    "f": filiais,
                    "tp": tipo_produto or "",
                    "gp": grupos or "",
                    "af": excluir_afericao,
                },
            )
            p_cached = cache.get_json(p_ck)
            if p_cached is not None:
                return AdelaideDashboardMetrics.model_validate(p_cached)

            from src.webposto import WebPostoClient, WebPostoConfig
            client = WebPostoClient(
                WebPostoConfig(
                    chave=p_chave,
                    base_url=normalize_base(
                        _env("WEBPOSTO_BASE_URL", settings.webposto_base_url)
                    ),
                    max_retries=0,
                )
            )
            out_single = await build_adelaide_metrics(
                periodo,
                client,
                role=role,
                data_inicial=data_inicial,
                data_final=data_final,
                filial=filiais,
                codigos_produto=codigos,
                grupos_produto=grupos_ids,
                apenas_combustivel=apenas_comb,
                excluir_afericao=excluir_afericao,
                strict=True,
            )
            # Salva no cache individual do posto (300 segundos)
            cache.set_json(p_ck, out_single.model_dump(mode="json"), ttl=300)
            return out_single

        # Consulta concorrente (paralelismo real usando asyncio.gather)
        tasks = [_query_single_posto_metrics(p_info) for p_info in postos_to_query]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results: List[AdelaideDashboardMetrics] = []
        errors = []
        for p_info, res in zip(postos_to_query, results):
            if isinstance(res, Exception):
                errors.append(f"Erro em {p_info['nome']}: {res}")
            else:
                valid_results.append(res)

        # Se nenhum resultado for válido, levanta erro
        if not valid_results:
            raise HTTPException(
                status_code=502,
                detail=f"Não foi possível obter dados de nenhum posto. Erros: {'; '.join(errors)}",
            )

        # Se pedimos um posto e obtivemos ele, ou sobrou só 1 posto válido
        if len(valid_results) == 1:
            out = valid_results[0]
            # Se for consolidado ou tiver mais postos configurados mas só 1 respondeu, avisa na mensagem
            if len(postos_to_query) > 1:
                out = out.model_copy(
                    update={
                        "mensagem": f"Apenas um posto respondeu. {'; '.join(errors)}",
                        "status_api": "dados_parciais"
                    }
                )
        else:
            # Consolidação matemática precisa (Decimal)
            from decimal import Decimal
            from src.domain.catalog.grupo_schema import UnidadeWebPosto
            from src.domain.adelaide.metrics_schema import quantize_money, mask_metrics_for_role

            faturamento_bruto = Decimal("0")
            faturamento_nao_combustivel = Decimal("0")
            galonagem_total = Decimal("0")
            credito_recuperavel = Decimal("0")
            despesas_caixa = Decimal("0")
            margem_liquida_real = Decimal("0")
            qtd_abastecimentos = 0
            qtd_itens_venda = 0
            
            fallback_any = False
            dados_reais_all = True
            
            # Combinação de produtos por código
            produtos_map = {}
            for r in valid_results:
                faturamento_bruto += r.faturamento_bruto
                faturamento_nao_combustivel += r.faturamento_nao_combustivel
                galonagem_total += r.galonagem_total
                credito_recuperavel += r.credito_recuperavel
                despesas_caixa += r.despesas_caixa
                margem_liquida_real += r.margem_liquida_real
                qtd_abastecimentos += r.qtd_abastecimentos
                qtd_itens_venda += r.qtd_itens_venda
                
                if r.fallback:
                    fallback_any = True
                if not r.dados_reais:
                    dados_reais_all = False
                
                for prod in r.por_produto:
                    cod = prod.get("codigo")
                    if cod is None:
                        cod = prod.get("nome") or "sem_codigo"
                    nome = prod.get("nome") or "Desconhecido"
                    litros_val = Decimal(prod.get("litros") or "0")
                    fat_val = Decimal(prod.get("faturamento") or "0")
                    pis_val = Decimal(prod.get("pis_cofins") or "0")
                    
                    if cod in produtos_map:
                        produtos_map[cod]["litros"] += litros_val
                        produtos_map[cod]["faturamento"] += fat_val
                        produtos_map[cod]["pis_cofins"] += pis_val
                    else:
                        produtos_map[cod] = {
                            "codigo": cod,
                            "nome": nome,
                            "litros": litros_val,
                            "faturamento": fat_val,
                            "pis_cofins": pis_val,
                        }

            # Monta lista final de por_produto
            por_produto_aggregated = []
            for p_data in produtos_map.values():
                por_produto_aggregated.append({
                    "codigo": p_data["codigo"],
                    "nome": p_data["nome"],
                    "litros": format(quantize_money(p_data["litros"]), "f"),
                    "faturamento": format(quantize_money(p_data["faturamento"]), "f"),
                    "pis_cofins": format(quantize_money(p_data["pis_cofins"]), "f"),
                })

            # Combustíveis (Auditoria Fiscal de CST) - Carregamos do catálogo fiscal local
            from src.domain.adelaide.fiscal_catalog import list_fiscal_audit_rows
            combustiveis = list_fiscal_audit_rows()

            rede = _rede_nome()
            nomes_unidades = ", ".join(p["nome"] for p in postos_to_query)
            unidade_consolidada = UnidadeWebPosto(
                empresa_codigo=999,
                fantasia=rede,
                razao_social=f"{rede} — {nomes_unidades}",
                cnpj="",
                base_url="",
                chave_mascarada="MULTI_UNIDADE",
            )

            msg_errors = f" | Erros parciais: {'; '.join(errors)}" if errors else ""
            out = AdelaideDashboardMetrics(
                faturamento_bruto=faturamento_bruto,
                faturamento_nao_combustivel=faturamento_nao_combustivel,
                galonagem_total=galonagem_total,
                credito_recuperavel=credito_recuperavel,
                despesas_caixa=despesas_caixa,
                margem_liquida_real=margem_liquida_real,
                periodo=valid_results[0].periodo,
                status_api="dados_reais_live" if dados_reais_all else "dados_parciais",
                fallback=fallback_any,
                dados_reais=dados_reais_all,
                mensagem=f"{rede}: {len(valid_results)} unidade(s) consolidada(s){msg_errors}.",
                unidade=unidade_consolidada,
                combustiveis=combustiveis,
                por_produto=por_produto_aggregated,
                qtd_abastecimentos=qtd_abastecimentos,
                qtd_itens_venda=qtd_itens_venda,
                data_inicial=valid_results[0].data_inicial,
                data_final=valid_results[0].data_final,
                filtros_aplicados={
                    "periodo": periodo,
                    "rede": rede,
                    "postos_ids": [p["id"] for p in postos_to_query],
                    "postos_consultados": [p["nome"] for p in postos_to_query],
                    "excluir_afericao": excluir_afericao,
                },
            )
            # Reaplica máscara de permissão se necessário
            out = mask_metrics_for_role(out, role)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if elapsed_ms > 15:
            import logging
            logging.getLogger(__name__).debug(
                "Adelaide consolidated metrics %sms (alvo <15ms com cache quente)", elapsed_ms
            )

        # Salva o resultado final consolidado no cache (300 segundos)
        cache.set_json(ck, out.model_dump(mode="json"), ttl=300)
        return out

    @app.on_event("startup")
    async def prewarm_adelaide_kpis() -> None:
        """Pré-aquece KPIs Hoje / 7D / 30D em background (Grok cache layer)."""
        import asyncio

        async def _run() -> None:
            # Apenas 'hoje' e '7d' para evitar o processamento pesado de 30 dias na inicialização síncrona
            for p in ("hoje", "7d"):
                try:
                    await _adelaide_overview_impl(p, None, posto="consolidado")
                except Exception:
                    pass

        asyncio.create_task(_run())

    @app.get("/health", tags=["gateway"])
    async def gateway_health():
        chave = _resolve_chave()
        base = normalize_base(_env("WEBPOSTO_BASE_URL", settings.webposto_base_url))
        report = await run_health_checks(base, has_api_key=bool(chave))
        report["engine"] = "Adelaide Cloud Native"
        report["valkey_cache"] = cache.stats().get("backend", "memory")
        report["cache_hit_ratio_pct"] = cache.stats().get("hit_ratio_pct", 0)
        return report

    @app.get("/internal/logs/recent", tags=["internal"])
    def internal_logs_recent(limit: int = Query(50, ge=1, le=200)):
        """Últimas linhas de log (buffer em memória — apenas dev/diagnóstico)."""
        if settings.environment == "production" and not settings.debug:
            raise HTTPException(status_code=404, detail="Not found")
        return {"lines": recent_logs(limit)}

    @app.get("/api/v1/dashboard/filtros", tags=["gateway", "dashboard"])
    async def dashboard_filtros_meta():
        """Catálogo de filtros suportados no cockpit e parâmetros da API Quality."""
        return build_filtros_meta()

    @app.get("/dashboard", response_class=HTMLResponse, tags=["gateway"])
    async def dashboard_executivo():
        p = ROOT / "static" / "dashboard_logos.html"
        if not p.is_file():
            raise HTTPException(404, "static/dashboard_logos.html não encontrado")
        return FileResponse(p, media_type="text/html; charset=utf-8")

    @app.get("/produtos", response_class=HTMLResponse, tags=["gateway", "produtos"])
    async def pagina_produtos_crud():
        p = ROOT / "static" / "produtos_crud.html"
        if not p.is_file():
            raise HTTPException(404, "static/produtos_crud.html não encontrado")
        return FileResponse(p, media_type="text/html; charset=utf-8")

    @app.get("/api/v1/proxy/{endpoint:path}", tags=["gateway"])
    async def webposto_proxy_v1(
        endpoint: str,
        request: Request,
        api_key: Optional[str] = Query(None, alias="api_key"),
    ):
        """Proxy reverso GET — CHAVE na query WebPosto (não Bearer)."""
        chave = _resolve_chave(api_key)
        if not chave:
            raise HTTPException(
                status_code=401,
                detail="Chave de integração WebPosto não informada.",
            )

        path = endpoint.strip()
        if not path.startswith("/"):
            path = f"/{path}"
        if not path.upper().startswith("/INTEGRACAO"):
            path = f"/INTEGRACAO/{path.lstrip('/')}"

        fwd: Dict[str, Any] = dict(request.query_params)
        fwd.pop("api_key", None)

        base = normalize_base(_env("WEBPOSTO_BASE_URL", settings.webposto_base_url))
        url = f"{base}{path}"
        params = merge_query(chave, fwd)
        ck = cache.cache_key("proxy_v1", path, params)
        cached = cache.get_json(ck)
        if cached is not None:
            cached["cache_hit"] = True
            return cached

        t0 = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=_wp_http_timeout(15.0), verify=True
            ) as client:
                response = await client.get(url, params=params)
        except httpx.RequestError as exc:
            stale = cache.get_json(ck + ":stale")
            if stale is not None:
                stale["cache_hit"] = True
                stale["stale"] = True
                return stale
            raise HTTPException(status_code=502, detail=f"Rede: {exc!s}") from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if response.status_code != 200:
            detail = response.text[:500] if response.text else "Erro na API Quality"
            raise HTTPException(status_code=response.status_code, detail=detail)

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        payload = {
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "data": body,
            "cache_hit": False,
        }
        if response.status_code == 200:
            cache.set_json(ck, payload, ttl=60)
            cache.set_json(ck + ":stale", payload, ttl=600)
        return payload

    @app.get("/api/v1/adelaide/overview", response_model=AdelaideDashboardMetrics, tags=["adelaide"])
    async def get_adelaide_executive_overview(
        periodo: str = Query("mensal"),
        api_key: Optional[str] = Query(None, alias="api_key"),
        role: str = Query("director", description="director|presidente|operador"),
        data_inicial: Optional[date] = Query(None, description="Data inicial (sobrescreve preset)"),
        data_final: Optional[date] = Query(None, description="Data final (sobrescreve preset)"),
        filial: Optional[str] = Query(None, description="Códigos de filial separados por vírgula"),
        tipo_produto: Optional[str] = Query(
            None,
            description="todos | combustivel | codigo:1257884",
        ),
        grupos: Optional[str] = Query(
            None, description="Códigos de grupo separados por vírgula (ex: 24554,24555)"
        ),
        excluir_afericao: bool = Query(True, description="Excluir registros de aferição"),
        posto: Optional[str] = Query(
            "consolidado",
            description="Uma ou mais unidades: consolidado (LISBÔA), rio_doce (POSTO VIP RIO DOCE), casa_caiada (POSTO CASA CAIADA)",
        ),
    ):
        p = "mensal" if periodo in ("30d", "30dias") else periodo
        return await _adelaide_overview_impl(
            p,
            api_key,
            role,
            data_inicial=data_inicial,
            data_final=data_final,
            filial=filial,
            tipo_produto=tipo_produto,
            grupos=grupos,
            excluir_afericao=excluir_afericao,
            posto=posto,
        )

    @app.post("/api/v1/adelaide/metrics/async", status_code=202, tags=["adelaide"])
    async def fetch_adelaide_metrics_async(
        background_tasks: BackgroundTasks,
        periodo: PeriodoMetricas = Query(PeriodoMetricas.mensal),
        api_key: Optional[str] = Query(None, alias="api_key"),
        role: str = Query("director"),
        data_inicial: Optional[date] = Query(None),
        data_final: Optional[date] = Query(None),
        filial: Optional[str] = Query(None),
        tipo_produto: Optional[str] = Query(None),
        grupos: Optional[str] = Query(None),
        excluir_afericao: bool = Query(True),
        posto: Optional[str] = Query(
            "consolidado",
            description="Uma ou mais unidades: consolidado (LISBÔA), rio_doce (POSTO VIP RIO DOCE), casa_caiada (POSTO CASA CAIADA)",
        ),
    ):
        """Consulta pesada em background — HTTP 202 + polling em /api/v1/jobs/{id}."""
        job_id = await create_job()
        p = periodo.value

        async def _work():
            return await _adelaide_overview_impl(
                p,
                api_key,
                role,
                data_inicial=data_inicial,
                data_final=data_final,
                filial=filial,
                tipo_produto=tipo_produto,
                grupos=grupos,
                excluir_afericao=excluir_afericao,
                posto=posto,
            )

        background_tasks.add_task(run_job, job_id, _work())
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "accepted",
                "poll_url": f"/api/v1/jobs/{job_id}",
            },
        )

    @app.get("/api/v1/jobs/{job_id}", tags=["adelaide"])
    async def get_async_job(job_id: str):
        rec = await get_job(job_id)
        if not rec:
            raise HTTPException(404, "Job não encontrado")
        payload: Dict[str, Any] = {
            "job_id": rec.id,
            "status": rec.status.value,
            "created_at": rec.created_at,
            "finished_at": rec.finished_at,
        }
        if rec.status.value == "done" and rec.result is not None:
            payload["result"] = (
                rec.result.model_dump(mode="json")
                if hasattr(rec.result, "model_dump")
                else rec.result
            )
        if rec.error:
            payload["error"] = rec.error
        return payload

    @app.get(
        "/api/v1/adelaide/metrics",
        response_model=AdelaideDashboardMetrics,
        tags=["adelaide"],
    )
    async def fetch_adelaide_metrics(
        periodo: PeriodoMetricas = Query(PeriodoMetricas.mensal),
        api_key: Optional[str] = Query(None, alias="api_key"),
        role: str = Query("director", description="director|presidente|operador"),
        data_inicial: Optional[date] = Query(None, description="Data inicial (sobrescreve preset)"),
        data_final: Optional[date] = Query(None, description="Data final (sobrescreve preset)"),
        filial: Optional[str] = Query(None, description="Códigos de filial separados por vírgula"),
        tipo_produto: Optional[str] = Query(
            None,
            description="todos | combustivel | codigo:1257884",
        ),
        grupos: Optional[str] = Query(
            None, description="Códigos de grupo separados por vírgula"
        ),
        excluir_afericao: bool = Query(True, description="Excluir registros de aferição"),
        posto: Optional[str] = Query(
            "consolidado",
            description="Uma ou mais unidades: consolidado (LISBÔA), rio_doce (POSTO VIP RIO DOCE), casa_caiada (POSTO CASA CAIADA)",
        ),
    ):
        """Orquestrador tributário Adelaide — somente dados reais WebPosto + cache 60s."""
        p = periodo.value
        return await _adelaide_overview_impl(
            p,
            api_key,
            role,
            data_inicial=data_inicial,
            data_final=data_final,
            filial=filial,
            tipo_produto=tipo_produto,
            grupos=grupos,
            excluir_afericao=excluir_afericao,
            posto=posto,
        )

    @app.get(
        "/api/v1/webposto/grupos-produto",
        response_model=GruposProdutoResponse,
        tags=["webposto", "produtos"],
    )
    async def get_webposto_grupos_produto(
        api_key: Optional[str] = Query(None, alias="api_key"),
    ):
        """Grupos reais agregados do catálogo PRODUTO (multi-seleção no cockpit)."""
        chave = _resolve_chave(api_key)
        if not chave:
            raise HTTPException(
                status_code=401,
                detail="Chave WebPosto ausente. Configure WEBPOSTO_API_KEY no .env ou informe api_key.",
            )
        ck = cache.cache_key(
            "grupos_produto",
            "/INTEGRACAO/PRODUTO",
            {"k": chave[-8:]},
        )
        cached = cache.get_json(ck)
        if cached is not None:
            return GruposProdutoResponse.model_validate(cached).model_copy(
                update={"cache_hit": True}
            )
        try:
            from src.webposto import WebPostoClient, WebPostoConfig
            from src.webposto.exceptions import AuthError
            from src.application.usecases.fetch_unidade_webposto import fetch_unidade_webposto

            client = WebPostoClient(
                WebPostoConfig(
                    chave=chave,
                    base_url=normalize_base(
                        _env("WEBPOSTO_BASE_URL", settings.webposto_base_url)
                    ),
                    max_retries=0,
                )
            )
            # Injeta o código da empresa para consultas subsequentes a bicos e ativos
            unidade = await fetch_unidade_webposto(
                client,
                base_url=normalize_base(_env("WEBPOSTO_BASE_URL", settings.webposto_base_url)),
                chave=chave,
            )
            if unidade and unidade.empresa_codigo is not None:
                client._config.empresa_codigo = unidade.empresa_codigo

            base = normalize_base(
                _env("WEBPOSTO_BASE_URL", settings.webposto_base_url)
            )
            result = await fetch_produto_grupos(
                client, base_url=base, chave=chave
            )
        except AuthError:
            raise HTTPException(status_code=401, detail="Chave WebPosto inválida.")
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Não foi possível listar grupos: {exc!s}",
            )
        cache.set_json(ck, result.model_dump(mode="json"), ttl=300)
        return result

    @app.get(
        "/api/v1/webposto/produtos",
        response_model=PaginatedProdutosResponse,
        tags=["webposto", "produtos"],
    )
    async def get_webposto_produtos(
        pagina: int = Query(1, ge=1, description="Página (1-based)"),
        limite: int = Query(50, ge=1, le=200, alias="limit"),
        descricao: Optional[str] = Query(None, description="Filtro por nome/descrição"),
        grupo: Optional[int] = Query(None, description="Código do grupo de produto (único)"),
        grupos: Optional[str] = Query(
            None, description="Vários grupos separados por vírgula"
        ),
        situacao: str = Query(
            "todos",
            description="Filtro de status: todos | ativos | inativos",
        ),
        tipo_produto: Optional[str] = Query(
            None,
            description="Tipo do produto: C|P|S|combustivel|todos",
        ),
        subgrupo: Optional[int] = Query(
            None,
            description="Código subGrupo1/2/3 (Quality)",
        ),
        subgrupos: Optional[str] = Query(
            None, description="Vários subgrupos separados por vírgula"
        ),
        todos: bool = Query(
            False,
            description="Catálogo completo: todas as páginas, sem repetir código de produto",
        ),
        api_key: Optional[str] = Query(None, alias="api_key"),
    ):
        """
        Catálogo completo via GET /INTEGRACAO/PRODUTO (CHAVE na query — integração Quality).
        """
        chave = _resolve_chave(api_key)
        if not chave:
            raise HTTPException(
                status_code=401,
                detail="Chave WebPosto ausente. Configure WEBPOSTO_API_KEY no .env ou informe api_key.",
            )

        grupos_ids = _parse_grupos_csv(grupos)
        subgrupos_ids = _parse_grupos_csv(subgrupos)
        sit = (situacao or "todos").strip().lower()
        if sit not in ("todos", "ativos", "inativos"):
            sit = "todos"
        ck = cache.cache_key(
            "produtos",
            "/INTEGRACAO/PRODUTO/v2",
            {
                "p": pagina,
                "l": limite,
                "all": todos,
                "d": descricao or "",
                "g": grupo,
                "gs": grupos or "",
                "sit": sit,
                "tp": tipo_produto or "",
                "sg": subgrupo,
                "sgs": subgrupos or "",
                "k": chave[-8:],
            },
        )
        cached = cache.get_json(ck)
        if cached is not None:
            out = PaginatedProdutosResponse.model_validate(cached)
            return out.model_copy(update={"cache_hit": True})

        try:
            from src.webposto import WebPostoClient, WebPostoConfig
            from src.webposto.exceptions import AuthError
            from src.application.usecases.fetch_unidade_webposto import fetch_unidade_webposto

            client = WebPostoClient(
                WebPostoConfig(
                    chave=chave,
                    base_url=normalize_base(
                        _env("WEBPOSTO_BASE_URL", settings.webposto_base_url)
                    ),
                    max_retries=0,
                )
            )
            # Carrega a unidade para saber o codigo da empresa e injetar se necessário
            unidade = await fetch_unidade_webposto(
                client,
                base_url=normalize_base(_env("WEBPOSTO_BASE_URL", settings.webposto_base_url)),
                chave=chave,
            )
            if unidade and unidade.empresa_codigo is not None:
                client._config.empresa_codigo = unidade.empresa_codigo

            if todos:
                result = await fetch_produtos_catalog_completo(
                    client,
                    descricao=descricao,
                    grupo=grupo,
                    grupos=grupos_ids,
                    situacao=sit,  # type: ignore[arg-type]
                    tipo_produto=tipo_produto,
                    subgrupo=subgrupo,
                    subgrupos=subgrupos_ids,
                )
            else:
                result = await fetch_produtos_catalog(
                    client,
                    pagina=pagina,
                    limite=limite,
                    descricao=descricao,
                    grupo=grupo,
                    grupos=grupos_ids,
                    situacao=sit,  # type: ignore[arg-type]
                    tipo_produto=tipo_produto,
                    subgrupo=subgrupo,
                    subgrupos=subgrupos_ids,
                )
        except AuthError:
            raise HTTPException(
                status_code=401,
                detail="Chave WebPosto inválida ou sem permissão em PRODUTO.",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Serviço WebPosto temporariamente indisponível: {exc!s}",
            )

        cache.set_json(ck, result.model_dump(mode="json"), ttl=300 if todos else 60)
        return result

    @app.get(
        "/api/v1/webposto/produtos/{produto_id}",
        response_model=WebPostoProdutoSchema,
        tags=["webposto", "produtos"],
    )
    async def get_webposto_produto_por_id(
        produto_id: int,
        api_key: Optional[str] = Query(None, alias="api_key"),
    ):
        chave = _resolve_chave(api_key)
        if not chave:
            raise HTTPException(status_code=401, detail="Configure WEBPOSTO_API_KEY no .env")
        try:
            from src.webposto.exceptions import AuthError, NotFoundError

            client = _make_webposto_client(chave)
            produto = await obter_produto(client, produto_id)
        except AuthError:
            raise HTTPException(status_code=401, detail="Chave WebPosto inválida.")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        if produto is None:
            raise HTTPException(status_code=404, detail=f"Produto {produto_id} não encontrado")
        return produto

    @app.post(
        "/api/v1/webposto/produtos",
        response_model=ProdutoCrudResponse,
        tags=["webposto", "produtos"],
    )
    async def post_webposto_produto(
        body: ProdutoCreateRequest,
        api_key: Optional[str] = Query(None, alias="api_key"),
    ):
        chave = _resolve_chave(api_key)
        if not chave:
            raise HTTPException(status_code=401, detail="Configure WEBPOSTO_API_KEY no .env")
        try:
            from src.webposto.exceptions import AuthError, BadRequestError

            client = _make_webposto_client(chave)
            return await criar_produto(client, body)
        except AuthError:
            raise HTTPException(status_code=401, detail="Chave WebPosto inválida.")
        except BadRequestError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.put(
        "/api/v1/webposto/produtos/{produto_id}",
        response_model=ProdutoCrudResponse,
        tags=["webposto", "produtos"],
    )
    async def put_webposto_produto(
        produto_id: int,
        body: ProdutoUpdateRequest,
        api_key: Optional[str] = Query(None, alias="api_key"),
    ):
        chave = _resolve_chave(api_key)
        if not chave:
            raise HTTPException(status_code=401, detail="Configure WEBPOSTO_API_KEY no .env")
        try:
            from src.webposto.exceptions import AuthError, BadRequestError

            client = _make_webposto_client(chave)
            return await atualizar_produto(client, produto_id, body)
        except AuthError:
            raise HTTPException(status_code=401, detail="Chave WebPosto inválida.")
        except BadRequestError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.get("/api/config")
    async def api_config():
        k = (
            _env("WEBPOSTO_API_KEY")
            or _env("WEBPOSTO_CHAVE")
            or settings.webposto_api_key
            or ""
        ).strip()
        ph = "sua_chave_api_rest_aqui"
        valid = bool(k and k not in (ph, "SEU_TOKEN_AQUI"))
        hint = f"{k[:4]}…{k[-4:]}" if valid and len(k) >= 12 else None
        return {
            "has_key": valid,
            "key_hint": hint,
            "base_url": normalize_base(
                _env("WEBPOSTO_BASE_URL", settings.webposto_base_url)
            ),
            "cache": cache.stats(),
        }

    @app.get("/api/health/webposto")
    async def health_webposto_key():
        """Monitoramento da chave .env com try/except dedicado."""
        chave = (
            _env("WEBPOSTO_API_KEY")
            or _env("WEBPOSTO_CHAVE")
            or settings.webposto_api_key
        ).strip()
        if not chave:
            return {"ok": False, "detail": "WEBPOSTO_API_KEY ausente no .env"}
        base = normalize_base(_env("WEBPOSTO_BASE_URL", settings.webposto_base_url))
        url = f"{base}/INTEGRACAO/EMPRESAS"
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=_wp_http_timeout(5.0)) as client:
                r = await client.get(url, params={"CHAVE": chave})
            elapsed = int((time.perf_counter() - t0) * 1000)
            return {
                "ok": r.status_code == 200,
                "status_code": r.status_code,
                "elapsed_ms": elapsed,
                "endpoint_testado": "/INTEGRACAO/EMPRESAS",
            }
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}

    @app.post("/api/webposto/proxy")
    async def webposto_proxy(req: ProxyBody):
        chave = _resolve_chave(req.chave)
        if not chave:
            raise HTTPException(
                status_code=400,
                detail="Informe a CHAVE no dashboard ou configure WEBPOSTO_API_KEY no .env",
            )

        path = req.path if req.path.startswith("/") else f"/{req.path}"
        method = req.method.upper().strip()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            raise HTTPException(status_code=400, detail="Método não suportado")

        ck = cache.cache_key("proxy", path, {**req.query, "m": method})
        if req.use_cache and method == "GET":
            cached = cache.get_json(ck)
            if cached is not None:
                cached["cache_hit"] = True
                return cached

        base = normalize_base(_env("WEBPOSTO_BASE_URL", settings.webposto_base_url))
        url = f"{base}{path}"
        params = merge_query(chave, req.query)
        t0 = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=_wp_http_timeout(30.0), verify=True
            ) as client:
                if method == "GET":
                    r = await client.get(url, params=params)
                elif method == "POST":
                    r = await client.post(url, params=params, json=req.json_body)
                elif method == "PUT":
                    r = await client.put(url, params=params, json=req.json_body)
                else:
                    r = await client.request(
                        method, url, params=params, json=req.json_body
                    )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Rede: {exc!s}") from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            try:
                body = r.json()
            except Exception:
                body = r.text
        else:
            body = r.text[:50000] if r.text else None
        if body is None and r.text:
            body = r.text[:50000]

        payload = {
            "status_code": r.status_code,
            "elapsed_ms": elapsed_ms,
            "content_type": ct,
            "url_requested": str(r.request.url),
            "body": body,
            "cache_hit": False,
        }
        if req.use_cache and method == "GET" and r.status_code == 200:
            cache.set_json(ck, payload, ttl=60)
        return payload

    @app.get("/api/executive/kpis")
    async def executive_kpis(
        periodo: str = Query("hoje", description="hoje | 7d | 30d"),
        request: Request = None,
    ):
        role = "director"
        if request:
            token = request.cookies.get("access_token")
            if token:
                try:
                    from src.infrastructure.security.jwt_utils import decode_token

                    role = decode_token(token).get("role", "director")
                except Exception:
                    pass

        di, df, label = periodo_preset(periodo)
        try:
            from src.webposto import WebPostoClient, WebPostoConfig

            chave = (
                _env("WEBPOSTO_API_KEY")
                or _env("WEBPOSTO_CHAVE")
                or settings.webposto_api_key
            )
            client = WebPostoClient(
                WebPostoConfig(
                    chave=chave,
                    base_url=normalize_base(
                        _env("WEBPOSTO_BASE_URL", settings.webposto_base_url)
                    ),
                    max_retries=0,
                )
            )
            resp = await fetch_executive_kpis(
                FetchExecutiveKpisRequest(
                    data_inicial=di,
                    data_final=df,
                    periodo_label=label,
                    role=role,
                ),
                client,
            )
            return resp.model_dump(mode="json")
        except Exception as exc:
            from src.domain.adelaide.tax_profile import ExecutiveKpiSummary

            empty = ExecutiveKpiSummary(
                periodo=label,
                fallback=True,
                mensagem=str(exc),
            )
            return {
                "periodo": label,
                "kpis": empty.model_dump(mode="json"),
                "anomalias_caixa": [],
                "ok": False,
                "fallback": True,
                "mensagem": str(exc),
            }

    @app.get("/api/cache/stats")
    async def cache_stats():
        return cache.stats()

    # ── Frontend estático ─────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def dashboard_root():
        p = ROOT / "dashboard_vendas.html"
        if not p.is_file():
            raise HTTPException(404, "dashboard_vendas.html não encontrado")
        return FileResponse(p, media_type="text/html; charset=utf-8")

    @app.get("/app/vendas", response_class=HTMLResponse)
    async def dashboard_vendas():
        return await dashboard_root()

    if THEME_DIR.is_dir():
        app.mount("/theme", StaticFiles(directory=str(THEME_DIR)), name="theme")

    static = ROOT / "static"
    if static.is_dir():
        app.mount("/static", StaticFiles(directory=str(static)), name="static")

    js_catalog = ROOT / "api_hub_catalog.js"
    if js_catalog.is_file():

        @app.get("/api_hub_catalog.js")
        async def catalog_js():
            return FileResponse(js_catalog, media_type="application/javascript")

    return app


app = create_unified_app()


def main() -> None:
    import uvicorn

    port = int(
        _env("API_PORT") or _env("EXPLORADOR_PORT") or "5000"
    )
    print("\n  Logos WebPosto Gateway")
    print(f"  Health:    http://127.0.0.1:{port}/health")
    print(f"  Cockpit:   http://127.0.0.1:{port}/dashboard")
    print(f"  Produtos:  http://127.0.0.1:{port}/produtos")
    print(f"  Operacional: http://127.0.0.1:{port}/\n")
    uvicorn.run(
        "src.presentation.app:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
