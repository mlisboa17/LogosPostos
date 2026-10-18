# STATUS — LOGOS Auditoria (atualizado em 17/10/2026)

## LOGOS MATCH v0.1.0 (18/10/2026) — app de bandeja entregue em código
Branch feature/logos-match (worktree LogosPostos-match), `WebPosto_API/apps/match/`: coleta Premmia/PagBank/webPosto, conciliação por posto, painel local, canais (toast/Telegram/e-mail), flags `--redefinir-admin` e `--apagar-credenciais`, PyInstaller onedir (`apps/match/build/`, smoke OK) e script Inno Setup.
**Pendente:** gerar o instalador .exe (falta o Inno Setup/`iscc` nesta máquina; rodar `apps/match/build/build.ps1`), verificação em máquina limpa (checklist no README do app), smoke manual da bandeja.

Repositório canônico: C:\Projetos\LOGOS\LogosPostos · branch feature/cash-audit-fechamento
Última entrega de código: Sprint 19 (A–D) · branch feature/cash-audit-fechamento, sem merge
PR a abrir: https://github.com/mlisboa17/LogosPostos/pull/new/feature/cash-audit-fechamento
Histórico de sprints: um prompt por sprint em docs/prompts/ (SPRINT_05 ... SPRINT_12, PREMMIA_00, TELEGRAM_00)

## SITUAÇÃO EM 17/10/2026 — Claude assume o desenvolvimento (leia primeiro)

**17/10 19:30 — RESOLVIDO:** diretor voltou as travas para 0. Reprocessados (sem Telegram) 15/10 e 16/10: 4 unidades
lidas, AUDIT_PARTIAL (esperado: PagBank 118508 credencial inválida; Mais/Cielo/Rede sem integração). Em 16/10 o
Premmia não coletou por "login já tentado" (regra de 1 login por noite) → reprocessar 16/10 depois do robô de 18/10.

**(histórico) Bloqueio urgente (ação do diretor):** `WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1` no `.env` desde o teste do
piloto de cartão (15/10). O robô das 03:00 **recusa rodar com escrita ligada** (gate PROD-SAFE) → **sem auditoria
nas noites de 16/10 e 17/10**. Voltar as duas para `0`; depois reprocessar 15–16/10.

**Direção aceita (revisão com ChatGPT/Gemini, 16–17/10):**
- Missão: prevenção na origem + auditoria confiável (somente leitura) + correção humana orientada.
- **Escrita no ERP congelada** (OFX, cartão, baixa, despesas, estoque). Piloto de cartão fica pronto e desligado.
- IA não calcula fatos financeiros; tudo sai do motor com teste. Casos reais viram golden cases (1º: Doze 14/10,
  686,71 = 34,75 + 139,35 + 500,00 + 12,61).
- Produção deve rodar versão aprovada fora da pasta de trabalho (PROD-RELEASE-01, ainda não feito).
- Processo: problema + critério de aceite → uma entrega ponta a ponta → validação → release. Sem micro-sprints.

**Fatos novos do diretor (17/10):**
- Maquininhas PagBank são **integradas**; às vezes a integração não reconhece a transação (cartão cobrado,
  venda fica como dinheiro, cupom sem vínculo). Analisar caso a caso → Sprint 20.
- Ecossistemas posto + loja (caixas e PDVs sempre separados): VIP (mesmo CNPJ, loja por centro de custo);
  Casa Caiada 5555 + Conveniência 24h 118508 (CNPJs diferentes); Doze 74014 + Conveniência Real (Linx — fora;
  a partir de nov/2026 vai para o CNPJ do posto no webPosto, por centro de custo).
- Mais Pagamentos: Doze = "Posto Abreu e Lima" (Asaas); Casa Caiada e VIP = Fiserv. PAGPIX desativada.
  Login da API dá 401 com as credenciais do webPosto → perguntar à Quality.

**Ordem de trabalho:**
1. Travas em 0 (diretor) e conferir o robô na noite seguinte (run PROD_SAFE_01 com AUDIT_COMPLETE).
2. PROD-RELEASE-01: aceitar a reconstrução semântica do estado local (é estado do robô, regenerado a cada noite)
   e isolar a produção numa pasta/versão aprovada, com testes isolados de tmp.
3. Sprint 20 — cupons sem vínculo (padrão por frentista/PDV/horário; somente leitura).
4. Mapeamento real (GET) das rotas V1 de conveniência e combustível (vendas/itens, estoque/extrato/contagem,
   compras, encerrante, tanque, LMC) em 1 posto + 1 loja.
5. Perguntas à Quality: POS integrado que falha (log, vincular depois), PIX no PDV, acesso Mais Pagamentos, débito OFX.

## MAIS-BANK-02 — fontes de liquidação/repasse; diagnóstico concluído — 17/10/2026
- Branch `feature/cash-audit-fechamento`. Relatório curto:
  [MAIS_BANK_02_SETTLEMENT_SOURCES.md](docs/validation/MAIS_BANK_02_SETTLEMENT_SOURCES.md).
  Histórico MAIS-BANK-01 preservado; aprovação recebida só para investigação
  read-only, não para migração, implementação da conciliação ou produção.
