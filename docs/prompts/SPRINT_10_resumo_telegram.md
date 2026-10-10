# Prompt — SPRINT 10: resumo diário do robô pelo Telegram (Cursor / Antigravity / VS Code)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem merge na main e sem troca de branch. Somente leitura no ERP (`WEBPOSTO_WRITES=0`). `.env` só via `load_dotenv`, **nunca imprimir nem editar o `.env`**. Altere SOMENTE as funções citadas; não reescreva arquivos inteiros; **não adicione dependências** (use o `httpx` já existente). Datas no padrão Brasil (America/Recife). Testes nunca gravam no banco real nem enviam mensagem de verdade.

Decisão do diretor (10/10/2026): o resumo diário vai pelo **Telegram** (gratuito; WhatsApp tem custo). Destinatário inicial: só o diretor.

## Regras de privacidade da mensagem (obrigatórias)

- Sem nome de funcionário, CPF, número de conta, NSU ou chave. Frentista só pelo código.
- Totais por unidade + lista de despesas e vales (itens 3 e 4). Demais detalhes ficam no Painel do Diretor (login).
- O token do bot vai na URL da API do Telegram: **nunca registrar URL, cabeçalhos ou `str(exc)` no log** — só o tipo do erro e o status HTTP.

## PARTE A — Mensagem curta

@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py
@WebPosto_API/src/modules/cash_reconciliation/config/units.json
@WebPosto_API/src/modules/cash_reconciliation/domain/fechamento.py
@WebPosto_API/src/modules/cash_reconciliation/rules/fechamento.py
@WebPosto_API/src/modules/cash_reconciliation/application/auditar_fechamento.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_detalhes.py
@WebPosto_API/tests/unit/cash_reconciliation/test_resumo_diario.py

1. `units.json`: campo opcional `apelido` por unidade — 74014 "Doze", 11495 "VIP", 5555 "Casa Caiada", 118508 "Conv. 24h". Sem apelido → usa `nome`.
2. Nova função `gerar_mensagem_curta(...)` em `resumo_diario.py` (mesmos dados de `gerar_resumo_diario`, que **não muda**), texto simples, no máximo ~15 linhas:
   ```
   LOGOS — Caixas de 09/10/2026 (robô ok | robô com falha)
   ⚠ Doze: falta R$ 2.263,18 sem desconto (caixa ainda não consolidado)
   ⚠ VIP: 2 faltas, R$ 1.303,04 sem desconto
   ✓ Conv. 24h: sem falta
   Pendências: 105 abertas · 0 vencidas
   Aviso: PagBank da Conv. 24h com credencial inválida
   ```
   - ⚠ quando houver falta sem desconto ou quebra acima de R$ 100 na unidade; ✓ caso contrário.
   - "(caixa ainda não consolidado)" quando o caixa com falta tiver alerta `NAO_CONSOLIDADO`.
   - Linha de pendências com abertas e **vencidas** (regra da Sprint 09).
   - Linha "Aviso:" só se houver adquirente com `credencial inválida` ou unidade com falha.
3. **Despesas do caixa** (pedido do diretor), por unidade, depois das linhas de falta:
   ```
   Despesas Doze (3 · R$ 412,00):
   - R$ 250,00 · Gelo · 3.01.004 Material de consumo
   - R$ 120,00 · Conta de luz · 3.02.001 Energia
   - R$ 42,00 · Lanche equipe · SEM PLANO ⚠
   ```
   - Dados: `AuditoriaCaixa.despesas` já gravado (`valor`, `descricao`, `plano_conta_codigo`).
   - Nome do plano de contas: se a spec oficial V1 (`docs/architecture` / memória `webposto-spec-oficial`) tiver rota de plano de contas, buscar em `adapters/` com cache em memória por execução e gravar o nome no resultado (campo opcional novo); se não tiver, mostrar só o código. Não inventar rota.
   - Descrição cortada em 40 caracteres; despesa sem plano → "SEM PLANO ⚠".
   - Ordenar por valor; mostrar até 8 por unidade e depois "+N outras (R$ X)".
