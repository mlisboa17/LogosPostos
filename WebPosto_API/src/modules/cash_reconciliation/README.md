# Auditoria de caixa e recebimentos

As regras `FECHAMENTO_V2` e `CARTOES_V1` continuam no domínio do módulo.
O ERP é consultado somente por leitura; correções são humanas.

## Recebimentos

- `GET /api/v1/cash-audit/recebimentos?unidade=<empresaCodigo>&dia=AAAA-MM-DD`
- Cada adquirente vem de `config/units.json`. Apenas o PagBank ativo é consultado.
- Casados expõem quantidade e total, não comprovantes individuais. Divergências
  incluem candidatos, motivos e proveniência.
- `pendente` e `credencial inválida` não significam zero transações: o resumo
  `casados` fica nulo. Falhas de uma adquirente não interrompem as demais.
- Mais Pagamentos está pausada até confirmação da documentação oficial.
  Rede, Cielo e Premmia permanecem pendentes; não há geradores fictícios.

Na aplicação, abra `/app/financial?view=cash-audit`, selecione unidade e período
(máximo de 31 dias inclusivos). A seção **Recebimentos eletrônicos** consulta os
dias do período com concorrência limitada. Dias indisponíveis são sinalizados;
totais e ranking são parciais nesses casos. Sugestões não confirmam autoria.
Cada recebimento conta uma vez por frentista candidato; pares prováveis entram
no ranking sem duplicar a mesma investigação.

O adaptador webPosto interpreta explicitamente o marcador de cancelamento
(`N`/`S`, booleano ou equivalente), preservando a hora das vendas PIX e
restringindo vendas, pagamentos e itens à unidade solicitada.

## Testes sintéticos

Execute a partir de `WebPosto_API`, sem carregar credenciais nos testes unitários:

```powershell
python -m pytest tests/unit/cash_reconciliation -q -o addopts=""
node --test tests/frontend/cashAudit.test.mjs
```
