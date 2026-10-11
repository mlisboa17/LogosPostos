# Mensagem para o Gemini — participar da organização do LOGOS

(Copie tudo abaixo da linha e cole no Gemini. Em seguida, cole também o conteúdo de `docs/CONTEXTO_PARA_IAS.md`.)

---

Olá, Gemini. Você vai participar como **consultor** da organização do sistema LOGOS Auditoria. Quem decide é o diretor (Marcio). Quem revisa a arquitetura e transforma ideias em tarefas é o Claude (arquiteto). Quem escreve código é um agente por vez (VS Code, Cursor ou Antigravity), sempre a partir de uma "sprint" escrita. **Nesta etapa, não escreva código.** Responda só no formato pedido.

Logo abaixo eu colo o documento `CONTEXTO_PARA_IAS.md`, que explica o que o LOGOS é, o que já existe e as regras. Leia antes de responder.

## A situação

O repositório oficial (`C:\Projetos\LOGOS\LogosPostos`) tem **1.403 arquivos**, mas o LOGOS que funciona é pequeno:
- `WebPosto_API/src/modules/cash_reconciliation/` (conferência de caixa, cartões, Premmia, pendências, relatório do dia)
- `WebPosto_API/src/modules/commercial_performance/` (placar de metas por frentista)
- `WebPosto_API/src/modules/webposto_integration/` (leitura do webPosto)
- `WebPosto_API/src/jobs/` (robô das 03:00 e Telegram)
- telas `directorDashboard`, `cashAudit`, `conferenciaRecebimentos`, `pendencias`, `commercialScore`
- `STATUS.md` e `docs/` (regras, ADRs, prompts)

O resto é **legado** de tentativas anteriores com várias IAs: ~100 arquivos soltos na raiz (relatórios "PHASE6_COMPLETE", "CLAUDE_3.7_FINAL_REPORT", "GEMINI_2.0_INFRASTRUCTURE", "DIVISAO_PARALELA_3_IAS", vários README/COMECE_AQUI), infraestrutura não usada (Docker, nginx, Grafana, Prometheus, Mongo, Reflex), código antigo em `WebPosto_API/src` (`services/`, `presentation/`, `gateway/`, `crud.py`, `main-mlisboa17.py`…) e telas antigas (`accountsPayable`, `cashFlow`, `financeCenter`, `expenses`, `stock`, `sales`, `executiveDashboard`, `fuelExecutiveDashboard`, `dashboard`). Esse legado confunde as IAs, que o tratam como parte do sistema.

## Proposta do arquiteto (para você avaliar)

1. Mover todo o legado para `_legado/` (sem apagar nada; histórico preservado no Git).
2. Raiz limpa: `STATUS.md`, um único `README.md`, `docs/`, `WebPosto_API/`.
3. Menu do sistema só com: Painel do Diretor, Fechamento, Conferência de Recebimentos, Pendências, Placar.
4. Testes continuam passando (prova de que nada útil quebrou).
5. Regra permanente: "um agente por vez; nenhuma IA implementa plano que não esteja numa sprint em `docs/prompts/`".

## O que eu quero de você

Responda com:
1. **Concorda ou discorda** de cada um dos 5 itens, com o motivo em 1–2 linhas.
2. **Riscos** que você vê na limpeza (ex.: algo do legado que o sistema atual ainda importa).
3. **Até 3 ideias** de organização ou de produto que você considera mais valiosas para o diretor, **usando o formato de proposta do CONTEXTO_PARA_IAS.md** (IDEIA / PROBLEMA / O QUE JÁ EXISTE / DADOS NECESSÁRIOS / ESCREVE NO WEBPOSTO? / RISCOS / TAMANHO). Use apenas rotas que existem na API oficial do webPosto (ex.: `/INTEGRACAO/V1/MAPAS_DESEMPENHO`, `/INTEGRACAO/V1/ABASTECIMENTOS`, `/INTEGRACAO/V1/VENDAS`). Não invente rotas.
4. Sobre a sua ideia anterior de **ranking de produtividade dos frentistas**: reescreva-a como evolução do placar existente (`commercial_performance`), incluindo também **qualidade** (trocas de forma, faltas, cobranças duplicadas que o LOGOS já detecta).
