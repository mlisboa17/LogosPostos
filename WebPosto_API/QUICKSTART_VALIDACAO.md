# 🚀 QUICKSTART - VALIDAÇÃO DE COMPRAS

## Comece agora

### 1. Rodar os testes

```bash
cd WebPosto_API

# Instalar dependências
pip install pytest pytest-asyncio

# Rodar testes da validação
pytest tests/services/test_compras_validator.py -v
```

**Resultado esperado**:
```
test_valid_compra_item PASSED
test_invalid_quantidade_zero PASSED
test_invalid_quantidade_negativa PASSED
test_negative_valor PASSED
test_invalid_data PASSED
test_preco_outlier_deteccao PASSED
test_no_outliers_preco_estavel PASSED
test_detecta_preco_extremo PASSED
test_relatorio_dados_perfeitos PASSED
test_relatorio_muitos_problemas PASSED
test_consistencia_ok_entrada_igual_compra PASSED
test_consistencia_falta_compra_em_estoque PASSED

✅ 12 passed
```

---

### 2. Usar no código (programaticamente)

```python
from src.services.data_validation.compras_validator import ComprasValidator
from src.infrastructure.clients.webposto_client import WebPostoClient

# Inicializar
client = WebPostoClient(base_url="https://api.webposto.com")
validator = ComprasValidator(client, db_client=None)

# Validar 30 dias de compras
relatorio = await validator.generate_data_quality_report(
    data_inicial="2024-07-18",
    data_final="2024-08-17"
)

print(f"Status: {relatorio['status']}")
print(f"Cobertura: {relatorio['cobertura_dados_percentual']}%")
print(f"Problemas encontrados: {relatorio['compras_com_problema']}")
print(f"\nRecomendações:")
for rec in relatorio['recomendacoes']:
    print(f"  • {rec}")
```

---

### 3. Usar via API REST

**Iniciar servidor**:
```bash
# No diretório WebPosto_API
python -m uvicorn src.interfaces.http.app:app --reload
```

**Chamar endpoint**:
```bash
# Health check de dados (últimos 7 dias)
curl http://localhost:8000/api/v1/data-validation/compras/health

# Resposta esperada:
{
  "status": "OK",
  "cobertura_dados_percentual": 98.5,
  "compras_analisadas": 1500,
  "problemas_criticos": 3,
  "recomendacoes": [
    "3 fornecedores aumentaram preço >20% - verificar negociação"
  ]
}
```

**Validar 30 dias de compras**:
```bash
curl "http://localhost:8000/api/v1/data-validation/compras?dias=30"

# Resposta esperada:
{
  "status": "PRONTO_PARA_IA",
  "periodo": "2024-07-18 a 2024-08-17",
  "total_compras": 1500,
  "compras_com_problema": 13,
  "cobertura_dados_percentual": 99.1,
  "fornecedores_analisados": 45,
  "fornecedores_com_anomalia": 3,
  "problemas_encontrados": [
    {
      "compra_item_id": "ITEM_001",
      "produto_id": "SKU_123",
      "problemas": ["Custo divergiu 50% do histórico"],
      "diferenca_percentual": 50.0
    }
  ],
  "recomendacoes": [
    "3 fornecedores aumentaram preço >20% - verificar negociação",
    "Revisar 13 compras com dados inconsistentes"
  ]
}
```

**Validar item específico**:
```bash
curl -X POST http://localhost:8000/api/v1/data-validation/compras/validar-item \
  -H "Content-Type: application/json" \
  -d '{
    "id": "ITEM_123",
    "produto_id": "SKU_456",
    "valor": 1000,
    "frete": 100,
    "imposto": 50,
    "quantidade": 10,
    "data_compra": "2024-08-17T10:00:00"
  }'

# Resposta:
{
  "compra_item_id": "ITEM_123",
  "produto_id": "SKU_456",
  "is_valid": true,
  "custo_real": 115.0,
  "custo_esperado": 115.0,
  "diferenca": 0.0,
  "diferenca_percentual": 0.0,
  "problemas": []
}
```

---

## O que esperar

### ✅ Dados com qualidade (status = PRONTO_PARA_IA)

Quando `cobertura_dados_percentual > 95%` e sem anomalias críticas:

```
Status: PRONTO_PARA_IA
├─ Compras analisadas: 1500
├─ Problemas encontrados: 13 (0.9%)
├─ Cobertura: 99.1%
└─ Recomendações: 2

→ IAs podem analisar com confiança
```

### ⚠️ Dados com problemas (status = REQUER_REVISAO)

Quando há muitas anomalias ou gaps:

```
Status: REQUER_REVISAO
├─ Compras analisadas: 1500
├─ Problemas encontrados: 150 (10%)
├─ Cobertura: 85%
└─ Recomendações: 5

→ Revisar dados antes de executar IAs
```

---

## Próximas etapas

1. **Semana 1**: Rodar validação e identificar problemas
2. **Semana 2**: Corrigir dados (trabalho manual pequeno)
3. **Semana 2-3**: Validação retorna "PRONTO_PARA_IA"
4. **Semana 3-4**: Iniciar Comprador IA com dados confiáveis

---

## Troubleshooting

**Erro: "Compra não encontrada"**
→ Verificar se IDs estão corretos no WebPostos

**Erro: "Número de anomalias muito alto"**
→ Normal em primeira execução. Isso IDENTIFICA os problemas que precisam ser corrigidos.

**Pergunta: "Todos os dados com problema devem ser corrigidos?"**
→ Não. Foque nos problemas que afetam compras/estoque/custo. Anomalias menores podem ser aceitas se <5% dos registros.

---

## KPIs para acompanhar

| Métrica | Inicial | Target |
|---------|---------|--------|
| Cobertura dados | ? | >95% |
| Problemas encontrados | ? | <5% |
| Anomalias de preço | ? | <3% |
| Status | REQUER_REVISAO | PRONTO_PARA_IA |

---

Agora execute: `pytest tests/services/test_compras_validator.py -v`
