# STATUS — LOGOS Auditoria (atualizado em 10/10/2026, noite)

Repositório canônico: C:\Projetos\LOGOS\LogosPostos · branch feature/cash-audit-fechamento
Último commit de código: a40b2bb (Sprint 11 concluída) · branch sincronizado com o GitHub privado (sem merge na main)
PR a abrir: https://github.com/mlisboa17/LogosPostos/pull/new/feature/cash-audit-fechamento
Histórico de sprints: um prompt por sprint em docs/prompts/ (SPRINT_05 ... SPRINT_12, PREMMIA_00, TELEGRAM_00)

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

## Ponto de parada (11/10/2026 03:00)
- Sprint 14 CONCLUÍDA (50cdc21, 97c6bd3, 0255950): tela "Conferência de Recebimentos" com 4 grupos
  (Lançar/Alterar/Apurar/Conferir à mão), visão diária por adquirente, 17 correções prontas (status "proposta",
  ADR-003 Fase 0), conferência manual auditada, período até D-2 e máx. 7 dias, datas dd/mm/aaaa em todo o frontend.
  308 testes backend + 56 frontend verdes.
- 01–09/10: Casa Caiada 1.280 · R$ 115.016,23 conferidos; Doze 2.955 · R$ 203.167,01; grupo 3 (sem lastro) = 0.
  Reincidente: frentista 277311 (Casa Caiada), 3 trocas · R$ 163,90.
- Mais Pagamentos usada em Doze, Casa Caiada e VIP (aparece como "Transferência Bancária"): R$ 278 mil em 9 dias
  SEM conferência. Bloqueio: client_id/secret de integração (ver MAIS_01 no backlog).
- Sprint 14.1 CONCLUÍDA (e6d0190, fa7e677): Telegram sem KeyError; Premmia abre o login no modo invisível
  (validado 11/10 03:52, Doze e Casa Caiada); falha do portal = aviso. Robô 10/10: falha=0, aviso=1. 321 testes verdes.
- CIELO_01 (novo, 11/10/2026): diretor homologou o Extrato Eletrônico EDI da Cielo, conciliação própria.
  EC matriz 1050633722 (VIP loja EC 1003946779 aparece no portal). Arquivos: CIELO03 (vendas cartões),
  CIELO16 (Pix na maquininha), CIELO04 (pagamentos/liquidação). Acesso por API: OAuth2 client_credentials
  (client_id/client_secret) + assinatura HMAC no header X-Signature + certificado mTLS;
  POST https://api-internet.cielo.com.br/cielo-extc-serv-edi-link-exp-external/extc-serv-edi-link-external/v1/link/generate
  (merchantCode, fileType 3=vendas 4=pagamentos, processType D/R/M, startDate/endDate) → links temporários de download.
  Pendente do diretor: gerar a chave no portal Cielo, colocar no .env, certificado mTLS, manual de layout e de links.
- Próximo: CIELO_01 · MAIS_01 (quando chegar a credencial) · Sprint 15 (dossiê + medir acerto das propostas) · EXTRATOS_01.

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

## Decisões fixas
Não trocar CONSUMER_TOKEN/ADMIN_TOKEN · conciliação de depósitos fora do escopo · somente leitura no ERP
· .env só via load_dotenv · metas só para postos · testes nunca gravam no banco real
· TODA ocorrência (pendência, tela, Telegram, planilha) mostra o NOME do frentista + código (decisão do diretor 10/10/2026);
  sem frentista identificável → "frentista não identificado" + motivo; nomes nunca no Git nem no chat dos agentes

## Retomada
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; Get-Content data\cash_audit\noturno.log -Tail 2; python -m uvicorn src.main:app --port 8000
Tela: http://localhost:8000/app/financial (login; Ctrl+F5 na primeira vez)
