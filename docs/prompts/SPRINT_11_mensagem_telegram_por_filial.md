# Prompt — SPRINT 11: mensagem do Telegram separada por filial, com nomes e planilha (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem merge na main e sem troca de branch. Somente leitura no ERP (`WEBPOSTO_WRITES=0`). `.env` só via `load_dotenv`, nunca imprimir nem editar. Altere SOMENTE as funções citadas; não reescreva arquivos inteiros. Datas no padrão Brasil (America/Recife). Testes nunca gravam no banco real e **nunca enviam mensagem de verdade** (use `httpx.MockTransport`).

Decisões do diretor (10/10/2026):
- O Telegram já funciona (`--teste` chegou). Destinatário: só o diretor.
- **Mostrar o NOME do funcionário, não o código**, na mensagem e na planilha do Telegram. (Continua proibido versionar nomes: nada de nome real em código, testes ou commits — testes usam nomes sintéticos; arquivos gerados ficam em `data/`, fora do Git.)
- Mensagem **separada por filial** com um traço, e **planilha** anexada com o detalhe.

Arquivos:
@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py
@WebPosto_API/src/modules/webposto_integration/funcionarios.py
@WebPosto_API/src/shared/notificacao/telegram.py
@WebPosto_API/src/jobs/noturno.py
@WebPosto_API/pyproject.toml
@WebPosto_API/tests/unit/cash_reconciliation/test_resumo_diario.py

## PARTE A — Mensagem separada por filial

1. `gerar_mensagem_curta`: enviar com `parse_mode="HTML"` (escapar `<`, `>` e `&` de todo texto vindo do ERP, como descrições). Layout:
   ```
   <b>LOGOS — Caixas de 09/10/2026</b>
   Robô ok · Pendências: 105 abertas · 0 vencidas
   Aviso: PagBank da Conv. 24h com credencial inválida
   ━━━━━━━━━━━━━━━━
   <b>⚠ DOZE</b>
   Falta sem desconto: R$ 2.263,18 — Fulano (caixa ainda não consolidado)
   Despesas: 3 · R$ 1.056,00
   • R$ 900,00 — decoração posto — MANUTENÇÃO PREDIAL
   • R$ 150,00 — extra — B08 APOIO DIARISTA
   • R$ 6,00 — posto — ÁGUA PARA CONSUMO
   Vales: 3 · R$ 300,00
   • Fulano R$ 200,00 · Beltrano R$ 60,00 · Sicrano R$ 40,00
   ━━━━━━━━━━━━━━━━
   <b>⚠ VIP</b>
   ...
   ━━━━━━━━━━━━━━━━
   <b>✓ CONV. 24H</b>
   Sem falta
   ...
   ```
   - Ordem das filiais: primeiro as com ⚠, depois as com ✓.
   - Falta mostra o **nome do operador do caixa**.
   - Vales: nome + valor, ordenados por valor; se mais de 6, mostrar os 6 maiores e "+N outros (R$ X)". Tirar o "(Vale)" repetido; rótulo da origem só quando não for vale comum (ex.: "falta de caixa").
   - Despesas: até 8 por filial, depois "+N outras (R$ X)"; sem plano → "SEM PLANO ⚠".
   - Corrigir o ";" antes do parêntese. Sem linha vazia sobrando.
   - Uma mensagem por filial se o total passar de 4.000 caracteres (cabeçalho só na primeira).
2. Nomes: usar `buscar_nomes_funcionarios` (já existe em `webposto_integration`) **no momento de montar a mensagem**, com cache por execução. Se o nome não vier, mostrar "func. <código>". Não gravar nomes em `data/cash_audit/` além do que já é gravado hoje.
3. O resumo em arquivo (`data/resumos/<dia>.md`) e o Painel não mudam.

## PARTE B — Planilha anexada

1. Declarar `openpyxl` no `pyproject.toml` (já está instalado no ambiente; é a única dependência permitida nesta sprint).
2. Gerar `data/resumos/<aaaa-mm-dd>.xlsx` (fora do Git) com abas:
   - **Resumo**: uma linha por filial — caixas, quebra, faltas sem desconto (R$), despesas (qtd, R$), vales (qtd, R$), pendências abertas e vencidas.
   - **Caixas**: filial, caixa, operador (nome), abertura/fechamento (`dd/mm/aaaa HH:mm`), consolidado (sim/não), quebra, falta sem desconto.
   - **Despesas**: filial, caixa, valor, descrição, plano de contas (código e nome), alerta "SEM PLANO".
   - **Vales**: filial, caixa, funcionário (nome), valor, origem.
   - Valores como número (formato `R$ #.##0,00`), cabeçalho em negrito, filtros ativados, colunas com largura ajustada.
3. `telegram.py`: nova função `enviar_documento(caminho, legenda, *, token, chat_ids, cliente=None)` via `sendDocument` (multipart), mesmas regras de log sem token.
4. `noturno.py`: depois das mensagens, enviar a planilha com a legenda "Detalhe do dia 09/10/2026". Falha no envio da planilha = aviso, não falha do robô.

## PARTE C — Testes

Nome sintético aparece na mensagem e na planilha geradas no teste; HTML escapado (descrição com `<b>` não quebra); ordem ⚠ antes de ✓; divisão acima de 4.000 caracteres; planilha com as 4 abas e valores numéricos; `sendDocument` com `MockTransport`; token sintético nunca aparece no log (`caplog`).

## Ao terminar

```
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; python -m pytest tests/unit/cash_reconciliation tests/unit/commercial_performance tests/unit/test_auth_access.py -q -o addopts=""; python -m pytest tests/unit -q -o addopts="" -k "telegram or resumo"; node --test tests/frontend/*.test.mjs
```
Gere a mensagem e a planilha de 09/10/2026 **sem enviar** e mostre a mensagem no chat **trocando os nomes por "Funcionário A", "Funcionário B"...** (nomes reais só no Telegram e na planilha local). **Não envie nada pelo Telegram** — o diretor fará o teste.
Commits: `feat(resumo): mensagem do Telegram separada por filial com nomes` e `feat(resumo): planilha diária anexada no Telegram`. Depois `git push`.
