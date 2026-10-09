# Guia de Consumo da API Logos Gateway

Este documento define como outros sistemas devem consumir a API na porta 8050.

## Base URL

- Local: `http://127.0.0.1:8050`
- Homolog/Prod: `https://api.seu-dominio.com.br`

## Endpoints

### GET /ready
Finalidade: readiness probe para orquestracao.

Resposta esperada:

```json
{
  "status": "ready",
  "service": "logos-gateway",
  "port": 8050
}
```

### GET /health
Finalidade: liveness operacional do gateway e SQLite local.

Resposta esperada:

```json
{
  "status": "healthy",
  "database": "up",
  "port": 8050,
  "service": "logos-gateway",
  "db_query_ms": 5.123,
  "external_dependencies": "ignored"
}
```

### GET /v1/expenses
Finalidade: retornar despesas de caixa normalizadas para o Logos.

Headers obrigatorios:
- `X-Consumer-Token`: token do sistema consumidor.
- `X-Posto-ID`: identificador do posto cadastrado no SQLite local.

Query params:
- `data_consulta` (opcional): datetime ISO 8601.

Exemplo de requisicao:

```http
GET /v1/expenses?data_consulta=2026-05-17T00:00:00
X-Consumer-Token: <CONSUMER_TOKEN>
X-Posto-ID: 23
```

Exemplo de resposta:

```json
{
  "posto_id": "23",
  "data_consulta": "2026-05-17T00:00:00",
  "total": 2,
  "items": [
    {
      "id": "wp_1001",
      "posto_id": "23",
      "valor": "150.50",
      "descricao": "Sangria caixa",
      "timestamp": "2026-05-17T09:12:00",
      "origem": "webposto"
    }
  ]
}
```

### GET /v1/products
Finalidade: retornar cadastro completo de produtos do posto no WebPosto.

Headers obrigatorios:
- `X-Consumer-Token`: token do sistema consumidor.
- `X-Posto-ID`: identificador do posto cadastrado no SQLite local.

Query params:
- `include_inactive` (opcional): `true/false`.
- `force_refresh` (opcional): ignora cache local quando `true`.

Exemplo de requisicao:

```http
GET /v1/products?include_inactive=false&force_refresh=false
X-Consumer-Token: <CONSUMER_TOKEN>
X-Posto-ID: 23
```

Exemplo de resposta:

```json
{
  "posto_id": "23",
  "total": 2,
  "items": [
    {
      "id": "9001",
      "codigo": "P-001",
      "sku": "P-001",
      "nome": "Gasolina Comum",
      "descricao": "Gasolina Comum",
      "unidade": "LT",
      "grupo": "Combustiveis",
      "subgrupo": "Gasolinas",
      "categoria": "Combustivel",
      "preco_venda": "5.89",
      "preco_custo": "5.10",
      "ativo": true,
      "ean": null,
      "ncm": null,
      "cest": null,
      "raw": {"...": "payload original"}
    }
  ]
}
```

## Regras de Negocio que o consumidor recebe prontas

- Somente movimentos com `tipo = DEBITO`.
- Protecao contra duplicidades relacionadas ao fluxo de exclusao financeira.
- Valores monetarios serializados como string decimal, sem ponto flutuante binario.
- Cache local de 5 minutos para mesma combinacao posto+data.

## Contrato JSON Schema

Arquivo:
- `consumer-kit/contracts/expenses.response.schema.json`

Uso recomendado:
- validar payload de resposta antes de persistir no sistema consumidor.

## Exemplo rapido para consumidor Python

Arquivos:
- `consumer-kit/python/gateway_client.py`
- `consumer-kit/python/example_consumer.py`

Execucao:

```powershell
Set-Location .\consumer-kit\python
pip install -r requirements.txt
python .\example_consumer.py
```

## Exemplo rapido para testes HTTP manuais

Arquivo:
- `consumer-kit/http/gateway_requests.http`

Use com extensao REST Client do VS Code.

## Tabela de erros para integradores

- `404`: posto nao configurado.
- `403`: posto inativo.
- `401`: consumidor nao autorizado (token invalido/ausente).
- `502/503`: indisponibilidade temporaria da integracao externa.

## Recomendacoes para outros sistemas

- Sempre enviar `X-Posto-ID`.
- Configurar timeout de cliente entre 10 e 15 segundos.
- Implementar retry curto para 502/503.
- Registrar logs por posto e data_consulta para rastreabilidade.

