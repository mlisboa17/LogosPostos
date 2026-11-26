# QUICKSTART — Diretor IA

## O que faz

Orquestra os relatórios das cinco IAs de negócio em um único brief executivo:

1. **Comprador IA** — `generate_executive_brief`
2. **Tax Advisor IA** — `generate_tax_audit_report`
3. **Precificador IA** — `gerar_relatorio_precificacao`
4. **Validação de Compras** — `generate_data_quality_report`
5. **Financeiro IA** — `gerar_relatorio_financeiro`

Não reanalisa dados: só normaliza achados, ordena por impacto em R$ e monta o quadro de status.  
`fonte_indisponivel` aparece como **pendência**, nunca como zero.  
Total em R$ soma **somente** impactos informados pela própria IA.  
Somente leitura. `WEBPOSTO_WRITES=0`.

---

## Testes

```bash
cd WebPosto_API
set WEBPOSTO_WRITES=0
set DRY_RUN=true
pytest tests/services/test_diretor_orquestrador.py -q --no-cov
```

Regressão das IAs:

```bash
pytest tests/services/test_buyer_analyzer.py tests/services/test_tax_advisor_analyzer.py tests/services/test_pricing_analyzer.py tests/services/test_compras_validator.py tests/services/test_financeiro_analyzer.py tests/services/test_diretor_orquestrador.py -q --no-cov
```

---

## API (`/api/v1/diretor-ai`)

```bash
python -c "from src.interfaces.http.app import create_app; create_app()"
```

| Método | Rota | Uso |
|--------|------|-----|
| GET | `/api/v1/diretor-ai/brief` | Brief consolidado |
| GET | `/api/v1/diretor-ai/health` | Health + quais analisadores foram injetados |

Resposta do brief (resumo):

- `status_ias` — sempre as cinco IAs (`ok` / `vazio` / `fonte_indisponivel` / `erro`)
- `achados` — ordenados por `|impacto_rs|` decrescente
- `impacto_total_rs` — soma só dos que têm valor
- `achados_sem_valor` — achados sem R$ calculado
- `pendencias` — motivos de fonte/erro
- `mensagem` — texto em português simples

---

## O que não faz

- Não escreve no ERP.
- Não chama `TROCA_PRECOS` nem adaptadores de escrita de cartão/despesa.
- Não funde achados de origens diferentes (mesmo com o mesmo valor).
- Não substitui `executive_snapshot_service` / `finance_intelligence_snapshot_service` (esses agregam KPIs do ERP; o Diretor orquestra briefs das IAs).
