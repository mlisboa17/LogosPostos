# MAIS-BANK-04 — Saldo intermediário, repasses e crédito bancário

**17/10/2026 · branch `feature/cash-audit-fechamento` · HEAD `5bff018` conferido · diagnóstico READ ONLY.**

Repositório oficial confirmado: `C:\Projetos\LOGOS\LogosPostos`. Escopo Mais: **Doze 74014, VIP 11495 (incluindo sua própria conveniência) e Casa Caiada 5555**. A confirmação mais recente do dono prevalece sobre o texto inicial do anexo: **Conveniência 24h 118508 não utiliza Mais**, não integra matrizes de contas/repasses Mais nem tem plataforma pendente nesse contexto. Permanece nos demais módulos; nenhuma configuração operacional foi alterada. Matera faz parte do ecossistema informado, mas sua associação operacional continua não comprovada.

Base local: [STATUS](../../STATUS.md), [MAIS-BANK-01](MAIS_BANK_01_SOURCE_GAP_MATRIX.md), [02](MAIS_BANK_02_SETTLEMENT_SOURCES.md), [03](MAIS_BANK_03_SOURCE_VALIDATION.md), [regras de negócio](../regras-negocio/REGRAS_DE_NEGOCIO.md), [ADR-002](../architecture/adr/ADR-002-cash-arch-01-antes-do-arch-02.md), [ADR-003](../architecture/adr/ADR-003-autonomia-gradual-de-escrita-no-erp.md), contratos e código vinculados abaixo. As fontes públicas da etapa 02 foram revisadas pelo relatório local, **sem acessar a internet novamente**. Nenhuma conta, aplicação, teste, script operacional ou job foi executado; sem leitura/alteração de `.env`, integração externa, Telegram, transferência, deploy, commit, push ou merge. Legado somente como referência documental, sem migração.

**Resultado:** podemos definir a prova necessária, mas ainda não fechar saldo nem confirmar repasse/crédito real da cadeia Mais. **PIX do dia − repasse do dia não mede perda.** Dinheiro pode permanecer disponível, bloqueado ou em trânsito; saldo que fecha não prova a composição individual de um repasse.

## A. Funcionamento dos repasses

Classificação das respostas: **CONFIRMADA** = informação explicitamente confirmada pelo dono ou evidência operacional identificada, com limite indicado; **DOCUMENTADA** = contrato/descrição local, não operação habilitada; **NÃO COMPROVADA** = sem evidência suficiente; **DEPENDE DA MAIS/INSTITUIÇÃO** = informação/contrato/autorização externa necessária.

**CONFIRMADA como informação operacional do dono, não execução auditada:** há possibilidade de solicitar repasse manual e de rotina da Mais executar repasse automático conforme configuração. Não foi fornecido histórico que identifique uma execução, operador, horário ou valor. O modo de cada transferência precisa de evidência própria; não inferir “automático” pelo horário ou recorrência.

