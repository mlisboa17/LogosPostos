---
name: webposto-api
description: Consulta e diagnóstico da API de Integração do webPosto (Quality Automação) — o que existe, o que realmente funciona com a chave real, o que é proibido (escrita no ERP) e como sondar com segurança. Use sempre que o trabalho envolver rotas /INTEGRACAO do webPosto, CHAVE de integração, sincronização com o ERP dos postos, ou a pergunta "dá para pegar X do webPosto?".
---

# API webPosto (Quality Automação)

Fontes, em ordem de confiança:
1. **Teste real** (sondagem): `C:\Projetos\LOGOS\LogosPostos-match\docs\external\webposto\sondagem_<data>_<empresa>.json`
2. **Catálogo** (OpenAPI + resultado do teste, em português): `...\docs\external\webposto\CATALOGO_API.md`
3. **OpenAPI oficial**: `https://web.qualityautomacao.com.br/v3/api-docs/integracao` (cópias datadas em `docs/external/webposto/openapi_integracao_*.json`)
4. **Confluence da Quality**: `https://qualityautomacao.atlassian.net/wiki/spaces/webPosto/pages/923402268/APIs+webPosto` (pouco detalhe; parte exige login)

Comece sempre lendo o `CATALOGO_API.md`. Se ele tiver mais de 30 dias ou a rota não estiver lá, atualize (abaixo).

## Regras que não se negociam

- **Escrita é proibida sem aprovação explícita do diretor, por operação.** POST/PUT/PATCH/DELETE gravam no ERP de produção dos postos; não há homologação documentada. Nunca chame uma escrita "para testar". Isso vale também para GET com nome de ação (`ENVIAR_PENDENTE`, etc.).
- **A CHAVE vê a rede inteira.** A chave "Api Integração" consulta qualquer `empresaCodigo` (provado em 08/11/2026). Nunca imprimir, logar, colocar em URL de relatório, planilha, chat ou commit. Ler do `.env` (`WEBPOSTO_API_KEY_*`) e mascarar como `***` em qualquer saída.
- **Ao sondar, imprima só estrutura** (status, contagem, nomes de campo), nunca valores de cliente, CNPJ, CPF ou valores financeiros.
- Pausa entre chamadas (≥ 0,4 s); a API não documenta limite de requisições.

## Como a API funciona

- Base `https://web.qualityautomacao.com.br`; autenticação: query `CHAVE=...` em toda chamada.
- Rotas `/INTEGRACAO/V1/...`: filtro `empresaCodigo`, paginação `ultimoCodigo` + `limite` (máx. usual 2.000), envelope `{"ultimoCodigo": n, "resultados": [...]}`. Repita passando o `ultimoCodigo` até vir lista vazia ou cursor nulo/repetido.
- Rotas legadas (sem `/V1/`): parâmetros diferentes (`filial`, `pagina`); preferir as V1.
- Datas em `AAAA-MM-DD`; negócio em America/Recife.
- O código Python reutilizável já existe: `src.modules.webposto_integration.http.paginar(unidade, rota, params)` (repo LogosPostos). Use-o em vez de escrever cliente novo.

## Armadilhas confirmadas no teste real (09/11/2026)

| Rota | O que a documentação não diz |
|---|---|
| `V1/CARTOES_PAGAR`, `V1/CHEQUES_PAGAR` | `tipoData` é obrigatório ("Tipo de data não informado") |
| `V1/MOVIMENTACOES_CAIXA` | exige o caixa ("Caixa não informado") |
| `V1/DFE_XMLS` | exige série, número e modelo do documento |
| `V1/NOTAS_SAIDA/XMLS` | exige id da nota ou número + série + modelo |
| `V1/AUDITORIA` | datas em data-hora com fuso (OffsetDateTime), não `AAAA-MM-DD` |
| `V1/VENDAS/ITENS/FIDELIDADE` | exige `vendaItemVoucherCodigo` ou `listaVendaItemCodigo` |
| `V1/WEBHOOKS` | HTTP 412: precisa de contrato com o comercial da Quality |
| `APRIX_*` | só para filiais que usam o Aprix |
| `RELATORIO/*` | "Tipo não suportado" com o primeiro valor do enum; testar os outros tipos |
| `V1/FORNECEDORES` | `codigo` = `fornecedorCodigo`; código é global da rede; sem campo de situação (ativo/inativo) nem vínculo com empresa na resposta — vínculo sai consultando por `empresaCodigo` |
| `V1/NOTAS_ENTRADA/XML/{chave}` | devolve `nfeProc` completo (application/xml); 404 "XML não encontrado." quando não há |
| `V1/NOTAS_SERVICO` | NFS-e tomadas normalmente não aparecem (veio vazio em 23/10/2026) |

## Atualizar o diagnóstico (só leitura)

Na pasta `C:\Projetos\LOGOS\LogosPostos-match\WebPosto_API`:

```
.venv\Scripts\python.exe scripts\webposto_catalogo.py baixar
.venv\Scripts\python.exe scripts\webposto_catalogo.py sondar --empresa 74014 --env-var WEBPOSTO_API_KEY_POSTO_DOZE_FILIAL_II --env-file C:\Projetos\LOGOS\LogosPostos\WebPosto_API\.env
.venv\Scripts\python.exe scripts\webposto_catalogo.py gerar
```

`sondar` nunca chama escrita. Compare a nova OpenAPI com a anterior (rotas novas, removidas e alteradas) e conte ao usuário o que mudou para as integrações em uso (VENDAS, CARTOES, CAIXAS, NOTAS_ENTRADA, FORNECEDORES, PRODUTOS...).

## Responder "dá para fazer X?"

1. Procure a rota no `CATALOGO_API.md` (leitura × escrita, filtros, resultado do teste).
2. Se for leitura e o teste deu ✅: dá. Indique rota, filtros e paginação.
3. Se deu ❌/⏸: diga o motivo real (parâmetro obrigatório, contrato, Aprix) e como resolver.
4. Se só existe como escrita: diga que existe, que grava no ERP e que precisa de aprovação do diretor.
5. Se não existe rota: diga isso e proponha perguntar à Quality (suporte/comercial) ou alternativa (relatório, arquivo).
6. Para dúvida de semântica (o que um campo significa), proponha uma sondagem só de leitura com 2–3 empresas, imprimindo só estrutura e contagens.

Unidades: Doze Filial II 74014, Casa Caiada 5555, VIP 11495, Conveniência 24h 118508 (chaves `WEBPOSTO_API_KEY_*` no `.env` do repo LogosPostos).