- Fontes: matriz anterior, código financeiro oficial, contratos locais
  Mais/webPosto e documentação pública oficial Asaas/Fiserv/Software Express.
  Só páginas públicas foram acessadas; nenhuma conta/API financeira real.
- Asaas documenta GET financialTransactions (extrato com valor/saldo e
  paymentId/transferId), pix/transactions (E2E/status/data/taxa/payment),
  transfers (destino/valor/líquido/taxa/E2E/status) e finance/balance.
  Capacidade do fornecedor documentada, mas acesso à conta do Doze/subconta
  BaaS e vínculo real Mais → crédito → repasse ainda não comprovados.
- Fiserv: Hub Pix existe, mas produto contratado, custodiante/PSP e canal de
  extrato/repasse das contas VIP/Casa Caiada não identificados. Não presumir
  que Hub/SiTef ou API de adquirência ofereça extrato dessa conta.
- Banco final: leitor OFX/proveniência oficiais reutilizáveis; uso histórico
  BB/Bradesco/Itaú em espécie não comprova crédito de repasse Asaas/Fiserv.
  Faltam banco/conta/titular de destino e extratos/detalhes das duas pontas.
- Riscos: DONE da origem não prova crédito final; E2E cliente difere do
  repasse; saldo fungível não identifica composição do lote; mesmo valor/data
  não cria vínculo. ERP conciliado/usaOfx continuam sem prova independente.
  API key comum não deve ser presumida restrita à leitura.
- Recomendação: primeiro pacote documental Doze/Asaas → banco tradicional,
  com extrato intermediário, composição/ID do repasse, taxas e crédito no
  destino. Identificar produto/custodiante Fiserv em paralelo; não aperfeiçoar
  cliente Mais isolado nem criar arquitetura paralela.
- Próxima etapa: obter mapa CNPJ/contas e amostras oficiais autorizadas para
  validação manual, marcando agrupamentos/parcelamentos/ambiguidades pendentes.
  Consulta real ou implementação exige nova aprovação específica.
- Nesta etapa só relatório MAIS-BANK-02 e STATUS.md alterados; sem acesso a
  .env, contas reais, operação financeira, código, migração, job, commit,
  push ou merge. Alterações preexistentes preservadas. Parado no diagnóstico.

## MAIS-BANK-01 — investigação local concluída; implementação não autorizada — 17/10/2026
- Matriz de fontes, campos financeiros, evidências, lacunas e componentes
  reutilizáveis em [MAIS_BANK_01_SOURCE_GAP_MATRIX.md](docs/validation/MAIS_BANK_01_SOURCE_GAP_MATRIX.md).
- Comparados o projeto antigo do OneDrive e o oficial. Não foi encontrada
  cadeia comprovada por pagamento: Mais → crédito na conta Asaas/Fiserv →
  repasse identificado → crédito na conta bancária de destino.
- Cliente Mais antigo usa rotas não presentes no contrato local e fallback
  sandbox; serviço ainda pode preencher total ERP com baseline da adquirente.
  Não portar como integração real. A esteira de quatro vias procura método
  PIX que esse cliente não implementa.
- OpenAPI Mais oficial local oferece lista/detalhe de transações com E2E,
  bruto/pago/líquido/taxa e consultas de PIX de saída. Não foram encontrados
  ali extrato/saldo de conta ou listagem de repasses. ASAAS/FISERV no enum de
  última confirmação não comprovam consulta direta dessas contas.
- Mantido o bloqueio histórico de autenticação: 401 de 11/10 já registrado
  abaixo; não repetir sem credencial nova e autorização. Total Mais oficial
  permanece declaração humana, não coleta da API nem comprovação bancária.
- webPosto documenta GET V1/MOVIMENTOS_CONTA, V2/TRANSFERENCIAS_BANCARIAS e
  V1/CONTAS, além de POST V1/OFXS. Amostra antiga liga transferência a movimento
  do próprio ERP; não são evidências independentes. Não foi comprovada leitura
  segregada/rastreável de movimentos efetivamente importados do banco.
- usaOfx, conciliado e saldo ERP não certificam banco. O modelo de entrada OFX
  tem extratoExterno/dataCredito, mas o retorno de movimentos não os expõe
  como tais. Histórico de importação da conta 86188 mantém incidente de
  débitos errados; aceite HTTP não comprova sinal nem crédito efetivo.
- Reaproveitáveis sob revisão/aprovação: classificação Mais antiga, padrões
  OFX e comparação de lotes; priorizar leitor OFX e PagBank EDI já oficiais.
  Falta validar contas/titulares, crédito recebedor, referência de repasse,
  taxas e crédito no destino com fontes bancárias independentes.
- Apenas este relatório e STATUS.md alterados. Nenhuma chamada externa,
  leitura de .env, execução de integração/teste de aplicação, migração,
  escrita ERP, mudança de trava, commit, push ou deploy. Probe preexistente
  preservado. Próxima etapa somente com aprovação humana explícita.

## PROD-RELEASE-01 — PARADO no pré-check — 17/10/2026
- Branch `feature/cash-audit-fechamento`, HEAD `76cd8e2`; nenhuma implementação
  de release iniciada. Evidências em
  [PROD_RELEASE_01_VALIDATION.md](docs/validation/PROD_RELEASE_01_VALIDATION.md).
