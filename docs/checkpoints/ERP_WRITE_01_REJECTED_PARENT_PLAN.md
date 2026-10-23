# CHECKPOINT — LOGOS ERP-WRITE-01

## Tentativa única rejeitada pelo webPosto — plano pai

**Data:** 23/10/2026  
**Empresa:** `5555 — AP CASA CAIADA`  
**Conta:** `27173 — Banco do Brasil`  
**Valor:** `R$ 626,00`  
**Data do movimento:** `10/10/2026`  
**Descrição:** `PRÓ-LABORE — MÁRCIO`  
**Plano enviado:** `29021 — PRO LABORE`  
**Centro de custo:** `7295 — PISTA`

## Resultado

Antes do envio, a consulta `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA` retornou zero movimentos para a conta/data e zero possíveis duplicatas de R$ 626,00. O histórico local de idempotência também não possuía operação anterior.

Foi realizada uma única tentativa autorizada de `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`. O webPosto respondeu HTTP 400 e recusou a operação antes de criar o movimento:

> Movimentação financeira não pode ser alterada porque o plano de conta atual é pai. Ele deve ser filho. Plano de Conta Gerencial: PRO LABORE - 2.02.

Não houve repetição automática.

## Confirmação posterior

- Nova consulta somente leitura: zero movimentos e zero correspondências de R$ 626,00.
- Idempotência local: `FALHOU_SEM_ENVIO`, sem ID ERP.
- Token individual: consumido e não reutilizável.
- Allowlist em código: restaurada para `{17837}`.
- Arquivo temporário de liberação: removido.
- SQLite Master Data: débito da conta `27173` continua desabilitado.

## Estado

- **Movimento criado no ERP:** NÃO.
- **Mutação persistida no ERP:** ZERO.
- **Nova tentativa autorizada:** NÃO.
- **Bloqueio atual:** é necessário identificar no cadastro oficial do webPosto uma conta filha válida sob `PRO LABORE - 2.02`.

O catálogo local conhece apenas `29021 — PRO LABORE` e não contém filho comprovado. Nenhum código substituto foi inferido.

SHA-256 da simulação atualizada: `3177B6A81864139561319B71735BA6B76704CCDDCDB8F2B9D5B6CA3444D8BF04`.

