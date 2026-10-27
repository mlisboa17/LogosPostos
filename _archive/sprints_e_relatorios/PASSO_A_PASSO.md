# PASSO-A-PASSO - Setup Local Logos Auditoria

**Logos Mode: ON. Instruções exatas e sequenciais.**

---

## 📌 PRÉ-REQUISITOS

Você precisa ter:
- [ ] Internet
- [ ] Computador Linux/macOS/Windows (WSL2)
- [ ] 50GB espaço em disco
- [ ] 4GB RAM disponível

---

## 🔴 PASSO 1: Clonar o código

```bash
# Abrir terminal/cmd

# Ir para onde quer o projeto
cd /home/seu-usuario
# OU
cd /Users/seu-usuario
# OU
cd C:\Users\seu-usuario (Windows)

# Clonar
git clone https://seu-repo.com/logos-auditoria.git
cd logos-auditoria

# Verificar se tem arquivo setup_local.sh
ls -la setup_local.sh
# Esperado: -rwxr-xr-x (verde)
```

---

## 🟠 PASSO 2: Executar script de setup

```bash
# Tornar executável (se não estiver)
chmod +x setup_local.sh

# RODAR SCRIPT (isso vai demorar ~5-10 min)
./setup_local.sh

# O script vai:
# ✓ Detectar seu sistema (Linux/macOS/Windows)
# ✓ Instalar Docker
# ✓ Instalar Python 3.11
# ✓ Instalar dependências
# ✓ Criar pasta venv
# ✓ Instalar pacotes Python
# ✓ Build Docker image
# ✓ Iniciar stack Docker
# ✓ Rodar testes
```

**Esperar até ver:**
```
✓ SETUP LOCAL COMPLETO!
```

---

## 🟡 PASSO 3: Ativar virtual environment

```bash
# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

# Esperado: verá (venv) antes do prompt
# Exemplo: (venv) user@machine:~/logos-auditoria$
```

---

## 🟢 PASSO 4: Verificar que tudo está rodando

```bash
# Ver containers Docker
docker-compose ps

# Esperado: 6 containers "Up"
# - api
# - mongo
# - redis  
# - nginx
# - prometheus
# - grafana
```

Se algum estiver "Exit" ou "unhealthy":
```bash
docker-compose logs api
# Ver o erro e reportar
```

---

## 🟢 PASSO 5: Testar API

```bash
# Health check
curl http://localhost:8000/auditoria/health

# Esperado: 
# {"status":"ok","service":"Logos Auditoria","version":"1.0"}
```

Se retornar erro:
```bash
# Ver logs
docker-compose logs -f api
# Ctrl+C para parar
```

---

## 🟢 PASSO 6: Acessar sistema

### Opção A: Dashboard
```
Abrir navegador: http://localhost:8000
```

### Opção B: Swagger UI (API)
```
Abrir navegador: http://localhost:8000/docs
```

### Opção C: Monitoramento
```
Grafana: http://localhost:3000
User: admin
Senha: admin

Prometheus: http://localhost:9090
```

---

## 🟢 PASSO 7: Rodar testes

```bash
# Com virtual environment ativo
pytest test_auditoria.py -v

# Esperado: 20+ testes passando (PASSED)
```

Se falhar algum:
```bash
# Ver detalhes do erro
pytest test_auditoria.py::TestDespesaCaixa -v
```

---

## 🟢 PASSO 8: Configurar .env para webPosto

```bash
# Abrir arquivo .env
nano .env
# OU
code .env
# OU
vim .env

# Editar estas linhas:
WEBPOSTO_BASE_URL=http://seu-webposto-ou-localhost:3000/api
WEBPOSTO_BEARER_TOKEN=seu_token_jwt_aqui

# Salvar (Ctrl+O + Enter + Ctrl+X no nano)
```

---

## 📊 PASSO 9: Rodar servidor local

### Opção A: Com Docker
```bash
docker-compose up
# Vai mostrar logs em tempo real
# Ctrl+C para parar
```

