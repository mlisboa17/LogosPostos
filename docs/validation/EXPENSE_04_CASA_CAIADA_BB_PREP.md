# LOGOS — EXPENSE-04-PILOT-PREP-BB: Preparação do Primeiro Lançamento Real (Casa Caiada / Banco do Brasil)

**Data:** 18/10/2026 18:00  
**Repositório Oficial:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Empresa:** AP CASA CAIADA LTDA — `empresaCodigo: 5555`  
**Banco:** Banco do Brasil (001 / 1)  
**Situação:** Despesa já paga por conta bancária (sem lançamento no ERP)  
**Status de Escrita no ERP:** NÃO AUTORIZADA (`READ ONLY` estrito, zero escritas reais)  
**Classificação do Piloto:** **BLOCKED FOR IMMEDIATE ERP WRITE (COM PROPOSTA PREPARADA)**  

---

## 1. Respostas Objetivas aos 10 Requisitos Mandatórios

### 1. Qual é a conta Banco do Brasil da Casa Caiada?
- **Banco:** Banco do Brasil S.A. (código de compensação: `001` / `1`)
- **Agência:** `2365-5`
- **Conta Corrente:** `56816-3`
- **Titularidade:** A POSTO CASA CAIADA LTDA
- **CNPJ Oficial:** `04.284.939/0001-86`

### 2. Qual é o código dessa conta no webPosto?
- No cadastro do webPosto, ela aparece na listagem do endpoint `/INTEGRACAO/CONTA` com a descrição exata:
  `"BANCO DO BRASIL (56816-3)"`.
- **Porém, o código numérico interno (`contaCodigo` / `cdConta`) NÃO está mapeado no arquivo `units.json` nem no repositório local.**
- No `units.json`, a única conta associada à filial `5555` é a conta `17837`, descrita oficialmente como `"CAIXA(POSTO)"` (dinheiro físico / cofre da pista), a qual **não pode ser utilizada para despesas bancárias**.
- Dos 17 códigos de conta retornados por `/INTEGRACAO/CONTA` para o grupo econômico (`17837, 20936, 27173, 27406, 55028, 55460, 58061, 58062, 59117, 60536, 65321, 69050, 69446, 70766, 82912, 82918, 86377`), os snapshots persistidos em `financial_origin_matrix.json` guardaram apenas a linha de amostra (`sampleRow` = `17837`), descartando o `contaCodigo` numérico específico de `BANCO DO BRASIL (56816-3)`.
- **Situação:** Código numérico no webPosto pendente de vinculação cadastral formal.

### 3. Quais fontes comprovam essa associação?
1. **Extrato Oficial OFX:** `C:\Projetos\LOGOS\extratos\BB\BancoBrasil_CasaCaiada_SETEMBRO2026.ofx`  
   - Header do arquivo: `<BANKID>1`, `<BRANCHID>2365-5`, `<ACCTID>56816-3`, `<ORG>Banco do Brasil`.
2. **Extrato Oficial PDF:** `C:\Projetos\LOGOS\extratos\BB\BancoBrasil_CasaCaiada_SETEMBRO2026.pdf` (pág. 1)  
   - Cabeçalho: `Cliente: A POSTO CASA CAIADA LTDA | Agência: 2365-5 | Conta: 56816-3 | Período: 01 a 30/09/2026`.  
   - CNPJ em lançamentos PIX recebidos: `04.284.939/0001-86`.
3. **Mapeamento de Unidades (`units.json`, linhas 91-94):**  
   - `"contas_compartilhadas": [{"nome": "BB CASA CAIADA", "banco": "BB", "membros": [5555, 118508], "_obs": "Conv 24h deposita semanalmente aqui; deposito do Casa Caiada tambem ocorre no Bco24h do Posto BR Shopping (rota do chefe de pista)"}]`.  
   - Esse padrão de depósitos no `POSTO BR SHOPPING ATMR` é confirmado em múltiplas linhas do extrato PDF da conta `56816-3`.