- Contagem reconciliada: 19 arquivos do PROD-SAFE-01 + 2 relatórios anteriores
  = 21 acumulados; probe preexistente excluído. `git diff --stat` sem novos
  mostra 16 rastreados. Inventário dos 21 registrado no relatório.
- Bloqueio: restauração anterior de estado/MD foi reconstrução semântica,
  não há baseline integral suficiente para provar bytes/metadados originais.
  Ressalva acrescentada ao relatório anterior, sem apagar histórico.
- Estado atual já foi atualizado pela tarefa de 17/10 às 03:00, referência
  16/10, auditoria falha e sem unidades; não foi sobrescrito. Log preexistente
  mostra bloqueio de configuração e envio ok; não foi execução desta tarefa.
- Teste CLI específico está em tmp, mas não existe guarda persistente geral
  contra gravações fora de temporários; runner isolado anterior foi removido.
  Garantia para testes futuros ainda não atendida; nenhum teste executado aqui.
- Produção continua no workspace, Python global; tarefa apenas consultada.
  Destino production inexistente; sem versão/tag proposta ou aprovada,
  manifesto, venv, deploy, health check ou rollback implementados.
- Próximo passo: recuperar backup autenticado ou obter decisão explícita
  sobre aceitar a reconstrução semântica; preparar isolamento reproduzível
  de testes antes de retomar release. Mudança real da tarefa depende de
  aprovação humana explícita e permanece não realizada.
- Apenas documentação nesta tarefa. Nenhum ERP write, integração externa,
  Telegram real, browser, commit, push ou merge; `.env` não lido/impresso/
  alterado, nenhuma trava modificada, escrita não habilitada.

## PROD-SAFE-01 — run integrity e publicação fail-closed — 16/10/2026
- Branch `feature/cash-audit-fechamento`; sem commit, push, merge ou deploy.
  Validação em [PROD_SAFE_01_RUN_INTEGRITY_VALIDATION.md](docs/validation/PROD_SAFE_01_RUN_INTEGRITY_VALIDATION.md).
- Causa raiz: envio desacoplado do resultado da coleta e releitura de snapshot
  do dia sem provar run/frescor. Incidente de 16/10 foi barreira local de
  configuração; não se comprovou relatório normal com números antigos.
- UUID criado antes das travas, propagado e persistido atomicamente por run,
  com início/fim, referência, estados de fonte/auditoria e motivo seguro.
  Legados seguem legíveis, mas não provam coleta atual.
- Gate valida run, data, timestamps e cobertura antes do resumo e do Telegram.
  FAILED/BLOCKED/STALE/NOT_COLLECTED obrigatórios impedem publicação financeira.
  EMPTY_VALID exige consulta bem-sucedida e contrato que permita vazio.
  Incompleto gera só aviso operacional, sem saldos, zeros financeiros ou XLSX.
- Fontes obrigatórias/degradáveis documentadas por fluxo; Premmia/Mais/OFX
  não viraram obrigações globais. Premmia antigo mantém timestamp e é omitido
  financeiramente; Mais preserva declaração original; OFX preserva hashes/
  cobertura. Placar agendado força coleta viva, sem fallback para cache.
- WEBPOSTO_WRITES deve ser exatamente `0`; configuração ausente/inválida e
  modo automático ativo bloqueiam com diagnóstico. Agendado não chama piloto
  automático/propostas de escrita; piloto manual não foi habilitado/alterado.
  Bootstrap absoluto via load_dotenv preservado; `.env` oficial não editado.
- AUDIT_COMPLETE/PARTIAL/FAILED separados de delivery das mensagens/documento;
  entrega de alerta não promove auditoria. Reenvio de MD tem rótulo histórico.
  Falha técnica/financeira retorna 1; entrega falha não rebaixa audit status.
- Testes ampliados offline: 611 aprovados, zero tentativas externas/browser;
  rodada final focada: 94 aprovados (sobreposta, não somar). Mypy: 11
  arquivos funcionais sem erros. Golden sintético inalterado:
  686,71 = 34,75 + 139,35 + 500,00 + 12,61. Frontend não alterado.
- Teste CLI legado foi isolado em tmp após gravação local de estado/MD de
  teste; estado anterior restaurado da evidência e MD vazio reconstituído.
  Nenhum lançamento, integração real ou Telegram real durante a validação.
- Riscos: freshness remota é prova de consulta corrente, não certificação
  interna do fornecedor; Mais/OFX continuam fontes locais explícitas, sem TTL
  inventado. Histórico e piloto manual fora do gate noturno. Produção ainda
  NÃO isolada; tarefa continua apontando ao workspace, sem alteração.
- Escrita segue congelada no job; nenhum raw financeiro/segredo copiado ao Git.
  Próximo passo recomendado: **PROD-RELEASE-01**.

## PROD-SAFE-00 — diagnóstico do job/frescor — 16/10/2026
- Branch `feature/cash-audit-fechamento`, base `76cd8e2`; diagnóstico concluído
  em [PROD_SAFE_00_JOB_FRESHNESS_DIAGNOSIS.md](docs/validation/PROD_SAFE_00_JOB_FRESHNESS_DIAGNOSIS.md).
