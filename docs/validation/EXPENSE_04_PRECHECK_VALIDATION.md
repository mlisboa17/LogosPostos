# Relatório de Validação e Pré-Checagem de Segurança — EXPENSE-04-PRECHECK

**Data de Execução:** 2026-10-18  
**Branch:** `feature/cash-audit-fechamento`  
**Prioridade:** P0 — Segurança Financeira e Integridade de Escrita  
**Ambiente:** Validação 100% Offline (Sem escrita real no ERP, sem chamadas externas de rede)  
**Status Final:** **READY FOR CONTROLLED PILOT** (sujeito a condições operacionais estritas)

---

## 1. Sumário Executivo

A missão **EXPENSE-04-PRECHECK** consistiu na revisão final de segurança, endurecimento de barreiras financeiras e testes offline exaustivos para viabilizar, com risco zero de escrita descontrolada, o primeiro lançamento piloto de despesas no webPosto.

Foram identificadas e corrigidas vulnerabilidades de governança no adaptador de escrita e no tratamento de callbacks, implementado o gerenciador atômico de autorização fina para o piloto (`GerenciadorAutorizacaoPiloto`) e construída uma suíte de testes dedicada cobrindo 22 requisitos mandatórios de segurança financeira.

Todas as travas físicas globais (`WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0`) permanecem intocadas no arquivo `.env`.

---

## 2. Controles Existentes e Auditoria de Segurança

Antes do início desta intervenção, o pipeline continha os seguintes controles herdados:
1. **EXPENSE-01:** Verificação de duplicidade por imagem (SHA-256) e dados financeiros, fila com governança de estados e eliminação de fallback cego de empresa.
2. **EXPENSE-02:** Proposta de aprovação estruturada com versão e hash canônico SHA-256 de 16 caracteres, botões interativos no Telegram com tickets anti-replay (`secrets.token_hex(8)`) e autorização restrita ao ID do diretor.
3. **EXPENSE-03:** Adaptador tipado estritamente aderente à OpenAPI V1 do webPosto (`POST /TITULOS_PAGAR`, `POST /MOVIMENTOS_CONTA`, `PATCH /TITULOS_PAGAR/PAGAR`, `POST /ARQUIVOS`), verificação de travas físicas `.env`, idempotência local via SQLite e auditoria append-only em `data/lancamentos_logos/<empresa>/`.
4. **EXPENSE-03-SCOPE-FIX:** Exclusão do Posto Real (`empresaCodigo 5558` e `codWeb 7`).

---

## 3. Vulnerabilidades Encontradas e Correções Aplicadas

Durante a auditoria minuciosa da pré-checagem, foram detectadas e neutralizadas 5 fragilidades críticas:

### 3.1. Vulnerabilidade 1: Expansão externa da allowlist de empresas
- **Diagnóstico:** Em `validar_unidade_autorizada`, a presença do argumento `unidades_cadastradas` executava `autorizadas.update(k for k in unidades_cadastradas.keys() if k not in (5558, 7))`. Um dicionário externo ou mock poderia injetar empresas arbitrárias no escopo do Expense Hunter.
- **Correção:** Allowlist fechada imutável `EMPRESAS_AUTORIZADAS_SET = frozenset({74014, 11495, 5555, 118508})`. Se `unidades_cadastradas` for fornecido, ele apenas confirma se a unidade permitida está cadastrada; jamais expande o conjunto.
- **Proteções extras:** Rejeição explícita de valores booleanos (`True`/`False`), strings vazias, valores `None` e identificadores de natureza estranha.

