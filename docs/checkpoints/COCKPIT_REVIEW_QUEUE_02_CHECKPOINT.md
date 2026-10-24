# Checkpoint — Hardening de Segurança e Validação RBAC da Fila de Revisão (COCKPIT-REVIEW-QUEUE-02)

**Data:** 23/10/2026
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`
**Branch:** `feature/cash-audit-fechamento`
**Base HEAD:** `0f62c72dcdd1fe30bc8d0d1a163bcbc3716bc592`

---

## 1. Resumo Executivo

Validação de segurança e governança de acesso (RBAC estrito) implementada e comprovada para a Fila Local de Revisão e Aprendizagem antes de qualquer liberação operacional:

1. **Matriz de Acesso RBAC Explícita:**
   - **Diretor (`diretor`):** Leitura de todas as empresas e operações completas de alteração (`classificar`, `bloquear`, `cancelar`);
   - **Auditor (`auditor`):** Leitura irrestrita de todas as empresas; qualquer tentativa de mutação bloqueada com HTTP 403;
   - **Gerente (`gerente`):** Leitura estritamente restrita à sua própria empresa (`company_id`); tentativa de leitura de outra unidade ou de alteração de pendências bloqueada com HTTP 403;
   - Nenhum perfil além de `diretor` tem autorização para alterar pendências nesta etapa.
2. **Proteção de Rotas e Páginas:**
   - Endpoint HTML `/revisao` protegido por autenticação obrigatória via `get_current_user` (HTTP 401 para requisições não autenticadas);
   - Rotas de API retornam HTTP 401 para requisições anônimas ou com tokens inválidos;
   - Página Next.js preserva o padrão de autenticação do Cockpit LOGOS.
3. **Tratamento e Registro Transparente de Rotas:**
   - Restaurado o log original de aviso em `cash-audit` (`logging.getLogger(__name__).warning("Rotas cash-audit não carregadas: %s", exc)`);
   - Falhas de carregamento em `classification-review` registradas explicitamente com severidade de erro e stacktrace (`logging.getLogger(__name__).error(..., exc_info=True)`);
   - Teste unitário automatizado garante que todas as rotas da fila e a rota `/revisao` estão devidamente registradas no aplicativo FastAPI unificado.
4. **Validação de Build do Frontend:**
   - Status: `BLOCKED_BUILD_VALIDATION`.
   - Motivo: `frontend/cockpit/node_modules` ausente no ambiente local e diretriz estrita de "Não instalar dependências novas" impede a execução do `next build`.
5. **Barreiras e Integridade Operacional:**
   - Conta `198966` com `candidato_lancavel=0` e `permite_despesa=0`, categoricamente rejeitada para planos definitivos;
   - Conta financeira `27173` e allowlist `{17837}` inalteradas e bloqueadas;
   - ERP WRITES = ZERO (0 POST, 0 PUT, 0 PATCH, 0 DELETE ao webPosto).

---

## 2. Matriz de Acesso RBAC

| Perfil / Papel | Leitura Fila Geral | Leitura Própria Empresa | Leitura Outra Empresa | Classificar | Bloquear | Cancelar |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Diretor** (`diretor`) | Permitido (200) | Permitido (200) | Permitido (200) | Permitido (200) | Permitido (200) | Permitido (200) |
| **Auditor** (`auditor`) | Permitido (200) | Permitido (200) | Permitido (200) | **Negado (403)** | **Negado (403)** | **Negado (403)** |
| **Gerente** (`gerente`) | Filtrado p/ unidade | Permitido (200) | **Negado (403)** | **Negado (403)** | **Negado (403)** | **Negado (403)** |
| **Não Autenticado** | **Negado (401)** | **Negado (401)** | **Negado (401)** | **Negado (401)** | **Negado (401)** | **Negado (401)** |

---

## 3. Cobertura de Testes Automatizados

- 32 testes na suíte `tests/unit/classification_review/` (18 testes de API/RBAC + 14 testes de ciclo de vida e concorrência).
- 106 testes de regressão com Master Data e sincronização de planos 100% aprovados.
- Testes cobrem exaustivamente:
  - 401 para ausência de credenciais;
  - Auditor leitura 200, mutação 403;
  - Gerente leitura própria 200, leitura outra unidade 403, mutação 403;
  - Diretor mutação 200;
  - Proteção de `/revisao` com 401;
  - Rejeição da conta 198966;
  - Registro de rotas no app unificado;
  - Ausência total de chamadas mutacionais ao webPosto.
