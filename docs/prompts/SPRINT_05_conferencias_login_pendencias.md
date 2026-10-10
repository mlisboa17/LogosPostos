# Prompt — SPRINT 05: mais conferências automáticas, login e fila de pendências

> Workspace `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem push, merge ou troca de branch.
> Execute as sprints **na ordem**, uma por vez. Ao fim de cada uma: testes (pytest dos módulos + frontend) verdes, tela conferida no navegador, **1 commit**, resumo curto com números reais. Depois siga para a próxima — exceto onde estiver escrito **PARE E APRESENTE O PLANO**.

## Estado atual (não refaça)

- Último commit: `11ec0a9`. Prontos: auditoria de fechamento (`FECHAMENTO_V2`), recebimentos PagBank com atribuição a frentista (`CARTOES_V1`), robô noturno (dias 06 e 07/10 gravados), datas padrão Brasil, placar de metas (API, tela, robô; metas de out/2026 do VIP).
- Decisões do sócio-diretor: tokens `CONSUMER_TOKEN`/`ADMIN_TOKEN` **não** serão trocados (não sugerir); conciliação de depósitos × extrato está **fora de escopo**; metas só para postos.
- Adquirentes fora do PagBank (Mais Pagamentos, Cielo, Rede) e Premmia dependem de fornecedor: **não mexer nesta sprint**.

## Regras gerais

Somente leitura no ERP · `.env` só via `load_dotenv`, nunca imprimir valores · nunca dados fictícios ("fonte indisponível") · testes só sintéticos · toda regra nova = **versão nova** · datas `dd/mm/aaaa` (fuso Recife) · antes de usar uma rota nova do webPosto, faça sondagem read-only mostrando só nomes de campos e contagens · arquitetura: monólito modular, sem import cruzado entre `cash_reconciliation` e `commercial_performance` (compartilhado vai em `webposto_integration`).

---

## Sprint 5.1 — Mais conferências automáticas do fechamento (só webPosto) → regra `FECHAMENTO_V3`

1. **Quebra não descontada do operador** — caixa fechado com **falta** em dinheiro acima de R$ 10 e **sem vale de falta** lançado para o operador/caixa em `GET /INTEGRACAO/V1/VALES_FUNCIONARIO` (origem `D` = falta de caixa; `C` = sobra). Vermelho: "Falta de R$ X sem desconto lançado". Se houver vale, mostrar "descontado (vale R$ Y)" e, se o valor do vale for diferente da falta, laranja com a diferença.
2. **Caixa parado sem consolidar** — tolerância configurável `dias_tolerancia_consolidacao` (padrão **2** dias corridos após o fechamento, fuso Recife): dentro da tolerância = laranja; acima = **vermelho** "Fechado há N dias sem consolidar". A quebra de caixa não consolidado segue a mesma lógica (laranja dentro da tolerância, vermelha depois). Registre no README que o padrão 2 aguarda confirmação do sócio-diretor.
3. **Despesas pagas com dinheiro do caixa** — `GET /INTEGRACAO/V1/MOVIMENTACOES_CAIXA` tipo `D` (débito/despesa) do caixa: listar no detalhe do caixa; laranja quando **sem plano de contas** (`planoContaCodigo` vazio) ou sem descrição útil.
4. **Reincidência no mês** — por operador do caixa (`funcionarioCodigo`) e por frentista (atribuições/sugestões de `CARTOES_V1`): quantidade de quebras, valor total de faltas, sangrias alteradas, recebimentos a maior atribuídos. Endpoint `GET /api/v1/cash-audit/reincidencia?unidade=&mes=AAAA-MM` e seção "Reincidência do mês" na tela de Auditoria de Caixa (nome do funcionário via `V1/FUNCIONARIOS`; nunca versionar nomes).
5. Robô noturno grava os novos campos; telas mostram os chips novos ("Sem desconto", "Parado N dias", "Despesa sem plano").

## Sprint 5.2 — Login e permissões nas rotas financeiras — **PARE E APRESENTE O PLANO antes de implementar**

Hoje `/api/v1/cash-audit/*` e `/api/v1/commercial/*` respondem sem login.
1. Inventarie o mecanismo existente (`src/interfaces/http/routes/auth.py`, `dependencies.get_current_user`, `infrastructure/security/jwt_utils.py`, cookie `AUTH_*` no `.env`) — **reutilize** (REUSE > ADAPT > CREATE).
2. Proponha: perfis **diretor** (tudo, todas as unidades), **gerente** (só a própria unidade), **auditor** (leitura); como o frontend envia o token; o que acontece com o robô noturno (não usa HTTP) e com o modo TV do placar (token de exibição somente leitura, por unidade).
3. **PARE** e mostre o plano em até 15 linhas. Implemente só após aprovação: dependência de autenticação nas rotas, filtro por unidade conforme perfil, testes 401/403/200, tela de login reaproveitando a existente.

## Sprint 5.3 — Fila de pendências com justificativa (depois da 5.2)

1. Cada alerta vermelho/laranja (fechamento, recebimentos, reincidência) vira uma **pendência** com: unidade, dia, tipo, valor, referência (caixa/sangria/transação), status `aberta → justificada → aprovada | recusada`, responsável, justificativa, histórico com data/hora e usuário (imutável: correção gera novo evento).
2. Persistência local (SQLite em `WebPosto_API/data/`, fora do Git) atrás de um repositório no próprio módulo; idempotente (o robô noturno não duplica pendências do mesmo alerta).
3. Tela "Pendências": filtros por unidade/status/tipo, gerente justifica, diretor aprova/recusa; contador de pendências abertas no menu.
4. Testes de ciclo de vida e de permissão (gerente não aprova; gerente não vê outra unidade).

## Sprint 5.4 — Higiene do repositório

1. Parar de versionar `.pyc`/`__pycache__` (`git rm -r --cached` só desses artefatos + `.gitignore`), sem apagar arquivos do disco.
2. **Não** remova os 28 snapshots já versionados: apenas liste-os no resumo (decisão do sócio-diretor).
3. Atualize `docs/status/` com um relatório curto do que mudou nesta sprint.

## Entrega por sprint

Saída dos testes · commit (`feat(cash-audit): ...`, `feat(auth): ...`, `chore: ...`) · resumo: arquivos, números reais (ex.: quantas quebras sem desconto em 06–07/10 por unidade), decisões e pendências.
