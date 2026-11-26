# 🚀 QUICKSTART - PRECIFICADOR IA

## Comece agora

### 1. Rodar os testes

```bash
cd WebPosto_API

# Rodar testes do Precificador IA
pytest tests/services/test_pricing_analyzer.py -v
```

**Resultado esperado**:
```
test_margem_saudavel PASSED
test_margem_baixa PASSED
test_margem_negativa PASSED
test_margem_critica PASSED
test_markup_calculo PASSED
test_margem_com_impostos_diversos PASSED
test_sugestao_margem_negativa PASSED
test_sugestao_margem_baixa PASSED
test_impacto_mensal_reajuste PASSED
test_preco_psicologico PASSED
test_pequeno_reajuste_margem_ok PASSED
test_detectar_obsoleto PASSED
test_detectar_baixa_rotacao PASSED
test_detectar_composto_errado PASSED
test_sem_perdas_detectadas PASSED
test_gerar_relatorio_precificacao PASSED
test_relatorio_status_critico PASSED
test_relatorio_status_alerta PASSED
test_arredondar_para_90 PASSED
test_arredondar_para_99 PASSED
test_arredondar_para_90_baixo PASSED
test_arredondar_aumenta_inteiro PASSED
test_fluxo_completo_margem_negativa PASSED
test_cenario_produto_boom PASSED

✅ 24 passed
```

---

### 2. Usar via API REST

**Iniciar servidor**:
```bash
python -m uvicorn src.interfaces.http.app:app --reload
```

---

## 📊 ENDPOINTS DO PRECIFICADOR IA

### 1️⃣ **Análise de Margens Consolidada**

```bash
curl http://localhost:8000/api/v1/pricing-ai/analise-margens
```

**Resposta**:
```json
{
  "total_produtos": 250,
  "margens_negativas": {
    "quantidade": 5,
    "impacto_mensal": -2500.0,
    "produtos": [
      {
        "produto_id": "SKU_PROBLEMA",
        "margem_percentual": -15.5,
        "recomendacao": "Aumentar preço ou reduzir custo imediatamente"
      }
    ]
  },
  "margens_baixas": {
    "quantidade": 23,
    "impacto_mensal": 15000.0,
    "produtos": [
      {
        "produto_id": "SKU_BAIXA",
        "margem_percentual": 12.3,
        "recomendacao": "Considerar aumento de preço"
      }
    ]
  },
  "status": "CRÍTICO"
}
```

**Interpretação**:
- **5 produtos com margem negativa** → R$ 2.500/mês de perda
- **23 produtos com margem baixa** → Oportunidade de R$ 15.000/mês
- **Status CRÍTICO** → Ação imediata necessária

---

### 2️⃣ **Produtos com Margem Negativa**

```bash
curl http://localhost:8000/api/v1/pricing-ai/margens-negativas
```

**Resposta**:
```json
[
  {
    "produto_id": "SKU_ERRO1",
    "descricao": "Produto Premium X",
    "preco_venda": 50.0,
    "custo_total": 60.0,
    "margem_bruta": -10.0,
    "margem_percentual": -20.0,
    "markup": -0.83,
    "recomendacao": "Aumentar preço ou reduzir custo imediatamente",
    "problemas": ["Margem negativa: -20.0%", "Markup muito baixo: -83.33%"]
  }
]
```

**O que fazer**:
- Ação imediata obrigatória
- Aumentar preço OU negociar custo com fornecedor
- Cada unidade vendida perde R$ 10

---

### 3️⃣ **Produtos com Margem Baixa**

```bash
curl "http://localhost:8000/api/v1/pricing-ai/margens-baixas?threshold_percentual=15"
```

**Resposta**:
```json
[
  {
    "produto_id": "SKU_CAFE",
    "descricao": "Café Premium 500g",
    "preco_venda": 100.0,
    "custo_total": 85.0,
    "margem_percentual": 14.9,
    "margem_status": "BAIXA",
    "recomendacao": "Considerar aumento de preço"
  },
  {
    "produto_id": "SKU_LEITE",
    "descricao": "Leite Integral 1L",
    "preco_venda": 40.0,
    "custo_total": 35.5,
    "margem_percentual": 12.7,
    "margem_status": "BAIXA",
    "recomendacao": "Considerar aumento de preço"
  }
]
```

**O que fazer**:
- Revisar estes 23 produtos
- Aumentar preço em 5-10% (reduz risco operacional)
- Verificar se podem ser comprados mais barato

---

### 4️⃣ **Analisar Margem de Um Produto**

```bash
curl -X POST http://localhost:8000/api/v1/pricing-ai/analisar-margem \
  -H "Content-Type: application/json" \
  -d '{
    "produto_id": "SKU_NOVO",
    "preco_venda": 100.0,
    "custo_produto": 60.0,
    "aliquota_icms": 12
  }'
```

