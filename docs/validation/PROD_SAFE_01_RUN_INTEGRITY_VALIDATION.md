# PROD-SAFE-01 — integridade do run e publicação fail-closed

Data: 16/10/2026. Branch: `feature/cash-audit-fechamento`. Base: `76cd8e2`.
Sem commit, push, merge, deploy, alteração de tarefa Windows ou execução real do job.

## 1. Causa raiz e limite do incidente

Base: [auditoria](LOGOS_CURRENT_CAPABILITY_AUDIT.md) e
[PROD-SAFE-00](PROD_SAFE_00_JOB_FRESHNESS_DIAGNOSIS.md).
O `main` chamava a publicação depois de `executar`, inclusive após retorno 1.
O publicador recarregava snapshots pela data, sem vínculo com a tentativa atual.
A planilha também podia preencher zeros quando faltava fechamento.

Em **16/10, às 03:00**, houve barreira **local**, não falha do fornecedor:
`WEBPOSTO_WRITES != "0"` no modo não automático. Task iniciou 03:00:01,
retornou 1 e o ledger marcou envio às 03:00:45. Não se investigou o valor
privado/origem efetiva da variável. Não havia snapshots de 15/10 e o MD
avisava que a conferência não rodou. **Não há prova de números antigos
publicados como atuais nesse episódio**; o risco estrutural estava no código.

O bootstrap já resolvia `.env` pelo caminho absoluto do módulo, não pelo cwd.
Foi explicitado em `CAMINHO_ENV`, mantendo `load_dotenv(..., override=False)`.
Não foi encontrada evidência para atribuir o incidente a resolução de caminho.
Configuração herdada ainda tem precedência; configuração ausente/inválida não
libera a execução financeira.

## 2. Fluxo e evidência implementados

```text
main: criar run_id → persistir tentativa → load_dotenv absoluto
  → validar configuração somente leitura
  → declarar fontes esperadas por unidade
  → Premmia opcional → fechamento vivo → recebimentos vivos → fontes locais
  → snapshots e pendências locais → placar com coleta forçada
  → validar registros/run/data/horário/cobertura → finalizar e classificar
  → COMPLETE: resumo financeiro; PARTIAL/FAILED: somente aviso operacional
  → Telegram: repetir gate, usar resultados em memória
  → persistir delivery separado, sem alterar audit status por causa da entrega
```

`ExecucaoNoturna` usa UUID local, início/fim no fuso existente, dia de negócio,
versão `PROD_SAFE_01`, fontes/motivos, `audit_status`, `delivery_status` e
`document_delivery_status`. A coleta usa esse mesmo ID na proveniência diária.
O placar vivo é relacionado ao run somente após validar escopo e timestamp.

A persistência atômica existente grava
`data/resumos/execucoes/<run_id>.json`: tentativa inicial, resultado final e
resultado de entrega. O estado de saúde recebe campo opcional `execucao`;
JSONs legados continuam legíveis. O arquivo por run é a evidência final de
delivery; o estado de saúde é gravado antes do envio. Snapshots legados sem
`fontes_execucao` **não** servem como prova de coleta corrente.

### Estados determinísticos

| Fonte | Interpretação |
|---|---|
| `SUCCESS` | Consulta/validação executada com resultado válido |
| `EMPTY_VALID` | Consulta concluída e ausência permitida pelo contrato |
| `FAILED` | Tentativa ou conclusão/persistência falhou |
| `BLOCKED` | Barreira de configuração/regra impediu execução |
| `STALE` | Evidência fora do run, horário, referência ou cobertura |
| `NOT_COLLECTED` | Fonte esperada sem evidência de processamento |

Todas as obrigatórias válidas: `AUDIT_COMPLETE`; parte delas válida:
`AUDIT_PARTIAL`; nenhuma válida: `AUDIT_FAILED`. Configuração válida sozinha
não promove uma coleta falha a PARTIAL. Publicação também exige run terminado.
Ausência de escopo/unidades, registro faltante, duplicado ou fora do escopo
bloqueia composição; não equivale a dia válido sem movimento.

