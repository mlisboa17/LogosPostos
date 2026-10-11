# Prompt — SPRINT 14: Conferência de Recebimentos — LANÇAR / ALTERAR / APURAR / CONFERIR À MÃO (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. **Só comece depois que a Sprint 13.2 estiver commitada.** Somente leitura no ERP e nos portais (o Logos **recomenda** ações; não lança, não altera, não exclui — ADR-003). `.env` só via `load_dotenv`; sem reescrever arquivos inteiros; reutilize o motor existente (CARTOES_V3_3, Pydantic) — **não** introduza Pandas nem um segundo motor; testes sintéticos sem navegador/portal; nada pelo Telegram; no chat nomes como "Funcionário A..." e NSU só com 4 últimos dígitos. **Toda ocorrência: nome do frentista + código (RN-REDE-002) e sempre quantidade · R$.** Cada item cita o ID da regra (`REGRAS_DE_NEGOCIO.md`).

## Objetivo

Transformar o resultado da conciliação (PagBank, Premmia e futuras adquirentes) numa **lista de ações** para o gerente, em 4 grupos fixos:

| Grupo | Quando | Ação recomendada | Cor |
|---|---|---|---|
| **1. LANÇAR NO WEBPOSTO** | Recebido na adquirente e **sem nenhum lançamento** correspondente (nem venda em outra forma) | Incluir o recebimento (forma, valor, hora, frentista sugerido) | 🟠 |
| **2. ALTERAR NO WEBPOSTO** | O dinheiro entrou, mas o registro está errado: forma/bandeira/adquirente trocada; venda lançada como **dinheiro** paga por cartão/app (troca de forma); lançamento manual com hora fictícia ligado a transação real (par provável); 1 lançamento agregado de vários cartões (grupo provável) | Retificar **De → Para** (ex.: "Dinheiro → Premmia Cartão APP", "Premmia Crédito → Premmia Desconto", "POS PREMMIA → Premmia Pix", "1 Maestro manual R$ 179,45 → 4 cartões") | 🟠 |
| **3. APURAR — LANÇAMENTO SEM LASTRO** | Lançado no webPosto e **sem transação** em nenhuma adquirente ativa, mesmo após a busca cruzada (item A.2) | Flag **"SUSPEITA DE LANÇAMENTO SEM LASTRO"**; recomendar apuração e, após apuração, exclusão do registro. Não é acusação: é prioridade de verificação | 🔴 |
| **4. CONFERIR À MÃO** | O Logos ainda não tem fonte para conferir (ex.: PIX CNPJ do Doze — RN-CARTAO-009; adquirentes "pendente") | Diretor/gerente marca **Conferido** ou **Não encontrado** (+ observação); "Não encontrado" move para o grupo 3 | ⚪ |

Casos reais que **têm** de cair no grupo certo (01–09/10/2026):
- Casa Caiada 01/10 07:01, Premmia Cartão APP R$ 100,00, venda 375370418 lançada em DINHEIRO → **2. ALTERAR** (Dinheiro → Premmia Cartão APP).
- Casa Caiada 01/10 08:47 R$ 13,90 e 09/10 08:24 R$ 50,00, 10:19 R$ 30,00, 15:26 R$ 34,75 (PagBank, venda em dinheiro) → **2. ALTERAR**.
- Casa Caiada 02/10 12:00 "PREMMIA" R$ 40,00 manual, sem pagamento → **3. APURAR**.
- Casa Caiada 07/10 grupo R$ 179,45 → **2. ALTERAR** (1 → 4).
- Doze: 2 Premmia Crédito R$ 10,00 que são desconto e POS PREMMIA R$ 200,02 → **2. ALTERAR**; PIX manuais com hora 01:00 casados no PagBank → **2. ALTERAR** (hora/vínculo); 01/10 R$ 160,00 sem abastecimento → **1. LANÇAR**.
- Doze PIX CNPJ (7 · R$ 2.480,41) → **4. CONFERIR À MÃO**.

## PARTE A — Classificação

@WebPosto_API/src/modules/cash_reconciliation/application/conciliar_cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/recebimentos.py
@WebPosto_API/src/modules/cash_reconciliation/domain/cartoes.py

