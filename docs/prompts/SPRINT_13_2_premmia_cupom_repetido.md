# Prompt — SPRINT 13.2: cupom Premmia repetido e integridade da planilha mensal (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Mesmas regras da Sprint 13.1: somente leitura; `.env` só via `load_dotenv`; sem reescrever arquivos; testes sintéticos sem navegador/portal; nada pelo Telegram; **sem novo login no portal**; no chat sem CPF/nome de cliente e nomes de funcionários como "Funcionário A...". Nova versão: **`CARTOES_V3_3`**. Regras: RN-PREMMIA-002, RN-CARTAO-002.

## Bug confirmado pelo diretor (11/10/2026)

- Export original do Doze (`data/premmia/originais/74014_2026-10-01_2026-10-09_*.xlsx`): **210 linhas**. Planilha mensal `data/premmia/postodoze_10_2026.xlsx`: **208 linhas**.
- As 2 linhas perdidas são descontos de **R$ 7,00 em 04/10 (14:28:35 e 14:55:41)**. Elas usam o **mesmo "Código Transação"** de um cupom promocional que também aparece em 07/10 14:17:33. A deduplicação por código manteve uma e apagou as outras.
- Efeito: dois descontos lançados corretamente no webPosto (04/10 14:30 e 16:01) apareceram como "lançado e não pago". **Falso positivo.**
- Casa Caiada não teve códigos repetidos (140 = 140), mas a correção vale para todos.

@WebPosto_API/src/modules/cash_reconciliation/adapters/premmia_portal.py
@WebPosto_API/src/modules/cash_reconciliation/rules/cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py
@WebPosto_API/tests/unit/cash_reconciliation/test_cartoes.py
@docs/regras-negocio/REGRAS_DE_NEGOCIO.md

## Correção

1. **Deduplicação da planilha mensal:** linha repetida só se forem iguais **código + data/hora + valor + forma**. Mesmo código com data/hora diferente = transações diferentes.
2. **Casamento com código repetido (CARTOES_V3_3):** quando o mesmo código (NSU exato ou cupom no sufixo) aparece em mais de uma transação, casar por **código + valor + dia**, ligando cada transação do portal ao lançamento do ERP de **horário mais próximo** (um para um, sem reutilizar). Sem candidato no mesmo dia → segue como a maior/a menor.
3. **Integridade a cada coleta:** comparar, por dia, as linhas do export original com as gravadas na planilha mensal. Se diferir → aviso "Premmia: N linhas do portal não entraram na planilha" na unidade e no Telegram (não é falha do robô) e registro em log.
4. **Remontar** `postodoze_10_2026.xlsx` e `postocasacaiada_10_2026.xlsx` a partir de `data/premmia/originais/` (sem login), guardando a versão anterior em `data/premmia/antes_v33/`. Conferir 210 = 210 (Doze) e 140 = 140 (Casa Caiada).
5. Reprocessar **01 a 09/10/2026** das duas unidades. Pendências que deixarem de valer (ex.: os 2 descontos de R$ 7,00) → `aprovada`, usuário `robo`, justificativa "CARTOES_V3_3: cupom repetido estava sendo deduplicado indevidamente". Histórico preservado.
6. Atualizar `REGRAS_DE_NEGOCIO.md` (RN-PREMMIA-002: deduplicação e integridade; RN-CARTAO-002: código repetido) e o histórico.
7. Testes: 3 usos do mesmo cupom (2 no mesmo dia) → 3 linhas na planilha e 3 casamentos; duplicata verdadeira (linha idêntica) → 1 linha; integridade diferente → aviso; nenhum acesso ao portal.

## Relatório (linguagem simples, sempre quantidade · R$)

Por unidade: conferido; tabela por forma (portal × webPosto × diferença); ocorrências restantes item a item, separadas em **lançado e não pago**, **forma errada** e **recebido e não lançado**.

Rodar os testes de sempre. Commit: `fix(premmia): CARTOES_V3_3 — cupom repetido e integridade da planilha mensal`. Depois `git push`.
