# Prompt — SPRINT 15.1: relatório com dados atuais e regras novas do caso Doze 10/10 (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Somente leitura no ERP e nos portais; `.env` só via `load_dotenv`; sem reescrever arquivos inteiros; testes sintéticos sem portais; nada pelo Telegram. Datas `dd/mm/aaaa HH:mm`. Nomes de funcionários autorizados no chat (decisão do diretor 11/10/2026); sem CPF, nome de cliente ou NSU completo. Nova versão da regra de cartões: **`CARTOES_V3_4`**.

## O que deu errado no relatório de 10/10 (Doze) — caso real investigado pelo arquiteto

| Relatório (dados gravados às 03:54) | Realidade (webPosto às 14h de 11/10) |
|---|---|
| Falta de R$ 884,80 | Falta de **R$ 84,80**: depois do robô alguém lançou **PIX CNPJ R$ 800,00** manual às 16:00, sem venda |
| "Lançar" Visa R$ 250,07 às 19:12 | **Cobrança em duplicidade**: PagBank tem 2 Visa de R$ 250,07 na **mesma maquininha** (…4038), 19:12:26 (aut. 018845) e 19:13:21 (aut. 024956); o webPosto tem **uma** venda (cupom 10294, 19:13:34, Diesel S10, R$ 350,07 = Cartão POS R$ 250,07 + Dinheiro R$ 100,00, frentista Matheus Gomes da Silva 302036) casada com a das 19:13:21. Ação certa: **estornar** a das 19:12 |
| Grupo 4 vazio | **PIX CNPJ R$ 800,00** precisa de conferência no extrato (RN-CARTAO-009) |
| Abastecimentos/litros "não persistido" | Existem em `V1/ABASTECIMENTOS` (10 frentistas, 1.460 abastecimentos, ~14.370 L, R$ 85.778,72) |
| Despesas sem centro de custo | Centro de custo deve ser lido/gravado (RN-REDE-007) |
| — | Vale de **R$ 1.000,00** para Wanderson da Silva (299246) **fora de caixa** (caixa 0) não apareceu |

Totais corretos do dia: PagBank EDI **495 · R$ 36.541,86** × webPosto **494 · R$ 36.291,79** (493 cartões PagSeguro + 1 PIX na venda) → diferença **1 · R$ 250,07** (a duplicidade). Premmia portal **32 · R$ 2.570,17** = webPosto **32 · R$ 2.570,17**.

@WebPosto_API/src/modules/cash_reconciliation/application/relatorio_caixa_dia.py
@WebPosto_API/src/modules/cash_reconciliation/rules/cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/classificar_recebimentos.py
@WebPosto_API/src/modules/cash_reconciliation/application/conciliar_cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_detalhes.py
@WebPosto_API/src/jobs/relatorio_caixa.py
@docs/regras-negocio/REGRAS_DE_NEGOCIO.md

## PARTE A — Relatório sempre com dados atuais

1. Por padrão o relatório **reconsulta o webPosto** (caixas, apresentado/apurado, cartões, vendas e formas de pagamento, vales, despesas, abastecimentos) e **reconcilia de novo** PagBank (EDI) e Premmia (planilha mensal, sem login) para o dia pedido; opção `--gravado` usa só o resultado salvo. Mostrar no topo "Dados consultados em dd/mm/aaaa HH:mm" e, se diferir do gravado pelo robô, um bloco **"Mudou desde o robô"** (ex.: "Dinheiro apurado R$ 22.677,80 → R$ 21.877,80; novo lançamento PIX CNPJ R$ 800,00 manual 16:00").
2. Totais por adquirente no formato pedido pelo diretor: **EDI/portal × webPosto × diferença (N · R$)**, e a lista dos itens que explicam a diferença.
3. Abastecimentos por frentista (quantidade, litros, R$) a partir de `V1/ABASTECIMENTOS` (sem aferição); despesas com centro de custo/setor; vales **fora de caixa** do dia em bloco próprio.

## PARTE B — Regras novas (CARTOES_V3_4)

1. **Cobrança em duplicidade:** duas ou mais transações da adquirente com **mesmo valor, mesma maquininha (terminal), até 3 min** de diferença e **só uma** venda/cartão correspondente no webPosto → alerta vermelho `CARTAO_COBRANCA_DUPLICADA` na Sprint 14 como grupo **3 (Apurar)** com ação **"verificar estorno ao cliente"** (não "lançar"); mostrar as duas horas, autorizações (finais), terminal, a venda/cupom e o frentista. Se aparecer cancelamento/estorno da transação extra nos dias seguintes → fechar sozinho com histórico.
2. **Venda com "Cartão POS" sem cartão detalhado:** forma de pagamento da venda (`V1/VENDAS_FORMA_PAGAMENTO`, tipo cartão) sem registro correspondente em `V1/CARTOES` → grupo 2 "Detalhar cartão da venda <cupom>" com o pagamento provável da adquirente.
3. **PIX CNPJ (RN-CARTAO-009)** — inclusive lançado depois do robô → sempre grupo **4 (Conferir à mão)** com hora lançada, valor, caixa e operador.
4. **Vale fora de caixa** (caixa 0) → laranja informativo no relatório e no resumo ("Vale R$ 1.000,00 fora de caixa — Wanderson da Silva (299246)").
5. Atualizar `REGRAS_DE_NEGOCIO.md` (RN-CARTAO-011 duplicidade, RN-CARTAO-012 Cartão POS sem detalhe, RN-CAIXA-007 vale fora de caixa) e histórico.

## PARTE C — Testes e validação real

1. Testes sintéticos reproduzindo o caso: 2 transações iguais em 55 s no mesmo terminal + 1 venda → duplicidade (não "lançar"); estorno no dia seguinte fecha; venda Cartão POS sem cartão → grupo 2; PIX CNPJ lançado após o robô → grupo 4; "Mudou desde o robô" listado; vale fora de caixa.
2. Gerar `python -m src.jobs.relatorio_caixa --dia 10/10/2026 --unidade 74014` com dados atuais e mostrar no chat. **Tem de bater** com a tabela acima (falta R$ 84,80; diferença PagBank R$ 250,07 como duplicidade; Premmia 0; PIX CNPJ R$ 800,00 no grupo 4; vale R$ 1.000,00 fora de caixa). Depois gerar o das outras 3 unidades.

Rodar os testes de sempre. Commits: `fix(relatorio): relatório do caixa com dados atuais` e `feat(cartoes): CARTOES_V3_4 — cobrança em duplicidade e cartão POS sem detalhe`. Depois `git push`.
