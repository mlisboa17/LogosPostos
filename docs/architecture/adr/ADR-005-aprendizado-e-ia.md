# ADR-005: Aprendizado por unidade/setor e IA como assistente

## Status

**Proposed — 11/10/2026** (debatido com o sócio-diretor: "o Logos terá que aprender pouco a pouco"; "talvez não seja a hora, mas deixe preparado"). Relaciona-se com ADR-003 (autonomia gradual de escrita) e ADR-004 (grupos, unidades e setores).

## Context

- Limites fixos em R$ não servem para a rede inteira (um valor aceitável num posto grande é alto num posto pequeno), e futuros donos não devem ter de configurar tudo à mão.
- A Conveniência 24h foi migrada recentemente para o webPosto: **não há histórico** para definir o "normal" dela. Toda unidade nova estará na mesma situação.
- Já existem fontes de aprendizado: histórico de pendências (justificada/aprovada/recusada), propostas de correção da Sprint 14 (proposta → executada/descartada) e conferência manual (conferido/não encontrado).
- O projeto antigo tem um "copiloto executivo" com IA; a IA pode ajudar a ler descrições, explicar ocorrências e responder perguntas.

## Decision

1. **Aprendizado do "normal" (estatístico, sem IA):** por unidade e setor, calcular faixas de referência (média e percentis dos últimos 3 meses, média móvel) para despesas por plano de contas, faltas, vales, trocas de forma, recebimentos manuais etc. Alertas de "fora do padrão" usam a régua da própria unidade/setor.
2. **Período de aprendizado:** unidade ou setor com menos de ~60–90 dias de dados usa as **regras padrão do grupo**, com alertas de "fora do padrão" desligados ou mais tolerantes; data de início = migração/cadastro. Vale para a Conveniência 24h e para unidades de novos donos.
3. **Aprendizado com as decisões:** toda resposta de responsável e toda decisão do diretor é guardada com **motivo, categoria, usuário e data** (histórico append-only). Isso é o "material de estudo": mede o acerto das regras e das propostas (ADR-003) e indica quais alertas costumam ser ruído.
4. **IA como assistente, com guarda-corpos:**
   - Pode: sugerir plano de contas a partir da descrição da despesa, redigir dossiês e resumos, responder perguntas do diretor sobre os dados, sugerir respostas/justificativas.
   - **Não pode:** decidir sozinha que algo é fraude, fechar ou aprovar pendência, lançar/alterar/excluir no webPosto, ou trocar regras.
   - Toda sugestão da IA fica registrada com a fonte dos dados e é medida como as demais propostas.
   - Dados enviados à IA: só o necessário; sem senhas; nomes e documentos apenas quando indispensáveis e permitidos pelo dono do grupo.
5. **Parâmetros proporcionais (preparados, não ativados):** limites de despesa como percentual de uma base da unidade/setor (média móvel do faturamento ou da margem), com teto absoluto em R$ e regras por plano de contas — valores definidos pelo diretor **depois** do levantamento dos últimos 3 meses.

## Consequences

- Novos donos começam com regras padrão e passam a ter régua própria com o tempo.
- Exige guardar desde já as decisões com motivo (parte já existe nas pendências e propostas).
- A IA melhora a leitura e a explicação sem virar ponto único de decisão.

## Alternatives considered

- **Limites fixos por unidade, definidos à mão:** simples, mas não escala para novos donos e fica desatualizado.
- **IA decidindo os alertas:** rápido, mas sem rastreabilidade e com risco de acusar injustamente; rejeitado.
