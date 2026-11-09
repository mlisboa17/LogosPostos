# API de Integração webPosto (Quality Automação)

Tudo o que sabemos sobre a API do ERP dos postos: contrato oficial, teste real e regras de uso.

## Comece por aqui

| Arquivo | O que é |
|---|---|
| `CATALOGO_API.md` | **Leia primeiro.** Regras (o que pode e o que não pode) e todas as rotas, cada uma com o resultado do teste real. |
| `sondagem_<data>_<empresa>.json` | Resultado bruto do teste real (status, tempo, quantidade e nomes de campo; nunca valores). |
| `openapi_integracao_<data>.json` | Cópia datada do contrato oficial. |

Para gerar tudo de novo (só leitura, nunca grava no ERP), na pasta `WebPosto_API`:

```
.venv\Scripts\python.exe scripts\webposto_catalogo.py baixar
.venv\Scripts\python.exe scripts\webposto_catalogo.py sondar --empresa 74014 --env-var WEBPOSTO_API_KEY_POSTO_DOZE_FILIAL_II --env-file C:\Projetos\LOGOS\LogosPostos\WebPosto_API\.env
.venv\Scripts\python.exe scripts\webposto_catalogo.py gerar
```

## Usar com qualquer IA

- **Claude Code** (terminal, VS Code ou app): a habilidade `webposto-api` carrega sozinha quando o assunto é webPosto. Ela está em `~/.claude/skills/webposto-api/` (vale em todos os projetos desta máquina) e em `.claude/skills/webposto-api/` neste repositório.
- **Cursor, ChatGPT, Gemini ou outra:** anexe `CATALOGO_API.md` (e, se a pergunta for sobre campos, o `openapi_integracao_<data>.json` mais recente) e cole este início de conversa:

  > Você vai me ajudar com a API de Integração do webPosto. Use somente o arquivo CATALOGO_API.md anexado como fonte. Siga as Regras dele: nunca proponha chamar POST/PUT/PATCH/DELETE sem eu aprovar, nunca peça nem mostre a CHAVE, e diga quando a rota não foi testada. Minha pergunta: ...

- **Nunca** envie a chave (`CHAVE`) nem o `.env` para nenhuma IA ou site.

## Cópias do contrato oficial

| Arquivo | Origem | Capturado em | SHA-256 do original |
|---|---|---|---|
| `openapi_integracao_2026-10-06.json` | `https://web.qualityautomacao.com.br/v3/api-docs/integracao` | 2026-10-06 | `256a34a396bd79febd6f61a69677c14bd450014ec4c95a4f6abe08b24a6a0ee7` |
| `openapi_integracao_2026-11-09.json` | mesma | 2026-11-09 | `18eaebd59bc292bd47f247f7ba964dae09add065a2e778b48cf849aa7afcd1be` |

Swagger UI: `https://web.qualityautomacao.com.br/webjars/swagger-ui/index.html?configUrl=/v3/api-docs/swagger-config`.
Confluence da Quality: `https://qualityautomacao.atlassian.net/wiki/spaces/webPosto/pages/923402268/APIs+webPosto`.

## Observações
- 09/11/2026: 168 rotas, 184 operações (120 leituras, 64 escritas). Desde 06/10 entraram 21 rotas, saíram 9 e 14 mudaram (inclusive `V1/VENDAS`, `V1/VENDAS/ITENS`, `V1/PRODUTOS`, `V1/ABASTECIMENTOS`).
- O endereço `/v3/api-docs` (sem `/integracao`) mostra 19 rotas a mais (WhatsApp, WPIA, LMC/CAIXA de laudo) que não aparecem no Swagger público; não usar sem confirmar com a Quality.
- Rotas legadas (`/INTEGRACAO/CAIXA`, `CAIXA_APRESENTADO`, `FECHAMENTO_CAIXA`, `CONSULTAR_*_REDE`) usam `filial`/`pagina`; preferir as V1 (`empresaCodigo`, `ultimoCodigo` + `limite`).
- A spec não declara `securitySchemes`; a autenticação real é o parâmetro `CHAVE`. Nunca adicionar exemplos com chave real a esta pasta.
