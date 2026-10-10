# LOGOS SPACE

Plataforma corporativa de inteligência operacional e financeira para redes de postos de combustível. Consolida dados do **WebPosto (Quality Automação)** em dashboards executivos, centro financeiro, fluxo de caixa, inteligência de fornecedores e analytics de combustíveis — com arquitetura **Snapshot First** (TTL 300s) para performance sub-segundo em cache HIT.

**Versão baseline:** 2.0 · Commit `10917af` · Maturidade financeira **9.6/10**

---

## Módulos

| Módulo | Descrição | Status |
|--------|-----------|--------|
| **Combustíveis** | KPIs de abastecimento, LMC, vendas por filial | ✅ Operacional |
| **Finance Center** | CP, CR, Banco, Caixa, Despesas — visão corporativa | ✅ F01.1 |
| **Cash Flow** | Fluxo operacional e projeção | ✅ F01.2 |
| **Supplier Intelligence** | Concentração, risco, dependência (VIBRA homologada) | ✅ F01.4-C |
| **Supplier Segmentation** | Strategic suppliers + Corporate Cost Matrix | ✅ F01.4-D |
| **Analytics** | Executive snapshot, cobertura de rede, data quality | ✅ A03.7 |
| **Data Warehouse** | DDL dimensional/fatos prontos para ETL A04 | ⚠️ 85% readiness |

---

## Arquitetura

```
WebPosto API ──► webposto_client ──► Services (F01) ──► Snapshot Store (TTL 300s)
                                              │
                                              ▼
                                    FastAPI (8040) + SPA frontend
                                              │
                         /api/v1/finance/center | cash-flow | intelligence
```

- **Entrypoint:** `src/main.py` (porta **8040**)
- **UI:** `/app/financial?view=finance-center` | `view=cash-flow`
- **Regra de ouro:** nunca agregar `totalFinanceiro` somando DESPESA + CP + BANCO + CAIXA + CR

Documentação detalhada: [ARCHITECTURE_BASELINE_2.1.md](./ARCHITECTURE_BASELINE_2.1.md)

---

## Instalação

### Pré-requisitos

- Python 3.11+
- Node.js 18+ (Playwright E2E)
- Acesso à API WebPosto (chave por rede/filial)

### Backend

```powershell
cd WebPosto_API
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edite .env com WEBPOSTO_API_KEY e WEBPOSTO_BASE_URL
python -m src.main
```

API disponível em `http://127.0.0.1:8040`.

### Frontend

Servido pelo FastAPI em `/app/financial` (SPA estática em `frontend/`).

### Testes

```powershell
# Unit tests F01
python -m pytest tests/unit/test_cash_flow_service.py tests/unit/test_finance_center_service.py tests/unit/test_expense_classifier_v2.py tests/unit/test_expense_classifier_v3.py tests/unit/test_financial_intelligence_advanced.py tests/unit/test_supplier_mdm.py tests/unit/test_supplier_segmentation.py tests/unit/test_multiselect_utils.py -o addopts=

# E2E (API deve estar rodando na 8040)
npm install
npm run test:e2e:finance
```

---

## Configuração

Copie `.env.example` → `.env`:

| Variável | Descrição |
|----------|-----------|
| `WEBPOSTO_BASE_URL` | Base URL Quality Automação (HTTPS) |
| `WEBPOSTO_API_KEY` | Chave REST ativa |
| `API_PORT` | Porta local (padrão **8040**) |
| `WEBPOSTO_TIMEOUT_SECONDS` | Timeout HTTP (padrão 30) |

**Nunca commite `.env`.** Ver [SECURITY_AUDIT_REPORT.md](./SECURITY_AUDIT_REPORT.md).

### Acesso às rotas financeiras

As rotas `/api/v1/cash-audit/*` e `/api/v1/commercial/*` exigem a sessão HttpOnly
criada por `/auth/login`. Configure `AUTH_USERS_JSON` no `.env` com um array de
usuários contendo `email`, `password_hash` (PBKDF2-SHA256), `role` (`diretor`,
`gerente` ou `auditor`) e `company_id` inteiro para gerente. Quando preenchido,
esse cadastro substitui o usuário único legado `AUTH_USER_*`. Não inclua hashes
ou senhas no Git.

Diretores e auditores podem ler todas as unidades; gerentes só leem a própria.
O modo TV do placar usa cookie `display_token` HttpOnly, válido somente para
leitura do placar de uma unidade por até `AUTH_TV_TOKEN_EXPIRE_HOURS` (padrão
12, máximo 24). `AUTH_COOKIE_SECURE` controla a flag Secure dos cookies (padrão
`true`; use `false` somente em desenvolvimento HTTP local). A interface envia
cookies same-origin automaticamente; não guarda JWT em localStorage.

---

## Deploy

1. Provisionar servidor com Python 3.11+
2. Configurar `.env` de produção (secrets via vault / variáveis CI)
3. Executar `uvicorn src.main:app --host 0.0.0.0 --port 8040 --workers 4`
4. Reverse proxy (nginx) com TLS terminado
5. Opcional: Redis para cache distribuído (futuro A04)

Repositório oficial: [LogosPostos](https://github.com/mlisboa17/LogosPostos.git)

---

## Roadmap

| Fase | Escopo | Status |
|------|--------|--------|
| A01–A03.7 | Estabilização + consolidação financeira | ✅ |
| F01.0–F01.4-D | Finance Center → Supplier Segmentation | ✅ |
| **Release 2.0** | Governança + publicação | 🔄 Em preparação |
| F02 | Tesouraria (CP/CR aging avançado) | Planejado |
| A04 | ETL DW + carga dim/fact | Planejado (85% DDL) |
| F04 | Compras (NOTA_ENTRADA — aguarda token) | Bloqueado 401 |

Ver [FINANCIAL_ROADMAP_1.0.md](./FINANCIAL_ROADMAP_1.0.md).

---

## Status Atual

| Métrica | Valor |
|---------|-------|
| DRE Readiness | **89,81%** |
| OUTROS V3 | **0,52%** |
| Health Score V3 | **94** (rede) |
| Snapshot HIT rede | **13,5 ms** |
| Unit tests F01 | **39/39 PASS** (subset direto) |
| Playwright Finance Center | **14/15 PASS** (1 falha env — API offline) |
| Segurança pré-push | **RETIDO** — credenciais no histórico Git |

Relatório consolidado: [RELEASE_2_0_FINAL_REPORT.md](./RELEASE_2_0_FINAL_REPORT.md)

---

## Screenshots

Nenhum asset de screenshot versionado no repositório. Capturas disponíveis em `playwright-report/` após execução local de E2E (`npx playwright show-report`).

---

## Licença

Uso interno — Rede Lisbôa / LOGOS SPACE.
