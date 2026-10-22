# TECH-DEBT-01 — Auditoria Técnica de Scripts de Probe/Scratch e Arquivos Históricos

**Data:** 22/10/2026  
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Prioridade:** P2 — Higiene Técnica, Rastreabilidade e Segurança de Código  
**Modo:** READ-ONLY OFFLINE (Zero chamadas de rede, zero execuções de scripts, zero escritas no ERP)  
**Veredito:** **CONCLUÍDO COM RECOMENDAÇÃO DE ISOLAMENTO/DESCARTE FUTURO**

---

## 1. Contexto e Objetivos

Esta sprint técnica tem como objetivo auditar minuciosamente:
1. **Cinco scripts não rastreados** em `WebPosto_API/scripts/` (`probe_premmia_portal.py` e quatro scripts `scratch_*`);
2. **Dois arquivos históricos com sufixo pessoal** em `WebPosto_API/src/` (`dependencies-mlisboa17.py` e `main-mlisboa17.py`) em confronto direto com seus equivalentes canônicos (`dependencies.py` e `main.py`).

A análise avalia finalidade, proveniência, consumo de variáveis de ambiente (sem expor segredos), riscos operacionais e financeiro-cadastrais, dependências no ecossistema e recomendações objetivas de manutenção, adaptação, arquivamento ou descarte.

---

## 2. Inventário e Avaliação dos Cinco Scripts Não Rastreados

Nenhum dos cinco scripts abaixo foi executado durante esta auditoria.

### 2.1. `WebPosto_API/scripts/probe_premmia_portal.py`
- **Finalidade:** Automação de navegador (Playwright síncrono, `headless=False`, `slow_mo=300ms`) para login interativo no portal de revendedores Premmia / Vibra Energia (`https://cn.vibraenergia.com.br/premmia/revendedor/login`), navegação até a conferência de pagamentos, exportação do relatório de transações em Excel (XLSX) e posterior confronto com registros do ERP webPosto da filial VIP (`empresaCodigo 11495`).
- **Origem Provável:** Desenvolvido durante a concepção da Sprint de conciliação Premmia (documentado nos prompts `PREMMIA_00_teste_controlado.md` e `SPRINT_13_premmia_01.md`).
- **Integrações Externas Utilizadas:**
  1. *Portal Web Premmia / Vibra Energia* (`cn.vibraenergia.com.br`) via Playwright;
  2. *API REST webPosto* (`https://web.qualityautomacao.com.br/INTEGRACAO/V1/`) via cliente HTTP `httpx`.
- **Endpoints Envolvidos:**
  - `https://cn.vibraenergia.com.br/premmia/revendedor/login`
  - `https://cn.vibraenergia.com.br/premmia/revendedor/conferencia/pagamentos`
  - `/INTEGRACAO/V1/CARTOES`
  - `/INTEGRACAO/V1/VENDAS_FORMA_PAGAMENTO`
  - `/INTEGRACAO/V1/VENDAS`
- **Variáveis de Ambiente Consumidas:**
  - `PREMMIA_usuario_POSTO_VIP` (ou `PREMMIA_USUARIO_POSTO_VIP`)
  - `PREMMIA_SENHA_POSTO_VIP`
  - Variável de chave da filial VIP (via `unidade.chave_env`, ex.: `WEBPOSTO_CHAVE_11495`)
  - `WEBPOSTO_BASE_URL`
  - `WEBPOSTO_WRITES` (utilizada como trava preventiva: aborta se for diferente de "0")
- **Risco de Escrita:**
  - *No ERP:* Zero escrita (apenas consultas `GET` paginadas sob `/INTEGRACAO/V1/`).
  - *Localmente:* Criação de diretórios e escrita de arquivos brutos/normalizados em `data/premmia/<data>/11495/`.