| Pergunta | Manual | Automático | Classificação / evidência atual |
|---|---|---|---|
| Como começa? | Dono/operador solicita transferência do saldo | Rotina da Mais pode iniciar conforme configuração operacional | CONFIRMADA como descrição do dono; NÃO COMPROVADA por evento real |
| Quem pode solicitar/configurar e em qual sistema/portal? | Perfis, permissões e canal não identificados | Quem mantém/configura rotina e quem efetivamente envia à instituição não identificado | DEPENDE DA MAIS/INSTITUIÇÃO; não atribuir papéis por suposição |
| Qual conta sai e qual recebe? | Conta intermediária e banco/titular destino precisam ser identificados | Mesmo requisito; não presumir destino igual ao manual | NÃO COMPROVADA por unidade; DEPENDE DA MAIS/INSTITUIÇÃO |
| Horário, dias, frequência, total/parcial, mínimo/reserva? | Não presumir retirada integral nem disponibilidade imediata | Não presumir diário, 100% do saldo, horário único, valor mínimo, número de execuções ou tratamento de feriados | DEPENDE DA MAIS/INSTITUIÇÃO; sem parâmetros locais comprovados |
| Há comprovante, ID e status? | Asaas documenta ID/E2E, destino, comprovante e estados de transferência | Mesma documentação não prova que a rotina Mais use esse recurso nem identifique o modo | DOCUMENTADA para Asaas; NÃO COMPROVADA na conta real; Matera/Fiserv dependem de contrato aplicável |
| Há taxa, rejeição, cancelamento ou nova tentativa? | Asaas documenta taxa e estados pendente/agendado/processando/bloqueado/realizado/falha/cancelado | Falha da rotina, reenvio, idempotência e tarifa por tentativa não estabelecidos | DOCUMENTADA para recursos Asaas; DEPENDE DA MAIS/INSTITUIÇÃO para operação contratada |
| Histórico distingue manual/automático e autor? | Exigir evento auditável ou declaração formal vinculada ao ID | Exigir ID da execução/regra/versão e transferência gerada, quando disponíveis | NÃO COMPROVADA: não localizado campo validado de modo no material examinado |

Nenhum recurso de criação de transferência foi chamado. Uma transferência agendada não é uma execução; execução automática não é crédito final.

## B. Matriz por instituição e fonte

| Instituição / fonte | Extrato | Saldo | Repasse | Tarifa | Identificador | Status da evidência |
|---|---|---|---|---|---|---|
| Mais — [contrato local](../external/maispagamentos/openapi_integracao_2026-10-11.json) | Lista/detalhe de transações; extrato financeiro consolidado/portal não comprovado | Sem consulta dedicada de saldo localizada | GET de pagamento conhecido por chave/QR; sem lista de repasses/composição ou rotina automática documentada nesse contrato | Detalhe de transação tem `taxa`; sem tabela operacional de retenções/repasses validada | `id`, `transacaoId`, E2E de entrada; saída pode ter `idPagamento`, `e2eId` | DOCUMENTADA para transações/saída conhecida; DEPENDE DA MAIS/INSTITUIÇÃO para saldo, rotina e acesso |
| Asaas — documentação reunida no [MAIS-BANK-02](MAIS_BANK_02_SETTLEMENT_SOURCES.md) | GET `/v3/financialTransactions`: `id`, `date`, `value`, `balance`, tipo e `paymentId`/`transferId` quando presentes | GET `/v3/finance/balance`: disponível atual; saldo inicial/final histórico exige extrato/cortes validados; bloqueado/contábil não estabelecidos nessa pesquisa | GET `/v3/transfers` e `/{id}`: valor/líquido, efetivação, status, destino e comprovante; não distingue por si rotina Mais | `transferFee`, `chargedFeeValue` no Pix, lançamentos de taxa/reversão | Pix: E2E, `payment`; ledger: referências; transferência: ID/E2E de saída | DOCUMENTADA publicamente na etapa 02; acesso à conta Doze/BaaS NÃO COMPROVADO |
| Matera | Contrato/layout aplicável à conta não encontrado | Inicial/final/disponível/bloqueado não comprovados | Produto, custodiante, canal e processo não identificados | Não comprovada | Enum Mais não é identificador de conta/repasse | NÃO COMPROVADA; DEPENDE DA MAIS/INSTITUIÇÃO |
| Fiserv | Sem contrato aplicável de conta no material examinado; Hub Pix/SiTef não supre | Inicial/final/disponível/bloqueado não comprovados | Produto/PSP/custodiante e canal aplicável ainda desconhecidos | Não comprovada | Sem amostra válida de conta/transferência da operação | NÃO COMPROVADA; DEPENDE DA MAIS/INSTITUIÇÃO |
| webPosto — [contrato local](../external/webposto/openapi_integracao_2026-10-06.json) | GET V1/MOVIMENTOS_CONTA, V2/TRANSFERENCIAS_BANCARIAS, recebíveis/remessas | V1/CONTAS `saldoAtual` e saldo do movimento são ERP, não da instituição | Registra transferência/baixa; `contaOrigem` e `documentoReferencia` ajudam a investigar | Taxas internas/administradora/remessa não provam débito externo | Empresa/venda/conta/movimento/documento de origem | DOCUMENTADA como contexto interno; NÃO COMPROVADA como fonte bancária independente |
| Banco final — OFX/extrato oficial fornecido pelo titular | Leitor oficial lê movimentos assinados, data, documento, descrição e FITID | Parser não preserva saldos oficiais de abertura/fechamento; soma líquida não é saldo | Crédito no destino precisa de linha oficial e referência compatível com saída | Débito/tarifa deve ter linha/semântica própria; não inferir por diferença | FITID/documento; E2E/contraparte pode exigir detalhe complementar | DOCUMENTADA/implementada a leitura; crédito real de repasse Mais NÃO COMPROVADO |

