# Checkpoint — Interface e Endpoints da Fila de Revisão no Cockpit (COCKPIT-REVIEW-QUEUE-01)

**Data:** 23/10/2026  
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Base HEAD:** `c0f66682a106090c835fe8f715bf72b5a4a69cb8`  

---

## 1. Resumo Executivo

Disponibilização da **Fila Local de Revisão e Aprendizagem** para operação humana no **Cockpit do LOGOS**, sem permitir qualquer escrita ou lançamento no ERP webPosto (`ERP WRITES = ZERO`).

A interface permite aos diretores e auditores visualizar pendências financeiras incertas, inspecionar evidências sanitizadas, analisar recomendações da IA, aplicar travas e classificar transações exclusivamente com contas-folha oficiais válidas.

---

## 2. Endpoints Locais Autenticados Implementados

Rotas registradas sob o prefixo `/api/v1/classification-review` com autenticação RBAC via JWT/Cookies (`get_current_user` e `require_unit_access`):

1. `GET /pendencias`: listagem com filtros por status (`PENDENTE_REVISAO`, `CLASSIFICADO`, `BLOQUEADO`, `CANCELADO`) e empresa (gerentes restritos à sua unidade).
2. `GET /pendencias/{id}`: detalhes completos com sanitização rigorosa de credenciais/documentos sensíveis.
3. `GET /pendencias/{id}/historico`: trilha auditável imutável de mudanças.
4. `POST /pendencias/{id}/classificar`: classificação humana definitiva com validação estrita de conta-folha válida; rejeição de 198966 e contas pai (HTTP 422); proteção de concorrência por versão (HTTP 409). Invalida qualquer aprovação ou proposta anterior.
5. `POST /pendencias/{id}/bloquear`: bloqueio manual justificado com registro de travas.
6. `POST /pendencias/{id}/cancelar`: cancelamento formal de transação descartada.
7. `GET /casos-semelhantes`: busca por similaridade textual em exemplos humanos confirmados.
8. `GET /metricas`: indicadores de acurácia da IA e volumetria por status.
9. `GET /planos-validos`: catálogo restrito de contas (`ativo=1, observado_ultima_sincronizacao=1, eh_folha=1, candidato_lancavel=1, plano != 198966`).
10. `GET /regras-candidatas`: listagem de regras em estágio probatório (regras com >= 3 casos marcadas apenas como elegíveis para revisão, sem ativação de automação ou lançamento).

---

## 3. Telas do Cockpit Disponibilizadas

1. **Cockpit Next.js (App Router + shadcn/ui):**
   - Página: [page.tsx](file:///C:/Projetos/LOGOS/LogosPostos/frontend/cockpit/src/app/revisao/page.tsx)
   - Componente: [classification-review-live.tsx](file:///C:/Projetos/LOGOS/LogosPostos/frontend/cockpit/src/components/classification-review-live.tsx)
   - Menu lateral: item "Classificação" adicionado em [app-sidebar.tsx](file:///C:/Projetos/LOGOS/LogosPostos/frontend/cockpit/src/components/app-sidebar.tsx).
2. **Cockpit Gateway HTML (FastAPI Nativo):**
   - Arquivo: [revisao_classificacao.html](file:///C:/Projetos/LOGOS/LogosPostos/WebPosto_API/static/revisao_classificacao.html) servido na rota `/revisao`.

Ambas as telas exibem:
- Metadados completos da transação (empresa, conta, data, valor formatado e descrição);
- Evidências sanitizadas (`[REDACTED]`);
- Sugestões da IA, percentual de confiança e justificativa;
- Badges de travas impeditivas ativas;
- Seletor dinâmico restrito exclusivamente a planos folha oficiais válidos;
- Trilha auditável de eventos em tempo real;
- Banner de governança atestando `ERP WRITES = ZERO`.

---

## 4. Controles e Salvaguardas

- **Rejeição Categórica da Conta 198966:** Validação no frontend e backend bloqueia qualquer tentativa de definir a conta temporária 2.04.10 como plano definitivo.
- **Isolamento de Dados de Produção:** Banco operacional `master_data.sqlite3` mantido estritamente limpo de dados fictícios (`COUNT = 0`). Todos os testes utilizam bancos temporários isolados (`tmp_path`).
- **Conta 27173 e Allowlist:** Intocadas (débito despesa permanece bloqueado; allowlist `{17837}`).
- **Zero Mutações ERP:** Nenhuma chamada `POST`, `PUT`, `PATCH` ou `DELETE` ao webPosto.

---

## 5. Testes e Validação

- 27 testes unitários e de integração em `WebPosto_API/tests/unit/classification_review/` (14 de serviço/domínio + 13 de API/segurança).
- 151 testes na suíte global passando 100% sem falhas.
