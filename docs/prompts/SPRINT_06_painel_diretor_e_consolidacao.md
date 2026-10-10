# Prompt — SPRINT 06: consolidação, números reais e painel do diretor

> Workspace `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem push, merge ou troca de branch.
> Uma sprint por vez; ao fim de cada uma: testes verdes (backend + frontend), tela conferida no navegador, **1 commit**, resumo com **números reais**.

## Estado atual (não refaça)

Último commit `176e1ff`. Prontos: `FECHAMENTO_V3` (falta sem desconto, caixa parado, despesas do caixa, reincidência), login com perfis diretor/gerente/auditor, fila de pendências (SQLite em `data/pendencias/`), placar de metas, robô noturno, higiene de `.pyc`.
Decisões vigentes: não mexer em `CONSUMER_TOKEN`/`ADMIN_TOKEN`; adquirentes fora do PagBank e Premmia aguardam fornecedor; conciliação de depósitos fora de escopo.

Regras gerais: somente leitura no ERP · `.env` só via `load_dotenv`, nunca imprimir valores · nunca dados fictícios · testes sintéticos · regra nova = versão nova · datas `dd/mm/aaaa` (Recife) · sem import cruzado entre módulos.

---

## Sprint 6.1 — Login sem credencial padrão (correção de segurança)

1. `settings.py`: `auth_user_email` e `auth_user_password` **sem valor padrão** (hoje `admin@company.com` / `password`). Sem usuário configurado, o login deve **recusar** com mensagem clara ("login não configurado"), nunca aceitar padrão.
2. Aceitar senha **somente como hash** quando `AUTH_USERS_JSON` for usado; manter compatibilidade com o `AUTH_USER_EMAIL`/`AUTH_USER_PASSWORD` atual do `.env` **sem alterar o `.env`** (decisão do diretor).
3. Criar utilitário `python -m src.infrastructure.security.gerar_hash` que pede a senha sem eco (`getpass`) e imprime só o hash — para o diretor cadastrar gerentes por unidade em `AUTH_USERS_JSON`. Documentar no README com exemplo de JSON (valores fictícios óbvios, ex.: `gerente.vip@exemplo.com`).
4. Testes: sem configuração → recusa; `password` padrão nunca aceita; hash válido aceita.

## Sprint 6.2 — Números reais do FECHAMENTO_V3 e pendências reais

1. Rode o robô noturno para **06/10, 07/10 e 08/10/2026** (reprocessar 06 e 07 com a regra nova é esperado e idempotente).
2. Confirme que o robô **gera pendências** a partir dos alertas (sem duplicar ao reprocessar). Se não gerar, implemente.
3. Entregue tabela por unidade e dia: caixas, quebras (R$), **faltas sem desconto** (quantidade e R$), **caixas parados** (dias), **despesas sem plano de contas**, recebimentos PagBank (casados / a maior / a menor / pares), pendências abertas. E o top 5 de reincidência do mês por unidade (use código do funcionário no chat; nomes só na tela).

## Sprint 6.3 — Painel do Diretor (tela inicial)

Nova tela **"Painel do Diretor"** (menu, primeira opção para o perfil diretor; gerente vê só a própria unidade), estilo dark existente:
1. **Saúde do robô:** última execução, dia processado, unidades com falha; **alerta vermelho se o robô não rodou nas últimas 26 h** (hoje ele ainda não está agendado no Windows).
2. **Hoje por unidade** (cards): quebra do último dia fechado, faltas sem desconto, caixas parados, recebimentos a maior/a menor, pendências abertas (com link para a fila filtrada).
3. **Placar** resumido dos postos: % Bronze/Prata/Ouro e projeção.
4. **Adquirentes:** situação por unidade (ativo / pendente / credencial inválida).
5. Tudo lido dos resultados gravados (rápido); botão "atualizar agora" só para o diretor.
6. Gerar também um **resumo em texto** do dia (`data/resumos/<dia>.md`, fora do Git) no fim do robô noturno — base para envio por WhatsApp/e-mail numa sprint futura (canal ainda não definido).

## Sprint 6.4 — Proteção do trabalho (somente preparar, não executar)

O branch tem dezenas de commits que existem só neste computador. **Não faça push.** Prepare:
1. `docs/status/PR_feature_cash_audit.md`: descrição do Pull Request (o que muda, como testar, riscos, ADR-002) e checklist de revisão.
2. Verifique que nenhum arquivo com dado real ou segredo está rastreado (varredura de valores do `.env` contra `git ls-files`, sem imprimir valores; listar só arquivo e nome da variável).
3. Reporte: quantidade de commits à frente de `logos/main`, tamanho do diff, e os comandos que o diretor deve aprovar para enviar o branch ao GitHub.

## Entrega por sprint

Saída dos testes · commit (`fix(auth): ...`, `feat(cash-audit): ...`, `feat(painel): ...`, `docs: ...`) · resumo com números reais, decisões e pendências.
