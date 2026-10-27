# Setup Completo - Logos Auditoria + webPosto

**⏱️ Tempo estimado:** 5-10 minutos

---

## Pré-requisitos

- Python 3.9+
- pip (gestor de pacotes)
- Acesso a credenciais webPosto (Base URL + Bearer Token)

---

## ✅ Passo 1: Clonar/Copiar arquivos

```bash
# Assumindo que você já tem os arquivos em:
# /sessions/elegant-modest-volta/mnt/Api_WebPosto/

cd /sessions/elegant-modest-volta/mnt/Api_WebPosto
ls -la
```

Arquivos esperados:
```
✓ config.py
✓ models_auditoria.py
✓ webposto_client.py
✓ servicos_auditoria.py
✓ requirements.txt
✓ .env.example
✓ AUDITORIA_README.md
✓ INTEGRACAO_WEBPOSTO.md
✓ startup.sh
```

---

## ✅ Passo 2: Preparar configurações

### Opção A: Automático (Linux/Mac)
```bash
chmod +x startup.sh
./startup.sh
```

### Opção B: Manual

**2.1 - Copiar arquivo de configurações**
```bash
cp .env.example .env
```

**2.2 - Editar `.env` com suas credenciais**
```bash
# Abrir em seu editor favorito
nano .env  # ou vim, code, etc
```

Editar linhas OBRIGATÓRIAS:
```env
# OBRIGATÓRIO: URL base da API webPosto
WEBPOSTO_BASE_URL=http://seu-webposto.com/api

# OBRIGATÓRIO: Bearer token JWT para autenticação
WEBPOSTO_BEARER_TOKEN=seu_token_jwt_aqui_xyz123...
```

Opcional (se usar Logos Eye, Space, Vorcaro):
```env
LOGOS_EYE_ENABLED=true
LOGOS_EYE_URL=http://logos-eye.localhost:5000

LOGOS_SPACE_ENABLED=true
LOGOS_SPACE_DB=mongodb://localhost:27017/logos

VORCARO_ENABLED=false
```

**2.3 - Validar que .env foi salvo**
```bash
cat .env | grep WEBPOSTO
# Deve mostrar sua URL e token
```

---

## ✅ Passo 3: Instalar dependências

```bash
pip install -r requirements.txt --break-system-packages
```

**Saída esperada:**
```
Successfully installed fastapi uvicorn pydantic httpx pytest ...
```

Se houver erro, tentar:
```bash
python3 -m pip install -r requirements.txt --break-system-packages
```

---

## ✅ Passo 4: Validar configurações

```bash
python config.py
```

**Saída esperada (sucesso):**
```
✓ Config: webPosto=http://seu-webposto.com/api
✓ LogosEye=true
✓ LogosSpace=true
✓ Configurações carregadas com sucesso!
```

**Se erro:**
- Verificar se `.env` foi editado corretamente
- Verificar se `WEBPOSTO_BASE_URL` e `WEBPOSTO_BEARER_TOKEN` não estão vazios
- Verificar se não há espaços extras nas linhas

---

## ✅ Passo 5: Iniciar servidor

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

INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

Se aparecer `⚠️  Usando dados MOCK (webPosto indisponível)`:
- webPosto está offline ou credenciais erradas
- API continuará funcionando com dados MOCK para testes

---

## ✅ Passo 6: Testar endpoints

Abrir novo terminal (manter servidor rodando):

### Health check
```bash
curl http://localhost:8000/auditoria/health
```

**Resposta esperada:**
```json
{"status": "ok", "service": "Logos Auditoria", "version": "1.0"}
```

### Extrair despesas
```bash
curl http://localhost:8000/auditoria/despesas/real_01
```

**Resposta esperada:**
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

### Extrair fechamentos
```bash
curl http://localhost:8000/auditoria/fechamentos/real_01
```

### Resumo de auditoria (KPIs + insights)
```bash
curl http://localhost:8000/auditoria/resumo/real_01
```

### Documentação interativa (Swagger UI)
Abrir no navegador:
```
http://localhost:8000/docs
```

---

## ✅ Passo 7: Rodar testes

```bash
pytest test_auditoria.py -v
```

**Saída esperada:**
```
test_auditoria.py::TestDespesaCaixa::test_criar_despesa_valida PASSED
test_auditoria.py::TestDespesaCaixa::test_despesa_valor_negativo PASSED
test_auditoria.py::TestMovimentacaoEspecie::test_movimento_calcula_diferenca PASSED
...
======================== 20 passed in 1.23s ========================
```

---

## 🎯 Próximas etapas

### 1. Criar Dashboard React/Tailwind
```bash
# Consumir endpoints da API
# GET /auditoria/despesas/{unidade_id}
# GET /auditoria/fechamentos/{unidade_id}
# GET /auditoria/resumo/{unidade_id}
```

### 2. Integrar com Logos Eye (Alertas)
```python
# Adicionar alerts para:
# - Despesas sem documento
# - Despesas sem categoria
# - Quebra de caixa > R$10
```

### 3. Persistir em Logos Space (MongoDB)
```python
# Salvar resumos diários para histórico
# Consultas históricas por unidade
```

### 4. Analytics com Vorcaro
```python
# Rastrear desvios de despesa
# Gráficos de tendência
# Anomalias por unidade
```

---

## 🆘 Troubleshooting

### `ModuleNotFoundError: No module named 'fastapi'`
```bash
pip install -r requirements.txt --break-system-packages
```

### `WEBPOSTO_BEARER_TOKEN não configurada`
Editar `.env` e adicionar token válido:
```bash
nano .env
# WEBPOSTO_BEARER_TOKEN=seu_token_aqui
```

### `Connection refused (webPosto offline)`
- Verificar se webPosto está rodando
- Verificar se `WEBPOSTO_BASE_URL` está correto
- API continuará com dados MOCK como fallback

### Porta 8000 já em uso
```bash
# Usar porta diferente
PORT=8001 python servicos_auditoria.py
```

### Erro de validação Pydantic (422)
- Schema dos dados do webPosto não bate com modelos
- Verificar estrutura JSON retornada por webPosto
- Comparar com `schema_auditoria.json`

---

## 📚 Documentação

| Arquivo | Propósito |
|---------|-----------|
| `AUDITORIA_README.md` | Estrutura de dados (modelos, enums) |
| `INTEGRACAO_WEBPOSTO.md` | Setup detalhado de integração |
| `schema_auditoria.json` | Schema completo OpenAPI |
| `requirements.txt` | Dependências Python |
| `.env.example` | Template de configurações |

---

## ✅ Checklist de verificação

- [ ] `.env` criado e editado com credenciais reais
- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] Configurações validadas (`python config.py`)
- [ ] Servidor rodando (`python servicos_auditoria.py`)
- [ ] Health check OK (`curl http://localhost:8000/auditoria/health`)
- [ ] Endpoints funcionando (testes com curl)
- [ ] Testes unitários passando (`pytest test_auditoria.py -v`)
- [ ] Documentação Swagger acessível (`http://localhost:8000/docs`)

---

## 🚀 Você está pronto!

Logos Auditoria está configurado e conectado ao webPosto.

**Próximo:** Criar dashboard React/Tailwind para visualizar dados.

---

**Versão:** 1.0  
**Última atualização:** 2026-04-12  
**Mantido por:** Logos Engineering
