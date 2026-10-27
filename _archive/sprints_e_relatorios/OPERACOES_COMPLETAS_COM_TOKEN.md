# 🔐 OPERAÇÕES COMPLETAS COM SEU TOKEN WebPosto

**Token:** Veja `.env` (não exponha)  
**Base URL:** `https://api.webposto.com.br`  
**Data:** 2026-05-08

---

## 📋 SUMÁRIO EXECUTIVO

Com seu token atual você pode:

| Categoria | Operações | Status |
|-----------|-----------|--------|
| **Consultar (GET)** | 51 endpoints | ✅ Pleno Acesso |
| **Criar (POST)** | Títulos, Movimentos, Notas | ✅ Liberado |
| **Alterar (PUT)** | Títulos, Clientes, Movimentos | ✅ Liberado |
| **Deletar (DELETE)** | Soft Delete com auditoria | ✅ Liberado |
| **Auditoria** | Rastreamento completo de tudo | ✅ Ativo |

---

## 🔍 1. OPERAÇÕES DE LEITURA (GET) — 51 ENDPOINTS

### 1.1 **ABASTECIMENTO** (Combustível)

#### ✅ Listar Abastecimentos
```bash
GET /INTEGRACAO/ABASTECIMENTO
```
**Parâmetros:**
- `data_inicio` (obrigatório) - formato ISO
- `data_fim` (obrigatório) - formato ISO
- `pagina` - número da página
- `limite` - registros por página
- `filtro` - campos para filtrar

**Exemplo cURL:**
```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/ABASTECIMENTO?CHAVE=$WEBPOSTO_CHAVE&data_inicio=2026-01-01&data_fim=2026-05-08&pagina=1&limite=100"
```

**Retorna:**
```json
{
  "data": [
    {
      "id": "ABC123",
      "cliente_id": "CLI001",
      "data": "2026-05-07T10:30:00",
      "valor": 250.50,
      "litros": 100.0,
      "produto_id": "GASOLINA_COMUM",
      "bomba": "BOMBA_1",
      "combustivel": "Gasolina Comum",
      "procedencia": "Distribuidor XYZ"
    }
  ],
  "total": 1250,
  "pagina": 1
}
```

---

#### ✅ Divergências de Abastecimento
```bash
GET /INTEGRACAO/ABASTECIMENTO_DIVERGENCIA
```
**Retorna:** Abastecimentos que tiveram discrepâncias

**Exemplo:**
```json
{
  "divergencias": [
    {
      "abastecimento_id": "ABC123",
      "valor_esperado": 250.50,
      "valor_informado": 248.75,
      "diferenca": -1.75,
      "percentual": "-0.70%"
    }
  ]
}
```

---

#### ✅ Encerrantes de Abastecimento
```bash
GET /INTEGRACAO/ABASTECIMENTO_ENCERRANTE
```
**Retorna:** Leitura final dos medidores (odômetros/horímetros)

**Exemplo:**
```json
{
  "encerrantes": [
    {
      "data": "2026-05-08",
      "veiculo_id": "VEI001",
      "odometro": 125450,
      "horímetro": 1250
    }
  ]
}
```

---

### 1.2 **CLIENTES**

#### ✅ Listar Clientes
```bash
GET /INTEGRACAO/CLIENTE
```

**Retorna:**
```json
{
  "clientes": [
    {
      "id": "CLI001",
      "razao_social": "Transportadora ABC Ltda",
      "nome_fantasia": "ABC Transportes",
      "cnpj": "12.345.678/0001-90",
      "cpf": null,
      "contato": "João Silva",
      "telefone": "(11) 98765-4321",
      "email": "contato@abc.com.br",
      "endereco": "Rua das Flores, 123",
      "cidade": "São Paulo",
      "estado": "SP",
      "ativo": true,
      "data_cadastro": "2025-01-15",
      "credito_limite": 50000.00
    }
  ],
  "total": 157
}
```

---

