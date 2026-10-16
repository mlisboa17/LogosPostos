# Prompt — SPRINT 19: o Logos explica a falta do caixa e diz exatamente o que corrigir

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). `.env` só via `load_dotenv`/`dotenv_values`, nunca imprimir nem editar. Sem reescrever arquivos. Somente leitura no webPosto, exceto o lançamento de cartão já existente (18b), que continua só com travas + "ok" do diretor. Testes sintéticos. Extratos em `C:\Projetos\LOGOS\extratos\` (somente leitura). Meta: ~30 min por parte.

Regras de texto (obrigatórias, memória do diretor): o próprio Logos explica em português simples, sem jargão; caixa identificado como na tela do webPosto ("Doze · Pista — 14/10, 1º turno (Wanderson, 00:01)"); toda ocorrência com **nome + código do frentista**.

@WebPosto_API/src/modules/cash_reconciliation/application/relatorio_caixa_dia.py
@WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py
@WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py

## Caso real que o arquiteto montou à mão (Doze, 14/10/2026) — o Logos tem de fazer igual, sozinho

Falta de dinheiro **R$ 686,71** (caixa não consolidado):
| Parte | Valor | Fonte |
|---|---:|---|
| Mastercard PagBank lançado como dinheiro — AILTON LUIZ DA SILVA (299239), 11:26 | R$ 34,75 | EDI PagBank × vendas |
| PIX da maquininha PagBank ("BACEN") lançado como dinheiro — AILTON (299239), 14:20 | R$ 139,35 | EDI PagBank × vendas |
| PIX Mais Pagamentos a mais que o webPosto: portal R$ 10.741,86 × "Transf. Crédito" R$ 10.241,86 | R$ 500,00 | total informado pelo diretor |
| Sem explicação | R$ 12,61 | — |
PIX CNPJ (direto na conta PagBank, extrato `PagBank_DOZE_10_a_14_Outubro2026.ofx`): nenhum de cliente em 14/10 — os 6 "Pix recebido" são transferências entre os postos do grupo (Posto Abreu e Lima = Doze, Auto Posto Casa Caiada, Posto Doze) e créditos da Vibra.

## PARTE A — "De onde vem a falta" por caixa

No relatório do caixa, na tela e no resumo do Telegram, para cada caixa com falta/sobra: uma tabela como a acima, somando até o total, com a linha "sem explicação" no final. Cada parte diz **o que corrigir, onde e para qual frentista**:
- cartão/PIX PagBank lançado como dinheiro → "Posso lançar o cartão (Mastercard PagSeguro, NSU final 0163) na venda 377600619 do AILTON (299239)" + botão [Lançar] (caminho da 18b);
- PIX Mais Pagamentos ou PIX CNPJ → **não há rota na API**: instrução exata para a tela ("no caixa Doze · Pista 14/10, venda das 14:20 de R$ 500,00 do FULANO (código): trocar Dinheiro → Transferência Bancária / conta MAIS PAGAMENTOS").

## PARTE B — PIX CNPJ automático pelo extrato do PagBank

Ler os OFX da pasta `PAGBANK` da unidade (deduplicar por FITID). PIX CNPJ de cliente = "Pix recebido" **menos** transferências entre empresas do grupo e créditos de fornecedores (reaproveitar o filtro de grupo da DESPESAS_00; nomes: Posto Abreu e Lima = Doze, Auto Posto Casa Caiada, Posto Doze, Posto VIP, Loja de Conveniência, Posto Real; fornecedores: Vibra etc.). Casar cada PIX CNPJ com lançamento manual de transferência no caixa do dia (valor/hora); o que sobrar → candidato "PIX CNPJ não lançado" com a venda/abastecimento de mesmo valor perto da hora e o frentista. Status no relatório deixa de ser "⏳ extrato não anexado" quando o extrato cobre o dia.

## PARTE C — Mais Pagamentos pelo total do dia (enquanto não há API)

Comando `python -m src.jobs.mais_pagamentos_total --unidade 74014 --dia dd/mm/aaaa --total 10741,86` **e** resposta no Telegram ("Mais Pagamentos Doze 14/10 10741,86", só o chat do diretor) → grava em `data/mais_pagamentos/` e compara com "Transf. Crédito" do caixa. Diferença → linha na Parte A. Se o diretor informar também a **hora e o valor** de um PIX ("14/10 14:35 500,00"), o Logos procura a venda de mesmo valor perto da hora **lançada como dinheiro** e diz o frentista.

## PARTE D — Ajustes da 18b

1. Depois de `nao_entrou` (resolvido), permitir **nova tentativa** do mesmo NSU somente com `--confirmar --nsu --nova-tentativa` (ok explícito do diretor), registrada na auditoria.
2. Incluir o **PIX da maquininha PagBank** como lançável quando existir administradora PagBank PIX/BACEN única no webPosto (`V1/ADMINISTRADORAS`); senão, explicar "não há administradora de PIX PagBank cadastrada — lançar à mão".

## Entrega

Testes sintéticos de cada parte (grupo filtrado, PIX CNPJ casado/não casado, total Mais Pagamentos com diferença, nova tentativa, PIX BACEN).
Rodar real (somente leitura) para **Doze 14/10/2026** com `--total 10741,86` e mostrar no chat a tabela "De onde vem a falta" — tem de bater com a do arquiteto (174,10 + 500,00 + 12,61 = 686,71). Não lançar nada.
Atualizar `REGRAS_DE_NEGOCIO.md` (RN-CARTAO-009 PIX CNPJ, nova RN da explicação da falta) e `STATUS.md`.
Commits por parte. Depois `git push`.
