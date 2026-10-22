# CHECKPOINT — TECH-DEBT-03

Data: 22/10/2026

## Autorização do proprietário

O proprietário autorizou explicitamente:

- remover `dependencies-mlisboa17.py`;
- remover `main-mlisboa17.py`;
- remover os quatro scripts `scratch_*.py` auditados no TECH-DEBT-01;
- mover `probe_premmia_portal.py` para uma pasta de ferramentas em quarentena, sem executá-lo;
- realizar push da branch atual, sem merge.

Também determinou conferência visual prévia da agência `2365-5` no webPosto antes de qualquer decisão sobre a conta 27173. Reclassificação e piloto continuam não autorizados.

## Resultado

- Arquivos históricos corrompidos removidos.
- Rascunhos `scratch_*` removidos.
- Probe Premmia preservado em `WebPosto_API/tools/premmia/quarantine/`.
- Probe não executado.
- `python -m compileall -q WebPosto_API/src`: aprovado (`exit 0`).
- Master data + autenticação + cash reconciliation: `737 passed`.
- Isolamento Premmia: zero tentativas reais de navegador/portal.
- Conta 27173 permanece `TRANSITORIA`, sem débito.
- Piloto Casa Caiada permanece `BLOCKED`.

