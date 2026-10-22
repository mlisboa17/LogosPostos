# LOGOS — EXPENSE-AUDIT-01: Auditoria Funcional do Expense Hunter e Validação das Operações no webPosto

**Data da Auditoria:** 17/10/2026 21:30  
**Branch Canônica:** `feature/cash-audit-fechamento`  
**Prioridade:** P0 — Integridade financeira e segurança de escrita  
**Modo:** READ ONLY (nenhuma escrita realizada no ERP, travas mantidas em zero, nenhuma alteração em produção)  
**Documentos de Referência:**
- [STATUS.md](../../STATUS.md)
- [ARCH_MODULE_01_CURRENT_STRUCTURE.md](../architecture/ARCH_MODULE_01_CURRENT_STRUCTURE.md)
- [REGRAS_DE_NEGOCIO.md](../regras-negocio/REGRAS_DE_NEGOCIO.md) (RN-ERP-003, ADR-003)
- `docs/external/webposto/openapi_integracao_2026-10-06.json`
- `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_cartao.py`
- `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py`

---

## 1. Resumo Executivo

O objetivo do **Expense Hunter** é entregar o fluxo completo:
$$\text{Comprovante (Foto/PDF/Áudio)} \longrightarrow \text{Reconhecimento (IA)} \longrightarrow \text{Conferência (Extrato/ERP)} \longrightarrow \text{Aprovação Humana} \longrightarrow \text{Lançamento ERP} \longrightarrow \text{Confirmação}$$

### Diagnóstico de Maturidade Atual
1. **Captura e Extração IA (85% implementado):** O recebimento de comprovantes via Telegram (`receber_comprovantes.py`) e a extração estruturada de dados com Gemini (`gemini_comprovantes.py`) estão implementados e testados offline com mocks e tipagem Pydantic (`comprovante.py`). A preservação do original em disco local (`WebPosto_API/data/despesas_avulsas/comprovantes/`) funciona.
2. **Conferência e Cruzamento OFX (90% implementado):** A lógica de casamento com extratos bancários locais (`despesas_sem_lancamento.py`) e identificação de títulos a pagar já quitados (`titulos_pagos_sem_baixa.py`) é robusta e conta com ampla cobertura de testes unitários offline (exclusão de tarifas, aplicações financeiras e transferências entre postos do grupo).
3. **Fila Local e Revisão (70% implementado, mas incompleto):** A persistência atômica da fila em `data/despesas_avulsas/fila.json` funciona, mas possui status rudimentares (`"sem extrato ainda"`, `"a classificar"`, `"pronto para lançar"`). **Não há botões ou comandos de aprovação humana individual, não há tokens de aprovação e não há barreira de re-execução.**
4. **Operações Financeiras no webPosto (0% implementado para despesas):** Não existe adaptador de escrita para despesas. As travas de segurança `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` estão ativas e foram respeitadas.
5. **Divergência Crítica de Negócio:** O sistema anterior tratava despesas como se todas fossem uma única operação. No entanto, o ERP webPosto exige **três operações financeiras com contratos, semânticas e endpoints totalmente distintos**:
   - **Operação A (Despesa nova a pagar):** Não possui endpoint documentado de criação avulsa na OpenAPI V1.
   - **Operação B (Despesa já paga sem título):** Envolve débito em conta via `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` e anexo via `POST /INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}`. Não possui rota de estorno via API.
   - **Operação C (Título existente quitado no banco):** Envolve baixa de título via `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` e anexo via `POST /INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{id}`. Exige correspondência prévia estrita para evitar duplicidade de débito.

---

## 2. Fluxo Efetivamente Implementado

O fluxo construído nas Sprints anteriores reside quase inteiramente no módulo `WebPosto_API/src/modules/cash_reconciliation/`:

