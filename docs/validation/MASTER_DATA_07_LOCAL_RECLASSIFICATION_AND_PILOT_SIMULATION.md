# MASTER-DATA-07 — Reclassificação local e simulação do piloto Casa Caiada

**Data:** 23/10/2026  
**Autorização:** expressa do proprietário nesta conversa  
**Escopo autorizado:** cadastro SQLite local e simulação offline  
**Escrita ERP:** não autorizada e não executada

## Reclassificação efetivada

A conta `27173` foi atualizada no `master_data.sqlite3` por meio do repositório já existente, dentro de transação atômica e com trilha append-only:

- empresa: `5555`;
- descrição: `BANCO DO BRASIL (56816-3)`;
- tipo: `CONTA_CORRENTE`;
- banco: `001 — Banco do Brasil S.A.`;
- agência: `2365-5`;
- conta: `56816-3`;
- ativa: sim;
- confiabilidade: `CONFIRMADO`;
- débito de despesas: **desabilitado** (`0`).

Auditoria criada: `audit_id 235`, ação `ATUALIZACAO`, origem `AUTORIZACAO_EXPRESSA_PROPRIETARIO_MASTER_DATA_07`. Antes da atualização foi criado backup local recuperável do SQLite.

## Simulação completa do lançamento

Artefato versionado: [`MASTER_DATA_07_PILOT_SIMULATION.json`](MASTER_DATA_07_PILOT_SIMULATION.json).  
SHA-256 após registro da tentativa rejeitada: `3177B6A81864139561319B71735BA6B76704CCDDCDB8F2B9D5B6CA3444D8BF04`.

```json
{
  "descricao": "PRÓ-LABORE — MÁRCIO",
  "data": "2026-10-10",
  "valor": 626.00,
  "conta": 27173,
  "documento": "COMPROVANTE_BB_20261010",
  "centroCusto": null,
  "planoConta": 29021,
  "filial": 5555,
  "contaMovimentoTipo": "DEBITO",
  "tipoPessoa": "NAO_IDENTIFICADO",
  "pessoa": null
}
```

Este payload é uma proposta de `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`; não foi transmitido.

## Decisão posterior do proprietário

Em 23/10/2026, o proprietário determinou que a operação deve ser lançada exclusivamente na AP Casa Caiada como `PRÓ-LABORE — MÁRCIO`, na forma de movimento de saída de conta e sem fornecedor. O nome `Posto Real Ltda` permanece somente como evidência do recebedor no comprovante bancário e não integra a descrição, pessoa ou fornecedor do lançamento.

O contrato OpenAPI `ParametrosIncluirMovimentoConta` exige apenas `descricao`; `centroCusto`, `planoConta` e `pessoa` aceitam nulo. Como nenhum centro administrativo confirmado está cadastrado e o centro `7295 — PISTA` é incompatível com pró-labore, a proposta mantém `centroCusto: null` em vez de inventar um código. O plano `29021 — PRO LABORE` permanece preenchido.

A verificação de duplicidade existente é histórica e local. Antes de qualquer autorização futura de escrita, será necessária nova consulta somente leitura ao ERP para confirmar que o lançamento ainda não existe.

## Barreiras comprovadamente preservadas

- `permite_debito_despesa = 0` no SQLite;
- conta `27173` fora de `CONTAS_AUTORIZADAS_POR_UNIDADE[5555]`;
- nenhuma alteração em `.env` ou nas chaves físicas de escrita;
- nenhum token de autorização emitido;
- nenhuma chamada externa;
- nenhuma escrita ERP;
- piloto real continua `BLOCKED`.

