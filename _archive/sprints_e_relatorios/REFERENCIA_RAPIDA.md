# 📋 GUIA DE REFERÊNCIA RÁPIDA — Seu Token

**Token:** Veja `.env` (WEBPOSTO_BEARER_TOKEN)

---

## 🔍 QUICK REFERENCE — O QUE FAZER EM 10 SEGUNDOS

### Quero CONSULTAR...

| O quê? | URL | Como? |
|--------|-----|-------|
| Abastecimentos de hoje | `/INTEGRACAO/ABASTECIMENTO?data_inicio=2026-05-08&data_fim=2026-05-08` | GET |
| Todos os clientes | `/INTEGRACAO/CLIENTE` | GET |
| Todos os produtos | `/INTEGRACAO/PRODUTO` | GET |
| Títulos a receber | `/INTEGRACAO/TITULO_RECEBER?status=pendente` | GET |
| Títulos a pagar | `/INTEGRACAO/TITULO_PAGAR` | GET |
| Movimento de caixa | `/INTEGRACAO/CAIXA?data_inicio=2026-05-08&data_fim=2026-05-08` | GET |
| Relatório de vendas | `/INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL?data_inicio=2026-05-01&data_fim=2026-05-31` | GET |
| Estoque | `/INTEGRACAO/RELATORIO/ESTOQUE` | GET |
| Frota de cliente | `/INTEGRACAO/CLIENTE_FROTA` | GET |
| Cartão de crédito | `/INTEGRACAO/CARTAO_COMPRA` | GET |

---

### Quero CRIAR...

| O quê? | Endpoint | Campos Obrigatórios |
|--------|----------|-------------------|
| Título a Receber | POST `/api/v1/financeiro` | tipo, valor, data_vencimento, descricao, cliente_fornecedor |
| Cliente | POST `/api/v1/clientes` | razao_social, nome_fantasia, cnpj, contato, telefone, email, endereco, cidade, estado |
| Movimento Caixa | POST `/api/v1/caixa/movimentos` | descricao, valor, tipo (entrada/saida), categoria |
| Abastecimento | POST `/api/v1/abastecimentos` | cliente_id, data, valor, litros, produto_id |

---

### Quero ALTERAR...

| O quê? | Endpoint | Enviar |
|--------|----------|--------|
| Marcar título pago | PUT `/api/v1/financeiro/{id}` | `{"pago": true, "data_pagamento": "2026-05-08T14:50:00Z"}` |
| Aumentar crédito cliente | PUT `/api/v1/clientes/{id}` | `{"credito_limite": 150000}` |
| Corrigir movimento | PUT `/api/v1/caixa/movimentos/{id}` | `{"valor": 5600, "descricao": "..."}` |

---

### Quero DELETAR...

| O quê? | Endpoint | Resultado |
|--------|----------|-----------|
| Título | DELETE `/api/v1/financeiro/{id}` | Marca como cancelado (soft delete) |
| Cliente | DELETE `/api/v1/clientes/{id}` | Marca como inativo se sem dependências |
| Movimento | DELETE `/api/v1/caixa/movimentos/{id}` | Marca como cancelado |

---

## 🔧 HEADERS NECESSÁRIOS

```bash
# Para requisições com seu token (GET externo)
-H "CHAVE: $WEBPOSTO_CHAVE"  # Carregado de .env

# Para requisições locais (POST/PUT/DELETE)
-H "Content-Type: application/json"
-H "X-Usuario: seu-usuario"           # Quem está fazendo
-H "X-Motivo: Razão da operação"      # Por quê está fazendo
```

---

## 📊 PARÂMETROS DE FILTRO

| Parâmetro | Valores | Exemplo |
|-----------|---------|---------|
| `pagina` | número (1, 2, 3...) | `?pagina=1` |
| `limite` | 1-500 | `?limite=100` |
| `data_inicio` | YYYY-MM-DD | `?data_inicio=2026-05-01` |
| `data_fim` | YYYY-MM-DD | `?data_fim=2026-05-08` |
| `status` | pendente, pago, vencido, cancelado | `?status=pendente` |
| `tipo` | RECEBER, PAGAR | `?tipo=RECEBER` |
| `ordenar_por` | campo | `?ordenar_por=data_vencimento` |

---

## 🔢 51 ENDPOINTS DISPONÍVEIS

### Abastecimento (3)
- `GET /INTEGRACAO/ABASTECIMENTO`
- `GET /INTEGRACAO/ABASTECIMENTO_DIVERGENCIA`
- `GET /INTEGRACAO/ABASTECIMENTO_ENCERRANTE`

### Clientes (4)
- `GET /INTEGRACAO/CLIENTE`
- `GET /INTEGRACAO/CLIENTE_FROTA`
- `GET /INTEGRACAO/GRUPO_CLIENTE`
- `GET /INTEGRACAO/INTEGRACAO_CLIENTE_CADASTRO`

