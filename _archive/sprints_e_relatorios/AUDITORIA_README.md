# Logos Auditoria - Estrutura de Dados

**Logos Mode: ON**. Documentação densa para auditar postos com rigor.

## 📋 O que você tem aqui

3 arquivos Python estruturados para extrair e validar despesas + fechamentos de caixa:

| Arquivo | Propósito |
|---------|-----------|
| `models_auditoria.py` | Modelos Pydantic (validação + esquemas) |
| `servicos_auditoria.py` | FastAPI endpoints + lógica de consolidação |
| `exemplo_uso.py` | Exemplos práticos e testes |

---

## 🎯 Estrutura de Dados

### 1. **DespesaCaixa** - Toda despesa registrada
```python
{
  "id": "exp_001",                          # Único
  "unidade_id": "real_01",                  # Real, Casa Caiada, VIP
  "caixa_tipo": "pista",                    # pista | conveniencia | restaurante
  "horario": "2026-04-12T14:30:00",
  "categoria": "gelo",                      # luz, gelo, vale_op, manutencao, etc
  "valor": 85.50,                           # Validado: > 0, arredondado em 2 casas
  "operador": "João Silva",
  "status_justificativa": "justificada",    # pendente | justificada | rejeitada | em_analise
  "tem_documento": true,                    # Flag: existe anexo?
  "documento_anexo": "/docs/gelo_001.pdf"
}
```

**Validações automáticas:**
- ✓ Valor > 0
- ✓ Valor arredondado para 2 casas decimais
- ✓ Categoria validada contra enum
- ✓ Status obrigatório

---

### 2. **FechamentoCaixa** - Consolidação diária por caixa
```python
{
  "id": "fech_001",
  "unidade_id": "real_01",
  "caixa_tipo": "pista",
  "horario_abertura": "2026-04-12T07:00:00",
  "horario_fechamento": "2026-04-12T23:00:00",
  
  # Faturamento
  "faturamento_bruto": 5420.50,
  "despesas_caixa_total": 130.50,
  
  # Saldos por espécie (detalhe abaixo)
  "movimentacoes": [
    {
      "especie": "dinheiro",
      "valor_esperado": 2500.00,
      "valor_informado": 2495.30,
      "diferenca": 4.70,              # Calculado automaticamente
      "variacao_percentual": 0.19     # Calculado automaticamente
    },
    // ... outras espécies
  ],
  
  # Caixa
  "saldo_esperado_dinheiro": 2500.00,
  "saldo_informado_dinheiro": 2495.30,
  "quebra_caixa": 4.70,                # Calculado automaticamente
  
  # Status
  "status": "fechado",                 # aberto | fechado | consolidado | em_auditoria
  "operador_fechamento": "Maria Santos",
  
  # Bandeiras para auditoria
  "flagged_auditoria": false,
  "motivo_auditoria": null,
  "despesas_sem_categoria": 0,
  "despesas_sem_documento": 0
}
```

**Cálculos automáticos:**
- `diferenca = valor_esperado - valor_informado`
- `variacao_percentual = (diferenca / valor_esperado) * 100`
- `quebra_caixa = saldo_esperado - saldo_informado`

---

### 3. **MovimentacaoEspecie** - Detalhamento por tipo de pagamento
6 espécies financeiras:
- `DINHEIRO` - Cédulas e moedas
- `PIX` - Transferências Pix
- `CARTAO_DEBITO` - Débito à vista
- `CARTAO_CREDITO` - Crédito
- `FROTISTA` - Combustível abonado
- `PRAZO` - Fiado/conta-corrente

**Cálculos validados:**
- Diferença entre esperado e informado
- Variação percentual
- Bandeiras outliers (> 1% variação)

---

### 4. **ResumoAuditoriaUnidade** - KPIs + Insights Estoicos
Consolidação diária por unidade:

