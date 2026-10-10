# Prompt — CASH-AUDIT-04: Padrão Brasil para datas, horas e fuso

> Executar **depois** de concluir e commitar a fase em andamento. Fase própria, com testes e commit.

## Regra (vale para todo o módulo `src/modules/cash_reconciliation/` e para a tela `frontend/pages/cashAudit.js`)

1. **Fuso único: `America/Recife`** (horário de Brasília, UTC−3, sem horário de verão — unidades em Pernambuco).
   Crie `src/modules/cash_reconciliation/domain/tempo.py` com:
   - `FUSO = ZoneInfo("America/Recife")`
   - `agora() -> datetime` (com fuso), `hoje() -> date`, `ontem() -> date`
   - `para_local(dt) -> datetime`: datetime com fuso → converte para Recife; datetime sem fuso → assume que já é horário de Brasília.
   - `formatar_data(d) -> "07/10/2026"`, `formatar_hora(dt) -> "14:05"`, `formatar_data_hora(dt) -> "07/10/2026 14:05"`
   - `ler_data(texto)` aceitando `07/10/2026` **e** `2026-10-07`.
2. **Proibido no módulo:** `datetime.now()`, `date.today()`, `datetime.utcnow()` ou `.replace(tzinfo=None)` para "jogar fora" o fuso. Use os helpers. Substitua os usos atuais (proveniência `executado_em` em `auditar_fechamento.py`, `conciliar.py`, `conciliar_cartoes.py`, `interfaces/http.py`, `jobs/noturno.py`; `--dia` padrão do robô; `para_abastecimento` e PIX em `adapters/webposto_cartoes.py`).
3. **Dados de fontes externas** (webPosto, PagBank, Premmia, Mais Pagamentos): normalizar com `para_local`. Se a fonte mandar UTC/`Z`, **converter** (não cortar).
4. **Transporte técnico continua ISO 8601** — parâmetros de API, JSON, nomes de pastas/arquivos (`data/cash_audit/2026-10-07/`) e chamadas às APIs externas usam `AAAA-MM-DD` / `AAAA-MM-DDTHH:MM:SS-03:00`. Isso não aparece para o usuário e evita ambiguidade.
5. **Tudo que o usuário vê é pt-BR:** datas `dd/mm/aaaa`, horas `HH:mm` (24h), data e hora `dd/mm/aaaa HH:mm`, moeda `R$ 1.234,56`. Inclui: tela, mensagens de alerta, resumos/logs legíveis do robô noturno, relatórios/CSV/exportações.
   - Frontend: centralize em `frontend/services/format.js` (`formatDate` já é pt-BR; adicione `formatTime` e `formatDateTime` com `Intl.DateTimeFormat("pt-BR", { timeZone: "America/Recife" })`). Em `cashAudit.js`, troque recortes de string (`slice(11, 19)`, `item.dia` cru, `executado_em` cru) pelos formatadores.
   - Campos de data do formulário com `lang="pt-BR"`; padrão do período calculado no fuso de Recife (não UTC).
6. **Robô noturno:** `--dia` padrão = `ontem()` no fuso de Recife; aceitar `--dia 07/10/2026` e `--dia 2026-10-07`. O `registrar_robo_noturno.ps1` deve avisar se o fuso do Windows não for UTC−03:00 (03:00 = horário de Brasília).
7. **Dependência:** declarar `tzdata` em `pyproject.toml` e `requirements.txt` (no Windows o `zoneinfo` não funciona sem ele).

## Testes obrigatórios

- `ontem()` perto da meia-noite: 08/10/2026 01:00 UTC → 07/10/2026 22:00 em Recife → `ontem()` = 06/10/2026.
- `para_local`: `2026-10-05T03:28:48Z` → 05/10/2026 00:28:48 Recife; sem fuso → inalterado.
- `formatar_*` e `ler_data` (os dois formatos; data inválida → erro claro em português).
- Proveniência com fuso `-03:00`.
- Teste que falha se aparecer `datetime.now(`, `date.today(` ou `utcnow(` em `src/modules/cash_reconciliation/` (varredura simples dos arquivos .py).

Rodar `python -m pytest tests/unit/cash_reconciliation -q -o addopts=""`, conferir a tela no navegador, commit `fix(cash-audit): padrão Brasil para datas, horas e fuso`.