- Inspecionados: composição `src/jobs/noturno.py`, wrapper/job de caixa,
  fechamento, recebimentos/conciliação, fontes da falta, persistência/saúde,
  Premmia, OFX, Mais, placar/cache, renderizadores, painel, utilitário Telegram,
  testes existentes, registrador e tarefa Windows, log/estado/ledger locais.
- Diagnóstico: **fail-closed na barreira de coleta; fail-open na composição
  resumo/envio quanto à completude e freshness**. Não é prova de escrita
  financeira fail-open. `main` tenta envio após retorno 1; exceção que escapa
  da coleta interrompe antes. Saída 0 também permite fontes degradadas.
- Falha de 16/10/2026: bloqueio local às 03:00 por condição
  `WEBPOSTO_WRITES != "0"` no modo não automático; não foi erro de fornecedor.
  Task iniciou 03:00:01 e terminou com resultado 1; ledger registra envio ok
  às 03:00:45. Não se consultou o valor/origem da variável.
- Evidência refina o risco: não havia snapshots de 15/10 e o MD local avisa
  conferência não realizada nas quatro unidades. Não se comprovou envio de
  relatório financeiro normal com dados antigos nesse episódio. O código,
  porém, aceita snapshot anterior do MESMO dia sem conferir idade/execução.
  Não troca automaticamente o dia 15 pelo 14 no Telegram.
- Gaps: sem gate de fontes obrigatórias/atuais antes do resumo ou Telegram;
  sem estados completos por fonte/auditoria. Frescor parcial (referência,
  proveniência, coleta Premmia, declaração Mais), não prova conjunta.
  Planilha pode zerar campos sem fechamento; ledger ok significa entrega de
  mensagens, não sucesso documental nem da auditoria.
- Recomendação mínima, NÃO implementada: gate e diagnóstico da tentativa atual,
  resultado/run ligado ao envio, publicar apenas aviso operacional quando
  incompleto; definir critérios de validade por fonte sem inventar TTL/regra.
  Só testar código de saída 0 é insuficiente por causa das degradações.
- Produção continua no workspace com Python global e logon Interactive.
  Isolamento futuro exige release/venv, ação/cwd aprovados, dados/segredos/logs
  preservados fora da release e smoke/rollback; nada movido ou reconfigurado.
- Nenhuma alteração funcional, execução de job/teste funcional, integração,
  write operacional/financeiro ou envio. `.env` não lido/alterado; nenhum raw
  financeiro/segredo copiado. Sem commit, push ou merge.
- Próximo passo sugerido: aprovar correção mínima do gate/frescor com testes
  offline de bloqueio, snapshot antigo, vazio válido e fonte degradada;
  depois planejar cutover isolado sem mudar regras financeiras.

## Auditoria de capacidades atuais — 16/10/2026 (somente leitura)
- Branch: `feature/cash-audit-fechamento`, base `76cd8e2`; sem merge.
  Entrega: [LOGOS_CURRENT_CAPABILITY_AUDIT.md](docs/validation/LOGOS_CURRENT_CAPABILITY_AUDIT.md).
  Apenas documentação; nenhuma correção/refatoração ou implementação funcional.
- Escopo analisado: Python versionados, entrypoints/routers, clientes/adapters,
  testes, configuração de unidades, persistência, scripts e tarefa Windows.
  Comparação estática com OpenAPI de 06/10/2026 e 23 entradas do registry antigo,
  usado só como catálogo, sem importar/copiar seu código ou políticas.
- Inventário: 200 declarações de rota em 30 arquivos (não simultaneamente
  publicadas), 101 na montagem principal, 176 chamadas com path /INTEGRACAO literal,
  156 paths na OpenAPI. Limites do AST e aliases detalhados no relatório.
- Capacidades com evidência operacional anterior: auditoria de caixa, contexto
  de vendas/cartões PagBank, parser OFX, portal Premmia nos casos conferidos,
  placar, comparação Mais via CLI e explicação da falta da Sprint 19.
  Isso não certifica todos os endpoints HTTP nem disponibilidade atual.
- Implementadas sem validação operacional completa: inclusão/compensação e nova
  tentativa do piloto, casamento positivo PIX CNPJ, receptores novos,
  fila Gemini/comprovantes ponta a ponta e integrações analíticas legadas.
  Cielo/Rede e coleta automática Mais não têm adapter de adquirente ativo.
- Achado operacional prioritário: tarefa real das 03:00 roda do workspace
  `C:\Projetos\LOGOS\LogosPostos\WebPosto_API`, não de release isolada.
  Argumento registrado usa módulo antigo que encaminha à composição nova.
  Em 16/10/2026: LastTaskResult=1; log mostra coleta bloqueada e marcador de envio
  Telegram. O código tenta envio mesmo após retorno de falha; envio ok não
  comprova dado fresco. Nenhuma tarefa foi alterada/reexecutada nesta auditoria.
- Golden case 14/10: teste sintético afirma a tabela 34,75 + 139,35 + 500,00 +
  12,61 = 686,71. Snapshot antigo persistido do mesmo dia não contém as novas
  fontes/campos e representa outro instante; não é replay integral desse resultado.
