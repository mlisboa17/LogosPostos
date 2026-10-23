# Checkpoint — Fila Local de Revisão e Aprendizagem (EXPENSE-REVIEW-QUEUE-01)

**Data:** 23/10/2026  
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Base HEAD:** `e057837592ad94ac27997f34ec1fa01278a2d504`  

---

## 1. Resumo Executivo

Implementação completa da **Fila Local de Revisão e Aprendizagem** para classificações incertas no LOGOS, sem realizar nenhuma mutação ou lançamento no ERP (`ERP WRITES = ZERO`).

A fila desacopla a recepção/extração de despesas do lançamento financeiro definitivo, assegurando que transações com baixa confiança ou inconsistências passem por validação humana prévia e sirvam como base de aprendizado supervisionado contínuo.

---

## 2. Arquitetura e Persistência Reutilizada (REUSE > ADAPT > CREATE)

- **Armazenamento ACID:** SQLite WAL mode com foreign keys e locks de escrita pessimistas (`BEGIN IMMEDIATE`).
- **Base Central:** Integrado ao SQLite de Master Data (`WebPosto_API/data/master_data/master_data.sqlite3`), permitindo validação relacional direta contra empresas, contas bancárias e planos de conta.
- **Backup Verificável Pré-Migração:**
  - Arquivo: `WebPosto_API/data/master_data/master_data.pre_revisao_01.20261023T222326Z.sqlite3.bak`
  - Tamanho: 630.784 bytes
  - SHA-256: `09168F8EC7DF198FCA38808F1A21FD6CF477FFD762FBED1FD2EB3EA62B62AE74`
- **Migração Reversível Idempotente:**
  - Script: `WebPosto_API/src/modules/master_data/adapters/migrations/migration_002_fila_revisao_classificacao.py`
  - Tabelas criadas:
    1. `fila_revisao_classificacao` (ciclo de vida, travas, versionamento otimista);
    2. `fila_revisao_historico` (trilha imutável e append-only);
    3. `classificacao_exemplos_confirmados` (exemplos humanos consolidados para busca por similaridade);
    4. `classificacao_regras_candidatas` (regras em estágio probatório, exigindo >= 3 confirmações e autorização formal).

---

## 3. Regras de Negócio e Salvaguardas Implacáveis

1. **Confiança nunca supera uma trava:**
   Mesmo com 100% de confiança da IA (`confianca_ia = 1.0`), havendo trava cadastral (ex: conta não autorizada, duplicidade, divergência), o item é categoricamente gravado como `BLOQUEADO`.
2. **Baixa confiança vira pendência:**
   Casos com confiança abaixo do limiar (0.85) são direcionados exclusivamente para `PENDENTE_REVISAO`.
3. **Conta Oficial 198966 (`2.04.10 - SAÍDAS PENDENTES DE CLASSIFICAÇÃO`):**
   Permanece estritamente com `permite_despesa = 0` e `candidato_lancavel = 0`. Bloqueada para lançamentos reais e categoricamente impedida de ser definida como plano definitivo na revisão humana.
4. **Aprendizagem Supervisionada:**
   - Decisões humanas viram **exemplos confirmados**, nunca regras automáticas.
   - Regras candidatas exigem no mínimo 3 confirmações idênticas E aprovação humana formal (`promover_regra_candidata`).
5. **Concorrência e Idempotência:**
   - Hash unívoco SHA-256 impede duplicatas.
   - Controle de versão otimista (`versao`) impede revisões simultâneas conflitantes (`RevisaoConcorrenteErro`).
6. **Segurança de Dados:**
   - Sanitização automática de credenciais, chaves de API, senhas e números de cartão em referências de evidências.

---

## 4. Testes e Validação

- **Suíte de Testes da Fila:** `WebPosto_API/tests/unit/classification_review/test_fila_revisao_classificacao.py`
  - 14 testes cobrindo migração, idempotência, baixa confiança, travas, concorrência, bloqueio da conta 198966, promoção de regras, auditoria e sanitização (100% aprovados).
- **Regressão Global:** 138 testes executados e aprovados (Master Data, Reconciliação, Pré-validação, Escrita e Fila de Revisão).
- **ERP WRITES:** Rigorosamente **ZERO** (0 POST, 0 PUT, 0 PATCH, 0 DELETE).
