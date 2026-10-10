# Prompt — CASH-AUDIT-02: Endpoint + Tela "Fechamento do Dia"

> Cole este prompt no agente do VS Code (Copilot/Codex/Claude) com o workspace aberto em `C:\Projetos\LOGOS\LogosPostos`.

---

## Contexto

Você está no repositório canônico do LOGOS (`mlisboa17/LogosPostos`), branch **`feature/cash-audit-fechamento`**. Não troque de branch e não faça push.

Antes de codar, leia:
1. `docs/architecture/LOGOS_ARCHITECTURE_DIRECTIVE.md` (monólito modular, proveniência § 6.2, tenant § 6.1)
2. `docs/architecture/LOGOS_CONTEXT_MAP.md` § 2.4 (Cash & Reconciliation)
3. `docs/architecture/adr/ADR-002-cash-arch-01-antes-do-arch-02.md`
4. O módulo pronto: `WebPosto_API/src/modules/cash_reconciliation/` — em especial
   `application/auditar_fechamento.py` (`auditar_unidade`), `domain/fechamento.py`, `rules/fechamento.py` (regra `FECHAMENTO_V1`).

O caso de uso já existe e foi validado em produção. **Sua tarefa é só expor via API e criar a tela.** Não altere as regras de `FECHAMENTO_V1` (há uma decisão de negócio pendente sobre "quebra provisória" de caixa não consolidado).

## Tarefa 1 — Endpoint de API

Crie `WebPosto_API/src/modules/cash_reconciliation/interfaces/http.py` com um `APIRouter`:

- `GET /api/v1/cash-audit/fechamento?unidade=<empresaCodigo>&inicio=YYYY-MM-DD&fim=YYYY-MM-DD`
  - `unidade` obrigatório e deve existir em `config/units.json` (via `carregar_unidades()`); senão **404**.
  - `inicio`/`fim` obrigatórios; `fim >= inicio`; período máximo de 31 dias; senão **422**.
  - Chama `auditar_unidade(...)` e devolve o `ResultadoAuditoria` serializado (Pydantic `model_dump(mode="json")`), incluindo por caixa: `caixa`, `modalidades`, `alertas`, `quebra`, `severidade`; e no topo `quebra_total` e `proveniencia`.
  - `WebPostoErro` → **502** com mensagem genérica. **Nunca** inclua a CHAVE, URL com query ou corpo bruto do webPosto na resposta ou no log.
- `GET /api/v1/cash-audit/unidades` → lista `[{empresa_codigo, nome}]` de `units.json` (sem `chave_env`).

Registre o router em `WebPosto_API/src/presentation/app.py` seguindo o padrão existente (bloco `try/except` com `logging.warning`, como o de `audit_routes`). **Não** reutilize o prefixo `/auditoria` — ele pertence ao legado `src/interfaces/http/routes/auditoria.py`, que não deve ser alterado.

Observação: `quebra` e `severidade` são `@property`; garanta que entrem na resposta (ex.: montar um DTO de resposta no próprio `interfaces/http.py` ou usar `@computed_field`). Escolha o caminho de menor impacto e mantenha o domínio sem dependência de FastAPI.

### Testes (obrigatórios)
`WebPosto_API/tests/unit/cash_reconciliation/test_http.py` com `fastapi.testclient.TestClient` sobre um app mínimo que inclua só esse router, fazendo **monkeypatch de `auditar_unidade`** (nada de rede):
- 200 com payload esperado (inclui `quebra`, `severidade`, `quebra_total`, `proveniencia.versao_regra == "FECHAMENTO_V1"`)
- 404 unidade inexistente · 422 datas inválidas / período > 31 dias
- 502 quando `auditar_unidade` levanta `WebPostoErro("HTTP 400: ... segredo ...")` — e a resposta **não** contém "segredo"
- `/unidades` não expõe `chave_env`

Rode: `cd WebPosto_API && python -m pytest tests/unit/cash_reconciliation -q -o addopts=""` — tudo verde (hoje são 27 testes).

## Tarefa 2 — Tela "Fechamento do Dia"

Frontend vanilla JS em `WebPosto_API/frontend/` (ver `app.js` e `pages/cashFlow.js` como padrão de página; reutilize `services/format.js` → `formatCurrency` e o cliente HTTP existente em `services/`).

Crie `frontend/pages/cashAudit.js` com `renderCashAudit(...)` e registre no `app.js` como as demais páginas (menu: **"Auditoria de Caixa"**).

Layout (dark mode, pragmático, foco em leitura rápida):
1. **Filtros:** seletor de unidade (de `/api/v1/cash-audit/unidades`) + data início/fim (padrão: últimos 7 dias).
2. **Cards KPI:** Quebra total do período · Caixas com alerta vermelho · Caixas não consolidados · Sangrias sem destino · Sangrias alteradas.
3. **Tabela de caixas** (uma linha por caixa): Data · Turno · Centro de custo · Situação (aberto / fechado / consolidado) · Quebra (R$) · Alertas.
   - Linha com `severidade = "vermelho"` → fundo/borda **vermelho**; `"laranja"` → **laranja**.
   - Clicar na linha expande: tabela por modalidade (Apresentado · Apurado · Diferença) e lista de alertas (mensagem pronta vem da API).
4. Rodapé discreto com a proveniência: versão da regra e horário da execução.

Sem bibliotecas novas. Cores via variáveis CSS já existentes em `styles.css`, se houver; senão crie poucas variáveis no topo do arquivo de estilo da página.

## Restrições (não negociáveis)

- Não alterar `rules/fechamento.py`, `rules/matching.py` nem o legado `/auditoria`.
- Não ler, imprimir, criar ou commitar `.env`; não criar fixtures com dados reais.
- Não tocar na conciliação de depósitos (`application/conciliar.py`) — está fora de escopo.
- Código e mensagens em português, seguindo o estilo do módulo (Pydantic v2, `Decimal`, modelos `frozen`).

## Entrega

1. Testes verdes (cole a saída do pytest).
2. Um commit no branch atual, mensagem no padrão:
   `feat(cash-audit): endpoint e tela Fechamento do Dia`
   com rodapé `Co-Authored-By` do agente, se aplicável.
3. Resumo curto: arquivos criados/alterados, como abrir a tela, e qualquer decisão tomada (ex.: DTO vs `computed_field`).