1. Nova função de aplicação `classificar_recebimentos(...)` (arquivo novo `application/classificar_recebimentos.py`) que recebe os resultados já calculados por adquirente da unidade/dia e devolve itens `AcaoRecebimento` (modelo Pydantic frozen novo em `domain/`): grupo, motivo, de → para, valor, data/hora, adquirente, forma, NSU (mascarado na exibição), venda, caixa, frentista (nome + código ou "não identificado" + motivo), ID da regra, evidências.
2. **Busca cruzada antes do grupo 3:** um lançamento sem par na sua adquirente só vai para o grupo 3 depois de procurar, nas **outras adquirentes ativas da unidade** e em outras formas, transação de **mesmo valor no mesmo dia** (até 30 min). Achou → grupo 2 ("lançado como X, pago como Y").
3. **Troca de forma:** "recebido e não lançado" cuja venda/abastecimento atribuído foi lançado em dinheiro (já detectado como `troca_de_forma`) → grupo 2, não grupo 1.
4. **Reincidência por frentista:** contar no mês os itens do grupo 2 de troca de forma e do grupo 3 por frentista; 3 ou mais → selo "REINCIDENTE" no item e no resumo (caso real: frentista 277311 do Casa Caiada, 3 trocas · R$ 163,90).
5. Nova regra no `REGRAS_DE_NEGOCIO.md`: **RN-CARTAO-010 — Classificação acionável dos recebimentos** (os 4 grupos, busca cruzada, reincidência), com histórico.

## PARTE B — Tela, conferência manual, pendências e Telegram

@WebPosto_API/src/modules/cash_reconciliation/interfaces/http.py
@WebPosto_API/src/modules/cash_reconciliation/application/gerar_pendencias.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/pendencias.py
@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py
@WebPosto_API/frontend/pages/directorDashboard.js

1. Endpoint `GET /cash-audit/conferencia-recebimentos?unidade=&inicio=&fim=` (escopo do gerente respeitado), lido dos resultados gravados.
2. Tela nova `frontend/pages/conferenciaRecebimentos.js` (menu logo após o Painel do Diretor), estilo dark existente:
   - cabeçalho: unidade, período, "Conferido: N · R$ X";
   - tabela **por forma**: adquirente × webPosto × diferença (R$), por adquirente e aba "Todas";
   - os 4 grupos em blocos, cada um com "N · R$ X" e a lista (data/hora, valor, de → para, frentista, regra, selo REINCIDENTE).
3. **Conferência manual (grupo 4):** botões Conferido / Não encontrado + observação; grava no SQLite de pendências como evento com usuário e data/hora (histórico preservado); "Não encontrado" cria pendência vermelha do grupo 3. Endpoint `POST` correspondente, só diretor/gerente da unidade.
4. Pendências: grupo 3 = vermelha individual; grupos 1 e 2 = laranja agrupada por caixa/dia (RN-PEND-001); idempotente; substituídas com histórico.
5. Telegram, por filial: `Recebimentos: N conferidos · R$ X` e `1 Lançar N · R$ · 2 Alterar N · R$ · 3 Apurar N · R$ · 4 Conferir à mão N · R$`, e cada item do grupo 3 em linha própria com o nome do frentista. Planilha diária: aba "Ações de recebimento" com os 4 grupos e colunas Conferido (S/N) e Observação.

## PARTE C — Testes e dados reais

1. Testes sintéticos de cada grupo, da busca cruzada (lançado como PagBank, pago no Premmia → grupo 2), da troca de forma, do grupo provável, da reincidência e da conferência manual (Não encontrado → grupo 3). Nenhum acesso ao portal.
2. Reprocessar 01–09/10/2026 para Doze e Casa Caiada a partir dos dados gravados (sem login) e conferir que os casos reais listados acima caem no grupo esperado.
3. Relatório no chat por unidade: Conferido (N · R$); os 4 grupos com N · R$ e item a item; reincidentes.

Rodar os testes de sempre e `node --test tests/frontend/*.test.mjs`. Conferir a tela no navegador local (somente leitura; não marcar conferência real).
Commits: `feat(recebimentos): classificação lançar/alterar/apurar/conferir` e `feat(recebimentos): tela de conferência, conferência manual e Telegram`. Depois `git push`.