- Gaps reais: release/frescor/proveniência reproduzível; integração e validação V1
  de contagem/extrato/itens de entrada para conveniência e de equipamento/
  medição/descarga para combustível. A OpenAPI já documenta essas fontes.
- Riscos: produção no checkout, resumo após coleta bloqueada, evidência
  sobrescrita, escopos de extrato, versões de clientes e retries de escrita.
  Travas cartão/OFX não constituem congelamento universal dos proxies/wrappers.
- Decisões NÃO tomadas: arquitetura nova, deploy, correção, mudança de flags,
  autorização de lançamento, cadastro de tarefa, commit/push ou merge.
  Pendências/recomendações não foram implementadas.
- Próximo passo recomendado: isolar release aprovada e comprovar saúde/frescor
  do job das 03:00, reusando entrypoints/proveniência/testes; formalizar replay
  anonimizado do golden case antes de ampliar conveniência/combustível.
- Nenhum request externo, envio Telegram/Gemini, browser ou write operacional/
  financeiro executado. `.env` não foi lido, impresso ou editado; nenhum raw real
  foi copiado ao Git. Histórico 824 backend + 72 frontend da Sprint 19 preservado;
  não reexecutado nesta auditoria exclusivamente documental.

## Sprint 19 — Parte A
- Relatório, tela e resumo compartilham a decomposição da diferença de dinheiro
  por caixa, com fonte, venda, nome/código do frentista, correção e residual
  "Sem explicação". Candidatos ambíguos não explicam faltas.
- Vínculo ao caixa vem da venda oficial; não se distribui total entre caixas
  por suposição. O botão Lançar abre a revisão do piloto 18b, nunca confirma
  pelo relatório. Nenhum lançamento nem envio Telegram nesta sprint.

## Sprint 19 — Parte D e validação real
- Nova tentativa do mesmo NSU apenas com `--confirmar --nsu ... --nova-tentativa`,
  novo ok do diretor e todas as tentativas anteriores resolvidas como `nao_entrou`.
  Cada tentativa tem ação distinta, referência à anterior e reserva bruta própria;
  pendência não resolvida, NSU já existente e limites continuam bloqueando.
- PIX/BACEN usa administradora PIX PagBank ativa e única da lista oficial. Sem
  administradora ou com empate: conferir/lançar à mão. NSU e autorização continuam
  obrigatórios: não são inventados nem substituídos por outro identificador.
- Validação real Doze 14/10/2026: falta R$ 686,71 (não consolidado), Mastercard
  R$ 34,75 + PIX da maquininha R$ 139,35 + Mais Pagamentos R$ 500,00 +
  sem explicação R$ 12,61. Portal declarado R$ 10.741,86 × Transf. Crédito R$ 10.241,86.
- Extrato PIX CNPJ coberto: 0 clientes, 6 créditos de grupo/fornecedores excluídos.
  Administradora PIX PAGBANK existe, mas o PIX BACEN não informa NSU/autorização:
  a tabela orienta conferência manual, sem oferecer lançamento incompleto.
- Duas validações reais restritas por transporte a GET: 65 consultas cada; nenhum
  POST/DELETE, nenhuma coleta de portal Premmia e nenhum envio ao Telegram.
  `.env` somente via `load_dotenv`, sem impressão ou alteração.
- CLI real `src.jobs.mais_pagamentos_total --unidade 74014 --dia 14/10/2026 --total 10741,86`:
  saída 0, 14 GET, total salvo apenas localmente; nenhuma escrita no ERP/envio.
- Testes finais: 824 backend (`tests/unit` + `tests/services`) e 72 frontend aprovados.
  Avisos preexistentes de depreciação/JWT e módulo JavaScript mantidos.

## Sprint 18b — implementada; primeiro lançamento NÃO autorizado
- Prévia, painel e Telegram usam a mesma explicação em português simples e o mesmo
  serviço de confirmação/desfazer. Lançar/Não lançar só para diretor; gerente apenas lê.
- Cartão PagBank ausente, abastecimento único de mesmo valor em dinheiro, nota ≥ 90,
  caixa não consolidado/bloqueado, administradora unívoca, R$ 300/cartão e R$ 1.000/dia/posto.
- `python -m src.jobs.lancar_cartao --unidade 74014 --dia 14/10/2026` é somente prévia;
  confirmar exige `--confirmar --nsu <completo>`, duas travas físicas e novo ok do diretor.
- POST 201 não é sucesso: reconsulta NSU/venda/caixa/valor e dinheiro/cartão apurados.
  Se não confirmar, desfaz; falha/ambiguidade bloqueia repetição e exige conferência na tela.
- Auditoria persistente e trava por posto; botão Desfazer na aba Lançamentos do Logos.
  Resumo diário conta apenas lançamentos confirmados.
- Telegram: envio explícito por `src.jobs.telegram --propostas-cartao --unidade ... --dia ...`;
  conversa privada configurada via TELEGRAM_DIRETOR_CHAT_ID/USER_ID; botão expira em 24h.
  Usar um único consumidor do bot (`--ouvir-cartoes` ou o worker de comprovantes).
