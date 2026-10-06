# LOGOS Platform Context Map

## 1. Como interpretar este mapa

Este mapa é um **TO-BE de trabalho**, não um inventário certificado do AS-IS. A confirmação ocorrerá por descoberta no código, nas bases de dados, nos fluxos operacionais e na documentação canônica.

Rótulos usados:

- **Comprovado:** sustentado por evidência já observada.
- **A validar:** responsabilidade, ownership, dependência ou integração ainda não confirmada.
- **Candidato:** evento ou contrato proposto; não é contrato oficial.
- **Futuro:** ampliação possível, dependente de nova decisão.

## 2. Contextos de negócio propostos

### 2.1. Identity & Organization

- **Propósito TO-BE:** representar organizações, unidades, usuários e vínculos organizacionais.
- **Responsabilidades/ownership:** **a validar** contra os cadastros e modelos atuais.
- **Dependências candidatas:** Authentication, Authorization e Tenant Management.
- **Eventos candidatos:** `OrganizationCreated`, `BranchActivated`, `UserAssignedToBranch`.
- **Integrações futuras:** diretórios corporativos ou ERPs, somente se justificadas.

### 2.2. Data Integration

- **Propósito TO-BE:** ingerir, normalizar e disponibilizar dados de fontes operacionais.
- **Escopo observado:** a plataforma possui relação operacional com dados do WebPosto; conectores, formatos e ownership precisam de inventário.
- **Responsabilidades/ownership:** logs de ingestão, mapeamentos e equivalências são **candidatos a validar**.
- **Eventos candidatos:** `RawDataIngested`, `IntegrationDataNormalized`, `IngestionFailed`.
- **Integrações candidatas:** sistemas legados, arquivos e APIs efetivamente encontrados; coletores fiscais e planilhas permanecem **a validar**.

### 2.3. Financial Operations

- **Escopo suportado hoje:** revisão financeira, despesas, indicadores e suporte a análises financeiras observadas no produto e nas discussões operacionais.
- **Propósito TO-BE imediato:** organizar regras e dados financeiros necessários aos casos de uso comprovados, com proveniência.
- **Ownership:** **a validar**; não se presume ownership de títulos, fornecedores, plano de contas ou lançamentos sem evidência.
- **Eventos candidatos:** somente após descoberta dos fluxos reais; nomes como `FinancialEntryRecorded` não são contrato oficial.
- **Ampliações futuras:** contas a pagar, contas a receber, liquidações, provisionamentos, faturamento e integração com ERP/gateways dependem de evidência e decisão próprias. Este mapa não define um ERP financeiro completo.

### 2.4. Cash & Reconciliation

- **Escopo suportado hoje:** revisão, auditoria e conciliação de caixa como caso prioritário de valor; detalhes do fechamento real devem ser validados.
- **Propósito TO-BE imediato:** detectar, explicar e acompanhar divergências de caixa com proveniência e isolamento de tenant.
- **Ownership:** fechamentos, divergências e evidências são **candidatos a validar** contra tabelas e fluxos existentes.
- **Eventos candidatos:** `CashShiftClosed`, `ReconciliationCompleted`, `CashDiscrepancyDetected`.
- **Ampliações futuras:** adquirentes, cartões, convênios, VANs, OFX, APIs bancárias e conciliação bancária não são consideradas existentes ou aprovadas sem evidência.

### 2.5. Commercial Intelligence

- **Propósito TO-BE:** analisar vendas, desempenho comercial e indicadores de margem quando sustentados por fontes confiáveis.
- **Ownership e cálculos:** **a validar**, inclusive fonte, granularidade e versão das regras.
- **Eventos candidatos:** `CommercialTargetMissed`, `SalesAnomalyIdentified`.
- **Integrações futuras:** índices de mercado e ferramentas analíticas, mediante decisão.

### 2.6. Inventory & Fuel

