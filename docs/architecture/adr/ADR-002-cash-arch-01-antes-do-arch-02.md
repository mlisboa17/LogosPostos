# ADR-002: CASH-ARCH-01 (Conciliação de Espécie) antes do ARCH-02

## Status

**Accepted — 2026-10-06** (aprovado pelo responsável do produto em sessão de trabalho; oficial após merge na `main` de `mlisboa17/LogosPostos`).

Decisão complementar do ARCH-01: o repositório canônico é `mlisboa17/LogosPostos`, branch `main`, com checkout de trabalho em `C:\Projetos\LOGOS\LogosPostos` (fora do OneDrive).

## Context

`CURRENT_ARCHITECTURE_STATE.md` § 9 define a sequência ARCH-01 → ARCH-02 (Platform Contracts v0) → CASH-ARCH-01. O ARCH-02 ainda não foi iniciado.

Entretanto, a conciliação de espécie passou a ter **evidência operacional real** (2026-10-06):

| Item | Evidência | Classificação |
|---|---|---|
| `GET /INTEGRACAO/V1/SANGRIAS_CAIXA` | Spec oficial (`docs/external/webposto/`) + sondagem em produção nas unidades 74014, 11495, 5555, 118508: 25 campos idênticos à spec, paginação por cursor `ultimoCodigo` | AS-IS comprovado |
| `contaCodigo` da sangria = destino do dinheiro | Mapeado via `V1/CONTAS` (ex.: 86248 "BANCO 24H - DOZE FILIAL", 86081 "CAIXA(POSTO)") | AS-IS comprovado |
| Extratos OFX (BB, Bradesco, Itaú) | Arquivos de set/2026 fornecidos pelo negócio; depósitos em espécie identificáveis por histórico/terminal/hora | AS-IS comprovado |
| Casamento sangria × depósito | Protótipo: 96% das sangrias "BANCO 24H" do Doze (set/2026) casadas por valor + hora | Evidência de viabilidade |
| Conta webPosto "CAIXA(POSTO)" como espelho do cofre | Saldo negativo (−R$ 1,02 mi) e sem depósitos registrados | **Refutado** — não usar como fonte de verdade do cofre |

`LOGOS_CONTEXT_MAP.md` § 2.4 tratava OFX e conciliação bancária como não existentes "sem evidência". Pela regra § 4.1 do mapa, a evidência acima promove esses itens no contexto **Cash & Reconciliation**.

## Decision

1. Executar **CASH-ARCH-01 — Conciliação de Espécie (Sangria × Extrato)** como primeiro slice vertical, antes do ARCH-02.
2. O slice vive em `WebPosto_API/src/modules/cash_reconciliation/` (módulo vertical: `domain`, `rules`, `adapters`, `application`, `config`).
3. Contratos de tenant e proveniência são **locais ao módulo** (v0), mínimos e explícitos: unidade (`empresaCodigo`) obrigatória em toda operação; todo resultado carrega `Proveniencia` (fontes, hash dos extratos, instante, id de execução, versão da regra). O ARCH-02 deverá absorver ou substituir esses contratos com base no que o slice revelar.
4. Regras de casamento são versionadas (`SANGRIA_DEPOSITO_V1`); qualquer mudança gera nova versão.
5. O saldo do cofre é calculado como `sangrias para cofre − depósitos em espécie no extrato`, **não** a partir da conta "CAIXA(POSTO)" do webPosto.

## Consequences

- Entrega valor de auditoria antes da formalização dos contratos de plataforma.
- Risco de retrabalho controlado: contratos locais pequenos, isolados no módulo.
- Extratos e dados reais **nunca** entram no repositório; testes usam fixtures sintéticos.
- Chaves webPosto são por unidade, lidas de variáveis de ambiente indicadas em configuração (nome da variável, nunca o valor). Ver `security/ARCH01_SECRET_AUDIT_RUNBOOK.md`.

## Alternatives considered

- **Esperar o ARCH-02:** mantém a sequência, mas adia o caso de maior valor e define contratos sem evidência (contraria "evidência sobre suposição").
- **Usar a conta "CAIXA(POSTO)" do webPosto como cofre:** refutado pelos dados.