- Automático preparado no robô e DESLIGADO no exemplo (`LOGOS_CARTAO_AUTOMATICO=0`).
  Não editaram o `.env`, não houve envio Telegram nem lançamento real nesta sprint.
- O teste real do Mastercard R$ 34,75 de Ailton, Doze 14/10, continua aguardando
  aprovação específica do diretor e conferência das travas (WEBPOSTO_WRITES sem duplicata).
  Após qualquer teste real, voltar WEBPOSTO_WRITES e LOGOS_ERP_ESCRITA para 0.
- Validação: 445 testes da conciliação aprovados (48 regressões novas), 70 testes
  frontend e 5 do adaptador Telegram; nenhuma falha. Avisos preexistentes de
  depreciação/JWT/coverage mantidos. Texto do Ailton gerado pelo serviço real em
  prévia com somente GET, sem confirmar e sem criar tickets Telegram.

## Pronto
- Auditoria de fechamento FECHAMENTO_V4: quebra, falta sem desconto, caixa parado, despesas do caixa, reincidência;
  sangria sem conta da Conveniência 24h (repasse ao Casa Caiada) e do Casa Caiada (cofre) é informativa
- Recebimentos PagBank CARTOES_V2 (Doze 74014 e Casa Caiada 5555) com atribuição ao frentista e grupos prováveis
- Login por perfil (diretor/gerente/auditor), Painel do Diretor, placar de metas (VIP com metas de out/2026)
- Fila de pendências: vermelho individual, laranja agrupado por caixa/dia, prazo (vermelho 2 dias, laranja 5) e VENCIDAS
- Robô noturno agendado (03:00, tarefa "LOGOS - Auditoria de Caixa", modo -SemAdmin); credencial inválida = aviso, não falha
- Resumo diário pelo Telegram (bot @Weblogosbot, só o diretor): mensagem por filial com nomes + planilha .xlsx;
  TELEGRAM_ENVIO=1 desde 10/10/2026 (envio automático após o robô)
- Datas no padrão Brasil (America/Recife)
- **Sprint BAIXA_00 (Parte A — somente leitura):** identificação de títulos a pagar já quitados no banco por extrato (`titulos_pagos_sem_baixa.py`, `src/jobs/baixar_titulos.py`). Resolução de contas via `units.json` (BB 86248, PagBank 86188), deduplicação por FITID e detecção de pagamentos agrupados (tolerância ±15% no mês anterior).
- **Sprint DESPESAS_00 (Parte A & 00.1 — somente leitura):** identificação de despesas avulsas pagas na rua sem lançamento no ERP (`despesas_sem_lancamento.py`, `src/jobs/despesas_avulsas.py`). Deduplicação por FITID, filtro de grupo/aplicações/tarifas, reconhecimento de baixas agrupadas (`pagamento[]`), e reaproveitamento do casamento da BAIXA_00 (débito com título em aberto vai para "tem título em aberto — usar baixa", nunca avulso). Sugestão de plano/centro de custo e exportação XLSX.
- **Sprint DESPESAS_00 (Parte B — fila local, somente leitura no webPosto):** recepção de comprovantes pelo Telegram (`receber_comprovantes.py`) com escuta segura por whitelist do diretor (`TELEGRAM_CHAT_IDS`). Leitura multimodal via Gemini (`gemini_comprovantes.py`) para fotos, PDFs e áudios do diretor com transcrição e extração de entidades. Casamento com débitos dos extratos OFX (`processar_comprovante.py`), resolução de unidade pagadora, sugestão de plano de contas e centro de custo, e persistência em fila local `data/despesas_avulsas/fila.json` (status: "pronto para lançar", "a classificar", "sem extrato ainda"). Resposta interativa e amigável formatada para o bot Telegram. Zero gravações no webPosto.

## INCIDENTE EM ABERTO COM A QUALITY (11/10/2026) — OFX PagBank Doze 10/10 importado com débitos como crédito
- 11/10/2026: o DIRETOR EXCLUIU pela tela do webPosto os registros OFX de 10/10 da conta 86188 (sem Quality).
- Sprint 17B enviou pela API /V1/OFXS (conta 86188 PAGBANK DOZE FILIAL, dia 10/10/2026) 507 lançamentos: webPosto aceitou
  (201), mas a tela de conciliação mostrou Créditos R$ 132.804,13 e Débitos R$ 0,00 → os 8 débitos (R$ 64.847,35) entraram
  como crédito ("tipo":"Débito" não reconhecido). Os 499 créditos estão certos.
- **Sprint 17B.1 CONCLUÍDA — barreira reforçada e blindada:**
  1. Travas lidas EXCLUSIVAMENTE do arquivo `.env` via `dotenv_values` (ignora variáveis de processo, recusa duplicidade).
  2. Débito BLOQUEADO até confirmação formal pela Quality (`formato_tipo_debito_confirmado`, padrão ausente). Qualquer lote com débito é estritamente recusado.
  3. Anti-reenvio por `(cdConta, dia)` independentemente do arquivo/hash. Dia 10/10/2026 da conta 86188 marcado como "importado com débitos errados — aguardando correção" e bloqueado até liberação explícita auditada (`--liberar-dia`).
  4. Sucesso declarado apenas após conferência humana na tela de conciliação (`ENVIADO — CONFERIR NA TELA` e `--confirmar-conferencia`).
  5. Removidos atalhos fora do padrão (`WebPosto_API/adapters/` e `src/jobs/` na raiz).