```
[Diretor no Telegram] 
        │ (Foto, PDF, Áudio, Texto)
        ▼
[src/jobs/receber_comprovantes.py]
        │ 1. Filtra chat_id do diretor (whitelist)
        │ 2. Baixa bytes via Telegram API
        ▼
[application/processar_comprovante.py]
        │ 3. Salva original em data/despesas_avulsas/comprovantes/
        │ 4. Invoca GeminiExtractor (gemini-2.5-flash / gemini-1.5-flash)
        ▼
[adapters/gemini_comprovantes.py] ──> Retorna DadosComprovante (Pydantic)
        │
        ▼
[application/despesas_sem_lancamento.py]
        │ 5. Lê extratos OFX locais (BB e PagBank)
        │ 6. Casa valor (exato ou até +10% juros), data (±3 dias) e favorecido
        │ 7. Identifica se débito já é título aberto em titulos_pagos_sem_baixa.py
        │ 8. Sugere Plano de Contas e Centro de Custo por palavras-chave
        ▼
[application/fila_despesas.py]
        │ 9. Persiste atomicamente em data/despesas_avulsas/fila.json
        ▼
[src/jobs/receber_comprovantes.py]
        │ 10. Responde mensagem amigável de confirmação ao diretor
        ▼
[FIM DO FLUXO ATUAL] ──(Nenhum lançamento no ERP; nenhuma escrita ocorre)
```

---

## 3. Matriz AS-IS de Funcionalidades

| Funcionalidade | Componente Principal | Status Atual | Detalhes / Limitações |
|---|---|---|---|
| Captura de Foto via Telegram | `receber_comprovantes.py` | **Implementado e Testado** | Baixa a maior resolução (`photo[-1]`), salva como `.jpg`. Whitelist por `TELEGRAM_CHAT_IDS`. |
| Captura de PDF via Telegram | `receber_comprovantes.py` | **Implementado e Testado** | Lê documento MIME `application/pdf`, salva em disco. |
| Captura de Áudio via Telegram | `receber_comprovantes.py` | **Implementado e Testado** | Lê voz/áudio OGG/Opus do Telegram, salva como `audio.ogg`. |
| Extração de Comprovante (IA) | `gemini_comprovantes.py` | **Implementado e Testado** | Prompt estruturado com JSON Schema; parse seguro de datas brasileiras e decimais monetários. Mock para testes offline. |
| Transcrição de Áudio (IA) | `gemini_comprovantes.py` | **Implementado e Testado** | Transcreve o áudio e extrai entidades (valor falado, fornecedor, serviço mencionado). |
| Preservação do Arquivo Original | `fila_despesas.py` | **Implementado e Testado** | Grava em `data/despesas_avulsas/comprovantes/comp_{id}.ext`. Isolado do Git. |
| Casamento com Extrato Bancário | `processar_comprovante.py` | **Implementado e Testado** | Cruza com extratos OFX locais. Tolera até 10% de juros e janela de ±3 dias. |
| Exclusão de Operações do Grupo | `despesas_sem_lancamento.py` | **Implementado e Testado** | Exclui transferências entre postos da rede (VIP, Doze, Casa Caiada, Real, etc.), aplicações financeiras e tarifas. |
| Sugestão de Plano de Contas | `processar_comprovante.py` | **Implementado e Testado** | Mapeia termos contábeis aprendidos ("pedreiro" $\rightarrow$ 198595, "piso" $\rightarrow$ 194968, "farda" $\rightarrow$ 29057, "DARF" $\rightarrow$ 29128, "FGTS" $\rightarrow$ 29086). |
| Detecção de Título Já Aberto | `titulos_pagos_sem_baixa.py` | **Implementado e Testado** | Identifica se o débito casa com obrigação preexistente (`TITULO_PAGAR`) antes de classificar como despesa avulsa. |
| Persistência da Fila Local | `fila_despesas.py` | **Implementado e Testado** | Gravação atômica em JSON (`fila.tmp` $\rightarrow$ `fila.json`). |
| Resposta do Bot ao Diretor | `processar_comprovante.py` | **Implementado e Testado** | Formata mensagem clara com valor, favorecido, data, banco e categoria sugerida. |
| Detecção de Documento Duplicado | `processar_comprovante.py` | **Parcial / Lacuna** | Reconhece se é resposta à mesma mensagem do Telegram (`reply_to`), mas **não calcula hash SHA-256** do arquivo nem bloqueia foto reenviada em nova mensagem. |
| Detecção de Débito Já Usado na Fila | `processar_comprovante.py` | **Parcial / Lacuna** | Casamento não verifica se o `fitid` já foi associado a outro item previamente gravado na fila. |
| Resolução Segura de Empresa | `processar_comprovante.py` | **Parcial / Risco** | Se a conta bancária não for unívoca, aplica fallback forçado para Doze (74014), o que pode lançar despesa na empresa errada. |
| Aprovação Humana Individual | `fila_despesas.py` | **Lacuna** | Não existem estados `"aguardando_aprovacao"`, `"aprovado"`, `"rejeitado"`. Status atual vai direto para `"pronto para lançar"`. |
| Interface / Botão de Aprovação | `receber_comprovantes.py` | **Lacuna** | Não envia botões inline no Telegram (`[Aprovar]`, `[Editar]`, `[Rejeitar]`). |
| Registro de Auditoria da Aprovação | `comprovante.py` | **Ausente** | Faltam campos de quem aprovou, data/hora e hash do payload aprovado (imutabilidade). |
| Adaptador de Escrita no ERP | `adapters/` | **Ausente (Conforme regra)** | Nenhum código de escrita de despesas foi criado. Travas no `.env` mantidas em 0. |
| Associação de Anexo no ERP | `adapters/` | **Ausente** | Rota `POST /INTEGRACAO/V1/ARQUIVOS/...` conhecida na OpenAPI, mas sem cliente de envio. |
| Confirmação Pós-Gravação | `adapters/` | **Ausente** | Falta rotina para verificar se o lançamento realmente constou no webPosto após timeout de escrita. |

