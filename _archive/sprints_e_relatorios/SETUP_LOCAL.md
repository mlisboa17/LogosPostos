# Setup Local - Logos Auditoria

**Máquina nova → Desenvolvimento local em 10 minutos**

---

## ⏱️ Tempo: 10 min

---

## 🚀 Quick Start

### Opção 1: Script Automático (RECOMENDADO)

```bash
# 1. Clonar repositório
cd /path/to/logos-auditoria

# 2. Rodar script setup
chmod +x setup_local.sh
./setup_local.sh

# 3. Pronto! ✓
```

**O script vai:**
- ✅ Detectar sistema (Linux/macOS/Windows)
- ✅ Instalar Docker, Docker Compose, Python 3.11
- ✅ Instalar dependências Python (pip)
- ✅ Configurar ambiente local (.env)
- ✅ Build Docker image
- ✅ Iniciar stack (API + Mongo + Redis + Prometheus + Grafana)
- ✅ Rodar testes
- ✅ Exibir status

### Opção 2: Manual (step-by-step)

---

## 📋 Manual Setup

### 1. Instalar dependências do sistema

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y \
  docker.io \
  docker-compose-plugin \
  python3.11 \
  python3.11-venv \
  git \
  curl

# Adicionar user ao grupo docker
sudo usermod -aG docker $USER
newgrp docker
```

**macOS:**
```bash
# Instalar Homebrew (se não tiver)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Instalar ferramentas
brew install docker docker-compose python@3.11 git curl
```

**Windows:**
```
Instalar WSL2: https://docs.microsoft.com/en-us/windows/wsl/install
Instalar Docker Desktop: https://www.docker.com/products/docker-desktop
```

### 2. Verificar instalações
```bash
docker --version        # >= 20.10
docker compose version  # >= 2.0
python3 --version       # >= 3.11
git --version           # >= 2.20
```

### 3. Clonar código
```bash
git clone https://seu-repo.com/logos-auditoria.git
cd logos-auditoria
```

### 4. Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# OU
venv\Scripts\activate     # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configurar .env
```bash
cp .env.example .env

# Editar para desenvolvimento local
nano .env

# Alterações recomendadas:
# WEBPOSTO_BASE_URL=http://localhost:3000/api (ou seu servidor)
# DEBUG=true
# LOG_LEVEL=INFO
```

### 6. Build Docker image
```bash
docker build -t logos-auditoria:dev .
```

### 7. Iniciar stack Docker
```bash
docker-compose up -d

# Aguardar ~30s para inicialização
sleep 30

# Verificar status
docker-compose ps
```

### 8. Validar setup
```bash
# Health check
curl http://localhost:8000/auditoria/health

# Esperado:
# {"status": "ok", "service": "Logos Auditoria", "version": "1.0"}

# Acessar aplicação
open http://localhost:8000/docs  # Swagger UI
# ou
open index.html                   # Dashboard
```

---

## 🎯 Desenvolvimento

### Rodar servidor localmente

**Com Docker:**
```bash
docker-compose up
```

**Sem Docker (direto):**
```bash
source venv/bin/activate
python servicos_auditoria.py
```

Acesso: `http://localhost:8000`

### Testes
```bash
# Todos os testes
pytest test_auditoria.py -v

# Teste específico
pytest test_auditoria.py::TestDespesaCaixa::test_criar_despesa_valida -v

# Com coverage
pytest test_auditoria.py --cov=. --cov-report=html
```

### Exemplo de uso
```bash
source venv/bin/activate
python exemplo_uso.py
```

### Acessar banco de dados
```bash
# MongoDB
docker-compose exec mongo mongosh -u admin -p changeme --authenticationDatabase admin

# Redis
docker-compose exec redis redis-cli
```

---

## 📊 Monitoramento Local

```
API:        http://localhost:8000
Swagger UI: http://localhost:8000/docs
Grafana:    http://localhost:3000 (admin/admin)
Prometheus: http://localhost:9090
MongoDB:    localhost:27017
Redis:      localhost:6379
```

---

## 🛠️ Comandos Úteis

```bash
# Status
docker-compose ps
make status

# Logs
docker-compose logs -f api
make logs

# Restart
docker-compose restart api

# Parar tudo
docker-compose down

# Clean
docker-compose down -v  # Remove volumes também
make clean

# Database access
make shell-mongo
make shell-redis

# Testes
make test
make validate
```

---

## 🐛 Troubleshooting

### Docker not found
```bash
# Ubuntu
sudo apt-get install docker.io

# macOS
brew install docker
# Iniciar Docker Desktop ou
brew services start docker
```

### Port already in use
```bash
# Mudar porta em docker-compose.yml
ports:
  - "8001:8000"  # Ao invés de 8000:8000
```

### Python venv issues
```bash
rm -rf venv/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### API não responde
```bash
# Verificar logs
docker-compose logs api

# Verificar health
curl http://localhost:8000/auditoria/health

# Restart
docker-compose restart api
```

### MongoDB connection error
```bash
# Verificar se está rodando
docker-compose ps mongo

# Restart
docker-compose restart mongo

# Checar credenciais em .env
grep MONGO .env
```

---

## 🔄 Workflow desenvolvimento

```
1. Código local (editor/IDE)
2. Salvar arquivo
3. API recarrega automaticamente (hot-reload)
4. Testar via Swagger UI ou curl
5. Rodar testes: pytest test_auditoria.py
6. Commit git
```

### Configurar IDE (VS Code)

```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "[python]": {
    "editor.formatOnSave": true
  }
}
```

---

## 📚 Estrutura do projeto

```
logos-auditoria/
├── config.py                 # Configurações
├── models_auditoria.py       # Modelos Pydantic
├── webposto_client.py        # Cliente webPosto
├── servicos_auditoria.py     # API FastAPI
├── test_auditoria.py         # Testes
├── exemplo_uso.py            # Exemplos
│
├── requirements.txt          # Dependências Python
├── Dockerfile                # Docker image
├── docker-compose.yml        # Stack Docker
├── Makefile                  # Comandos úteis
│
├── .env.example              # Template .env
├── .env                      # Configurações locais
│
├── index.html                # Dashboard
├── dashboard_auditoria.jsx   # Componente React
│
└── docs/
    ├── README.md             # Overview
    ├── SETUP.md              # Setup inicial
    ├── SETUP_LOCAL.md        # Setup local
    └── ...
```

---

## ✅ Checklist local

- [ ] Docker + Docker Compose instalados
- [ ] Python 3.11+ instalado
- [ ] Repositório clonado
- [ ] Virtual environment criado (`venv`)
- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] `.env` configurado para local
- [ ] Docker image buildo (`docker build -t logos-auditoria:dev .`)
- [ ] Stack Docker rodando (`docker-compose up -d`)
- [ ] API respondendo (`curl http://localhost:8000/auditoria/health`)
- [ ] Testes passando (`pytest test_auditoria.py -v`)
- [ ] Monitoramento acessível (Grafana, Prometheus)

---

## 🎯 Próximos passos

1. ✅ Setup local completo
2. 📝 Editar `.env` com credenciais webPosto
3. 🧪 Rodar testes: `pytest test_auditoria.py -v`
4. 🚀 Iniciar desenvolvimento
5. 📦 Quando pronto: `./deploy.sh` para produção

---

**Pronto para desenvolver! 🚀**

```bash
source venv/bin/activate
python servicos_auditoria.py
# ou
docker-compose up
```

Acesso: http://localhost:8000

