# LOGOS Platform Architecture Directive

## 1. Escopo

Esta diretiva define a direção TO-BE da plataforma LOGOS e as regras de governança da migração. Ela não certifica que o código atual já cumpra essas regras.

### Classificação obrigatória

- **AS-IS comprovado:** evidência no código, repositório, documentação canônica ou operação.
- **TO-BE aprovado:** decisão arquitetural aceita, ainda a implementar ou validar.
- **Hipótese futura:** opção não aprovada ou dependente de descoberta.

> AS-IS comprovado, TO-BE aprovado e hipótese futura devem ser explicitamente diferenciados. Nenhum contrato, evento, integração, tabela ou responsabilidade pode ser apresentado como existente ou definitivo sem evidência no código, documentação canônica ou validação operacional.

## 2. Visão da plataforma — TO-BE aprovado

A LOGOS evoluirá de aplicações predominantemente operacionais para uma plataforma de governança operacional, conciliação, prevenção de perdas e suporte à decisão, com dados auditáveis e proveniência verificável.

## 3. Princípios de governança

- **Autoridade canônica:** toda decisão arquitetural relevante deve existir no Git antes de ser considerada oficial. Conversas, minutas e sessões de IA são preparatórias.
- **Migração orientada a valor:** código novo segue o TO-BE; legado só migra com benefício concreto, risco controlado e escopo delimitado.
- **Parcimônia estrutural:** não antecipar partições físicas, serviços distribuídos, eventos ou integrações sem evidência.
- **Pragmatismo:** `REUSE > ADAPT > CREATE`.
- **Evidência sobre suposição:** divergências entre documentação e realidade operacional devem reabrir a decisão e gerar atualização no Git.

## 4. Padrão arquitetural — TO-BE aprovado

A topologia padrão é um **modular monolith** organizado por verticais de domínio.

### 4.1. Módulos verticais

- Cada módulo deve encapsular lógica de aplicação, domínio e adaptadores relacionados ao seu contexto.
- Interfaces públicas entre módulos devem ser explícitas.
- Acesso direto à persistência privada de outro módulo deve ser impedido progressivamente.
- Chamadas locais tipadas e eventos são mecanismos candidatos de comunicação; a escolha depende do caso de uso.
- Ownership claro e independência de persistência são propriedades desejadas do TO-BE. O AS-IS precisa ser inventariado antes que qualquer isolamento seja declarado existente.

### 4.2. Boy Scout Rule controlada

- Melhorias ficam restritas aos arquivos e fluxos tocados pela entrega em curso.
- Refatoração oportunista que altere comportamento externo exige testes e justificativa.
- Mudança estrutural no legado deve estar vinculada a item de trabalho com benefício e risco descritos.
- Limpeza adjacente não pode ampliar silenciosamente o escopo nem atrasar o objetivo principal.
- Se a melhoria revelar uma decisão arquitetural nova, ela deve ser documentada e canonicalizada no Git.

## 5. Fronteiras e comunicação

### 5.1. Fronteiras de domínio

As fronteiras do Context Map são uma proposta de trabalho. A confirmação de responsabilidades, ownership e dependências exige confronto com código, dados e operação.

### 5.2. Domain Events

- Eventos devem possuir contratos explícitos, versionamento e semântica clara.
- A emissão deve ser confiável e observável conforme a criticidade do fluxo.
- Imutabilidade do fato publicado é uma propriedade desejada; correções devem gerar novos fatos, não reescrever fatos consumidos.
- Garantias transacionais, persistência, idempotência, retry, ordenação, auditoria e eventual uso de outbox serão definidas por caso de uso.
- Não se presume que os eventos atuais sejam transacionais, auditáveis ou confiáveis sem validação técnica.
- Os nomes listados no Context Map são candidatos, não contratos oficiais do ARCH-02.

### 5.3. Hunters

Cash Hunter, Expense Hunter e outros Hunters são capabilities analíticas e operacionais que usam os bounded contexts relevantes. Não formam módulos de domínio independentes por padrão.

## 6. Diretrizes transversais — TO-BE aprovado

### 6.1. Tenant isolation

- Toda operação de leitura, escrita e publicação deve carregar e validar contexto de tenant.
- Consultas ou mutações sem escopo explícito de tenant são proibidas no TO-BE.
- A implementação concreta e as lacunas do AS-IS deverão ser verificadas no ARCH-02 e nos slices subsequentes.

### 6.2. Data provenance

Valores financeiros calculados, conciliados ou exibidos para decisão devem referenciar origem, instante de ingestão/processamento, identificador de execução e versão da regra, quando aplicável.

### 6.3. Decision flow

`DecisionCase` é a direção aprovada para registrar detecção, hipótese, recomendação, intervenção e outcome. Seu esquema e contratos permanecem fora do ARCH-01.

### 6.4. LOGOS Vision

O Vision deverá ser isolado operacionalmente quando seu perfil de CPU, memória, GPU, streaming, deploy ou falha puder afetar o núcleo transacional. A integração TO-BE será por contratos explícitos de evidência/findings. A topologia concreta será validada em `VISION-INTEGRATION-01`; não se presume hoje um barramento, transporte ou contrato específico.

## 7. Extração de serviços

O modular monolith permanece o padrão. A extração de um módulo exige ADR e evidência de ao menos um gatilho relevante:

1. hardware especializado;
2. escala ou carga desproporcional;
3. cadência de deploy independente por necessidade operacional;
4. isolamento de falhas para proteger o core;
5. segregação regulatória ou de segurança.

A existência de uma fronteira conceitual, por si só, não justifica um microserviço.
