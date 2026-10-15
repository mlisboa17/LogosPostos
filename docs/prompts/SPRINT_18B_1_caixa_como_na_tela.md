# Prompt — SPRINT 18b.1 (correção rápida): identificar o caixa como o diretor vê no webPosto

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). Somente leitura no webPosto. `.env` só via `load_dotenv`, nunca imprimir nem editar. Sem reescrever arquivos. **Não enviar nada pelo Telegram e não lançar nada.** Rodar só os testes afetados durante o trabalho; bateria completa no final. Meta: 20 min.

@WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py
@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py

## Problema (diretor, 15/10/2026)

O Logos escreve "Doze · Pista (caixa 4466831)". **O código interno do caixa não aparece na tela do webPosto** — o diretor não consegue achar o caixa por ele.

## Correção

1. Em **todo texto ao diretor** (proposta de cartão da 18b, botões do Telegram, resumo do Telegram, tela "Lançamentos do Logos", planilha), identificar o caixa como na tela do webPosto, a partir de `V1/CAIXAS` (`dataMovimento`, `turno`, `funcionarioCodigo` → nome por `V1/FUNCIONARIOS`, `abertura`, `fechamento`, `apurado`) e do setor (centro de custo):
   > **Doze · Pista — caixa de 14/10/2026, 1º turno, aberto por WANDERSON DA SILVA às 00:01 (fechado 00:02 de 15/10), apurado R$ 50.016,49**
   Versão curta para listas: `Doze · Pista — 14/10, 1º turno (Wanderson, 00:01)`.
   Quando só houver um caixa no dia/setor, acrescentar "(único caixa do dia)".
2. O código interno (`caixaCodigo`) fica **só** em log, auditoria e planilha (coluna própria "código interno"), nunca no texto principal.
3. Na proposta de cartão, mostrar também os valores para o diretor conferir na tela: **"Antes: dinheiro R$ 15.855,41 · cartão R$ 23.439,22. Depois de lançar: dinheiro R$ 15.820,66 · cartão R$ 23.473,97."**
4. Nome do funcionário: se não houver nome, usar "funcionário 299246" (nunca vazio). Datas e horas em dd/mm/aaaa HH:mm (America/Recife).

Testes: texto sem `caixaCodigo`; formato longo e curto; "único caixa do dia"; antes/depois calculado; fallback sem nome.
Mostrar no chat o texto que o Logos gera agora para o cartão Mastercard R$ 34,75 do Ailton (Doze, 14/10) e as linhas de caixa do resumo de 13/10/2026 — sem enviar e sem lançar.
Commit: `fix(textos): caixa identificado como na tela do webPosto`. Depois `git push`.
