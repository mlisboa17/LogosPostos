# Prompt — SPRINT 12: CARTOES_V3 — mesmo NSU com valor diferente e cancelamentos (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem merge na main e sem troca de branch. Somente leitura no ERP (`WEBPOSTO_WRITES=0`) e no PagBank. `.env` só via `load_dotenv`, nunca imprimir nem editar. Altere SOMENTE as funções citadas; não reescreva arquivos inteiros; não adicione dependências. Datas no padrão Brasil. Testes sintéticos, nunca gravam no banco real nem enviam Telegram. No chat: sem nomes de funcionários (use "Funcionário A..."), sem NSU completo (mostre só os 4 últimos dígitos).

## Problema

Em `rules/cartoes.py`, função de casamento (~linhas 50–62): quando o **NSU ou a autorização** batem, a transação vira "casada" **sem comparar o valor**. Exemplo: webPosto R$ 150,00 e PagBank R$ 100,00 com o mesmo NSU → hoje passa como conferido, e os R$ 50,00 nunca serão recebidos.
Além disso, `adapters/pagbank_edi.py` (~linhas 41–43) **descarta** transações canceladas/ajustes (`tipo_evento != "1"` ou status não aprovado). O lançamento do webPosto correspondente aparece como "a menor" sem explicação.

Arquivos:
@WebPosto_API/src/modules/cash_reconciliation/rules/cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/domain/cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/domain/recebimentos.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/pagbank_edi.py
@WebPosto_API/src/modules/cash_reconciliation/application/conciliar_cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/gerar_pendencias.py
@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py
@WebPosto_API/frontend/pages/cashAudit.js
@WebPosto_API/tests/unit/cash_reconciliation/test_cartoes.py
@WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py
@WebPosto_API/tests/frontend/cashAudit.test.mjs

## PARTE A — Regra CARTOES_V3

1. Nova `VERSAO = "CARTOES_V3"` (atualizar a docstring com os itens novos). Resultados V2 gravados continuam abrindo (campos novos opcionais com padrão vazio).
2. Casamento por NSU/autorização: calcular `diferenca = valor_webposto - valor_pagbank`. Se `|diferenca| >= R$ 0,01` → o casamento ganha `valor_divergente=True` e `diferenca`:
   - **webPosto maior que PagBank** → alerta **vermelho** `CARTAO_VALOR_A_MENOR` ("Lançado R$ X, recebido R$ Y — faltam R$ Z"). É dinheiro que não vai entrar.
   - **PagBank maior que webPosto** → alerta **laranja** `CARTAO_VALOR_A_MAIOR`.
   - O casamento por valor+hora (PIX sem NSU) não muda — ele já exige valor igual.
3. Cancelamentos: em `pagbank_edi.py`, **não descartar**; devolver separadamente as transações com `tipo_evento != "1"` ou status não aprovado, como `TransacaoAdquirente` com campo novo opcional `situacao` ("cancelada", "estornada", "ajuste" ou o código original, se desconhecido). Ver primeiro nos dados reais quais valores existem (item 6) e mapear só os confirmados. Elas **não** entram no casamento normal.
4. Lançamento do webPosto sem par ("a menor") que tenha uma transação cancelada/estornada com o mesmo NSU/autorização → motivo "cancelada no PagBank em dd/mm/aaaa HH:mm" (continua vermelho: o webPosto registrou uma venda que não vai ser paga).
5. **NSU repetido no webPosto** (caso real VIP 05/10/2026: o mesmo NSU de um PIX Premmia de R$ 30,00 foi lançado em **duas vendas** diferentes, às 23:04 e 23:09, e o portal tem **um** pagamento): antes do casamento, agrupar `CartaoErp` por NSU/autorização (ignorando vazios); grupo com 2+ lançamentos → alerta **vermelho** `CARTAO_NSU_REPETIDO` com as vendas, horários, valores e o frentista de cada venda (via abastecimento/venda, mesma lógica da atribuição). Só o primeiro entra no casamento; os demais saem como "a menor" com o motivo "NSU já usado na venda X". Isso pode ser lançamento em duplicidade ou o mesmo comprovante usado para duas vendas — é grave e precisa de tratativa.
6. Guardar `tipoInclusao` do `V1/CARTOES` em `CartaoErp` (campo opcional; valores vistos: `PDV-TEF`, `PDV-Mobile`) e mostrá-lo no detalhe de toda divergência — permite saber se o lançamento foi automático ou manual. Liste no relatório os valores distintos encontrados.
7. Totais por adquirente no resultado: `casados_valor_divergente` (quantidade e soma das diferenças) e `cancelados` (quantidade e soma).

## PARTE B — Pendências, tela e Telegram

1. `gerar_pendencias.py`: `CARTAO_VALOR_A_MENOR` → pendência vermelha individual `recebimento_valor_a_menor`; `CARTAO_VALOR_A_MAIOR` → entra no grupo laranja do dia/caixa (regra da Sprint 07). Idempotente.
2. `cashAudit.js`, só na tabela de recebimentos: coluna "Diferença" para casados com valor divergente (vermelho se faltar dinheiro) e a etiqueta "cancelada no PagBank" no item "a menor" quando houver.
3. `resumo_diario.py`, na mensagem do Telegram: linha por filial "Cartões: N com valor menor que o recebido (faltam R$ X)" só quando houver; e "N cancelados no PagBank" quando houver.

## PARTE C — Testes e dados reais

1. Testes: mesmo NSU e valor igual → casado sem alerta; mesmo NSU e webPosto maior → vermelho com a diferença; PagBank maior → laranja; cancelada com mesmo NSU de um "a menor" → motivo de cancelamento; resultado V2 antigo abre; pendência não duplica.
2. Reprocessar **01 a 09/10/2026** para Doze (74014) e Casa Caiada (5555) (`python -m src.modules.cash_reconciliation.jobs.noturno --dia dd/mm/aaaa`, um dia por vez; não envia Telegram).
3. **Teste de aceitação com dado real:** reprocessar também o VIP (11495) em 05/10/2026 — o PIX Premmia de R$ 30,00 com NSU repetido nas vendas 376185045 e 376185515 **tem que** aparecer como `CARTAO_NSU_REPETIDO` (vermelho) mesmo sem o portal Premmia integrado (a regra olha só o webPosto). Se não aparecer, a sprint não está pronta.
4. Antes de mapear o item A.3, liste os valores distintos de `status_pagamento` e `tipo_evento` encontrados no EDI desses dias, com a quantidade de cada um (só agregados).

## Ao terminar

```
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; python -m pytest tests/unit/cash_reconciliation tests/unit/commercial_performance tests/unit/test_auth_access.py -q -o addopts=""; node --test tests/frontend/*.test.mjs
```
Informe por unidade (01 a 09/10): casados, **casados com valor divergente** (quantidade e R$ a menor / a maior), cancelados (quantidade e R$), e quantos "a menor" agora têm motivo de cancelamento. Valores de `status_pagamento`/`tipo_evento` encontrados.
Commits: `feat(cartoes): CARTOES_V3 — valor divergente no mesmo NSU e cancelamentos` e `feat(cartoes): pendências, tela e Telegram da CARTOES_V3`. Depois `git push`.
