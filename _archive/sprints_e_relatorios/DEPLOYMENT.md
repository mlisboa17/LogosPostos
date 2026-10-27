# Deployment Guide - Logos Auditoria

**Logos Mode: ON. Instruções precisas para IR PARA PRODUÇÃO.**

---

## 🚀 Quick Deploy (5 minutos)

### 1. Clonar/Copiar código
```bash
cd /opt/logos-auditoria
git clone [repo] .  # ou copiar arquivos
```

### 2. Preparar environment
```bash
cp .env.example .env.production

# Editar com valores reais
nano .env.production

# Variáveis obrigatórias:
export WEBPOSTO_BASE_URL=https://webposto.production.com/api
export WEBPOSTO_BEARER_TOKEN=seu_jwt_token_aqui
export MONGO_ROOT_PASSWORD=$(openssl rand -base64 32)
```

### 3. Build Docker image
```bash
docker build -t logos-auditoria:v1.0.0 .

# Validar
docker run --rm logos-auditoria:v1.0.0 python -m pytest test_auditoria.py
```

### 4. Push para registry
```bash
docker tag logos-auditoria:v1.0.0 registry.com/logos-auditoria:v1.0.0
docker push registry.com/logos-auditoria:v1.0.0
```

### 5. Certificado SSL
```bash
# Gerar auto-signed (DEV) ou usar Let's Encrypt
mkdir -p ssl

# Let's Encrypt
certbot certonly --standalone -d auditoria.production.com
cp /etc/letsencrypt/live/auditoria.production.com/fullchain.pem ssl/cert.pem
cp /etc/letsencrypt/live/auditoria.production.com/privkey.pem ssl/key.pem
```

### 6. Deploy
```bash
# Usar .env.production
export $(cat .env.production | xargs)

# Rodar stack Docker
docker-compose -f docker-compose.yml up -d

# Validar
docker-compose logs -f api
curl https://localhost/api/auditoria/health
```

---

## 📋 Pré-requisitos

### Hardware (mínimo)
- CPU: 2 cores
- RAM: 4GB
- Disk: 50GB SSD
- Network: 100Mbps

### Software
- Docker 20.10+
- Docker Compose 2.0+
- Nginx 1.18+
- MongoDB 5.0+ (ou gerenciado)
- Redis 6.0+ (opcional)

### Acesso
- SSH com chave (não senha)
- Sudo sem password
- Port 443 aberto (HTTPS)

---

## 🔐 Security Setup

### 1. Firewall
```bash
# UFW (Ubuntu)
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw enable
```

### 2. Users
```bash
# Criar user não-root
useradd -m -s /bin/bash logos
usermod -aG docker logos
usermod -aG sudo logos

# SSH key
mkdir -p /home/logos/.ssh
echo "your-public-key" > /home/logos/.ssh/authorized_keys
chmod 600 /home/logos/.ssh/authorized_keys
chown -R logos:logos /home/logos/.ssh
```

### 3. SSL/TLS
```bash
# Validar certificado
openssl x509 -in ssl/cert.pem -text -noout

# Renew (adicionar cron)
0 3 * * * certbot renew --quiet
```

### 4. Secrets Management
```bash
# Usar AWS Secrets Manager
aws secretsmanager create-secret \
  --name logos/production \
  --secret-string file://secrets.json

# Ou Vault
vault kv put secret/logos/production \
  webposto_bearer_token=xyz \
  mongo_password=abc
```

---

## 📊 Monitoramento Setup

### Prometheus
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'logos-api'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/metrics'
```

### Grafana
```bash
# Acessar http://localhost:3000
# User: admin / Password: ${GRAFANA_PASSWORD}
# Adicionar Prometheus como data source
# Importar dashboard: 1860 (Node Exporter)
```

### Alertas (AlertManager)
```yaml
# alertmanager.yml
route:
  receiver: 'team-slack'

receivers:
  - name: 'team-slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK'
        channel: '#alerts'
```

---

## 🔄 Logging Centralizado

### ELK Stack (opcional)
```bash
# Elasticsearch
docker run -d -p 9200:9200 \
  -e "discovery.type=single-node" \
  docker.elastic.co/elasticsearch/elasticsearch:8.0.0

# Logstash
# Kibana
docker run -d -p 5601:5601 \
  docker.elastic.co/kibana/kibana:8.0.0
