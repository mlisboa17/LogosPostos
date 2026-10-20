# MASTER-DATA-03 — FINANCIAL SECURITY & EXPENSE HUNTER AUDIT
## Auditoria de Segurança, Barreira Pré-Escrita, Idempotência e Autorização

**Módulo:** Expense Hunter / Auditoria Financeira (`src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py`)
**Data:** 2026-10-20
**Status:** AUDITADO E VALIDADO OFFLINE
**Branch:** `feature/cash-audit-fechamento`
**Escopo:** Barreira pré-escrita, governança de aprovação, isolamento e proteção contra duplicação.

---

### 1. FLUXO REAL AUDITADO

O pipeline de despesas do Expense Hunter percorre a seguinte cadeia de governança:

```
[ Comprovante Extraído ]
           │
           ▼
[ Fila de Despesas ] (Detecção de duplicidade por chave sha256)
           │
           ▼
[ Aprovação Humana (Telegram/Web) ] ──► Assinatura do hash canônico (canonical_hash)
           │
           ▼
[ MasterDataService: Validação Pré-Escrita ] (Barreira de Integridade Cadastral)
     ├── Empresa ativa e cadastrada no Master Data
     ├── Conta bancária pertence à empresa pagadora
     ├── Conta bancária NÃO é caixa físico (17837) nem cofre de sangria
     ├── Plano de contas válido, ativo e compatível
     ├── Centro de custo compatível com o tipo de operação
     └── Favorecido/fornecedor validado
           │
           ▼
[ GerenciadorAutorizacaoPiloto ] (Token de liberação P0)
     ├── Validade temporal (expira em janela configurada)
     ├── Vinculado estritamente ao comprovante_id e empresa
     └── Consumo de uso único (Single-Use Token)
           │
           ▼
[ Tabela de Idempotência Local (BEGIN IMMEDIATE) ]
     ├── Status: EM_EXECUCAO
           │
           ▼
[ WebPosto ERP Adapter ] (POST /INTEGRACAO/V1/DESPESAS) ──► NUNCA EXECUTADO NESTE CICLO
```

---

### 2. AUDITORIA DOS 10 PONTOS DE CONTROLE

| # | Ponto de Controle | Mecanismo de Implementação | Comportamento Verificado | Status |
|---|---|---|---|---|
| 1 | **Bloqueio de empresas inativas** | `validar_aprovacao_para_escrita()` verifica `empresa.ativa == True`. | Impede lançamento em empresas desativadas ou suspensas. | **PASS** |
| 2 | **Bloqueio de contas de outras empresas** | `conta.empresa_codigo == dados.empresa_codigo`. | Impede uso cruzado de contas entre postos do grupo. | **PASS** |
| 3 | **Bloqueio de caixa físico e cofre** | `conta.bloqueada_para_despesa_bancaria == True` ou tipo `CAIXA_FISICO`/`COFRE`. | Rejeita explicitamente a conta `17837` e cofres. | **PASS** |
| 4 | **Validação do plano de contas** | `master_data.obter_plano_contas()` verifica existência e ativação. | Rejeita planos inválidos (ex: `99999`). | **PASS** |
| 5 | **Compatibilidade de centro de custo** | `master_data.obter_centro_custo()` valida escopo e regras ADR 004. | Rejeita centros de custo incompatíveis ou inexistentes. | **PASS** |
| 6 | **Identidade do favorecido** | Registro em log de auditoria e validação de CNPJ/CPF quando aplicável. | Registra divergência e previne substituição de beneficiário. | **PASS** |
| 7 | **Imutabilidade dos dados aprovados** | `calcular_hash_conteudo()` compara payload submetido com o aprovado. | Qualquer alteração (valor, conta, empresa) anula a aprovação. | **PASS** |
| 8 | **Idempotência de lançamento** | `IdempotenciaDespesas` com locking via `BEGIN IMMEDIATE` e hash canônico. | Comprovante repetido é detectado antes do ERP. | **PASS** |
| 9 | **Proteção de token de autorização** | `GerenciadorAutorizacaoPiloto`: status `EMITIDO` → `CONSUMIDO`, timestamp TTL. | Reutilização ou expiração resulta em erro imediato. | **PASS** |
| 10 | **Tratamento de timeout no ERP** | Registro de estado `RESULTADO_DESCONHECIDO` com bloqueio permanente. | **Nunca reexecuta automaticamente** sem confirmação oficial. | **PASS** |

