# LOGOS — Verificação Definitiva de Contratos OpenAPI V1 (Expense Hunter)

**Data de Validação:** 17/10/2026  
**Fonte Exclusiva de Evidência:** `docs/external/webposto/openapi_integracao_2026-10-06.json` (OpenAPI 3.0.1, 26.455 linhas)  
**Modo de Inspeção:** Programático (Análise estrutural e validação via JSON pointers)  
**Status de Escrita no ERP:** `READ ONLY` estrito (`WEBPOSTO_WRITES=0`, `LOGOS_ERP_ESCRITA=0`)  

---

## 1. Sumário Executivo da Verificação

| # | Endpoint Pesquisado | Existe na OpenAPI? | Path / Método Real na OpenAPI | Operação Funcional Atendida |
|---|---------------------|:------------------:|-------------------------------|-----------------------------|
| 1 | `POST /INTEGRACAO/V1/TITULOS_PAGAR` | **SIM** | `POST /INTEGRACAO/V1/TITULOS_PAGAR` | Inclusão de despesa futura/a pagar (Operação A) |
| 2 | `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` | **SIM** | `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` | Lançamento direto de despesa já paga (Operação B) |
| 3 | `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` | **SIM** | `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` | Baixa/quitação de título a pagar existente (Operação C) |
| 4 | `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA` | **SIM** | `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA` | Consulta, auditoria e conferência de movimentos bancários |
| 5 | `POST /INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}` | **SIM\*** | `POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}` | Vínculo de comprovante em movimento manual (`tipoOrigem="MOVIMENTO_CONTA_MANUAL"`) |
| 6 | `POST /INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{id}` | **SIM\*** | `POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}` | Vínculo de comprovante/boleto em título (`tipoOrigem="TITULO_PAGAR"`) |

*\* Nota sobre itens 5 e 6: Na OpenAPI V1, a rota não é instanciada como path estático com a string do tipo cravada, mas sim como endpoint RESTful parametrizado `POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}`, onde `tipoOrigem` possui enum formal contendo expressamente `"MOVIMENTO_CONTA_MANUAL"` e `"TITULO_PAGAR"`, e `{origem}` é o identificador numérico da entidade.*

---

## 2. Inspeção Detalhada por Endpoint

---

### Endpoint 1: `POST /INTEGRACAO/V1/TITULOS_PAGAR`

- **Existe literalmente na OpenAPI?** **SIM**.
- **Path e Método Exatos:** `POST /INTEGRACAO/V1/TITULOS_PAGAR`
- **Referência no Arquivo JSON:** Linha 10.685 (`#/paths/~1INTEGRACAO~1V1~1TITULOS_PAGAR/post`)
- **operationId:** `incluirTituloPagar`
- **Tipo de Conteúdo Aceito:** `application/json` (`requestBody.required: true`)
- **Schema Utilizado:** `#/components/schemas/IncluirTituloDto` (Linha 13.996)
- **Campos Obrigatórios (`required`):**
  - `descricao` (string)
  - `numeroTitulo` (string)
- **Campos Opcionais Relevantes:**
  - `fornecedorCodigo` (integer, int32)
  - `valorParcela` (number, double, minimum: 0.0)
  - `numeroParcelas` (integer, int32)
  - `dataMovimento` (string, format: date)
  - `vencimento` (string, format: date)
  - `planoContaCodigo` (integer, int32)
  - `centroCustoCodigo` (integer, int32)
  - `empresaCodigo` (integer, int32 — filial em que o fornecedor será vinculado; quando vazio usa a do usuário autenticado)
  - `observacao` (string, maxLength: 255)
  - `dataValida` (boolean)
- **Códigos e Formato de Resposta:**
  - `201 Created`: schema `#/components/schemas/JsonObject` (Linha 10.707)
- **Identificador Retornado:** Objeto JSON contendo os dados do título incluído (identificador interno gerado).
- **Notas de Integração:** Metadados `x-mcp` da rota confirmam: *"Lança um novo título a pagar (fornecedorCodigo, valor, dataVencimento, empresaCodigo...)."*

---

### Endpoint 2: `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`