## 3. Política por fluxo e prova de frescor

| Fonte/caminho | Obrigação neste job | Evidência/critério |
|---|---|---|
| Configuração | Obrigatória | `WEBPOSTO_WRITES` exatamente `0`; modo automático desligado |
| Fechamento por unidade | Obrigatório | Consultas vivas de caixas, apresentado, sangrias, vales e movimentações; run/dia/timestamp |
| PagBank ou outra adquirente não Premmia, não pendente | Obrigatória no recebimento configurado | Resultado da conciliação viva e consultas D−1/D/D+1; credencial inválida agora impede resumo normal |
| Adquirente configurada pendente | Degradável, como antes | Sem adapter novo nem promessa de conferência |
| Premmia | Opcional/degradável | Dia e `Coletado em` originais da aba Coletas; arquivo antigo vira STALE, valores omitidos da publicação |
| Mais | Opcional, declaração local, não portal | Validação atual de unidade/dia e comparação; preserva `informado_em` original |
| PIX CNPJ/OFX | Opcional, arquivo local | Validação atual de banco/conta/cobertura/FITID e contexto vivo; preserva hashes OFX |
| Placar no job composto | Obrigatório naquele fluxo combinado | Coleta forçada, sem snapshot/cache, posto/dia/horário do run |
| Nomes, administradora PIX, histórico de pendências/recorrência | Degradáveis/contextuais | Não substituem saldo ou coleta do dia; avisos existentes mantidos |

Não foi criada obrigação global para Premmia, Mais ou OFX. Para o caminho
composto agendado, falha comercial já era erro técnico do job; conservadoramente
também impede publicação normal nessa composição. A política não altera os
endpoints manuais de consulta/histórico.

Para fontes remotas obrigatórias: ID do run igual, data de referência igual,
timestamp entre início e fim e cobertura contendo o dia. Metadados vêm da
fronteira de consulta viva, não de recarimbar um JSON encontrado no disco.
O registro diário também precisa ter proveniência atual e todas as evidências
esperadas. Falha da coleta atual nunca faz fallback para snapshot do mesmo dia.
Timestamp e ID antigos são preservados quando o dado é marcado STALE.

**Limite da prova:** demonstra chamada/validação corrente pelo Logos e seu
escopo, não certifica atualização interna do fornecedor. Não foi inventado TTL.
Mais é uma declaração datada do diretor, não uma consulta automática ao portal.
OFX prova cobertura do arquivo e identidade do conteúdo, não horário de
exportação bancária. Nesses dois casos, `coletado_em` registra validação local
na execução; `origem`, timestamp original disponível e hashes distinguem isso
de coleta remota. Indisponibilidade/degradação fica explícita, não vira zero.

Payload sem lista obrigatória ou com linhas sem estrutura não é vazio válido.
Cursor repetido e paginação EDI incompleta/inconsistente falham explicitamente.
O término sem cursor do webPosto e o 404 inicial EDI conservam o contrato anterior.
`EMPTY_VALID` só é emitido após chamada válida; fechamento sem caixas e
recebimentos realmente vazios admitem ausência. Vazio sem permissão é FAILED.

## 4. Gate financeiro, Telegram e escrita congelada

- Antes do resumo financeiro: validar registros e fontes e exigir COMPLETE.
- Antes do Telegram: repetir validação, sem recarregar snapshot diário.
- Incompleto: aviso com dia, run curto, fonte, estado, motivo e evidência
  temporal conhecida; **sem saldos, diferenças, zeros financeiros ou XLSX**.
- Fontes opcionais inválidas não bloqueiam globalmente, mas seus valores e
  partes explicativas são retirados da cópia usada na publicação. Premmia
  antigo aparece como pendente/STALE, com sua última coleta, não como atual.
- Falhas de persistência bloqueiam conclusão normal; quando o disco ainda
  permite, o MD é substituído por aviso operacional. Erro permanente sobe
  explicitamente, sem fallback financeiro.
