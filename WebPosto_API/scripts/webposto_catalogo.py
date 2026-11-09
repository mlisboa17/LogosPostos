"""Catálogo vivo da API de Integração do webPosto (Quality Automação).

Três passos, todos somente leitura:
  baixar   baixa a OpenAPI oficial e guarda uma cópia datada em docs/external/webposto/
  sondar   chama cada rota GET com a chave de uma empresa e registra status, tempo, quantidade
           e campos devolvidos (nunca valores). Escritas (POST/PUT/PATCH/DELETE) NUNCA são chamadas.
  gerar    monta docs/external/webposto/CATALOGO_API.md a partir da OpenAPI + última sondagem

Uso (na pasta WebPosto_API):
  python scripts/webposto_catalogo.py baixar
  python scripts/webposto_catalogo.py sondar --empresa 74014 --env-var WEBPOSTO_API_KEY_POSTO_DOZE_FILIAL_II
  python scripts/webposto_catalogo.py gerar

A chave é lida do .env (ou de --env-file) e nunca é impressa nem gravada.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

BASE = "https://web.qualityautomacao.com.br"
SPEC_URL = BASE + "/v3/api-docs/integracao"
RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "docs" / "external" / "webposto"
ESCRITA = ("post", "put", "patch", "delete")
# GET com nome de ação: não é chamado nem na sondagem (pode ter efeito colateral).
_GET_SUSPEITO = re.compile(r"ENVIAR|AUTORIZ|CORRIGIR|FATURAR|REAJUST|LANCAR|CONSOLIDAR|CONCILIAR",
                           re.IGNORECASE)


def _ler_env(arquivo: Path, var: str) -> str:
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if linha.strip().startswith(f"{var}="):
            return linha.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _spec_mais_recente() -> Path:
    arquivos = sorted(PASTA.glob("openapi_integracao_*.json"))
    if not arquivos:
        sys.exit("Nenhuma OpenAPI baixada. Rode: python scripts/webposto_catalogo.py baixar")
    return arquivos[-1]


def baixar(_args) -> None:
    r = httpx.get(SPEC_URL, timeout=120)
    r.raise_for_status()
    PASTA.mkdir(parents=True, exist_ok=True)
    destino = PASTA / f"openapi_integracao_{date.today().isoformat()}.json"
    destino.write_bytes(r.content)
    d = r.json()
    ops = [(m, p) for p, v in d["paths"].items() for m in v if m in ("get",) + ESCRITA]
    print(f"{destino.name}: {len(d['paths'])} rotas, {len(ops)} operações "
          f"({sum(m == 'get' for m, _ in ops)} leituras, {sum(m != 'get' for m, _ in ops)} escritas)")


# ---------------------------------------------------------------- sondagem

def _valor(param: dict, empresa: int, hoje: date):
    nome, sch = param["name"], param.get("schema", {})
    if "enum" in sch:
        return sch["enum"][0]
    if nome.lower() in ("empresacodigo", "filial", "unidade") or nome == "filiais":
        return empresa
    fmt, tipo = sch.get("format"), sch.get("type")
    if fmt == "date":
        return (hoje if "final" in nome.lower() else hoje - timedelta(days=7)).isoformat()
    if fmt == "date-time":
        return (datetime.combine(hoje, datetime.min.time()) if "final" not in nome.lower()
                else datetime.combine(hoje, datetime.max.time().replace(microsecond=0))).isoformat()
    if nome == "limite":
        return 5
    if tipo == "boolean":
        return "false"
    return None  # sem valor seguro: a rota fica como "precisa de parâmetro"


def _forma(corpo) -> tuple[str, int | None, list[str]]:
    if isinstance(corpo, dict) and isinstance(corpo.get("resultados"), list):
        itens = corpo["resultados"]
        campos = sorted({k for x in itens if isinstance(x, dict) for k in x})
        return "paginado", len(itens), campos
    if isinstance(corpo, list):
        campos = sorted({k for x in corpo if isinstance(x, dict) for k in x})
        return "lista", len(corpo), campos
    if isinstance(corpo, dict):
        return "objeto", None, sorted(corpo)
    return type(corpo).__name__, None, []


def sondar(args) -> None:
    env = Path(args.env_file) if args.env_file else RAIZ / "WebPosto_API" / ".env"
    chave = _ler_env(env, args.env_var)
    if not chave:
        sys.exit(f"Variável {args.env_var} não encontrada em {env}")
    spec = json.loads(_spec_mais_recente().read_text(encoding="utf-8"))
    hoje = date.today()
    resultados = []
    with httpx.Client(base_url=BASE, timeout=90) as http:
        for caminho, metodos in sorted(spec["paths"].items()):
            for metodo, op in metodos.items():
                if metodo in ESCRITA:
                    resultados.append({"metodo": metodo.upper(), "rota": caminho, "estado": "escrita_nao_testada"})
                    continue
                if metodo != "get":
                    continue
                item = {"metodo": "GET", "rota": caminho}
                if _GET_SUSPEITO.search(caminho):
                    resultados.append({**item, "estado": "get_com_acao_nao_testado"})
                    continue
                params, falta = {"CHAVE": chave}, []
                for p in op.get("parameters", []):
                    v = _valor(p, args.empresa, hoje)
                    if p["in"] == "path":
                        if v is None:
                            falta.append(p["name"])
                        continue
                    if v is not None and (p.get("required") or p["name"] in ("empresaCodigo", "limite",
                                                                             "dataInicial", "dataFinal")):
                        params[p["name"]] = v
                    elif p.get("required") and v is None:
                        falta.append(p["name"])
                if falta or "{" in caminho:
                    resultados.append({**item, "estado": "precisa_parametro", "faltam": falta or ["id na rota"]})
                    continue
                t0 = time.perf_counter()
                try:
                    r = http.get(caminho, params=params)
                    ms = round((time.perf_counter() - t0) * 1000)
                    item.update(http_status=r.status_code, ms=ms)
                    if r.status_code == 200:
                        try:
                            forma, qtd, campos = _forma(r.json())
                            item.update(estado="ok", forma=forma, quantidade=qtd, campos=campos)
                        except ValueError:
                            item.update(estado="ok", forma=r.headers.get("content-type", "?"))
                    else:
                        msg = r.text[:200].replace(chave, "***")
                        item.update(estado="erro", mensagem=re.sub(r"\s+", " ", msg))
                except httpx.HTTPError as exc:
                    item.update(estado="falha_rede", mensagem=type(exc).__name__)
                resultados.append(item)
                print(f"{item.get('http_status', '-')!s:>4} {item['estado']:<10} {caminho}")
                time.sleep(args.pausa)
    saida = PASTA / f"sondagem_{hoje.isoformat()}_{args.empresa}.json"
    saida.write_text(json.dumps({"data": hoje.isoformat(), "empresa": args.empresa,
                                 "spec": _spec_mais_recente().name, "resultados": resultados},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{saida.name}: " + ", ".join(f"{k}={v}" for k, v in Counter(x['estado'] for x in resultados).items()))


# ---------------------------------------------------------------- catálogo

def _descricao(op: dict) -> str:
    return re.sub(r"\s+", " ", (op.get("summary") or op.get("description") or "")).strip()[:110]


def gerar(_args) -> None:
    spec_arq = _spec_mais_recente()
    spec = json.loads(spec_arq.read_text(encoding="utf-8"))
    sondagens = sorted(PASTA.glob("sondagem_*.json"))
    sond = json.loads(sondagens[-1].read_text(encoding="utf-8")) if sondagens else {"resultados": []}
    por_rota = {(x["metodo"], x["rota"]): x for x in sond["resultados"]}
    linhas_l, linhas_e = [], []
    for caminho, metodos in sorted(spec["paths"].items()):
        for metodo, op in metodos.items():
            if metodo not in ("get",) + ESCRITA:
                continue
            filtros = ", ".join(p["name"] for p in op.get("parameters", []) if p["in"] == "query"
                                and p["name"] not in ("CHAVE",))[:120]
            s = por_rota.get((metodo.upper(), caminho), {})
            if metodo == "get":
                if s.get("estado") == "ok":
                    teste = f"✅ {s.get('quantidade', '')} reg · {s.get('ms')} ms"
                elif s.get("estado") == "erro":
                    teste = f"❌ HTTP {s.get('http_status')}: {s.get('mensagem', '')[:60]}"
                elif s.get("estado") == "precisa_parametro":
                    teste = "⏸ precisa de " + ", ".join(s.get("faltam", []))
                elif s.get("estado") == "get_com_acao_nao_testado":
                    teste = "⚠ GET com nome de ação, não testado"
                else:
                    teste = "—"
                linhas_l.append(f"| `{caminho}` | {_descricao(op)} | {filtros} | {teste} |")
            else:
                linhas_e.append(f"| {metodo.upper()} | `{caminho}` | {_descricao(op)} |")
    n_ok = sum(1 for x in sond["resultados"] if x.get("estado") == "ok")
    texto = f"""# Catálogo da API de Integração webPosto (Quality Automação)