#### ✅ Frota (Veículos por Cliente)
```bash
GET /INTEGRACAO/CLIENTE_FROTA
```

**Retorna:**
```json
{
  "cliente_id": "CLI001",
  "frota": [
    {
      "id": "VEI001",
      "placa": "ABC-1234",
      "marca": "Scania",
      "modelo": "R440",
      "ano": 2020,
      "km_atual": 125450,
      "combustivel": "Diesel",
      "capacidade_tanque": 300,
      "status": "ativo"
    }
  ]
}
```

---

#### ✅ Grupos de Clientes
```bash
GET /INTEGRACAO/GRUPO_CLIENTE
```

**Retorna:**
```json
{
  "grupos": [
    {
      "id": "GRP001",
      "nome": "Clientes Premium",
      "descricao": "Clientes com maior volume",
      "quantidade_clientes": 45
    }
  ]
}
```

---

### 1.3 **FINANCEIRO** (Títulos a Receber/Pagar)

#### ✅ Listar Títulos a Receber
```bash
GET /INTEGRACAO/TITULO_RECEBER
```

**Parâmetros:**
- `data_inicio` - filtrar por período
- `data_fim` - filtrar por período
- `status` - pendente, pago, vencido, cancelado
- `cliente_id` - filtrar por cliente

**Retorna:**
```json
{
  "titulos": [
    {
      "id": "TIT001",
      "numero_nf": "NF-12345",
      "cliente_id": "CLI001",
      "cliente_nome": "Transportadora ABC",
      "valor": 5000.00,
      "data_emissao": "2026-04-15",
      "data_vencimento": "2026-05-15",
      "data_pagamento": null,
      "status": "pendente",
      "dias_vencido": 0,
      "juros": 0.00,
      "multa": 0.00,
      "desconto": 0.00
    }
  ],
  "total_a_receber": 145000.50,
  "total_vencido": 12500.00
}
```

---

#### ✅ Listar Títulos a Pagar
```bash
GET /INTEGRACAO/TITULO_PAGAR
```

**Retorna:** Mesma estrutura, porém com fornecedores em vez de clientes

---

#### ✅ Caixa (Turnos / Movimentos)
```bash
GET /INTEGRACAO/CAIXA
```

**Parâmetros:**
- `data_inicio` - início do período
- `data_fim` - fim do período

**Retorna:**
```json
{
  "movimentos": [
    {
      "id": "CAIXA001",
      "data": "2026-05-08",
      "turno": 1,
      "operador": "Maria Silva",
      "saldo_abertura": 1000.00,
      "entradas": 5500.00,
      "saidas": 2000.00,
      "saldo_fechamento": 4500.00,
      "diferenca": 0.00,
      "status": "fechado"
    }
  ]
}
```

---

#### ✅ Caixa: Apresentado × Apurado
```bash
GET /INTEGRACAO/CAIXA_APRESENTADO
```

**Retorna:** Comparação entre valor declarado vs. realizado

```json
{
  "comparativo": [
    {
      "data": "2026-05-08",
      "valor_apresentado": 4500.00,
      "valor_apurado": 4500.00,
      "diferenca": 0.00,
      "percentual_diferenca": "0.00%"
    }
  ]
}
```

---

#### ✅ Cartão de Crédito - Compras
```bash
GET /INTEGRACAO/CARTAO_COMPRA
```

**Retorna:** Todas as compras feitas em cartão

```json
{
  "compras": [
    {
      "id": "CART001",
      "data": "2026-05-07",
      "cartao_final": "****1234",
      "bandeira": "Visa",
      "merchant": "Abastecimento SP",
      "valor": 350.00,
      "parcelas": 1,
      "status": "autorizado"
    }
  ]
}
```

---

#### ✅ Cartão - A Pagar
```bash
GET /INTEGRACAO/CARTAO_PAGAR
```

**Retorna:** Resumo do que será cobrado nos cartões

---

