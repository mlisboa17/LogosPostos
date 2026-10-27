# 🐚 EXEMPLOS cURL — Testar Token Diretamente

**Token:** Veja `.env` (não exponha em exemplos)  
**Base URL:** `https://api.webposto.com.br`  
**Local API:** `http://localhost:8000`

---

## 🚀 OPERAÇÕES RÁPIDAS

### ✅ 1. CONSULTAR ABASTECIMENTOS DE HOJE

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/ABASTECIMENTO?CHAVE=$WEBPOSTO_CHAVE&data_inicio=2026-05-08&data_fim=2026-05-08&pagina=1&limite=100" \
  -H "Content-Type: application/json"
```

**Resultado esperado:**
```json
{
  "data": [
    {
      "id": "ABC123",
      "cliente_id": "CLI001",
      "valor": 250.50,
      "litros": 100.0,
      "combustivel": "Gasolina Comum"
    }
  ],
  "total": 1250
}
```

---

### ✅ 2. LISTAR CLIENTES

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/CLIENTE?CHAVE=$WEBPOSTO_CHAVE&pagina=1&limite=50"
```

---

### ✅ 3. LISTAR PRODUTOS

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/PRODUTO?CHAVE=$WEBPOSTO_CHAVE&pagina=1&limite=50"
```

---

### ✅ 4. LISTAR TÍTULOS A RECEBER

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/TITULO_RECEBER?CHAVE=$WEBPOSTO_CHAVE&status=pendente&pagina=1&limite=50"
```

---

### ✅ 5. LISTAR TÍTULOS A PAGAR

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/TITULO_PAGAR?CHAVE=$WEBPOSTO_CHAVE&pagina=1&limite=50"
```

---

### ✅ 6. LISTAR MOVIMENTOS DE CAIXA

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/CAIXA?CHAVE=$WEBPOSTO_CHAVE&data_inicio=2026-05-08&data_fim=2026-05-08"
```

---

### ✅ 7. GERAR RELATÓRIO DE VENDAS

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL?CHAVE=$WEBPOSTO_CHAVE&data_inicio=2026-05-01&data_fim=2026-05-31"
```

---

### ✅ 8. RELATÓRIO DE ESTOQUE

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/RELATORIO/ESTOQUE?CHAVE=$WEBPOSTO_CHAVE"
```

---

## ➕ CRIAR DADOS

### ✅ 1. CRIAR NOVO TÍTULO A RECEBER

```bash
curl -X POST "http://localhost:8000/api/v1/financeiro" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: seu-usuario" \
  -H "X-Motivo: Venda realizada hoje" \
  -d '{
    "tipo": "RECEBER",
    "valor": 5000.00,
    "data_vencimento": "2026-06-08T00:00:00Z",
    "descricao": "Fatura de venda - Pedido #12345",
    "cliente_fornecedor": "Transportadora ABC Ltda",
    "categoria": "Vendas"
  }'
```

**Resposta:**
```json
{
  "status": "success",
  "mensagem": "Título criado com sucesso",
  "dados": {
    "id": "TIT_ABC123XYZ",
    "tipo": "RECEBER",
    "valor": 5000.00,
    "status": "pendente",
    "data_criacao": "2026-05-08T18:30:45Z"
  }
}
```

---

### ✅ 2. CRIAR NOVO CLIENTE

```bash
curl -X POST "http://localhost:8000/api/v1/clientes" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: gerente" \
  -H "X-Motivo: Novo cliente cadastrado" \
  -d '{
    "razao_social": "Nova Transportadora Ltda",
    "nome_fantasia": "Nova Transportes",
    "cnpj": "98.765.432/0001-12",
    "contato": "João Silva",
    "telefone": "(11) 99999-8888",
    "email": "contato@nova.com.br",
    "endereco": "Avenida Principal, 999",
    "cidade": "São Paulo",
    "estado": "SP",
    "credito_limite": 100000.00
  }'
```

---

### ✅ 3. CRIAR MOVIMENTO DE CAIXA

```bash
curl -X POST "http://localhost:8000/api/v1/caixa/movimentos" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: operador_caixa" \
  -H "X-Motivo: Entrada de vendas - Turno 1" \
  -d '{
    "descricao": "Entrada de vendas - Turno 1",
    "valor": 5500.00,
    "tipo": "entrada",
    "categoria": "vendas",
    "referencia": "TURNO_1_08_05_2026"
  }'
```

---

## ✏️ ATUALIZAR DADOS

### ✅ 1. ATUALIZAR TÍTULO (Marcar como Pago)

**Passo 1: Obter ID do título**
```bash
curl -X GET "http://localhost:8000/api/v1/financeiro?status=pendente&tipo=RECEBER" \
  -H "Content-Type: application/json"
```

Copie o `id` do título retornado.