**Precisão e acesso:** extrato Asaas documentado tem data, não horário de cada linha; Pix/transferência têm datas de criação/efetivação. Não criar hora de compensação. `access_token` público não comprova permissão contratada nem chave somente leitura. Mais requer autenticação própria; 401 histórico não foi repetido. Matera pode ser tecnologia do arranjo: não presumir que seja o custodiante ou que APIs de parceiro sejam acessíveis ao posto.

**Crédito intermediário:** detalhe Pix Asaas pode ligar E2E Mais → `payment` → `paymentId` do lançamento; precisa de prova na mesma conta. Pagamento confirmado, crédito contábil, liberação de saldo e saída são fatos distintos. Fonte Mais não substitui extrato Asaas/Matera/Fiserv.

**webPosto:** venda/caixa/forma de pagamento, cartões, títulos e remessas ajudam na rastreabilidade. MOVIMENTOS_CONTA aceita também lançamentos internos/POST/PATCH; `conciliado`/`usaOfx` não certificam origem bancária. V1/OFXS é POST de importação, sem GET segregado do extrato bancário nessa cópia; não reativar. Cobertura e amostras históricas no [MAIS-BANK-03, seção C](MAIS_BANK_03_SOURCE_VALIDATION.md).

## C. Matriz por unidade — somente operação Mais

| Unidade | Conta intermediária | Banco final | Repasse manual | Repasse automático | Status |
|---|---|---|---|---|---|
| Doze — 74014 | Asaas (“Posto Abreu e Lima”), conforme dono; titular/CNPJ/conta/custodiante exatos pendentes | Não comprovado; BB configurado para espécie não prova destino Mais | Possibilidade geral informada; autorização, canal e execução desta conta não comprovados | Possibilidade geral informada; regra/horário/saldo elegível e execução desta conta não comprovados | CONFIRMADA associação declarada; demais itens NÃO COMPROVADOS / DEPENDE DA MAIS/INSTITUIÇÃO |
| VIP — 11495, pista e própria conveniência | Fiserv, conforme dono; produto/custodiante/titular/conta pendentes | Não comprovado; não inferir Bradesco/Itaú de destinos de espécie | Não comprovado por conta/evento | Não comprovado por conta/regra/evento | CONFIRMADA associação declarada; demais itens NÃO COMPROVADOS / DEPENDE DA MAIS/INSTITUIÇÃO |
| Casa Caiada — 5555 | Fiserv, conforme dono; produto/custodiante/titular/conta pendentes | Não comprovado; não inferir BB/cofre de espécie | Não comprovado por conta/evento | Não comprovado por conta/regra/evento | CONFIRMADA associação declarada; demais itens NÃO COMPROVADOS / DEPENDE DA MAIS/INSTITUIÇÃO |

Matera permanece sem associação operacional comprovada. Não acrescentar unidade fictícia nem deduzir conta pelo enum. Fonte do mapa: confirmação do dono no [STATUS](../../STATUS.md); [units.json](../../WebPosto_API/src/modules/cash_reconciliation/config/units.json) é contexto, não prova de titularidade e não foi alterado.