- **Propósito TO-BE:** representar estoque e movimentações de combustíveis ou mercadorias nos casos de uso comprovados.
- **Ownership:** leituras de tanque, descargas, arqueação, sobras e faltas estão **a validar**.
- **Eventos candidatos:** `FuelDeliveryReceived`, `TankMeasurementRecorded`, `PhysicalInventoryVarianceDetected`.
- **Integrações futuras:** telemetria de tanques, como Veeder-Root, somente após confirmação de escopo.

### 2.7. Fiscal & Compliance

- **Propósito TO-BE:** tratar evidências e verificações fiscais necessárias aos fluxos comprovados.
- **Ownership:** documentos, metadados e inconsistências fiscais permanecem **a validar**.
- **Eventos candidatos:** `FiscalInvoiceMissing`, `TaxDiscrepancyFlagged`.
- **Integrações futuras:** SEFAZ, guardas de XML e outros provedores dependem de evidência e análise regulatória/técnica.

### 2.8. Audit & Loss Prevention

- **Propósito TO-BE:** consolidar achados, evidências e acompanhamento de perdas ou desvios.
- **Escopo observado:** auditoria e prevenção de perdas são direções relevantes; modelos de caso e ownership ainda exigem validação.
- **Eventos candidatos:** `AuditAlertTriggered`, `LossPreventionCaseOpened`.
- **Consumos candidatos:** divergências de caixa, estoque, fiscal ou evidências do Vision, após contratos aprovados.
- **Integração com Vision:** **a validar**; não se presume hoje barramento ou transporte específico.

### 2.9. Decision Intelligence

- **Propósito TO-BE:** orquestrar recomendações, intervenções e outcomes por meio de `DecisionCase`.
- **Ownership:** registros de decisão, recomendações, ações e outcomes são candidatos; o esquema será definido após ARCH-01.
- **Eventos candidatos:** `DecisionRecommended`, `DecisionInterventionLogged`, `DecisionOutcomeRecorded`.
- **Integrações futuras:** modelos analíticos ou de IA por meio de mecanismos aprovados e observáveis.

## 3. Platform Services e status

Os status abaixo descrevem a maturidade documental atual, não uma garantia de cobertura funcional. Devem ser confirmados durante a canonicalização e o inventário técnico.

| Capability transversal | Status | Leitura atual |
|---|---|---|
| Authentication | `partial` | Algum mecanismo é esperado em uma aplicação operacional; implementação e cobertura precisam ser inventariadas. |
| Authorization | `partial` | Regras podem existir, mas RBAC/ABAC formal e cobertura não estão confirmados. |
| Tenant Management | `partial` | O requisito é aprovado; garantias estruturais do AS-IS ainda precisam de evidência. |
| Audit Trail | `partial` | Há necessidade de auditoria; imutabilidade, cobertura e before/after não são presumidos. |
| Notifications | `conceptual` | Canais, provedores e casos de uso não foram confirmados. |
| Observability | `partial` | Logs podem existir; métricas, traces e correlação ponta a ponta estão a validar. |
| AI Gateway | `planned` | Direção possível para governança de modelos; não se declara serviço existente. |
| Feature Flags | `conceptual` | Estratégia e ferramenta não aprovadas. |
| Data Provenance | `planned` | Requisito aprovado para valores sensíveis; implementação permanece pendente. |

Valores permitidos: `existing`, `partial`, `planned`, `conceptual`. `existing` só deverá ser usado após evidência suficiente de implementação e operação.

## 4. Regras de evolução do mapa

1. Promover um item de **candidato/a validar** para oficial somente com evidência e decisão no Git.
2. Não criar contrato de evento ou integração apenas para completar simetria documental.
3. Registrar owner de dados apenas após verificar escrita, fonte de verdade e responsabilidades operacionais.
4. Atualizar este mapa quando um slice vertical revelar fronteiras reais diferentes das propostas.
5. Tratar divergências como aprendizado arquitetural, não como motivo para ocultar o AS-IS.