#### ✅ Movimento de Conta
```bash
GET /INTEGRACAO/MOVIMENTO_CONTA
```

**Parâmetros:**
- `data_inicio`
- `data_fim`
- `conta_id` (opcional)

**Retorna:**
```json
{
  "movimentos": [
    {
      "data": "2026-05-08",
      "descricao": "Depósito Clientes",
      "valor": 15000.00,
      "tipo": "entrada",
      "saldo_anterior": 50000.00,
      "saldo_novo": 65000.00,
      "banco": "Banco ABC",
      "conta": "123456-7"
    }
  ]
}
```

---

#### ✅ Plano de Contas
```bash
GET /INTEGRACAO/PLANO_DE_CONTAS
```

**Retorna:** Estrutura contábil (contas, grupos, subgrupos)

---

#### ✅ Fechamento de Caixa
```bash
GET /INTEGRACAO/FECHAMENTO_CAIXA
```

**Retorna:** Resumo dos fechamentos do período

---

#### ✅ Transferências (Bancárias & Internas)
```bash
GET /INTEGRACAO/TRANSFERENCIA
GET /INTEGRACAO/TRANSFERENCIA_BANCARIA
```

---

### 1.4 **PRODUTOS**

#### ✅ Listar Produtos
```bash
GET /INTEGRACAO/PRODUTO
```

**Retorna:**
```json
{
  "produtos": [
    {
      "id": "PROD001",
      "nome": "Gasolina Comum",
      "descricao": "Combustível para veículos",
      "categoria": "Combustível",
      "preco_unitario": 5.50,
      "unidade": "Litro",
      "estoque_atual": 5000,
      "estoque_minimo": 1000,
      "fornecedor": "Distribuidora XYZ",
      "ativo": true
    }
  ],
  "total": 45
}
```

---

#### ✅ Combustível (Cadastro)
```bash
GET /INTEGRACAO/COMBUSTIVEL
```

**Retorna:** Apenas combustíveis cadastrados

---

#### ✅ Estoque
```bash
GET /INTEGRACAO/ESTOQUE
```

**Retorna:** Posição completa de estoque por produto

---

#### ✅ Preço por Produto
```bash
GET /INTEGRACAO/PRECO_PRODUTO
```

**Retorna:** Tabela de preços e histórico de variações

---

#### ✅ Tributos ICMS
```bash
GET /INTEGRACAO/INTEGRACAO_PRODUTO_TRIBUTO_ICMS
```

**Retorna:** Alíquotas ICMS por produto

---

#### ✅ Tributos PIS/COFINS
```bash
GET /INTEGRACAO/INTEGRACAO_PRODUTO_TRIBUTO_PIS_CONFINS
```

**Retorna:** Alíquotas PIS/COFINS por produto

---

### 1.5 **VENDAS & NOTAS FISCAIS**

#### ✅ Listar Vendas
```bash
GET /INTEGRACAO/VENDA
```

**Parâmetros:**
- `data_inicio`
- `data_fim`
- `cliente_id`
- `status` - pendente, realizada, cancelada

**Retorna:**
```json
{
  "vendas": [
    {
      "id": "VENDA001",
      "data": "2026-05-08",
      "numero_nf": "NF-12345",
      "cliente_id": "CLI001",
      "cliente_nome": "Transportadora ABC",
      "valor_total": 5000.00,
      "valor_desconto": 0.00,
      "valor_liquido": 5000.00,
      "itens": [
        {
          "produto": "Gasolina Comum",
          "quantidade": 500,
          "unidade": "Litro",
          "valor_unitario": 5.50,
          "subtotal": 2750.00
        }
      ],
      "forma_pagamento": "Dinheiro",
      "status": "realizada"
    }
  ],
  "total_vendas": 245000.00
}
```

---

#### ✅ Notas Fiscais Saída
```bash
GET /INTEGRACAO/NOTA_FISCAL_SAIDA
```

**Retorna:** NFs emitidas (vendas)

---