## D. Modelo de conservação de saldo — proposta, não implementada

### Critérios mínimos de fechamento

Uma conta identificada por custodiante/produto/titular/CNPJ/conta/subconta, mesma moeda e base de saldo, no período com cortes explícitos:

**Saldo final calculado = saldo inicial oficial + créditos efetivados − débitos efetivados.**

**Resíduo = saldo final oficial − saldo final calculado.**

- Exigir saldo inicial **e** final oficiais, mesma base (contábil ou disponível), período/fuso/corte e extrato completo: todas as páginas/arquivos, créditos, débitos e ajustes, não só PIX ou transferências. A soma dos movimentos sem essas âncoras mede variação, não saldo. Não inferir saldo inicial zero.
- Saldo contábil não é automaticamente disponível. Bloqueios/liberações/reservas podem mudar o disponível sem débito contábil. Solicitar semântica e eventos oficiais; só usar `contábil = disponível + bloqueado` se o fornecedor confirmar que a identidade é válida para aquele produto. Saldo atual disponível não fecha período histórico.
- Quando a fonte permitir, decompor entradas em recebimentos PIX, outros créditos, devoluções de transferências e ajustes positivos; saídas em transferências efetivamente debitadas, tarifas, devoluções ao pagador, estornos e ajustes negativos. Preservar tipo bruto, sinal, ID, referência original, data efetiva e motivo. Tipo desconhecido continua explícito; se impedir interpretação/completude, fechamento inconclusivo.
- Usar lançamentos do extrato uma única vez. Se crédito já for líquido, a taxa não é subtraída novamente; se bruto e tarifa vierem separados, ambos entram. Detalhe Pix/comprovante enriquece o lançamento, **não cria outro crédito/débito**. Devolução/estorno é evento próprio, sem apagar original; transferência rejeitada pode ter débito e crédito de retorno, conforme extrato.
- Abertura é imediatamente antes dos movimentos incluídos e fechamento depois dos últimos incluídos, conforme corte da instituição. Sem ordem intradiária validada, conciliar período/dia, não inventar saldo a cada horário. Carregar fechamento anterior só se oficial, mesma base e sem lacuna; não transportar saldo simulado.
- Preservar precisão monetária/Decimal e moeda da fonte; nenhuma tolerância arbitrária. Resíduo zero, com cobertura/semântica/titularidade validadas, demonstra conservação da conta no período, **não autoria, ausência de fraude, composição individual de lotes ou crédito no destino**.
- Resíduo não zero com fontes incompletas = informação insuficiente. Com extrato completo e bases validadas = divergência de conciliação a apurar, não perda financeira automaticamente. Sem saldo oficial/semântica, não declarar fechamento mesmo que movimentos se compensem.

### Como distinguir os resultados

| Situação | Prova mínima / tratamento |
|---|---|
| Saldo ainda disponível | Snapshot/extrato oficial disponível no corte, conta e cobertura identificadas. Demonstra posição na conta, não quais PIX a compõem |
| Saldo bloqueado/reservado | Fonte oficial com valor, motivo e corte; não inferir bloqueio de diferença entre recebido e transferido |
| Repasse pendente | ID/status de solicitação/agendamento/processamento; separar eventual reserva do débito efetivo, sem dupla contagem |
| Repasse realizado na origem | ID/status efetivo e débito correspondente; ainda sem concluir recebimento pelo banco |
| Crédito bancário confirmado | Crédito oficial na conta destinatária e vínculo verificável com a transferência, conforme seção F |
| Divergência efetiva de conciliação | Resíduo não explicado com bases e cobertura comprovadas; investigar movimentos/duplicidades/ajustes, sem rotular como perda |
| Informação insuficiente | Falta de saldo, extrato, identificação, status, precisão temporal ou referência; explicitar o elo ausente, nunca preencher com zero |

