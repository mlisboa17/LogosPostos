# Prompt — SPRINT 13.1: casamento do desconto Premmia, POS PREMMIA e valores em tudo (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Mesmas regras da Sprint 13: somente leitura no ERP e no portal; `.env` só via `load_dotenv`; sem reescrever arquivos; testes sintéticos que nunca abrem navegador nem acessam o portal; nada pelo Telegram; no chat sem CPF/nome de cliente e com nomes de funcionários trocados por "Funcionário A...". **Regra fixa RN-REDE-002:** nome do frentista em toda ocorrência. Nova versão da regra: **`CARTOES_V3_2`**.
**Não é preciso novo login no portal:** use as planilhas mensais já coletadas (`data/premmia/postocasacaiada_10_2026.xlsx` e `postodoze_10_2026.xlsx`).

## Evidência (revisão do arquiteto, 11/10/2026)

1. **Desconto Premmia:** o código do portal aparece no **final do NSU do ERP**, depois do último hífen. Casa Caiada 06/10, 7 de 7 casos:
   - portal `GQE6WQJN` (00:57:33, R$ 5,00) ↔ ERP `PREMMIA DESCONTO CUPOM` NSU `...735-GQE6WQJN` (00:57:57, R$ 5,00)
   - portal `M3M2ZUWG` (07:45:22, R$ 12,00) ↔ ERP `...523-M3M2ZUWG` (07:45:34, R$ 12,00)
   - mesmo padrão nos outros 5. Diferença de horário de 10 s a 1 min.
   Hoje esses casos caem como "a maior" + "a menor" com o mesmo valor (Casa Caiada: 36 casos, R$ 287,50).
2. **POS PREMMIA:** Doze 08/10, PIX de R$ 200,02 no portal e `POS PREMMIA` R$ 200,02 no ERP com códigos diferentes (pagamento na maquininha do Premmia).
3. **Doze — correção do diretor:** descontos Premmia lançados como HIPERCARD foram corrigidos no cadastro do webPosto. Consulta de hoje no ERP (Doze, 01–09/10): não há mais HIPERCARD; `PREMMIA DESCONTO CUPOM` passou a 27 lançamentos / R$ 210,50. O portal tem R$ 423,50 de desconto no período — **a diferença restante tem de aparecer explicada item a item**.

@WebPosto_API/src/modules/cash_reconciliation/rules/cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/conciliar_cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py
@WebPosto_API/frontend/pages/cashAudit.js
@WebPosto_API/tests/unit/cash_reconciliation/test_cartoes.py
@docs/regras-negocio/REGRAS_DE_NEGOCIO.md

## PARTE A — Regras de casamento (CARTOES_V3_2)

1. **Chave de cupom:** além do NSU exato, casar quando o NSU do ERP **termina em `-<código do portal>`** (comparar o trecho após o último hífen, sem diferenciar maiúsculas), com o **mesmo valor** e **mesmo dia**. Chave registrada como `"cupom"`. Vale para qualquer adquirente que use esse padrão; não afrouxar o NSU exato dos demais.
2. **POS PREMMIA:** transação do portal sem casamento × lançamento `POS PREMMIA` sem casamento → casar por **mesmo valor e até 10 min** (mesma regra do PIX sem NSU), chave `"valor_hora"`. Se houver mais de um candidato, não casar: vira par provável para conferência.
3. Nenhum casamento só por valor fora desses dois casos (manter a decisão da Sprint 13).
4. Atualizar `REGRAS_DE_NEGOCIO.md`: RN-CARTAO-002 (chave de cupom e POS PREMMIA) e RN-PREMMIA-001 (forma `PREMMIA DESCONTO CUPOM`), com data e versão `CARTOES_V3_2` no histórico.
5. Testes: os 7 casos reais de 06/10 reproduzidos com dados sintéticos (códigos inventados no mesmo formato) → casam; NSU que só contém o código no meio (não no final) → não casa; POS com dois candidatos → par provável; resultado V3_1 antigo continua abrindo.

## PARTE B — Valores sempre junto com a quantidade (pedido do diretor)

1. Telegram, tela de recebimentos e relatório do agente: **todo número de itens vem com o valor em R$** (ex.: "Divergências: 2 · R$ 140,00"; "A maior: 1 · R$ 100,00"; "Conferidos: 103 · R$ 14.622,05").
2. Por forma de pagamento (Cartão APP, Pix, Desconto, Vale, POS): quantidade e R$ do portal × webPosto e a diferença em R$.
3. Teste frontend e de mensagem cobrindo os valores.

## PARTE C — Reprocessamento e relatório

1. Reprocessar **Casa Caiada e Doze, 01 a 09/10/2026**, a partir das planilhas mensais (sem login), com a CARTOES_V3_2.
2. Relatório no chat, **em linguagem simples e com valores**, por unidade:
   - Conferido: quantidade · R$.
   - Divergências reais restantes, **item a item**: dia, hora, forma, valor, lado (só no portal / só no webPosto), frentista ("Funcionário A..."), e uma frase do que provavelmente significa.
   - Doze: explicar a diferença restante de desconto (portal R$ 423,50 × webPosto R$ 210,50 em 10/10), dizendo quantos descontos do portal ficaram sem lançamento e em que dias.
   - Tabela por forma: portal × webPosto × diferença (R$).
3. Rodar os testes de sempre e confirmar zero acesso ao portal nos testes.

Commits: `feat(cartoes): CARTOES_V3_2 — desconto Premmia por cupom e POS PREMMIA` e `feat(resumo): valores em R$ junto das quantidades`. Depois `git push`.
