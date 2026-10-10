# Prompt — CASH-AUDIT-03: Recebimentos eletrônicos (PIX/Premmia), tela e robô noturno

> Cole no agente do VS Code com o workspace aberto em `C:\Projetos\LOGOS\LogosPostos`.
> Trabalhe **uma fase por vez**; ao fim de cada fase: testes verdes + 1 commit + resumo curto. Depois siga para a próxima.

---

## Contexto (leia antes de codar)

- Repositório canônico: `C:\Projetos\LOGOS\LogosPostos`, branch **`feature/cash-audit-fechamento`**. Não troque de branch, não faça merge, **não faça push**.
- Arquitetura: `docs/architecture/LOGOS_ARCHITECTURE_DIRECTIVE.md`, `LOGOS_CONTEXT_MAP.md` § 2.4, `adr/ADR-002-*.md`. Monólito modular; tudo novo vive em `WebPosto_API/src/modules/cash_reconciliation/` (`domain/`, `rules/`, `adapters/`, `application/`, `interfaces/`, `config/`). Testes em `WebPosto_API/tests/unit/cash_reconciliation/`.
- Já pronto (não reescreva, **reutilize**):
  - Auditoria de fechamento: `rules/fechamento.py` (`FECHAMENTO_V2`), `application/auditar_fechamento.py`, rota `/api/v1/cash-audit/fechamento`, tela `frontend/pages/cashAudit.js`.
  - Conciliação de recebimentos: `rules/cartoes.py` (`CARTOES_V1`: casamento por NSU/autorização; valor+hora só p/ PIX sem NSU; investigação por abastecimento com pontuação 35/30/20/15, ≥80 e único atribui frentista, 50–79 ou empate = sugestão; pares prováveis), `application/conciliar_cartoes.py` (`conciliar`, `conciliar_pagbank`), `adapters/pagbank_edi.py`, `adapters/webposto_cartoes.py`, `adapters/webposto_http.py` (`paginar`).
- Código de referência resgatado (Codex e outros): branch local **`resgate/conciliacao-4-vias`**. **Não faça checkout/merge dele.** Leia arquivos com `git show resgate/conciliacao-4-vias:<caminho>`. Relevantes:
  `WebPosto_API/src/gateway/mais_pagamentos_client.py`, `src/services/bank_reconciliation/mais_pagamentos_reconciliation_service.py`, `src/services/financial/mais_pagamento_mapping.py`, `src/services/integrations/premmia_collector.py`, `src/services/integrations/premmia_rpa.py`, `src/services/financial/premmia_*.py`, `src/services/finance/bidirectional_divergence_engine.py`, testes correspondentes em `tests/unit/`.
- **Lição aprendida:** o cliente PagBank do Codex tinha 2 bugs silenciosos (perdia a hora; lia só a 1ª página). **Antes de portar qualquer cliente externo, faça uma sondagem read-only da resposta real imprimindo apenas nomes de campos, tipos e contagens — nunca valores, nomes de clientes, CPF ou chaves.** Ajuste o port ao formato real e cubra com teste.

### Adquirentes por unidade (fonte: negócio, 2026-10-07)

| Unidade (empresaCodigo) | Cartões | PIX | Observação |
|---|---|---|---|
| Doze Filial (74014) | PagBank | PagBank | ✅ funcionando |
| Casa Caiada (5555) | PagBank | PagBank | ✅ funcionando |
| VIP (11495) – pista | Rede (EDI ainda não liberado) | Mais Pagamentos | no webPosto o PIX Mais Pagamentos aparece como **TRANSFERÊNCIAS BANCÁRIAS** (`transfBanc`) |
| VIP (11495) – loja | Cielo (sem credencial) | Mais Pagamentos | |
| Conveniência 24h (118508) | Cielo (sem credencial) | PagBank | PagBank EDI respondeu 401 — tratar como "credencial inválida", sem quebrar o job |
| Premmia (todas) | — | — | via portal Vibra (robô) |

Registre esse mapa em `config/units.json` (campo novo `adquirentes` por unidade, só nomes — sem credenciais) e faça o caso de uso escolher as adquirentes pela configuração.

---

## Fase 1 — PIX Mais Pagamentos (VIP)

1. Sondagem read-only da API Mais Pagamentos (credenciais nas variáveis `MAIS_PAGAMENTOS_*` do `.env`; descubra os nomes pelo código resgatado). Documente o formato real em docstring.
2. Lado webPosto: descubra como o PIX do VIP chega (forma de pagamento "TRANSFERÊNCIA BANCÁRIA"/`transfBanc` em `VENDAS_FORMA_PAGAMENTO` e/ou `CAIXAS_APRESENTADO`). Sondagem read-only da mesma forma.
3. `adapters/mais_pagamentos.py` → `TransacaoAdquirente(adquirente="MAIS_PAGAMENTOS", ...)`; reaproveite `rules/cartoes.py` (`casar`, `investigar`, `parear_sobras`). Se o PIX não tiver NSU, o casamento é por valor+hora (já suportado). Generalize `conciliar_*` sem duplicar lógica.
4. Testes sintéticos (MockTransport) + rodar com dados reais do VIP em 1 dia e reportar contagens (casados / a maior / a menor / pares / atribuídos).