---

### 3. CENÁRIOS DE SEGURANÇA TESTADOS E COMPROVADOS

No arquivo de testes [`test_master_data_03.py`](file:///c:/Projetos/LOGOS/LogosPostos/WebPosto_API/tests/unit/master_data/test_master_data_03.py), todos os cenários obrigatórios foram comprovados:

#### Cenário 1: Mesmo comprovante submetido duas vezes
- **Evidência:** `test_09_mesmo_comprovante_duplicado_bloqueado`
- **Resultado:** A segunda submissão é bloqueada com `IdempotenciaError("Operação já confirmada")`. Zero chamadas duplicadas ao ERP.

#### Cenário 2: Mesmo comprovante com alteração de valor
- **Evidência:** `test_10_comprovante_com_valor_alterado_invalida_aprovacao`
- **Resultado:** Alteração de R$ 626,00 para R$ 627,00 altera o hash de conteúdo. A aprovação anterior é invalidada e o status retorna para `aguardando_revisao`.

#### Cenário 3: Conta bancária alterada após aprovação
- **Evidência:** `test_11_conta_bancaria_alterada_invalida_aprovacao`
- **Resultado:** Modificação da conta de débito após a revisão humana invalida o hash e bloqueia o processamento.

#### Cenário 4: Empresa modificada após aprovação
- **Evidência:** `test_12_empresa_modificada_invalida_aprovacao`
- **Resultado:** Troca da empresa (ex: de 5555 para 74014) resulta em divergência de assinatura canônica e invalidação.

#### Cenário 5: Token inválido, expirado ou reutilizado
- **Evidência:** `test_13_token_piloto_invalido_expirado_reutilizado`
- **Resultado:**
  - Token inexistente: `TokenInvalidoError`.
  - Token com timestamp expirado (> TTL): `TokenExpiradoError`.
  - Token já consumido: `TokenJaUtilizadoError`.

#### Cenário 6: Tentativa de débito na conta 17837
- **Evidência:** `test_14_tentativa_debito_17837_na_barreira_escrita`
- **Resultado:** A barreira `validar_aprovacao_para_escrita()` emite `ContaNaoPermitidaParaDespesaError` com log em auditoria.

#### Cenário 7: Tentativa de débito em conta de outra empresa
- **Evidência:** `test_15_tentativa_debito_conta_outra_empresa`
- **Resultado:** A barreira pré-escrita bloqueia com `ContaNaoPertenceAEmpresaError`.

#### Cenário 8: Resposta de timeout após possível processamento remoto
- **Evidência:** `test_16_tratamento_timeout_resultado_desconhecido`
- **Resultado:** O status da operação é marcado como `RESULTADO_DESCONHECIDO`. Tentativas subsequentes de reexecução são bloqueadas preventivamente com `OperacaoPendenteConfirmacaoManualError` para evitar duplicidade de débito no ERP.

---

### 4. DECLARAÇÃO DE LIMITAÇÃO DE IDEMPOTÊNCIA DO ERP

> [!IMPORTANT]
> **Idempotência Ponta a Ponta NÃO Comprovada no ERP:**
> A idempotência local (LOGOS) está 100% validada e comprovada por testes unitários e de integração offline. No entanto, o ERP webPosto não foi testado com payloads repetidos em ambiente real, pois nenhuma escrita foi autorizada. Por isso, o sistema assume que o ERP **não** é idempotente por padrão e adota a postura de bloqueio preventivo total em qualquer cenário de dúvida ou timeout.

---

### 5. CONCLUSÃO DO AGENTE B

A barreira de segurança financeira do Expense Hunter está robusta, imutável e à prova de manipulação inadvertida. Lançamentos com dados divergentes ou reutilizações de autorização são terminantemente rejeitados antes de alcançar qualquer adaptador de rede.
