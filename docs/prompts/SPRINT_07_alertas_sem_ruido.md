# Prompt — SPRINT 07: alertas sem ruído (Cursor / Antigravity / VS Code)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem merge na main e sem troca de branch. Somente leitura no ERP. Não ler nem imprimir o `.env`. Altere SOMENTE as funções citadas; não reescreva arquivos inteiros; não adicione dependências. Datas no padrão Brasil.

## PARTE A — Configuração pendente não é falha do robô

Contexto: na execução automática de 10/10/2026 03:00 o robô terminou com `unidades_com_falha=1` (código de saída 1) apenas porque o PagBank da Conveniência 24h (118508) está com credencial inválida — problema conhecido de configuração. Isso deixa o Painel do Diretor vermelho todas as noites.

Arquivos:
@WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py
@WebPosto_API/src/modules/cash_reconciliation/application/painel_diretor.py
@WebPosto_API/frontend/pages/directorDashboard.js
@WebPosto_API/tests/unit/cash_reconciliation/test_noturno.py
@WebPosto_API/tests/unit/cash_reconciliation/test_painel_diretor.py
@WebPosto_API/tests/frontend/directorDashboard.test.mjs

1. `jobs/noturno.py`, na função `executar` (bloco que conta `unidades_com_falha`, ~linhas 104–127): conte como **falha** apenas `erro_fechamento` ou adquirente com `situacao == "erro"`. Conte `situacao == "credencial inválida"` separadamente em `unidades_com_aviso`. Na linha final do log, registre `unidades_com_falha=X unidades_com_aviso=Y`. Código de saída: 1 só se houver falha real; avisos saem com 0.
2. Grave `unidades_com_aviso` no resultado persistido da execução, junto do campo existente de falhas (campo opcional com padrão vazio, para não quebrar os JSON antigos).
3. `application/painel_diretor.py`, só na função que monta a saúde do robô: três estados — `ok` (sem falha nem aviso), `atencao` (só avisos: listar unidade + adquirente + "credencial inválida") e `falha` (falha real ou robô sem rodar há mais de 26 h). Logs antigos sem `unidades_com_aviso` continuam sendo lidos.
4. `frontend/pages/directorDashboard.js`, só no card de saúde do robô: `atencao` em laranja com a lista de avisos; `falha` continua vermelho.
5. Testes (sem rede): credencial inválida → saída 0 e `atencao`; erro de fechamento → saída 1 e `falha`; log antigo → continua funcionando; frontend renderiza os três estados.

## PARTE B — Pendências agrupadas (aplicar SOMENTE se o diretor aprovar)

Contexto: 155 pendências abertas em 8 dias, a maioria laranja (ex.: sangria alterada). Regra proposta: **vermelho = pendência individual; laranja = uma pendência por caixa e por dia**, agrupando os alertas laranja daquele caixa.

Arquivos:
@WebPosto_API/src/modules/cash_reconciliation/application/gerar_pendencias.py
@WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py
@WebPosto_API/frontend/pages/pendencias.js

1. `gerar_pendencias.py`, só na função que transforma alertas de fechamento em pendências: os alertas vermelhos continuam um por um; os laranja do mesmo `(unidade, dia, caixaCodigo)` viram **uma** pendência do tipo `caixa_alertas_laranja`, com a lista de alertas no detalhe e o valor somado. Mantenha a idempotência: a chave da pendência agrupada é `(unidade, dia, caixa, "laranja")`; reprocessar não duplica, só atualiza o detalhe se a pendência ainda estiver `aberta`.
2. Pendências laranja individuais já existentes e ainda `aberta` do mesmo caixa/dia: marcar como `substituida` (novo evento no histórico, sem apagar) e apontar para a agrupada.
3. `frontend/pages/pendencias.js`, só na renderização do detalhe: mostrar a lista de alertas da pendência agrupada.
4. Testes: 3 alertas laranja no mesmo caixa → 1 pendência; vermelho continua individual; reprocessar não duplica; individuais antigas viram `substituida` com histórico.

## Ao terminar (A, e B se aplicada)

Rode e mostre a saída:
```
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; python -m pytest tests/unit/cash_reconciliation -q -o addopts=""; node --test tests/frontend/directorDashboard.test.mjs tests/frontend/pendencias.test.mjs
python -m src.modules.cash_reconciliation.jobs.noturno --dia 09/10/2026
```
Informe: código de saída do robô, linha final do log, estado da saúde no Painel e (se B) quantas pendências abertas ficaram de 01 a 09/10 por unidade (antes eram 155 até 08/10).
Commits separados: `fix(cash-audit): credencial inválida é aviso, não falha do robô` e (se B) `feat(cash-audit): pendências laranja agrupadas por caixa e dia`. Depois `git push`.
