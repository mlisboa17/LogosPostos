# LOGOS — MASTER-DATA-05: Relatório de Evidências da Conta Bancária (Conta 27173)
## Bank Account Identity Evidence Review — Casa Caiada (Filial 5555)

**Data:** 22/10/2026  
**Repositório:** `C:\Projetos\LOGOS\LogosPostos`  
**Branch:** `feature/cash-audit-fechamento`  
**Checkpoint Base:** `3e1c2f8` (MASTER-DATA-04)  
**Prioridade:** P0  
**Status da Conta 27173:** **BLOCKED**  
**Status do Piloto Casa Caiada:** **BLOCKED**  
**Escritas no ERP:** **ZERO (0)**  
**Chamadas Externas:** **ZERO (0)**  

---

### 1. OBJETIVO DA INVESTIGAÇÃO

Determinar documentalmente e tecnicamente se o código de conta **`27173`** no ERP webPosto corresponde comprovadamente à conta corrente do **Banco do Brasil**, agência **`2365-5`**, conta **`56816-3`**, de titularidade de **`AUTO POSTO CASA CAIADA LTDA`** (`empresaCodigo: 5555`, CNPJ: `04.284.939/0001-86`).

Esta investigação é estritamente local e baseada em evidências fáticas auditáveis já residentes no projeto, sem execução de novas requisições de rede ou modificações no ERP.

---

### 2. INVESTIGAÇÃO CADASTRAL DA CONTA 27173 (AGENTE A)

#### 2.1. Origem Histórica da Classificação TRANSITORIA
1. **Primeira Aparição:** A conta `27173` surgiu no projeto durante a execução do scan/probe inicial da API webPosto (`webposto_network_probe_result.json`, linhas 165-190). Na ocasião, o endpoint `/INTEGRACAO/CONTA` retornou 17 identificadores numéricos de contas da rede (`17837, 20936, 27173, 27406, ...`), porém os snapshots persistidos em `financial_origin_matrix.json` armazenaram apenas uma amostra superficial (`sampleRow` = `17837`), descartando as filiais e descrições detalhadas de cada conta.
2. **Ingestão no Catálogo Local SQLite (`master_data.sqlite3`):**
   - No bootstrap do catálogo mestre em 21/10/2026 14:33:44 (`MasterDataService._obter_contas_iniciais()`, linhas 352-361 de `master_data_service.py`), a conta `27173` foi inserida na tabela `master_contas_financeiras`.
   - **Metadados Persistidos:**
     - `conta_codigo`: `27173`
     - `empresa_codigo`: `None` (não associada a nenhuma filial)
     - `descricao`: `"CONTA TRANSITORIA 27173"`
     - `tipo_conta`: `"TRANSITORIA"`
     - `banco_codigo`: `None`, `agencia`: `None`, `conta_numero`: `None`
     - `ativo`: `1` (True)
     - `permite_debito_despesa`: `0` (False)
     - `confiabilidade`: `"HISTORICO"`
     - `origem_dado`: `"webposto_probe"`
     - `atualizado_em`: `"2026-10-21T14:33:44.079632+00:00"`
3. **Registro na Trilha de Auditoria (`master_data_audit_log`):**
   - `audit_id`: `21`
   - `tipo_entidade`: `"CONTA_FINANCEIRA"`
   - `identificador`: `"27173"`
   - `acao`: `"INSERCAO"`
   - `origem`: `"bootstrap_master_data"`
   - `timestamp`: `"2026-10-21T14:33:44.351846+00:00"`

#### 2.2. Avaliação de Comprovação: Comprovada vs. Inferida
- **CONCLUSÃO INEQUÍVOCA:** A classificação como `"TRANSITORIA"` foi **INFERIDA PREVENTIVAMENTE**, **NÃO COMPROVADA**.
- **Fundamento:** Como o retorno preliminar do probe não continha o mapeamento estruturado de qual empresa era dona de cada conta, a arquitetura do LOGOS aplicou o princípio de segurança *fail-closed*: todas as contas órfãs de empresa foram rotuladas preventivamente como `TRANSITORIA` e marcadas com `permite_debito_despesa = False`.
- Portanto, **não existe evidência contábil no webPosto de que a conta 27173 seja uma conta transitória de fato**. Trata-se exclusivamente de um rótulo de retenção defensiva no LOGOS.

#### 2.3. Vínculos e Regras Internas Existentes
- **`units.json`:** A filial `5555` possui apenas a conta `17837` mapeada como cofre/caixa físico (`"destino_padrao": 17837`). A conta `27173` **não consta** em `units.json`.
- **`webposto_escrita_despesa.py`:** A allowlist imutável `CONTAS_AUTORIZADAS_POR_UNIDADE[5555]` contém apenas `{17837}`. A conta `27173` **não está autorizada**.
- **Nenhum job em produção:** O fechamento noturno das 03:00 e os jobs de sangria ignoram `27173`.

---

### 3. CORRELAÇÃO DE EVIDÊNCIAS E CONFRONTO DE FONTES (AGENTE B)

#### 3.1. Dados Extraídos do Extrato Oficial do Banco do Brasil
No projeto residem os arquivos oficiais do extrato de Setembro/2026 da Casa Caiada:
1. **Extrato OFX:** `C:\Projetos\LOGOS\extratos\BB\BancoBrasil_CasaCaiada_SETEMBRO2026.ofx`
   - `<FI><ORG>Banco do Brasil</ORG><FID>1</FID></FI>`
   - `<BANKACCTFROM>`
     - `<BANKID>1</BANKID>` (Código compensação Banco do Brasil: `001`)
     - `<BRANCHID>2365-5</BRANCHID>` (Agência)
     - `<ACCTID>56816-3</ACCTID>` (Conta Corrente)
     - `<ACCTTYPE>CHECKING</ACCTTYPE>`