### Financeiro (12)
- `GET /INTEGRACAO/TITULO_RECEBER`
- `GET /INTEGRACAO/TITULO_PAGAR`
- `GET /INTEGRACAO/CAIXA`
- `GET /INTEGRACAO/CAIXA_APRESENTADO`
- `GET /INTEGRACAO/CARTAO_COMPRA`
- `GET /INTEGRACAO/CARTAO_PAGAR`
- `GET /INTEGRACAO/CARTAO_REMESSA`
- `GET /INTEGRACAO/FECHAMENTO_CAIXA`
- `GET /INTEGRACAO/MOVIMENTO_CONTA`
- `GET /INTEGRACAO/PLANO_DE_CONTAS`
- `GET /INTEGRACAO/TRANSFERENCIA`
- `GET /INTEGRACAO/TRANSFERENCIA_BANCARIA`

### Produtos (9)
- `GET /INTEGRACAO/PRODUTO`
- `GET /INTEGRACAO/COMBUSTIVEL`
- `GET /INTEGRACAO/ESTOQUE`
- `GET /INTEGRACAO/LISTA_DE_ITENS`
- `GET /INTEGRACAO/PRECO_PRODUTO`
- `GET /INTEGRACAO/PRODUTO_INVENTARIO_ITENS`
- `GET /INTEGRACAO/RETORNO_CADASTRO_PRODUTO`
- `GET /INTEGRACAO/INTEGRACAO_PRODUTO_TRIBUTO_ICMS`
- `GET /INTEGRACAO/INTEGRACAO_PRODUTO_TRIBUTO_PIS_CONFINS`

### Pedidos (3)
- `GET /INTEGRACAO/APRIX_CUSTO`
- `GET /INTEGRACAO/DISTRIBUIDORA`
- `GET /INTEGRACAO/LMC`
- `GET /INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO`

### Relatórios (4)
- `GET /INTEGRACAO/RELATORIO/ESTOQUE`
- `GET /INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL`
- `GET /INTEGRACAO/RELATORIO/VENDA_PRODUTO`
- `GET /INTEGRACAO/RELATORIO/RESUMO_VENDAS`

### Vendas & NF (9)
- `GET /INTEGRACAO/ADMINISTRADORA`
- `GET /INTEGRACAO/FILIAL`
- `GET /INTEGRACAO/NOTA_FISCAL_ENTRADA`
- `GET /INTEGRACAO/NOTA_FISCAL_SAIDA`
- `GET /INTEGRACAO/PEDIDO_COMPRAS`
- `GET /INTEGRACAO/PRAZO_TABELA_PRECO`
- `GET /INTEGRACAO/USUARIO`
- `GET /INTEGRACAO/USUARIO_EMPRESA_REDE`
- `GET /INTEGRACAO/VENDA`
- `GET /INTEGRACAO/VENDA_REDE`

### Adicionais (5)
- `GET /INTEGRACAO/ADIANTAMENTO_FORNECEDOR`
- `GET /INTEGRACAO/FINANCEIRO_EXCLUSAO`
- `GET /INTEGRACAO/INTEGRACAO_LISTA_CLIENTE_PRAZO`
- `GET /INTEGRACAO/RETORNO_CADASTRO_CLIENTE`

**TOTAL: 51 endpoints**

---

## ❌ CÓDIGOS DE ERRO

| Código | Significado | Solução |
|--------|------------|---------|
| 200 | ✅ OK | Sucesso! |
| 201 | ✅ Created | Recurso criado |
| 204 | ✅ No Content | Deletado com sucesso |
| 400 | ❌ Bad Request | Verifique JSON/parâmetros (veja `detail`) |
| 401 | ❌ Unauthorized | Token inválido ou expirado |
| 403 | ❌ Forbidden | Sem permissão para esta operação |
| 404 | ❌ Not Found | Recurso não existe |
| 422 | ❌ Validation Error | Falha na validação (veja campos) |
| 429 | ❌ Too Many Requests | Rate limit excedido (espere 60s) |
| 500 | ❌ Server Error | Erro interno (contate suporte) |

---

## ⏱️ RATE LIMITS

| Limite | Quantidade | Ação |
|--------|-----------|------|
| Por Hora | 1000 requisições | Resposta 429 se exceder |
| Por Minuto | 100 requisições | Resposta 429 se exceder |
| Simultâneas | 10 requisições | Fila automática de espera |
| Timeout | 30 segundos | Erro 504 Gateway Timeout |

---

## 📝 MODELOS (Pydantic)

### TituloFinanceiro (Criar)
```json
{
  "tipo": "RECEBER",           // RECEBER ou PAGAR
  "valor": 5000.00,            // > 0
  "data_vencimento": "2026-06-08T00:00:00Z",
  "descricao": "...",          // 3-255 caracteres
  "cliente_fornecedor": "...", // 3-255 caracteres
  "categoria": "Vendas"        // Categoria livre
}
```

### ClienteFinanceiro (Criar)
```json
{
  "razao_social": "...",
  "nome_fantasia": "...",
  "cnpj": "12.345.678/0001-90",
  "contato": "...",
  "telefone": "(11) 98765-4321",
  "email": "email@example.com",
  "endereco": "...",
  "cidade": "...",
  "estado": "SP",
  "credito_limite": 100000.00  // Opcional
}
```

