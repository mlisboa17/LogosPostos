# PR — Auditoria de caixa, pendências e Painel do Diretor

## Resumo

Consolidar neste branch a auditoria de fechamento `FECHAMENTO_V3`, a fila local de pendências, o placar persistido, a autenticação sem credencial padrão e o Painel do Diretor. O painel exibe saúde do robô, último fechamento, recebimentos, pendências, adquirentes e projeção de metas com escopo por perfil.

## O que muda

- Login sem credenciais padrão; suporte a usuários configurados com hash e utilitário local para gerar hashes.
- Snapshots diários da auditoria, pendências rastreáveis, reincidência e placar comercial persistidos fora do Git.
- Painel escuro inicial para diretor e gerente; o gerente fica restrito à sua unidade.
- Leituras do painel limitadas aos resultados gravados; banco de pendências aberto em modo somente leitura. Ausências não são apresentadas como zeros.
- Estado do robô, alerta de atraso superior a 26 horas e resumo diário agregado em `WebPosto_API/data/resumos/`.
- Testes sintéticos para autenticação, isolamento, persistência, saúde e renderização.
- TELEGRAM_02.1: resumo por posto/setor/caixa, principal com até 25 linhas e
  continuação sem descartar alertas. Mantém despesas (até oito itens no resumo,
  com descrição/plano/valor), vales com nome e código, recebimentos por forma,
  NSU mascarado e avisos Premmia com a data dos últimos dados.
- A falta usa a regra existente `LIMITE_QUEBRA` (R$ 10), sem corte fixo de R$ 100.
  Faltas sem desconto e caixas não consolidados exigem atenção mesmo abaixo do limite;
  caixas abertos não entram nas faltas.
- Reenvio explícito do texto já gravado: `python -m src.jobs.telegram --reenviar-resumo 13/10/2026`.
  Lê somente o resumo local, divide mensagens longas e não consulta nem escreve no ERP.
  **Executar somente depois do "ok" do diretor**; não há envio automático por esse comando sem opção.
  O arquivo do resumo e o histórico do robô não são alterados pelo reenvio.
- TELEGRAM_02.2: uma linha por adquirente com totais dos casamentos e ocorrências
  da conciliação, sem diferenças geradas pela grafia das bandeiras. Até cinco itens
  a maior/a menor/duplicidade por posto, com hora, valor e responsável; excedentes
  ficam na planilha. Aliases de Mastercard, Maestro, Visa Electron e Elo são
  agrupados somente na tabela de formas da planilha; Cartão APP aparece à parte
  como crédito sem bandeira discriminada.
- Sangrias alteradas do mesmo caixa são somadas em um único alerta, ordenado
  com faltas e demais itens pelo valor. O snapshot guarda apenas o valor atual:
  não há evidência para mostrar o valor anterior à alteração.
- Validação TELEGRAM_02.2: `python -m pytest tests/unit/cash_reconciliation -q`
  com 397 aprovados e nenhuma falha. Resumo e planilha de 13/10/2026 regenerados
  somente de snapshots locais, com rede bloqueada; principal de 14 linhas.
  Doze e Casa Caiada conferidos sem diferenças artificiais por bandeira; VIP
  com quatro sangrias totalizando R$ 667,00. Nenhum envio ou escrita no webPosto.

## Como testar

### Sprint 18b.1 — caixa como na tela

- Propostas, listas, botões privados do Telegram, histórico da tela e resumo
  identificam o caixa por posto/setor, data do movimento, turno, funcionário
  de abertura e horário em America/Recife, sem o código interno no texto.
- O formato completo inclui fechamento e total apurado de `V1/CAIXAS`;
  o curto usa o primeiro nome. Nomes ausentes usam `funcionário <código>`.
  Apenas um caixa no dia/setor recebe `(único caixa do dia)`.
- A proposta mostra dinheiro e cartão antes/depois, calculados com os apurados
  de `V1/CAIXAS_APRESENTADO`. Saldos ausentes bloqueiam a proposta.
- O código permanece no payload/auditoria e em coluna própria `Código interno`
  nas planilhas. Histórico antigo é formatado na leitura, sem regravar auditoria.
- A prévia só consulta dados. Não executar aprovação, robô ou envio Telegram
  para validar os textos; nenhum lançamento ou envio é necessário.
- Validação 18b.1: 762 testes backend (`tests/unit` e `tests/services`) e
  71 testes frontend aprovados. Os testes novos cobrem formatos exatos,
  horário UTC convertido para Recife, unicidade por dia/setor/unidade,
  nomes vazios, ausência de saldos, cálculo antes/depois e histórico legado.
  Integrações reais não são parte dessa bateria sintética.