### Opção B: Sem Docker (direto)
```bash
# Com venv ativo
python servicos_auditoria.py

# Esperado:
# INFO: Uvicorn running on http://0.0.0.0:8000
```

---

## 🔍 PASSO 10: Validar tudo

```bash
# Em outro terminal:

# 1. API respondendo?
curl http://localhost:8000/auditoria/health

# 2. Dashboard acessível?
open http://localhost:8000
# ou firefox http://localhost:8000

# 3. Banco de dados?
docker-compose exec mongo mongosh -u admin -p changeme --authenticationDatabase admin

# 4. Logs?
docker-compose logs -f api

# 5. Testes?
pytest test_auditoria.py -v
```

---

## 🎯 Comandos do dia-a-dia

```bash
# Ver status
make status
docker-compose ps

# Ver logs
make logs
docker-compose logs -f api

# Rodar testes
make test
pytest test_auditoria.py -v

# Parar tudo
docker-compose down

# Reiniciar
docker-compose restart api

# Acessar MongoDB
make shell-mongo

# Acessar Redis
make shell-redis

# Ver todos os comandos
make help
```

---

## ❌ Se algo der errado

### Erro 1: Port already in use
```bash
# Mudar porta em docker-compose.yml
# Linha: ports: - "8000:8000"
# Para: - "8001:8000"

docker-compose up -d
curl http://localhost:8001/auditoria/health
```

### Erro 2: Docker daemon not running
```bash
# macOS
open /Applications/Docker.app

# Linux
sudo systemctl start docker

# Windows (Docker Desktop)
# Abrir Docker Desktop
```

### Erro 3: Python não encontrado
```bash
# Verificar versão
python3 --version
# Esperado: Python 3.11+

# Se não tiver:
# Linux: sudo apt-get install python3.11
# macOS: brew install python@3.11
```

### Erro 4: Permissão negada
```bash
# Fazer executável
chmod +x setup_local.sh

# Ou rodar com bash
bash setup_local.sh
```

### Erro 5: venv não ativa
```bash
# Recriar venv
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ✅ Checklist completo

- [ ] **Passo 1:** Código clonado em `/home/seu-usuario/logos-auditoria`
- [ ] **Passo 2:** Script `setup_local.sh` executado com sucesso
- [ ] **Passo 3:** Virtual environment ativado (`venv` aparece no prompt)
- [ ] **Passo 4:** `docker-compose ps` mostra 6 containers "Up"
- [ ] **Passo 5:** `curl http://localhost:8000/auditoria/health` retorna status OK
- [ ] **Passo 6:** Dashboard acessível em `http://localhost:8000`
- [ ] **Passo 7:** Testes passam: `pytest test_auditoria.py -v`
- [ ] **Passo 8:** `.env` editado com suas credenciais webPosto
- [ ] **Passo 9:** Servidor rodando (`docker-compose up` ou `python servicos_auditoria.py`)
- [ ] **Passo 10:** Tudo validado (API, Dashboard, Banco, Logs)

---

## 🎉 PRONTO!

Sistema rodando localmente.

### Próximos passos:

1. **Desenvolver:**
   ```bash
   source venv/bin/activate
   # Editar código
   # Servidor recarrega automaticamente
   ```

2. **Testes:**
   ```bash
   pytest test_auditoria.py -v
   ```

3. **Quando pronto para produção:**
   - Ler `GO_LIVE.md`
   - Rodar `python3 deploy_automation.py`

---

## 📞 DÚVIDAS?

Se der erro em qualquer passo:

1. **Ler o erro mensagem completa** (copiar e colar)
2. **Procurar no `TROUBLESHOOTING` acima**
3. **Ver logs:**
   ```bash
   docker-compose logs api
   docker-compose logs mongo
   ```

---

**Você está aqui → [Setup Local] → Desenvolvimento → Produção**

Bora desenvolver! 🚀
