# Prompt — SPRINT 15.2 (correção rápida): total do PagBank no bloco de status (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Somente leitura; sem reescrever arquivos; nada pelo Telegram. **Rodar só os testes de `tests/unit/cash_reconciliation/test_relatorio_caixa_dia.py` e `test_recebimentos.py` durante o trabalho; a bateria completa só no final.** Meta: 20 minutos.

## Bug (relatório da Sprint 15.1, Casa Caiada 10/10/2026)

- Bloco de status: **"✅ PagBank (EDI): 110 · R$ 9.133,98"**.
- Bloco de recebimentos do mesmo relatório: **109 · R$ 8.983,98** casados.
- Conferência ao vivo do arquiteto (11/10, 15h15): **EDI PagBank = 109 · R$ 8.983,98**; 109 casados; nenhum a maior, a menor, par ou grupo. Ou seja, o status somou **um item a mais de R$ 150,00** (provável dupla contagem — ex.: forma de pagamento da venda "Cartão POS"/PIX de `V1/VENDAS_FORMA_PAGAMENTO` somada junto com o cartão de `V1/CARTOES`, ou transação de alerta somada além dos casados).

@WebPosto_API/src/modules/cash_reconciliation/application/relatorio_caixa_dia.py
@WebPosto_API/src/modules/cash_reconciliation/domain/recebimentos.py
@WebPosto_API/tests/unit/cash_reconciliation/test_relatorio_caixa_dia.py

## Correção

1. O lado **"fonte"** do status = **só transações da adquirente** (EDI/portal), aprovadas, sem estornadas, cada uma **uma vez** (por identificador/NSU). O lado **"webPosto"** = cartões de `V1/CARTOES` das administradoras mapeadas + formas de pagamento de venda **sem cartão detalhado** (essas uma vez só, nunca somadas se já existir o cartão).
2. Os números do status e do bloco de recebimentos têm de sair **da mesma fonte de dados** no mesmo relatório (sem misturar gravado e atual).
3. Teste de regressão com o caso: 109 transações · R$ 8.983,98 dos dois lados → "✅ 109 · R$ 8.983,98", e um teste com venda "Cartão POS" + cartão detalhado da mesma venda contando **uma vez**.
4. Regerar `python -m src.jobs.relatorio_caixa --dia 10/10/2026 --unidade 5555` e mostrar o bloco de status no chat (`set PYTHONIOENCODING=utf-8` antes, para não dar erro de acentuação no terminal).

Commit: `fix(relatorio): total do PagBank no status sem dupla contagem`. Depois `git push`.
