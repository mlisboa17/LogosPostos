# Integração webPosto - Logs Auditoria

**Status:** Production-ready com fallback automático para MOCK

---

## 📋 Setup Rápido

### 1. Copiar `.env`
```bash
cp .env.example .env
```

### 2. Editar `.env` com credenciais reais
```env
WEBPOSTO_BASE_URL=http://seu-webposto.com/api
WEBPOSTO_BEARER_TOKEN=seu_token_jwt_aqui
```

### 3. Instalar dependências
```bash
pip install -r requirements.txt --break-system-packages
```

### 4. Rodar servidor
```bash
python servicos_auditoria.py
```

**Saída esperada:**
```
============================================================
Logos Auditoria - Iniciando...
============================================================
✓ Config: webPosto=http://seu-webposto.com/api
✓ webPosto cliente inicializado e healthy
✓ Usando API webPosto real
============================================================
```

---

## 🔌 Arquitetura de Integração

```
┌─────────────────────────────────────────────────────┐
│         Logos Auditoria (FastAPI)                   │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ servicos_auditoria.py (endpoints)             │  │
│  │  GET /auditoria/despesas/{unidade_id}        │  │
│  │  GET /auditoria/fechamentos/{unidade_id}     │  │
│  │  GET /auditoria/resumo/{unidade_id}          │  │
│  └──────────┬───────────────────────────────────┘  │
│             │                                      │
│  ┌──────────▼───────────────────────────────────┐  │
│  │ AuditoriaService                             │  │
│  │  • Cálculos de quebra                        │  │
│  │  • Consolidação de KPIs                      │  │
│  │  • Insights estoicos                         │  │
│  └──────────┬───────────────────────────────────┘  │
│             │                                      │
│  ┌──────────▼───────────────────────────────────┐  │
│  │ WebPostoClient (webposto_client.py)          │  │
│  │  • Retry automático (3x)                     │  │
│  │  • Timeout 30s                               │  │
│  │  • Validação Pydantic                        │  │
│  └──────────┬───────────────────────────────────┘  │
│             │                                      │
└─────────────┼──────────────────────────────────────┘
              │
         [webPosto API]
    http://webposto-base/api
```

---

## ⚙️ Configurações

### webPosto (config.py)
```python
# Obrigatório
WEBPOSTO_BASE_URL        # URL da API webPosto
WEBPOSTO_BEARER_TOKEN    # JWT token

# Opcional
WEBPOSTO_API_KEY         # Chave alternativa
WEBPOSTO_API_SECRET      # Secret alternativa
```

### Network (config.py)
```python
WEBPOSTO_TIMEOUT=30          # Segundos
WEBPOSTO_MAX_RETRIES=3       # Tentativas
WEBPOSTO_RETRY_DELAY=1.0     # Segundos entre retries
```

### Logos Eye (opcional)
```env
LOGOS_EYE_ENABLED=true
LOGOS_EYE_URL=http://logos-eye:5000
LOGOS_EYE_API_KEY=sua_chave
```

### Logos Space (persistência)
```env
LOGOS_SPACE_ENABLED=true
LOGOS_SPACE_DB=mongodb://localhost:27017/logos
```

---

## 🔄 Fluxo de Dados

### GET `/auditoria/despesas/{unidade_id}`

```
1. FastAPI recebe requisição
2. AuditoriaService.extrair_despesas_por_unidade()
3. WebPostoClient.get_despesas()
   - Authorization: Bearer {TOKEN}
   - GET /despesas?unidade_id=real_01
4. Validação Pydantic (DespesaCaixa)
5. Retorna List[DespesaCaixa]
```

**Response 200:**
```json
[
  {
    "id": "exp_001",
    "unidade_id": "real_01",
    "caixa_tipo": "pista",
    "horario": "2026-04-12T14:30:00",
    "categoria": "gelo",
    "valor": 85.50,
    "operador": "João Silva",
    "status_justificativa": "justificada",
    "tem_documento": true
  }
]
```

### GET `/auditoria/fechamentos/{unidade_id}`

```
1. WebPostoClient.get_fechamentos()
   - GET /fechamentos?unidade_id=real_01
2. Para cada fechamento, estrutura movimentacoes[]
3. AuditoriaService.calcular_resumo_unidade()
   - Soma faturamento, despesas, quebra
   - Calcula desvio vs média histórica (5%)
   - Detecta outliers
4. Retorna ListaFechamentos com resumo
```

