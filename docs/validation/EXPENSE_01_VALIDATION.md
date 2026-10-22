# LOGOS — EXPENSE-01: Validação de Integridade da Fila, Anti-duplicidade e Revisão Obrigatória

**Data:** 17/10/2026 21:45  
**Branch Canônica:** `feature/cash-audit-fechamento`  
**Prioridade:** P0 — Integridade financeira e prevenção de duplicidade  
**Modo:** READ ONLY (nenhuma escrita no ERP webPosto, travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` rigorosamente mantidas)  
**Documentos de Referência:**
- [STATUS.md](../../STATUS.md)
- [EXPENSE_AUDIT_01_CURRENT_STATE.md](EXPENSE_AUDIT_01_CURRENT_STATE.md)
- [ARCH_MODULE_01_CURRENT_STRUCTURE.md](../architecture/ARCH_MODULE_01_CURRENT_STRUCTURE.md)
- [REGRAS_DE_NEGOCIO.md](../regras-negocio/REGRAS_DE_NEGOCIO.md) (RN-ERP-003, ADR-003)

---

## 1. Resumo das Mudanças

Neste primeiro incremento do Expense Hunter (**EXPENSE-01**), foram implementadas as garantias essenciais de segurança, governança e integridade operacional antes de qualquer escrita no ERP:
1. **Remoção do Fallback de Empresa:** Eliminada qualquer atribuição automática e cega da empresa Posto Doze (`74014`) quando a conta de débito ou evidência textual não forem unívocas. Unidades ambíguas agora assumem `EMPRESA_INDEFINIDA` e exigem revisão humana compulsória (`aguardando_revisao`).
2. **Anti-Duplicidade de Comprovante (SHA-256):** O arquivo original (foto, PDF ou áudio) tem seu hash SHA-256 calculado. Se o mesmo documento for reenviado, o sistema não gera um novo item financeiro na fila, aponta para o registro preexistente e notifica o diretor.
3. **Segregação de Despesa Duplicada:** Documentos diferentes (hashes distintos) que representam a mesma despesa (mesmo valor, data e favorecido) não são descartados às cegas: eles são registrados com `alerta_duplicidade` e forçados para `aguardando_revisao`, impedindo aprovação inadvertida.
4. **Proteção de Transação Bancária (FITID + Conta):** O vínculo financeiro agora valida a trinca unívoca `(banco, conta, fitid)`. Débitos já consumidos por outros itens ativos na fila são ignorados para novos comprovantes. Além disso, extratos sem identificação de conta (`conta_sufixo` ausente) não realizam vínculo automático.
5. **Máquina de Estados Conforme ADR-003:** Implementada a máquina de estados formal (`recebido`, `aguardando_revisao`, `aguardando_aprovacao`, `aprovado`, `rejeitado`, `lancamento_solicitado`, `lancado_erp`, `falha`, `resultado_desconhecido`). **Nenhum comprovante recém-processado nasce aprovado.** Transições para `aprovado` exigem ação humana explícita e registram trilha auditável (`TransicaoFila`).
6. **Compatibilidade Retroativa:** Registros antigos de `fila.json` que possuíam status como `"pronto para lançar"` continuam sendo lidos perfeitamente, mas seu status canônico é tratado como `aguardando_aprovacao` (nunca aprovado retroativamente).

---

## 2. Arquivos Modificados

| Arquivo | Natureza da Modificação |
|---|---|
| `WebPosto_API/src/modules/cash_reconciliation/domain/comprovante.py` | Criação do enum `StatusDespesa`, modelo `TransicaoFila`, mapeamento legado `LEGACY_STATUS_MAP`, novos campos `arquivo_sha256`, `debito_casado_conta`, `alerta_duplicidade`, `duplicado_de_id` e propriedade `chave_transacao_bancaria`. |
| `WebPosto_API/src/modules/cash_reconciliation/application/fila_despesas.py` | Adicionada exceção `TransicaoInvalidaErro`, tabela `TRANSICOES_VALIDAS`, funções de busca `buscar_item_por_sha256`, `buscar_item_por_transacao_bancaria`, `buscar_possiveis_duplicatas` e função de transição validada `transicionar_status`. |
| `WebPosto_API/src/modules/cash_reconciliation/application/processar_comprovante.py` | Cálculo do SHA-256 do arquivo original, verificação prévia de documento duplicado, proteção contra reutilização de FITID na mesma conta, eliminação total do fallback para Doze (74014), verificação de alerta de duplicidade e transição explícita de estados. |
| `WebPosto_API/tests/unit/cash_reconciliation/test_comprovantes_fila.py` | Atualização das asserções de status legado para `StatusDespesa` e criação de 14 novos testes unitários cobrindo todos os cenários exigidos pela especificação. |

Nenhum arquivo foi movido. Nenhum módulo novo foi criado.

---

## 3. Regras de Anti-Duplicidade e Integridade

### A. Documento Duplicado (Mesmo Arquivo)
- **Identificação:** `arquivo_sha256 = hashlib.sha256(arquivo_bytes).hexdigest()`.
- **Ação:** Se já existir item ativo na fila com o mesmo hash:
  - Não cria um segundo registro financeiro na fila;
  - Marca `duplicado_de_id = id_existente`;
  - Responde ao diretor: `"Comprovante já recebido anteriormente (ID: ..., status: ...). O arquivo é idêntico e não foi duplicado na fila."`

### B. Possível Despesa Duplicada (Arquivos Diferentes, Mesma Despesa)
- **Identificação:** Hashes diferentes, mas mesmo valor, data (±2 dias) e favorecido similar ou mesmo débito bancário.
- **Ação:** Cria o item na fila para auditoria e rastreabilidade, mas define:
  - `alerta_duplicidade = "Possível despesa duplicada: coincide com item ... (R$ ...)"`;
  - Status forçado para `aguardando_revisao`;
  - Resposta alerta o diretor sobre a necessidade de conferência humana antes de qualquer avanço.

### C. Proteção de FITID e Conta Bancária
- **Chave Unívoca da Transação:** `(banco, conta, fitid)`.
- **Prevenção de Colisão:**
  - O mesmo `fitid` não pode ser reutilizado para comprovar despesas distintas na mesma conta;
  - Se outro comprovante já consumiu o débito bancário, o novo comprovante não realiza matching e fica como `aguardando_revisao`;
  - O mesmo `fitid` em contas bancárias distintas é permitido, pois bancos diferentes podem gerar sequenciais coincidentes.
- **Contas Não Confiáveis:** Se o extrato vier sem `conta_sufixo`, o matching automático é bloqueado por segurança.

---

## 4. Remoção do Fallback de Empresa

### Como era:
Quando o extrato não casava ou a conta era ambígua, o código executava:
```python
# CÓDIGO ANTERIOR (PERIGOSO):
if not unidade_encontrada:
    if "PAGBANK" in banco_encontrado or "DOZE" in normalizar_texto(texto_complementar):
        unidade_encontrada = unidades_map.get(74014)
    elif unidades_map:
        unidade_encontrada = next(iter(unidades_map.values()))
unidade_cod = unidade_encontrada.empresa_codigo if unidade_encontrada else 74014
unidade_nome = unidade_encontrada.nome if unidade_encontrada else "POSTO DOZE FILIAL II"
```
Esse fallback causava risco severo de lançar despesas de outras unidades (Posto VIP, Casa Caiada, Real) na filial do Posto Doze.

### Como ficou:
A empresa só é atribuída se houver **evidência confiável**:
1. Conta bancária do extrato cadastrada explicitamente na unidade (`contas_extrato` em `units.json`); OU
2. Menção inequívoca e exclusiva no texto complementar do diretor ("posto vip", "casa caiada", "doze").
3. **Sem evidência confiável:**
   ```python
   unidade_cod = None
   unidade_nome = "EMPRESA_INDEFINIDA"
   unidade_apelido = "INDEFINIDA"
   ```
   O item transiciona compulsoriamente para `aguardando_revisao` e é **terminantemente impedido de transicionar para `aguardando_aprovacao` ou `aprovado`** até que a empresa seja revisada.

---

## 5. Máquina de Estados e Governança

### Estados Implementados
1. `recebido`: Estado de entrada imediata do comprovante.
2. `aguardando_revisao`: Pendente de conciliação bancária, definição de categoria contábil, resolução de empresa indefinida ou conferência de alerta de duplicidade.
3. `aguardando_aprovacao`: Todos os dados preenchidos e conciliados (empresa identificada, extrato casado, categoria sugerida e sem duplicidade). Aguardando deliberação humana.
4. `aprovado`: Autorizado expressamente por usuário humano com permissão. Proibido disparar via sistema.
5. `rejeitado`: Descartado pelo diretor.
6. `lancamento_solicitado`: Disparo do envio ao webPosto (não acionado nesta sprint).
7. `lancado_erp`: Confirmado após sucesso e anexo no webPosto (não acionado nesta sprint).
8. `falha`: Erro de validação ou timeout (não acionado nesta sprint).
9. `resultado_desconhecido`: Incerteza pós-timeout pendente de checagem via `GET` (não acionado nesta sprint).

### Trilha de Auditoria (`historico_transicoes`)
Cada transição gera um registro atômico contendo:
- `de_status`: estado anterior;
- `para_status`: novo estado;
- `motivo`: razão explícita da transição;
- `origem`: agente da transição (`"sistema"`, `"diretor_telegram"`, `"revisao_manual"`);
- `timestamp`: instante ISO 8601;
- `usuario`: identificador do operador humano quando aplicável.

---

## 6. Cobertura de Testes Unitários Offline

Foram implementados e verificados **14 testes unitários obrigatórios** em `WebPosto_API/tests/unit/cash_reconciliation/test_comprovantes_fila.py`:

| # | Teste | Cenário Validado |
|---|---|---|
| 1 | `test_expense_01_01_upload_comprovante_novo` | Upload de novo comprovante calcula SHA-256 e registra trilha com `recebido` e `aguardando_aprovacao`. |
| 2 | `test_expense_01_02_mesmo_arquivo_enviado_novamente` | Arquivo idêntico não cria novo item na fila; aponta para o anterior com aviso de duplicidade. |
| 3 | `test_expense_01_03_fotos_diferentes_mesma_despesa` | Arquivos diferentes para mesma despesa geram `alerta_duplicidade` e forçam status `aguardando_revisao`. |
| 4 | `test_expense_01_04_empresa_nao_identificada` | Comprovante sem conta/menção confiável registra `EMPRESA_INDEFINIDA` e status `aguardando_revisao`. Fallback Doze eliminado. |
| 5 | `test_expense_01_05_empresa_identificada_corretamente` | Extrato casado com conta da unidade 74014 resolve empresa corretamente como `POSTO DOZE FILIAL II`. |
| 6 | `test_expense_01_06_fitid_repetido_na_mesma_conta` | Débito bancário já usado por um item ativo não pode ser vinculado a outro comprovante da mesma conta. |
| 7 | `test_expense_01_07_fitid_igual_em_contas_diferentes` | Chave bancária considera `(banco, conta, fitid)`, permitindo matching em contas distintas sem falsa colisão. |
| 8 | `test_expense_01_08_fitid_sem_identificacao_confiavel_da_conta` | Extrato sem `conta_sufixo` não realiza vínculo financeiro automático; item fica em `aguardando_revisao`. |
| 9 | `test_expense_01_09_persistencia_e_leitura_registros_anteriores` | Registros legados com `status: "pronto para lançar"` são lidos perfeitamente e tratados como `aguardando_aprovacao` (não aprovados). |
| 10 | `test_expense_01_10_recuperacao_apos_interrupcao` | Gravação atômica via `.tmp` e leitura resiliente mesmo com resíduos de interrupção em disco. |
| 11 | `test_expense_01_11_transicoes_validas_e_invalidas` | Validação de transições permitidas e bloqueio de transições inválidas (ex: direto para aprovado ou com empresa indefinida). |
| 12 | `test_expense_01_12_nenhum_registro_criado_como_automaticamente_aprovado` | Garantia de que novos comprovantes nunca nascem nos status `aprovado`, `lancamento_solicitado` ou `lancado_erp`. |
| 13 | `test_expense_01_13_nenhum_write_erp_realizado` | Confirmação de que `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` permanecem zerados e sem acionamento. |
| 14 | `test_expense_01_14_nenhuma_chamada_real_externa` | Isolamento estrito com mock extractor e diretórios temporários, sem chamadas ao Gemini, Telegram ou webPosto. |

---

## 7. Riscos e Recomendações

1. **Revisão de Empresas Indefinidas:** Quando uma despesa for paga por PIX pessoal de sócio sem vínculo imediato a uma conta bancária da empresa, ela permanecerá em `aguardando_revisao`. No Incremento 3, a interface do Telegram deverá oferecer botões rápidos para o diretor selecionar a qual posto a despesa pertence (`[Posto Doze]`, `[Posto VIP]`, `[Casa Caiada]`).
2. **Histórico Local de Fila:** A fila `data/despesas_avulsas/fila.json` é a fonte da verdade local do Expense Hunter e está adequadamente ignorada no Git. Recomenda-se manter rotina periódica de backup em diretório seguro do servidor.
3. **Escrita no webPosto Mantida Inerte:** Nenhuma chamada de escrita foi construída ou liberada. As travas `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0` continuam protegendo o ambiente.

---

## 8. Próximo Incremento Recomendado

- **Incremento 2 (EXPENSE-02):** Preparar comandos financeiros tipados (`ParametrosIncluirMovimentoConta` e `PagarTituloDto`) e validar contratos em testes offline, modelando estritamente os payloads das Operações B e C sem executar requisições HTTP reais.
