# QUICKSTART — Financeiro IA (Fase 5)

## O que faz

Automatiza quatro frentes que hoje são manuais ou espalhadas:

1. **Fluxo de caixa projetado** — entradas/saídas por dia e alerta se o saldo projetado fica negativo em N dias (padrão 7).
2. **Conferência de cartões** — venda cartão no webPosto × recebido em PagBank, Cielo, Premmia e Mais Pagamentos (diferença por dia e bandeira, em R$).
3. **Inadimplência** — títulos vencidos e clientes frota/prazo em atraso.
4. **Despesas problemáticas** — despesas de caixa sem categoria (plano/conta) ou sem comprovante.

**Fora do escopo:** conciliação depósito × extrato bancário.  
**Aportes** de outra origem geram aviso e **não** entram na conciliação.  
**Caixa** = posto + setor/centro ou nome do caixa — **nunca** frentista.  
**Unidade:** Doze Filial (`empresaCodigo` **74014**), não "Real".

Somente leitura. `WEBPOSTO_WRITES=0`. Sem fonte real → `{"status":"fonte_indisponivel","motivo":"..."}`.

---

## Testes

```bash
cd WebPosto_API
set WEBPOSTO_WRITES=0
set DRY_RUN=true
pytest tests/services/test_financeiro_analyzer.py -q --no-cov
```

Exemplo de aceite nos testes: venda R$ 1.000 no cartão e R$ 980 recebidos → diferença **R$ 20** com causa informada.

Suíte de IAs (regressão):

```bash
pytest tests/services/test_buyer_analyzer.py tests/services/test_tax_advisor_analyzer.py tests/services/test_pricing_analyzer.py tests/services/test_compras_validator.py tests/services/test_financeiro_analyzer.py -q --no-cov
```

---

## API (`/api/v1/financeiro-ai`)

Subir app:

```bash
python -c "from src.interfaces.http.app import create_app; create_app()"
# ou
uvicorn src.interfaces.http.app:app --reload
```

| Método | Rota | Uso |
|---|---|---|
| GET | `/fluxo-caixa` | `CorporateCashFlowService`; falha → `fonte_indisponivel` |
| POST | `/fluxo-caixa/analisar` | Body com `movimentos`, `saldo_inicial`, `horizonte_dias` |
| GET | `/conferencia-cartoes` | Leitura `pagbank_edi` / `extrato_reader` / CARTOES; sem credencial → `fonte_indisponivel` com motivo |
| POST | `/conferencia-cartoes/analisar` | Body com `vendas_cartao` + `recebimentos_adquirentes` |
| GET | `/inadimplencia` | `CorporateFinanceCenterService` (recebíveis); falha → `fonte_indisponivel` |
| POST | `/inadimplencia/analisar` | Body com `titulos` |
| GET | `/despesas-problematicas` | `webposto_detalhes.buscar_despesas`; falha → `fonte_indisponivel` |
| POST | `/despesas-problematicas/analisar` | Body com `despesas` |
| GET | `/relatorio` | Consolida as quatro frentes |
| GET | `/health` | Health check |

### Exemplo — diferença de R$ 20

```bash
curl -X POST http://localhost:8000/api/v1/financeiro-ai/conferencia-cartoes/analisar ^
  -H "Content-Type: application/json" ^
  -d "{\"vendas_cartao\":[{\"dia\":\"2026-11-25\",\"bandeira\":\"VISA\",\"valor\":1000}],\"recebimentos_adquirentes\":[{\"dia\":\"2026-11-25\",\"bandeira\":\"VISA\",\"valor\":980,\"adquirente\":\"PagBank\"}]}"
```

Resposta esperada (trecho): `diferenca_total: 20.0`, `causa: webposto_maior_que_adquirente`.

---

## Reuso interno

- Normalização monetária: `src.services.financial_reconciliation_engine.to_decimal`
- Fluxo e títulos: `CorporateCashFlowService` + `CorporateFinanceCenterService` (injetados nos GET)
- Cartões/despesas (leitura): `src.modules.cash_reconciliation.adapters` (`pagbank_edi`, `extrato_reader`, `webposto_cartoes`, `webposto_detalhes`) — sem adaptadores de escrita
- POST com payload continua disponível para diagnóstico offline

---

## Datas

Fuso `America/Recife`. Campos `data_audit` e dias de alerta em **dd/mm/aaaa** (hora em `data_audit` como HH:mm).