---

## 4. Componentes REUSE / ADAPT / CREATE

Aplicando rigorosamente o princípio arquitetural **REUSE > ADAPT > CREATE**:

### A. REUSE (Reaproveitamento Direto)
1. `WebPosto_API/src/modules/cash_reconciliation/adapters/gemini_comprovantes.py`:
   - Reutilizar integralmente o `GeminiExtractor`, seus prompts de extração de comprovantes e áudios, e a infraestrutura de mock para testes isolados.
2. `WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py`:
   - Reutilizar para leitura de OFX, normalização de FITID e validação de cabeçalhos.
3. `WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py`:
   - Reutilizar as listas de exclusão (`EMPRESAS_GRUPO_PADRAO`, `APLICACOES_BANCARIAS_PADRAO`, `TARIFAS_BANCARIAS_PADRAO`) e as funções de extração de favorecido e casamento de texto (`texto_confere`).
4. `WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py`:
   - Reutilizar `encontrar_candidatos_baixa()` para conferir se qualquer comprovante ou débito refere-se a um título existente antes de propor despesa nova.
5. Padrão de Barreira de Escrita de `webposto_escrita_cartao.py` e `webposto_escrita_ofx.py`:
   - Reutilizar o modelo rigoroso de checagem física de travas no `.env`, mascaramento de dados sensíveis em logs (`mensagem_segura`), locks de concorrência e auditoria append-only.

### B. ADAPT (Adaptações Necessárias)
1. `WebPosto_API/src/modules/cash_reconciliation/domain/comprovante.py`:
   - **Adaptar:** Expandir `ItemFilaDespesa` para conter:
     - `hash_arquivo_sha256`: string com SHA-256 do arquivo original;
     - `status`: adotar a máquina de estados formal da ADR-003 (`recebido`, `aguardando_revisao`, `aguardando_aprovacao`, `aprovado`, `rejeitado`, `lancado_erp`, `falha_escrita`);
     - `aprovado_por`: identificador do diretor que aprovou;
     - `aprovado_em`: timestamp ISO da aprovação humana;
     - `payload_aprovado_hash`: hash dos valores aprovados (evita adulteração pós-aprovação).
