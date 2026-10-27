# Dashboard Logos Auditoria

**Dark mode pragmático, focado em dados. Zero distrações.**

---

## 🚀 Quick start

### Opção 1: HTML Standalone (Recomendado)
```bash
# 1. Certificar que API está rodando
python servicos_auditoria.py

# 2. Abrir no navegador
open index.html
# ou
firefox index.html
# ou
chrome index.html
```

**URL:** `file:///path/to/index.html`

### Opção 2: React JSX (desenvolvimento)
```bash
# Usar ferramenta de build (Vite, Create React App, etc)
# Ou copiar dashboard_auditoria.jsx para seu projeto React
```

---

## 📊 Funcionalidades

### 1. **Seletor de Unidade + Data**
```
[Real ▼] [2026-04-12] [Carregando...]
```
- Real, Casa Caiada, VIP
- Filtra dados em tempo real

### 2. **Cards KPI**
```
┌─────────────────────────────────────────┐
│ Faturamento Bruto                    💰 │
│ R$ 5.420,50                             │
│ 2.4% em despesas                        │
├─────────────────────────────────────────┤
│ Despesas Operacionais               📊 │
│ R$ 130,50                               │
│ Desvio: -2.5%                           │
├─────────────────────────────────────────┤
│ Saldo em Espécie                    💵 │
│ R$ 2.495,30                             │
│ 3 caixas fechados                       │
├─────────────────────────────────────────┤
│ Quebra de Caixa                     📉 │
│ R$ 4,70  [ALERTA SE > R$10]             │
│ 0.09% do faturamento                    │
└─────────────────────────────────────────┘
```

### 3. **Tabela de Movimentações**
Detalhamento por espécie financeira:
- DINHEIRO, PIX, CARTÃO_DÉBITO, CARTÃO_CRÉDITO, FROTISTA, PRAZO
- Valor esperado vs informado
- Diferença em R$ e %
- Cores: 🔴 RED (diferença > 0), 🟢 GREEN (OK)

### 4. **Auditoria de Despesas**
Todas as despesas com flags:
```
Horário  | Categoria      | Valor    | Operador     | Doc | Status
---------|----------------|----------|--------------|-----|----------
14:30    | gelo           | R$ 85.50 | João Silva   | ✓   | justificada
16:45    | luz            | R$ 45.00 | Maria Santos | ✗   | pendente ⚠️
12:00    | vale_operador  | R$120.00 | Pedro Costa  | ✓   | justificada
```

**Coluna Documento:**
- ✓ (verde) = tem anexo
- ✗ (vermelho) = SEM ANEXO (linha destaca em vermelho)

### 5. **Painel Insights do Auditor**
Alertas estoicos automáticos:
```
⚠️ Unidade outlier: desvio de 15.2% vs padrão 5%
🔴 Quebra crítica: R$ 45.80 (0.85%)
📄 2 despesa(s) sem documento anexo
🏷️ 1 despesa(s) sem categoria
🔍 1 caixa(s) em auditoria
```

---

## 🎨 Design

- **Dark Mode:** Fundo gray-950, texto white
- **Cores:**
  - 🔴 RED-500: Alertas críticos, diferenças negativas
  - 🟠 ORANGE-400: Avisos (variação > 1%)
  - 🟢 GREEN-400: OK, sem problemas
  - 🔵 BLUE-500: Informativo
  - 🟡 YELLOW-500: Atenção (documentos faltando)

---

## 🔌 API Endpoints Consumidos

| Endpoint | Propósito |
|----------|-----------|
| `GET /auditoria/resumo/{unidade_id}` | KPIs consolidados |
| `GET /auditoria/despesas/{unidade_id}` | Lista de despesas |
| `GET /auditoria/fechamentos/{unidade_id}` | Fechamentos + movimentações |

**Response esperada:**
```json
{
  "resumo": {
    "unidade_id": "real_01",
    "faturamento_total": 5420.50,
    "despesas_operacionais": 130.50,
    "saldo_especie_total": 2495.30,
    "quebra_total": 4.70,
    "desvio_percentual_media_despesas": -2.5,
    "outlier_unidade": false
  }
}
```

---

## 🛠️ Troubleshooting

| Problema | Solução |
|----------|---------|
| `ERR_ACCESS_DENIED` ao abrir HTML | Abrir com `http://localhost:8080` em vez de `file://` (CORS) |
| `Error ao carregar dados` | Verificar se API está rodando em `http://localhost:8000` |
| Dados antigos/em cache | Ctrl+Shift+R (hard refresh) ou F12 → Network → Disable cache |
| Gráficos vazios | Aguardar carregamento, verificar console (F12) |

### CORS Issue (se necessário)
Se aparecer erro CORS, adicionar no `servicos_auditoria.py`:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 📱 Responsivo

- **Desktop:** Layout 3 colunas (KPIs + 2 seções) + sidebar
- **Tablet:** Grid 2x2 para KPIs
- **Mobile:** Stack vertical, 1 coluna

---

## 🎯 Próximas Melhorias

- [ ] Gráfico de comparativo entre unidades (Recharts BarChart)
- [ ] Exportar relatório em PDF
- [ ] Integração com Logos Eye (webhooks)
- [ ] Cache local (localStorage)
- [ ] Temas customizáveis
- [ ] Dark/Light mode toggle

---

## 🔐 Segurança

- ✓ HTTPS recomendado em produção
- ✓ Sem dados sensíveis em localStorage
- ✓ Token da API não exposto no frontend
- ✓ Validação Pydantic no backend

---

## 📝 Arquivos

| Arquivo | Propósito |
|---------|-----------|
| `index.html` | Dashboard standalone (abrir no navegador) |
| `dashboard_auditoria.jsx` | Componente React (importar em projeto) |
| `DASHBOARD.md` | Documentação (este arquivo) |

---

## ✅ Checklist

- [ ] API rodando (`http://localhost:8000`)
- [ ] `index.html` acessível
- [ ] Filtro de unidade funcionando
- [ ] Dados carregando (sem erro)
- [ ] Cards KPI preenchidos
- [ ] Tabelas com dados reais
- [ ] Insights mostrando alertas
- [ ] Responsive OK no mobile

---

**Versão:** 1.0  
**Status:** Production-ready  
**Last updated:** 2026-04-12