Gerado por `WebPosto_API/scripts/webposto_catalogo.py` em {date.today():%d/%m/%Y}.
OpenAPI: `{spec_arq.name}` ({len(spec['paths'])} rotas). Sondagem: `{sondagens[-1].name if sondagens else 'nenhuma'}`
({n_ok} leituras responderam com dados ou vazio sem erro).

Este arquivo é para pessoas e para qualquer IA: leia as **Regras** antes de propor qualquer chamada.

## Regras (o que podemos e o que não podemos)

1. **Base:** `{BASE}`. Autenticação: parâmetro de query `CHAVE` em toda chamada. Não há header nem OAuth.
2. **A chave "Api Integração" vê a rede inteira.** Ela não fica restrita à empresa que a gerou: consulta qualquer
   `empresaCodigo` da rede (confirmado em 08/11/2026). Tratar como segredo da rede, nunca colocar em URL de log,
   planilha, chat ou repositório. Chaves restritas só existem para integrações específicas (Equals, GAIA).
3. **Leitura (GET) é livre** para integrações e BI. Use sempre `empresaCodigo`, período curto e paginação.
4. **Escrita (POST/PUT/PATCH/DELETE) mexe no ERP de produção.** No LOGOS e no Logos Match, a escrita está
   **congelada**: só com aprovação explícita do diretor, por operação. Não existe ambiente de homologação
   documentado; testar escrita significa gravar em produção.
