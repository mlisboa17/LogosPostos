# 🎨 FRONTEND REFLEX - DIVISÃO PARALELA 3 IAs

## 📋 Estructura de Tarefas

### 🔄 **GEMINI 2.0** (Performance/Infraestrutura)
**Responsável**: Docker, Build Pipeline, Cache, Performance

#### Arquivos:
- `docker-compose.yml` (adicionar frontend service)
- `Dockerfile.frontend` (NEW - Multi-stage)
- `config/turbopack.config.js` (NEW)
- `.dockerignore` (otimizado)

#### Checklist:
- [ ] Multi-stage build (Node 22 + Python 3.12)
- [ ] Docker image < 200MB (alpine-slim)
- [ ] Turbopack config com hot-reload <100ms
- [ ] Redis cache para GlobalState
- [ ] Healthcheck no port 3000
- [ ] Asset compression (Brotli)
- [ ] State Update latency <20ms

---

### 💻 **CLAUDE 3.7** (UX/DDD Architecture)
**Responsável**: State Management, Componentes, Navegação

#### Arquivos:
- `src/presentation/__init__.py` (NEW)
- `src/presentation/frontend/__init__.py` (NEW)
- `src/presentation/frontend/state.py` (NEW - GlobalState)
- `src/presentation/frontend/components/__init__.py` (NEW)
- `src/presentation/frontend/components/dashboard_card.py` (NEW)
- `src/presentation/frontend/components/sync_progress.py` (NEW)
- `src/presentation/frontend/components/company_selector.py` (NEW)
- `src/presentation/frontend/router.py` (NEW - Permissões)

#### Checklist:
- [ ] GlobalState com UserSession, SyncStatus, ActiveCompany
- [ ] Componentes Atomic Design (Atom/Molecule/Organism)
- [ ] Tipagem estrita Pydantic V2 em todos States
- [ ] Navegação baseada em RBAC (Partner/Director)
- [ ] Error Handling visual (Toasts)
- [ ] Strict MyPy typing (0 errors)

---

### 🎨 **GROK 4** (UI/Algoritmos & Motion)
**Responsável**: Temas, Renderização, Animações

#### Arquivos:
- `src/presentation/frontend/styles/__init__.py` (NEW)
- `src/presentation/frontend/styles/themes.py` (NEW - Dark/Light)
- `src/presentation/frontend/styles/colors.py` (NEW - Color System)
- `src/presentation/frontend/components/rateio_chart.py` (NEW - Renderização condicional)
- `src/presentation/frontend/animations.py` (NEW - Framer Motion)
- `requirements-frontend.txt` (NEW - Reflex + deps)

#### Checklist:
- [ ] Dark Mode por padrão ('Logos Dark')
- [ ] Renderização condicional gráficos Rateio
- [ ] Motion Design com Reflex animations
- [ ] Lighthouse Accessibility: 100
- [ ] Mobile-First responsividade
- [ ] Assets otimizados (SVG inline)

---

## 🔗 Dependências Entre Tarefas

```
GEMINI 2.0 (Docker)
    ↓
    └→ Aguarda requirements-frontend.txt (GROK 4)
    
CLAUDE 3.7 (State)
    ↓
    └→ Usa themes.py (GROK 4)
    └→ Usa animations.py (GROK 4)
    
GROK 4 (Styles/Themes)
    ↓
    └→ Alimenta CLAUDE 3.7
    └→ Suporta GEMINI 2.0 (assets otimizados)
```

## 📊 Sequência de Execução

### Fase 1: Setup Base (PARALELO)
- [x] CLAUDE 3.7: Criar state.py (GlobalState base)
- [x] GROK 4: Criar themes.py + colors.py
- [x] GROK 4: requirements-frontend.txt (Reflex + Framer Motion)

### Fase 2: Componentes (SERIAL - após Phase 1)
- [ ] CLAUDE 3.7: DashboardCard, SyncProgress, CompanySelector
- [ ] GROK 4: Rateio renderização condicional

### Fase 3: Docker + CI/CD (SERIAL - após Phase 1-2)
- [ ] GEMINI 2.0: Dockerfile.frontend multi-stage
- [ ] GEMINI 2.0: docker-compose.yml atualizado
- [ ] GEMINI 2.0: turbopack.config.js

### Fase 4: Validação (PARALELO)
- [ ] CLAUDE 3.7: MyPy check (0 errors)
- [ ] GROK 4: Lighthouse check (score 100)
- [ ] GEMINI 2.0: Build Docker + healthcheck

---

## ✅ Critérios de Sucesso

| Métrica | Meta | Status |
|---------|------|--------|
| Docker Image Size | < 200MB | ⏳ |
| Hot Reload | < 100ms | ⏳ |
| State Update | < 20ms | ⏳ |
| MyPy Errors | 0 | ⏳ |
| Lighthouse Score | 100 | ⏳ |
| Accessibility | WCAG 2.1 AA | ⏳ |

---

## 🚀 Timeline Estimada

- **Fase 1**: 30min (setup paralelo)
- **Fase 2**: 40min (componentes serial)
- **Fase 3**: 35min (docker serial)
- **Fase 4**: 15min (validação paralelo)

**Total**: ~2h para sistema completo
