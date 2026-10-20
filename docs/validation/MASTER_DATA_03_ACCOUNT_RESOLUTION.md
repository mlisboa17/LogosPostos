# MASTER-DATA-03 — ACCOUNT RESOLUTION
## Resolução Oficial da Conta Banco do Brasil da Casa Caiada

**Módulo:** Master Data Financeiro (`src/modules/master_data`)
**Data:** 2026-10-20
**Status:** BLOCKED PARA EXECUÇÃO EXTERNA / READY PARA PREPARAÇÃO OFFLINE
**Branch:** `feature/cash-audit-fechamento`
**Escopo:** Catálogo mestre, identificação bancária e sincronização controlada.

---

### 1. OBJETIVO E ESCOPO

O objetivo deste relatório (Agente A) é auditar e implementar os mecanismos formais de resolução da conta bancária oficial do **Banco do Brasil** para a empresa **AUTO POSTO CASA CAIADA LTDA** (`empresaCodigo=5555`), garantindo que:
1. O contrato read-only de consulta ao ERP webPosto esteja rigidamente especificado.
2. A resolução da conta seja estrita, multidimensional (6 dimensões) e deterministicamente auditável.
3. Nenhum código de conta (`contaCodigo`) seja inferido, adivinhado ou aproximado por similaridade de texto.
4. A conta transitória/caixa físico `17837 — CAIXA(POSTO)` permaneça inviolavelmente bloqueada.
5. Nenhuma chamada externa de rede ocorra sem autorização humana explícita.

---

### 2. CONTRATO READ-ONLY DE CONSULTA BANCÁRIA