```python
{
  "unidade_id": "real_01",
  "data": "2026-04-12",
  
  # Números
  "faturamento_total": 5420.50,        # Soma de caixas
  "despesas_operacionais": 130.50,
  "saldo_especie_total": 2495.30,      # Dinheiro em cofres
  
  # Quebras
  "quebra_total": 4.70,
  "quebra_percentual": 0.09,            # Vs faturamento
  
  # Status de caixas
  "caixas_fechados": 3,
  "caixas_abertos": 0,
  "caixas_em_auditoria": 1,
  
  # Alertas
  "despesas_sem_categoria_total": 2,
  "despesas_sem_documento_total": 3,
  "caixas_com_quebra_acima_10": 1,      # Quebra > R$10
  
  # Insight Estoico
  "desvio_percentual_media_despesas": -2.25,  # Vs 5% padrão
  "outlier_unidade": false              # True se |desvio| > 10%
}
```

---

## 🔌 API Endpoints

### GET `/auditoria/despesas/{unidade_id}`
Retorna lista de despesas estruturadas.
```bash
curl http://localhost:8000/auditoria/despesas/real_01
```

### GET `/auditoria/fechamentos/{unidade_id}`
Retorna fechamentos + resumo consolidado.
```bash
curl http://localhost:8000/auditoria/fechamentos/real_01
```

### GET `/auditoria/resumo/{unidade_id}`
KPIs de auditoria (insights estoicos).
```bash
curl http://localhost:8000/auditoria/resumo/real_01
```

### GET `/auditoria/despesas-por-categoria/{unidade_id}`
Agrupamento por categoria com totais e bandeiras.
```bash
curl http://localhost:8000/auditoria/despesas-por-categoria/real_01
```

### POST `/auditoria/registrar-despesa`
Registra nova despesa com validação Pydantic.
```bash
curl -X POST http://localhost:8000/auditoria/registrar-despesa \
  -H "Content-Type: application/json" \
  -d '{...}'
```

---

## 🚀 Como usar

### 1. **Instalar**
```bash
pip install fastapi pydantic python-dateutil uvicorn --break-system-packages
```

### 2. **Rodar a API**
```bash
python servicos_auditoria.py
```

API ativa em `http://localhost:8000`  
Docs: `http://localhost:8000/docs` (Swagger UI automático)

### 3. **Executar exemplos**
```bash
python exemplo_uso.py
```

---

## ✅ Validações incluídas

| Campo | Validação |
|-------|-----------|
| `valor` (despesas) | > 0, arredondado em 2 casas |
| `categoria` | Enum estrito (9 categorias) |
| `status_justificativa` | Enum estrito (4 status) |
| `caixa_tipo` | Enum estrito (3 tipos) |
| `especie` | Enum estrito (6 espécies) |
| `horario` | ISO 8601 datetime |
| `id` | Obrigatório (string única) |

Pydantic lança `ValidationError` em violações → FastAPI retorna 422.

---

## 🎯 Integração com ecossistema

### Logos Eye (Monitoramento)
Despesas sem documento ou categoria → Alertas em tempo real
```python
if despesa.tem_documento == False:
    logos_eye.alert(
        tipo="auditoria",
        severidade="warning",
        mensagem=f"Despesa {despesa.id} sem documento"
    )
```

### Logos Space (Consolidação)
Resumos diários salvos em banco → Consultas históricas
```python
db.resumos_auditoria.insert_one(resumo.dict())
```

### Vorcaro (Analytics)
Desvios percentuais → Gráficos de tendência
```python
vorcaro.track_metric(
    "despesas_desvio_media",
    resumo.desvio_percentual_media_despesas
)
```

---

## 📊 Próximas Etapas

1. **Integração webPosto real** - Substituir MOCK por chamadas à API webPosto
2. **Persistência** - MongoDB/PostgreSQL para histórico
3. **Dashboard React/Tailwind** - Visualizar despesas + fechamentos
4. **Logos Eye hooks** - Alertas automáticos
5. **Reconciliação automática** - Compara sistema vs operador
6. **Machine Learning** - Detectar anomalias padrão

---

## 🔒 Notas de Segurança

- **Validação rigorosa:** Pydantic valida toda entrada antes de processar
- **Sem confiança no operador:** Diferenças sempre capturadas
- **Auditoria trail:** Cada despesa tem ID único + timestamp
- **Categorização obrigatória:** Sem "outros" genéricos

---

**Versão:** 1.0  
**Última atualização:** 2026-04-12  
**Status:** Production-ready