#### ✅ Notas Fiscais Entrada
```bash
GET /INTEGRACAO/NOTA_FISCAL_ENTRADA
```

**Retorna:** NFs recebidas (compras)

---

#### ✅ Vendas Rede
```bash
GET /INTEGRACAO/VENDA_REDE
```

**Retorna:** Vendas consolidadas de múltiplas filiais

---

#### ✅ Pedidos de Compras
```bash
GET /INTEGRACAO/PEDIDO_COMPRAS
```

**Retorna:** Pedidos abertos e realizados

---

#### ✅ Pedidos de Combustível
```bash
GET /INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO
```

**Retorna:** Pedidos específicos de combustível

---

### 1.6 **RELATÓRIOS**

#### ✅ Rel. Estoque
```bash
GET /INTEGRACAO/RELATORIO/ESTOQUE
```

**Retorna:** Posição de estoque detalhada

---

#### ✅ Rel. Venda Combustível
```bash
GET /INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL
```

**Parâmetros:**
- `data_inicio`
- `data_fim`

**Retorna:**
```json
{
  "periodo": "2026-04-01 a 2026-05-08",
  "vendas_por_produto": [
    {
      "produto": "Gasolina Comum",
      "quantidade": 15000,
      "valor": 82500.00,
      "percentual": "42.5%"
    }
  ],
  "total_quantidade": 35300,
  "total_valor": 194150.00
}
```

---

#### ✅ Rel. Venda Produto
```bash
GET /INTEGRACAO/RELATORIO/VENDA_PRODUTO
```

**Retorna:** Vendas de produtos (não combustível)

---

#### ✅ Resumo Vendas
```bash
GET /INTEGRACAO/RELATORIO/RESUMO_VENDAS
```

**Retorna:** Consolidado rápido de vendas

---

### 1.7 **ADMINISTRAÇÃO**

#### ✅ Listar Usuários
```bash
GET /INTEGRACAO/USUARIO
```

**Retorna:**
```json
{
  "usuarios": [
    {
      "id": "USU001",
      "nome": "Maria Silva",
      "email": "maria@empresa.com",
      "funcao": "Gerente",
      "ativo": true,
      "ultimo_acesso": "2026-05-08T15:30:00"
    }
  ]
}
```

---

#### ✅ Filiais
```bash
GET /INTEGRACAO/FILIAL
```

**Retorna:** Endereços e dados das filiais

---

#### ✅ Administradoras (de Cartão)
```bash
GET /INTEGRACAO/ADMINISTRADORA
```

**Retorna:** Bandeiras e administradoras configuradas

---

---

## ➕ 2. OPERAÇÕES DE CRIAÇÃO (POST)

### 2.1 Criar Título a Receber
```bash
POST /api/v1/financeiro
```

**Headers:**
```
Content-Type: application/json
X-Usuario: seu-usuario          # Recomendado
X-Motivo: Razão da criação      # Recomendado
```

**Body:**
```json
{
  "tipo": "RECEBER",
  "valor": 5000.00,
  "data_vencimento": "2026-06-08T00:00:00Z",
  "descricao": "Fatura de venda - Pedido #12345",
  "cliente_fornecedor": "Transportadora ABC Ltda",
  "categoria": "Vendas"
}
```

**Validações:**
- ✅ `valor` > 0
- ✅ `descricao` entre 3-255 caracteres
- ✅ `cliente_fornecedor` entre 3-255 caracteres
- ✅ `tipo` = RECEBER ou PAGAR

**Resposta (200 OK):**
```json
{
  "status": "success",
  "mensagem": "Título criado com sucesso",
  "dados": {
    "id": "TIT_ABC123XYZ",
    "tipo": "RECEBER",
    "valor": 5000.00,
    "data_vencimento": "2026-06-08T00:00:00",
    "status": "pendente",
    "data_criacao": "2026-05-08T18:30:45Z",
    "modificado_por": "seu-usuario"
  }
}
```

---