2. `WebPosto_API/src/modules/cash_reconciliation/application/processar_comprovante.py`:
   - **Adaptar:**
     - Calcular hash SHA-256 do arquivo recebido e rejeitar documentos idênticos já presentes na fila;
     - Excluir FITIDs que já constem na fila ativa ao casar com o extrato bancário;
     - Remover o fallback hardcoded para Doze (74014) quando a unidade for duvidosa; se duvidosa, marcar status como `"aguardando_revisao"` solicitando confirmação de qual posto realizou o pagamento.
3. `WebPosto_API/src/jobs/receber_comprovantes.py`:
   - **Adaptar:** Incluir botões inline de resposta do Telegram (`InlineKeyboardMarkup`) para permitir aprovação ou rejeição com um toque pelo diretor, disparando callback seguro com verificação de autorização.
4. `WebPosto_API/src/modules/cash_reconciliation/application/fila_despesas.py`:
   - **Adaptar:** Adicionar transições protegidas de estado (inspiradas em `propostas_lancamento.py`) para impedir aprovação duplicada ou modificação de item já aprovado.

### C. CREATE (Criação Futura — Apenas nos Incrementos Autorizados)
1. `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py`:
   - Criar módulo isolado de escrita de despesa **somente no Incremento 4**, contendo:
     - Função `incluir_movimento_conta_despesa()` (`POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`);
     - Função `baixar_titulo_despesa()` (`PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR`);
     - Função `anexar_comprovante_despesa()` (`POST /INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}`);
     - Conferência prévia de saldo e existência;
     - Dupla trava no `.env` (`WEBPOSTO_WRITES=1` e `LOGOS_EXPENSE_ESCRITA=1`);
     - Limite financeiro máximo por transação (ex: R$ 5.000,00);
     - Registro em log de auditoria append-only em `data/lancamentos_logos/<empresa>/`.

---

## 5. Captura e Reconhecimento

Análise detalhada do comportamento atual:

1. **Recepção de Fotos:**
   - O Telegram envia uma lista de resoluções. O bot seleciona a maior (`msg["photo"][-1]`), baixa via `getFile`, salva localmente e envia ao Gemini com MIME `image/jpeg`. O Gemini extrai com sucesso campos visíveis em comprovantes PIX, boletos e recibos.
2. **Recepção de Documentos PDF:**
   - Mensagens com `document` e MIME `application/pdf` são baixadas, gravadas como `.pdf` e submetidas diretamente à API multimodal do Gemini, processando PDFs de uma ou mais páginas.
3. **Tratamento de Áudio:**
   - Mensagens de voz (`voice`) ou arquivos de áudio (`audio`) são baixados em formato OGG/Opus. O Gemini transcreve o conteúdo e extrai entidades financeiras faladas ("paguei duzentos reais a seu Zé pedreiro da pista").
   - O orquestrador combina o áudio com o texto complementar e atualiza o favorecido e valor caso a foto esteja ilegível ou ausente.
4. **Armazenamento do Arquivo Original:**
   - O arquivo físico original é salvo em `WebPosto_API/data/despesas_avulsas/comprovantes/comp_{id}.{ext}` ou `audio_{id}.ogg`.
   - **Garantia:** O arquivo nunca é descartado; o caminho é registrado em `ItemFilaDespesa.arquivo_comprovante`.
5. **Registro de Campos Financeiros:**
   - *Fornecedor/Favorecido:* Extraído da foto/áudio e limpo por `extrair_favorecido()`.
   - *Empresa:* Resolvida prioritariamente pelo extrato bancário casado (`contas_extrato` da unidade em `units.json`). Caso não haja casamento, cai em fallback.
   - *Valor:* Tipado rigorosamente como `Decimal` após passar por `_parse_valor_seguro()` (suporta formatação brasileira).
   - *Data:* Extraída e convertida para `date`. Se omitida no comprovante, herda a data do extrato casado.
   - *Meio de Pagamento:* Tipado como `"PIX"`, `"Boleto"`, `"TED"`, `"Imposto"` ou `"Outros"`.
