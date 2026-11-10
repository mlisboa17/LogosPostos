# Instruções para assistentes de IA (Copilot, Codex, Cursor, Claude)

## API do webPosto (ERP dos postos — Quality Automação)

Antes de responder qualquer pergunta ou escrever código que use rotas `/INTEGRACAO` do webPosto:

1. Leia `docs/external/webposto/CATALOGO_API.md`: regras, todas as rotas e o resultado do teste real de cada leitura.
2. Para detalhes de campos, use a OpenAPI mais recente em `docs/external/webposto/openapi_integracao_<data>.json`.
3. Armadilhas confirmadas e o passo a passo para sondar com segurança: `.claude/skills/webposto-api/SKILL.md`.

Regras obrigatórias:
- **Nunca** chamar nem propor chamar POST/PUT/PATCH/DELETE sem aprovação explícita do diretor: grava no ERP de produção.
- **Nunca** imprimir, logar, commitar ou pedir a `CHAVE` de integração. Ela vê a rede inteira. Ler do `.env` (`WEBPOSTO_API_KEY_*`).
- Ao testar uma rota, só GET, com `empresaCodigo`, período curto e `limite` pequeno; mostrar só estrutura e contagens, nunca dados de clientes.
- Reutilizar `src.modules.webposto_integration.http.paginar` em vez de criar cliente HTTP novo.
- Se o catálogo tiver mais de 30 dias, atualize: `WebPosto_API/scripts/webposto_catalogo.py baixar`, `sondar`, `gerar`.

## Projeto
- Logos Match: `WebPosto_API/apps/match/` (README e `STATUS.md` na raiz dizem onde paramos).
- Testes: `cd WebPosto_API && .venv/Scripts/python -m pytest tests/unit/match tests/unit/fiscal_docs tests/unit/cash_reconciliation -q`.
- Datas exibidas em dd/mm/aaaa, fuso America/Recife. Commits em português. Não commitar `.env`, `dist/`, `build/`.
