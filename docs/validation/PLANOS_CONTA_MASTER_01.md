# PLANOS-CONTA-MASTER-01 — Catálogo Gerencial Compartilhado

**Fonte:** `GET /INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL`  
**Modo:** somente leitura  
**Compartilhado entre empresas:** sim  
**Escritas ERP:** zero  
**SHA-256 do catálogo JSON:** `BDF68D4F690249A70B69424C0B9FA237C09704FE8D6EF258E37DABC1D0CD8C57`

## Resumo

- Planos oficiais: **251**
- Contas pai: **28**
- Folhas estruturais candidatas a lançamento: **223**
- Códigos no catálogo local anterior: **200**
- Códigos oficiais ausentes localmente: **51**
- Códigos locais ausentes no retorno oficial: **0**

`candidatoLancavel` significa apenas que o item é folha na árvore. A aceitação final continua dependente das demais validações do ERP.

## PRO LABORE

Filhos diretos encontrados sob a conta pai oficial:

- `29044` — `2.02.01` — RETIRADA SOCIOS
- `39370` — `2.02.02` — SR. MOISES
- `47654` — `2.02.03` — MONICA LISBOA
- `49982` — `2.02.04` — DESPESAS DONA ELIANE
- `148303` — `2.02.05` — MARCIO LISBOA

### Folhas sob `148303 — MARCIO LISBOA`

- `148304` — `2.02.05.001` — MARCIO CARRO
- `148305` — `2.02.05.002` — BOLETO PAGO CC EMPRESA
- `148306` — `2.02.05.003` — TRANSFERENCIAS P CONTA PF
- `148307` — `2.02.05.004` — CARTAO EMPRESA
- `158764` — `2.02.05.005` — MARCIO-PROLABORE

Para o caso `PRÓ-LABORE — MÁRCIO`, a correspondência literal encontrada é `158764 — MARCIO-PROLABORE` (`2.02.05.005`). Ela é folha estrutural no retorno oficial. Nenhuma escrita foi realizada com esse código.

## Artefato completo

- [PLANOS_CONTA_MASTER_01.json](PLANOS_CONTA_MASTER_01.json)