6. **Tratamento de Incertezas:**
   - Se o valor ou data faltam, o item recebe status `"sem extrato ainda"`.
   - Se a conta contábil não puder ser determinada pelas regras de palavras-chave, recebe `"a classificar"` com centro de custo padrão 7295 (PISTA).
7. **Cobertura de Testes:**
   - O arquivo `WebPosto_API/tests/unit/cash_reconciliation/test_comprovantes_fila.py` (530 linhas) cobre 100% dos cenários de parsing, mocks do Gemini, filtros de chat_id do diretor e CRUD em `fila.json`.
8. **Validação com Documentos Reais:**
   - Validado com dezenas de comprovantes sintéticos e amostras de extratos reais locais da rede. A validação ponta a ponta com a API do Gemini ao vivo depende de credencial ativa no `.env`, operando com mock nos testes automatizados.

---

## 6. Revisão e Aprovação Humana

### Análise da Máquina de Estados
A auditoria constatou que o sistema atual possui um ciclo de vida incompleto em `comprovante.py`:
- **Estados atuais:** `"sem extrato ainda"` $\rightarrow$ `"a classificar"` $\rightarrow$ `"pronto para lançar"`.
- **Problema de Governança:** O estado `"pronto para lançar"` é atingido automaticamente assim que o extrato casa e uma categoria é sugerida. Isso dá a falsa impressão de que o sistema está autorizado a escrever.

### Requisitos Obrigatórios da ADR-003 para Aprovação Humana
Para garantir a segurança financeira exigida pelo dono, a máquina de estados deve ser estritamente sequencial:

```
[RECEBIDO]
    │ (Processamento IA e extrato concluído)
    ▼
[AGUARDANDO_REVISAO]  (Faltam dados, empresa ambígua ou conta a classificar)
    │ (Revisão de categoria pelo diretor ou gerente)
    ▼
[AGUARDANDO_APROVACAO] (Todos os campos preenchidos; exibido no Telegram/UI)
    │
    ├─── [REJEITADO] (Cancelado pelo diretor; processo encerrado)
    │
    └─── [APROVADO] (Autorizado individualmente por usuário com permissão)
            │ (Disparo do worker de escrita com travas ativas)
            ▼
        [ENVIANDO_ERP] (Idempotência gravada; aguardando resposta webPosto)
            │
            ├─── [LANCADO_ERP] (Confirmado via 201/204 + verificação de leitura)
            └─── [FALHA_ESCRITA] (Timeout ou erro HTTP; exige conferência antes de retry)
```

### Mecanismos de Proteção e Controles
1. **Autorização Estrita:** Apenas usuários cujo `chat_id` conste expressamente em `TELEGRAM_CHAT_IDS` podem aprovar.
2. **Proibição de Lotes Cegos:** Não permitir botão "Aprovar Todos". Cada lançamento deve ser deliberado individualmente com seus valores, fornecedor e empresa visíveis.
3. **Imutabilidade Pós-Aprovação:** Uma vez aprovado, qualquer alteração em valor, empresa, fornecedor ou plano de contas invalida o token de aprovação e retorna o item para `"aguardando_aprovacao"`.
4. **Proteção Contra Reenvio em Timeout:** Se a requisição de escrita sofrer timeout, o item vai para `"falha_escrita"` e o sistema **nunca reenvia imediatamente**. Ele deve executar uma consulta `GET` no ERP para verificar se o registro foi gravado antes de permitir nova tentativa.

---

## 7. Duplicidade: Três Conceitos Distintos

