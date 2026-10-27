# Quick Start Guide - WebPosto Integration (PASSO 7-8)

## What Changed?

### Before (PASSO 1-6)
- Single audit-only dashboard
- Manual API service configuration
- No consolidated view

### Now (PASSO 7-8)
- **Three-module unified dashboard** (Auditoria, Abastecimento, Vendas)
- **Simplified Docker deployment** (single docker-compose up -d)
- **Production-ready infrastructure** (health checks, monitoring, logging)

---

## Files You Need to Know About

| File | Purpose | Status |
|------|---------|--------|
| **index.html** | The consolidated dashboard | ✅ Ready |
| **docker-compose.yml** | All services configuration | ✅ Ready |
| **Dockerfile.webposto** | API image build | ✅ Ready |
| **.env** | Configuration (create from example) | ⏳ Create |

---

## 30-Second Setup

```bash
# 1. Go to the project directory
cd /mnt/Api_WebPosto

# 2. Create environment file
cat > .env << 'EOF'
MONGO_ROOT_USER=admin
MONGO_ROOT_PASSWORD=changeme
GRAFANA_PASSWORD=admin
WEBPOSTO_BASE_URL=http://your-api.local
WEBPOSTO_BEARER_TOKEN=your-token
ENVIRONMENT=production
DEBUG=false
EOF

# 3. Start everything
docker-compose up -d

# 4. Wait 10 seconds for services to initialize

# 5. Open in browser
# http://localhost
```

That's it! The dashboard should be running.

---

## What's Running?

```
Service          Port    Purpose
────────────────────────────────────────────
WebPosto API     8000    Backend service
Nginx            80/443  Dashboard & reverse proxy
MongoDB          27017   Data persistence
Redis            6379    Caching layer
Prometheus       9090    Metrics collection
Grafana          3000    Monitoring dashboards
```

---

## Access Dashboard

**Main Dashboard (Consolidated)**
```
http://localhost/index.html
or
http://localhost/ (if Nginx is configured)
```

**Three Tabs Available**
1. **Auditoria** (Audit & Financial)
   - Revenue, expenses, cash flow
   - Anomaly detection
   
2. **Abastecimento** (Fuel Operations)
   - Daily fuel sales
   - Volume and pricing analysis
   
3. **Vendas** (Sales & Revenue)
   - Transaction tracking
   - Category breakdown

**Monitoring (Optional)**
```
Prometheus: http://localhost:9090
Grafana:    http://localhost:3000 (admin/admin)
```

---

## Common Tasks

### Check Service Status
```bash
docker-compose ps
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f mongo
```

### Test API
```bash
# Check health
curl http://localhost:8000/auditoria/health

# Test data endpoint
curl http://localhost:8000/auditoria/resumo/real_01
```

### Restart Services
```bash
# Restart API only
docker-compose restart api

# Restart all
docker-compose restart
```

### Stop Everything
```bash
docker-compose down

# Also remove volumes (WARNING: deletes data)
docker-compose down -v
```

---

## Data API Endpoints

### Auditoria (Legacy, Fully Supported)
```
GET /auditoria/resumo/{unidade}           # Summary for unit
GET /auditoria/despesas/{unidade}         # Expense details
GET /auditoria/fechamentos/{unidade}      # Cash reconciliation
GET /auditoria/health                     # Health check
```

Units: `real_01`, `casa_caiada_01`, `vip_01`

### Abastecimento (New)
```
GET /abastecimento/data/{date}            # Daily transactions
GET /abastecimento/resumo/{date}          # Daily summary
```

Date format: `YYYY-MM-DD`

### Vendas (New)
```
GET /vendas/data/{date}                   # Daily transactions
GET /vendas/resumo/{date}                 # Daily summary
```

Date format: `YYYY-MM-DD`

---

## Example API Calls

```bash
# Get audit summary for Real unit
curl -X GET "http://localhost:8000/auditoria/resumo/real_01" \
  -H "Content-Type: application/json"

# Get fuel sales for today
curl -X GET "http://localhost:8000/abastecimento/resumo/2026-04-13" \
  -H "Content-Type: application/json"

# Get sales data for yesterday
curl -X GET "http://localhost:8000/vendas/data/2026-04-12" \
  -H "Content-Type: application/json"
```

---

## Troubleshooting

### Dashboard Shows Errors/Empty Data?

**Step 1: Check API is running**
```bash
docker-compose ps api
# Should show "Up"

curl -v http://localhost:8000/auditoria/health
# Should return 200 OK
```

**Step 2: Check endpoint exists**
```bash
# Try a specific endpoint
curl -s http://localhost:8000/auditoria/resumo/real_01 | jq .
```

**Step 3: Check logs**
```bash
docker-compose logs api | tail -50
```

### Services Won't Start?

```bash
# Check logs
docker-compose logs

# Verify ports are free
netstat -tlnp | grep -E "8000|27017|6379"

# Try building again
docker-compose build --no-cache api
docker-compose up -d
```