**Resposta**:
```json
{
  "produto_id": "SKU_NOVO",
  "preco_venda": 100.0,
  "custo_total": 74.4,
  "margem_bruta": 25.6,
  "margem_percentual": 25.6,
  "margem_status": "SAUDÁVEL",
  "markup": 34.41,
  "problemas": [],
  "recomendacao": "Margem dentro dos padrões"
}
```

**Interpretação**:
- Custo total: R$ 74,40 (produto + impostos + overhead)
- Margem: R$ 25,60 por unidade (25,6%)
- Status: Saudável ✅
- Pode vender tranquilamente

---

### 5️⃣ **Sugestões de Reajuste de Preço**

```bash
curl "http://localhost:8000/api/v1/pricing-ai/sugestoes-reajuste?apenas_urgentes=false"
```

**Resposta**:
```json
[
  {
    "produto_id": "SKU_PROBLEMA",
    "descricao": "Produto Premium X",
    "preco_atual": 50.0,
    "preco_sugerido": 75.90,
    "percentual_ajuste": 51.8,
    "margem_atual": -20.0,
    "margem_sugerida": 1.5,
    "impacto_mensal": 2590.0,
    "motivo": "Produto com margem negativa",
    "urgencia": "CRÍTICA"
  },
  {
    "produto_id": "SKU_CAFE",
    "descricao": "Café 500g",
    "preco_atual": 100.0,
    "preco_sugerido": 107.90,
    "percentual_ajuste": 7.9,
    "margem_atual": 14.9,
    "margem_sugerida": 22.8,
    "impacto_mensal": 1580.0,
    "motivo": "Margem abaixo do mínimo saudável",
    "urgencia": "ALTA"
  }
]
```

**O que fazer**:
1. **CRÍTICA** - SKU_PROBLEMA: Aumentar de R$ 50 → R$ 75.90 (51.8% aumento, impacto R$ 2.590/mês)
2. **ALTA** - SKU_CAFE: Aumentar de R$ 100 → R$ 107.90 (7.9% aumento, impacto R$ 1.580/mês)

**Notas**:
- Preços são psicológicos (terminam em .90, .99)
- Impacto = (novo_preco - preco_atual) * volume_mensal
- Acumulado: 2 reajustes = R$ 4.170/mês de ganho

---

### 6️⃣ **Perdas Ocultas**

```bash
curl http://localhost:8000/api/v1/pricing-ai/perdas-ocultas
```

**Resposta**:
```json
[
  {
    "tipo": "OBSOLETO",
    "produto_id": "SKU_ANTIGO",
    "descricao": "Produto descontinuado",
    "perda_estimada_mensal": 1500.0,
    "dias_sem_venda": 120,
    "quantidade_parada": 500,
    "recomendacao": "Considerar remoção do catálogo ou liquidação"
  },
  {
    "tipo": "BAIXA_ROTACAO",
    "produto_id": "SKU_LENTO",
    "descricao": "Produto lento",
    "perda_estimada_mensal": 300.0,
    "dias_sem_venda": 60,
    "quantidade_parada": 300,
    "recomendacao": "Liquidar com desconto ou parar compras"
  }
]
```

**O que fazer**:
- **OBSOLETO** (120 dias): Remover catálogo ou liquidar com 40% desconto
- **BAIXA_ROTAÇÃO** (60 dias): Fazer promoção ou parar de comprar
- **PERDA**: R$ 1.500 + R$ 300 = R$ 1.800/mês

---

### 7️⃣ **Relatório Executivo**

```bash
curl http://localhost:8000/api/v1/pricing-ai/relatorio-precificacao
```

**Resposta**:
```json
{
  "data_audit": "2024-08-17T15:30:00",
  "estado": "PE",
  "margens_negativas": 5,
  "margens_baixas": 23,
  "oportunidades_reajuste": 28,
  "perdas_ocultas_detectadas": 8,
  
  "impacto_margens_negativas": -2500.0,
  "impacto_reajustes": 15000.0,
  "impacto_perdas_ocultas": -1800.0,
  
  "impacto_total_mensal": 10700.0,
  
  "recomendacoes": [
    "Corrigir 5 produtos com margem negativa",
    "Aplicar reajustes em 28 produtos",
    "Investigar 8 produtos com perdas ocultas"
  ],
  
  "status": "CRÍTICO"
}
```