5. **Paginação:** `ultimoCodigo` + `limite` (rotas V1; máximo usual 2.000). Envelope `{{"ultimoCodigo", "resultados": []}}`.
   Repetir a chamada passando o `ultimoCodigo` devolvido até vir lista vazia ou cursor nulo.
6. **Datas:** `AAAA-MM-DD` nos filtros. Fuso do negócio: America/Recife.
7. **Rotas legadas** (sem `/V1/`) usam outros nomes de parâmetro (`pagina`, `filial`). Prefira as `/V1/`.
8. **Documentação muda sem aviso:** entre 06/10 e 09/11/2026 entraram 21 rotas, saíram 9 e 14 mudaram.
   Rode `baixar` + `sondar` + `gerar` antes de começar uma integração nova.
9. A OpenAPI não documenta limite de requisições. Use pausa entre chamadas (a sondagem usa 0,4 s) e evite
   rodar sincronizações grandes em horário de pico do posto.

## Leituras (GET)

| Rota | Para que serve | Filtros | Teste real |
|---|---|---|---|
{chr(10).join(linhas_l)}

## Escritas (não chamar sem aprovação)

| Método | Rota | Para que serve |
|---|---|---|
{chr(10).join(linhas_e)}
"""
    (PASTA / "CATALOGO_API.md").write_text(texto, encoding="utf-8")
    print(f"CATALOGO_API.md: {len(linhas_l)} leituras, {len(linhas_e)} escritas")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baixar").set_defaults(f=baixar)
    s = sub.add_parser("sondar")
    s.add_argument("--empresa", type=int, required=True)
    s.add_argument("--env-var", required=True)
    s.add_argument("--env-file")
    s.add_argument("--pausa", type=float, default=0.4)
    s.set_defaults(f=sondar)
    sub.add_parser("gerar").set_defaults(f=gerar)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