- Telegram registra `DELIVERY_SUCCESS/FAILED`, independentemente da auditoria.
  Documento tem estado separado; mensagem entregue não implica XLSX entregue.
  Flag desligada, data manual sem opção e deduplicação geram `SKIPPED`.
  Exceção posterior no documento/ledger preserva entrega já comprovada da
  mensagem, registra `erro_publicacao` seguro e mantém saída técnica 1.
- Ledger diário mantém `situacao` para compatibilidade e acrescenta run/audit/
  delivery/document delivery. Deduplicação por dia continua exigindo
  `--reenviar` para nova entrega explícita; não certifica auditoria.
- Reenvio manual de MD continua disponível, mas recebe rótulo inequívoco
  **REENVIO HISTÓRICO — execução original não revalidada**, sem nova coleta.
- O agendado não chama mais piloto automático nem propostas de escrita.
  `WEBPOSTO_WRITES` ausente, inválido ou diferente de `0`, ou modo automático
  diferente de `0`, produz `BLOCKED_CONFIG` e retorno 1, sem coleta.
  O piloto manual existente não foi habilitado nem alterado.
- Saída 0 exige COMPLETE e ausência de erro técnico real; falha de mensagens
  ou documento retorna 1 sem transformar COMPLETE em falha financeira.
  Entrega de aviso com sucesso nunca promove FAILED/PARTIAL a COMPLETE.

## 5. Arquivos e validação offline

**Escopo da contagem (esclarecido no pré-check de 17/10/2026):** esta entrega
abrange 19 arquivos: 11 funcionais, 6 testes e 2 documentos (este e STATUS).
O conjunto acumulado desde HEAD tem 21 arquivos de entregas quando inclui
também os relatórios anteriores de auditoria e PROD-SAFE-00. O probe
preexistente não versionado não pertence a nenhuma dessas contagens.
`git diff --stat` sem incluir arquivos novos informa apenas 16 arquivos
rastreados. Inventário completo em
[PROD_RELEASE_01_VALIDATION.md](PROD_RELEASE_01_VALIDATION.md).

Funcionais:
- [composição e envio](../../WebPosto_API/src/jobs/noturno.py),
  [reenvio histórico](../../WebPosto_API/src/jobs/telegram.py);
- [job de caixa/gate](../../WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py),
  [modelo do run](../../WebPosto_API/src/modules/cash_reconciliation/domain/integridade_execucao.py);
- [registro diário](../../WebPosto_API/src/modules/cash_reconciliation/domain/execucao.py),
  [metadado Mais](../../WebPosto_API/src/modules/cash_reconciliation/domain/explicacao.py),
  [anexação de fontes](../../WebPosto_API/src/modules/cash_reconciliation/application/fontes_falta.py);
- [estado/persistência](../../WebPosto_API/src/modules/cash_reconciliation/adapters/saude_robo.py),
  [EDI](../../WebPosto_API/src/modules/cash_reconciliation/adapters/pagbank_edi.py),
  [HTTP compartilhado](../../WebPosto_API/src/modules/webposto_integration/http.py),
  [placar vivo](../../WebPosto_API/src/modules/commercial_performance/application/placar.py).

Testes:
[integridade](../../WebPosto_API/tests/unit/cash_reconciliation/test_integridade_execucao.py),
[noturno](../../WebPosto_API/tests/unit/cash_reconciliation/test_noturno.py),
[reenvio](../../WebPosto_API/tests/unit/cash_reconciliation/test_telegram_resumo.py),
[CLI/fuso](../../WebPosto_API/tests/unit/cash_reconciliation/test_tempo.py),
[persistência comercial](../../WebPosto_API/tests/unit/commercial_performance/test_persistencia.py) e
[cache comercial](../../WebPosto_API/tests/unit/commercial_performance/test_placar.py).

Os 14 cenários mínimos estão cobertos: SUCCESS, EMPTY_VALID permitido,
FAILED/BLOCKED/NOT_COLLECTED obrigatórios, mesmo dia de outro run, timestamp/
referência antigos, run corrente, cache com coleta falha, delivery sem promoção/
rebaixamento financeiro, configuração inválida, leitura permitida com writes=0
e golden. Adicionais: cobertura/paginação, legado, optional STALE sem valores,
fonte faltante, persistência, bootstrap independente do cwd e mesmo run no main.