```

### Stdout → CloudWatch (AWS)
```bash
# Adicionar ao docker-compose.yml
logging:
  driver: awslogs
  options:
    awslogs-group: /logos/auditoria
    awslogs-region: us-east-1
    awslogs-stream-prefix: api
```

---

## 🔄 CI/CD Pipeline

### GitHub Actions
```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]
    paths:
      - 'servicos_auditoria.py'
      - 'models_auditoria.py'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Test
        run: pytest test_auditoria.py -v

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build
        run: docker build -t logos-auditoria:${{ github.sha }} .
      - name: Push
        run: |
          docker tag logos-auditoria:${{ github.sha }} registry.com/logos-auditoria:latest
          docker push registry.com/logos-auditoria:latest

  deploy:
    needs: build
    runs-on: self-hosted
    steps:
      - name: Deploy
        run: |
          cd /opt/logos-auditoria
          docker-compose pull
          docker-compose up -d --no-deps api
```

---

## 🆘 Troubleshooting

| Problema | Solução |
|----------|---------|
| `connection refused` | Verificar firewall, ports abertos |
| `CORS error` | Adicionar `ALLOWED_ORIGINS` em config |
| `webPosto offline` | Health check webPosto, token válido |
| `MongoDB connection` | Verificar `LOGOS_SPACE_DB`, credentials |
| `SSL certificate error` | Validar certificado com `openssl x509` |
| `High memory usage` | Aumentar limite Docker, otimizar queries |

---

## ✅ Post-Deployment Checks

```bash
# 1. Health
curl -k https://auditoria.production.com/health

# 2. Logs
docker-compose logs --tail=50 api

# 3. Performance
docker stats

# 4. Database
docker exec logos-space-db mongosh -u admin -p $MONGO_ROOT_PASSWORD \
  --authenticationDatabase admin \
  --eval "db.adminCommand('ping')"

# 5. Endpoints
curl -k https://auditoria.production.com/api/auditoria/resumo/real_01
```

---

## 📈 Scaling

### Horizontal (múltiplas instâncias)
```yaml
# docker-compose.yml
api:
  deploy:
    replicas: 3
  depends_on:
    - mongo
    - redis
```

### Load Balancer (Nginx)
```nginx
upstream api {
  least_conn;
  server api-1:8000 weight=1;
  server api-2:8000 weight=1;
  server api-3:8000 weight=1;
}
```

### Database
```bash
# MongoDB Replication
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo-1:27017" },
    { _id: 1, host: "mongo-2:27017" },
    { _id: 2, host: "mongo-3:27017" }
  ]
})
```

---

## 🔄 Backup & Restore

### MongoDB Backup
```bash
# Backup
docker exec logos-space-db mongodump \
  -u admin -p $MONGO_ROOT_PASSWORD \
  --authenticationDatabase admin \
  --out /backup/mongo-$(date +%Y%m%d)

# Restore
docker exec logos-space-db mongorestore \
  -u admin -p $MONGO_ROOT_PASSWORD \
  --authenticationDatabase admin \
  /backup/mongo-20260412
```

### Redis Backup
```bash
# Snapshot
docker exec logos-cache redis-cli BGSAVE

# Copy
docker cp logos-cache:/data/dump.rdb ./backups/
```

---

## 🚨 Incident Response

### API down
```bash
# 1. Check status
docker-compose ps

# 2. Check logs
docker-compose logs --tail=100 api

# 3. Restart
docker-compose restart api

# 4. Rollback (if needed)
docker-compose pull
docker image ls logos-auditoria
docker-compose up -d --no-deps --force-recreate api
```

### Database corruption
```bash
# 1. Stop API
docker-compose stop api

# 2. Restore from backup
docker exec logos-space-db mongorestore \
  -u admin -p $MONGO_ROOT_PASSWORD \
  --authenticationDatabase admin \
  /backup/mongo-latest

# 3. Restart
docker-compose up -d api
```

---

## 📝 Documentação

Manter atualizado:
- [ ] Architecture diagram
- [ ] Deployment checklist
- [ ] Runbook
- [ ] Disaster recovery plan
- [ ] Contact list (escalation)

---

**Version:** 1.0  
**Status:** Production-ready  
**Last updated:** 2026-04-12
