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

## PARTE A2 — Status da conferência no topo (pedido do diretor, 11/10/2026)

Abrir o relatório (e cada unidade no Telegram e no Painel) com um bloco de status:
1. **Cada fonte contra o webPosto, na mesma forma de pagamento** (nunca adquirentes entre si): PagBank (EDI) × cartões/PIX PagBank no webPosto; Premmia (portal) × formas Premmia; Mais Pagamentos × "Transferência Bancária"; PIX CNPJ × extrato anexado (Sprint 17, quando houver); Dinheiro × apresentado pelo operador. O webPosto não é uma linha própria.
2. **Três estados por fonte:** ✅ conferido e bate (N · R$); ❌ conferido com diferença (fonte R$ × webPosto R$ → diferença R$, e o motivo resumido, ex.: "cobrança em duplicidade Visa 19:12"); ⏳ não conferido (motivo: "aguardando credencial", "extrato não anexado", "coleta falhou"). **Fonte não conferida nunca aparece como ✅.**
3. **Resultado:** "✅ CONFERÊNCIA REALIZADA — tudo bate" só se não houver ❌ nem ⏳; "❌ DIFERENÇAS ENCONTRADAS" se houver ❌ (somar as diferenças em R$); "⚠ CONFERÊNCIA PARCIAL" se só houver ⏳.
4. Exemplos que o teste tem de reproduzir (10/10/2026): **Casa Caiada** — PagBank ✅ 109 · R$ 8.983,98; Premmia ✅ 14 · R$ 1.032,57; Mais Pagamentos ⏳ R$ 3.702,54; Dinheiro ❌ falta R$ 11,71 → "1 diferença (R$ 11,71) e 1 fonte sem conferência". **Doze** — PagBank ❌ R$ 36.541,86 × R$ 36.291,79 → R$ 250,07 (duplicidade); Premmia ✅ 32 · R$ 2.570,17; Mais Pagamentos ⏳ R$ 23.881,93; Dinheiro ❌ falta R$ 84,80.
5. Painel: selo por unidade/dia (✅ / ❌ / ⚠) com link para o relatório.
6. **Totais por adquirente usam o mapa de administradoras por unidade** (config, não código): no Doze (74014) e no Casa Caiada (5555), "**AMERICAN EXPRESS**" faz parte do **PagBank** (decisão do diretor 11/10/2026), além de "PAGSEGURO" e "PIX PAGBANK". Hoje `ADMINISTRADORAS` em `application/conciliar_cartoes.py` só tem PAGSEGURO/PIX PAGBANK: o casamento já usa todos os cartões, mas o total "webPosto" e o "a menor" precisam do mapa completo. Teste: Doze 09/10 PagBank EDI 402 · R$ 31.591,35 = webPosto 402 · R$ 31.591,35 (com o Amex de R$ 100,00).

## PARTE A3 — Direção da diferença, sincronização manual e validação de valores altos (diretor, 11/10/2026)

1. **Sempre mostrar o lado maior** em cada fonte: "**PagBank maior** que o webPosto → cartão não reconhecido automaticamente → **lançar/ajustar no webPosto**" (grupo 1/2); "**webPosto maior** que o PagBank → lançado sem pagamento → **apurar**" (grupo 3, mais grave). Mesma lógica para Premmia e demais fontes.
2. **Botão "Atualizar agora"** (diretor e gerente da unidade) na tela e endpoint `POST /cash-audit/sincronizar?unidade=&dia=`: reconsulta webPosto, PagBank e Premmia (planilha; sem login extra no portal fora do robô) e recalcula o dia; mostra "Dados de dd/mm HH:mm". Limite de 1 sincronização por unidade a cada 2 minutos.
3. **Validação antes de alertar valores altos:** diferença acima de um limite por unidade (padrão: R$ 300,00 ou 3× a mediana das diferenças dos últimos 30 dias da unidade, o que for maior) em **caixa não consolidado** ou com dado de mais de 1 h → **sincronizar automaticamente** e, se continuar, marcar "**a confirmar**" (não "cobrar") até o caixa ser consolidado. Caso real: Casa Caiada 09/10 falta R$ 816,34 com caixa não consolidado.

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
