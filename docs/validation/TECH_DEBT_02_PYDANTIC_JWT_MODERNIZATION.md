# TECH-DEBT-02 — Modernização Pydantic e timestamps JWT

Data: 22/10/2026

## Escopo

Modernização offline e compatível com Pydantic v2, sem alteração de regras financeiras, integrações externas ou dados produtivos.

## Alterações

- `cliente_dto.py`: `@validator` substituído por `@field_validator`; configuração ORM migrada para `ConfigDict(from_attributes=True)`.
- `settings.py`: configuração interna migrada para `SettingsConfigDict`.
- `jwt_utils.py`: timestamps JWT passaram de `datetime.utcnow()` para `datetime.now(timezone.utc)`.

## Validação

- Autenticação e serviço de clientes: `16 passed`.
- Autenticação + cash reconciliation após isolamento da chave JWT de testes: `681 passed`, zero warnings.
- Isolamento Premmia: zero tentativas reais de navegador/portal.
- Redução dos avisos da suíte cash reconciliation: `151 → 92`.

O fixture global agora injeta uma chave JWT exclusiva de testes com comprimento adequado. Nenhuma chave, segredo, `.env` ou configuração de produção foi lida ou alterada nesta etapa.

## Travas preservadas

- `ACCOUNT 27173: BLOCKED`.
- Conta 27173 permanece `TRANSITORIA` e sem débito para despesas.
- `CASA CAIADA PILOT: BLOCKED`.
- `CADEIA MAIS PAGAMENTOS: BLOCKED`.
- Zero chamadas ERP, portal ou API externa.
