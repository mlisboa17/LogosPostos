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

## Como testar

Executar na pasta `WebPosto_API`:

```powershell
python -m pytest tests/unit -q --no-cov
node --test tests/frontend/*.test.mjs
```

Validação registrada: 412 testes backend e 29 frontend aprovados na suíte completa. A conferência local no navegador usou snapshots existentes e não executou o robô nem escreveu no ERP.

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