**Passo 2: Atualizar**
```bash
curl -X PUT "http://localhost:8000/api/v1/financeiro/TIT_ABC123XYZ" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: gerente_financeiro" \
  -H "X-Motivo: Recebimento confirmado via transferência" \
  -d '{
    "pago": true,
    "data_pagamento": "2026-05-08T14:50:00Z",
    "valor": 5200.00
  }'
```

**Resposta:**
```json
{
  "status": "success",
  "mensagem": "Título atualizado com sucesso",
  "dados": {
    "id": "TIT_ABC123XYZ",
    "pago": true,
    "valor": 5200.00,
    "data_atualizacao": "2026-05-08T18:35:20Z"
  }
}
```

---

### ✅ 2. ATUALIZAR CLIENTE

```bash
curl -X PUT "http://localhost:8000/api/v1/clientes/CLI_XYZ123" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: gerente" \
  -H "X-Motivo: Aumento de crédito liberado" \
  -d '{
    "credito_limite": 150000.00,
    "telefone": "(11) 98888-7777"
  }'
```

---

## 🗑️ DELETAR DADOS

### ✅ 1. DELETAR TÍTULO

```bash
curl -X DELETE "http://localhost:8000/api/v1/financeiro/TIT_ABC123XYZ" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: gerente" \
  -H "X-Motivo: Duplicata removida"
```

**Resposta:**
```json
{
  "status": "success",
  "mensagem": "Título deletado com sucesso",
  "dados": {
    "id": "TIT_ABC123XYZ",
    "status": "cancelado",
    "data_cancelamento": "2026-05-08T18:40:00Z"
  }
}
```

---

## 🔗 FLUXO COMPLETO DE EXEMPLO

### Cenário: Registrar uma venda do dia

**1️⃣ Consultar se o cliente existe**

```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/CLIENTE?CHAVE=$WEBPOSTO_CHAVE&pagina=1&limite=100" \
  | grep "Transportadora ABC"
```

Se não encontrar, criar cliente:

```bash
curl -X POST "http://localhost:8000/api/v1/clientes" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: vendedor" \
  -H "X-Motivo: Novo cliente para venda" \
  -d '{
    "razao_social": "Transportadora ABC Ltda",
    "nome_fantasia": "ABC Transportes",
    "cnpj": "12.345.678/0001-90",
    "contato": "João Silva",
    "telefone": "(11) 98765-4321",
    "email": "contato@abc.com.br",
    "endereco": "Rua das Flores, 123",
    "cidade": "São Paulo",
    "estado": "SP",
    "credito_limite": 50000.00
  }'
```

**2️⃣ Criar título de receber (fatura)**

```bash
curl -X POST "http://localhost:8000/api/v1/financeiro" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: vendedor" \
  -H "X-Motivo: Venda de combustível - Pedido #12345" \
  -d '{
    "tipo": "RECEBER",
    "valor": 2500.00,
    "data_vencimento": "2026-06-08T00:00:00Z",
    "descricao": "Venda de Gasolina - Pedido #12345",
    "cliente_fornecedor": "Transportadora ABC Ltda",
    "categoria": "Vendas"
  }'
```

Copie o `id` retornado (ex: `TIT_ABC123XYZ`)

**3️⃣ Registrar entrada no caixa**

```bash
curl -X POST "http://localhost:8000/api/v1/caixa/movimentos" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: caixa" \
  -H "X-Motivo: Entrada - Venda Transportadora ABC" \
  -d '{
    "descricao": "Venda Transportadora ABC - Pedido #12345",
    "valor": 2500.00,
    "tipo": "entrada",
    "categoria": "vendas",
    "referencia": "TIT_ABC123XYZ"
  }'
```

**4️⃣ Confirmar recebimento posterior**

```bash
curl -X PUT "http://localhost:8000/api/v1/financeiro/TIT_ABC123XYZ" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: gerente_financeiro" \
  -H "X-Motivo: Recebimento confirmado - Transferência bancária" \
  -d '{
    "pago": true,
    "data_pagamento": "2026-05-10T15:30:00Z"
  }'
```

---

## 📋 LISTA DE TODOS OS ENDPOINTS GET

