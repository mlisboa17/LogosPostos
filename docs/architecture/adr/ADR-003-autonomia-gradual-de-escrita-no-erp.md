# ADR-003: Autonomia gradual do Logos para lançar no webPosto

## Status

**Accepted — 2026-10-10** (aprovado pelo sócio-diretor em sessão de trabalho; oficial após merge na `main` de `mlisboa17/LogosPostos`).
Até a Fase 2 ser liberada formalmente, a regra vigente continua: **somente leitura no ERP** (`WEBPOSTO_WRITES=0`).

## Context

- A conciliação depende de lançamentos corretos no webPosto. Casos reais (out/2026):
  - Casa Caiada 07/10: quatro vendas no cartão PagBank (soma R$ 179,45) lançadas como **um único cartão manual**.
  - Doze 05/10: PIX PagBank de R$ 1.000,00 lançado à mão com hora fictícia (01:00), sem venda.
  - VIP 05/10: o mesmo NSU de PIX Premmia usado em duas vendas.
  - "Desconto" Premmia (recebível) lançado em forma de pagamento não identificada até 09/10.
- Lançamento manual acontece por falta de tempo e de conferência detalhada. O diretor quer que o Logos passe a **lançar sozinho** o que tiver alta certeza, avisando, e ganhe autonomia com o tempo.
- A API oficial do webPosto tem rotas de escrita (ex.: `POST/PATCH/DELETE /INTEGRACAO/V1/CARTOES`, `MOVIMENTOS_CONTA`, `TITULOS_RECEBER`), hoje **bloqueadas** pelo projeto.
- As notas atuais do Logos (ex.: atribuição de frentista: valor 35 + hora 30 + troca de forma 20 + valor quebrado 15) são **pontuações heurísticas**, não probabilidades medidas.

## Decision

1. **Autonomia por fases, por tipo de lançamento** (cada tipo avança sozinho, nunca "tudo de uma vez"):

| Fase | Comportamento | Critério para avançar |
|---|---|---|
| **0 — Sombra** | Não escreve. Registra a "proposta de lançamento" (o que lançaria, nota, evidências) e depois compara com o que o gerente lançou/corrigiu. | ≥ 98% de acerto no tipo, em ≥ 2 semanas e ≥ 50 casos |
| **1 — Um toque** | Envia a proposta no Telegram/Painel; só lança após aprovação humana (diretor ou gerente da unidade). | ≥ 95% aprovadas sem correção, em ≥ 2 semanas |
| **2 — Automático com limite** | Lança sozinho e **avisa** na mensagem do dia ("Lancei N itens, R$ X"), com link para desfazer. | Decisão explícita do diretor por tipo |
| **3 — Ampliação** | Novos tipos entram sempre pela Fase 0. | — |

2. **Nota de certeza calibrada:** cada proposta tem uma nota de 0 a 100; o limiar de lançamento (ex.: 85/90) só vale depois de medido na Fase 0 ("das propostas com nota ≥ 90, quantas estavam certas"). Sem medição, a nota não autoriza nada.
3. **Travas permanentes** (valem em todas as fases):
   - Interruptor geral `LOGOS_ERP_ESCRITA` (padrão `0`): desligado, o Logos volta a só ler, imediatamente.
   - Liberação por tipo em configuração versionada (lista de tipos permitidos e fase de cada um).
   - Limites por lançamento e por dia, por unidade (valores iniciais definidos pelo diretor na liberação da Fase 2).
   - Nunca alterar caixa **consolidado**; nunca apagar registro sem antes gravar como recriá-lo.
   - Toda escrita gera registro de auditoria: o quê, por quê, nota, evidências, quem aprovou (ou "automático"), resposta do ERP e como desfazer.
   - Falha ou resposta inesperada do ERP → para aquele tipo na noite e avisa; não repete.
4. **Ordem sugerida de tipos** (do mais simples ao mais delicado): (a) desconto/forma Premmia sem lançamento correspondente; (b) cartão/PIX presente na adquirente e ausente no webPosto, com frentista atribuído com nota alta; (c) correção de data/hora de lançamento manual; (d) substituição de lançamento agregado por itens (ex.: 1 cartão manual → 4 cartões) — por último, pois apaga e recria.
5. Toda escrita aparece no resumo do Telegram e numa aba própria do Painel ("Lançamentos do Logos").

## Consequences

- O Logos passa a ter histórico objetivo de acerto antes de qualquer escrita real.
- A Fase 0 não muda nada no ERP e pode começar já (registro local em `data/`, fora do Git).
- Exige um módulo/porta de escrita isolado (`adapters/` de escrita separado dos de leitura), com testes que provem que, com o interruptor desligado, nenhuma chamada de escrita sai.
- Aumenta a responsabilidade operacional: lançamentos automáticos têm de ser reversíveis e rastreáveis.

## Alternatives considered

- **Lançar direto com limiar fixo (85/90) desde já:** rejeitado — a nota ainda não é medida; um erro em lote no ERP é pior do que nenhum lançamento.
- **Nunca escrever no ERP:** mantém o problema dos lançamentos manuais e agregados, que prejudica a conciliação.
- **Escrever só com aprovação humana para sempre:** seguro, mas não reduz o trabalho dos gerentes; fica como Fase 1.
