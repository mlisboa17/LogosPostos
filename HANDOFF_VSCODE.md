# Handoff — Logos Match (para continuar no VS Code)

Data: 01/11/2026 · Branch `feature/logos-match` · worktree `C:\Projetos\LOGOS\LogosPostos-match` · PR rascunho https://github.com/mlisboa17/LogosPostos/pull/2

## Onde paramos
Executando o plano **`docs/superpowers/plans/2026-11-01-logos-match-extratos.md`** (spec: `docs/superpowers/specs/2026-10-18-logos-match-design.md` §14, aprovada pelo diretor).

| Task | Situação |
|---|---|
| 1 — autorização injetável em `webposto_escrita_ofx.enviar_ofx_webposto` | **em andamento, NÃO commitada**: há alterações parciais em `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py` e `WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_ofx.py`. Revisar o diff (`git diff`), completar os testes do plano + `test_previa_com_autorizacao_injetada_sem_env` (a prévia `confirmar=False` também deve aceitar a autorização injetada, sem `.env`), rodar a suíte e commitar. |
| 2 — pasta de extratos, reconhecimento, sem duplicidade, arquivo | pendente |
| 3 — camada 1: prévia + aprovação + importação no webPosto | pendente |
| 4 — aprovações pelo Telegram (botões) | pendente |
| 5 — camada 2: lista do que falta no financeiro (sem escrever) | pendente |
| 6 — autonomia gradual + versão 0.4.0 + instalador | pendente |

Fazer **uma task por vez, na ordem**, com TDD (teste falhando → implementar → passar) e um commit por task. O plano tem nomes, assinaturas, mensagens exatas e testes de cada task.

## Como testar
```
cd WebPosto_API
.venv/Scripts/python -m pytest -o addopts="" -p no:warnings tests/unit/match tests/unit/cash_reconciliation tests/unit/test_segredos.py -q
```
Base antes da Task 1: **953 passed**.

## Regras que não podem ser quebradas
- Escrita no webPosto **só** por `enviar_ofx_webposto` (barreira: só `IMPORTAR_APENAS_DIAS_INEXISTENTES_SISTEMA`, ≤7 dias, só dias passados, conta conferida em `V1/CONTAS`, histórico local). A camada 2 **não escreve** no webPosto neste plano.
- Sem `.env` real nem segredos em código/log/HTML/Telegram; exceções no log só com o nome do tipo.
- Testes 100% offline; usar `LOGOS_MATCH_DIR` com pasta temporária.
- Painel: sessão guarda só `usuario_id`, autorização por `acesso.pode_agora`, CSRF em todo POST, sem JavaScript.
- Commits em português; não commitar `.env`, `dist/`, `build/`.

## Pendências fora do plano
1. **Empresas que "somem" após reiniciar**: causa provável = o app foi aberto de dentro do Claude Desktop (MSIX virtualiza `%LOCALAPPDATA%` para `...\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\LogosMatch`). O app aberto pelo Windows usa `%LOCALAPPDATA%\LogosMatch`. Confirmar abrindo pelo **Menu Iniciar**, cadastrando uma empresa e reiniciando.
2. Teste da v0.2/0.3 instalada neste PC (telas Coleta/Histórico, Pasta da rede, desinstalar com "Apagar dados") — ver topo do `STATUS.md`.
3. Quando terminar o plano: revisão geral da branch, gerar `dist\LogosMatch-Setup-0.4.0.exe` (`apps\match\build\build.ps1`), push e tirar o PR do rascunho.