- **Existe literalmente na OpenAPI?** **SIM**.
- **Path e Método Exatos:** `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`
- **Referência no Arquivo JSON:** Linha 4.957 (`#/paths/~1INTEGRACAO~1V1~1MOVIMENTOS_CONTA/post`)
- **operationId:** `incluirMovimentoConta`
- **Tipo de Conteúdo Aceito:** `application/json` (`requestBody.required: true`)
- **Schema Utilizado:** `#/components/schemas/ParametrosIncluirMovimentoConta` (Linha 14.656)
- **Campos Obrigatórios (`required`):**
  - `descricao` (string)
- **Campos Opcionais Relevantes:**
  - `data` (string, format: date)
  - `valor` (number)
  - `conta` (integer, int32 — identificador da conta corrente/caixa)
  - `documento` (string, nullable)
  - `centroCusto` (integer, int32, nullable)
  - `planoConta` (integer, int32, nullable)
  - `filial` (integer, int32 — código da empresa/unidade)
  - `contaMovimentoTipo` (string, enum: `["CREDITO", "DEBITO"]`)
  - `tipoPessoa` (string, enum: `["NAO_IDENTIFICADO", "CLIENTE", "FORNECEDOR", "FUNCIONARIO"]`)
  - `pessoa` (integer, int32, nullable — código do favorecido)
- **Códigos e Formato de Resposta:**
  - `201 Created` (Linha 4.975)
- **Identificador Retornado:** O corpo da resposta HTTP 201 não define schema estruturado na OpenAPI. A confirmação do identificador gerado e validação de consistência devem ser realizadas por conferência via `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA`.

---

### Endpoint 3: `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR`

- **Existe literalmente na OpenAPI?** **SIM**.
- **Path e Método Exatos:** `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR`
- **Referência no Arquivo JSON:** Linha 10.718 (`#/paths/~1INTEGRACAO~1V1~1TITULOS_PAGAR~1PAGAR/patch`)
- **operationId:** `pagarTituloPagar`
- **Tipo de Conteúdo Aceito:** `application/json` (`requestBody.required: true`)
- **Schema Utilizado:** `#/components/schemas/PagarTituloDto` (Linha 15.553)
- **Campos Obrigatórios (`required`):**
  - `tituloPagarCodigo` (array de integer int32, minItems: 1)
- **Campos Opcionais Relevantes:**
  - `contaCodigo` (integer, int32 — conta bancária de onde sairá o pagamento)
  - `dataPagamento` (string, format: date)
  - `dataValida` (boolean)
  - `pagamentoDataPosterior` (boolean)
- **Códigos e Formato de Resposta:**
  - `204 No Content` (Linha 10.738)
- **Identificador Retornado:** Nenhum no corpo (resposta padrão HTTP 204). A liquidação do título é idempotente e auditada pela mudança de saldo e status do título no ERP.

---

### Endpoint 4: `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA`

- **Existe literalmente na OpenAPI?** **SIM**.
- **Path e Método Exatos:** `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA`
- **Referência no Arquivo JSON:** Linha 4.758 (`#/paths/~1INTEGRACAO~1V1~1MOVIMENTOS_CONTA/get`)
- **operationId:** `consultarMovimentoConta`
- **Parâmetros Query Relevantes:**
  - `empresaCodigo` (integer, int32)
  - `dataInicial` (string, format: date)
  - `dataFinal` (string, format: date)
  - `ultimoCodigo` (integer, int32 — cursor incremental para paginação eficiente)
  - `limite` (integer, int32, maximum: 2000)
  - `mostraSaldo` (boolean)
  - `dataHoraAtualizacao` (string, format: date-time)
  - `documentoOrigemCodigo` (integer, int32)
  - `tipoDocumentoOrigem` (string, enum com 64 valores incluindo `MANUAL`, `TITULO_PAGAR`, `TRANSFERENCIA`, etc.)
  - `contaCodigo` (integer, int32)
- **Códigos e Formato de Resposta:**
  - `200 OK`: schema `#/components/schemas/RetornoPaginadoMovimentoConta` (Linha 16.183)
- **Identificador Retornado:** Retorna payload com array `itens` de `MovimentoContaDto`, contendo `codigo`, `data`, `valor`, `documento`, `conta`, `centroCusto`, `planoConta`, `historico`, `tipoDocumentoOrigem`, etc.

---

