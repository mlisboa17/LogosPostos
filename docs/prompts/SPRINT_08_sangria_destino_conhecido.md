# Prompt — SPRINT 08: sangria com destino conhecido (Cursor / Antigravity / VS Code)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem merge na main e sem troca de branch. Somente leitura no ERP. `.env` só via `load_dotenv`, nunca imprimir valores. Altere SOMENTE as funções citadas; não reescreva arquivos inteiros; não adicione dependências. Datas no padrão Brasil. Conciliação de depósitos continua FORA do escopo.

Contexto: de 01 a 09/10/2026 há 46 pendências vermelhas `fechamento_sangria_sem_destino` (Conveniência 24h 118508: 24; Casa Caiada 5555: 21; VIP 11495: 1).
Decisão do diretor (10/10/2026): **na Conveniência 24h, sangria sem conta de destino é o processo normal — o dinheiro vai para o Casa Caiada.** Não é falha.

Arquivos:
@WebPosto_API/src/modules/cash_reconciliation/config/units.json
@WebPosto_API/src/modules/cash_reconciliation/domain/models.py
@WebPosto_API/src/modules/cash_reconciliation/rules/fechamento.py
@WebPosto_API/src/modules/cash_reconciliation/application/auditar_fechamento.py
@WebPosto_API/src/modules/cash_reconciliation/application/gerar_pendencias.py
@WebPosto_API/tests/unit/cash_reconciliation/test_fechamento.py
@WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py

## PARTE A — Conveniência 24h (aprovada)

1. `units.json`, só na unidade 118508: adicionar `"repasse_sangria_para": 5555` (sem número de conta).
2. `domain/models.py`, na configuração da unidade: campo opcional `repasse_sangria_para: int | None = None` (JSON antigos continuam válidos).
3. `rules/fechamento.py`: nova versão **`FECHAMENTO_V4`** (regra nova = versão nova; manter o comportamento V3 para quem não tem configuração). Em `auditar_caixa`, novo parâmetro opcional `repasse_sangria_para: int | None = None`. No laço das sangrias (~linha 129): se `conta_codigo is None` **e** há repasse configurado → NÃO gerar `SANGRIA_SEM_DESTINO`; em vez disso registrar no resultado do caixa a informação "Sangria de R$ X às HH:MM repassada ao Casa Caiada" (informativo, sem severidade vermelho/laranja, não vira pendência). Sem repasse configurado → continua vermelho como hoje. `SANGRIA_ALTERADA` não muda.
4. `application/auditar_fechamento.py`, em `auditar_unidade`/`auditar`: passar `repasse_sangria_para` da configuração da unidade para `auditar_caixa`. Nome da unidade de destino lido do `units.json`, não fixo no código.
5. `gerar_pendencias.py`: pendências `fechamento_sangria_sem_destino` ainda `aberta` de unidade com repasse configurado → fechar com status existente adequado (`aprovada`), usuário `robo`, justificativa "Regra FECHAMENTO_V4: sangria da Conveniência 24h repassada ao Casa Caiada (decisão do diretor em 10/10/2026)". Evento no histórico, sem apagar. Pendências `justificada`/`recusada` não são tocadas.
6. Testes (sem rede): 118508 com sangria sem conta → sem alerta vermelho e com informativo; unidade sem repasse → continua vermelho; reprocessar não duplica e fecha as abertas antigas com histórico; JSON de resultado V3 antigo continua abrindo.

## PARTE B — Casa Caiada (aprovada pelo diretor em 10/10/2026: sangria sem conta vai para o cofre)

O `units.json` já tem `"destino_padrao": 17837` (cofre BB) no Casa Caiada, mas a regra de fechamento ignora esse campo; por isso as 21 sangrias aparecem como "sem destino".
Se aprovada: na regra V4, sangria sem conta em unidade com `destino_padrao` → informativo "assumida no cofre (destino padrão)", sem pendência; fechar as abertas do Casa Caiada como no item 5, com justificativa citando o destino padrão.

## Ao terminar

```
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; python -m pytest tests/unit/cash_reconciliation tests/unit/commercial_performance tests/unit/test_auth_access.py -q -o addopts=""; node --test tests/frontend/
python -m src.modules.cash_reconciliation.jobs.noturno --dia 09/10/2026
```
Para reprocessar 01 a 08/10 use o mesmo comando dia a dia (idempotente).
Informe: linha final do log, pendências abertas de 01 a 09/10 por unidade e por tipo (antes: 151 abertas, 46 `sangria_sem_destino`).
Commit: `feat(cash-audit): FECHAMENTO_V4 — sangria da Conveniência 24h repassada ao Casa Caiada` (e, se B, `feat(cash-audit): destino padrão do Casa Caiada na regra de fechamento`). Depois `git push`.