- **Incidente permanece aberto** aguardando resposta da Quality sobre como débitos são reconhecidos na rota `POST /INTEGRACAO/V1/OFXS`. Nenhum envio contendo débito é autorizado.

## Ponto de parada (11/10/2026 ~15:30) — pausa pedida pelo diretor
- Sprints 15 (relatório do caixa do dia), 15.1 (dados atuais, status ✅/❌/⏳, Atualizar agora, duplicidade, Cartão POS,
  Amex = PagBank) e 15.2 (total do status sem dupla contagem) CONCLUÍDAS: 395e061, 4ff7673, 52f3b5e.
- Casos reais 10/10: Doze — cobrança em duplicidade Visa R$ 250,07 (19:12, sem estorno), falta R$ 34,80 (consolidado);
  Casa Caiada — tudo bate, falta R$ 14,71. 09/10: diretor lançou 4 cartões à mão no Casa Caiada → dinheiro esperado caiu
  R$ 128,75 (incluir cartão NÃO conta em dobro); falta final R$ 6,59, consolidado.
- Sangria Alberis 05/10 R$ 267,00 "Banco 24h": ficou no cofre (resposta do diretor) → corrigir a conta; regra nova de
  valor impossível no Banco 24h (cédulas 20/50/100/200) na Sprint 17.
- Prévia da tela nova (local, com nomes): WebPosto_API/data/previas/conferencia_do_dia.html — aguardando ajustes do diretor.
- **Sprint 18a CONCLUÍDA — porta de escrita de cartão isolada, desligada, com prévia e auditoria:**
  1. Porta isolada `POST /INTEGRACAO/V1/CARTOES` e `DELETE /INTEGRACAO/V1/CARTOES/{id}` (para desfazer) em `src/modules/cash_reconciliation/adapters/webposto_escrita_cartao.py`.
  2. Campos estritamente conforme a spec oficial da OpenAPI (`IncluirAlterarCartaoDto`). Sem PATCH.
  3. Dupla trava exigida EXCLUSIVAMENTE do arquivo `.env` físico via `dotenv_values` (`WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1`). Ignora variáveis de processo e recusa duplicatas.
  4. Resolução unívoca de administradora (Amex Doze e Casa Caiada = PagBank; sem ambiguidade).
  5. Montagem estrita a partir de proposta (exige NSU completo, autorização, administradora, venda, caixa, frentista, valor, data; falta de qualquer um recusa montagem).
  6. CLI `python -m src.jobs.lancar_cartao --unidade <cod> --dia dd/mm/aaaa` lista prévia elegível; `--confirmar` sempre recusa com "piloto não liberado (Sprint 18b)".
  7. Auditoria append-only em `data/lancamentos_logos/<empresa>/` (fora do Git) registrando o quê, evidências, autorização, payload sanitizado, resposta e como desfazer.
  8. Bateria completa: 330 testes passando (19 novos testes específicos de barreira de escrita de cartão).
- PRÓXIMO: Sprint 18b (1º lançamento controlado do piloto com o diretor acompanhando).
## Em andamento
- SPRINT_12 CARTOES_V3 (prompt pronto, não executado): mesmo NSU com valor diferente; cancelamentos do EDI
- PREMMIA_00 (VIP, 01 a 09/10/2026): login OK sem CAPTCHA (3 vezes); filtro de datas pela URL OK; tentativa 3 parou
  esperando a tabela. Próxima: exportar o .xlsx sem exigir a tabela (seção "Exportação XLSX" do prompt).
  Script: WebPosto_API/scripts/probe_premmia_portal.py (sem commit).
  ATUALIZAÇÃO 21:06: tentativa 4 OK — .xlsx exportado (89 pagamentos, 01 a 09/10). Crédito bate 100%.
  "Código Transação" do portal = nsu do V1/CARTOES (casamento por NSU funciona no Premmia).
  Achado: VIP 05/10 o mesmo NSU de PIX Premmia R$ 30 lançado em 2 vendas (23:04 e 23:09) → regra NSU repetido na CARTOES_V3.
  PREMMIA_01 (porte): arquivo por posto e mês, ex. data/premmia/postovip_10_2026.xlsx, acrescentando os dias coletados
  (decisão do diretor 10/10/2026); sem cópias por dia.
  "Desconto" do Premmia é RECEBÍVEL (a Vibra paga ao posto) — conciliar como as demais formas. Em 10/10/2026 o diretor
  cadastrou essa forma de recebimento no webPosto das filiais que não tinham; lançamentos até 09/10 seguem na forma antiga.

## Aguardando o diretor
1. Revisar e abrir o PR (descrição pronta em docs/status/PR_feature_cash_audit.md); merge na main só após revisão
2. Fornecedores: credencial PagBank da Conveniência 24h, documentação da Mais Pagamentos, EDI da Rede, credencial Cielo;
   perguntar à Vibra se há API/EDI do Premmia
