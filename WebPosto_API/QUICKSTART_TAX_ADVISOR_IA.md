# 🚀 QUICKSTART - TAX ADVISOR IA

## Comece agora

### 1. Rodar os testes

```bash
cd WebPosto_API

# Rodar testes do Tax Advisor IA
pytest tests/services/test_tax_advisor_analyzer.py -v
```

**Resultado esperado**:
```
test_valid_ncm PASSED
test_ncm_formato_invalido_poucos_digitos PASSED
test_ncm_formato_invalido_nao_numerico PASSED
test_ncm_vazio PASSED
test_ncm_checksum_valido PASSED
test_ncm_checksum_invalido PASSED
test_cest_vazio_valido PASSED
test_cest_valido PASSED
test_cest_formato_invalido PASSED
test_cest_nao_numerico PASSED
test_cst_valido_simples PASSED
test_cst_invalido_para_regime PASSED
test_cst_formato_invalido PASSED
test_detect_ncm_inconsistente PASSED
test_no_divergencias_quando_consistente PASSED
test_validate_tax_calculation PASSED
test_tax_calculation_exemplo_concreto PASSED
test_find_produtos_sem_ncm PASSED
test_generate_tax_audit_report PASSED
test_report_status_critico_quando_ha_problemas PASSED

✅ 20 passed
```

---

### 2. Usar via API REST

**Iniciar servidor**:
```bash
python -m uvicorn src.interfaces.http.app:app --reload
```

---

## 📊 ENDPOINTS DO TAX ADVISOR IA

### 1️⃣ **Auditoria Tributária Completa**

```bash
curl http://localhost:8000/api/v1/tax-advisor/audit-report
```

**Resposta**:
```json
{
  "data_audit": "2024-08-17T15:30:00",
  "estado": "PE",
  "regime": "SIMPLES",
  "problemas_encontrados": 15,
  "problemas_criticos": 3,
  "divergencias": [
    {
      "tipo": "NCM_INCONSISTENTE",
      "produto_id": "SKU_CAFE",
      "ncms_encontrados": ["27160000", "27160001"],
      "severidade": "ALTA",
      "problema": "Produto tem 2 NCMs diferentes",
      "recomendacao": "Unificar NCM para 27160000"
    }
  ],
  "produtos_sem_classificacao": 8,
  "risco_fiscal_estimado": 15000.0,
  "recomendacoes": [
    "Corrigir 15 divergências de classificação",
    "Classificar 8 produtos sem NCM/CEST"
  ],
  "status": "CRÍTICO"
}
```

**Interpretação**:
- **CRÍTICO**: Ação imediata necessária
- Risco fiscal: R$ 15.000 em potencial multa
- 3 problemas graves precisam correção

---

### 2️⃣ **Divergências de Classificação**

```bash
curl http://localhost:8000/api/v1/tax-advisor/divergencias?periodo_dias=30
```

**Resposta**:
```json
[
  {
    "tipo": "NCM_INCONSISTENTE",
    "produto_id": "SKU_CAFE",
    "ncms_encontrados": ["27160000", "27160001"],
    "severidade": "ALTA",
    "problema": "Produto tem 2 NCMs diferentes em notas diferentes",
    "recomendacao": "Revisar e unificar para um único NCM"
  },
  {
    "tipo": "CST_INCONSISTENTE",
    "produto_id": "SKU_LEITE",
    "csts_encontrados": ["00", "20"],
    "severidade": "MÉDIA",
    "problema": "Produto tem 2 CSTs diferentes",
    "recomendacao": "Unificar CST conforme regime"
  }
]
```

**O que fazer**:
- ALTA: Corrigir hoje (afeta nota fiscal)
- MÉDIA: Corrigir esta semana (risco de rejeição)

---

### 3️⃣ **Produtos Sem Classificação**

```bash
curl http://localhost:8000/api/v1/tax-advisor/sem-classificacao
```

**Resposta**:
```json
[
  {
    "produto_id": "SKU_NOVO_1",
    "descricao": "Refrigerante Genérico",
    "tipo_falta": "NCM_FALTANDO",
    "severidade": "ALTA",
    "recomendacao": "Classificar produto com NCM válido"
  },
  {
    "produto_id": "SKU_NOVO_2",
    "descricao": "Bebida Energética X",
    "tipo_falta": "NCM_FALTANDO",
    "severidade": "ALTA",
    "recomendacao": "Classificar produto com NCM válido"
  }
]
```

**O que fazer**:
- Bloquear venda desses produtos até classificação
- Usar NCM similaridade para avaliar (Ex: bebida = 22029000)

---

### 4️⃣ **Validar NCM Individual**