### 3.2. Vulnerabilidade 2: Contaminação de contas financeiras entre empresas
- **Diagnóstico:** `validar_aprovacao_para_escrita` conferia se `conta_financeira_codigo > 0`, mas não validava se aquela conta pertencia à empresa indicada no comprovante. Um erro humano ou proposta corrompida poderia debitar na conta de uma empresa despesas de outra.
- **Correção:** Implementação de `validar_conta_financeira_unidade` baseada no mapeamento canônico comprovado em `units.json` e no cadastro de contas do webPosto (`financial_origin_matrix.json`):
  - **74014 (Posto Doze):** `{86248, 86081, 86188}` (BB Depósito Direto, BB Cofre, PagBank)
  - **11495 (Posto VIP):** `{65321, 55028}` (Bradesco Depósito Direto, Itaú Cofre)
  - **5555 (Casa Caiada):** `{17837}` (BB Cofre "CAIXA(POSTO)", titularidade nativa comprovada da filial 5555)
  - **118508 (Conveniência 24h):** `frozenset()` — Não possui conta bancária própria (`conta_codigo: null` em `units.json`). A conta `17837` pertence exclusivamente à filial 5555; seu uso em débitos de 118508 é **estritamente BLOQUEADO por ambiguidade e contaminação inter-filiais**. Para 118508, apenas `NOVA_CONTA_A_PAGAR` é aceita até o negócio cadastrar conta bancária oficial.
  - Qualquer tentativa de usar conta de outra empresa (ex: usar 86248 em Casa Caiada ou 17837 em Conveniência 24h) é abortada com `BarreiraDespesaErro`.

### 3.3. Vulnerabilidade 3: Reexecução pós-timeout ou estado incerto na idempotência
- **Diagnóstico:** Em `IdempotenciaDespesas.iniciar_operacao`, o bloqueio de concorrência verificava apenas `estado_atual in ("CONFIRMADO", "EM_EXECUCAO")`. Se uma requisição anterior entrasse em `RESULTADO_DESCONHECIDO` (ex: timeout de rede ou resposta sem ID), uma nova chamada ao executor passava para o `UPDATE ... SET estado = 'EM_EXECUCAO'`, permitindo duplicar lançamento não confirmado.
- **Correção:** Inclusão de `"RESULTADO_DESCONHECIDO"` no conjunto de bloqueio atômico. Um item com resultado incerto fica permanentemente travado contra reenvios automáticos no SQLite até reconciliação explícita.

### 3.4. Vulnerabilidade 4: Confirmação ambígua de movimento de conta
- **Diagnóstico:** Em `confirmar_movimento_conta`, a busca via `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA` iterava sobre os resultados e retornava o primeiro registro que casasse com o valor e tipo. Se houvesse dois ou mais movimentos com o mesmo valor no mesmo dia na mesma conta, o sistema assumia o primeiro registro arbitrariamente.
- **Correção:** Implementada contagem de candidatos (`len(candidatos)`). Se houver exatamente 1 candidato, confirma; se houver múltiplos candidatos com o mesmo valor, registra alerta de ambiguidade e retorna `None`. O executor trata a confirmação como inconclusiva e transiciona para `RESULTADO_DESCONHECIDO`, impedindo vinculação a id espúrio.

### 3.5. Vulnerabilidade 5: Parsing inseguro de parâmetros de callback no Telegram
- **Diagnóstico:** Em `processar_callback_despesa`, `cod_u = int(val_param)` e `cod_p = int(val_param)` não estavam protegidos contra strings malformadas, gerando exceções não tratadas de `ValueError`.
- **Correção:** Envolvimento em blocos `try/except (ValueError, TypeError)` disparando `DespesaTelegramErro` controlado e auditável.

---

## 4. Arquitetura de Autorização Fina do Piloto

Para atender ao requisito P0 de segurança operacional sem liberar escrita indiscriminada no ERP, foi desenvolvida a solução **AutorizacaoPilotoDespesa / GerenciadorAutorizacaoPiloto**:

### 4.1. Princípios de Desenho
- **Não existe flag genérica:** Proibida flag estilo `ALLOW_ALL_WRITES=true`.
- **Dupla custódia:** Para qualquer escrita ocorrer, o sistema exige:
  1. Travas físicas globais no `.env` (`WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1`);
  2. Autorização criptográfica individual para aquela transação específica.
- **Segredo não persistido e não logado:** O token em texto puro (`secrets.token_urlsafe(32)`) é entregue uma única vez ao operador responsável. No banco SQLite é armazenado exclusivamente o hash `SHA-256` do token. O sanitizador de logs `mensagem_segura` ofusca qualquer token ou segredo.
- **Identidade exata em 8 dimensões financeiras:** O token só autoriza a operação se coincidir estritamente com:
  1. `operacao_id` (ID unívoco do item na fila);
  2. `empresa_codigo` (empresa autorizada);
  3. `tipo_operacao` (NOVA_CONTA_A_PAGAR, DESPESA_JA_PAGA ou TITULO_EXISTENTE);
  4. `valor` (valor financeiro idêntico);
  5. `hash_aprovado` (hash canônico aprovado pelo diretor);
  6. `conta_codigo` (conta financeira vinculada);
  7. `autorizador_id` (identidade do autorizador);
  8. `expira_em` (prazo máximo de tolerância, padrão 30 minutos).