- **Risco de Bloqueio de Conta:** **ALTO**. Automações baseadas em Playwright contra portais corporativos sujeitam o usuário a desafios de CAPTCHA, Cloudflare, 2FA ou bloqueio por tentativas excessivas/detecção de bot. O código possui detecção preventiva (`Parada("bloqueado por CAPTCHA, 2FA...")`), mas o risco na borda da rede do provedor é real.
- **Risco de Vazamento de Segredo:** **MÉDIO**. O código possui sanitizadores explícitos (`sem_segredos()` para payloads JSON e mascaramento visual `mask=[page.locator("body")]` em screenshots de erro), mas manipula credenciais em memória e as insere em campos de texto do browser.
- **Classificação:** **ARQUIVAR / MANTER EM QUARENTENA**. Não deve ser integrado como rotina automatizada contínua sem infraestrutura dedicada de headless seguro e governança formal de credenciais do revendedor Vibra.

---

### 2.2. `WebPosto_API/scripts/scratch_audit_p0.py`
- **Finalidade:** Script utilitário simples em Python para inspecionar localmente a estrutura do arquivo JSON `WebPosto_API/scripts/audit_p0_results.json`, filtrando rotas e chaves associadas a termos cadastrais (`conta`, `empresa`, `centro`, `fornecedor`, `plano`).
- **Origem Provável:** Ferramenta descartável de inspeção rápida criada pelo desenvolvedor/IA durante a fase MASTER-DATA-01.
- **Integrações Externas:** **NENHUMA (0)**.
- **Endpoints Envolvidos:** **NENHUM (0)**.
- **Variáveis de Ambiente Consumidas:** **NENHUMA (0)**.
- **Risco de Escrita:** **ZERO**. Apenas leitura do arquivo local.
- **Risco de Bloqueio de Conta:** **ZERO**.
- **Risco de Vazamento de Segredo:** **BAIXO**. Apenas exibe chaves e tamanhos no terminal.
- **Classificação:** **CANDIDATO A DESCARTE**. Totalmente descartável, pois seus achados já foram consolidados nos relatórios definitivos de Master Data.

---

### 2.3. `WebPosto_API/scripts/scratch_check_probe_raw.py`
- **Finalidade:** Verificar localmente a presença e ler as primeiras 10 linhas do arquivo de log `audit_p0_output.txt` e exibir os primeiros 300 caracteres do código-fonte de `webposto_network_probe.py`.
- **Origem Provável:** Script scratch de debug pontual do pipeline de sonda de rede.
- **Integrações Externas:** **NENHUMA (0)**.
- **Endpoints Envolvidos:** **NENHUM (0)**.
- **Variáveis de Ambiente Consumidas:** **NENHUMA (0)**.
- **Risco de Escrita:** **ZERO**.
- **Risco de Bloqueio de Conta:** **ZERO**.
- **Risco de Vazamento de Segredo:** **BAIXO**.
- **Classificação:** **CANDIDATO A DESCARTE**. Arquivo temporário de desenvolvimento sem valor operacional residual.

---

### 2.4. `WebPosto_API/scripts/scratch_probe.py`
- **Finalidade:** Inspecionar localmente as chaves e a quantidade de registros das respostas salvas em `audit_p0_results.json` e `webposto_network_probe_result.json`.
- **Origem Provável:** Script de suporte exploratório para elaboração do mapeamento de schemas da API webPosto.
- **Integrações Externas:** **NENHUMA (0)**.
- **Endpoints Envolvidos:** **NENHUM (0)**.
- **Variáveis de Ambiente Consumidas:** **NENHUMA (0)**.
- **Risco de Escrita:** **ZERO**.
- **Risco de Bloqueio de Conta:** **ZERO**.
- **Risco de Vazamento de Segredo:** **BAIXO**.
- **Classificação:** **CANDIDATO A DESCARTE**. Funções de inspeção superadas pelo inventário cadastral formal.

---

