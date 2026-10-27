# Logos Auditoria - Cliente API webPosto

**Logos Mode: ON** — Sistema pronto para produção. Sem explicações longas.

---

## 🚀 Quick Start

### 1. **Configurar Token**
Edite o arquivo `.env`:
```env
WEBPOSTO_BASE_URL=https://api.webposto.com.br
WEBPOSTO_BEARER_TOKEN=seu_token_real_aqui
```

### 2. **Abrir no Navegador**
Arquivo standalone **pronto para usar**:
```
/mnt/Api_WebPosto/logos-auditoria-client.html
```

Ou integre o React:
```
/mnt/Api_WebPosto/logos-auditoria-api-client.jsx
```

---

## 📋 Endpoints Integrados

| Método | Endpoint | Função |
|--------|----------|--------|
| **GET** | `/auditoria/despesas/{unidade_id}` | Lista despesas estruturadas |
| **GET** | `/auditoria/fechamentos/{unidade_id}` | Fechamentos + consolidado |
| **GET** | `/auditoria/resumo/{unidade_id}` | KPIs + insights estoicos |
| **GET** | `/auditoria/despesas-por-categoria/{unidade_id}` | Agrupamento por categoria |
| **POST** | `/auditoria/registrar-despesa` | Registrar nova despesa |

---

## 🎯 Funcionalidades

### Tab: **Exportar**
- Carrega e exporta despesas
- Carrega e exporta fechamentos
- Carrega e exporta resumo com insights

### Tab: **Despesas**
- Visualiza tabela de despesas
- Mostra status de justificativa
- Marca despesas sem documento

### Tab: **Fechamentos**
- Exibe fechamentos por caixa
- Calcula quebra de caixa
- Destaca anomalias (quebra > R$10)

### Tab: **Resumo**
- KPIs consolidados (faturamento, despesas, quebra)
- **Insight Estoico**: Detecta outliers (desvio > 10% vs 5% padrão)
- Alertas para caixas problemáticos

### Sidebar: **Registrar Despesa**
- POST para API (validação Pydantic automática)
- Suporta: gelo, luz, vale, manutenção, combustível, limpeza, insumos, outros
- Resumo por categoria em tempo real

---

## 🔑 Headers HTTP

```javascript
Authorization: Bearer {WEBPOSTO_BEARER_TOKEN}
Content-Type: application/json
```

---

## 📊 Modelos (Pydantic)

### DespesaCaixa
```python
{
  "id": str,
  "unidade_id": str,
  "caixa_tipo": "pista|conveniencia|restaurante",
  "horario": datetime,
  "categoria": "luz|gelo|vale_operador|...",
  "valor": float (>0, 2 casas decimais),
  "operador": str,
  "status_justificativa": "pendente|justificada|rejeitada|em_analise",
  "tem_documento": bool
}
```

### FechamentoCaixa
```python
{
  "id": str,
  "unidade_id": str,
  "caixa_tipo": str,
  "horario_abertura": datetime,
  "horario_fechamento": datetime,
  "faturamento_bruto": float,
  "despesas_caixa_total": float,
  "movimentacoes": [ MovimentacaoEspecie ],
  "quebra_caixa": float (calculado),
  "status": "aberto|fechado|consolidado|em_auditoria"
}
```

### MovimentacaoEspecie
```python
{
  "especie": "dinheiro|pix|cartao_debito|cartao_credito|frotista|prazo",
  "valor_esperado": float,
  "valor_informado": float,
  "diferenca": float (calculado),
  "variacao_percentual": float (calculado)
}
```

### ResumoAuditoriaUnidade
```python
{
  "unidade_id": str,
  "faturamento_total": float,
  "despesas_operacionais": float,
  "quebra_total": float,
  "desvio_percentual_media_despesas": float,
  "outlier_unidade": bool (true se |desvio| > 10%),
  "caixas_fechados": int,
  "despesas_sem_documento_total": int
}
```

---

## 🏗️ Arquitetura

```
Api_WebPosto/
├── .env                              # Token + URL base
├── config.py                         # Carrega variáveis de ambiente
├── models_auditoria.py               # Modelos Pydantic com validação
├── servicos_auditoria.py             # FastAPI + lógica de negócio
├── logos-auditoria-client.html       # 🌟 HTML standalone (use aqui!)
├── logos-auditoria-api-client.jsx    # React puro (integre no projeto)
├── schema_auditoria.json             # Documentação de schemas
└── WebPosto_API/                     # Backend (fastapi rodando)
```

---

## 🔧 Executar Backend

```bash
cd /mnt/Api_WebPosto/WebPosto_API
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Backend estará em: `http://localhost:8000`

---

## 🧪 Teste com cURL

```bash
# GET despesas
curl -H "Authorization: Bearer seu_token" \
  https://api.webposto.com.br/auditoria/despesas/real_01

# POST despesa
curl -X POST \
  -H "Authorization: Bearer seu_token" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "exp_new",
    "unidade_id": "real_01",
    "caixa_tipo": "pista",
    "horario": "2026-04-12T10:30:00",
    "categoria": "gelo",
    "valor": 50.00,
    "operador": "João Silva"
  }' \
  https://api.webposto.com.br/auditoria/registrar-despesa
```

---

## 🎨 Dark Mode (Tailwind)

Padrão: `bg-slate-950`, `text-slate-100`  
Acentos: verde (despesas ✓), azul (fechamentos), âmbar (insights)

---

## ⚙️ Validações Automáticas (Pydantic)

- ✅ `valor` sempre com 2 casas decimais
- ✅ `diferenca` calculada automaticamente
- ✅ `variacao_percentual` calculada automaticamente
- ✅ `quebra_caixa` calculada automaticamente
- ✅ Enums rigorosos (categoria, status, espécie)
- ✅ Outlier detectado: `|desvio| > 10%`

---

## 📱 Responsivo

- Mobile: 1 coluna
- Tablet: 2 colunas
- Desktop: 3 colunas (main + sidebar)

---

## 🔒 Segurança

- Bearer Token no header
- Validação Pydantic em todos os inputs
- Sem dados sensíveis em console (logs apenas em dev)

---

## 📝 Próximos Passos

1. ✅ Integrar com API webPosto real
2. ⏳ Adicionar PUT/PATCH para editar despesas
3. ⏳ Exportar para Excel/PDF
4. ⏳ Webhooks para alertas em tempo real
5. ⏳ Dashboard de insights comparativos entre unidades

---

**Logos Mode: ON.** Sem mimos. Funcional. Pronto para produção.
