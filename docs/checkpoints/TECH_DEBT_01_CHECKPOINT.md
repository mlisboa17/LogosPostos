# CHECKPOINT — LOGOS TECH-DEBT-01
## Auditoria de Scripts Não Rastreados e Arquivos Históricos (-mlisboa17.py)

**Data e Hora:** 2026-10-22 15:30:00 -03:00  
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Commit Base:** `4cfc880` (docs(settlement): checkpoint MAIS-BANK-05)  
**Prioridade:** P2 — Higiene Técnica e Rastreabilidade  
**Classificação:** TECH DEBT AUDITED / ACCOUNT 27173: BLOCKED / PILOTO CASA CAIADA: BLOCKED  
**Escritas no ERP:** ZERO (0)  
**Chamadas Externas:** ZERO (0)  

---

### 1. ESTADO DA AUDITORIA TÉCNICA

Neste ciclo (TECH-DEBT-01), executou-se a auditoria técnica e estática dos arquivos residuais do repositório:

1. **Cinco Scripts Não Rastreados em `WebPosto_API/scripts/`:**
   - `probe_premmia_portal.py`: Script de automação de navegador (Playwright) para o portal Premmia/Vibra da filial VIP (`11495`) e consulta read-only ao ERP. Consome `PREMMIA_usuario_POSTO_VIP`, `PREMMIA_SENHA_POSTO_VIP`, chave da unidade 11495 e `WEBPOSTO_BASE_URL`. Possui risco alto de bloqueio de conta/CAPTCHA. Classificado como **ARQUIVAR / QUARENTENA**.
   - `scratch_audit_p0.py`: Leitor local de `audit_p0_results.json`. Zero chamadas externas e zero credenciais. Classificado como **CANDIDATO A DESCARTE**.
   - `scratch_check_probe_raw.py`: Leitor local de logs `audit_p0_output.txt`. Zero chamadas externas e zero credenciais. Classificado como **CANDIDATO A DESCARTE**.
   - `scratch_probe.py`: Leitor local de chaves JSON. Zero chamadas externas e zero credenciais. Classificado como **CANDIDATO A DESCARTE**.
   - `scratch_probe_endpoints.py`: Filtro local de endpoints cadastrais salvos. Zero chamadas externas e zero credenciais. Classificado como **CANDIDATO A DESCARTE**.
   - *Garantia:* Nenhum dos scripts foi executado.

2. **Dois Arquivos Históricos `-mlisboa17.py` em `WebPosto_API/src/`:**
   - `dependencies-mlisboa17.py` (63 linhas) e `main-mlisboa17.py` (17 linhas) são fragmentos truncados com erros fatais de sintaxe gerados por conflitos de sincronização de arquivo / rascunhos antigos.
   - Não possuem nenhuma importação ativa, não são referenciados por testes, Docker, jobs ou inicializadores da aplicação.
   - Seus equivalentes canônicos (`dependencies.py` e `main.py`) compilam com sucesso, importam limpo e sustentam as rotas em produção.
   - *Garantia:* Nenhum arquivo histórico foi renomeado, removido ou modificado nesta sprint.

---

### 2. AVALIAÇÃO DE GOVERNANÇA E SEGURANÇA

1. **Preservação de Integridade:** Os cinco scripts de probe/scratch continuam não rastreados e fora de qualquer commit. Os dois arquivos com sufixo `-mlisboa17.py` foram mantidos intocados para deliberação futura.
2. **Conta 27173 (Banco do Brasil Casa Caiada):** Permanece estritamente classificada como `TRANSITORIA` no banco de dados local `master_data.sqlite3`, com débito desabilitado (`permite_debito_despesa = False`).
3. **Piloto Casa Caiada:** Permanece estritamente **BLOCKED**.
4. **Cadeia Mais Pagamentos:** Permanece estritamente **BLOCKED**.

---

### 3. ARTEFATOS PRODUZIDOS

- [TECH_DEBT_01_SCRIPTS_AND_LEGACY_AUDIT.md](../validation/TECH_DEBT_01_SCRIPTS_AND_LEGACY_AUDIT.md): Relatório de auditoria técnica exaustiva.
- [docs/checkpoints/TECH_DEBT_01_CHECKPOINT.md](TECH_DEBT_01_CHECKPOINT.md): Este documento de checkpoint.
- [STATUS.md](../../STATUS.md): Atualizado com a seção do ciclo TECH-DEBT-01.

---

### 4. TESTES E VALIDAÇÕES EXECUTADOS

- `python -m py_compile WebPosto_API/src/main.py WebPosto_API/src/interfaces/http/dependencies.py`: **100% OK (Exit code 0)**.
- `python -c "import sys; sys.path.insert(0, 'WebPosto_API'); from src.interfaces.http.dependencies import get_current_user, get_db; print('Dependencies OK')"`: **100% OK**.
- `python -c "import sys; sys.path.insert(0, 'WebPosto_API'); from src.main import app; print('App OK')"`: **100% OK**.
- `python -m pytest WebPosto_API/tests/unit/cash_reconciliation/test_piloto_cartao.py -q --no-cov`: **48 passed, 7 warnings** (0 tentativas reais de portal/rede).
