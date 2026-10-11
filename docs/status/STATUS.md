# STATUS DO SISTEMA LOGOS — AUDITORIA E ERP

**Data de atualização:** 11/10/2026  
**Branch:** `feature/cash-audit-fechamento`  
**Escopo:** SPRINT BAIXA_00 (Parte A) e SPRINT DESPESAS_00 (Parte A) — Somente Leitura

---

## 1. SPRINT BAIXA_00 (Parte A — Somente Leitura)
- **Objetivo:** Identificar títulos em aberto no webPosto que já foram quitados nos extratos bancários (Banco do Brasil e PagBank).
- **Módulo:** `src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py`
- **CLI:** `python -m src.jobs.baixar_titulos --unidade 74014`
- **Regras implementadas:**
  - Janela de busca: `vencimento - 10` a `+ 40` dias;
  - Deduplicação de extratos por `FITID`;
  - Exclusão de débitos consumidos por títulos baixados (`dataPagamento +- 1` dia, valor exato);
  - Filtro de transferências internas entre contas/empresas do grupo e aplicações automáticas;
  - Resolução de fornecedores via razão social, fantasia e aliases;
  - Resolução de contas de liquidação via `units.json` (`86248` BB, `86188` PagBank);
  - Classificação estrita em: prontos para baixar, conferir à mão, ambíguos e agrupados.
- **Resultado real Doze (74014):**
  - Prontos para baixar: 13 títulos (R$ 202.220,07)
  - Conferir à mão: 2 títulos (R$ 2.850,00)
  - Ambíguos: 35 títulos (R$ 42.530,79)
  - Agrupados: 0 títulos
- **Status:** Concluído e testado.

---

## 2. SPRINT DESPESAS_00 (Parte A — Somente Leitura)
- **Objetivo:** Identificar débitos de extrato sem nenhum registro no ERP (nem título/baixa em `V1/TITULOS_PAGAR`, nem lançamento em `V1/MOVIMENTOS_CONTA`), correspondendo a despesas pagas "na rua".
- **Módulo:** `src/modules/cash_reconciliation/application/despesas_sem_lancamento.py`
- **CLI:** `python -m src.jobs.despesas_avulsas --unidade 74014 --de 01/08/2026 --ate 30/09/2026`
- **Regras implementadas:**
  - Leitura dos OFX da unidade com deduplicação por `FITID`;
  - Filtro de transferências para empresas do grupo (Posto VIP, Casa Caiada, Igarassu, Posto Real, Loja de Conveniência, Posto Doze/CCD, Alexandre, Posto Avenida);
  - Filtro de aplicações bancárias automáticas e tarifas/seguros bancários;
  - Verificação de registros prévios: baixa de título (`pagamento[]`), débitos de `V1/MOVIMENTOS_CONTA`, títulos em aberto (`vencimento -10/+40` dias) e pagamentos agrupados;
  - Classificação dos débitos restantes por tipo: PIX pessoa, QR Code, boleto e imposto;
  - Alerta especial para FGTS / CEF Matriz: `conferir - folha`;
  - Sugestão de classificação (Plano de Contas e Centro de Custo) aprendida do histórico de títulos e movimentos manuais anteriores, com fallback para `A CLASSIFICAR`;
  - Exportação em relatório no terminal e planilha Excel XLSX em `data/despesas_avulsas/`.
- **Resultado real Doze (74014, ago-set/2026):**
  - Despesas avulsas identificadas: 63 lançamentos (R$ 113.326,52)
  - PIX pessoa: 26 lançamentos (R$ 68.452,35 | 60.4%)
  - Boleto: 16 lançamentos (R$ 23.951,15 | 21.1%)
  - QR Code: 16 lançamentos (R$ 10.574,49 | 9.3%)
  - Imposto: 5 lançamentos (R$ 10.348,53 | 9.1%)
  - Débitos ignorados (grupo/aplicação/tarifa): 185 (R$ 2.504.559,53)
  - Débitos já registrados no webPosto: 25 (R$ 92.230,03)
- **Status:** Concluído e testado.

---

## 3. Próximos Passos
- **Parte B:** Fila local com leitura de comprovantes e áudio via Telegram/Gemini (sem gravar no webPosto).
- **Sprint DESPESAS_01:** Escrita de lançamentos avulsos com barreira de segurança estrita.
