# Current Architecture State — LOGOS Platform

## 1. Finalidade e regra de leitura

Este documento registra o baseline do ARCH-01 sem transformar decisões ou possibilidades em fatos. Cada afirmação relevante é classificada como:

- **AS-IS comprovado:** sustentado por evidência observável no código, no repositório, em documentação canônica ou em validação operacional.
- **TO-BE aprovado:** direção arquitetural aceita, ainda sujeita à implementação e à verificação.
- **Hipótese futura:** possibilidade que depende de descoberta, evidência ou nova decisão registrada no Git.

Nenhum contrato, evento, integração, tabela ou ownership de dados deve ser tratado como existente ou definitivo sem evidência correspondente.

## 2. AS-IS comprovado

- O repositório anteriormente catalogado como principal, `NewWebLogos`, foi observado vazio no GitHub no levantamento que originou este baseline.
- A base de código operacionalmente relevante observada reside primariamente em `API_WEBPOSTO`.
- `API_WEBPOSTO` apresenta separação técnica em camadas, incluindo `api`, `application`, `domain`, `infrastructure`, `interfaces`, `presentation` e `shared`.
- Foi observada a presença de arquivo `.env` rastreado no histórico ou branch de `API_WEBPOSTO`. O conteúdo, o alcance da exposição e o estado atual das credenciais ainda precisam ser classificados pelo runbook de segurança.
- O LOGOS Vision utiliza ou prevê dependências e cargas específicas de visão computacional, como OpenCV, YOLO, RTSP e possível uso de GPU. O grau atual de acoplamento com o core deve ser verificado no código e na operação.

## 3. TO-BE aprovado

- **Direção estratégica:** governança top-down com migração bottom-up.
- **Topologia alvo:** modular monolith organizado por verticais de domínio.
- **Migração:** sem reescrita big-bang e sem microserviços prematuros.
- **Prioridade de implementação:** `REUSE > ADAPT > CREATE`.
- **Código novo:** segue o TO-BE e contratos explícitos entre módulos.
- **Legado:** migra somente quando houver benefício concreto, risco controlado e escopo delimitado.
- **Hunters:** são capabilities de negócio/produto, não bounded contexts ou silos arquiteturais independentes.
- **Dados financeiros:** todo valor calculado ou transformado deve possuir proveniência verificável.
- **Multi-tenancy:** o isolamento de tenant deve ser estrutural na persistência e no ciclo de execução.
- **DecisionCase:** será a espinha dorsal informacional do ciclo de decisão e outcome; seu modelo detalhado será definido em trabalho posterior, sem antecipar contratos do ARCH-02.
- **Vision:** deve ser isolado operacionalmente quando necessário para proteger o núcleo transacional, integrando-se por contratos explícitos de evidência/findings.
- **Persistência:** ownership claro e independência de persistência entre módulos são propriedades desejadas do TO-BE; não são presumidas no AS-IS.

## 4. Hipóteses e validações pendentes

- Se `API_WEBPOSTO` será o repositório canônico definitivo ou se haverá unificação/migração para `NewWebLogos`.
- Se o `.env` histórico contém ou conteve credenciais reais, ativas, remotamente expostas ou com risco residual.
- Quais tabelas e fluxos pertencem efetivamente a cada domínio e qual é o nível de acoplamento do legado.
- Quais eventos, integrações e contratos do Context Map serão confirmados por evidência.
- Capacidade, assertividade, volume e requisitos reais de hardware do pipeline Vision.
- Necessidade futura de integrações com adquirentes, VANs, bancos, OFX, ERPs, SEFAZ, telemetria ou provedores analíticos.

## 5. Riscos abertos

- **Segurança:** possíveis credenciais ou chaves ainda válidas no histórico Git.
- **Governança:** ambiguidade entre repositórios e branches de referência.
- **Acoplamento oculto:** dependências cruzadas, inclusive via `shared`, ainda não inventariadas.
- **Contaminação de domínio:** regras financeiras, fiscais ou de conciliação acopladas ao processamento de visão.
- **Falsa precisão arquitetural:** assumir ownership, eventos ou integrações antes de validar o comportamento real.

## 6. Gate atual

**ARCH-01 — Governance & Safety Baseline**

- Auditar e conter segredos do repositório.
- Definir formalmente repositório e branch canônicos.
- Revisar este pacote com responsáveis técnicos e operacionais.
- Registrar o baseline aprovado no Git.

> **Regra de ouro:** toda decisão arquitetural relevante deve existir no Git antes de ser considerada oficial. Enquanto este pacote não estiver no repositório canônico, ele é uma versão pronta para canonicalização, não a fonte oficial.

## 7. Próxima execução

**ARCH-02 — Platform Contracts v0**, após conclusão do ARCH-01. O ARCH-02 deverá definir contratos canônicos de tenant, identidade, eventos base, auditoria e linhagem. Este baseline não cria código de produção nem contratos Pydantic antecipadamente.

## 8. Non-negotiables

1. `REUSE > ADAPT > CREATE`.
2. No big-bang rewrite.
3. No premature microservices.
4. New code follows TO-BE.
5. Legacy migrates only when justified.
6. Hunters are capabilities, not architectural silos.
7. Financial numbers require provenance.
8. Tenant isolation is structural.
9. Real operational evidence over synthetic assumptions.
10. AS-IS, TO-BE e hipóteses futuras permanecem explicitamente separados.

## 9. Contexto para retomada

```yaml
Architecture Direction: Hybrid — Top-Down Governed, Bottom-Up Migrated
Current Gate: ARCH-01 — Governance & Safety Baseline
Canonical Status: Pending repository and branch canonicalization
Approved Sequence:
  - ARCH-01: Governance & Safety Baseline
  - ARCH-02: Platform Contracts v0
  - CASH-ARCH-01: First Vertical Slice
  - CASH-HUNTER-01: Cash Hunter Operationalization
  - FIN-ARCH-01: Financial Core Alignment
  - DECISION-01: Decision Management & Outcome Loop
  - EXPENSE-HUNTER-01: Expense Hunter Operationalization
  - VISION-INTEGRATION-01: Vision Evidence Contracts & Decoupled Integration
Non-Negotiables:
  - REUSE > ADAPT > CREATE
  - No big-bang rewrite
  - No premature microservices
  - New code follows TO-BE
  - Legacy migrates only when justified
  - Hunters are capabilities, not architectural silos
  - Financial numbers require provenance
  - Tenant isolation is structural
  - Real operational evidence over synthetic assumptions
```
