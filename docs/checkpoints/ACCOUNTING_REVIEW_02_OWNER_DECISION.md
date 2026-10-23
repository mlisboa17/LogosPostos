# CHECKPOINT — LOGOS ACCOUNTING-REVIEW-02

## Decisão do proprietário sobre o movimento de R$ 626,00

**Data:** 23/10/2026  
**Empresa:** `5555 — AP CASA CAIADA`  
**Conta:** `27173 — Banco do Brasil`  
**Operação:** saída de conta (`DEBITO`)  
**Classificação:** `29021 — PRO LABORE`  
**Histórico:** `PRÓ-LABORE — MÁRCIO`

## Decisão expressa

O proprietário esclareceu que o lançamento não pertence ao Posto Real. Deve ser registrado somente na AP Casa Caiada como pró-labore de Márcio, na forma de movimentação de saída da conta bancária, sem fornecedor.

## Payload offline corrigido

- `filial: 5555`;
- `conta: 27173`;
- `valor: 626.00`;
- `data: 2026-10-10`;
- `descricao: PRÓ-LABORE — MÁRCIO`;
- `planoConta: 29021`;
- `centroCusto: null`;
- `contaMovimentoTipo: DEBITO`;
- `tipoPessoa: NAO_IDENTIFICADO`;
- `pessoa: null`.

O centro de custo fica vazio porque o contrato oficial permite nulo, não existe centro administrativo confirmado no cadastro local e `7295 — PISTA` é bloqueado para pró-labore.

## Preservação da evidência

`Posto Real Ltda` continua registrado somente como recebedor observado no comprovante bancário. Não consta como empresa, fornecedor, pessoa ou descrição do movimento proposto.

## Travas mantidas

- débito da conta `27173` desabilitado;
- conta fora da allowlist de escrita;
- nenhuma chamada ou escrita ERP;
- nenhuma emissão de token;
- execução real ainda não autorizada.

## Validação offline

- JSON validado sintaticamente;
- SHA-256: `4E9E9A8F071AE7A510C29A53918E49CF200578C0FDEC4CF1F44334C013AE8A0C`;
- preparação do piloto + precheck + adaptador de despesas: **61 passed**;
- zero tentativas reais de navegador/portal.

