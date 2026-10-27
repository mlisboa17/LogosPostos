# GO LIVE - Logos Auditoria

**Logos Mode: ON. Instruções exatas para COLOCAR EM PRODUÇÃO.**

---

## ⏱️ Timeline: 30 minutos

---

## 🔴 T-30MIN: Preparação

### 1. Preparar servidor
```bash
# SSH no servidor de produção
ssh ubuntu@seu-servidor-prod.com

# Criar diretório
mkdir -p /opt/logos-auditoria
cd /opt/logos-auditoria

# Clone repo (ou copie arquivos)
git clone https://seu-repo.com/logos-auditoria.git .
```

### 2. Copiar .env.production
```bash
# Trazer configurações de um Vault/Secrets Manager
# OPÇÃO 1: AWS Secrets Manager
aws secretsmanager get-secret-value --secret-id logos/production \
  --query SecretString --output text > .env.production

# OPÇÃO 2: HashiCorp Vault
vault kv get -format=json secret/logos/production | \
  jq -r '.data.data | to_entries | map("\(.key)=\(.value)") | .[]' > .env.production

# OPÇÃO 3: Manual (não recomendado)
cp .env.production.example .env.production
# Editar com credenciais reais
nano .env.production
```

### 3. Validar .env.production
```bash
# Verificar que as variáveis obrigatórias estão preenchidas
grep "WEBPOSTO_BASE_URL" .env.production | grep -v "seu_"
grep "WEBPOSTO_BEARER_TOKEN" .env.production | grep -v "seu_"
grep "MONGO_ROOT_PASSWORD" .env.production | grep -v "changeme"

# Se tudo OK:
echo "✓ Environment válido"
```

### 4. Certificado SSL
```bash
# OPÇÃO 1: Let's Encrypt (RECOMENDADO)
sudo certbot certonly --standalone \
  -d auditoria.production.com \
  -d api.production.com

# Copiar para o projeto
mkdir -p ssl
sudo cp /etc/letsencrypt/live/auditoria.production.com/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/auditoria.production.com/privkey.pem ssl/key.pem
sudo chown $USER:$USER ssl/*

# OPÇÃO 2: Self-signed (DEV ONLY)
openssl req -x509 -newkey rsa:4096 \
  -keyout ssl/key.pem -out ssl/cert.pem \
  -days 365 -nodes
```

---

## 🟡 T-15MIN: Backup

### Backup databases atuais (se migração)
```bash
# Se tem banco de dados existente, fazer backup agora
docker-compose exec mongo mongodump \
  -u admin -p $MONGO_ROOT_PASSWORD \
  --authenticationDatabase admin \
  --out backups/pre-deployment-$(date +%Y%m%d-%H%M%S)

docker exec logos-cache redis-cli BGSAVE
docker cp logos-cache:/data/dump.rdb backups/redis-backup.rdb
```

### Log de deployment
```bash
# Criar arquivo para documentar o deploy
cat > deployment.log << EOF
Deployment: $(date)
Version: v1.0.0
Environment: production
Prepared by: $(whoami)
EOF
```

---

## 🟢 T-0MIN: DEPLOY

### 1. Rodar script de automação
```bash
# Fazer deploy com script automático
python3 deploy_automation.py \
  --environment production \
  --version v1.0.0 \
  --registry seu-registry.com

# OU fazer step-by-step:
```

### 2. Build + Push (se step-by-step)
```bash
# Build
docker build -t seu-registry.com/logos-auditoria:v1.0.0 .

# Validar
docker run --rm seu-registry.com/logos-auditoria:v1.0.0 \
  python -m pytest test_auditoria.py

# Push
docker push seu-registry.com/logos-auditoria:v1.0.0
```

### 3. Iniciar stack Docker
```bash
# Load environment
export $(cat .env.production | xargs)

# Pull images
docker-compose pull

# Start
docker-compose up -d

# Aguardar inicialização
sleep 10
```

### 4. Validar deployment
```bash
# Health check
curl -k https://localhost/api/auditoria/health
# Esperado: {"status": "ok", "service": "Logos Auditoria", "version": "1.0"}

# Testar API
curl -k https://localhost/api/auditoria/resumo/real_01

# Testar Dashboard
curl -k https://localhost/ | head -c 100

# Verificar logs
docker-compose logs --tail=50 api
docker-compose logs --tail=50 nginx
docker-compose logs --tail=50 mongo
```

---

## ⏸️ T+5MIN: Monitoramento