### 2.5. `WebPosto_API/scripts/scratch_probe_endpoints.py`
- **Finalidade:** Iterar sobre a lista de endpoints registrada no artefato estático local `webposto_network_probe_result.json`, filtrando nomes relacionados a cadastros mestres e imprimindo status HTTP, contagem de registros e campos retornados.
- **Origem Provável:** Rascunho de análise estática utilizado na formulação de `MASTER_DATA_01_INVENTORY.md`.
- **Integrações Externas:** **NENHUMA (0)**.
- **Endpoints Envolvidos:** **NENHUM (0)**.
- **Variáveis de Ambiente Consumidas:** **NENHUMA (0)**.
- **Risco de Escrita:** **ZERO**.
- **Risco de Bloqueio de Conta:** **ZERO**.
- **Risco de Vazamento de Segredo:** **BAIXO**.
- **Classificação:** **CANDIDATO A DESCARTE**. Informações já totalmente absorvidas na documentação canônica de Master Data.

---

## 3. Análise dos Arquivos Históricos com Sufixo Pessoal (`-mlisboa17.py`)

Dois arquivos versionados na árvore de trabalho do projeto possuem o sufixo `-mlisboa17.py`:
1. `WebPosto_API/src/interfaces/http/dependencies-mlisboa17.py`
2. `WebPosto_API/src/main-mlisboa17.py`

### 3.1. Confronto com os Arquivos Canônicos

#### A. `dependencies-mlisboa17.py` (63 linhas) vs. `dependencies.py` (141 linhas)
- **Estado do Arquivo Histórico:** O arquivo `dependencies-mlisboa17.py` é uma versão embrionária incompleta. Termina abruptamente na linha 63 dentro do docstring da função `get_auditoria_service()`, sem corpo funcional e com aspas triplas abertas.
  - *Compilação (`py_compile`):* Falha com `SyntaxError: unterminated triple-quoted string literal (detected at line 63)`.
  - *Conteúdo:* Tentativa de injeção de `AuditoriaService` e `WebPostoClient`, incompatível com a arquitetura atual de autenticação e rotas.
- **Estado do Arquivo Canônico:** `WebPosto_API/src/interfaces/http/dependencies.py` é o arquivo oficial e operacional (141 linhas), perfeitamente estruturado e completo.
  - *Compilação (`py_compile`):* **Exit code 0** (compilação limpa).
  - *Importação:* `from src.interfaces.http.dependencies import get_current_user, get_db` executa sem erros.
  - *Conteúdo:* Implementa autenticação JWT (`get_current_user`, `get_tv_user`, `get_commercial_user`), controle de permissões por perfil (`require_unit_access`), gerenciamento de sessão assíncrona SQLAlchemy (`get_db`) e injeção do EventBus e serviços.

#### B. `main-mlisboa17.py` (17 linhas) vs. `main.py` (17 linhas)
- **Estado do Arquivo Histórico:** `main-mlisboa17.py` é um fragmento corrompido de 17 linhas que foi interrompido no meio de uma declaração de importação:
  ```python
  from src.interfaces.http.routes import (
      auditoria,
      clientes,
  ```
  - *Compilação (`py_compile`):* Falha com `SyntaxError: '(' was never closed`.
  - *Conteúdo:* Não instancia FastAPI, não define rotas e não configura inicialização.
- **Estado do Arquivo Canônico:** `WebPosto_API/src/main.py` (17 linhas) é o launcher oficial da aplicação FastAPI.
  - *Compilação (`py_compile`):* **Exit code 0** (compilação limpa).
  - *Importação:* `from src.main import app` instancia a aplicação via `create_app()` com sucesso.
  - *Conteúdo:* Ponto de entrada padrão para `uvicorn.run("src.main:app", ...)`.

---

### 3.2. Natureza e Diagnóstico dos Arquivos `-mlisboa17.py`
A inspeção técnica confirma categoricamente que esses arquivos são **cópias residuais de conflito de sincronização de arquivo** (típicas de processos de sincronização de nuvem como OneDrive ou ferramentas de IDE ao detectar concorrência de escrita com o usuário `mlisboa17`) ou **rascunhos abandonados de edição intermitente**.