### Endpoints 5 e 6: Vínculo de Arquivos e Comprovantes

#### 5. `POST /INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}`
#### 6. `POST /INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{id}`

- **Existe literalmente na OpenAPI?**
  - **Literalmente como string estática:** **NÃO**.
  - **Como contrato parametrizado formal:** **SIM**, implementado como `POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}`.
- **Path e Método Exatos:** `POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}`
- **Referência no Arquivo JSON:** Linha 482 (`#/paths/~1INTEGRACAO~1V1~1ARQUIVOS~1{tipoOrigem}~1{origem}/post`)
- **operationId:** `incluirArquivoFechamentoCaixa`
- **Parâmetros de Rota (Path Parameters):**
  - `tipoOrigem` (string, required: true): possui enum com 48 opções, contemplando expressamente:
    - `"MOVIMENTO_CONTA_MANUAL"` (Linha 524) $\rightarrow$ vincula arquivo ao movimento de conta avulso.
    - `"TITULO_PAGAR"` (Linha 497) $\rightarrow$ vincula arquivo/comprovante ao título a pagar.
  - `origem` (integer, int32, required: true): código numérico da entidade (`{id}` do título ou `{id}` do movimento).
- **Tipo de Conteúdo Aceito:** `application/json` (`requestBody.required: true`)
- **Schema Utilizado:** `#/components/schemas/IncluirArquivoFechamentoCaixaDto` (Linha 15.356)
- **Campos do Schema (`IncluirArquivoFechamentoCaixaDto`):**
  - `nome` (string — nome do arquivo com extensão, ex: `"comprovante_pix_1234.pdf"`)
  - `conteudo` (string, format: byte — payload do arquivo em Base64)
- **Códigos e Formato de Resposta:**
  - `201 Created`: schema `#/components/schemas/JsonObject` (Linha 562)
- **Identificador Retornado:** Objeto JSON com dados e ID do arquivo armazenado.
- **Rota Complementar de Remoção:** `DELETE /INTEGRACAO/V1/ARQUIVOS/{id}` (Linha 458, `operationId: "excluirArquivoFechamentoCaixa"`).

---

## 3. Matriz de Viabilidade para Desenvolvimento de Adaptadores

Com base exclusivamente nos contratos comprovados na OpenAPI V1:

| Operação Financeira | Viabilidade Documental | Endpoint Principal | Endpoint de Anexo | Status de Risco Técnico |
|---|:---:|---|---|---|
| **Operação A:** Lançar despesa futura/a pagar | **TOTAL (100%)** | `POST /INTEGRACAO/V1/TITULOS_PAGAR` (`IncluirTituloDto`) | `POST /INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{id}` | Baixo. Contrato totalmente tipado e schema documentado. |
| **Operação B:** Lançar despesa já paga (débito em conta) | **TOTAL (100%)** | `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` (`ParametrosIncluirMovimentoConta`) | `POST /INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}` | Baixo. Resposta 201 não traz schema explícito, exigindo conciliação por `GET /MOVIMENTOS_CONTA`. |
| **Operação C:** Baixar título a pagar existente | **TOTAL (100%)** | `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` (`PagarTituloDto`) | `POST /INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{id}` | Baixo. Contrato direto e idempotente via array `tituloPagarCodigo`. |
| **Conferência e Auditoria:** Extrato de movimentos | **TOTAL (100%)** | `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA` | N/A | Totalmente aderente com suporte a paginação por cursor (`ultimoCodigo`). |

---

## 4. Conclusão e Diretrizes de Próximos Passos

1. **Inexistência de Impedimento Documental:** Nenhum dos endpoints críticos do fluxo do Expense Hunter é hipotético ou ausente na OpenAPI V1. Todos possuem especificação contratual formal.
2. **Desenvolvimento de Adaptadores:** Os adaptadores da camada de infraestrutura/gateway podem ser modelados com DTOs Pydantic/dataclasses estritamente aderentes a `IncluirTituloDto`, `ParametrosIncluirMovimentoConta`, `PagarTituloDto` e `IncluirArquivoFechamentoCaixaDto`.
3. **Parada Segura:** Nenhuma escrita ou chamada HTTP foi executada ou implementada. As travas de segurança `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` permanecem intactas.