### 2.2 Criar Movimento de Caixa
```bash
POST /api/v1/caixa/movimentos
```

**Body:**
```json
{
  "descricao": "Entrada de vendas - Turno 1",
  "valor": 5500.00,
  "tipo": "entrada",
  "categoria": "vendas",
  "referencia": "VENDA_12345"
}
```

**Resposta:**
```json
{
  "status": "success",
  "id": "MOV_XYZ123",
  "saldo_anterior": 1000.00,
  "saldo_novo": 6500.00
}
```

---

### 2.3 Criar Cliente
```bash
POST /api/v1/clientes
```

**Body:**
```json
{
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
}
```

---

### 2.4 Criar Abastecimento
```bash
POST /api/v1/abastecimentos
```

**Body:**
```json
{
  "cliente_id": "CLI001",
  "data": "2026-05-08T10:30:00Z",
  "valor": 350.00,
  "litros": 65.45,
  "produto_id": "GASOLINA_COMUM",
  "bomba": "BOMBA_1",
  "combustivel": "Gasolina Comum",
  "placa_veiculo": "ABC-1234"
}
```

---

---

## ✏️ 3. OPERAÇÕES DE ATUALIZAÇÃO (PUT)

### 3.1 Atualizar Título
```bash
PUT /api/v1/financeiro/{titulo_id}
```

**Headers:**
```
X-Usuario: seu-usuario
X-Motivo: Confirmar recebimento      # Recomendado
```

**Body (parcial — envie apenas campos a alterar):**
```json
{
  "valor": 5200.00,
  "pago": true,
  "data_pagamento": "2026-05-08T15:30:00Z",
  "status": "pago"
}
```

**Resposta:**
```json
{
  "status": "success",
  "mensagem": "Título atualizado com sucesso",
  "dados": {
    "id": "TIT_ABC123XYZ",
    "valor": 5200.00,
    "pago": true,
    "data_pagamento": "2026-05-08T15:30:00",
    "data_atualizacao": "2026-05-08T18:35:20Z",
    "modificado_por": "seu-usuario"
  }
}
```

---

### 3.2 Atualizar Cliente
```bash
PUT /api/v1/clientes/{cliente_id}
```

**Body:**
```json
{
  "credito_limite": 150000.00,
  "telefone": "(11) 98888-7777",
  "ativo": true
}
```

---

### 3.3 Atualizar Movimento de Caixa
```bash
PUT /api/v1/caixa/movimentos/{movimento_id}
```

**Body:**
```json
{
  "valor": 5600.00,
  "descricao": "Entrada de vendas corrigida - Turno 1"
}
```

---

### 3.4 Atualizar Status de Venda
```bash
PUT /api/v1/vendas/{venda_id}
```

**Body:**
```json
{
  "status": "cancelada",
  "motivo": "Cliente solicitou cancelamento"
}
```

---

---

## 🗑️ 4. OPERAÇÕES DE DELEÇÃO (DELETE)

### 4.1 Deletar Título
```bash
DELETE /api/v1/financeiro/{titulo_id}
```

**Headers:**
```
X-Usuario: seu-usuario
X-Motivo: Eliminação por duplicata   # Recomendado
```

**Resposta:**
```json
{
  "status": "success",
  "mensagem": "Título deletado com sucesso",
  "dados": {
    "id": "TIT_ABC123XYZ",
    "status": "cancelado",
    "data_cancelamento": "2026-05-08T18:40:00Z",
    "motivo": "Eliminação por duplicata",
    "deletado_por": "seu-usuario"
  }
}
```

**Nota:** Delete é soft delete — o registro fica marcado como "cancelado", não é removido fisicamente.

---

### 4.2 Deletar Movimento de Caixa
```bash
DELETE /api/v1/caixa/movimentos/{movimento_id}
```

**Resposta:** Movimento marcado como cancelado

---

### 4.3 Deletar Cliente
```bash
DELETE /api/v1/clientes/{cliente_id}
```