### CaixaMovimento (Criar)
```json
{
  "descricao": "...",
  "valor": 5500.00,
  "tipo": "entrada",           // entrada ou saida
  "categoria": "vendas",       // vendas, despesa, etc
  "referencia": "VENDA_123"    // Opcional
}
```

---

## 🔐 REGRAS DE NEGÓCIO

| Regra | Verificação |
|-------|-------------|
| Valor positivo | `valor > 0` ✅ |
| Descrição não vazia | `len(descricao) > 2` ✅ |
| Cliente/Fornecedor válido | `len(nome) >= 3` ✅ |
| Data vencimento futura | `data_vencimento > agora` ✅ |
| Tipo = RECEBER ou PAGAR | Validação de enum ✅ |
| Caixa: tipo entrada/saida | Validação de enum ✅ |
| Soft delete apenas | Nunca apaga fisicamente ✅ |
| Auditoria obrigatória | Registra tudo ✅ |

---

## 📂 ESTRUTURA DE RESPOSTA

### Sucesso (200/201)
```json
{
  "status": "success",
  "mensagem": "Operação realizada",
  "dados": { /* objeto criado/alterado */ },
  "timestamp": "2026-05-08T18:30:45Z"
}
```

### Erro (4xx/5xx)
```json
{
  "status": "error",
  "detail": "Descrição do erro",
  "timestamp": "2026-05-08T18:30:45Z"
}
```

### Listagem
```json
{
  "status": "success",
  "total": 150,
  "pagina": 1,
  "limite": 50,
  "total_paginas": 3,
  "dados": [ /* array de registros */ ],
  "timestamp": "2026-05-08T18:30:45Z"
}
```

---

## 🎯 FLUXOS COMUNS

### Fluxo 1: Registrar Venda
```
1. GET /INTEGRACAO/CLIENTE
   → Verificar se cliente existe
   
2. POST /api/v1/financeiro
   → Criar título a receber
   
3. POST /api/v1/caixa/movimentos
   → Registrar entrada no caixa
   
4. PUT /api/v1/financeiro/{id}
   → Quando cliente pagar, marcar como pago
```

### Fluxo 2: Consultar Inadimplência
```
1. GET /INTEGRACAO/TITULO_RECEBER?status=vencido
   → Lista todos os vencidos
   
2. Processar notificação de cobrança
   
3. PUT /api/v1/financeiro/{id}
   → Atualizar com data de recebimento
```

### Fluxo 3: Sincronizar Dados
```
1. GET /INTEGRACAO/CLIENTE
   → Atualizar clientes locais
   
2. GET /INTEGRACAO/PRODUTO
   → Atualizar produtos locais
   
3. GET /INTEGRACAO/ABASTECIMENTO
   → Atualizar abastecimentos
   
4. Salvar tudo no banco local
```

---

## 🚀 EXEMPLO MÍNIMO (3 LINHAS)

### cURL
```bash
curl -X GET "https://api.webposto.com.br/INTEGRACAO/CLIENTE?CHAVE=$WEBPOSTO_CHAVE"
```

### Python
```python
import httpx
r = httpx.get("https://api.webposto.com.br/INTEGRACAO/CLIENTE", params={"CHAVE": os.getenv("WEBPOSTO_CHAVE")})
print(r.json())
```

### JavaScript
```js
fetch(`https://api.webposto.com.br/INTEGRACAO/CLIENTE?CHAVE=${process.env.WEBPOSTO_CHAVE}`)
  .then(r => r.json()).then(d => console.log(d))
```

---

## 💾 ARQUIVOS DE REFERÊNCIA

| Arquivo | Conteúdo |
|---------|----------|
| `SUMARIO_TOKEN.md` | Este arquivo (referência visual) |
| `OPERACOES_COMPLETAS_COM_TOKEN.md` | Documentação completa (80+ págs) |
| `exemplo_uso_completo.py` | Código Python pronto |
| `exemplos_curl.md` | Comandos cURL prontos |

---

## 🎓 APRENDER MAIS

```
1. Leia: OPERACOES_COMPLETAS_COM_TOKEN.md
2. Teste: exemplos_curl.md (copiar/colar)
3. Código: exemplo_uso_completo.py (rodar e adaptar)
4. Produção: usar suas próprias integrações
```

---

## ✅ CHECKLIST DE INÍCIO

- [ ] Li SUMARIO_TOKEN.md (este arquivo)
- [ ] Li OPERACOES_COMPLETAS_COM_TOKEN.md
- [ ] Testei um GET com cURL
- [ ] Testei um POST com cURL
- [ ] Adaptei o código Python
- [ ] Rodei meu primeiro teste
- [ ] Integrei no meu sistema

**Pronto para produção!** 🚀

---

**Gerado:** 2026-05-08  
**Versão:** 1.0  
**Status:** ✅ Ready  

📌 **Bookmark este arquivo para referência rápida!**