3. Opcional: apagar a pendência sintética da unidade 321 do banco real

## Backlog (sprints futuras)
- METAS_02 — Metas de out/2026 do Doze e do Casa Caiada (adiado pelo diretor; aguarda Bronze/Prata/Ouro)
- Telegram: trocar a planilha (pequena no celular) por algo mais legível; tirar código interno do plano de contas;
  faltas confirmadas x provisórias; DESPESAS_V1 (valor alto, plano incompatível, acima da média)
- Integrações Mais Pagamentos, Rede, Cielo e PagBank Conv 24h (dependem dos fornecedores)
- MAIS_01 — Mais Pagamentos (PIX do VIP; no webPosto "Transferência Bancária"). Já existe no branch
  resgate/conciliacao-4-vias o cliente do Codex (src/gateway/mais_pagamentos_client.py): endpoints /v1/transactions e
  /v1/settlements e cabeçalhos X-Account-ID/X-Account-Key ADIVINHADOS (deram 401 em 07/10) e, pior, devolve dados
  FICTÍCIOS ("sandbox") quando falha → NÃO portar. Aproveitável: mais_pagamento_mapping.py (classificação PIX × transferência
  no webPosto, sem I/O). Credenciais por unidade já no .env (MAIS_PAGAMENTOS_ACCOUNT_ID_/KEY_<emp>). Bloqueio: documentação
  oficial da API ou exportação (portal/arquivo) da Mais Pagamentos. Mesmo padrão do Premmia se houver portal.
  ATUALIZAÇÃO 11/10/2026: API oficial pública encontrada (https://api.maispagamentos.com.br/webjars/swagger-ui.html;
  cópia em docs/external/maispagamentos/openapi_integracao_2026-10-11.json). Login: POST /usuarios/v1/login-integracao,
  form-urlencoded, Authorization Basic base64(id:chave), grant_type=client_credentials, scope=events → access_token.
  Transações: GET /transacoes/v1/{conta}?data-inicial&data-final&tipo-transacao=imediata (Bearer). Teste com as credenciais
  do VIP no .env: protocolo aceito, resposta "Credenciais incorretas" (401) → pedir à Mais Pagamentos o USUÁRIO DE
  INTEGRAÇÃO (client_id/secret), o scope correto e o código da "conta". Não repetir tentativas (risco de bloqueio).
  11/10/2026: 7 tentativas de login, todas 401 "Credenciais incorretas" (VIP normal/invertida/X-API-Key, genérica,
  Casa Caiada e as 2 combinações cruzadas genérica × 5555). NÃO TESTAR DE NOVO sem credencial nova gerada no painel
  da Mais Pagamentos (o diretor suspeita que a chave é regenerada).
- EXTRATOS_01 (adiante, decisão do diretor 11/10/2026) — captura automática dos extratos bancários/PagBank que chegam
  por e-mail, para confirmar recebimentos fora das maquininhas. Primeiro caso: PIX CNPJ do Doze (PIX pela chave do posto,
  direto na conta PagBank, sem maquininha — não aparece no EDI transacional). Doze 01–09/10: 7 lançamentos manuais
  · R$ 2.480,41 sem conferência hoje. Ver RN-CARTAO-009.
- Sprint 13 / 13.1 concluídas (commits 00c28d1, 8480d35): Premmia Casa Caiada 139 · R$ 14.909,55 conferidos, sobram
  2 · R$ 140,00; Doze 208 · R$ 16.582,25 conferidos, sobram 2 · R$ 14,00.
- 28 snapshots antigos ainda versionados; arquivar a pasta antiga do OneDrive

## Sprint 19 — Parte B
PIX CNPJ pelo OFX PagBank da conta da unidade, FITID único, exclusão de grupo/Vibra e
casamento um a um por valor/hora; cobertura e pendências persistidas no relatório.
Nenhuma escrita no webPosto e nenhum envio ao Telegram.

## Sprint 19 — Parte C
Total Mais Pagamentos declarado pelo diretor em JSON local atômico por unidade/dia;
CLI `src.jobs.mais_pagamentos_total` e entrada privada do mesmo diretor nos receptores
Telegram existentes (não executar dois pollings ao mesmo tempo).
Comparação apenas com `transfBanc` (Transf. Crédito), sem somar transferência débito.
Detalhe valor/hora procura venda em dinheiro; total sem detalhe não inventa frentista.
Nesta sprint os receptores não foram iniciados e nenhum envio foi realizado.

## Decisões fixas
Não trocar CONSUMER_TOKEN/ADMIN_TOKEN · conciliação de depósitos fora do escopo · somente leitura no ERP
· .env só via load_dotenv · metas só para postos · testes nunca gravam no banco real
· TODA ocorrência (pendência, tela, Telegram, planilha) mostra o NOME do frentista + código (decisão do diretor 10/10/2026);
  sem frentista identificável → "frentista não identificado" + motivo; nomes nunca no Git nem no chat dos agentes

## Retomada
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; Get-Content data\cash_audit\noturno.log -Tail 2; python -m uvicorn src.main:app --port 8000
Tela: http://localhost:8000/app/financial (login; Ctrl+F5 na primeira vez)
