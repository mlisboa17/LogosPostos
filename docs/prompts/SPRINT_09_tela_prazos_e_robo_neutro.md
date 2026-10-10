# Prompt — SPRINT 09: informativos na tela, prazo das pendências e robô sem import cruzado (Cursor / Antigravity / VS Code)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem merge na main e sem troca de branch. Somente leitura no ERP (`WEBPOSTO_WRITES=0`). `.env` só via `load_dotenv`, nunca imprimir valores. Altere SOMENTE as funções citadas; não reescreva arquivos inteiros; não adicione dependências. Datas no padrão Brasil (America/Recife, `dd/mm/aaaa HH:mm`). Nunca dados fictícios em telas ou resultados.
**Nunca grave dados de teste no banco real** (`data/pendencias/`, `data/cash_audit/`): testes usam `tmp_path` (já existe `tests/unit/cash_reconciliation/conftest.py`); conferência no navegador é só leitura — não crie, justifique nem aprove pendências.

Estado: FECHAMENTO_V4 pronta (commit e06f389); 105 pendências abertas de 01 a 09/10/2026.

## PARTE A — Informativos visíveis na tela do Fechamento

A V4 grava `informativos` por caixa (ex.: "Sangria de R$ X às HH:MM repassada ao Casa Caiada", "assumida no cofre"), mas a tela não mostra.

@WebPosto_API/frontend/pages/cashAudit.js
@WebPosto_API/tests/frontend/cashAudit.test.mjs

1. `cashAudit.js`, só na renderização do detalhe do caixa: bloco "Informações" em cinza (sem cor de alerta) listando os informativos. Não contam como alerta nem entram nos totais de pendência. Resultado antigo sem `informativos` → bloco não aparece.
2. Teste frontend: com informativos → bloco aparece; sem o campo → nada quebra.

## PARTE B — Prazo das pendências (cobrança dos gerentes)

@WebPosto_API/src/modules/cash_reconciliation/config/units.json
@WebPosto_API/src/modules/cash_reconciliation/domain/pendencias.py
@WebPosto_API/src/modules/cash_reconciliation/interfaces/http.py
@WebPosto_API/frontend/pages/pendencias.js
@WebPosto_API/frontend/pages/directorDashboard.js
@WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py
@WebPosto_API/tests/frontend/pendencias.test.mjs
@WebPosto_API/tests/frontend/directorDashboard.test.mjs

1. Prazo configurável no `units.json` (bloco geral, não por unidade): `"prazo_pendencia_dias": {"vermelho": 2, "laranja": 5}` — valores iniciais, o diretor pode mudar.
2. Calcular (sem nova coluna no banco) a partir da data de criação, no fuso de Recife: `aberta_ha_dias` e `vencida` (status `aberta` e idade > prazo). Expor em `_serializar_pendencia` e no filtro de `listar_pendencias` (`vencidas=true`).
3. `pendencias.js`: mostrar "aberta há N dias"; pendência vencida com selo "VENCIDA"; ordenar vencidas primeiro; filtro "Só vencidas".
4. `directorDashboard.js`, nos cards por unidade: "Vencidas: N" com link para a fila filtrada (unidade + vencidas). Gerente vê só a própria unidade (regra atual de escopo).
5. Testes: prazo vermelho 2 dias → 3 dias aberta = vencida; justificada nunca é vencida; virada de dia em Recife (ex.: criada 23:30) conta certo; filtro e selo no frontend.

## PARTE C — Robô noturno sem import cruzado entre módulos

Hoje `cash_reconciliation/jobs/noturno.py` importa `commercial_performance` (linhas ~14–16), violando a regra "sem import cruzado entre módulos".

@WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py
@scripts/registrar_robo_noturno.ps1

1. Criar `WebPosto_API/src/jobs/noturno.py` (ponto de composição, fora dos módulos): roda a auditoria de caixa e depois o placar, com o mesmo log, mesma linha final e mesmo código de saída de hoje. A parte de caixa continua em `cash_reconciliation`; a de placar em `commercial_performance`.
2. `cash_reconciliation/jobs/noturno.py`: remover os imports de `commercial_performance`; manter `python -m src.modules.cash_reconciliation.jobs.noturno [--dia dd/mm/aaaa]` funcionando (delegando ao novo ponto de composição) para **não precisar registrar de novo a tarefa do Windows**.
3. `registrar_robo_noturno.ps1`: passar a usar `-m src.jobs.noturno` (vale no próximo registro; não registre a tarefa agora).
4. Teste arquitetural: nenhum arquivo em `src/modules/cash_reconciliation` importa `commercial_performance` e vice-versa.

## Ao terminar

```
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; python -m pytest tests/unit/cash_reconciliation tests/unit/commercial_performance tests/unit/test_auth_access.py -q -o addopts=""; node --test tests/frontend/*.test.mjs
python -m src.modules.cash_reconciliation.jobs.noturno --dia 09/10/2026
```
Informe: testes, linha final do log, pendências vencidas por unidade hoje, e confirme que o banco real não recebeu dados de teste.
Commits separados: `feat(cash-audit): informativos do fechamento na tela`, `feat(pendencias): prazo e pendências vencidas`, `refactor(jobs): robô noturno sem import cruzado entre módulos`. Depois `git push`.
