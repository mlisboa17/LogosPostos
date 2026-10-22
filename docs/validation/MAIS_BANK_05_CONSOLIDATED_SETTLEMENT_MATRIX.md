# MAIS-BANK-05 — Matriz Consolidada de Liquidação, Custódia e Repasses

**Data:** 22/10/2026  
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Prioridade:** P0 — Governança Financeira e Prova de Liquidação  
**Ambiente:** Validação 100% Offline (Zero chamadas externas, zero escritas no ERP)  
**Veredito Consolidado:** **CADEIA MAIS PAGAMENTOS: BLOCKED (TODAS AS UNIDADES)**  

---

## 1. Contexto e Objetivo da Consolidação

Esta auditoria consolida e confronta os relatórios técnicos preliminares:
- [MAIS_BANK_01_SOURCE_GAP_MATRIX.md](MAIS_BANK_01_SOURCE_GAP_MATRIX.md) (Matriz de fontes e lacunas)
- [MAIS_BANK_02_SETTLEMENT_SOURCES.md](MAIS_BANK_02_SETTLEMENT_SOURCES.md) (Fontes de liquidação e repasse)
- [MAIS_BANK_03_SOURCE_VALIDATION.md](MAIS_BANK_03_SOURCE_VALIDATION.md) (Contas recebedoras, extratos e repasses)
- [MAIS_BANK_04_BALANCE_AND_PAYOUT_MODEL.md](MAIS_BANK_04_BALANCE_AND_PAYOUT_MODEL.md) (Saldo intermediário, repasses e crédito bancário)
- Confronto direto com [STATUS.md](../../STATUS.md), regras de negócio e ADRs arquiteturais vigentes.

O objetivo é estabelecer, sob os princípios **fail-closed** e **anti-presunção**, uma verdade canônica estrita sobre o fluxo financeiro da adquirente Mais Pagamentos, distinguindo categoricamente evidências fáticas auditadas de declarações humanas, suposições técnicas e lacunas documentais.

---

## 2. Taxonomia Rigorosa da Informação

Para evitar que hipóteses de trabalho sejam promovidas a certezas financeiras, todas as afirmações sobre a operação Mais Pagamentos são classificadas segundo a seguinte taxonomia:

1. **Fato Comprovado por Evidência Local:** Dado diretamente extraído de arquivo auditável, extrato OFX local verificado com hash, retorno HTTP sanitizado ou código-fonte testado com mock reproduzível.
2. **Declaração do Proprietário:** Informação transmitida pelo dono/diretor do posto (ex.: "Doze usa Asaas; VIP e Casa Caiada usam Fiserv; 118508 não usa Mais"). Constitui direcionador de investigação e escopo de negócio, mas **NÃO substitui evidência cadastral ou extrato bancário**.
3. **Inferência / Hipótese Técnica:** Raciocínio lógico dedutivo derivado de contratos públicos (ex.: OpenAPI Asaas, Hub SiTef/Fiserv ou enums da Mais Pagamentos). Não autoriza vincular contas, disparar débitos ou assumir conciliação.
4. **Lacuna Documental:** Informação financeira mandatória ausente nos repositórios locais e no ERP (ex.: ausência de chave E2E de saída, código de lote ou agência bancária).
5. **Dependência de Terceiro:** Necessidade de ação externa indispensável (ex.: envio de extrato oficial pelo banco ou abertura de chamado na Quality/Mais Pagamentos para obtenção de credencial read-only).

---

## 3. Delimitação Estrita do Escopo Vigente

Conforme declaração formal do proprietário em 17/10/2026 e ratificada nos documentos 01 a 04:
- **Unidades no Escopo Mais Pagamentos:**
  - **Posto Doze (`empresaCodigo 74014`)**
  - **Posto VIP (`empresaCodigo 11495`, englobando pista e sua conveniência própria)**
  - **Auto Posto Casa Caiada (`empresaCodigo 5555`)**
