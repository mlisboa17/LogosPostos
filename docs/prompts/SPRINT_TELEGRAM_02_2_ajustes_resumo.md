# Prompt — SPRINT TELEGRAM_02.2 (correção rápida): recebimentos sem "diferenças" falsas e ordem por valor

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). Somente leitura. `.env` só via `load_dotenv`. Sem reescrever arquivos. **Não enviar nada pelo Telegram.** Rodar só os testes do resumo durante o trabalho; bateria completa no final. Meta: 20 min.

@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py

## O que o arquiteto viu no resumo de 13/10/2026 (`data/resumos/2026-10-13.md`)

1. **Bloco "💳 RECEBIMENTOS · Doze" mostra diferenças que não existem.** O portal chama "MASTERCARD" e o webPosto "MASTERCARD PAGSEGURO", e o resumo compara bandeira por bandeira pelo nome: aparecem "diferença R$ 3.427,53" e "diferença R$ −3.427,53" para o mesmo dinheiro (idem Maestro, Visa Electron, Elo). O diretor vai achar que faltam milhares de reais. A conciliação real diz "313 conferidos · R$ 19.600,13".
   → No Telegram, por posto, **uma linha por adquirente**: `PagBank: portal R$ X · webPosto R$ Y · ✅ conferido` ou `❌ diferença R$ Z`, usando o **mesmo resultado da conciliação** (casados, a maior, a menor) — nunca o agrupamento por nome de bandeira. Abaixo, só os itens **a maior/a menor/duplicidade** (no máximo 5, com hora, valor e frentista nome + código). A tabela por bandeira fica **só na planilha**, com as bandeiras do portal e do webPosto **agrupadas** (Mastercard = MASTERCARD PAGSEGURO; Maestro = MAESTRO PAGSEGURO; Visa Electron = VISA ELECTRON PAGSEGURO; Elo/Elo Débito = ELO DEBITO PAGSEGURO; "Cartão APP" explicado ou mostrado à parte).
2. **Ordem do "PRECISA DE VOCÊ":** estava sangria de R$ 432,00 antes de falta de R$ 182,51 e sangrias de R$ 6,00 e R$ 1,00 no meio das faltas. Ordenar **todos** os itens por valor (maior primeiro). Sangrias "alteradas após o lançamento" do mesmo caixa/dia viram **uma linha só** ("VIP · Pista — 4 sangrias alteradas após o lançamento (R$ 667,00)") e, se possível, dizer o valor antes → depois.

Testes de regressão: bandeiras com nomes diferentes no portal e no webPosto e mesmo total → nenhuma diferença; ordem por valor misturando tipos; sangrias agrupadas.
Regerar e mostrar no chat o resumo de 13/10/2026 (sem enviar).
Commit: `fix(telegram): recebimentos pela conciliação e itens por valor`. Depois `git push`.