Sem transferência no período, um fechamento oficial consistente pode mostrar recursos remanescentes na intermediária. Sem extrato completo, ausência de comprovante **não prova que não houve transferência**. Saldo remanescente não prova disponibilidade de cada PIX nem elimina a necessidade de comprovar seu crédito.

## E. Repasses agrupados e prevenção de falsas divergências

| Cenário | Tratamento determinístico proposto |
|---|---|
| A — vários PIX, um repasse | Validar cada crédito, saldo e débito agregado; alocação individual apenas com composição/referência oficial |
| B — manual parcial | Conferir débito e saldo remanescente; não tratar parcela não transferida como falta |
| C — automático | Validar regra/execução e valor elegível; separar modo do vínculo financeiro. Horário recorrente não comprova automação |
| D — saldo acumulado | Incluir abertura e movimentos anteriores necessários; repasse pode consumir recursos de outros dias |
| E — taxas/ajustes | Decompor eventos comprovados e sua incidência; não chamar residual de “taxa” sem documento |
| F — saída sem crédito final | Origem realizada com destino UNMATCHED/UNKNOWN conforme evidência; manter valor em trânsito, não crédito final ou perda presumida |
| G — entre empresas | Preservar titulares/CNPJs e autorização, débito/crédito separados; não somar transferência intragrupo como nova receita |

Reconciliação de saldo consistente permite explicar o agregado de recursos e transferências, **não escolher quais PIX compõem um repasse de saldo fungível**. Sem composição explícita, registrar “saldo conciliado; vínculo individual não comprovado”. Não usar FIFO, soma por valor, rateio proporcional ou candidato único como prova. N:N/fracionamentos exigem referências e controle de alocações/remanescentes sem reutilizar o mesmo valor.

Pedido manual e rotina automática podem coexistir: identificar cada transferência por conta + ID e débitos relacionados, não por modo/horário. Rejeição/reenvio pode gerar IDs distintos, reversões ou nenhum débito; preservar tentativas sem duplicar a transferência efetiva. Dias úteis/feriados/janelas dependem do produto; não presumir D+1 nem ignorar feriados. Movimentos fora da janela ficam pendentes de observação.

## F. Confirmação no banco de destino

Exigir simultaneamente:

1. Origem/titular/conta e destino/titular/conta identificados; detalhe da transferência, débito efetivo, valor/moeda, taxas, data/status e comprovante/ID.
2. Extrato oficial completo do banco destinatário e linha de crédito efetiva, data/horário na precisão fornecida, documento/FITID e detalhe de contraparte/E2E quando necessário. Comprovante da origem não substitui esse extrato.
3. Referência comum verificável: E2E **de saída** para PIX ou documento bancário equivalente confirmado pelas fontes. E2E do cliente não é E2E do repasse; FITID não é E2E. Destino/contraparte, valor e datas corroboram, sem substituir a referência quando houver ambiguidade.
4. Tarifas/parcelamentos/reversões explicados, sem usar crédito de outra operação nem duplicar alocação. Nome da instituição no histórico, valor igual, soma de valores ou único candidato na janela são candidatos para revisão, não confirmação automática.

Sem identificador comum inequívoco, reunir detalhes oficiais e revisão humana documentada; manter pendência enquanto o vínculo não for demonstrável. Arquivo hash preserva integridade da cópia, não autentica sozinho a origem. Saldo bancário inicial/final também é necessário se o objetivo futuro incluir fechar a conta final inteira, além de demonstrar o crédito.

Estados conceituais, **não enums implementados**; estados da transferência e da conciliação são dimensões separadas:

| Estado | Significado mínimo |
|---|---|
| `TRANSFER_REQUESTED` | Solicitação/agendamento identificados; não execução |
| `TRANSFER_PROCESSING` | Processamento segundo origem; reserva/débito devem ser informados separadamente |
| `TRANSFER_COMPLETED_AT_SOURCE` | Origem informa execução e débito correspondente; não confirma destino |
| `CREDIT_CONFIRMED_AT_DESTINATION` | Crédito oficial do destino associado de forma verificável |
| `REJECTED` | Rejeição/falha/cancelamento terminal documentado, preservando motivo e eventuais devoluções |
| `UNMATCHED` | Movimento/transferência conhecido, mas vínculo ainda não demonstrado; pode coexistir com conclusão na origem |
| `UNKNOWN` | Fonte/status/conta/cobertura insuficientes; não promover ausência a rejeição ou sucesso |

Não mapear status só por tradução: validar contrato e amostra do produto; saldo bloqueado ou transferência bloqueada não são rejeição terminal automaticamente. Reversões posteriores preservam o crédito histórico e indicam valor líquido/estado atual, sem “desconfirmar” silenciosamente o evento original.

## G. Reaproveitamento — REUSE > ADAPT > CREATE

| Componente | Classificação | Dependência/adaptação mínima futura |
|---|---|---|
| [extrato_reader.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py) | REUSE / ADAPT | Leitura OFX/Decimal/sinais/hash/data/FITID. Não preserva `LEDGERBAL`/`AVAILBAL`, conta completa/CNPJ ou E2E estruturado; `saldo_liquido` é variação. Exigir âncoras oficiais e detalhe complementar |
| Mesmo leitor: validação de completude | ADAPT antes de uso como prova integral | Pode pular lançamento sem data, gerar FITID `TRN_*` e deduplicar pela tupla; verificar contra arquivo bruto/contagens/totais, rejeitar conflitos e ausência de ID confiável na prova. Nenhuma correção feita aqui |
| [models.py](../../WebPosto_API/src/modules/cash_reconciliation/domain/models.py), [tempo.py](../../WebPosto_API/src/modules/cash_reconciliation/domain/tempo.py) | REUSE / ADAPT | Decimal, empresa, proveniência e helpers temporais; acrescentar por necessidade identidade protegida da conta, moeda/base/cortes de saldo e referências originais. Não fabricar hora |
| [conciliar.py](../../WebPosto_API/src/modules/cash_reconciliation/application/conciliar.py), DiaCofre/FluxoCofre | NÃO REUTILIZAR diretamente como fechamento da intermediária | `_dias` começa em zero e usa sangrias/depósitos de espécie. É variação do cofre no período, não saldo oficial da conta; apenas referência de organização |
| [persistência](../../WebPosto_API/src/modules/cash_reconciliation/adapters/persistencia.py), [pendências](../../WebPosto_API/src/modules/cash_reconciliation/adapters/pendencias.py) | REUSE / ADAPT | JSON atômico e padrões SQLite/histórico; manter cópias originais/revisões, IDs e escopo. Não executar gravação ou presumir trilha imutável universal |
| [integridade da execução](../../WebPosto_API/src/modules/cash_reconciliation/domain/integridade_execucao.py) | REUSE / ADAPT | Estados de fonte, run/cobertura e stale; saldo e transferência exigem semântica própria, não transformar SUCCESS da coleta em crédito confirmado |
| [relatórios](../../WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py) | REUSE / ADAPT | Explicações, faltas de fonte e pendências; separar conservação, origem/destino e composição. Não ligar ao job/Telegram nesta etapa |
| [units.json](../../WebPosto_API/src/modules/cash_reconciliation/config/units.json), [helper GET](../../WebPosto_API/src/modules/webposto_integration/http.py), [total Mais](../../WebPosto_API/src/modules/cash_reconciliation/application/mais_pagamentos.py) | REUSE como contexto | Manter escopo/declaração humana e configuração operacional; não equiparar cadastro ERP a titularidade/credencial bancária |
| [pix_cnpj.py](../../WebPosto_API/src/modules/cash_reconciliation/application/pix_cnpj.py) | ADAPT | Cobertura/ID/conflitos úteis; hoje PagBank, com candidatos por valor/hora e filtros que excluem grupo/provedores. Não aplicar diretamente a repasse |
| [matching.py](../../WebPosto_API/src/modules/cash_reconciliation/rules/matching.py), cliente Mais sandbox/baseline legado | NÃO REUTILIZAR como prova | Aproximações de espécie/soma/valor e respostas fictícias não conciliam dinheiro real |
| Normalização de saldo/repasse e validação de amostra | CREATE somente complemento mínimo após autorização | No módulo existente; âncoras oficiais, lançamentos completos, resíduo e provas de origem/destino. Sem novo conector/arquitetura paralela ou código legado |