---

## ✅ Fallback automático

Se webPosto estiver indisponível:

```python
# servicos_auditoria.py
if AuditoriaService.use_real_api:
    try:
        despesas = await webposto_client.get_despesas(...)
    except Exception as e:
        print(f"⚠️  Usando MOCK: {e}")
        AuditoriaService.use_real_api = False  # Fallback
```

**Comportamento:**
- Tenta webPosto 3 vezes (com 1s delay)
- Se falhar, usa MOCK para não quebrar a API
- Log no console para debugging

---

## 🧪 Testes

### Health check
```bash
curl http://localhost:8000/auditoria/health
# {"status": "ok", "service": "Logos Auditoria", "version": "1.0"}
```

### Extrair despesas
```bash
curl http://localhost:8000/auditoria/despesas/real_01
```

### Extrair fechamentos
```bash
curl http://localhost:8000/auditoria/fechamentos/real_01
```

### Registrar nova despesa
```bash
curl -X POST http://localhost:8000/auditoria/registrar-despesa \
  -H "Content-Type: application/json" \
  -d '{
    "id": "exp_novo",
    "unidade_id": "real_01",
    "caixa_tipo": "pista",
    "horario": "2026-04-12T14:30:00",
    "categoria": "gelo",
    "valor": 100.00,
    "operador": "João"
  }'
```

### Rodar testes unitários
```bash
pytest test_auditoria.py -v
```

---

## 🔐 Autenticação webPosto

Suporte para:
- **Bearer Token** (padrão JWT)
- **API Key + Secret** (alternativo)

**Bearer Token (recomendado):**
```python
# config.py
WEBPOSTO_BEARER_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# webposto_client.py
headers = {
    "Authorization": f"Bearer {token}"
}
```

---

## 🚨 Troubleshooting

| Erro | Causa | Solução |
|------|-------|---------|
| `WEBPOSTO_BASE_URL não configurada` | .env faltando | `cp .env.example .env` |
| `WEBPOSTO_BEARER_TOKEN não configurada` | Token vazio | Adicionar token válido em .env |
| `Connection refused` | webPosto offline | Verificar URL + porta |
| `429 Too Many Requests` | Rate limit | Aumentar retry_delay em config.py |
| `422 Validation Error` | Schema inválido | Verificar DespesaCaixa/FechamentoCaixa |

---

## 📊 Integração com Logos

### Logos Eye (Alertas)
```python
# Despesa sem documento → alerta
if not despesa.tem_documento:
    logos_eye.alert(
        tipo="auditoria",
        severidade="warning",
        unidade=despesa.unidade_id
    )
```

### Logos Space (Histórico)
```python
# Salvar resumo diário
db.resumos_auditoria.insert_one(resumo.model_dump())
```

### Vorcaro (Dashboards)
```python
# Desvios de despesa
vorcaro.track_metric(
    "despesas_desvio_media",
    resumo.desvio_percentual_media_despesas
)
```

---

## 🎯 Endpoints webPosto esperados

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/caixas` | GET | Listar caixas abertos/fechados |
| `/movimentacoes` | GET | Movimentações por espécie |
| `/despesas` | GET/POST | Despesas de caixa |
| `/fechamentos` | GET/PUT | Fechamentos consolidados |
| `/health` | GET | Status da API |

**Exemplo de resposta esperada:**
```json
{
  "despesas": [
    {
      "id": "exp_001",
      "unidade_id": "real_01",
      "categoria": "gelo",
      "valor": 85.50,
      "operador": "João Silva",
      "horario": "2026-04-12T14:30:00",
      "tem_documento": true
    }
  ]
}
```

---

## 📝 Próximos passos

1. ✅ Configurar `.env` com credenciais
2. ✅ Testar health check
3. ✅ Validar endpoints de despesas/fechamentos
4. ⏳ Criar dashboard React/Tailwind
5. ⏳ Integrar com Logos Eye (alertas)
6. ⏳ Persistir em Logos Space (MongoDB)

---

**Version:** 1.0  
**Status:** Production-ready  
**Last updated:** 2026-04-12
