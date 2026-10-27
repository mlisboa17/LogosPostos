# Production Checklist - Logos Auditoria

**Logos Mode: ON. Rigor absoluto antes de ir para produção.**

---

## ✅ PRÉ-DEPLOYMENT

### Configurações
- [ ] `.env.production` criado com todas as variáveis
- [ ] `WEBPOSTO_BASE_URL` aponta para produção
- [ ] `WEBPOSTO_BEARER_TOKEN` é token de produção (não dev)
- [ ] Credenciais Logos Eye/Space/Vorcaro válidas
- [ ] `DEBUG=false`
- [ ] `LOG_LEVEL=WARNING` (não INFO)
- [ ] Senhas/tokens NÃO estão em código

### Dependências
- [ ] `pip freeze > requirements.txt` atualizado
- [ ] Sem dependências de desenvolvimento (pytest, etc em produção?)
- [ ] Versões fixadas (não `latest`)

### Código
- [ ] Sem `print()` statements (usar logging)
- [ ] Sem `TODO` ou `FIXME` críticos
- [ ] Sem hardcoded URLs/IPs
- [ ] Tratamento de erro em todos endpoints
- [ ] Rate limiting implementado
- [ ] CORS configurado corretamente
- [ ] Validação de entrada (Pydantic) em todos endpoints

### Testes
- [ ] `pytest test_auditoria.py -v` passa 100%
- [ ] Load test com 100 requisições simultâneas
- [ ] Health check endpoint respondendo
- [ ] Timeout/retry funcionando corretamente
- [ ] Fallback para MOCK validado

### Segurança
- [ ] HTTPS habilitado (certificado SSL/TLS)
- [ ] Headers de segurança (CORS, CSP, X-Frame-Options)
- [ ] Rate limiting por IP
- [ ] Input validation (Pydantic)
- [ ] SQL injection protection (usando ORM)
- [ ] XSS protection (não renderizar user input)
- [ ] CSRF token implementado (se aplicável)

### Performance
- [ ] Database indexed (se usando MongoDB)
- [ ] Cache Redis configurado (opcional)
- [ ] CDN para assets estáticos
- [ ] Compression (gzip) habilitada
- [ ] Lazy loading implementado
- [ ] N+1 queries resolvidas

### Monitoramento
- [ ] Logging centralizado (stdout → ELK/Splunk/DataDog)
- [ ] APM (Application Performance Monitoring) setup
- [ ] Alertas configurados:
  - [ ] Erro rate > 5%
  - [ ] Response time > 1s
  - [ ] API webPosto offline
  - [ ] Disk space < 10%
  - [ ] Memory usage > 80%
- [ ] Dashboards criados (Grafana/Kibana)

### Backup & Disaster Recovery
- [ ] Backup automático de banco de dados (daily)
- [ ] Replicação geográfica (se crítico)
- [ ] Teste de restore (weekly)
- [ ] RTO/RPO documentado
- [ ] Runbook de disaster recovery criado

### Documentação
- [ ] README.md atualizado
- [ ] API docs (Swagger/OpenAPI) acessível
- [ ] Deployment guide escrito
- [ ] Runbook operacional criado
- [ ] Contatos de escalation documentados

---

## ✅ DEPLOYMENT

### Infraestrutura
- [ ] Servidor pronto (VM, K8s, managed service)
- [ ] Firewall configurado (porta 443 apenas)
- [ ] DNS apontando para production
- [ ] SSL/TLS certificado válido
- [ ] Load balancer (se multi-instance)

### Docker
- [ ] Dockerfile válido
- [ ] Docker image builado
- [ ] Image testado localmente
- [ ] Image com tag de versão (v1.0.0)
- [ ] Registry (Docker Hub/ECR) acesso configurado

### Database
- [ ] MongoDB pronto (if using Logos Space)
- [ ] Backup antes de deploy
- [ ] Migrations executadas
- [ ] Índices criados
- [ ] Connection string em .env

### Deployment
- [ ] CI/CD pipeline automatizado
- [ ] Build passa (tests + linting)
- [ ] Aprovação de change control
- [ ] Deployment reversível (rollback plan)
- [ ] Staging environment testado antes
- [ ] Canary deploy (5% → 50% → 100%)

### Post-Deployment
- [ ] Smoke tests passando
- [ ] Health check OK
- [ ] Endpoints respondendo
- [ ] Dashboard acessível
- [ ] Logs sendo coletados
- [ ] Alertas funcionando
- [ ] Equipe notificada

---

## ✅ PÓS-DEPLOYMENT (24h)

### Monitoramento
- [ ] Nenhum erro crítico nos logs
- [ ] Performance dentro do esperado
- [ ] Taxa de erro < 0.1%
- [ ] Response time p95 < 500ms
- [ ] webPosto conectando corretamente

### Validação funcional
- [ ] GET /auditoria/health → 200 OK
- [ ] GET /auditoria/resumo/{unidade} → 200 OK
- [ ] GET /auditoria/despesas/{unidade} → 200 OK
- [ ] POST /auditoria/registrar-despesa → 200 OK
- [ ] Dashboard carregando (index.html)

### Segurança
- [ ] Nenhum warning de segurança (SSL Labs A+)
- [ ] Headers de segurança presentes
- [ ] Rate limiting funcionando
- [ ] Sem dados sensíveis em logs

---

## ⚠️ ROLLBACK PLAN

Se algo der errado:

```bash
# 1. Parar deploy
docker stop logos-auditoria

# 2. Reverter para versão anterior
docker pull registry.com/logos-auditoria:v1.0.0
docker run -d --name logos-auditoria \
  -p 8000:8000 \
  --env-file .env.production \
  registry.com/logos-auditoria:v1.0.0

# 3. Health check
curl http://localhost:8000/auditoria/health

# 4. Notificar equipe
# Enviar Slack/PagerDuty alert
```

---

## 📝 SLA Targets

| Métrica | Target | Threshold |
|---------|--------|-----------|
| Availability | 99.9% | < 43 min/mês |
| Response Time (p95) | 500ms | > 1s = alerta |
| Error Rate | < 0.1% | > 1% = page |
| Deployment Time | < 15 min | > 30 min = investigate |

---

## 🔐 Credenciais (Secure Vault)

Armazenar em:
- [ ] AWS Secrets Manager
- [ ] HashiCorp Vault
- [ ] Azure Key Vault
- [ ] Sealed Secrets (K8s)

**NÃO em:**
- ❌ Git (.env no repo)
- ❌ Docker image (hardcoded)
- ❌ Logs (output sensível)

---

## 📞 Escalation

```
Nível 1: On-call Engineer
Nível 2: Team Lead (engenharia)
Nível 3: Diretor de Operações
Nível 4: CTO
```

---

## ✅ Sign-off

- [ ] Desenvolvedor: ________________ Data: _______
- [ ] QA/Tester: ________________ Data: _______
- [ ] DevOps/SRE: ________________ Data: _______
- [ ] Product Manager: ________________ Data: _______

---

**Status:** ⏳ READY FOR PRODUCTION
