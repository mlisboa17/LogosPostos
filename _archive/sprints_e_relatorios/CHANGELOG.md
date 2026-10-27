# Changelog

## 2026-05-08 - Fixes

- Fix: Update Pydantic model validators to correctly set computed fields (`diferenca`, `variacao_percentual`, `quebra_caixa`) in `models_auditoria.py`.
  - Ensures values are applied during model initialization and removes incompatible validator return patterns.
  - All unit tests now pass locally (`17 passed`).