4. **Vales de funcionários** (pedido do diretor), por unidade:
   ```
   Vales Doze (2 · R$ 380,00): func. 302036 R$ 300,00 (falta de caixa) · func. 118 R$ 80,00 (adiantamento)
   ```
   - Hoje o resultado só guarda `vales_falta` (origem D). Em `rules/fechamento.py`/`application/auditar_fechamento.py`, gravar também **todos** os vales do caixa num campo opcional novo `vales` (padrão vazio; resultados antigos continuam abrindo), sem mudar a regra de falta.
   - Rótulo da origem a partir da spec V1 (`VALES_FUNCIONARIO`); origem desconhecida → mostrar o código da origem.
   - **Só o código do funcionário**, nunca o nome.
5. A mensagem completa não pode passar de 4.000 caracteres (limite do Telegram 4.096): se passar, dividir em mais de uma mensagem, por unidade.
6. Testes: unidade sem problema → ✓; falta em caixa não consolidado → texto do aviso; despesa sem plano → "SEM PLANO ⚠"; mais de 8 despesas → "+N outras"; vale mostra código e nunca nome (teste com nome sintético no dado de entrada que **não** pode aparecer na saída); mensagem longa é dividida.

## PARTE B — Envio pelo Telegram

@WebPosto_API/src/jobs/noturno.py
@WebPosto_API/.env.example

1. Novo adaptador genérico `WebPosto_API/src/shared/notificacao/telegram.py` (sem regra de negócio): `enviar_mensagem(texto, *, token, chat_ids, cliente=None)` via `POST https://api.telegram.org/bot<token>/sendMessage`, timeout 15 s, até 2 tentativas. Retorna sucesso/falha por destinatário, sem expor o token.
2. Variáveis (só os **nomes** no `.env.example`): `TELEGRAM_ENVIO` (1 = liga; padrão desligado), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` (um ou mais ids separados por vírgula).
3. `src/jobs/noturno.py`, no `main`, após `executar` terminar: se `TELEGRAM_ENVIO=1` **e** o dia processado for ontem (execução automática), gera a mensagem curta e envia. Reprocessamento manual com `--dia` **não envia**, salvo com a nova opção `--enviar-telegram`.
4. Não enviar duas vezes o mesmo dia: registrar envio em `data/resumos/envios_telegram.json` (fora do Git). Opção `--reenviar` força.
5. **Falha no envio é aviso, não falha do robô**: código de saída não muda; log `Telegram envio=falhou motivo=<tipo/status>` ou `Telegram envio=ok destinatarios=N`.
6. Utilitário `python -m src.jobs.telegram --descobrir-chat`: lê `getUpdates` e imprime só o **id** e o primeiro nome de quem mandou mensagem ao bot (para o diretor copiar o id para o `.env`). E `python -m src.jobs.telegram --teste`: envia "LOGOS — teste de envio". Ambos falham com mensagem clara se faltar variável.
7. Testes com `httpx.MockTransport` (sem rede): envio ok; erro 401 → aviso sem token no log (verificar com `caplog` que o token sintético não aparece); não reenvia o mesmo dia; `TELEGRAM_ENVIO` desligado → não chama a API.

## Ao terminar

```
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; python -m pytest tests/unit -q -o addopts="" -k "resumo or telegram or noturno or pendencias"; python -m pytest tests/unit/cash_reconciliation tests/unit/commercial_performance tests/unit/test_auth_access.py -q -o addopts=""; node --test tests/frontend/*.test.mjs
```
Reprocesse 09/10/2026 (`python -m src.modules.cash_reconciliation.jobs.noturno --dia 09/10/2026`, que não envia) para gravar despesas com plano e todos os vales, e mostre a mensagem gerada (sem enviar). Informe se a rota de plano de contas existe na spec. **Não envie nada pelo Telegram** — o diretor fará o primeiro teste.
Commits: `feat(resumo): mensagem curta do robô noturno` e `feat(notificacao): envio do resumo diário pelo Telegram`. Depois `git push`.