**Resumo para o gestor**:
```
📊 PRECIFICAÇÃO - RELATÓRIO EXECUTIVO

💥 5 Produtos com MARGEM NEGATIVA (-R$ 2.500/mês)
⚠️  23 Produtos com MARGEM BAIXA
💰 Oportunidade de +R$ 15.000/mês em reajustes
🚫 8 Produtos com PERDAS OCULTAS (-R$ 1.800/mês)

🎯 IMPACTO TOTAL: R$ 10.700/mês de ganho potencial

✅ 3 Ações Prioritárias:
1. Aumentar preço de 5 produtos (margem negativa) - HOJE
2. Reajustar 23 produtos com margem baixa - Esta semana
3. Liquidar/remover 8 produtos obsoletos - Em andamento
```

---

## 🎯 CENÁRIO DE USO REAL

### **Manhã - 9:00 AM**

Diretor de operações pergunta: "Como está nossa precificação?"

```bash
curl http://localhost:8000/api/v1/pricing-ai/relatorio-precificacao
```

Resposta em < 2 segundos:
```
❌ CRÍTICO: 5 produtos vendendo no prejuízo
⚠️  23 produtos com margem insuficiente
💰 Ganho potencial: R$ 10.700/mês

Ação: Aumentar preços hoje (5) e esta semana (23)
```

### **9:30 AM - Reunião com equipe comercial**

```bash
# Quais produtos aumentar?
curl "http://localhost:8000/api/v1/pricing-ai/sugestoes-reajuste?apenas_urgentes=true"
```

Resultado: 5 produtos críticos com novo preço sugerido
- SKU_PROBLEMA: R$ 50 → R$ 75.90 (HOJE)
- 4 outros com aumento de 15-25%

**Ação**: Atualizar no ERP e comunicar vendedores

### **10:00 AM - Preços atualizados**

Equipe comercial recebe novos preços psicológicos

### **12:00 PM - Resultado da manhã**

- 5 produtos agora com margem saudável
- Impacto estimado: R$ 2.590/mês
- Comercial continua vendendo normalmente

### **Próxima semana - Reajustes de margem baixa**

Aplicar reajustes nos 23 produtos com margem 10-20%
- Aumentar preço em 5-10% cada
- Impacto adicional: R$ 15.000/mês
- Clientes veem isso como "ajuste de mercado"

---

## 💡 ESTRATÉGIA DE PRECIFICAÇÃO

### Como usar com outras IAs

```
Comprador IA (O que comprar?)
        ↓
Precificador IA (Qual preço vender?)
        ↓
Tax Advisor IA (Impostos correctos?)
        ↓
Decisão de negócio → Execução
```

**Exemplo prático**:
1. Comprador IA recomenda comprar Café
2. Precificador calcula: custo R$ 60, margem alvo 25%, preço R$ 80
3. Tax Advisor valida: NCM correto, impostos = 12%
4. Compra executada com margem garantida

---

## 📈 IMPACTO ESPERADO

### **Semana 1**
- ✅ Identificar 5-10 produtos com margem negativa
- ✅ Aumentar preços destes produtos (ganho R$ 2-5k/mês)
- ✅ Implementar feedback loop de preço

### **Mês 1**
- ✅ Revisar precificação de 30-50 produtos
- ✅ Aumentar margem média de 18% → 22% (+R$ 10-20k/mês)
- ✅ Reduzir perdas em obsoletos (R$ 2-5k/mês)

### **Contínuo**
- ✅ Reajuste automático de preços todo mês
- ✅ Detecção em tempo real de margens inadequadas
- ✅ Alertas quando novo produto tem margem negativa

---

## ✅ O QUE VOCÊ TEM AGORA

✅ Análise automática de margens (negativas, baixas, saudáveis)
✅ Cálculo de custo total (produto + impostos + overhead)
✅ Sugestões de reajuste com impacto financeiro
✅ Detecção de perdas ocultas (obsolescência, lentidão)
✅ Arredondamento psicológico de preços (X.90, X.99)
✅ 7 endpoints REST prontos para integrar
✅ 24 testes cobrindo todos cenários
✅ Relatórios executivos automáticos

**Resultado esperado quando rodar**:
```json
{
  "impacto_total_mensal": 10700.0,
  "margens_negativas": 5,
  "oportunidades_reajuste": 28,
  "status": "CRÍTICO"
}
```

---

## 🔄 Integração com Backend

```python
# No seu endpoint POST /compras, adicione:

from src.services.pricing_ai.pricing_analyzer import PricingAnalyzer

analyzer = PricingAnalyzer(webposto_client, db_client)

# Validar margem antes de aceitar compra
analise = await analyzer.analisar_margem_produto(
    produto_id=compra.produto_id,
    preco_venda=produto.preco_atual,
    custo_produto=compra.valor_unitario,
)

if analise.margem_status == "NEGATIVA":
    raise ValueError(f"Produto {produto_id}: margem negativa após compra")
```

---

Agora execute: `pytest tests/services/test_pricing_analyzer.py -v`

Depois teste: `curl http://localhost:8000/api/v1/pricing-ai/relatorio-precificacao`