| Endpoint | URL Completa |
|----------|-------------|
| Abastecimentos | `/INTEGRACAO/ABASTECIMENTO` |
| Divergências Abastecimento | `/INTEGRACAO/ABASTECIMENTO_DIVERGENCIA` |
| Encerrantes | `/INTEGRACAO/ABASTECIMENTO_ENCERRANTE` |
| Clientes | `/INTEGRACAO/CLIENTE` |
| Frota | `/INTEGRACAO/CLIENTE_FROTA` |
| Grupos Clientes | `/INTEGRACAO/GRUPO_CLIENTE` |
| Adiantamentos Fornecedor | `/INTEGRACAO/ADIANTAMENTO_FORNECEDOR` |
| Caixa | `/INTEGRACAO/CAIXA` |
| Caixa Apresentado vs Apurado | `/INTEGRACAO/CAIXA_APRESENTADO` |
| Cartão - Pagamento | `/INTEGRACAO/CARTAO_PAGAR` |
| Cartão - Compra | `/INTEGRACAO/CARTAO_COMPRA` |
| Cartão - Remessa | `/INTEGRACAO/CARTAO_REMESSA` |
| Fechamento Caixa | `/INTEGRACAO/FECHAMENTO_CAIXA` |
| Financeiro Exclusão | `/INTEGRACAO/FINANCEIRO_EXCLUSAO` |
| Movimento Conta | `/INTEGRACAO/MOVIMENTO_CONTA` |
| Plano Contas | `/INTEGRACAO/PLANO_DE_CONTAS` |
| Transferência | `/INTEGRACAO/TRANSFERENCIA` |
| Transferência Bancária | `/INTEGRACAO/TRANSFERENCIA_BANCARIA` |
| Títulos Pagar | `/INTEGRACAO/TITULO_PAGAR` |
| Títulos Receber | `/INTEGRACAO/TITULO_RECEBER` |
| APRIX Custo | `/INTEGRACAO/APRIX_CUSTO` |
| Distribuidoras | `/INTEGRACAO/DISTRIBUIDORA` |
| LMC | `/INTEGRACAO/LMC` |
| Pedidos Combustível | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO` |
| Combustível | `/INTEGRACAO/COMBUSTIVEL` |
| Estoque | `/INTEGRACAO/ESTOQUE` |
| Itens Inventário | `/INTEGRACAO/PRODUTO_INVENTARIO_ITENS` |
| Lista Itens | `/INTEGRACAO/LISTA_DE_ITENS` |
| Produtos | `/INTEGRACAO/PRODUTO` |
| Preço Produto | `/INTEGRACAO/PRECO_PRODUTO` |
| Tributo ICMS | `/INTEGRACAO/INTEGRACAO_PRODUTO_TRIBUTO_ICMS` |
| Tributo PIS/COFINS | `/INTEGRACAO/INTEGRACAO_PRODUTO_TRIBUTO_PIS_CONFINS` |
| Rel. Estoque | `/INTEGRACAO/RELATORIO/ESTOQUE` |
| Rel. Venda Combustível | `/INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL` |
| Rel. Venda Produto | `/INTEGRACAO/RELATORIO/VENDA_PRODUTO` |
| Resumo Vendas | `/INTEGRACAO/RELATORIO/RESUMO_VENDAS` |
| Administradoras | `/INTEGRACAO/ADMINISTRADORA` |
| Filiais | `/INTEGRACAO/FILIAL` |
| NF Entrada | `/INTEGRACAO/NOTA_FISCAL_ENTRADA` |
| NF Saída | `/INTEGRACAO/NOTA_FISCAL_SAIDA` |
| Pedidos Compras | `/INTEGRACAO/PEDIDO_COMPRAS` |
| Prazo Tabela Preço | `/INTEGRACAO/PRAZO_TABELA_PRECO` |
| Usuário Empresa Rede | `/INTEGRACAO/USUARIO_EMPRESA_REDE` |
| Usuários | `/INTEGRACAO/USUARIO` |
| Vendas | `/INTEGRACAO/VENDA` |
| Vendas Rede | `/INTEGRACAO/VENDA_REDE` |

---

## 🔧 COMO USAR COM POSTMAN

**1. Criar nova requisição**

**2. Method:** GET/POST/PUT/DELETE

**3. URL:** `http://localhost:8000/api/v1/...` (ou https://api.webposto.com.br/INTEGRACAO/...)

**4. Headers:**
```
Content-Type: application/json
X-Usuario: seu-usuario
X-Motivo: Descrição clara
CHAVE: $WEBPOSTO_CHAVE  (para GET na API externa, carregada de .env)
```

**5. Body (para POST/PUT):**
```json
{
  "tipo": "RECEBER",
  "valor": 5000.00,
  ...
}
```

**6. Send!**

---

## 💡 DICAS

**1. Testar rápido em Linux/Mac:**
```bash
# Salvar este arquivo e fazer:
chmod +x exemplos_curl.sh
./exemplos_curl.sh
```

**2. Capturar resposta em arquivo:**
```bash
curl -X GET "https://..." > resultado.json
cat resultado.json | jq .
```

**3. Ver apenas headers:**
```bash
curl -i -X GET "https://..."
```

**4. Timeout customizado:**
```bash
curl --max-time 10 -X GET "https://..."
```

**5. Usar variáveis de ambiente:**
```bash
export TOKEN="$WEBPOSTO_CHAVE"  # Carregue de .env
curl -X GET "https://api.webposto.com.br/INTEGRACAO/CLIENTE?CHAVE=$TOKEN"
```

---

**Pronto para testar!** 🚀
