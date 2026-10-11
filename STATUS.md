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

## Decisões fixas
Não trocar CONSUMER_TOKEN/ADMIN_TOKEN · conciliação de depósitos fora do escopo · somente leitura no ERP
· .env só via load_dotenv · metas só para postos · testes nunca gravam no banco real
· TODA ocorrência (pendência, tela, Telegram, planilha) mostra o NOME do frentista + código (decisão do diretor 10/10/2026);
  sem frentista identificável → "frentista não identificado" + motivo; nomes nunca no Git nem no chat dos agentes

## Retomada
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; Get-Content data\cash_audit\noturno.log -Tail 2; python -m uvicorn src.main:app --port 8000
Tela: http://localhost:8000/app/financial (login; Ctrl+F5 na primeira vez)