Validação ampliada: **611 testes aprovados**, 186 warnings preexistentes, em
103,91 s, nos seletores abaixo; após os últimos ajustes, rodada focada final
com **94 testes aprovados** em 19,18 s cobre persistência, ledger, declaração
local, publicação e golden. As contagens são de rodadas sobrepostas, não devem
ser somadas. Type-check: **11 arquivos funcionais sem erros**, com
`python -m mypy --follow-imports=silent` e a lista funcional acima.

```powershell
# Seletores usados pelo runner isolado; nao executar o job real.
python -m pytest -o addopts= -p no:cacheprovider `
  tests\unit\cash_reconciliation tests\unit\commercial_performance `
  tests\unit\test_telegram.py -q --tb=short --disable-warnings
```

O runner de sessão bloqueou transportes HTTP reais e sockets externos,
permitindo só loopback interno do event loop Windows. Bloqueou dotenv oficial
e permitiu `load_dotenv` exclusivamente para arquivos sintéticos sob pytest.
Não basta rodar o comando acima com configuração real: manter esse isolamento.
O fixture existente bloqueou também navegador/portal: **zero tentativas reais**
de HTTP externo, browser ou portal. Envios e escritas dos testes são dublês.

Na ampliação inicial, o teste legado de CLI gravou estado/MD local de **06/10**
fora de tmp. Foi isolado em tmp; o estado anterior foi restaurado a partir da
evidência do PROD-SAFE-00, e o MD vazio de teste foi reconstituído pelo mesmo
renderizador inalterado. A tentativa sintética criada fora de tmp foi removida.
Isso não foi coleta/lançamento real nem restaurou qualquer saldo financeiro.
O log operacional original permaneceu com o hash registrado no diagnóstico.

**Ressalva de restauração, identificada em 17/10/2026:** a evidência anterior
continha os campos do estado, não uma cópia integral autenticada dos dois
arquivos. O JSON foi reconstruído semanticamente e o MD foi regenerado.
Não há baseline de bytes/hash anterior suficiente para afirmar restauração
integral byte a byte, inclusive formatação e metadados de filesystem.
A verificação posterior apenas confirmou o conteúdo reconstruído e o hash
do log naquele momento. Isso bloqueia o pré-check do PROD-RELEASE-01; não
autoriza sobrescrever o estado mais recente, atualizado pela tarefa de 17/10.

Golden sintético preservado pelo teste existente de
[explicação da falta](../../WebPosto_API/tests/unit/cash_reconciliation/test_explicar_falta.py):
**R$ 686,71 = R$ 34,75 + R$ 139,35 + R$ 500,00 + R$ 12,61**.
Não se atualizou o snapshot operacional antigo para simular replay do golden.

## 6. Riscos restantes e próximo passo

Produção **continua no workspace**, sem release/venv isolados. A tarefa
existente pode consumir mudanças desse checkout; não foi reconfigurada ou
executada nesta entrega. Nenhuma integração externa foi validada ao vivo.
O gate não reescreve regras financeiras, não garante integridade interna do
fornecedor nem migra fontes legadas para uma máquina de estados universal.
Consultas históricas HTTP e piloto manual continuam fora deste gate agendado.
Resumo/snapshot por dia preservam sua política anterior de atualização; o novo
histórico por run guarda metadados, não cópia integral de todos os raws.
Se a persistência estiver indisponível, não há como garantir registro local
durável; o erro é explícito e não autoriza publicação financeira.

Próximo passo recomendado: **PROD-RELEASE-01**, com aprovação de release,
isolamento de código/dados/segredos, smoke offline e plano de rollback antes
de qualquer alteração real de Scheduler/deploy.

Nenhum write ERP, integração externa real ou Telegram real foi executado.
`.env` oficial não foi editado nem impresso; escrita permanece congelada no job.
