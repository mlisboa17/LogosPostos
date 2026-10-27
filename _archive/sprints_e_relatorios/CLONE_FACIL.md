# 🚀 CLONE + SETUP EM 1 COMANDO

---

## Copie e cole isto no seu terminal:

```bash
curl -fsSL https://seu-repo.com/install.sh | bash
```

**OU**

```bash
bash -c "$(curl -fsSL https://seu-repo.com/install.sh)"
```

---

## ⏱️ O que acontece (10 minutos)

1. ✅ Detecta seu sistema (Linux/macOS/Windows)
2. ✅ Instala Docker
3. ✅ Instala Python 3.11
4. ✅ Instala Git
5. ✅ Clona o repositório
6. ✅ Cria virtual environment
7. ✅ Instala dependências Python
8. ✅ Configura .env
9. ✅ Build Docker image
10. ✅ Inicia stack (6 containers)
11. ✅ Roda testes
12. ✅ Exibe status

---

## ✅ Pronto!

Depois que acabar, você terá:

```
✓ Código clonado em: ~/logos-auditoria
✓ Docker rodando (6 containers)
✓ API em: http://localhost:8000
✓ Dashboard em: http://localhost:8000
✓ Grafana em: http://localhost:3000
✓ Testes passando
```

---

## 🎯 Próximo passo (após instalar)

```bash
cd ~/logos-auditoria
source venv/bin/activate
docker-compose ps
```

**Esperado:**
```
NAME              STATUS
api               Up (healthy)
mongo             Up (healthy)
redis             Up
nginx             Up
prometheus        Up
grafana           Up
```

---

## 📖 Depois leia:

```
COMECE_AQUI.txt
PASSO_A_PASSO.md
```

---

## ⚙️ Se preferir manual:

```bash
# 1. Clone
git clone https://seu-repo.com/logos-auditoria.git
cd logos-auditoria

# 2. Setup
chmod +x setup_local.sh
./setup_local.sh

# Pronto!
```

---

**Qualquer dúvida: ver PASSO_A_PASSO.md seção "Se algo der errado"**