- **São código referenciado?** **NÃO**.
- **São importados por algum módulo?** **NÃO** (a própria sintaxe corrompida impede qualquer `import`).
- **São necessários para a aplicação ou testes?** **NÃO**.
- **São citados na documentação de débito técnico?** **SIM**. Artefatos como `ARCHITECTURE_BASELINE_1.0.md`, `ENTRYPOINT_MIGRATION.md`, `MIGRATION_PLAN_A02.md`, `TECH_DEBT_MASTER.md` e `STATUS.md` já os classificavam historicamente como débito técnico inativo com recomendação de remoção futura.

---

## 4. Auditoria de Referências em Todo o Repositório

Foi realizada uma busca textual exaustiva (grep) por referências aos sete arquivos:

| Arquivo Auditado | Ocorrências em Código Python | Ocorrências em Testes | Ocorrências em Docker/CI/Jobs | Ocorrências em Documentação/Status | Status de Dependência |
|---|---|---|---|---|---|
| `probe_premmia_portal.py` | 0 | 0 | 0 | 9 (Prompts históricos, checkpoints, status) | **Isolado / Não referenciado por rotinas** |
| `scratch_audit_p0.py` | 0 | 0 | 0 | 2 (Checkpoints e status recentes) | **Zero dependências** |
| `scratch_check_probe_raw.py` | 0 | 0 | 0 | 0 | **Zero dependências** |
| `scratch_probe.py` | 0 | 0 | 0 | 0 | **Zero dependências** |
| `scratch_probe_endpoints.py` | 0 | 0 | 0 | 0 | **Zero dependências** |
| `dependencies-mlisboa17.py` | 0 | 0 | 0 | 3 (Auditoria de capacidade e status) | **Zero dependências (Arquivo quebrado)** |
| `main-mlisboa17.py` | 0 | 0 | 0 | 11 (Matrizes de tech debt e status) | **Zero dependências (Arquivo quebrado)** |

Em contrapartida, os arquivos canônicos `dependencies.py` e `main.py` concentram dezenas de importações ativas em rotas HTTP, testes unitários, scripts de automação do gateway e definições de Dockerfile e Playwright.

---

## 5. Validações Offline Executadas

1. **Compilação Canônica:**
   - `python -m py_compile WebPosto_API/src/main.py WebPosto_API/src/interfaces/http/dependencies.py`
   👉 **SUCESSO (Exit code 0)**.
2. **Importação Canônica:**
   - `python -c "import sys; sys.path.insert(0, 'WebPosto_API'); from src.interfaces.http.dependencies import get_current_user, get_db; print('Dependencies OK')"`
   👉 **SUCESSO (Exit code 0)**.
   - `python -c "import sys; sys.path.insert(0, 'WebPosto_API'); from src.main import app; print('App OK')"`
   👉 **SUCESSO (Exit code 0)**.
3. **Testes Unitários Relacionados:**
   - `python -m pytest WebPosto_API/tests/unit/cash_reconciliation/test_piloto_cartao.py -q --no-cov`
   👉 **48 passed, 7 warnings in 6.52s** (Validação das rotas e dependências de usuário com mock; 0 chamadas externas).
4. **Nota sobre `compileall` Global:**
   - Conforme exigência regulatória, registra-se que o comando `python -m compileall .` falha exclusivamente devido à sintaxe truncada dos dois arquivos `-mlisboa17.py` (e exemplos na raiz), não havendo qualquer erro nos módulos funcionais do sistema.

---

## 6. Governança e Regras Invioláveis Mantidas

- **ACCOUNT 27173:** **BLOCKED** (`TRANSITORIA`, `permite_debito_despesa = False`).
- **CASA CAIADA PILOT:** **BLOCKED**.
- **CADEIA MAIS PAGAMENTOS:** **BLOCKED**.
- **ESCRITAS NO ERP:** **ZERO (0)**.
- **CHAMADAS EXTERNAS:** **ZERO (0)**.
- **PRESERVAÇÃO:** Nenhum arquivo `-mlisboa17.py` foi removido ou alterado nesta etapa. Os scripts não rastreados não foram executados e permanecem fora da área de staging.
