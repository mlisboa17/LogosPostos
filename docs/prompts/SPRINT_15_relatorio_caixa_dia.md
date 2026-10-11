# Prompt — SPRINT 15: Relatório detalhado do caixa do dia (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Somente leitura no ERP (`WEBPOSTO_WRITES=0`) e nos portais; `.env` só via `load_dotenv`, nunca imprimir; sem reescrever arquivos inteiros; reutilizar o que existe (resultados gravados em `data/cash_audit/<dia>/`, `domain/tempo.py`, helper de datas do frontend, `buscar_nomes_funcionarios`, classificação da Sprint 14). Testes sintéticos, sem acesso a portais. Nada pelo Telegram. Datas `dd/mm/aaaa HH:mm` (Recife). Toda ocorrência com **nome + código do frentista** (RN-REDE-002) e **quantidade · R$**.

**Autorização do diretor (11/10/2026):** neste relatório, **mostrar no chat os nomes reais dos funcionários**. Continua proibido: CPF, nome de cliente, NSU completo (só 4 últimos dígitos), valores do `.env`, e versionar dados reais (arquivos gerados ficam em `data/`, fora do Git).

## Objetivo

Criar no Logos a função **"Relatório do caixa do dia"** — tudo o que aconteceu nos caixas de uma unidade num dia, com detalhes e nomes — disponível por linha de comando, API e tela. Depois, **gerar o de 10/10/2026 para as 4 unidades e mostrá-lo no chat**.

## PARTE A — Montagem do relatório (aplicação)

Novo `application/relatorio_caixa_dia.py` (função pura sobre os resultados já gravados + nomes; buscar no webPosto só o que não estiver gravado). Por **unidade** e, quando houver centro de custo, por **setor** (RN-REDE-007: VIP = PISTA {7295} | CONVENIÊNCIA {21650, 22310} → FOOD {24423}; FECHAMENTO {18713} = "ajuste de NF", fora das despesas; demais unidades = setor único). Conteúdo:

1. **Cabeçalho:** unidade, dia, situação do robô (falha/aviso), quantidade de caixas.
2. **Por caixa:** código, operador (nome + código), abertura e fechamento, consolidado (sim/não), PDV.
3. **Por forma de pagamento do caixa:** apurado (sistema) × apresentado (operador) × diferença; **quebra** total; **falta sem desconto** (com valor e se o caixa está consolidado → "confirmada" ou "provisória").
4. **Sangrias:** hora, valor, destino (conta ou informativo da RN-SANGRIA-002/003), alterada (sim/não).
5. **Despesas:** hora, valor, descrição, plano de contas (código e nome), centro de custo/setor, alerta "SEM PLANO".
6. **Vales de funcionários:** funcionário (nome + código), valor, origem (falta de caixa / vale comum), caixa.
7. **Frentistas do dia:** por frentista (nome + código) — quantidade de abastecimentos, litros e valor (de `V1/ABASTECIMENTOS`, sem aferição), e as ocorrências ligadas a ele.
8. **Recebimentos (PagBank / Premmia; demais adquirentes como "pendente"):** conferidos (N · R$) e os 4 grupos da Sprint 14 (Lançar / Alterar / Apurar / Conferir à mão), item a item, com frentista provável e De → Para.
9. **Pendências do dia:** abertas, vencidas, por tipo (N · R$).
10. **Resumo no topo** (5 a 8 linhas): o que mais precisa de atenção no dia, em linguagem simples.

## PARTE B — Onde a função fica disponível

1. **Linha de comando:** `python -m src.jobs.relatorio_caixa --dia dd/mm/aaaa [--unidade 74014]` → imprime em texto e grava `data/relatorios/caixa_<aaaa-mm-dd>_<unidade>.md` e `.xlsx` (abas por bloco). Sem `--unidade` = todas.
2. **API:** `GET /cash-audit/relatorio-caixa?unidade=&dia=` (escopo do gerente respeitado).
3. **Tela:** na página de Fechamento, botão **"Relatório do dia"** que mostra o relatório (blocos recolhíveis) e permite baixar a planilha.
4. Registrar a regra **RN-CAIXA-006 — Relatório do caixa do dia** no `REGRAS_DE_NEGOCIO.md` e o histórico.

## PARTE C — Testes

Relatório sintético com 2 caixas, sangria, despesa sem plano, vale comum e de falta, troca de forma e falta provisória; setor PISTA × CONVENIÊNCIA × FOOD e FECHAMENTO fora das despesas; nomes vindos do helper; NSU mascarado; datas dd/mm/aaaa; endpoint com escopo do gerente; nenhuma chamada a portal.

## PARTE D — Executar para 10/10/2026 e mostrar no chat

1. Confirmar que existem resultados gravados de 10/10/2026 para 74014, 11495, 5555 e 118508; se faltar algum, rodar `python -m src.modules.cash_reconciliation.jobs.noturno --dia 10/10/2026` (não envia Telegram).
2. `python -m src.jobs.relatorio_caixa --dia 10/10/2026`.
3. **Mostrar no chat o relatório completo das 4 unidades, com os nomes dos funcionários**, na ordem: Doze, Casa Caiada, VIP (PISTA e CONVENIÊNCIA/FOOD), Conveniência 24h. Tabelas legíveis, valores em R$, datas dd/mm/aaaa HH:mm. Informar onde ficaram os arquivos `.md` e `.xlsx`.

Rodar os testes de sempre (`tests/unit/cash_reconciliation tests/unit/commercial_performance tests/unit/test_auth_access.py` e `node --test tests/frontend/*.test.mjs`).
Commits: `feat(caixa): relatório detalhado do caixa do dia` e `feat(caixa): relatório do dia na tela e na API`. Depois `git push`.
