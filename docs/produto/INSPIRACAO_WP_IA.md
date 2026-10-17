# Inspiração: WP IA (Quality / webPosto) — só ideias de produto

Fonte: documentação **pública** da Quality no Confluence (páginas "WP IA", "o que é?", "Chat", "Agentes", "Tarefas"), lida em 17/10/2026. Nenhum código, prompt interno ou chamada do WP IA foi usado ou inspecionado. Decisão do diretor: **não contratar** (cobra créditos por uso); usar apenas como referência de produto.

## O que o WP IA oferece (resumo)

- **Agentes** em cartões: Fechamento de Caixa e Movimentação de Combustíveis. Cada cartão mostra filial e data, progresso (caixas processadas / total), resumo (automático × precisa de atenção), situação de cada caixa/produto, última execução e estado (Ocioso, Concluído, Precisa de atenção). Botões: Executar, Detalhes, Histórico, Configurar.
- **Configuração do agente:** orientações adicionais da rede (texto), "ver o que o agente vai ler", instruções finais, execução automática diária, quem recebe os avisos, máximo de registros por execução.
- **Chat** com perfis de IA e "habilidades" (KPI de postos, métricas financeiras, compliance, radar econômico). A própria documentação avisa: "confira nas telas antes de registrar uma conclusão".
- **Tarefas:** transformar uma pergunta em consulta agendada (dia/semana/mês, horário, e-mail), com histórico de execuções; datas relativas ("hoje") recalculadas a cada execução.

## Ideias para o LOGOS (sem custo por uso, com fontes externas)

| Ideia do WP IA | Como fica no LOGOS |
|---|---|
| Cartão por agente com estado e última execução | Painel "Rotinas do Logos": Fechamento de caixa, Cartões/PagBank, Premmia, PIX CNPJ, Mais Pagamentos, Cupons sem vínculo, Despesas, Títulos — cada uma com estado (OK / Precisa de atenção / Falhou / Bloqueada), última execução (run_id do PROD-SAFE-01) e botão Detalhes/Histórico |
| "Automático × precisa de atenção" | Separar no resumo o que bateu sozinho do que precisa do diretor (já é a linha "PRECISA DE VOCÊ") |
| "Ver o que o agente vai ler" | Mostrar as fontes e a cobertura de cada rotina no dia (quais fontes foram lidas, de quando, o que faltou) — reaproveitar o gate de frescor do PROD-SAFE-01 |
| Orientações da rede em texto | Regras de negócio já estão em `REGRAS_DE_NEGOCIO.md`; mostrar na tela as regras ativas de cada rotina (somente leitura) |
| Quem recebe os avisos | Destinatários por rotina/unidade no Telegram (hoje só o diretor) — ex.: gerente do posto recebe só a unidade dele |
| Tarefas agendadas por pergunta | Futuro: "relatórios agendados" pré-definidos (ex.: cupons sem vínculo da semana, toda segunda 07:00) — sem IA calculando; IA só redige |
| Aviso "confira nas telas" | Toda explicação do Logos traz a evidência (registros que compõem cada número) — modelo de evidência |

## Diferencial do LOGOS (a confirmar)

Pela documentação, o WP IA trabalha sobre os dados do webPosto. O LOGOS cruza com fontes que o webPosto não vê (EDI PagBank, Premmia, extratos OFX/PIX CNPJ, total Mais Pagamentos) — é isso que explica faltas como a do Doze 14/10/2026 (cartão R$ 34,75 e PIX R$ 139,35 cobrados no PagBank e lançados como dinheiro). Confirmar só pela tela "Ver o que o agente vai ler" do próprio cliente, se o diretor quiser.