O método [`MasterDataService.preparar_consulta_conta_bb_casa_caiada()`](file:///c:/Projetos/LOGOS/LogosPostos/WebPosto_API/src/modules/master_data/application/master_data_service.py) foi inspecionado e validado. Ele gera o seguinte contrato de leitura:

```json
{
  "metodo": "GET",
  "endpoint": "/INTEGRACAO/V1/CONTAS",
  "parametros": {
    "empresaCodigo": 5555,
    "limite": 100
  },
  "criterio_busca": {
    "empresa_codigo": 5555,
    "banco": "001",
    "agencia": "2365-5",
    "conta": "56816-3",
    "titular": "AUTO POSTO CASA CAIADA LTDA",
    "cnpj": "04284939000186"
  },
  "instrucoes_seguranca": [
    "Consulta estritamente read-only (GET).",
    "Nenhum token ou escrita real permitido.",
    "Avaliar correspondência exata de banco, agência, conta e titularidade.",
    "Conta 17837 NUNCA pode ser selecionada como conta bancária."
  ],
  "autorizacao_necessaria": "EXECUCAO_READ_ONLY_CONSULTA_CONTAS_CASA_CAIADA"
}
```

**Status de Execução:** Nenhuma requisição HTTP/HTTPS foi despachada para o ERP. O sistema opera 100% offline.

---

### 3. MECANISMO DE AVALIAÇÃO EM 6 DIMENSÕES

Foi implementado e integrado ao [`MasterDataService`](file:///c:/Projetos/LOGOS/LogosPostos/WebPosto_API/src/modules/master_data/application/master_data_service.py) o método `avaliar_resposta_contas_erp(criterio, contas_erp=None)`.

Para que uma conta candidata retorne o estado `ACCOUNT_CONFIRMED`, ela precisa satisfazer simultaneamente todas as 6 dimensões de integridade:

| Dimensão | Regra de Avaliação | Normalização Segura |
|---|---|---|
| **1. Empresa** | `candidato.empresaCodigo == criterio.empresa_codigo` | Inteiro exato (`5555`). Rejeição imediata se diferente. |
| **2. Banco** | `candidato.banco == criterio.banco` | Dígitos apenas, `zfill(3)` (ex: `"1"` → `"001"`). |
| **3. Agência** | `candidato.agencia == criterio.agencia` | Extração de dígitos e separação de base/DV (ex: `"2365-5"` vs `"23655"`). |
| **4. Conta** | `candidato.conta == criterio.conta` | Extração de dígitos e separação de base/DV (ex: `"56816-3"` vs `"568163"`). |
| **5. Titular** | `titular_candidato.startswith(criterio.titular)` ou vice-versa | Remoção de espaços extras, pontuações e uppercase. |
| **6. CNPJ** | `candidato.cnpj == criterio.cnpj` | Apenas dígitos (14 caracteres: `04284939000186`). |

#### Normalizações Permitidas vs Proibidas:
- **Permitidas:** Remoção de pontuações (`.`, `-`, `/`), padronização de zeros à esquerda em códigos de bancos de 3 dígitos, tratamento de dígito verificador unificado ou separado por hífen.
- **Proibidas:** Busca por similaridade difusa (fuzzy match, Levenshtein), associação por palavras parciais no nome da conta ("BB", "BANCO", "POSTO"), ou inferência de conta a partir de lançamentos anteriores.

---

### 4. MÁQUINA DE ESTADOS EXPLÍCITOS DE RESOLUÇÃO

O enum [`EstadoResolucaoConta`](file:///c:/Projetos/LOGOS/LogosPostos/WebPosto_API/src/modules/master_data/domain/models.py) governa todos os desfechos possíveis da avaliação:

```
                  ┌──────────────────────────────┐
                  │        Início Busca          │
                  └──────────────┬───────────────┘
                                 │
                   [contas_erp is None?]
                    ├── Sim ──► ACCOUNT_PENDING_AUTHORIZATION
                    │
                   [Filtro Empresa + Banco + Agência + Conta]
                    ├── 0 candidatos ──────────► ACCOUNT_NOT_FOUND
                    ├── >1 candidatos ─────────► ACCOUNT_AMBIGUOUS
                    │
                   [1 candidato localizado]
                    ├── Divergência Titular/CNPJ ──► ACCOUNT_OWNER_MISMATCH
                    ├── Sem 'contaCodigo' válido ──► ACCOUNT_CODE_MISSING
                    └── Todas as 6 dimensões OK  ──► ACCOUNT_CONFIRMED
```

1. **`ACCOUNT_PENDING_AUTHORIZATION`**: Nenhuma listagem externa foi fornecida (modo offline / aguardando autorização humana).
2. **`ACCOUNT_NOT_FOUND`**: Nenhuma conta retornada pelo ERP corresponde ao banco, agência e conta especificados para a empresa.
3. **`ACCOUNT_AMBIGUOUS`**: Mais de uma conta no ERP apresentou correspondência. **Bloqueio estrito:** zero inferência heurística; exige intervenção cadastral.
4. **`ACCOUNT_OWNER_MISMATCH`**: Conta/agência batem, mas o titular ou CNPJ associado no ERP pertence a outra entidade ou filial divergente.
5. **`ACCOUNT_CODE_MISSING`**: Conta encontrada, porém o campo identificador `contaCodigo` do ERP é nulo ou vazio.
6. **`ACCOUNT_CONFIRMED`**: Conta unicamente identificada, com código oficial do ERP e 100% de conformidade nas 6 dimensões.

---

### 5. PROIBIÇÃO PERMANENTE DA CONTA 17837 — CAIXA(POSTO)

O código garante que a conta `17837`:
- É categorizada como `TIPO_CAIXA_FISICO`.
- Possui a flag `bloqueada_para_despesa_bancaria = True`.
- Em nenhuma hipótese pode ser associada a despesas originadas de comprovantes bancários (PIX, TED, DOC, Boleto).
- Caso seja submetida a `avaliar_resposta_contas_erp()`, ela é sumariamente descartada pelo filtro bancário e gera bloqueio.

---

### 6. FIXTURES OFFLINE E EVIDÊNCIAS DE TESTES

A implementação foi validada através de 20 testes no arquivo [`test_master_data_03.py`](file:///c:/Projetos/LOGOS/LogosPostos/WebPosto_API/tests/unit/master_data/test_master_data_03.py):

- `test_01_avaliar_contas_erp_pendente_autorizacao`: Confirma retorno `ACCOUNT_PENDING_AUTHORIZATION` sem dados de rede.
- `test_02_avaliar_contas_erp_nao_encontrada`: Confirma retorno `ACCOUNT_NOT_FOUND` quando a lista não contém a conta.
- `test_03_avaliar_contas_erp_ambigua`: Simula 2 contas com a mesma agência/conta e valida retorno `ACCOUNT_AMBIGUOUS`.
- `test_04_avaliar_contas_erp_divergencia_titularidade_empresa`: Simula conta com titular de outra empresa e valida retorno `ACCOUNT_OWNER_MISMATCH`.
- `test_05_avaliar_contas_erp_codigo_ausente`: Simula conta sem `contaCodigo` e valida `ACCOUNT_CODE_MISSING`.
- `test_06_avaliar_contas_erp_confirmada_com_sucesso`: Simula payload oficial correspondente e valida resolução `ACCOUNT_CONFIRMED`.
- `test_07_ingestao_incremental_e_desbloqueio_conta`: Ingestão incremental no banco SQLite real da fixture confirmando transição de `BLOCKED` para `CONFIRMED`.
- `test_08_bloqueio_estrito_permanente_conta_17837`: Valida bloqueio absoluto da conta 17837.

---

### 7. RISCOS RESIDUAIS E PRÓXIMOS PASSOS

1. **Risco:** O ERP webPosto retornar contas com formatos de agência com hífen ou espaços que fujam do padrão brasileiro.
   - **Mitigação:** A função de normalização utiliza `re.sub(r'[^0-9A-Za-z]', '', valor)` para bases e separadores explícitos de DV.
2. **Risco:** Execução acidental de chamadas de rede.
   - **Mitigação:** O método `avaliar_resposta_contas_erp` é estritamente síncrono e recebe listas pré-carregadas. Não possui dependências de HTTP clients ou sessões.
3. **Próximo Passo:** Solicitar autorização formal para execução read-only de `GET /INTEGRACAO/V1/CONTAS?empresaCodigo=5555&limite=100` quando for o momento da homologação em ambiente real.
