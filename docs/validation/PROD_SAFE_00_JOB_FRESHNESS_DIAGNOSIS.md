# PROD-SAFE-00 — job das 03:00 e frescor dos dados

**16/10/2026 · America/Recife · feature/cash-audit-fechamento · base 76cd8e2.**
Diagnóstico somente leitura: inspeção estática, tarefa Windows e metadados locais.
Não se importou/executou aplicação, job, integração ou teste funcional. Não se
leu/alterou `.env`; nenhum envio, write operacional, deploy, commit, push ou merge.
Somente este documento e o acréscimo correspondente em [STATUS](../../STATUS.md).
O [inventário anterior](LOGOS_CURRENT_CAPABILITY_AUDIT.md) permanece inalterado.

**Veredito:** fail-closed na barreira de coleta; **fail-open na composição
coleta → resumo/envio quanto à completude/frescor**. Não é fail-open de escrita
financeira demonstrada. O episódio real enviou aviso de ausência, não prova de
relatório financeiro normal com dados antigos. O caminho para isso existe.

## 1. Fluxo real do job

**Tarefa consultada:** `LOGOS - Auditoria de Caixa`, diária 03:00 UTC-03:00,
habilitada; `Interactive / Limited`, depende de sessão Windows aberta.
`IgnoreNew`, `StartWhenAvailable=True`, limite de execução 3h.

| Campo | Valor real |
|---|---|
| Executável | `C:\Program Files\Python314\pythonw.exe` |
| Argumentos | `-B -m src.modules.cash_reconciliation.jobs.noturno` |
| Working directory | `C:\Projetos\LOGOS\LogosPostos\WebPosto_API` |
| Python/venv | Python global; `python.exe` do mesmo diretório informa 3.14.4; ação não aponta para venv |
| Última / próxima | 16/10/2026 03:00:01, resultado **1** / 17/10/2026 03:00 |