- **Consumo único e atômico:** A verificação e o consumo ocorrem sob transação `BEGIN IMMEDIATE` no SQLite. Uma vez consumido (`consumida_em != None`), o token é descartado e qualquer tentativa de reuso é abortada.

---

## 5. Arquivos Modificados e Criados

| Arquivo | Ação | Finalidade |
|---|---|---|
| `WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_despesa.py` | Modificado | Endurecimento da allowlist imutável, validação de conta por empresa, bloqueio de reenvio em RESULTADO_DESCONHECIDO, detecção de ambiguidade em confirmação e suporte ao `GerenciadorAutorizacaoPiloto`. |
| `WebPosto_API/src/modules/cash_reconciliation/adapters/telegram_despesas.py` | Modificado | Proteção contra callbacks malformados com tratamento rigoroso de exceções. |
| `WebPosto_API/tests/unit/cash_reconciliation/test_expense_04_precheck.py` | Criado | Suíte oficial com 22 testes unitários offline cobrindo todos os cenários mandatórios de pré-checagem. |
| `docs/validation/EXPENSE_04_PRECHECK_VALIDATION.md` | Criado | Este relatório técnico de validação e pré-checagem. |
| `STATUS.md` | Modificado | Atualização do status operacional e registro dos controles P0. |

---

## 6. Resultados dos Testes Offline

### 6.1. Suíte Dedicada EXPENSE-04-PRECHECK (22/22 Aprovados)
```text
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
collected 22 items

WebPosto_API\tests\unit\cash_reconciliation\test_expense_04_precheck.py ...................... [100%]
============================== 22 passed in 2.04s ==============================
```

#### Cobertura dos Requisitos Mandatórios:
1. `test_01_somente_quatro_empresas_permitidas`: Valida 74014, 11495, 5555, 118508; rejeita códigos desconhecidos, nulos, booleanos e strings malformadas.
2. `test_02_posto_real_bloqueado`: Garante rejeição explícita do código 5558.
3. `test_03_codigo_7_bloqueado`: Garante rejeição explícita de codWeb 7.
4. `test_04_empresas_externas_nao_ampliam_allowlist`: Garante que cadastros externos não adicionam novas empresas à allowlist fechada.
5. `test_05_aprovacao_de_uma_despesa_nao_autoriza_outra`: Garante que o hash canônico vincula a aprovação unicamente ao ID da despesa de origem.
6. `test_06_empresa_alterada_apos_aprovacao`: Garante que alteração de empresa pós-aprovação invalida o hash e reverte para `AGUARDANDO_REVISAO`.
7. `test_07_conta_alterada_apos_aprovacao`: Garante que troca de conta pós-aprovação invalida o hash e bloqueia a escrita.
8. `test_08_valor_alterado_apos_aprovacao`: Garante que divergência de centavos invalida o hash e bloqueia a escrita.
9. `test_09_operacao_alterada_apos_aprovacao`: Garante que mudar de débito direto para baixa de título invalida a aprovação.
10. `test_10_token_piloto_vencido`: Garante rejeição de autorização após expiração do prazo estrito.
11. `test_11_token_piloto_reutilizado`: Garante bloqueio imediato na segunda tentativa de consumo do mesmo token.
12. `test_12_tentativa_operacao_fora_do_escopo`: Garante bloqueio caso o token seja submetido para outra empresa, outro item ou outro valor.
13. `test_13_timeout_em_post`: Garante marcação em `RESULTADO_DESCONHECIDO` sem qualquer retry automático.
14. `test_14_timeout_em_patch`: Garante comportamento seguro idêntico para baixa de títulos em PATCH.
15. `test_15_resultado_desconhecido_apos_reinicializacao`: Garante que o SQLite persiste o bloqueio de reenvio mesmo após reinício do processo.
16. `test_16_confirmacao_inequivoca_do_lancamento`: Garante que candidato único no GET pós-escrita confirma o lançamento com segurança.
17. `test_17_confirmacao_ambigua`: Garante que múltiplos movimentos com o mesmo valor impedem confirmação cega e marcam `RESULTADO_DESCONHECIDO`.
18. `test_18_conta_de_outra_empresa`: Garante que associar conta do Doze (86248) à Casa Caiada (5555) é bloqueado com erro contábil explícito.
19. `test_19_flags_em_zero_bloqueiam_escrita`: Garante que travas físicas desativadas impedem escrita mesmo com token de piloto válido.
20. `test_20_nenhuma_chamada_externa`: Garante 0 chamadas de rede externas através de mock transport.
21. `test_21_regressao_interoperabilidade_fluxos`: Garante interoperabilidade plena entre os modelos de EXPENSE-01, EXPENSE-02 e EXPENSE-03.
22. `test_22_testes_nao_escrevem_em_dados_operacionais_reais`: Garante isolamento estrito contra os arquivos físicos de produção.