RN-REDE-004 mantém conciliação de depósitos fora do escopo operacional; este documento prepara um diagnóstico/piloto Mais, não altera essa regra nem habilita conciliação em produção. ADR-002 comprova viabilidade histórica de espécie, não fechamento Asaas ou crédito Mais.

### Risco operacional prioritário — travas não universais

Informação do dono mantida: `WEBPOSTO_WRITES=0`, `LOGOS_ERP_ESCRITA=0`; **nenhuma leitura do arquivo para verificar valores**. A [inspeção estática MAIS-BANK-03, seção E](MAIS_BANK_03_SOURCE_VALIDATION.md) continua válida:

- Cartão incluir/excluir verifica ambas as flags físicas iguais a `1`, bloqueando ausências/duplicidades.
- OFX verifica `WEBPOSTO_WRITES` + `LOGOS_OFX_IMPORTACAO`, não a segunda flag geral; faz GET de contas antes da barreira, inclusive na prévia.
- SDK [HTTP](../../WebPosto_API/src/webposto/http.py)/[financeiro](../../WebPosto_API/src/webposto/endpoints/financeiro.py) e proxies [app](../../WebPosto_API/src/presentation/app.py)/[explorador](../../WebPosto_API/explorador_standalone.py) não compartilham guarda universal; SDK admite retry de métodos mutantes.
- Gate de publicação do [job](../../WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py) não bloqueia genericamente esses caminhos alternativos.

**Risco relevante para qualquer execução futura:** flags zeradas não comprovam congelamento de todos os caminhos. Não chamar writers, proxies, preview de importação ou aplicação para validar documentos. Não se afirmou exposição em produção nem se atribuiu severidade explorável sem avaliação própria. Sem execução/correção funcional nesta etapa; eventual endurecimento exige autorização separada.

## H. Lacunas e perguntas à Mais/instituições — não enviadas

1. Para **Doze, VIP e Casa Caiada**, qual CNPJ/titular/conta Mais/subconta, produto, instituição executora/custodiante (razão social/ISPB) e banco/titular/conta destino? Qual associação operacional Matera? Não incluir a 118508 no levantamento Mais.
2. Manual: quem solicita, em qual portal/canal, com quais perfis/limites, aprovação, saldo elegível e comprovante? O operador pode selecionar outro titular/destino? Como documentar autorização interempresa?
3. Automático: rotina pertence à Mais ou à instituição? Quem configura, qual horário/fuso, vigência/versão da regra, calendário, feriados/finais de semana e frequência? Pode executar várias vezes, coexistir com manual ou ser desativada?
4. Transfere total ou parcial? Percentual/teto/piso, valor mínimo, saldo mínimo residual, reserva/bloqueios/retenções e critérios de disponibilidade? Como tratar saldo de dias anteriores?
5. Há extrato oficial completo, saldos de abertura/fechamento por base, disponível/bloqueado e cortes históricos? Qual diferença entre saldo Mais e da custodiante? Como registrar liberação/bloqueio sem duplicar débito?
6. Qual consulta/exportação lista **todos** os repasses e tentativas, separa solicitado/executado, manual/automático/autor e associa execução da rotina ao ID financeiro? Formato, paginação, cobertura e referência original?
7. Quais IDs de transação/E2E/crédito/débito/transferência e comprovantes ligam as fontes? Existe composição de lote ou o repasse é apenas retirada de saldo fungível? Como representar fracionamentos e tarifa?
8. Qual política de rejeição, bloqueio, cancelamento, reenvio/idempotência, devolução e estorno? Tentativa cobra tarifa? Há crédito de retorno e prazo/status terminal documentado?
9. Quais tarifas de recebimento/repasse e ajustes/retenções, quando incidem, líquido versus bruto, vigência e lançamentos correspondentes? Não assumir que diferença seja taxa.
10. Que contrato/permissão permite leitura da conta específica Asaas/BaaS, Matera e Fiserv pelo estabelecimento? Mais/Quality fornecem canal ou parceiro? Existe escopo somente leitura e acesso histórico? Não solicitar segredos no Git nem testar autenticação sem aprovação.
11. Quality: quais IDs e origem externa ficam em vendas/movimentos/remessas? Como provar sincronização bancária independente, arquivo/linha/ID e atualização? ERP/OFX importado não cria segunda prova.
12. Banco destino: fornecer extrato oficial completo e detalhe do crédito, remetente/titular, E2E/documento, valor/moeda/data efetiva, tarifas e reversões. Qual canal autorizado fornece essa informação sem movimentação financeira?

