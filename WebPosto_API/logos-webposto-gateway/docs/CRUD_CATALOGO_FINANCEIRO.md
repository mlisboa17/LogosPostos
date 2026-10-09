# CRUD Catalogo e Financeiro

Este documento descreve o CRUD implementado para os modulos solicitados.

## Base

- Prefixo comum: `/v1/crud/{resource}`
- Metodos disponiveis por recurso:
  - `GET /v1/crud/{resource}`
  - `GET /v1/crud/{resource}/{id}`
  - `POST /v1/crud/{resource}`
  - `PUT /v1/crud/{resource}/{id}`
  - `DELETE /v1/crud/{resource}/{id}`

## Seguranca para escrita

- Todas as operacoes CRUD exigem header `X-Consumer-Token`.
- Operacoes `POST`, `PUT`, `DELETE` exigem header `X-Admin-Token`.
- Valor esperado: variavel de ambiente `ADMIN_TOKEN` (padrao local: `<ADMIN_TOKEN>`).

Exemplo:

```http
X-Consumer-Token: <CONSUMER_TOKEN>
X-Admin-Token: <ADMIN_TOKEN>
```

## Paginacao e filtros

No endpoint `GET /v1/crud/{resource}`:

- `offset` (default 0)
- `limit` (default 50, max 500)
- `status` (quando recurso tem campo status)
- `q` (busca textual em campos comuns)

Exemplo:

```http
GET /v1/crud/produtos?offset=0&limit=20&q=oleo
```

## Recursos implementados

- `grupos`
- `subgrupos`
- `produtos`
- `movimentacoes-caixa`
- `nfe-compras`
- `contas-a-pagar`
- `titulos-a-receber`
- `cartoes-a-receber`

## Exemplo rapido

### Criar grupo

```http
POST /v1/crud/grupos
Content-Type: application/json

{
  "nome": "Lubrificantes",
  "ativo": true
}
```

### Listar grupos

```http
GET /v1/crud/grupos
```

### Criar produto

```http
POST /v1/crud/produtos
Content-Type: application/json

{
  "subgrupo_id": 1,
  "sku": "SKU-001",
  "nome": "Oleo 5W30",
  "preco": "45.90",
  "ativo": true
}
```

### Registrar movimentacao de caixa

```http
POST /v1/crud/movimentacoes-caixa
Content-Type: application/json

{
  "posto_id": "23",
  "tipo": "DEBITO",
  "valor": "150.00",
  "descricao": "Sangria operador"
}
```

### Registrar NFE de compra

```http
POST /v1/crud/nfe-compras
Content-Type: application/json

{
  "numero_nfe": "123456",
  "fornecedor": "Distribuidora XPTO",
  "valor_total": "3240.50",
  "status": "aberta"
}
```

## Observacoes

- Valores monetarios usam `Decimal` no backend.
- IDs sao inteiros autoincrementais (exceto onde definido em outro fluxo).
- Este CRUD e base operacional para evoluir regras de negocio especificas por modulo.
- Validacoes de status e integridade referencial basica ja estao ativas (ex: grupo/subgrupo).
