# Prompt — SPRINT DESPESAS_00.1 (correção rápida): avulsos sem contar títulos e baixas agrupadas

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). Somente leitura; nada é gravado no webPosto. `.env` só via `load_dotenv`. Sem reescrever arquivos inteiros. Rodar só `test_despesas_sem_lancamento.py` e os testes da BAIXA_00 durante o trabalho; bateria completa no final. Meta: 20 min.

@WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py
@WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py

## Erros encontrados pelo arquiteto na execução real (Doze, ago–set/2026)

1. **Mesmo débito em duas listas.** A BAIXA_00 diz que os débitos Ictus R$ 2.567,82 (12/08) e R$ 4.475,36 (02/09) pagaram os títulos VECTOR 3145129 e 3166170 ("prontos para baixar"), mas a DESPESAS_00 lista os mesmos débitos como **avulsos**. Se os dois fossem lançados, a despesa contaria **duas vezes**.
   → A DESPESAS_00 deve **reaproveitar o casamento da BAIXA_00** (`titulos_pagos_sem_baixa.py`): débito que a BAIXA_00 classificou como pronto, conferir à mão, ambíguo ou agrupado **não é avulso**; vai para um grupo "tem título em aberto — usar baixa". Sem duplicar código.
2. **Baixa agrupada não reconhecida.** O débito PIX IPSEP R$ 4.950,00 de 13/08 aparece como avulso, mas no webPosto existem **18 baixas de R$ 275,00 em 13/08 na conta PAGBANK DOZE FILIAL** do mesmo fornecedor (soma = R$ 4.950,00).
   → Um débito está "registrado" também quando bate com a **soma das baixas do mesmo fornecedor, na mesma data e conta** (`pagamento[]` de `V1/TITULOS_PAGAR`).
3. **Pagamento agrupado em aberto não detectado** (as duas sprints mostram 0 agrupados). PIX IPSEP R$ 5.880,00 de 15/09 = frete de agosto: 23 títulos IPSEP em aberto somando R$ 6.480,00 (diferença R$ 600,00).
   → Regra RN-ERP-003 "pagamento agrupado": débito com nome do fornecedor ≈ soma dos títulos **em aberto** desse fornecedor do mês anterior (tolerância ±15%) → "agrupado — conferir à mão", mostrando a diferença. Nem avulso, nem pronto.
4. **STATUS duplicado.** O agente criou `docs/status/STATUS.md`. O STATUS oficial é o `STATUS.md` da **raiz**. Mover o conteúdo novo para a raiz (seção curta) e apagar `docs/status/STATUS.md`.

Testes de regressão (sintéticos) para os 4 casos. Rodar de novo as duas reais do Doze (`baixar_titulos` com todos os extratos e `despesas_avulsas --de 01/08/2026 --ate 30/09/2026`) e mostrar os resumos no chat: os débitos Ictus e IPSEP não podem aparecer como avulsos.
Commit: `fix(despesas): avulsos sem títulos em aberto e baixas agrupadas`. Depois `git push`.