**Condições:**
- ❌ Não pode ter vendas associadas
- ❌ Não pode ter títulos abertos

**Se tiver restrições:**
```json
{
  "status": "error",
  "mensagem": "Cliente não pode ser deletado",
  "detalhes": "Cliente possui 5 vendas realizadas e 2 títulos a receber"
}
```

---

---

## 🔐 5. AUDITORIA COMPLETA

Todas as operações de criação/atualização/exclusão são registradas com:

```json
{
  "operacao": "PUT",
  "tabela": "financeiro",
  "registro_id": "TIT_ABC123XYZ",
  "valores_anteriores": {
    "valor": 5000.00,
    "pago": false
  },
  "valores_novos": {
    "valor": 5200.00,
    "pago": true
  },
  "usuario": "seu-usuario",
  "motivo": "Confirmar recebimento",
  "ip_origem": "192.168.1.100",
  "data_hora": "2026-05-08T18:35:20Z",
  "hash_auditoria": "abc123def456..."
}
```

**Acessar Auditoria:**
```bash
GET /auditoria/registros?filtro_tabela=financeiro&filtro_registro_id=TIT_ABC123XYZ
```

---

## 📊 6. TABELA RESUMIDA — O QUE VOCÊ PODE FAZER

| Dados | GET | POST | PUT | DELETE | Auditado |
|-------|-----|------|-----|--------|----------|
| Clientes | ✅ | ✅ | ✅ | ✅* | ✅ |
| Produtos | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Abastecimentos | ✅ | ✅ | ✅ | ✅ | ✅ |
| Vendas | ✅ | ✅ | ✅ | ✅ | ✅ |
| Títulos Receber | ✅ | ✅ | ✅ | ✅ | ✅ |
| Títulos Pagar | ✅ | ✅ | ✅ | ✅ | ✅ |
| Caixa/Movimentos | ✅ | ✅ | ✅ | ✅ | ✅ |
| Notas Fiscais | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Cartão Crédito | ✅ | ✅ | ✅ | ✅ | ✅ |
| Relatórios | ✅ | ✅ | — | — | ✅ |

**Legenda:**
- ✅ Liberado
- ⚠️ Restrito (requer validações)
- — Não aplicável
- \* Soft delete apenas

---

## 🚀 7. EXEMPLOS DE USO PRÁTICO

### Exemplo 1: Registrar uma venda e criar título automático

```bash
# 1. Criar a venda
curl -X POST "https://api.webposto.com.br/api/v1/vendas" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: vendedor1" \
  -H "X-Motivo: Venda diária" \
  -d '{
    "cliente_id": "CLI001",
    "data": "2026-05-08T10:30:00Z",
    "valor_total": 5000.00,
    "itens": [
      {
        "produto_id": "GASOLINA",
        "quantidade": 909.09,
        "valor_unitario": 5.50
      }
    ]
  }'

# Retorna: {"id": "VENDA_123ABC"}

# 2. Criar título correspondente
curl -X POST "https://api.webposto.com.br/api/v1/financeiro" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: vendedor1" \
  -H "X-Motivo: Título da VENDA_123ABC" \
  -d '{
    "tipo": "RECEBER",
    "valor": 5000.00,
    "data_vencimento": "2026-06-08T00:00:00Z",
    "descricao": "Venda de combustível - VENDA_123ABC",
    "cliente_fornecedor": "Transportadora ABC Ltda",
    "categoria": "Vendas"
  }'
```

---

### Exemplo 2: Consultar títulos vencidos e cobrar

```bash
# 1. Listar títulos vencidos
curl -X GET "https://api.webposto.com.br/api/v1/financeiro?status=vencido&tipo=RECEBER"

# Retorna lista com todos vencidos

# 2. Marcar como pago quando cliente pagar
curl -X PUT "https://api.webposto.com.br/api/v1/financeiro/TIT_ABC123XYZ" \
  -H "Content-Type: application/json" \
  -H "X-Usuario: gerente_financeiro" \
  -H "X-Motivo: Recebimento transferência bancária" \
  -d '{
    "pago": true,
    "data_pagamento": "2026-05-08T14:50:00Z"
  }'
```

