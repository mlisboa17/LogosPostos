# Prompt — SPRINT 16: Investigador IA das ocorrências de caixa (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. **Só comece depois da Sprint 15.1 commitada.** Somente leitura no ERP e nos portais; `.env` só via `load_dotenv`, nunca imprimir a chave; sem reescrever arquivos; testes **sem chamar a IA real** (provedor falso); nada pelo Telegram nesta sprint. Regras: ADR-003 (autonomia gradual — Fase 0), ADR-005 (IA sugere, não decide), RN-REDE-002 (nome + código do frentista).

## Decisões do diretor (11/10/2026)

- Usar IA para investigar as ocorrências e reduzir o trabalho do diretor: ele só aprova ou recusa.
- Provedor inicial: **Gemini** (`GEMINI_API_KEY` no `.env`; ping OK). Modelos: padrão **`gemini-2.5-flash`**; casos difíceis **`gemini-2.5-pro`**. Outro provedor virá depois → interface trocável.
- **Autorizado enviar à IA nomes de funcionários e valores.** Continua proibido enviar: CPF, nome de cliente, NSU/autorização completos (só 4 finais), chaves/senhas.

## Reaproveitar (não copiar o resto)

No repositório antigo (`C:\Users\mlisb\OneDrive\ProjetosAntigravy\LOGOS SPACE\Api_WebPosto\WebPosto_API\src\services\ai\`): `providers.py` (GeminiProvider pelo endpoint OpenAI-compatível `https://generativelanguage.googleapis.com/v1beta/openai`, Bearer, classificação de erros, `mask_secret`) e `config.py`/`router.py` (alias de modelo). **Ler e portar só o provedor + escolha de modelo**, adaptados, para `WebPosto_API/src/shared/ia/` (genérico, sem regra de negócio). Não trazer RAG, copiloto executivo nem ferramentas de outros assuntos. Confirmar o formato atual da API no código antigo antes de portar; não inventar endpoint.

## PARTE A — Infra de IA (genérica)

1. `src/shared/ia/provedor.py`: interface `ProvedorIA.completar(mensagens, ferramentas=None, modelo) -> RespostaIA` + `GeminiProvedor` (timeout 60 s, até 2 tentativas em erro transitório, log só com tipo/status e chave mascarada) + `ProvedorFalso` para testes.
2. Interruptor `LOGOS_IA_ATIVA` (padrão 0) e `LOGOS_IA_MODELO` / `LOGOS_IA_MODELO_FORTE` no `.env.example` (só nomes). Limite de custo: no máximo **N investigações por noite** (`LOGOS_IA_MAX_CASOS`, padrão 20) e de tokens por caso.

## PARTE B — O Investigador (cash_reconciliation)

`application/investigador_ia.py`:
1. **Entrada:** pendências **vermelhas abertas** e itens dos grupos 1/3 da Sprint 14 do dia (ordem: maior valor primeiro, até o limite).
2. **Ferramentas somente leitura** que a IA pode chamar (function calling), reaproveitando adapters existentes: `consultar_caixa(caixa)`, `consultar_venda(cupom|venda)`, `formas_pagamento_venda(venda)`, `cartoes_webposto(dia, valor?, hora?)`, `transacoes_pagbank(dia, valor?, terminal?)`, `premmia_dia(dia)`, `vales(dia)`, `abastecimentos(dia, frentista?|valor?|hora?)`, `historico_frentista(codigo, 30 dias)`. Cada ferramenta devolve dados já mascarados (NSU 4 finais, sem CPF/cliente). **Nenhuma ferramenta escreve.**
3. **Saída estruturada (Pydantic, validada):** `conclusao` (texto curto), `categoria` (ex.: cobranca_duplicada, troca_de_forma, lancamento_sem_lastro, falta_real, erro_de_hora, cartao_sem_detalhe, outro), `provas` (lista de fatos com fonte), `frentista` (nome + código ou "não identificado" + motivo), `acao_recomendada` (texto + De → Para quando houver), `mensagem_gerente` (pronta), `certeza` (0–100, autodeclarada), `modelo`, `tokens`. Resposta fora do formato → descartada e registrada.
4. **Guarda-corpos (ADR-005):** a IA **não** fecha pendência, não lança, não estorna, não muda regra. Toda conclusão vira **proposta** (`data/propostas_ia/`, fora do Git) com status `proposta` → `aceita pelo diretor` / `recusada` / `corrigida`, para medir acerto (ADR-003 Fase 0). Mostrar sempre "sugestão da IA".
5. Robô noturno: depois da conciliação, se `LOGOS_IA_ATIVA=1`, investigar os casos e anexar ao resultado do dia. Falha da IA = aviso, nunca falha do robô.

## PARTE C — Onde aparece

1. Tela de pendências e Conferência de Recebimentos: bloco "Investigação (IA)" no item, com conclusão, provas, ação e botões **Aceitar / Recusar / Corrigir** (só diretor) — grava no histórico.
2. Relatório do caixa do dia (Sprint 15/15.1): seção "Investigações da IA".
3. Telegram (resumo diário): para cada vermelho investigado, 1–2 linhas com a conclusão e a ação (envio real fica para quando o diretor ligar `LOGOS_IA_ATIVA`).

## PARTE D — Testes e validação

1. Testes com `ProvedorFalso` (respostas gravadas): formato válido aceito; inválido descartado; ferramentas recebem só leitura; mascaramento; limite de casos; falha do provedor = aviso.
2. **Validação real controlada (1 caso):** com `LOGOS_IA_ATIVA=1` só no comando, investigar o caso **Doze 10/10 — Visa R$ 250,07 às 19:12** com `gemini-2.5-flash`. **Esperado:** categoria `cobranca_duplicada`, provas (2 transações iguais em ~55 s no terminal …4038, uma venda cupom 10294 de Matheus Gomes da Silva 302036, sem estorno), ação "verificar/estornar a cobrança das 19:12". Mostrar no chat a resposta completa, tokens usados e tempo. Repetir com `gemini-2.5-pro` e comparar.
3. Rodar os testes de sempre.

Commits: `feat(ia): provedor Gemini genérico com interruptor e limites`, `feat(ia): investigador de ocorrências de caixa (somente leitura, sugere)`, `feat(ia): investigação na tela, relatório e resumo`. Depois `git push`.
