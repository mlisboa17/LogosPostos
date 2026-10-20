# MASTER-DATA-03 — OFFICIAL IDENTITY & COMPANY GOVERNANCE
## Governança Cadastral das Empresas e Isolamento Operacional

**Módulo:** Master Data Financeiro (`src/modules/master_data`)
**Data:** 2026-10-20
**Status:** VALIDADO OFFLINE
**Branch:** `feature/cash-audit-fechamento`
**Escopo:** Identificação empresarial, segregação de adquirentes e governança cadastral.

---

### 1. MAPA DAS EMPRESAS DO GRUPO LOGOS

O inventário oficial consolidado no Master Data mantém a seguinte classificação e status:

| Empresa Código | CodWeb | Razão Social | CNPJ Cadastrado | Status Operacional | Elegível a Despesas? | Observação de Governança |
|---|---|---|---|---|---|---|
| **74014** | `1` | AUTO POSTO 12 DE OUTUBRO LTDA | `08.106.946/0001-09` | ATIVA | SIM | Empresa homologada |
| **11495** | `2` | AUTO POSTO VIP LTDA | `08.106.946/0002-90` | ATIVA | SIM | Empresa homologada |
| **5555** | `5` | AUTO POSTO CASA CAIADA LTDA | `04.284.939/0001-86` | ATIVA | SIM (Piloto em Prep.) | Conta BB pendente de confirmação oficial |
| **118508** | `6` | CONVENIENCIA 24 HORAS LTDA | `08.106.946/0003-70` | PENDENTE DE CONFIRMAÇÃO | NÃO | Não usa Mais Pagamentos; repassa sangria para 5555 |
| **5558** | `7` | POSTO REAL LTDA | `04.284.939/0002-67` | INATIVA / HISTÓRICA | **NÃO (BLOQUEIO P0)** | Contraparte financeira preservada; escritas proibidas |

---

### 2. AUDITORIA DA EMPRESA 118508 (CONVENIÊNCIA 24 HORAS LTDA)

A auditoria nos arquivos de configuração do sistema (`units.json` e fixtures do Master Data) revelou e confirmou os seguintes fatos arquiteturais:

1. **CNPJ Oficial Mantido como PENDENTE:**
   - O CNPJ candidato `08.106.946/0003-70` é consistente com a sequência de filiais do grupo (matriz `0001-09`, filial VIP `0002-90`), porém permanece classificado formalmente como `PENDENTE` até que seja retornado pela chamada read-only oficial do endpoint `/INTEGRACAO/EMPRESAS`.
   - **Critério de Aceite Atendido:** Nenhuma promoção de `PENDENTE` para `CONFIRMADO` foi executada.

2. **Isolamento de Adquirentes e Fluxos da Mais Pagamentos:**
   - A Conveniência 24h **NÃO opera com a Mais Pagamentos**.
   - No arquivo `units.json`, a seção de adquirentes para a unidade `conveniencia_24h` possui apenas:
     - `PAGBANK`
     - `CIELO`
     - `PREMMIA`
   - O flag `usa_mais_pagamentos` está definido e auditado como `False`.
   - A configuração de sangria de caixa estabelece `repasse_sangria_para = 5555` (Casa Caiada), com destino de conta bancária próprio nulo (`destinos.conta_codigo = null`).

3. **Validação por Teste:**
   - O teste `test_18_conveniencia_24h_nao_usa_mais_pagamentos` em [`test_master_data_03.py`](file:///c:/Projetos/LOGOS/LogosPostos/WebPosto_API/tests/unit/master_data/test_master_data_03.py) garante que a Conveniência 24h não é aceita em jobs ou parsers da Mais Pagamentos.

---

### 3. BLOQUEIO ESTRITO DO POSTO REAL (EMPRESA 5558 / CODWEB 7)

1. **Inatividade Operacional:**
   - O Posto Real está registrado com `ativa = False`.
   - Na barreira pré-escrita [`validar_aprovacao_para_escrita()`](file:///c:/Projetos/LOGOS/LogosPostos/WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py), qualquer tentativa de emissão de despesa tendo `5558` como pagadora falha com `EmpresaInativaError`.
   - No `MasterDataService`, `obter_empresa(5558)` retorna a entidade com o status inativo.

2. **Preservação Histórica e Distinção de Contraparte:**
   - O Posto Real foi historicamente favorecido em transações financeiras (ex: recebimento de aluguel ou repasse de despesas via PIX).
   - O teste `test_20_distincao_entre_empresa_operacional_e_recebedor_bancario` valida que o Posto Real pode ser registrado no catálogo de fornecedores/favorecidos como contraparte bancária sem que isso o habilite como empresa emitente de despesas.
   - **Critério de Aceite Atendido:** Nenhum registro histórico do Posto Real foi apagado.

---

### 4. CONTRATO READ-ONLY DE CONSULTA DE EMPRESAS

Para permitir a confirmação futura da identidade cadastral da Conveniência 24h e a checagem das demais entidades, foi implementado o método [`MasterDataService.preparar_consulta_empresas_oficial()`](file:///c:/Projetos/LOGOS/LogosPostos/WebPosto_API/src/modules/master_data/application/master_data_service.py):

```json
{
  "metodo": "GET",
  "endpoint": "/INTEGRACAO/EMPRESAS",
  "parametros": {},
  "instrucoes_seguranca": [
    "Consulta estritamente read-only (GET).",
    "Nenhuma escrita ou mutação permitida.",
    "Utilizar retorno para confirmar CNPJ da Conveniência 24h e validar situação cadastral.",
    "Registrar evidências no log de auditoria do Master Data."
  ],
  "autorizacao_necessaria": "EXECUCAO_READ_ONLY_CONSULTA_EMPRESAS_OFICIAL"
}
```

O teste `test_17_preparar_consulta_empresas_oficial` comprova o formato exato deste contrato. Nenhuma chamada de rede foi realizada.

---

### 5. CONCLUSÃO DO AGENTE C

A governança corporativa e o isolamento cadastral do Master Data estão rigorosamente assegurados:
- A Conveniência 24h está isolada dos fluxos da Mais Pagamentos e seu CNPJ segue categorizado como pendente de auditoria online.
- O Posto Real está permanentemente bloqueado para novas operações financeiras.
- As distinções entre empresas pagadoras e favorecidos estão auditadas e preservadas.