---

### Exemplo 3: Sincronizar dados locais com webPosto

```bash
# Obter todos abastecimentos de hoje
curl -X GET "https://api.webposto.com.br/INTEGRACAO/ABASTECIMENTO?CHAVE=$WEBPOSTO_CHAVE&data_inicio=2026-05-08&data_fim=2026-05-08"

# Atualizar seu banco de dados local com esses dados
# Criar registros de auditoria locais com a sincronização
```

---

### Exemplo 4: Gerar relatório de vendas do mês

```bash
# Obter vendas do mês
curl -X GET "https://api.webposto.com.br/INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL?CHAVE=$WEBPOSTO_CHAVE&data_inicio=2026-05-01&data_fim=2026-05-31"

# Processár e enviar para BI/Excel
```

---

## ⚠️ 8. LIMITAÇÕES E RESTRIÇÕES DO TOKEN

**Seu token PODE:**
- ✅ Ler TODOS os 51 endpoints
- ✅ Criar novos registros (títulos, movimentos, clientes)
- ✅ Alterar registros existentes
- ✅ Deletar registros (soft delete)
- ✅ Acessar auditoria completa

**Seu token NÃO PODE:**
- ❌ Excluir produtos cadastrados (apenas criar/atualizar)
- ❌ Modificar configurações globais da conta
- ❌ Desativar outro usuário
- ❌ Alterar permissões de tokens
- ❌ Deletar arquivos/documentos (apenas soft delete)

---

## 📞 9. CÓDIGOS DE ERRO COMUNS

| Código | Significado | Solução |
|--------|------------|---------|
| 200 | OK | Sucesso! |
| 201 | Created | Recurso criado com sucesso |
| 400 | Bad Request | Verifique JSON/parâmetros |
| 401 | Unauthorized | Token expirado ou inválido |
| 403 | Forbidden | Sem permissão para operação |
| 404 | Not Found | Registro não existe |
| 422 | Validation Error | Validação falhou (veja `detail`) |
| 429 | Rate Limit | Muitas requisições (espere 60s) |
| 500 | Server Error | Erro interno — contate suporte |

---

## 🎯 10. DICAS PRÁTICAS

**1. Sempre usar headers de auditoria:**
```bash
-H "X-Usuario: seu-usuario"
-H "X-Motivo: Razão clara da operação"
```

**2. Validar antes de criar:**
```bash
# Verificar se cliente existe antes de criar título
curl -X GET "https://api.webposto.com.br/INTEGRACAO/CLIENTE?CHAVE=..."
```

**3. Usar paginação para grandes volumes:**
```bash
curl -X GET ".../ABASTECIMENTO?...&pagina=1&limite=100"
# depois &pagina=2&limite=100, etc
```

**4. Sincronizar periodicamente:**
```bash
# A cada 1 hora
curl -X POST "http://localhost:8000/sync/full"
```

**5. Monitorar auditoria:**
```bash
# Ver tudo que foi feito com seu token
curl -X GET "http://localhost:8000/auditoria/por-token?token=<REDACTED>"
```

---

## 📝 RESUMO FINAL

Com seu token você tem **acesso COMPLETO** e **ILIMITADO** a:

- ✅ **51 endpoints de leitura** (GET)
- ✅ **CRUD completo** (Create, Read, Update, Delete)
- ✅ **Auditoria completa** (quem fez o quê, quando, de onde)
- ✅ **Validações automáticas** (Pydantic)
- ✅ **Rastreamento de origem** (IP + usuário)

**Seu token é PRODUCTION-READY!** 🚀

---

**Gerado:** 2026-05-08  
**Token:** Veja `.env` (WEBPOSTO_BEARER_TOKEN)  
**Status:** ✅ Ativo e Validado
