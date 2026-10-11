# Prompt — SPRINT 12.1: ajuste fino do NSU repetido (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Mesmas regras da Sprint 12 (somente leitura, `.env` só via `load_dotenv`, sem reescrever arquivos, testes sintéticos, nada pelo Telegram, nomes trocados por "Funcionário A..." no chat). Nova versão: **`CARTOES_V3_1`**.

## Problema (revisão do diretor sobre os 4 alertas `recebimento_nsu_repetido` de 01 a 09/10/2026)

| Caso | Situação | Avaliação |
|---|---|---|
| VIP 05/10 | mesmo NSU (UUID), mesmo valor R$ 30,00, mesmo frentista, 5 min de diferença | **real** — continua vermelho |
| Casa Caiada 02/10 | repetição só da autorização; valores R$ 20 e R$ 30; frentistas diferentes; 3h40 de diferença | provável coincidência de código de autorização |
| Doze 09/10 × 10/10 | repetição só da autorização; R$ 207,67 e R$ 200,00; dias e frentistas diferentes; pendência gravada com valor 0 | provável coincidência |
| Doze 06/10 | dois lançamentos **"Manualmente"**, venda 0, 01:00, R$ 150,04 e R$ 20,00 | não é NSU repetido: é **lançamento manual sem venda** |

Código de autorização tem poucos dígitos e se repete entre bandeiras/dias; sozinho não prova duplicidade.

@WebPosto_API/src/modules/cash_reconciliation/rules/cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/gerar_pendencias.py
@WebPosto_API/tests/unit/cash_reconciliation/test_cartoes.py
@WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py

## Ajuste

1. Agrupamento do NSU repetido: **vermelho `CARTAO_NSU_REPETIDO`** somente quando:
   - mesmo **NSU** (ou NSU TEF) não vazio, **ou**
   - mesma **autorização** + mesmo **valor** + mesmo **dia**.
   Autorização repetida com valor ou dia diferente → **não gera alerta** (registrar só no log de depuração).
2. Novo alerta **laranja `CARTAO_MANUAL_SEM_VENDA`**: cartão com `tipoInclusao == "Manualmente"` e sem venda (`vendaCodigo` vazio ou 0), um alerta por lançamento, com valor, hora, administradora e responsável se houver (operador do caixa); entra no grupo laranja do caixa/dia.
3. Pendência nunca com valor 0: valor = soma dos lançamentos excedentes do grupo.
4. Pendências `recebimento_nsu_repetido` ainda `aberta` que deixarem de valer pela regra nova → status `aprovada`, usuário `robo`, justificativa "Regra CARTOES_V3_1: autorização repetida com valor/dia diferentes não indica duplicidade". Histórico preservado. Justificadas/recusadas não são tocadas.
5. Testes: os 4 casos acima reproduzidos com dados sintéticos (resultado esperado conforme a tabela); idempotência.

## Ao terminar

Reprocessar 01 a 09/10/2026 de Doze, Casa Caiada e VIP; rodar os testes de sempre (`tests/unit/cash_reconciliation tests/unit/commercial_performance tests/unit/test_auth_access.py` e `node --test tests/frontend/*.test.mjs`).
Informe: alertas `CARTAO_NSU_REPETIDO` restantes (esperado: só o VIP 05/10), `CARTAO_MANUAL_SEM_VENDA` por unidade (quantidade e R$), pendências abertas por unidade.
Commit: `fix(cartoes): CARTOES_V3_1 — NSU repetido sem falso positivo e cartão manual sem venda`. Depois `git push`.
