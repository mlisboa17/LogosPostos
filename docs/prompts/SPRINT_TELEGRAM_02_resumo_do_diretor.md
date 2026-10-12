# Prompt — SPRINT TELEGRAM_02: resumo do Telegram para o diretor (curto, por caixa, com o que fazer)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). Somente leitura no webPosto. `.env` só via `load_dotenv`, nunca imprimir nem editar. Sem reescrever arquivos inteiros. Testes sintéticos (nenhum teste chama Telegram real). **Não enviar nada pelo Telegram** até o diretor dar "ok" no chat. Rodar só os testes do resumo durante o trabalho; bateria completa no final. Meta: ~30 min.

@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py
@WebPosto_API/src/jobs/telegram.py
@WebPosto_API/src/jobs/noturno.py

## Reclamação do diretor (12/10/2026)

O resumo das 03:39 (`data/resumos/2026-10-11.md`) veio "com muita informação, bagunçado e pequeno". Problemas: códigos (74014, 11495) em vez de nomes; linhas que não pedem ação ("Recebimentos a maior: R$ 0,00", "MAIS_PAGAMENTOS: pendente" repetido); o que importa fica escondido; não diz o que fazer.
Regra do diretor: **em um caixa trabalham vários frentistas** → o caixa se identifica por **nome do posto + setor (centro de custo) ou nome do caixa**, não por um frentista. **O VIP tem dois caixas por dia** (Pista cc 7295 e Loja/Conveniência cc 21650 — RN-REDE-007).

## Formato novo (mensagem principal, cabe numa tela de celular)

```
🌙 LOGOS — Caixas de sábado, 11/10/2026

⚠️ PRECISA DE VOCÊ
1. VIP · Loja (caixa 4464044, 1º turno) — falta R$ 1.910,09, sem desconto, não consolidado
2. Doze — conferência não rodou (erro ao consultar o fechamento)
3. Conveniência 24h — senha do PagBank inválida

⏳ AINDA ABERTOS
• VIP · Pista (caixa 4463975, 1º turno) — aberto desde 00:01; quebra só depois de fechar

✅ EM ORDEM
• Casa Caiada · Pista — falta R$ 16,56
• Conveniência 24h · Loja — falta R$ 6,82

📋 Pendências abertas: 121 — Doze 28 · VIP 45 · Casa Caiada 26 · Conv. 24h 22
```

Regras:
1. **Nome do posto** (de `units.json`) e **nome do setor** pelo centro de custo (RN-REDE-007; sem nome conhecido → "cc 24886"), número do caixa e turno. **Nunca o código da unidade.**
2. **Precisa de você** = falta acima do limite da unidade (usar o limite já existente; se não houver, R$ 10,00), falta sem desconto, cartão/PIX a menor, cobrança em duplicidade, conferência que falhou, credencial inválida, caixa parado. Cada item diz **o problema e o valor**; quando a ocorrência é individual (cartão, vale, troca de forma) aparece **nome + código do frentista**. Ordenar por valor.
3. **Caixa aberto** nunca aparece como falta: vai para "⏳ ainda abertos" com hora de abertura.
4. **Não mostrar** linhas com R$ 0,00 nem fontes "pendente" que ainda não têm integração (Mais Pagamentos, Rede, Cielo). Fonte só aparece quando der **erro**.
5. Datas `dd/mm/aaaa` com dia da semana; valores `R$ 1.910,09`.
6. Limite de ~25 linhas; o detalhe completo continua na planilha anexa e na tela do Logos.
7. A planilha anexa passa a ter a coluna "Caixa" no formato "VIP · Loja (4464044)" em vez do código da unidade.

## Também nesta sprint

- **Vazamento de teste da DESPESAS_00 Parte B:** os testes gravaram 13 arquivos falsos (8–14 bytes) em `WebPosto_API/data/despesas_avulsas/comprovantes/`. Corrigir os testes para usar `tmp_path` e apagar só esses arquivos falsos (conferir tamanho < 100 bytes antes).

## Entrega

1. Testes: nomes no lugar de códigos; VIP com dois caixas separados por setor; caixa aberto fora das faltas; sem linhas R$ 0,00; ordem por valor; limite de linhas.
2. Gerar o resumo novo de **11/10/2026** a partir dos dados já gravados (`data/cash_audit/2026-10-11/`) e **mostrar o texto no chat** (sem enviar).
3. Só depois do "ok" do diretor no chat: enviar uma vez pelo Telegram (`python -m src.jobs.telegram`) para ele ver no celular.

Commit: `feat(telegram): resumo do diretor curto, por caixa e com o que fazer`. Depois `git push`.