2. **Extrato PDF:** `C:\Projetos\LOGOS\extratos\BB\BancoBrasil_CasaCaiada_SETEMBRO2026.pdf` (Pág. 1)
   - `Cliente: A POSTO CASA CAIADA LTDA`
   - `Agência: 2365-5`
   - `Conta: 56816-3`
   - `Período: 01 a 30/09/2026`
   - Lançamento PIX (pág. 1): `01/09 18:11 04284939000186 AUTO POSTO` comprovando o CNPJ `04.284.939/0001-86`.

#### 3.2. Comparação com o Retorno Oficial do webPosto (MASTER-DATA-04)
Na consulta read-only oficial realizada em 21/10/2026 (`GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100`), o ERP retornou o registro exato:
```json
{
  "empresaCodigo": 5555,
  "contaCodigo": 27173,
  "descricao": "BANCO DO BRASIL (56816-3)",
  "saldoAtual": -8685811.91,
  "ativo": true,
  "usaOfx": false,
  "codigo": 27173
}
```

#### 3.3. Matriz de Evidências por Atributo
Abaixo, a comparação rigorosa entre as exigências de identificação e as fontes disponíveis:

| Atributo | Exigência da Conta Bancária | Valor no Extrato Oficial BB | Valor no Endpoint `/CONTAS` (27173) | Nível de Confiabilidade | Status de Comprovação |
|---|---|---|---|---|---|
| **1. Empresa / Filial** | Filial 5555 (Casa Caiada) | Titular Casa Caiada | `empresaCodigo: 5555` | **OFICIAL / ERP (100%)** | **CONFIRMADO** |
| **2. Banco** | `001` (Banco do Brasil) | `<BANKID>1</BANKID>` / `<ORG>Banco do Brasil</ORG>` | `"BANCO DO BRASIL"` (na descrição) | **ALTA / COMPATÍVEL (99%)** | **CONFIRMADO (TEXTUAL)** |
| **3. Agência** | `2365-5` | `<BRANCHID>2365-5</BRANCHID>` | *Não fornecido* | **AUSENTE NO ERP (0%)** | **PENDENTE DE COMPROVAÇÃO NA TELA DO ERP** |
| **4. Conta Corrente** | `56816-3` | `<ACCTID>56816-3</ACCTID>` | `"(56816-3)"` (na descrição) | **OFICIAL / ERP (100%)** | **CONFIRMADO (TEXTUAL)** |
| **5. Titular** | AUTO POSTO CASA CAIADA LTDA | `A POSTO CASA CAIADA LTDA` | *Não fornecido* | **AUSENTE NO RETORNO DE CONTAS** | **CONFIRMADO VIA FILIAL 5555** |
| **6. CNPJ** | `04.284.939/0001-86` | `04284939000186` (PIX Extrato) | *Não fornecido* | **AUSENTE NO RETORNO DE CONTAS** | **CONFIRMADO VIA FILIAL 5555** |

#### 3.4. Regra Anti-Presunção
- **Fato:** A descrição `"BANCO DO BRASIL (56816-3)"` no `contaCodigo: 27173` vinculada à filial `5555` é um indício documental contundente (não existe nenhuma outra conta BB para a filial 5555).
- **Ressalva de Auditoria:** O endpoint `/INTEGRACAO/V1/CONTAS` comprovadamente **não possui colunas estruturadas para agência, titular ou CNPJ**. Logo, o número da conta isoladamente, sem a confirmação do campo estruturado da agência `2365-5` na interface web do webPosto ou declaração expressa do proprietário, não cumpre formalmente o critério de 6 dimensões automatizado do `MasterDataService`.

#### 3.5. Dados que Exigem Comprovação Complementar
Para eliminação de 100% da dúvida residual, deve-se:
1. Inspecionar visualmente na interface do webPosto (`Financeiro > Cadastros > Contas / Bancos`) se a conta de código `27173`:
   - Possui o campo Agência preenchido como `2365-5` ou `2365`;
   - Possui o campo Banco preenchido como `001 - Banco do Brasil`;
   - Está vinculada à filial `5555 - AUTO POSTO CASA CAIADA LTDA`.
2. OU obter a **Autorização Formal do Diretor/Proprietário** reconhecendo expressamente que a conta `27173` é a conta BB `2365-5 / 56816-3`.

---

### 4. GOVERNANÇA E CONTROLE DE IMPACTO (AGENTE C)

1. **Conta 17837 Preservada:** A conta `17837 — CAIXA(POSTO)` permanece terminantemente bloqueada para saídas e despesas bancárias (`permite_debito_despesa = False`).
2. **Isolamento de Despesas:** Nenhuma despesa do robô utiliza ou utilizará a conta `27173` de maneira automática.
3. **Piloto de R$ 626,00 Bloqueado:** Permanece em estado `BLOCKED` no gate de segurança.

---

### 5. CONCLUSÃO DO AGENTE REVISOR

A conta **`27173`** é comprovadamente a única conta do Banco do Brasil cadastrada na filial 5555 do webPosto e ostenta o número exato da conta corrente `56816-3`. Sua anterior classificação como `TRANSITORIA` foi fruto exclusivo de um mecanismo defensivo do LOGOS, e não de sua natureza real no ERP.

Contudo, pela ausência da agência `2365-5` no payload do endpoint `/INTEGRACAO/V1/CONTAS`, o status operacional permanece:
**ACCOUNT 27173: BLOCKED** até deliberação humana formal ou conferência em tela.