```bash
curl -X POST http://localhost:8000/api/v1/tax-advisor/validar-ncm \
  -H "Content-Type: application/json" \
  -d '{
    "produto_id": "SKU_CAFE",
    "ncm": "27160000"
  }'
```

**Resposta**:
```json
{
  "produto_id": "SKU_CAFE",
  "ncm": "27160000",
  "is_valid": true,
  "categoria": "COMBUSTÍVEL",
  "descricao": "Óleos minerais",
  "aliquota_ii": 0,
  "problemas": []
}
```

---

### 5️⃣ **Calcular Impostos (ICMS/PIS/COFINS)**

```bash
curl -X POST http://localhost:8000/api/v1/tax-advisor/calcular-impostos \
  -H "Content-Type: application/json" \
  -d '{
    "produto_id": "SKU_CAFE",
    "ncm": "27160000",
    "estado": "PE",
    "base_calculo": 1000.0
  }'
```

**Resposta**:
```json
{
  "produto_id": "SKU_CAFE",
  "base_calculo": 1000.0,
  "aliquota_icms": 12.0,
  "aliquota_pis": 1.65,
  "aliquota_cofins": 7.6,
  "icms": 120.0,
  "pis": 16.5,
  "cofins": 76.0,
  "total_impostos": 212.5,
  "margem_liquida": 787.5,
  "percentual_impostos": 21.25
}
```

**Interpretação**:
- De R$ 1.000 → R$ 212,50 em impostos (21,25%)
- Margem líquida: R$ 787,50

---

## 🎯 CENÁRIO DE USO REAL

### **Manhã - 9:00 AM**

Gestor fiscal pede: "Temos risco tributário?"

```bash
curl http://localhost:8000/api/v1/tax-advisor/audit-report
```

Resposta em < 2 segundos:
```
❌ CRÍTICO: 3 divergências NCM → R$ 15k de risco
⚠️  8 produtos sem classificação
💡 Ação: Corrigir hoje, classificar esta semana

→ Risco: Multa SEFAZ = R$ 15.000 + juros
```

### **9:30 AM - Revisão de divergências**

```bash
curl http://localhost:8000/api/v1/tax-advisor/divergencias
```

Lista as 3 divergências:
1. SKU_CAFE: NCM 27160000 vs 27160001 → Unificar
2. SKU_LEITE: CST 00 vs 20 → Revisar regime
3. SKU_SUCO: Sem CEST quando deveria ter → Adicionar

### **10:00 AM - Corrigir no ERP**

Após correções, rodar novamente:

```bash
curl http://localhost:8000/api/v1/tax-advisor/audit-report
```

Nova resposta:
```
✅ OK: 0 divergências
✅ 0 produtos sem classificação
✅ Status: OK - Sem risco fiscal detectado
```

---

## 💰 IMPACTO FISCAL

### Risco evitado

| Problema | Multa Potencial | Ação | Prevenção |
|----------|-----------------|------|-----------|
| NCM incorreto | R$ 5.000-10.000 | Validar antes de nota | Auditoria contínua |
| CEST faltando | R$ 3.000-7.000 | Classificar produtos | Validação no cadastro |
| CST divergente | R$ 2.000-5.000 | Unificar | Monitoramento |
| Produto sem NCM | Bloqueio de venda | Classificar | Ação preventiva |
| **TOTAL** | **R$ 15.000+** | **5 ações** | **100% prevenção** |

### O que você evita

1. ❌ Rejeição de notas pela SEFAZ
2. ❌ Multas e juros de mora
3. ❌ Bloqueio de crédito ICMS
4. ❌ Possível auditoria fiscal
5. ❌ Retrabalho de notas

---

## 📊 INTEGRAÇÃO COM COMPRADOR IA

### Fluxo completo

```
Comprador IA (O que comprar?)
        ↓
Tax Advisor IA (Classificação correta?)
        ↓
Precificador IA (Preço com impostos?)
        ↓
Decisão de compra → Execução
```

Exemplo:
- Comprador IA recomenda comprar Café
- Tax Advisor valida NCM 27160000 ✅
- Precificador calcula margem com 12% ICMS
- Compra executada com segurança fiscal

---

## ✅ O QUE VOCÊ TEM AGORA

✅ 7 validações tributárias operacionais
✅ 5 endpoints REST prontos para integrar
✅ 20 testes cobrindo todos cenários
✅ Detecção automática de divergências
✅ Cálculo de impostos por NCM/Estado
✅ Relatórios executivos automáticos

**Resultado esperado quando rodar**:
```json
{
  "problemas_criticos": 0,
  "produtos_sem_classificacao": 0,
  "risco_fiscal_estimado": 0,
  "status": "OK"
}
```

---

Agora execute: `pytest tests/services/test_tax_advisor_analyzer.py -v`

Depois teste: `curl http://localhost:8000/api/v1/tax-advisor/audit-report`