## I. Próximo experimento real — preparado, não executado

**Uma unidade: Doze 74014/Asaas; PIX de 14/10/2026; observação de 14 a 16/10/2026.** Janela só se amplia com aprovação se o ciclo real exceder o período; não presumir repasse ou D+1.

Menor pacote oficial autorizado, fornecido pelo titular em canal protegido:

1. Identificação/titularidade da conta intermediária e banco final; uma venda e detalhe Mais de um PIX/E2E do dia 14, com valores/taxa/status.
2. Extrato Asaas **completo** de 14–16, saldo de abertura anterior ao primeiro evento e fechamento depois do último, mesma base/cortes; disponível/bloqueado separados quando aplicável. Detalhe Pix e referência do crédito. Saldo atual não substitui histórico.
3. Se houver repasse: detalhe/comprovante/ID/E2E, débito e tarifa, destino, status e evidência do modo manual/automático. Se houver composição de lote, fornecê-la; senão não atribuir individualmente os PIX.
4. Extrato oficial do banco final do mesmo intervalo e detalhe do crédito correspondente; ampliar só se autorizado para crédito posterior. Se não houver transferência, comprovar posição remanescente e completude, sem inventar crédito no banco.

Primeiro validar documentalmente identidade, cobertura, sinais e âncoras de saldo; depois conservação agregada; por fim origem→destino quando houver transferência. Não selecionar apenas as linhas que fazem a conta fechar.

**Aceite do experimento:** demonstrar o crédito intermediário do PIX e conservação oficial do período; se houver repasse, comprovar saída e crédito final independente. Sem repasse comprovado, resultado correto pode ser “recursos remanescentes na intermediária; transferência/crédito final não aplicável ao caso observado”, nunca “cadeia de repasse validada”. Modo desconhecido, composição ausente ou crédito fora da janela ficam explícitos.

**Menor trabalho futuro de implementação, somente após amostras e aprovação:** adaptar modelos/proveniência e relatório existentes para normalização local e fechamento com âncoras oficiais; reaproveitar OFX após validar suas limitações. Testar saldo inicial não zero, saldo retido/bloqueado, parcial/agrupado, taxa líquida/separada, reversão/rejeição, duplicidade, fonte incompleta e saída sem crédito. Nenhum novo conector, importação ERP ou alteração do job nessa primeira prova.

**Encerramento:** faltam extratos/âncoras, acesso à conta específica e dados de transferências reais; não há fechamento ou cadeia completa comprovada. Documentos anteriores tiveram apenas correção anotada de escopo. Configuração, `.env`, produção e dados financeiros intactos; nenhuma chamada externa ou operação financeira. **Parado para aprovação do dono.**