4. **Matriz de Origem Financeira (`WebPosto_API/financial_origin_matrix.json`, linha 230):**  
   - O endpoint `/INTEGRACAO/CONTA` (`CONTA_REDE`) registra explicitamente nos exemplos de contas da rede o registro literal: `"BANCO DO BRASIL (56816-3)"`.

### 4. O LOGOS já consegue identificar a conta automaticamente?
- **Parcialmente (Automação de Leitura Bancária: SIM; Resolução Cadastral no ERP: NÃO).**
- O robô do LOGOS extrai perfeitamente o banco (`BB`), agência (`2365-5`) e conta (`56816-3`) a partir de comprovantes e arquivos OFX.
- Todavia, a resolução determinística para o `contaCodigo` do webPosto em [webposto_escrita_ofx.py](file:///C:/Projetos/LOGOS/LogosPostos/WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py#L150) e em [webposto_escrita_despesa.py](file:///C:/Projetos/LOGOS/LogosPostos/WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py#L113) depende do bloco `contas_extrato` em `units.json`. Como Casa Caiada só possui a conta `17837` cadastrada, o LOGOS identifica a necessidade da conta BB, mas **bloqueia com segurança** a escrita para evitar contaminação do caixa físico ou uso de código inexistente.

### 5. Qual despesa real foi selecionada?
- **Favorecido / Fornecedor:** **FSIST** (Serviço de automação fiscal para consulta e download de documentos fiscais eletrônicos NF-e/DF-e dos postos).
- **Valor:** **R$ 34,90**
- **Data do pagamento bancário:** **28/09/2026**
- **Forma de Pagamento:** Boleto Bancário (compensado em conta corrente BB)
- **Identificadores Bancários Unívocos:**
  - `FITID`: `20260928134900`
  - `Documento (CHECKNUM)`: `92803`
  - `Lote bancário`: `13105`
  - `Descrição no extrato`: `Pagamento de Boleto - FSIST`
- **Justificativa da Seleção:** Despesa real, recorrente, de valor reduzido (baixo risco para teste piloto), com favorecido corporativo inconfundível, não sujeita a rateios ou deduções parciais, e sem nenhuma ambiguidade com transferências entre filiais do grupo ou aplicações financeiras.

### 6. O pagamento está comprovado?
- **SIM, com dupla comprovação bancária definitiva:**
  - **No OFX oficial:** `<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260928000000[-3:BRT]<TRNAMT>-34.90<FITID>20260928134900<CHECKNUM>92803<MEMO>Pagamento de Boleto - FSIST</STMTTRN>`.
  - **No PDF oficial (Página 8):** `28/09/2026 34,90 (-)13105 92803 Pagamento de Boleto / FSIST`.
- A saída de recursos é incontroversa e liquidada na conta bancária da Casa Caiada.

### 7. Já existe lançamento correspondente no ERP?
- **NÃO. A despesa está comprovadamente não lançada no webPosto:**
  - **Títulos a Pagar (`TITULO_PAGAR`):** Inspeção de todos os títulos da filial 5555 confirmou inexistência de títulos para "FSIST" ou no valor de R$ 34,90.
  - **Movimentos de Conta (`MOVIMENTO_CONTA`):** Nenhum débito manual registrado na filial 5555 para este favorecido ou valor.
  - **Despesas do Fechamento de Caixa:** Não consta nos relatórios diários de caixa (`caixa_2026-10-10_5555.md`).
  - Caracteriza-se legitimamente como **despesa avulsa paga por conta bancária**, típica da rotina de pagamentos do diretor via internet banking.

### 8. Qual payload exato está preparado?
Para atendimento do contrato OpenAPI V1 (`POST /INTEGRACAO/V1/MOVIMENTOS_CONTA`, schema `ParametrosIncluirMovimentoConta`):

```json
{
  "descricao": "FSIST - Consulta NF-e",
  "data": "2026-09-28",
  "valor": 34.90,
  "conta": "<PENDENTE_ID_CONTA_BB_5555>",
  "documento": "92803",
  "centroCusto": 7295,
  "planoConta": null,
  "filial": 5555,
  "contaMovimentoTipo": "DEBITO",
  "tipoPessoa": "NAO_IDENTIFICADO",
  "pessoa": null
}
```

*Nota Crítica de Governança:* O campo `"conta"` não foi preenchido com valor fictício. Em cumprimento estrito às regras da sprint, a escrita fica suspensa até a substituição pelo `contaCodigo` oficial.

### 9. Quais informações ainda dependem de revisão humana?
1. **Confirmação do `contaCodigo` do BB:** O diretor/proprietário deve informar qual código numérico interno do webPosto corresponde à conta `BANCO DO BRASIL (56816-3)` da filial 5555, OU autorizar a execução de consulta read-only `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555`.
2. **Plano de Contas Gerencial:** O LOGOS sugere classificar em despesas de informática/software ou no plano geral "A CLASSIFICAR". O diretor pode validar ou indicar a conta gerencial preferida da Casa Caiada.
3. **Centro de Custo:** Sugerido PISTA (`7295`), aplicável a despesas de suporte operacional da pista.

### 10. READY ou BLOCKED para autorização do piloto?
- **STATUS:** **BLOCKED FOR IMMEDIATE ERP WRITE** (com dossiê, payload e testes 100% preparados).
- **Critério de Desbloqueio:** O bloqueio é preventivo e decorre exclusivamente da ausência do mapeamento do `contaCodigo` numérico do Banco do Brasil em `units.json`. Assim que o diretor confirmar o código ou autorizar a consulta read-only ao cadastro de contas, o gate transitará imediatamente para **READY FOR SINGLE CONTROLLED WRITE**.

---

## 2. Experiência no Telegram (Proposta Não-Bloqueante)

Conforme os princípios de UX e governança do LOGOS, a proposta não será exibida como um formulário em branco nem como totalmente validada enquanto houver pendências:

```
============================================================
           LOGOS — Despesa Reconhecida
============================================================
Unidade:       AP Casa Caiada (5555)
Fornecedor:    FSIST (Consulta e Download NF-e)
Valor:         R$ 34,90
Pagamento:     Banco do Brasil (Ag: 2365-5 / CC: 56816-3)
Evidência:     Extrato Bancário BB (Doc: 92803 | FITID: 20260928134900)
Data Débito:   28/09/2026
Categoria:     INFORMÁTICA / SISTEMAS (Sugerida pelo LOGOS)
Centro Custo:  PISTA (7295)
Situação:      Paga via banco — Lançamento não encontrado no ERP

⚠️ PENDÊNCIA CADASTRAL:
A conta bancária BB (56816-3) não possui o cdConta vinculado 
em units.json. A conta 17837 é CAIXA(POSTO) e foi bloqueada.

[Aprovar]   [Informar Conta ERP]   [Rejeitar]
============================================================
```

---

## 3. Investigação Detalhada das Fontes

### 3.1. Confronto das Contas Existentes
| Fonte | Identificador Encontrado | Descrição / Papel | Status para Débito BB |
| :--- | :--- | :--- | :--- |
| `units.json` | `17837` | `"tipo": "cofre", "banco": "BB"` | **BLOQUEADO** (É caixa físico / cofre, não conta corrente bancária) |
| `financial_origin_matrix.json` | `"BANCO DO BRASIL (56816-3)"` | Cadastrada em `/INTEGRACAO/CONTA` para 5555 | **CONFIRMADA NO ERP**, mas com ID numérico não isolado no snapshot |
| Extrato OFX Setembro/2026 | `Ag: 2365-5 / CC: 56816-3` | Conta de movimentação e pagamento de boletos | **CONFIRMADA NO BANCO** |
| Extrato PDF Setembro/2026 | `Ag: 2365-5 / CC: 56816-3` | Cliente A POSTO CASA CAIADA LTDA, CNPJ 04.284.939/0001-86 | **CONFIRMADA NO BANCO** |

### 3.2. Por que a conta 17837 não pode ser utilizada?
O `units.json` possui:
```json
"destino_padrao": 17837,
"destinos": [
  {"conta_codigo": 17837, "tipo": "cofre", "banco": "BB", "prazo_dias": 1}
]
```
A conta 17837 é a conta interna de sangrias físicas da pista ("CAIXA(POSTO)"). Lançar um pagamento de boleto bancário nessa conta geraria:
1. Distorção contábil do saldo físico de dinheiro da pista;
2. Quebra da conciliação bancária do Banco do Brasil;
3. Falsa quebra de caixa no fechamento noturno das 03:00.

---

## 4. Evidências dos Testes Automatizados

Foi criada a suíte dedicada [`test_expense_04_pilot_prep_bb.py`](file:///C:/Projetos/LOGOS/LogosPostos/WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_pilot_prep_bb.py) que comprova todas as asserções de segurança e integridade sem efetuar chamadas externas:

```bash
pytest WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_pilot_prep_bb.py -v
Resultado: 11 passed in 0.68s (100% de sucesso)

# Testes executados:
# 1. test_01_identificacao_conta_bancaria_bb_casa_caiada: PASSED
# 2. test_02_bloqueio_conta_17837_para_pagamento_bancario: PASSED
# 3. test_03_bloqueio_codigo_ficticio_ou_conta_de_outra_empresa: PASSED
# 4. test_04_identificacao_despesa_fsist_no_extrato: PASSED
# 5. test_05_validacao_schema_payload_movimento_conta: PASSED
# 6. test_06_bloqueio_preparacao_sem_cd_conta_oficial: PASSED
# 7. test_07_classificacao_plano_contas_pro_labore_oficial: PASSED
# 8. test_08_preservacao_recebedor_bancario_e_beneficiario_economico: PASSED
# 9. test_09_determinacao_operacao_sem_titulo_previo: PASSED
# 10. test_10_pendencia_especifica_pj_vs_pro_labore: PASSED
# 11. test_11_payload_preparado_despesa_626_casa_caiada: PASSED
```

E a regressão focada do Expense Hunter:
```bash
pytest WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_pilot_prep_bb.py \
       WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py \
       WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_despesa.py \
       WebPosto_API/tests/unit/cash_reconciliation/test_telegram_despesas.py -o addopts=""
Resultado: 84 passed in 13.66s (100% de sucesso)
```

---

## 5. Próximo Passo para a Liberação da Escrita

Para realizar o primeiro lançamento real no webPosto, resta unicamente:
1. Obter a confirmação humana do `contaCodigo` correspondente a `"BANCO DO BRASIL (56816-3)"` na filial 5555;
2. Registrar o mapeamento em `units.json`:
   ```json
   "contas_extrato": [
     {"banco": "BB", "conta_sufixo": "56816-3", "cd_conta": <ID_CONFIRMADO>}
   ]
   ```
3. Adicionar `<ID_CONFIRMADO>` em `CONTAS_AUTORIZADAS_POR_UNIDADE[5555]` no adaptador [webposto_escrita_despesa.py](file:///C:/Projetos/LOGOS/LogosPostos/WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py);
4. Emitir o token criptográfico atômico via `GerenciadorAutorizacaoPiloto.criar_autorizacao(...)`;
5. Executar a escrita assistida via `executar_lancamento_despesa(...)`.

---

## 6. Classificação do Primeiro Piloto Casa Caiada — Comprovante BB R$ 626,00 (10/10/2026)

Em atendimento à decisão expressa do proprietário comunicada em 18/10/2026, foi estruturado o dossiê da operação de **R$ 626,00**, paga em **10/10/2026** por conta bancária do Banco do Brasil da Casa Caiada (`empresaCodigo: 5555`), tendo **Posto Real Ltda** como recebedor bancário e finalidade econômica informada de **PRÓ-LABORE — MÁRCIO**.

### 6.1. Localização no Plano de Contas Oficial do webPosto
- Foi inspecionado o catálogo oficial de contas do webPosto (`WebPosto_API/config/account_category_mapping.json`), composto por 200 planos cadastrados:
  - **Código Oficial Encontrado:** `29021`
  - **Descrição Gerencial:** `"PRO LABORE"`
  - **Código Contábil:** `29021`
  - **Natureza:** `D` (Débito)
  - **Apura DRE:** `true`
  - **Categoria LOGOS:** `PESSOAL`
  - **Classificação:** `PLANO_CONTA` (Catálogo Oficial do ERP)
- **Regra Anti-Invenção de Códigos:** Não existe e não foi criado nenhum código artificial com o nome de "PRÓ-LABORE MÁRCIO". O plano de contas do ERP é genérico por rubrica contábil (`29021 - PRO LABORE`), sendo a individuação de Márcio mantida na descrição do histórico e nos dados de beneficiário econômico.

### 6.2. Identificação da Conta Banco do Brasil
- **Filial Emissora:** Casa Caiada (`5555`).
- **Banco:** Banco do Brasil S.A. (`001` / `1`).
- **Agência:** `2365-5`.
- **Conta Corrente:** `56816-3`.
- **Titularidade:** A POSTO CASA CAIADA LTDA (CNPJ: `04.284.939/0001-86`).
- **Situação Cadastral:** Descrição no webPosto confirmada como `"BANCO DO BRASIL (56816-3)"` em `/INTEGRACAO/CONTA`. O `contaCodigo` numérico segue pendente de vinculação em `units.json` (a conta `17837` é CAIXA(POSTO) e foi sumariamente bloqueada para saídas bancárias).

### 6.3. Preservação do Recebedor Bancário e Beneficiário Econômico
- **Recebedor Bancário Original:** `Posto Real Ltda` (favorecido titular da conta de destino da transferência/PIX).
- **Beneficiário Econômico Informado:** `Márcio` (sócio / pró-labore).
- **Trilha de Auditoria:** O LOGOS mantém os dois campos dissociados de forma explícita para evitar perda de rastreabilidade bancária ou contaminação fiscal:
  - `comprovante.favorecido = "Posto Real Ltda"`
  - `comprovante.observacao_diretor = "PRÓ-LABORE — MÁRCIO"`
  - `origem_sugestao = "DECISAO_EXPRESSA_PROPRIETARIO"`
  - `data_registro = "18/10/2026"`

### 6.4. Consulta de Evidências, Duplicidade e Títulos a Pagar
- **Fechamento de Caixa de 10/10/2026:** Inspecionados `data/relatorios/caixa_2026-10-10_5555.md` e `data/cash_audit/2026-10-10/5555.json`. Não consta nenhuma saída física de dinheiro no valor de R$ 626,00.
- **Títulos a Pagar (`TITULO_PAGAR`):** Não há títulos em aberto ou baixados no valor de R$ 626,00 para a filial 5555, nem em nome de Posto Real Ltda, nem em nome de Márcio.
- **Movimentos de Conta (`MOVIMENTO_CONTA`):** Nenhum débito manual correspondente escriturado no ERP.
- **Conclusão:** Não há risco de duplicidade de lançamento.

### 6.5. Determinação da Operação Contábil no ERP
- Como **NÃO** existe título a pagar pré-cadastrado no ERP para esta obrigação, a operação contábil correta **NÃO** é uma baixa de título (`PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR`).
- A operação determinada pelo LOGOS é:
  **`OperacaoFinanceira.DESPESA_JA_PAGA`** → Lançamento direto de débito em conta bancária via:
  `POST /INTEGRACAO/V1/MOVIMENTOS_CONTA` (schema `ParametrosIncluirMovimentoConta`).

### 6.6. Trilha de Auditoria e Decisão do Proprietário
- **Origem:** `DECISAO_EXPRESSA_PROPRIETARIO`
- **Data do Registro:** `18/10/2026`
- **Autorizador:** Diretor / Proprietário
- **Classificação Registrada:** `29021 - PRO LABORE`
- **Centro de Custo:** `7295 - PISTA` (ou Administrativo)
- **Hash de Integridade:** Gerado no domínio via `calcular_hash_conteudo()`.

### 6.7. Pendência Contábil Específica (PJ × Pró-Labore)
- **Discrepância Detectada:** A transferência bancária teve como favorecido uma pessoa jurídica (**Posto Real Ltda**), porém a finalidade indicada pelo proprietário é **PRÓ-LABORE — MÁRCIO** (pessoa física / sócio).
- **Risco Contábil/Fiscal:** Pagamentos feitos a pessoas jurídicas intitulados como pró-labore podem suscitar exigência fiscal de retenção previdenciária/IRRF ou questionamentos contábeis sobre confusão patrimonial / mútuo entre filiais (já que Posto Real é unidade ligada ao mesmo grupo familiar/societário).
- **Diretriz Mandatória de Automação:** **O LOGOS NÃO substitui automaticamente a classificação indicada pelo proprietário** (mantém rigorosamente o plano `29021 - PRO LABORE`). Registra, contudo, uma **Pendência Específica de Alinhamento Contábil**: recomendação para que a contabilidade formal confirme se a contabilização deve ocorrer como pró-labore com nota explicativa de direcionamento bancário, ou se deve transitar como Adiantamento/Mútuo entre Filiais.

### 6.8. Payload Preparado para o Piloto (R$ 626,00)
```json
{
  "descricao": "PRÓ-LABORE MÁRCIO (Posto Real Ltda)",
  "data": "2026-10-10",
  "valor": 626.00,
  "conta": "<PENDENTE_ID_CONTA_BB_5555>",
  "documento": "COMPROVANTE_BB_20261010",
  "centroCusto": 7295,
  "planoConta": 29021,
  "filial": 5555,
  "contaMovimentoTipo": "DEBITO",
  "tipoPessoa": "OUTROS",
  "pessoa": null
}
```

### 6.9. Apresentação no Fluxo de Aprovação do Telegram
No Telegram, a proposta é renderizada preservando as evidências e explicitando a pendência contábil e cadastral:

```text
============================================================
           LOGOS — Despesa Reconhecida
============================================================
Unidade:       AP Casa Caiada (5555)
Favorecido:    Posto Real Ltda (Recebedor Bancário)
Beneficiário:  Márcio (Pró-labore informado pelo Proprietário)
Valor:         R$ 626,00
Documento:     Comprovante Bancário BB (10/10/2026)
Data:          10/10/2026
Classificação: PRO LABORE (29021) — Decisão expressa do proprietário
Centro Custo:  PISTA (7295)
Situação:      Despesa quitada no banco — débito confirmado (BB 56816-3)
Ação sugerida: preparar lançamento de débito em conta

⚠️ PENDÊNCIAS PARA APROVAÇÃO:
• Alerta Contábil/Fiscal: Transferência bancária destinada a PJ 
  (Posto Real Ltda) com finalidade declarada de Pró-labore (Márcio). 
  Classificação mantida como 29021. Requer validação contábil.
• Pendência Cadastral ERP: Conta bancária BB (56816-3) sem cdConta 
  vinculado em units.json. A conta 17837 é CAIXA(POSTO) e foi bloqueada.

[Aprovar]   [Corrigir Classificação]   [Rejeitar]
============================================================
```

### 6.10. Estado Final da Operação
- **Classificação:** **BLOCKED FOR IMMEDIATE ERP WRITE (COM PROPOSTA E PAYLOAD PREPARADOS)**.
- Nenhuma escrita realizada nesta etapa.

