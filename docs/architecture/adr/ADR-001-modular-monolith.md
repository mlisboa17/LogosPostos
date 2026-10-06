# ADR-001: Adoção de Modular Monolith como Arquitetura Padrão

## Status

**Accepted — pending ARCH-01 repository canonicalization**

Esta decisão somente se torna oficial após ser registrada no repositório e branch canônicos.

## Context

A LOGOS evolui de uma aplicação orientada a integrações e tarefas operacionais para uma plataforma com inteligência financeira, conciliação, auditoria e suporte à decisão.

No levantamento que originou o ARCH-01, `NewWebLogos` foi observado vazio no GitHub, enquanto a base operacional relevante foi localizada em `API_WEBPOSTO`, organizada predominantemente por camadas técnicas. A definição do repositório canônico permanece pendente.

Microserviços imediatos adicionariam infraestrutura, falhas parciais, contratos de rede, observabilidade distribuída e coordenação de deploy sem evidência de benefício proporcional. Uma reescrita integral elevaria o risco operacional. Ao mesmo tempo, manter o acoplamento horizontal sem fronteiras prejudicaria a evolução dos domínios.

## Decision

Adotar **modular monolith**, com divisão vertical progressiva por bounded contexts, como arquitetura padrão do LOGOS.

1. Novas funcionalidades devem respeitar módulos e interfaces explícitas.
2. O legado será migrado gradualmente, orientado por benefício concreto e pela Boy Scout Rule controlada.
3. Não haverá reescrita big-bang.
4. Não haverá microserviços prematuros.
5. Workloads com hardware, escala, deploy ou isolamento de falha incompatíveis com o core poderão ser isolados mediante evidência e decisão registrada. O LOGOS Vision é o principal candidato, mas transporte e contratos permanecem a definir.
6. Ownership e independência de persistência são metas do TO-BE; não se declara que já existam no AS-IS.

## Alternatives considered

### Manter o monólito horizontal atual

- **Vantagem:** menor esforço imediato.
- **Desvantagem:** amplia acoplamento e dificulta governança de dados e evolução por domínio.

### Microserviços imediatos

- **Vantagem:** isolamento físico potencial.
- **Desvantagem:** sobrecarga operacional e distribuída sem demanda comprovada.

### Reescrita completa

- **Vantagem:** oportunidade de desenho limpo.
- **Desvantagem:** risco, atraso de valor e perda de conhecimento operacional.

### Multi-repo por domínio

- **Vantagem:** versionamento independente.
- **Desvantagem:** maior atrito de contratos, CI/CD, descoberta e refatoração durante a fase atual.

## Consequences

### Positivas

- Deploy e operação mais simples no curto e médio prazo.
- Fronteiras explícitas permitem aprender com o legado antes de distribuir o sistema.
- Transações locais continuam disponíveis quando justificadas pelo caso de uso.
- Extrações futuras podem ocorrer de forma seletiva se o TO-BE de ownership e contratos for efetivamente alcançado.

### Negativas e desafios

- Exige disciplina para evitar importações e acessos de dados indevidos.
- Requer inventário progressivo do AS-IS e testes de arquitetura.
- Build e deploy compartilhados podem afetar módulos não relacionados.
- Serviços transversais podem se tornar pontos de acoplamento se não tiverem escopo claro.

## Risks and mitigations

- **Violação de fronteiras:** validar dependências no CI à medida que os módulos forem definidos.
- **Falsa independência de dados:** mapear writers, readers, migrations e fonte da verdade antes de declarar ownership.
- **Contratos prematuros:** manter eventos e integrações como candidatos até o ARCH-02 e os slices relevantes.
- **Deploy compartilhado:** investir em testes de contratos e regressão nos pontos críticos.

## Reversibility

A decisão é reversível, mas a facilidade de extração dependerá de propriedades ainda a construir: interfaces estáveis, baixo acoplamento, ownership claro e independência de persistência. Essas propriedades pertencem ao TO-BE e serão verificadas antes de qualquer extração; não são características presumidas do AS-IS.

## Triggers for reconsideration

Uma extração será avaliada por ADR quando houver evidência de um ou mais gatilhos:

1. hardware especializado, como GPU ou streaming intensivo;
2. escala ou concorrência desproporcional ao restante da plataforma;
3. cadência de deploy independente por requisito operacional ou contratual;
4. isolamento de falhas necessário para proteger o core;
5. segregação regulatória ou de segurança;
6. custo demonstrável menor do que a operação no modular monolith.

## Canonicalization gate

Antes de considerar este ADR oficial:

- confirmar repositório e branch canônicos;
- revisar a decisão com responsáveis técnicos e operacionais;
- confirmar que nenhum segredo foi incluído no pacote;
- registrar este ADR e os documentos relacionados no Git;
- vincular a revisão humana e eventuais ressalvas ao commit ou pull request.