### 6.2. Regressão Global da Suíte `cash_reconciliation`
- **Total de Testes:** 659
- **Aprovados:** 659 (100% de sucesso)
- **Falhas:** 0
- **Chamadas de Rede Reais:** 0 (Isolamento Premmia: 0 tentativas reais de navegador/portal).

---

## 7. Análise de Produção e Ambiente

### 7.1. Dependência do Job das 03:00 com o Workspace
- O repositório oficial em `C:\Projetos\LOGOS\LogosPostos` é o **mesmo diretório** do qual o Agendador de Tarefas do Windows (Task Scheduler) dispara a rotina diária `run_noturno.bat` às 03:00.
- O projeto `PROD-RELEASE-01` **não foi concluído** (paralisado na pré-checagem devido à falta de isolamento entre diretório de desenvolvimento e runtime de produção).
- A rotina noturna possui a barreira `PROD-SAFE-01`, que aborta imediatamente caso `WEBPOSTO_WRITES != 0` ou `LOGOS_ERP_ESCRITA != 0`.

### 7.2. Risco Operacional Identificado
Se o arquivo `.env` principal for temporariamente editado para `WEBPOSTO_WRITES=1` com o objetivo de testar um lançamento piloto e essa configuração não for revertida antes das 03:00, **o fechamento noturno das 03:00 será abortado pela barreira PROD-SAFE-01**.

### 7.3. Medida de Mitigação Obrigatória
O primeiro lançamento piloto **NÃO DEVE** alterar o arquivo `.env` compartilhado da raiz. O executor `executar_lancamento_despesa` aceita o parâmetro `caminho_env`, permitindo apontar para um arquivo temporário exclusivo de piloto (ex: `config/.env.piloto`) enquanto o `.env` oficial permanece estritamente em zero.

---

## 8. Condições Mandatórias para o Primeiro Lançamento Real (Piloto Controlado)

Para que o primeiro lançamento real no webPosto seja realizado, é indispensável cumprir cumulativamente:

1. **Autorização Expressa do Dono:** Confirmação explícita no chat para realizar a escrita piloto de 1 comprovante específico.
2. **Item Aprovado via Telegram:** O comprovante deve ter passado pelo ciclo de conferência do Telegram, possuindo `status = "aprovado"` e hash canônico íntegro.
3. **Emissão de Token de Piloto:** Geração de token criptográfico via `GerenciadorAutorizacaoPiloto.criar_autorizacao` com prazo máximo de 30 minutos e escopo restrito às 8 dimensões financeiras.
4. **Isolamento de Ambiente:** Utilização de arquivo de configuração isolado (`caminho_env`), preservando as flags do `.env` principal em `0`.
5. **Acompanhamento Ativo:** Monitoramento simultâneo do painel do webPosto e conferência da gravação em `data/lancamentos_logos/<empresa>/historico_despesas.json`.

---

## 9. Classificação Final

### **READY FOR CONTROLLED PILOT**

O sistema possui todas as barreiras de segurança física, lógica e criptográfica implementadas, validadas e testadas offline. Não existe possibilidade de vazamento de permissão, contaminação de contas, reenvio concorrente descontrolado ou ampliação de empresas autorizadas.

**PARADA OBRIGATÓRIA: NENHUM LANÇAMENTO REAL DEVE SER EXECUTADO SEM NOVA ORDEM EXPRESSA DO USUÁRIO.**