- Prévia real conferida exclusivamente com GET: Mastercard de R$ 34,75 no
  Doze em 14/10/2026, apurado de R$ 50.016,49, dinheiro de R$ 15.855,41
  para R$ 15.820,66 e cartão de R$ 23.439,22 para R$ 23.473,97.
  Linhas de caixa de 13/10 conferidas sem envio ou gravação.

Executar na pasta `WebPosto_API`:

```powershell
python -m pytest tests/unit -q --no-cov
node --test tests/frontend/*.test.mjs
```

Validação registrada: 412 testes backend e 29 frontend aprovados na suíte completa. A conferência local no navegador usou snapshots existentes e não executou o robô nem escreveu no ERP.

Validação TELEGRAM_02.1 (14/10/2026): `python -m pytest tests/unit/cash_reconciliation -q`
com 385 testes aprovados, zero falhas e zero tentativas reais de navegador/portal.
Os avisos incluem deprecações existentes e cobertura de cópias Python inválidas fora desta sprint.
O resumo e a planilha de 13/10/2026 foram regenerados exclusivamente com snapshots
e nomes da planilha já gravada, sem rede. Nenhum envio Telegram foi realizado.

## Evidência operacional observada

Na leitura dos snapshots em 10/10/2026, havia quatro unidades com fechamento até 08/10/2026 e 155 pendências abertas. O estado persistido do robô indicava zero unidades processadas na última execução registrada; o painel mostra isso como alerta operacional. Detalhes agregados da validação estão em [SPRINT_06_3_VALIDACAO.md](./SPRINT_06_3_VALIDACAO.md).

## ADR-002

Compatível com [ADR-002](../architecture/adr/ADR-002-cash-arch-01-antes-do-arch-02.md): a conciliação permanece no módulo vertical `cash_reconciliation`, com escopo de unidade e proveniência explícitos, sem importar dados reais ou credenciais para o Git. A entrega não antecipa a conciliação de depósitos nem altera a sequência de arquitetura além do que a decisão aceita.

## Riscos e itens que exigem revisão

- O estado observado do robô reportava zero unidades processadas. A tela sinaliza a inconsistência; esta entrega não reprocessou dados nem alterou o Agendador.
- A varredura de valores do `.env` contra arquivos rastreados não encontrou segredos reais. A ocorrência de `CONSUMER_TOKEN` no teste é o valor público legado `dev-consumer-token`, usado intencionalmente para testar rejeição; não é credencial ativa e não foi alterada.
- Não há endpoint de execução manual do robô; “Atualizar agora” recarrega somente dados persistidos.
- A tela ainda depende da atualização externa do robô para receber snapshots novos.

## Checklist de revisão

- [x] Varredura dos valores carregados do `.env` contra arquivos rastreados concluída sem imprimir valores. As correspondências são valores não sensíveis (URLs, `ENVIRONMENT`, `REDIS_URL`, papel de usuário, nomes de unidade e e-mail de login); nenhuma credencial real está rastreada.
- [x] A correspondência de `CONSUMER_TOKEN` em `WebPosto_API/logos-webposto-gateway/tests/test_security_tokens.py` é intencional: o teste verifica que o valor público legado `dev-consumer-token` é rejeitado. Nenhuma alteração foi feita por causa dessa ocorrência.
- [x] Confirmado: `.env` não está rastreado nem foi alterado.
- [x] Confirmado: `scripts/registrar_robo_noturno.ps1`, tokens e adquirentes pendentes não foram alterados nesta entrega.
- [x] Testes backend/frontend aprovados e tela conferida no navegador.
- [x] Acesso validado: diretor vê a rede; gerente vê somente sua unidade.
- [x] ERP permaneceu somente leitura e `data/` continua fora do Git.
- [ ] Revisar a procedência do registro de saúde sem unidades processadas.
- [ ] Aprovar explicitamente os comandos de publicação abaixo; nenhum foi executado nesta preparação.

## Comandos para aprovação do responsável

Executar somente após a revisão dos riscos e checklist:

```powershell
git push -u logos feature/cash-audit-fechamento
gh pr create --repo mlisboa17/LogosPostos --base main --head feature/cash-audit-fechamento --title "feat: painel do diretor e auditoria de caixa" --body-file docs/status/PR_feature_cash_audit.md
```

## Estado desta preparação

Branch local `feature/cash-audit-fechamento`; após o commit desta preparação, está 27 commits à frente e 0 atrás de `logos/main`. O diff `logos/main...HEAD` tem 146 arquivos, 38.431 inserções e 134 remoções. Nenhuma publicação, criação de PR ou alteração de branch foi realizada.