### MongoDB Connection Error?

```bash
# Check MongoDB
docker-compose logs mongo

# Test connection
docker-compose exec mongo mongosh admin --eval "db.adminCommand('ping')"

# Check credentials in .env
grep MONGO docker-compose.yml
```

### Redis Connection Error?

```bash
# Check Redis
docker-compose logs redis

# Test Redis
docker-compose exec redis redis-cli ping
```

---

## Configuration

### Add New Units to Dashboard

Edit `index.html` line 44:
```javascript
const UNIDADES = ['real_01', 'casa_caiada_01', 'vip_01']; // Add here
```

### Change API URL

Edit `index.html` line 43:
```javascript
const API_BASE = 'http://localhost:8000'; // Change here
```

### Change Colors/Theme

Edit `index.html` CSS section or Tailwind classes in components.

### Add New Endpoints

Edit dashboard components in `index.html` (search for `DashboardAbastecimento` or `DashboardVendas`).

---

## Performance Tips

### For Better Dashboard Performance
1. Clear browser cache (Ctrl+Shift+Delete)
2. Ensure API responses are fast: `curl -w "@curl-format.txt" http://localhost:8000/auditoria/resumo/real_01`
3. Check database indexes: `docker-compose exec mongo mongosh`

### For Better API Performance
1. Enable Redis caching
2. Optimize database queries
3. Add indexes to frequently filtered fields

### For Production
1. Enable HTTPS in Nginx
2. Set up SSL certificates
3. Enable compression
4. Configure rate limiting
5. Set up monitoring alerts

---

## Common API Response Examples

### Auditoria - Resumo
```json
{
  "unidade_id": "real_01",
  "faturamento_total": 15000.00,
  "despesas_operacionais": 2500.00,
  "saldo_especie_total": 12500.00,
  "quebra_total": 10.00,
  "quebra_percentual": 0.067,
  "desvio_percentual_media_despesas": 2.5,
  "outlier_unidade": false,
  "caixas_fechados": 3,
  "despesas_sem_documento_total": 0
}
```

### Abastecimento - Resumo
```json
{
  "data": "2026-04-13",
  "total_abastecido": 5000,
  "valor_total": 25000.00,
  "qtd_abastecimentos": 150,
  "ticket_medio": 166.67
}
```

### Vendas - Resumo
```json
{
  "data": "2026-04-13",
  "total_vendido": 50000.00,
  "qtd_vendas": 500,
  "ticket_medio": 100.00,
  "variacao_percentual": 12.5
}
```

---

## Security Notes

⚠️ **Before Production:**
1. Change default passwords (Grafana: admin/admin)
2. Use strong MongoDB password (not "changeme")
3. Store API tokens securely (use .env, never commit)
4. Enable HTTPS/TLS for Nginx
5. Restrict network access
6. Set up backup strategy
7. Enable audit logging
8. Regular security updates

✅ **Already Implemented:**
- Non-root Docker user
- Health checks with timeouts
- Environment-based configuration
- Separation of concerns (per service)

---

## Getting Help

### Check Documentation
1. Read `PASSO_7_8_FINAL_SUMMARY.md` (comprehensive)
2. Read `INTEGRATION_STEPS_7_8_COMPLETE.md` (technical details)
3. Check service logs: `docker-compose logs -f [service-name]`

### Verify Setup
```bash
bash VERIFY_INTEGRATION.sh
```

### Test Manually
```bash
# 1. Check all services running
docker-compose ps

# 2. Test API
curl http://localhost:8000/auditoria/health

# 3. Test dashboard
curl -I http://localhost/index.html

# 4. Test MongoDB
docker-compose exec mongo mongosh admin --eval "db.adminCommand('ping')"

# 5. View logs
docker-compose logs --tail=100
```

---

## Quick Reference

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Logs
docker-compose logs -f api

# Restart
docker-compose restart

# Rebuild
docker-compose build --no-cache

# Reset everything
docker-compose down -v && docker-compose up -d

# Check status
docker-compose ps

# Execute command in service
docker-compose exec api python -c "print('test')"
```

---

## What's Next?

After initial setup:

1. **Configure SSL/TLS** (for production)
   ```bash
   mkdir -p ssl
   # Add your certificates to ssl/
   ```

2. **Set up monitoring** (Prometheus/Grafana)
   - Access Grafana at http://localhost:3000
   - Import dashboards
   - Configure alerts

3. **Enable backups**
   - Schedule MongoDB backups
   - Test restore procedures

4. **Monitor performance**
   - Check API response times
   - Monitor database size
   - Review cache hit rates

5. **Scale if needed**
   - Add more API instances
   - Load balance with Nginx
   - Configure replication

---

**You're all set! Dashboard is ready at http://localhost**

For detailed information, see `PASSO_7_8_FINAL_SUMMARY.md`

Last updated: April 13, 2026
Status: ✅ PRODUCTION READY
