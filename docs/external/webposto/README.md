# Especificação oficial — API de Integração webPosto (Quality Automação)

Cópia de referência do contrato publicado pelo fornecedor. **Fonte da verdade para rotas, parâmetros e schemas do ERP**; código e relatórios locais devem ser cruzados com ela.

| Arquivo | Origem | Capturado em | SHA-256 do original |
|---|---|---|---|
| `openapi_integracao_2026-10-06.json` | `https://web.qualityautomacao.com.br/v3/api-docs/integracao` (Swagger UI: `/webjars/swagger-ui/index.html?configUrl=/v3/api-docs/swagger-config`) | 2026-10-06 | `256a34a396bd79febd6f61a69677c14bd450014ec4c95a4f6abe08b24a6a0ee7` |

O JSON foi apenas reformatado (indentação) para facilitar diffs; o hash refere-se ao download bruto.

## Observações
- OpenAPI 3.1, 156 paths. A spec publica rotas **V1/V2**; rotas legadas usadas no código (`/INTEGRACAO/CAIXA`, `CAIXA_APRESENTADO`, `FECHAMENTO_CAIXA`, `FINANCEIRO_EXCLUSAO`, `CONSULTAR_*_REDE`) **não constam** nela.
- Paginação V1: cursor `ultimoCodigo` + `limite` (não `pagina`/`tamanhoPagina`). Filtro de filial: `empresaCodigo`.
- A spec não declara `securitySchemes`; a autenticação real é o parâmetro `CHAVE` (ver `security/ARCH01_SECRET_AUDIT_RUNBOOK.md`). Nunca adicionar exemplos com chave real a esta pasta.

## Atualização
Baixar novamente, salvar como `openapi_integracao_<AAAA-MM-DD>.json`, registrar hash nesta tabela e comparar `paths` com a versão anterior.
