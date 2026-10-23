# CHECKPOINT — LOGOS PLANOS-CONTA-MASTER-01

## Catálogo mestre compartilhado de planos de conta

**Data:** 23/10/2026  
**Fonte:** `GET /INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL`  
**Escopo:** compartilhado entre todas as empresas  
**Modo:** somente leitura  
**Escritas ERP:** zero

## Resultado

- 251 planos gerenciais oficiais;
- 28 contas pai não lançáveis diretamente;
- 223 folhas estruturais candidatas a lançamento;
- catálogo local anterior com 200 códigos;
- 51 códigos oficiais ausentes no catálogo local anterior;
- zero códigos locais ausentes no retorno oficial.

O endpoint `PLANOS_CONTA_CONTABIL` respondeu HTTP 200, mas retornou zero registros para a credencial utilizada. O catálogo gerencial é o necessário para `MOVIMENTOS_CONTA`.

## Hierarquia de pró-labore relevante

```text
29021 — 2.02 — PRO LABORE [PAI]
└── 148303 — 2.02.05 — MARCIO LISBOA [PAI]
    ├── 148304 — 2.02.05.001 — MARCIO CARRO [FOLHA]
    ├── 148305 — 2.02.05.002 — BOLETO PAGO CC EMPRESA [FOLHA]
    ├── 148306 — 2.02.05.003 — TRANSFERENCIAS P CONTA PF [FOLHA]
    ├── 148307 — 2.02.05.004 — CARTAO EMPRESA [FOLHA]
    └── 158764 — 2.02.05.005 — MARCIO-PROLABORE [FOLHA]
```

Para a descrição autorizada `PRÓ-LABORE — MÁRCIO`, o código oficial correspondente é `158764 — MARCIO-PROLABORE`. Este código foi apenas identificado; não houve nova tentativa de escrita.

## Artefatos

- [PLANOS_CONTA_MASTER_01.json](../validation/PLANOS_CONTA_MASTER_01.json)
- [PLANOS_CONTA_MASTER_01.md](../validation/PLANOS_CONTA_MASTER_01.md)
- Coletor reproduzível: `WebPosto_API/scripts/mapear_planos_conta_v1.py`

SHA-256 do catálogo: `BDF68D4F690249A70B69424C0B9FA237C09704FE8D6EF258E37DABC1D0CD8C57`.

## Governança

`ehFolhaEstrutural` e `candidatoLancavel` são derivados exclusivamente da hierarquia oficial. Uma folha ainda pode ser recusada por outras regras do ERP. Pais nunca devem ser enviados como plano de lançamento.