- **Unidade FORA do Escopo Mais Pagamentos:**
  - **Conveniência 24 Horas (`empresaCodigo 118508`):** Declarado expressamente que **NÃO utiliza Mais Pagamentos**. Quaisquer menções preliminares em rascunhos sobre Asaas/Fiserv/Matera para a filial 118508 estão formalmente declaradas **SUPERADAS E ANULADAS**. Permanece em seus respectivos módulos operacionais padrão sem adquirente Mais.
- **Unidade Histórica / Inativa:**
  - **Posto Real (`empresaCodigo 5558`):** Totalmente inativa e bloqueada para lançamentos e conciliação de adquirentes.

---

## 4. Análise de Contradições e Divergências Entre os Documentos

A comparação minuciosa entre os quatro documentos e o `STATUS.md` revelou e pacificou os seguintes pontos:

| Ponto de Divergência | Apontamento Inicial / Rascunho | Resolução Consolidada / Regra de Ouro |
|---|---|---|
| **Status da Conveniência 24h (118508)** | MAIS-BANK-01/02 preliminares listavam "plataforma desconhecida/pendente". | Retificado em nota formal: **118508 não utiliza Mais Pagamentos**; escopo restrito a 74014, 11495 e 5555. |
| **Papel da Plataforma Matera** | Citada como participante do ecossistema devido ao enum `MATERA` na OpenAPI da Mais. | **Nenhuma unidade possui vínculo com a Matera**. A Matera atua como fornecedora de infraestrutura/BaaS, sem conta bancária ou custódia comprovada para o grupo. |
| **Contas Bancárias de Destino do Repasse** | Tendência a reutilizar as contas cadastradas em `units.json` (ex: BB 86248, Bradesco 65321). | **Proibição expressa**: aquelas contas foram cadastradas para sangrias físicas de dinheiro da pista (espécie); **não há prova documental** de que sejam o destino dos repasses de PIX/cartão Mais. |
| **Diferença Diária vs. Perda Financeira** | Tentativas anteriores de subtrair `PIX do dia - Repasses do dia`. | **MAIS-BANK-04 comprovou**: dinheiro em conta intermediária é **fungível**. Repasses agregados ou retenções de saldo não configuram perda financeira sem extrato e fechamento do período. |
| **Travas de Escrita no ERP** | Suposição de que `WEBPOSTO_WRITES=0` no `.env` bloqueia todas as escritas do projeto. | **MAIS-BANK-03 demonstrou**: o bloqueio físico é rigoroso nos adaptadores de cartão e despesas, mas chamadas brutas via SDK genérico exigem barreira adicional. Operação 100% offline mantida. |

---

## 5. Matriz Consolidada da Cadeia de Liquidação e Repasse

A tabela a seguir apresenta o estado de comprovação em 14 dimensões auditáveis para cada unidade do grupo:

| Dimensão | Posto Doze (`74014`) | Posto VIP (`11495`) | Casa Caiada (`5555`) | Conveniência 24h (`118508`) |
|---|---|---|---|---|
| **1. Unidade** | Posto Doze Filial II | Rio Doce / Posto VIP | Auto Posto Casa Caiada | Conveniência 24 Horas |
| **2. Plataforma Declarada** | Asaas ("Posto Abreu e Lima") | Fiserv | Fiserv | *Nenhuma* (Não utiliza Mais) |
| **3. Produto Operacional** | Cobrança / PIX Gateway | Hub PIX / SiTef | Hub PIX / SiTef | *Fora de escopo* |
| **4. Instituição Executora** | Mais Pagamentos | Mais Pagamentos | Mais Pagamentos | *N/A* |
| **5. Custodiante / PSP** | Asaas Gestão Financeira | Não identificado / Pendente | Não identificado / Pendente | *N/A* |
| **6. Titular da Conta Recebedora** | PENDENTE DE COMPROVAÇÃO | PENDENTE DE COMPROVAÇÃO | PENDENTE DE COMPROVAÇÃO | *N/A* |
| **7. CNPJ da Conta Recebedora** | PENDENTE (ERP: 52.308.604/0002-84) | PENDENTE (ERP: 03.008.754/0001-86) | PENDENTE (ERP: 04.284.939/0001-86) | *N/A* |
| **8. Conta / Subconta Lógica** | `{conta}` lógica não mapeada | `{conta}` lógica não mapeada | `{conta}` lógica não mapeada | *N/A* |
| **9. Regra de Repasse** | Manual / Automático não parametrizado | Manual / Automático não parametrizado | Manual / Automático não parametrizado | *N/A* |
| **10. Evidência de Venda (ERP)** | Documentada em `/V1/VENDAS` | Documentada em `/V1/VENDAS` | Documentada em `/V1/VENDAS` | *N/A* |
| **11. Evidência de Liquidação** | NÃO COMPROVADA (Login Mais 401) | NÃO COMPROVADA (Login Mais 401) | NÃO COMPROVADA (Login Mais 401) | *N/A* |
| **12. Evidência de Crédito Bancário** | NÃO COMPROVADA no banco final | NÃO COMPROVADA no banco final | NÃO COMPROVADA no banco final | *N/A* |
| **13. Nível de Confiança** | BAIXO (Apenas contrato público Asaas) | CRÍTICO (Sem contrato público de conta) | CRÍTICO (Sem contrato público de conta) | *N/A* |
| **14. Status Operacional** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **FORA DE ESCOPO** |