### Checklist pós-deployment
```bash
# 1. Verificar containers rodando
docker-compose ps
# Esperado: api, mongo, redis, nginx, prometheus, grafana all "Up"

# 2. Verificar status de saúde
watch -n 1 'docker-compose ps'

# 3. Monitorar logs em tempo real
docker-compose logs -f api &
docker-compose logs -f nginx &

# 4. Acessar dashboards
# - Aplicação: https://auditoria.production.com
# - Grafana: http://seu-servidor:3000 (admin/admin)
# - Prometheus: http://seu-servidor:9090

# 5. Verificar métricas
curl http://seu-servidor:9090/api/v1/query?query=up
```

### Testes funcionais (primeiros 5 min)
```bash
# 1. Login/Dashboard
curl -k https://auditoria.production.com/ -L | grep -q "Logos Auditoria" && echo "✓ Dashboard OK"

# 2. API
for endpoint in "health" "resumo/real_01" "despesas/real_01" "fechamentos/real_01"; do
  curl -s -k https://auditoria.production.com/api/auditoria/$endpoint > /dev/null && \
  echo "✓ $endpoint OK" || echo "✗ $endpoint FAILED"
done

# 3. Database
docker-compose exec mongo mongosh -u admin -p $MONGO_ROOT_PASSWORD \
  --authenticationDatabase admin \
  --eval "db.adminCommand('ping')" && echo "✓ MongoDB OK"

# 4. Cache
docker exec logos-cache redis-cli ping && echo "✓ Redis OK"
```

---

## 🚨 T+30MIN: Se algo der errado

### Rollback imediato
```bash
# Se erros críticos aparecem, rollback:
python3 deploy_automation.py --rollback

# OU manual:
docker-compose down
# Restaurar imagem anterior
docker-compose pull  # Isso puxa a versão anterior do registry
docker-compose up -d
```

### Checklist rollback
```bash
# 1. Parar deployment
docker-compose stop api

# 2. Restaurar banco de dados (se necessário)
docker-compose exec mongo mongorestore \
  -u admin -p $MONGO_ROOT_PASSWORD \
  --authenticationDatabase admin \
  /backup/pre-deployment-XXXXX

# 3. Reiniciar com versão anterior
docker-compose up -d
```

---

## 📊 Pós-Deployment (próximas horas)

### Monitoring Contínuo
```bash
# Acompanhar por 24h:
# 1. Error rate deve ser < 0.1%
# 2. Response time p95 < 500ms
# 3. CPU < 60%
# 4. Memory < 70%
# 5. Disk free > 20%

# Ver métricas Prometheus
curl http://seu-servidor:9090/api/v1/query?query='rate(http_requests_total[5m])'
```

### Alertas
```bash
# Verificar se alertas foram disparados (não deveriam)
# - Slack: verificar #logos-alerts
# - PagerDuty: não deve ter nenhum incident
# - Grafana: alertas devem estar verdes

# Se algo der alerta, investigar:
docker-compose logs api | grep ERROR
```

### Acessos críticos
```bash
# Notificar que o sistema está live
# 1. Comunicar ao time via Slack
# 2. Atualizar status page
# 3. Enviar email para stakeholders
# 4. Documentar no wiki/confluence
```

---

## 📝 Documentação Live

### Criar runbook operacional
```bash
# Documentar:
# - Como parar/iniciar API
# - Como fazer backup
# - Como restaurar banco
# - Contatos de escalation
# - Passo-a-passo para troubleshooting

cat > RUNBOOK_LIVE.md << 'EOF'
# Logos Auditoria - Runbook Operacional

## Status Atual
- Deployment: 2026-04-12 14:35 UTC
- Version: v1.0.0
- Environment: production
- Status: LIVE

## Parar Sistema
docker-compose down

## Iniciar Sistema
docker-compose up -d

## Acessar Database
docker-compose exec mongo mongosh

## Ver Logs
docker-compose logs -f api

## Contato Escalation
- On-call: +55 11 XXXX-XXXX
- Slack: @logos-oncall
EOF
```

---

## ✅ Checklist Final

- [ ] .env.production preenchido com valores reais
- [ ] Certificado SSL válido
- [ ] Backup pré-deployment realizado
- [ ] Docker images buildados e testados
- [ ] deploy_automation.py execução bem-sucedida
- [ ] Health check retorna 200 OK
- [ ] Dashboard acessível (HTTPS)
- [ ] API endpoints respondendo
- [ ] Monitoramento ativo (Prometheus/Grafana)
- [ ] Alertas configurados (Slack/PagerDuty)
- [ ] Logs sendo coletados
- [ ] Team notificado
- [ ] Documentação atualizada

---

## 🎉 LIVE!

Se todos os passos foram executados:

```
╔════════════════════════════════════════════╗
║  🚀 LOGOS AUDITORIA EM PRODUÇÃO!          ║
║  https://auditoria.production.com          ║
║  Status: OPERACIONAL                       ║
╚════════════════════════════════════════════╝
```

---

**Version:** 1.0  
**Last updated:** 2026-04-12