O [main do módulo antigo](../../WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py#L270)
encaminha para [src.jobs.noturno.main](../../WebPosto_API/src/jobs/noturno.py#L500).
O [registrador atual](../../scripts/registrar_robo_noturno.ps1) usa diretamente
`-B -m src.jobs.noturno`: diferença real, mas o wrapper encaminha à composição.
**Roda do workspace, não de release isolada.** `C:\Projetos\LOGOS\production`
não existe. O job não registra SHA aprovado; o código atual explica o fluxo,
mas não há prova imutável do checkout exato carregado às 03:00.

Ordem encontrada, não uma ordem idealizada:

1. `main`: argumentos → ontem Recife (15/10 neste caso) → `load_dotenv` →
   configurar log → `asyncio.run(executar(..., executar_placar=_executar_placar))`.
2. [executar](../../WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py#L111):
   verificar modo automático/travas → barreira de somente leitura → criar ID e
   carregar unidades. Bloqueio retorna **antes** do ID, coleta e atualização de saúde.
3. Para cada unidade, sequencialmente: se `premmia_ativo`, tentar portal/XLSX
   primeiro; falha vira aviso e não impede fechamento/outros adquirentes.
4. [coletar_unidade](../../WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py#L43):
   fechamento webPosto → adquirentes na ordem da configuração →
   montar ResultadoDiario → anexar fontes da falta.
   [Fechamento](../../WebPosto_API/src/modules/cash_reconciliation/application/auditar_fechamento.py#L87):
   CAIXAS → APRESENTADO → SANGRIAS → VALES → despesas por caixa → regras.
5. [Adquirentes](../../WebPosto_API/src/modules/cash_reconciliation/application/conciliar_cartoes.py#L366):
   PagBank consulta EDI D−1/D/D+1 **antes** do contexto webPosto;
   contexto = CARTOES → ABASTECIMENTOS → ITENS → FORMAS → VENDAS → CAIXAS →
   nomes (degradáveis) → conciliação. Premmia lê XLSX mensal → mesmo contexto →
   conciliação. Pendente/credencial inválida podem retornar sem coletar.
   Configuração atual: Doze/Casa Caiada têm PagBank ativo antes de Premmia ativo;
   VIP tem adquirentes pendentes; Conv. 24h tem PagBank com credencial inválida.
6. [Fontes da falta](../../WebPosto_API/src/modules/cash_reconciliation/application/fontes_falta.py#L14):
   ADMINISTRADORAS se há PIX/BACEN candidato → total Mais local → OFX local
   por conta/dia → contexto webPosto extra se necessário → comparação.
   **Não há uma etapa global obrigatória de coleta OFX nem conciliação
   sangria × depósito bancário no job atual.**
7. Piloto automático, somente se ativado: executar; se houve lançamento,
   recoletar unidade. Branch existente, não habilitado nem executado aqui.
   Salvar JSON → pendências do dia → reincidência com JSONs do mês → SQLite →
   acumular falhas/avisos. Exceção da unidade permite seguir para a próxima.
8. Placar por posto → resumo com resultados **em memória**, mesmo parciais →
   salvar MD → salvar EstadoRobo → log final → retornar 0/1.
9. `main` chama `_tentar_envio_telegram` **independentemente do inteiro retornado**.
   O envio recarrega JSONs → estado/pendências → nomes via GET se houver caixas →
   mensagens → salva MD novamente → tenta XLSX → mensagens/documento → ledger →
   propostas privadas, se configuradas. O resumo não incorpora o placar.
   Exceção que **escapa** de `executar`, em vez de retorno 1, interrompe `main`
   antes dessa chamada: o envio não acontece após absolutamente toda falha.

## 2. Falha de 16/10/2026

| Evidência | Constatação |
|---|---|
| Task Scheduler | Início 03:00:01; `LastTaskResult=1` |
| `data/cash_audit/noturno.log`, linha 1398 | 16/10/2026 **03:00** ERROR: `Execucao bloqueada: WEBPOSTO_WRITES deve ser 0.` |
| Mesmo log, linha 1399 | 16/10/2026 **03:00** INFO: `Telegram envio=ok` |
| Ledger local, referência 15/10 | `registrado_em=16/10/2026 03:00:45.137643 -03:00`, `situacao=ok` |
| Resumo MD de 15/10, presente | Última modificação 16/10/2026 03:00:35; quatro avisos de conferência não realizada |

**Fonte da falha:** barreira local em `cash_reconciliation/jobs/noturno.py`,
função `executar`, linhas 117–122. Com automático não ativado, a condição
`os.getenv("WEBPOSTO_WRITES") != "0"` registra a mensagem e retorna 1.
**Não foi exceção de webPosto/PagBank/Premmia nem timeout de fornecedor.**
O log permite inferir o branch, não qual valor/ausência/origem da variável o
causou. Não se leu configuração para tentar adivinhar. `load_dotenv` não força
override em `main`; variável herdada também pode influenciar a condição.

O formatter do log só tem precisão de **minuto**, não segundo. Hash SHA-256 do
log inspecionado: `e544432d396c8ac6bd87c8aa52a5509f722317a02ab185f254f0f803024dc95a`.
Log não contém PID/ID de execução nesse bloqueio; tarefa, sequência de marcadores
e ledger são evidências concordantes, não tracing imutável por processo.

## 3. Comportamento após falha

O corpo de coleta não continuou: zero novas coletas/persistências/placar/resumo
interno/saúde desse branch. **A composição continuou** para o envio e regenerou
o MD a partir da persistência. `main` devolve 1 mesmo quando a mensagem é enviada.

Estado local observado: `ultima_execucao=16/10/2026 00:32:49 -03:00`,
`dia_processado=06/10/2026`, unidades vazias, `resumo_gerado=True`. É anterior às
03:00 e referente a outro dia; não prova auditoria atual.
**Não havia JSON de 15/10**; havia quatro do dia 14/10.
O carregador do Telegram exige **o dia solicitado**, portanto não substituiu
automaticamente 15/10 por 14/10. O MD atual avisa “conferência não rodou” nas
quatro unidades e inclui contagens locais de pendências; não afirma “sem falta”.
Ledger não arquiva corpo/hash da mensagem: não se verificou remotamente o texto
entregue, apenas artefato local e sucesso registrado.

**Cenário permitido pelo código:** existe JSON válido de coleta anterior **para
o mesmo dia**, a nova tentativa falha antes de `salvar_dia`, e o envio recarrega
o anterior. O carregador valida unidade/dia, **não idade/execução atual**.
Sem erro no snapshot, o renderer pode mostrar “EM ORDEM”/“conferido” sem aviso
de obsolescência. Falha de gravação atômica também preserva o JSON anterior.
Se a saúde for do dia, pode acrescentar “auditoria com falha”, mas não rejeita
os números antigos; se for de outro dia, deduz falhas só dos JSONs antigos.

## 4. Persistência/cache/fallback

| Ponto | Reuso encontrado / limite |
|---|---|
| [carregar_dia](../../WebPosto_API/src/modules/cash_reconciliation/adapters/persistencia.py#L26) | JSON exato unidade/dia; sem TTL/run gate; sem fallback de dia. Ausente=None, corrompido/escopo errado=erro explícito. `os.replace` preserva anterior se falhar |
| [_coletar_dados_telegram](../../WebPosto_API/src/jobs/noturno.py#L91) | Releitura do disco, não usa a lista recém-coletada nem execucao_id; estado só aproveitado se dia_processado igual |
| Reincidência/planilha | [executar_reincidencia_mes](../../WebPosto_API/src/modules/cash_reconciliation/application/gerar_pendencias.py#L657) lê mês até D; [conferencia_para_registro](../../WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py#L320) lê demais dias do mês e decisões SQLite. Histórico intencional, sem selo de cobertura mensal |
| Fontes locais | OFX existente, Mais por dia, XLSX Premmia mensal; sem refresh global forçado. Premmia coleta só dias faltantes; já coletado pode ficar sem reconsulta de alterações posteriores |
| [obter_placar](../../WebPosto_API/src/modules/commercial_performance/application/placar.py#L243) | D passado com snapshot.dia==D retorna cache, sem validar idade; hoje pode somar snapshot de ontem. Falha de GET não retorna silenciosamente último válido; snapshot anterior permanece no disco |
| Estado/resumo/ledger | Estado anterior fica se early return; MD é sobrescrito antes de enviar; ledger por dia não contém run/hash e bloqueia repetição inclusive de envio marcado falhou, salvo --reenviar |
| Outros dados de saída | Pendências/decisões SQLite e histórico do piloto (“Lancei…”) são lidos, sem selo conjunto de execução; `telegram --reenviar-resumo` envia MD existente não vazio, sem revalidar fontes |
| Superfícies relacionadas, fora do agendamento | [painel_diretor](../../WebPosto_API/src/modules/cash_reconciliation/application/painel_diretor.py#L111) busca último snapshot disponível, podendo obter fechamento/recebimentos de referências distintas; APIs persistidas leem JSON do dia; relatório atual consulta rede e explicita falhas, mas renderer aceita registro fornecido. Planilha mensal de PIX manual entra na conferência gravada, não no caminho de coleta noturna acima |

Não há uso de Redis/Valkey, `SnapshotStore`/TTL do analytics ou “último GET válido”
no caminho HTTP V1 rastreado. Não atribuir ao job caches de aplicações paralelas.
Premmia ainda persiste bloqueio de verificação humana por dia-alvo e mantém
histórico de login na noite; isso governa tentativas, não prova frescor.

## 5. Frescor por fonte

“Obrigatória” abaixo descreve dependência/tratamento **do código**, não nova regra
financeira. Política declarativa de fontes obrigatórias por relatório: **NÃO DEFINIDO**.

| Fonte | Como coleta | Persistência | Timestamp/frescor | Pode usar dado antigo? | Obrigatória? |
|---|---|---|---|---|---|
| Fechamento webPosto | GET sequencial das cinco famílias | ResultadoDiario/fechamento | dia/inicio/fim; caixa data/abertura/fechamento; Proveniencia.executado_em ao calcular | Sim, JSON de D no envio; dia de movimento não mede idade | Necessária para fechamento; falha explícita mas resumo permitido |
| Contexto cartão webPosto | GET D−1..D+1 de cartão/venda/item/forma/caixa | Projeções nos recebimentos | momento das transações + proveniência da conciliação | Sim, snapshot D; sem fetched_at por endpoint/página | Necessário à conciliação ativa; nomes são degradáveis |
| PagBank | EDI paginado D−1/D/D+1, sem cache GET | Derivado no JSON | Data/hora da venda; executado_em da conciliação, não timestamp de publicação EDI | Sim, derivado persistido | Ativo requer consulta; erro conta falha, credencial inválida só aviso; configurado pendente não coleta |
| Premmia | Portal antes da unidade; lê XLSX | XLSX Transações/Coletas | Dia, Quantidade, Total, “Coletado em”; detecta dia não coletado | Sim, dia marcado coletado não exige refresh/TTL | Degradável: erro portal vira pendente+erro/aviso, não falha global |
| PIX CNPJ / OFX | Arquivo por conta PagBank que cubra D | OFX externo; hashes/coberto no JSON | inicio/fim, data/momento; hash prova identidade, não atualidade da exportação | Sim; ausência não bloqueia, conflito vira erro local | Opcional no código; requisito para afirmar completude PIX **NÃO DEFINIDO** |
| Mais Pagamentos | JSON declarado unidade/D | Total local → comparação derivada | dia + informado_em; comparação não preserva informado_em em ConferenciaMais | Sim, mesma declaração pode ser reutilizada | Opcional no código; ausência não bloqueia; completo sem total **NÃO DEFINIDO** |
| Administradora PIX / nomes | GET condicional | Descrição/motivo ou nomes no derivado | Sem coletado_em próprio | Sim, valor no snapshot; nomes podem ser novos junto a números antigos | Degradáveis; falha orienta manual/sem nome |
| Comercial | GET abastecimento/produto/item/funcionário ou snapshot | JSON por posto/mês | dia e Proveniencia.executado_em; merge hoje pode ter timestamp novo para histórico antigo | Sim, cache por data, não idade | Necessário ao placar solicitado; falha incrementa saída, mas não bloqueia resumo de caixa |
| Metas / unidades | JSON local | Configuração e dados/metas | Mês de referência; sem timestamp de leitura por fonte | Sim, arquivo existente | Unidades necessárias; metas ausentes permitidas, metas inválidas falham |
| Pendências / decisões / piloto | SQLite e histórico local | Eventos/estados | criada_em/registrado_em/instante próprios; contagens são atuais, não coleta financeira | Sim, histórico intencional | Resumo usa contagens; leitura pode falhar; não há gate financeiro conjunto |
| Telegram / saúde | Retornos HTTP e arquivos de estado | Ledger/EstadoRobo/MD | registrado_em=envio; ultima_execucao=estado; mtime=arquivo | Sim, não atestam fontes | Nenhum destes timestamps comprova AUDIT_SUCCESS |

Representação atual dos estados pedidos:

| Conceito | Existe hoje? |
|---|---|
| COLLECTED / SUCCESS / VALID | Aproximações: fechamento presente, adquirente `ok`, saída 0; validação de schema/escopo, não certificado de completude/frescor |
| EMPTY / EMPTY_VALID | Lista vazia/caixas=()/casados=0 com `ok`; HTTP V1 sem `resultados` também vira []; PagBank 404 retorna lista acumulada/vazia. Premmia distingue dia coletado vazio pela aba Coletas. Sem estado universal que prove vazio válido |
| FAILED | erro_fechamento; adquirente `erro`; falhas/saída 1; credencial inválida separada, só aviso. Algumas falhas locais PIX/Mais não entram em falhas globais |
| BLOCKED | Early return 1 + log; não cria registro/estado BLOCKED persistido dessa tentativa |
| STALE | Sem enum/TTL por fonte; painel tem alerta de atraso >26h/estado sem unidades, não usado como gate do envio |
| NOT_COLLECTED | Arquivo ausente=None; adquirente `pendente` mistura configuração, fonte não coletada e bloqueio humano com erro; Premmia tem exceção própria |
| COMPLETE / PARTIAL / FAILED da auditoria | Sem estado agregado dessas categorias; inteiro 0/1 + listas falha/aviso + resumo_gerado. Saída 0 pode conter fonte degradada; resumo_gerado significa arquivo produzido |

Portanto **vazio e falha são distinguíveis em alguns caminhos, não universalmente**.
Há metadados de referência/coleta, não prova de frescor de todas as fontes.

## 6. Gate atual antes do resumo

**GAP REAL: não há “todas as fontes obrigatórias válidas e atuais”.**
`executar` gera resumo mesmo com `falhas>0`; usa resultados parciais em memória.
O renderer registra fechamento ausente/erro e erros de adquirentes, mas não
verifica idade/run/manifesto de fontes. O relatório de caixa individual pode
mostrar “Dados registrados/consultados em” e falhas; exibir hora não é validá-la.
Premmia degradado e credencial inválida são avisos deliberados do código, não
licença para chamá-los auditoria completa.

## 7. Gate atual antes do Telegram

[_tentar_envio_telegram](../../WebPosto_API/src/jobs/noturno.py#L381) exige flag,
dia automático de ontem ou opção explícita manual, ausência de envio já
registrado (ou --reenviar), token/destinatários; leitura/renderização também
podem interromper por exceção. **Não recebe código_saida/execucao_id**, não exige
resumo_gerado nem saúde/completude/frescor. **GAP REAL.**
[_criar_planilha_telegram](../../WebPosto_API/src/jobs/noturno.py#L186) escreve
zero em várias colunas quando não há fechamento, sem coluna de status/fonte
nesse resumo: a mensagem avisa ausência, mas a planilha pode parecer zerada.

**DELIVERY_SUCCESS ≠ AUDIT_SUCCESS.** `sucesso` no envio considera mensagens,
não sucesso do documento nem da auditoria. Nenhum consumidor localizado promove
ledger a sucesso de auditoria; ele só evita reenvio. O painel usa EstadoRobo
(idade, unidades/falhas), não ledger. Porém o nome genérico `situacao=ok` e o
log podem induzir interpretação errada. Exceção no envio é logada e não muda
o inteiro já obtido; saída 0 tampouco garante entrega.

## 8. Gaps reais

1. Gate conjunto run/dia/unidade/fontes antes de publicar números; tentativa
   bloqueada/falha não substitui saúde antiga por estado da tentativa atual.
2. Manifesto mínimo por fonte com estado, cobertura, coleta e proveniência;
   validade de vazio, obrigatoriedade e validade temporal por relatório
   **NÃO DEFINIDOS**. Não inventar TTL nem tornar toda fonte obrigatória.
3. Releitura do disco sem vínculo à execução; JSON válido estruturalmente pode
   ser velho; datas agregadas não comprovam todas as páginas/fontes.
4. Sem estado audit COMPLETE/PARTIAL/FAILED; aviso degradado pode coexistir com
   retorno 0. Falta separar bloqueio operacional de erro de fornecedor.
5. Zeros em planilha sem fonte válida, ledger sem run/hash e sucesso documental
   separado; faltam testes do cenário completo bloqueio → envio → snapshot antigo.

Testes existentes **inspecionados, não rodados**:
[test_noturno.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_noturno.py)
L392 prova barreira isolada; L139 preservação de JSON; L407 dedup de envio;
L523 ledger ok com falha documental; L620 Premmia degradado com saída 0.
Não provam o gate ausente de `main`.

## 9. Correção mínima recomendada

**Não implementada.** Reusar ResultadoDiario, Proveniencia, EstadoRobo e renderer.
Primeiro: condicionar publicação normal ao resultado **da execução atual**;
ao bloquear/falhar, persistir diagnóstico da tentativa e emitir, se autorizado,
somente aviso operacional explícito, sem tabela zerada/números reaproveitados.
**Só `if codigo_saida == 0` é insuficiente:** há degradações com retorno 0.
Passar resultado/run atual ao envio (não recarregar livremente snapshots) e
validar unidade/dia, fontes exigidas, cobertura e validade acordada. Se faltarem
critérios, marcar incompleto/não validado, não “conferido”. Histórico continua
disponível apenas como histórico identificado. Registrar entrega separadamente.

Validar futuramente, offline com mocks: bloqueio; falha antes de salvar com JSON
antigo de D; vazio confirmado; Premmia degradado; fonte ausente; mistura de runs;
placar em cache; falha de documento. Sem alterar regras/limites financeiros.

**Isolamento futuro em `C:\Projetos\LOGOS\production`:** release/tag aprovada em
pasta separada; venv/dependências/browser aprovados; escolher comando direto
`src.jobs.noturno` e alterar ação do Scheduler para Python da release e cwd
`production\WebPosto_API`, mediante aprovação. Configurar conta/sessão/logon,
permissões e fuso. Separar/preservar dados/SQLite/logs/backups e segredos fora
da release substituível: paths atuais dependem de `__file__`; copiar código sem
migrar/reapontar dados cria base vazia. Rever path absoluto de extratos e manter
escopo por conta. Smoke offline/read-only, exclusão mútua de jobs/pollers e
rollback de release antes do cutover. **Nenhum destes passos foi executado.**