## Fase 2 — API e tela de recebimentos

1. `GET /api/v1/cash-audit/recebimentos?unidade=&dia=` → resultado por adquirente configurada (casados = só contagem e total; a maior, a menor e pares com detalhe; candidatos e motivos). Erro de credencial de uma adquirente **não derruba** as demais: retorna `{"adquirente": X, "erro": "credencial inválida"}` (sem detalhe técnico).
2. Na tela `cashAudit.js`, seção **"Recebimentos eletrônicos"** abaixo dos caixas, mesmo estilo dark já existente (`.ca-*`, chips, badges): por adquirente, KPIs (casados, a maior, a menor, pares) e tabela das divergências com: hora, valor, bandeira, classificação, **frentista atribuído** ou "sugestão (N candidatos)", motivos da pontuação. Vermelho = a menor; laranja = a maior; amarelo = par provável.
3. Ranking do período por frentista (atribuídos + sugestões), para reincidência.
4. Testes de rota com monkeypatch (sem rede). Verificar a tela no navegador e anexar screenshot no resumo.

## Fase 3 — Robô noturno (roda sozinho, captura e termina)

1. `src/modules/cash_reconciliation/jobs/noturno.py`, executável por `python -m src.modules.cash_reconciliation.jobs.noturno [--dia AAAA-MM-DD]` (padrão: ontem), a partir de `WebPosto_API`.
2. Para cada unidade do `units.json`: auditoria de fechamento + conciliação de cada adquirente configurada. Cada etapa isolada (`try/except` por unidade/adquirente) com timeout; uma falha não interrompe as outras.
3. Persistir o resultado (JSON com proveniência: execução, versão das regras, fontes) em `WebPosto_API/data/cash_audit/<dia>/<unidade>.json`. **Adicione `WebPosto_API/data/` ao `.gitignore`** — contém dados reais. Idempotente: reexecutar o mesmo dia sobrescreve.
4. Log resumido em arquivo (sem segredos, sem CPF, sem valores de cliente).
5. As rotas da Fase 2 passam a ler o resultado persistido quando existir (e consultar ao vivo só se não existir).
6. `scripts/registrar_robo_noturno.ps1`: registra no Agendador de Tarefas do Windows a execução diária às **03:00**. **Não execute o registro** — só crie o script e explique como rodar.

## Fase 4 — Premmia (somente se as fases 1–3 estiverem verdes)

Porte o coletor/robô Premmia como etapa do job noturno, **em processo separado** (subprocess com timeout) para não afetar a API. Credenciais só por variável de ambiente. **Se o portal exigir CAPTCHA ou verificação humana, pare e reporte — não tente contornar.** Reaproveite os parsers/testes resgatados.

---

## Restrições (não negociáveis)

- **Somente leitura no ERP** (`WEBPOSTO_WRITES=0`). O sistema sugere; correção é humana.
- **Segredos:** nunca escreva chave/token no código, testes, logs, commits ou respostas. O código resgatado tinha chaves hardcoded — não copie esse padrão. Teste não pode depender de valor real do `.env`.
- **Credenciais:** ficam em `WebPosto_API/.env` (fora do Git). Scripts e testes de integração carregam esse arquivo **programaticamente** — `from dotenv import load_dotenv; load_dotenv("WebPosto_API/.env")` ou `load_dotenv(".env")` a partir de `WebPosto_API` — exatamente como a aplicação já faz em `create_app`. **Nunca imprima, logue ou copie os valores**; não use `cat`/`type`/`Get-Content` no `.env`; para checar presença, use só o nome (`bool(os.getenv("X"))`). Não peça credenciais no chat. `WEBPOSTO_WRITES=0` já está no `.env`.
- Testes só com dados sintéticos. Não versionar extratos, JSON de resultados reais, CPF, nomes de clientes.
- Não alterar `rules/fechamento.py`, a rota legada `/auditoria` nem a conciliação de depósitos (`application/conciliar.py`, fora de escopo).
- Toda regra nova ou alterada ganha **versão** (`CARTOES_V2`, etc.) e testes.
- Português nos textos/mensagens; estilo do módulo (Pydantic v2 `frozen`, `Decimal`, funções puras nas regras).

## Como rodar

```
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API
python -m pytest tests/unit/cash_reconciliation -q -o addopts=""
python -m uvicorn src.main:app --port 8000      # tela: http://localhost:8000/app/financial?view=cash-audit
```
Hoje: 50 testes verdes. Caminhos longos no Windows: se criar worktree, use pasta curta (ex.: `C:\Projetos\LOGOS\_wt`).

## Entrega por fase

Saída do pytest · commit no padrão `feat(cash-audit): ...` · resumo curto com arquivos alterados, contagens reais obtidas e qualquer decisão/pendência (ex.: credencial inválida).