A auditoria confirmou a necessidade de segregar formalmente os três tipos de duplicidade:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MAPA DE DUPLICIDADES                            │
├────────────────────────┬───────────────────────────────────────────────┤
│ Conceito               │ Como Identificar e Bloquear                   │
├────────────────────────┼───────────────────────────────────────────────┤
│ 1. Documento           │ Hash SHA-256 do arquivo original ou mesmo     │
│    Duplicado           │ Telegram message_id. Se já existir na pasta   │
│                        │ de comprovantes, rejeita com aviso imediato. │
├────────────────────────┼───────────────────────────────────────────────┤
│ 2. Despesa             │ Mesmo banco, conta e FITID já registrado na   │
│    Duplicada           │ fila local ou em V1/MOVIMENTOS_CONTA.        │
│                        │ Bloqueia lançamento duplicado da mesma saída. │
├────────────────────────┼───────────────────────────────────────────────┤
│ 3. Pagamento de        │ Débito bancário que coincide com título em    │
│    Título Existente    │ aberto em V1/TITULOS_PAGAR.                   │
│                        │ NÃO É DESPESA AVULSA! Deve gerar BAIXA de     │
│                        │ título (Operação C), nunca nova despesa.      │
└────────────────────────┴───────────────────────────────────────────────┘
```

---

## 8. Auditoria dos Endpoints webPosto

Confrontando a OpenAPI oficial (`docs/external/webposto/openapi_integracao_2026-10-06.json`) com os requisitos de negócio das três operações:

| Caso de Negócio | Endpoint Oficial | Método | Payload Obrigatório | Efeito Financeiro | Pré-Condições | Evidência na OpenAPI |
|---|---|---|---|---|---|---|
| **A. Despesa Nova (a pagar)** | **LACUNA NA API** | `POST` | Não há endpoint documentado na V1 | Criação de obrigação futura no Contas a Pagar | Fornecedor cadastrado, plano de contas e centro de custo | `GET /INTEGRACAO/V1/TITULOS_PAGAR` existe (L2317). Não há `POST /V1/TITULOS_PAGAR`. Endpoint legado `/TITULO_PAGAR` dava 404 em testes. |
| **B. Despesa Paga (sem título)** | `/INTEGRACAO/V1/MOVIMENTOS_CONTA` | `POST` | `ParametrosIncluirMovimentoConta` (`cdEmpresa`, `cdConta`, `dtMovimento`, `cdPlanoConta`, `cdCentroCusto`, `vlMovimento`, `contaMovimentoTipo="DEBITO"`, `tipoDocumentoOrigem="MANUAL"`) | Debita saldo bancário no ERP imediatamente | Conta bancária cadastrada no webPosto (`cdConta`), plano de contas válido, empresa ativa | Linha 4957 da OpenAPI (`incluirMovimentoConta`). Retorna HTTP 201 Created. |
| **B. Anexo da Despesa Paga** | `/INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}` | `POST` | `IncluirArquivoFechamentoCaixaDto` (`arquivo`: base64, `nomeArquivo`, `tipoArquivo`) | Vincula o PDF/Foto ao movimento bancário manual | Movimento de conta já criado e ID retornado pelo POST anterior | Linha 482 da OpenAPI (`incluirArquivoFechamentoCaixa`, enum `MOVIMENTO_CONTA_MANUAL`). Retorna 201. |
| **C. Baixa de Título Existente** | `/INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` | `PATCH` | `PagarTituloDto` (array de objetos: `tituloPagarCodigo`, `contaCodigo`, `dataPagamento`) | Altera status do título para quitado e debita a conta bancária | Título com status "Aberto", valor compatível, conta bancária válida | Documentado na Sprint BAIXA_00 e OpenAPI V1. Retorna HTTP 204 No Content. |
| **C. Anexo no Título Quitado** | `/INTEGRACAO/V1/ARQUIVOS/TITULO_PAGAR/{tituloPagarCodigo}` | `POST` | `IncluirArquivoFechamentoCaixaDto` (`arquivo`: base64, `nomeArquivo`) | Vincula o comprovante ao título a pagar | Título existente no webPosto | Linha 482 da OpenAPI (enum `TITULO_PAGAR`). Retorna 201 Created. |
| **Consulta Prévia de Títulos** | `/INTEGRACAO/V1/TITULOS_PAGAR` | `GET` | Params: `dataInicial`, `dataFinal`, `empresaCodigo`, cursor `ultimoCodigo` | Nenhum (somente leitura) | Autenticação bearer token | Linha 2317 da OpenAPI (`consultarTituloPagar`). |
| **Consulta Prévia de Movimentos**| `/INTEGRACAO/V1/MOVIMENTOS_CONTA` | `GET` | Params: `dataInicial`, `dataFinal`, `empresaCodigo`, cursor `ultimoCodigo` | Nenhum (somente leitura) | Autenticação bearer token | Linha 4758 da OpenAPI (`consultarMovimentoConta`). |
| **Consulta Contas Bancárias** | `/INTEGRACAO/V1/CONTAS` | `GET` | Params: paginação | Nenhum (somente leitura) | Validação do `cdConta` antes de qualquer escrita | Linha 2102 da OpenAPI (`consultarConta`). |

### Alertas Críticos da API webPosto:
1. **Irreversibilidade de Movimentos:** O endpoint `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` **não possui rota de DELETE via API**. Lançamentos errados exigem exclusão manual por usuário administrador na interface gráfica do ERP.
2. **Baixa Integral de Títulos:** O endpoint `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` quita o título pelo valor nominal total. Não permite liquidação parcial via API.

---

## 9. Segurança e Idempotência

### Situação Atual das Travas de Escrita
- `WEBPOSTO_WRITES=0` (confirmado)
- `LOGOS_ERP_ESCRITA=0` (confirmado)
- Ambas devem permanecer em zero. **Nenhuma escrita está autorizada.**

### Requisitos Inegociáveis para o Futuro Adaptador de Escrita
Quando a escrita for autorizada em sprints futuras, ela deverá seguir a mesma "Barreira" já implementada em `webposto_escrita_cartao.py` e `webposto_escrita_ofx.py`:
1. **Leitura Física do `.env`:** Leitura direta do arquivo `.env` via parser isolado (`dotenv_values`), rejeitando variáveis de processo (`os.environ`) e recusando execução se as chaves estiverem duplicadas.
2. **Dupla Trava no Arquivo:** Exigir obrigatoriamente `WEBPOSTO_WRITES=1` e uma trava específica `LOGOS_EXPENSE_ESCRITA=1`.
3. **Teto Financeiro:** Estabelecer um limite de valor máximo por operação (ex: R$ 5.000,00). Valores acima desse teto são bloqueados automaticamente para escrita via API.
4. **Chave de Idempotência Determinística:**
   $$\text{Chave} = \text{SHA-256}(\text{empresa\_codigo} + \text{conta\_codigo} + \text{data} + \text{valor} + \text{fitid\_ou\_comprovante\_hash})$$
   Se a chave já constar no histórico local de lançamentos, a escrita é abortada.
5. **Auditoria Append-Only:** Gravar cada requisição e sua resposta em disco local em `WebPosto_API/data/lancamentos_logos/<empresa>/despesas_audit.jsonl` com timestamp, usuário e payload completo.
6. **Resiliência a Timeout de Rede:** Em caso de timeout durante o envio do `POST`, a aplicação **não deve retentar**. Ela deve consultar `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA` ou `GET /INTEGRACAO/V1/TITULOS_PAGAR` para conferir se o registro foi gravado antes de qualquer outra ação.

---

## 10. Lacunas Comprovadas e Perguntas à Quality

1. **Lacuna da Operação A (Inclusão de Título a Pagar):**
   - *Pergunta à Quality:* A API do webPosto V1 possui endpoint para cadastrar um novo título a pagar avulso (`POST /INTEGRACAO/V1/TITULOS_PAGAR`), ou a inclusão de títulos a pagar no webPosto é restrita à importação de documentos fiscais (NF-e de entrada)?
2. **Fornecedor Não Cadastrado na Operação B:**
   - *Pergunta à Quality:* Ao emitir um `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`, qual é o comportamento do ERP quando o campo `tipoPessoa="NAO_IDENTIFICADO"` é enviado? O webPosto aceita o movimento sem vínculo a cliente/fornecedor, ou exige que toda saída tenha uma `pessoaCodigo` válida?
3. **Anexo de Comprovantes em Movimento Manual:**
   - *Pergunta à Quality:* O endpoint `POST /INTEGRACAO/V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}` recebe como `{id}` o campo `codigo` retornado no corpo do `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`?

---

## 11. Plano Mínimo de Implementação

Seguindo o roteiro de entrega progressiva sem quebras:

### Incremento 1: Reconhecimento, Classificação e Fila com Anti-Duplicidade (Sem Escrita)
- **Objetivo:** Tornar a captura e a fila 100% confiáveis e blindadas contra duplicidade.
- **Entregas:**
  - Adicionar cálculo de SHA-256 do arquivo original e rejeitar fotos/PDFs repetidos;
  - Bloquear reaproveitamento de FITIDs bancários já presentes na fila;
  - Eliminar o fallback forçado para Doze (74014) em casos de empresa duvidosa;
  - Introduzir a máquina de estados formal da ADR-003 na fila local (`ItemFilaDespesa`).
- **Critério de Aceite:** Fila armazena itens com hashes imutáveis e estados claros, sem duplicatas, comprovado por testes unitários offline.

### Incremento 2: Comandos Financeiros Tipados e Validação Offline de Contratos
- **Objetivo:** Modelar as estruturas de dados necessárias para cada uma das três operações financeiras.
- **Entregas:**
  - Criar DTOs Pydantic estritos para `ParametrosIncluirMovimentoConta` e `PagarTituloDto` baseados na OpenAPI oficial de 2026-10-06;
  - Criar funções de montagem e validação dos payloads sem executar HTTP real;
  - Testes unitários com fixtures validando schemas e regras de formatação.
- **Critério de Aceite:** Payloads das Operações B e C montados e validados contra os schemas da OpenAPI com 100% de sucesso em testes offline.

### Incremento 3: Aprovação Individual no Telegram e Gestão de Idempotência
- **Objetivo:** Colocar a decisão de lançamento sob controle humano explícito do diretor.
- **Entregas:**
  - Adicionar botões interativos inline no Telegram (`[Aprovar]`, `[Rejeitar]`, `[Trocar Posto]`);
  - Registrar formalmente a decisão (`aprovado_por`, `aprovado_em`, `payload_aprovado_hash`);
  - Implementar armazenamento SQLite para controle transacional das aprovações (padrão de `propostas_lancamento.py`);
  - Implementar gerador de chaves de idempotência e tabela local append-only.
- **Critério de Aceite:** Diretor recebe o comprovante, clica em aprovar e a fila registra a transição de estado de forma auditável e segura, sem qualquer escrita externa.

### Incremento 4: Piloto de Escrita Real Controlada (Mediante Nova Autorização)
- **Objetivo:** Conectar a escrita ao webPosto com todas as barreiras de segurança ativas.
- **Pré-requisitos:** Autorização formal prévia do dono, liberação das travas de escrita no `.env`, empresa piloto definida e teto de valor estabelecido.
- **Entregas:**
  - Criação do adaptador `webposto_escrita_despesa.py`;
  - Validação da resposta do webPosto e confirmação pós-gravação via `GET`;
  - Upload do comprovante como anexo associado;
  - Envio de confirmação no Telegram com o ID gerado pelo ERP.
- **Critério de Aceite:** Despesa real aprovada é lançada no webPosto sem duplicidade, comprovante anexado e registro auditável gerado.

---

## 12. Riscos e Pontos que Exigem Confirmação Humana

1. **Risco de Lançamento na Empresa Errada:** Pagamentos feitos via PIX pessoal ou conta compartilhada podem ser atribuídos ao posto errado se não houver confirmação humana explícita.
2. **Risco de Duplicidade Financeira (Despesa vs Baixa):** Se um boleto pago no banco for cadastrado como despesa avulsa (Operação B) em vez de baixar o título existente (Operação C), a despesa constará em dobro no resultado do posto e o título continuará vencido e pendente no ERP.
3. **Risco de Falta de Estorno na API:** Como o webPosto não permite DELETE de movimentos manuais de conta via API, qualquer escrita errada demandará retrabalho manual do financeiro na interface do ERP.

---
**Status da Auditoria:** Concluída com sucesso. Nenhuma escrita realizada. Sistema mantido em modo READ ONLY.