---

## 6. Riscos em Aberto e Impacto na Operação

1. **Risco de Falsa Divergência Contábil:** Tratar a diferença entre vendas PIX capturadas no POS e repasses creditados no banco como "furo de caixa". Em contas BaaS/PSP, o saldo é fungível e repasses podem ocorrer em D+1, D+2, finais de semana acumulados ou reter valores mínimos operacionais.
2. **Risco de Contaminação Inter-Filiais:** Realizar repasses de uma filial para a conta bancária de outra filial sem contrato formal de mútuo ou documento contábil de suporte.
3. **Risco de Confusão com Sangria da Pista:** Utilizar as contas correntes cadastradas para depósito de dinheiro vivo da pista como se fossem as contas oficiais de recebimento de adquirentes eletrônicos.
4. **Risco de Reincidência de Login 401:** Disparar scripts automatizados contra a API da Mais Pagamentos com credenciais desatualizadas ou de escopo inválido, gerando bloqueio temporário por segurança.

---

## 7. Requisitos Mandatórios Antes de Qualquer Desbloqueio

Nenhum módulo automatizado de conciliação Mais Pagamentos poderá ser ativado sem que os seguintes requisitos documentais sejam plenamente satisfeitos:

1. **Mapa Cadastral Assinado:** Matriz oficial fornecida pela gerência contendo: `Unidade` → `CNPJ Titular` → `ID Lógico na Mais` → `Instituição Custodiante (ISPB/Razão)` → `Conta Bancária Final de Destino`.
2. **Pacote de Evidências Sanitizadas (Piloto Doze):**
   - Amostra real de 1 venda PIX do dia 14/10/2026 com ID da transação e código E2E.
   - Extrato analítico oficial da conta intermediária (Asaas) do período 14/10 a 16/10/2026 demonstrando a entrada do crédito e o eventual débito de repasse com taxa.
   - Extrato bancário oficial (OFX/PDF) da conta de destino final comprovando o recebimento do crédito correspondente.
3. **Credencial de Integração Read-Only Formal:** Obtenção junto à Quality Automação ou Mais Pagamentos de chave de integração dedicada exclusivamente a leitura (`GET`), com endpoints e scopes validados.

---

## 8. Veredito e Próximos Passos

- **STATUS CONSOLIDADO:** **BLOCKED** para todas as unidades no módulo Mais Pagamentos.
- **ACCOUNT 27173 (CASA CAIADA):** **BLOCKED** (preservada estritamente como `TRANSITORIA` no Master Data local).
- **PILOTO CASA CAIADA:** **BLOCKED** (zero escritas no ERP, aguardando decisão deliberada do diretor).
- **ESCRITAS NO ERP:** **ZERO (0)**.
- **CHAMADAS EXTERNAS:** **ZERO (0)**.
