# MAIS-BANK-03 — Contas recebedoras, extratos e repasses

**17/10/2026 · `feature/cash-audit-fechamento` · diagnóstico somente leitura; implementação não autorizada.**

Repositório e branch conferidos: `C:\Projetos\LOGOS\LogosPostos`, conforme solicitado. HEAD na conferência final anterior à edição: `5bff018`. Houve atualização concorrente do histórico/status durante a investigação; conteúdo preservado. O legado foi apenas consultado, nunca tratado como fonte de verdade.

**Conclusão:** ainda não existe caso comprovado de **venda webPosto → PIX Mais → crédito intermediário → repasse → crédito bancário final**. Asaas oferece o caminho documental mais concreto; Matera e Fiserv exigem primeiro identificar produto, custodiante, conta e direito de acesso. Priorizar a obtenção de evidências das duas contas, não o aperfeiçoamento isolado da confirmação do pagamento.

Base: [MAIS-BANK-01](MAIS_BANK_01_SOURCE_GAP_MATRIX.md), [MAIS-BANK-02](MAIS_BANK_02_SETTLEMENT_SOURCES.md), [auditoria de capacidade](LOGOS_CURRENT_CAPABILITY_AUDIT.md), [regras de negócio](../regras-negocio/REGRAS_DE_NEGOCIO.md), [ADR-002](../architecture/adr/ADR-002-cash-arch-01-antes-do-arch-02.md), [ADR-003](../architecture/adr/ADR-003-autonomia-gradual-de-escrita-no-erp.md), contratos e componentes vinculados abaixo. A documentação pública Asaas/Fiserv é a registrada na etapa 02, **sem nova consulta externa nesta etapa**. Não foram executados aplicação, testes, jobs ou scripts; nenhum acesso a `.env`, conta real, Telegram, agendador ou operação financeira. Somente este relatório e [STATUS](../../STATUS.md) foram editados nesta etapa; sem migração, deploy, commit, push ou merge.

Classificações: **CONFIRMADO EM EXECUÇÃO REAL** exige evidência operacional histórica identificada; **DOCUMENTADO** significa contrato, não acesso; **IMPLEMENTADO NÃO VALIDADO** significa código sem validação suficiente; **PARCIAL** cobre só parte da cadeia; **NÃO ENCONTRADO** limita-se ao material examinado; **DEPENDE DE TERCEIRO** exige autorização/informação externa. Nenhuma cadeia Mais recebe a primeira classificação.

## A. Matriz por unidade

**Correção de escopo — 17/10/2026, confirmação posterior do dono:** a Conveniência 24h (118508) **não utiliza Mais Pagamentos**. Retirada desta matriz e da investigação de repasses Mais; a classificação anterior de plataforma pendente fica superada, não constitui pendência de acesso. Nenhuma associação Asaas/Matera/Fiserv deve ser buscada para essa unidade no contexto Mais. Mantida nos demais módulos aplicáveis, sem alteração de configuração. Escopo vigente: Doze, VIP (incluindo sua própria conveniência) e Casa Caiada.

| Empresa | Plataforma | Conta intermediária | Banco final | Fonte | Evidência | Status |
|---|---|---|---|---|---|---|
| Doze — 74014 | Asaas, segundo o dono; cadastro Mais chamado “Posto Abreu e Lima” | Custodiante, titular/CNPJ, conta/subconta e vínculo ao ID Mais: PENDENTE DE VALIDAÇÃO | PENDENTE DE VALIDAÇÃO; BB configurado para espécie não comprova destino Mais | [STATUS](../../STATUS.md), [configuração](../../WebPosto_API/src/modules/cash_reconciliation/config/units.json), regras de negócio | Declaração humana e Mais pendente no cadastro; sem extrato Asaas ou crédito de repasse identificado | PARCIAL; DEPENDE DE TERCEIRO |
| VIP — 11495, pista e própria conveniência | Fiserv, segundo o dono; não presumir produto | Custodiante, titular/CNPJ, conta e vínculo Mais: PENDENTE DE VALIDAÇÃO | PENDENTE DE VALIDAÇÃO; Bradesco/Itaú na configuração são destinos de espécie | Mesmas fontes | Mesmo CNPJ para pista/loja é regra declarada; faltam documento de titularidade e identificação da conta | PARCIAL; DEPENDE DE TERCEIRO |
| Casa Caiada — 5555 | Fiserv, segundo o dono | Custodiante, titular/CNPJ, conta e vínculo Mais: PENDENTE DE VALIDAÇÃO | PENDENTE DE VALIDAÇÃO; BB/cofre não prova repasse eletrônico | Mesmas fontes | Mais pendente no cadastro; sem extrato da recebedora ou crédito final identificado | PARCIAL; DEPENDE DE TERCEIRO |

**Para todas as unidades:** números de CNPJ, identidade bancária completa, titularidade comprovada, produto, modalidade/frequência de repasse, acesso autorizado e IDs reais da cadeia estão **PENDENTES DE VALIDAÇÃO**. A configuração oficial não contém CNPJ; o modelo de unidade e o cadastro genérico de tenants não suprem essa prova. Não publicar números completos de contas/credenciais no relatório.

**Matera:** o dono confirma sua presença no ecossistema, mas não indica a unidade. Nenhuma associação empresa → Matera foi comprovada; o enum Mais não permite inferi-la. As relações acima não foram fixadas em código.

## B. Plataformas e fontes da cadeia

| Plataforma | Extrato | PIX | Repasse | Tarifas | Identificadores | Acesso | Status |
|---|---|---|---|---|---|---|---|
| Asaas | GET `/v3/financialTransactions`: lançamento, data, valor, saldo, tipo; `/v3/finance/balance`: saldo atual, não prova individual | GET `/v3/pix/transactions` e `/{id}`: crédito/débito, status, valor, criação/efetivação, devolução | GET `/v3/transfers` e `/{id}`: destino, execução, valor/líquido, status, comprovante; ligar ao débito no extrato | `chargedFeeValue`, `transferFee`, movimentos de tarifa/reversão | E2E, ID Pix, `payment` → `paymentId`; `transferId`, E2E de saída, referência externa | `access_token` documentado; conta Doze/subconta BaaS e permissão restrita à leitura não comprovadas | DOCUMENTADO; DEPENDE DE TERCEIRO |
| Matera | NÃO ENCONTRADO contrato local aplicável à conta; não inventar endpoint/saldo | Enum `MATERA` na Mais não documenta consulta Pix Matera | NÃO ENCONTRADO canal aplicável de transferências/repasses | NÃO ENCONTRADO layout aplicável | NÃO ENCONTRADO contrato de IDs da operação | Produto, instituição mantenedora/custodiante, modelo de conta e acesso do estabelecimento/parceiro desconhecidos | NÃO ENCONTRADO; DEPENDE DE TERCEIRO |
| Fiserv | NÃO ENCONTRADO contrato de extrato da conta utilizada | Existência pública de Hub Pix/SiTef registrada na etapa 02; não identifica o produto contratado | NÃO ENCONTRADO canal aplicável de conta/repasse | NÃO ENCONTRADO layout aplicável | Sem amostra aplicável; enum `FISERV` não supre | Quality/Fiserv precisam identificar produto, custodiante/PSP, portal, contrato e autenticação | PARCIAL; DEPENDE DE TERCEIRO |

### Mais Pagamentos: o que o contrato realmente permite

No [OpenAPI Mais local](../external/maispagamentos/openapi_integracao_2026-10-11.json), base declarada `https://api.maispagamentos.com.br` — não chamada:

- **Transação individual — DOCUMENTADO:** GET `/transacoes/v1/{conta}` e `/transacoes/v1/{conta}/{transacao}`, além das variantes V2; V2 admite busca por `txId`. O detalhe expõe `id`, `transacaoId`, `endToEndId`, `dataHora`, status, `valorBruto`, `valorPago`, `valorLiquido`, `taxa`, recebedor/CNPJ e `cnpjInstituicaoIntermediadora`. A lista não substitui o detalhe. Status V2: aberta/concluída/devolvida.
- **Conta intermediária — PARCIAL:** o parâmetro `{conta}`, CNPJ intermediador e enum de instituições ajudam a pedir o mapa; não constituem extrato dessa conta. `instituicao` descreve a instituição pagadora; agência/conta não têm papel suficientemente claro para tratá-las como conta recebedora/custodiante.
- **Saída Pix — DOCUMENTADO:** GET `/contas/v1/{id}/pagamento-chave-pix` por `idTransacao` e `/pagamento-qr-code` por `idPagamento`. Retorno pode conter `idPagamento`, `e2eId`, valor, status/status externo, data, pagador e recebedor/destino. São consultas de pagamento conhecido, **não listagem de repasses nem prova de crédito no destino**.
- **Liquidação/extrato consolidado — NÃO ENCONTRADO:** sem endpoint dedicado de extrato/saldo/lista de repasses ou ID inequívoco de liquidação no contrato examinado. Existência de extrato consolidado no portal e sua exportação permanecem **DEPENDE DE TERCEIRO**. Não concluir que não existem.
- **Última confirmação — DOCUMENTADO:** GET `/transacoes/v1/ultima-confirmacao-pagamento`; enum inclui `MATERA`, `ASAAS`, `FISERV` e outros. Timestamp de última confirmação não é movimento financeiro nem prova de acesso a essas plataformas.
- **Autenticação — DOCUMENTADO, não validado:** POST `/usuarios/v1/login-integracao` exige `Authorization`, `grant_type` e `scope`; `/usuarios/v1/login-pdv` usa corpo `cnpj`, `conta`, `pdv`, com outro modelo de retorno. A diferença existe no contrato; a elegibilidade estabelecimento × parceiro e os escopos de consulta dependem da Mais/Quality. Não reutilizar credenciais webPosto por suposição. Histórico registra 401, não login bem-sucedido; nenhum login foi repetido.

O oficial [mais_pagamentos.py](../../WebPosto_API/src/modules/cash_reconciliation/application/mais_pagamentos.py) registra total/detalhes informados pelo diretor, unidade/dia e proveniência humana, **não captura API, E2E ou crédito bancário**. O cliente legado continua inadequado: `/v1/transactions` e `/v1/settlements` não constam desse contrato e falhas podem virar dados sandbox aprovados/liquidados; o reconciliador ainda substitui total ERP ausente por baseline do provedor. Testes sintéticos não comprovam funcionamento real. Achados e arquivos detalhados no [MAIS-BANK-01, §4.2](MAIS_BANK_01_SOURCE_GAP_MATRIX.md).

### Campos, comprovação e lacunas

| Etapa financeira / fonte | Evidência disponível | Lacuna | Próxima ação |
|---|---|---|---|
| Venda / webPosto | Empresa, venda, caixa, data/valor, modalidade/administradora e referências internas | E2E e vínculo ao Pix Mais não comprovados no caso real | Amostra de uma venda e transação Mais correspondentes, não apenas total diário |
| Pagamento / Mais | Contrato: IDs, E2E, CNPJ recebedor/intermediador, bruto/pago/líquido/taxa, data/hora/status | Sem resposta autenticada validada; sem mapa de conta ou ID único de liquidação | Detalhe oficial sanitizado e autorização específica |
| Crédito recebedor / Asaas | Contrato: ID do lançamento, `date`, `value`, `balance`, tipo e referências; Pix fornece horário de efetivação/E2E | Extrato da conta específica e junção por E2E/`paymentId` ausentes; extrato não fornece horário de cada linha | Extrato oficial + detalhe Pix/cobrança da mesma conta/período |
| Crédito recebedor / Matera ou Fiserv | Declaração de ecossistema/enum; Fiserv associada a VIP/5555 pelo dono | Sem extrato aplicável, titular, conta, IDs, datas/valores/taxas comprovados | Identificar produto/custodiante e obter contrato/layout antes de conector |
| Repasse / intermediária | Asaas documenta ID/E2E de saída, valor/líquido/taxa, execução/status, banco/ISPB/agência/conta/titular/CNPJ destino | Sem transferência real e composição do lote; Matera/Fiserv sem contrato aplicável | Detalhe/comprovante + débito/tarifa + composição oficial, se agregada |
| Crédito final / banco | Leitor OFX preserva data/hora quando fornecida, valor/sinal, documento, descrição, FITID e hash do arquivo | Nenhum crédito de repasse identificado; E2E/contraparte estruturados não preservados; conta completa/titular pendentes | Extrato oficial completo e detalhe bancário com E2E/documento, remetente e conta destinatária |

Nenhum valor/data de pagamento, crédito intermediário ou repasse novo foi obtido. Não preencher ausências com simulação. O saldo Asaas é saldo de conta; `saldoAtual` ERP é saldo interno; `saldo_liquido` do leitor OFX é soma dos movimentos do arquivo, **não saldo bancário**. O leitor não preserva `LEDGERBAL`/`AVAILBAL`.

## C. Cobertura webPosto: contexto, não segunda prova bancária

Contrato analisado: [OpenAPI webPosto](../external/webposto/openapi_integracao_2026-10-06.json). Rotas abaixo são GET, salvo indicação; nenhuma foi executada.

| Rota sob `/INTEGRACAO` | Utilidade documentada | Limite de comprovação |
|---|---|---|
| `/V1/VENDAS`, `/V1/VENDAS/ITENS`, `/V1/CAIXAS`, `/V1/VENDAS_FORMA_PAGAMENTO` | Venda/caixa e forma: `empresaCodigo`, `vendaCodigo`, `financeiroCodigo`, `valorPagamento`, `taxaValor`, `taxaPercentual`, administradora | Expectativa/classificação ERP; não crédito da intermediária. PIX sintetizado pelo adaptador não ganha E2E/NSU por isso |
| `/V1/ADMINISTRADORAS` | Cadastro, referência externa/EDI, comissão, antecipação, taxa | Configuração não prova contrato ativo, conta custodiante ou tarifa efetivamente debitada |
| `/V1/CARTOES` | Venda, NSU/NSU TEF/autorização, vencimento, valor/taxa e data de pagamento | Recebível/baixa ERP; não extrato bancário |
| `/V1/CARTOES_REMESSA` | `cartaoRemessaCodigo`, referência, datas remessa/pagamento/recebimento, valor, despesas, líquido/acréscimos | Potencial lote interno; sem prova de vínculo à Mais ou à transferência bancária real |
| `/V1/CARTOES_PAGAR` | Cartões de compra a pagar, valor, situação e datas | Não presumir recebimento de vendas ou repasse Mais |
| `/V1/TITULOS_RECEBER`, `/V1/TITULOS_PAGAR` | Título, pendência, data/valor, cliente/venda/documento; modelo de recebimento tem referência/tipo/data/valor | Registro de obrigação/baixa, não confirmação independente de crédito. `RECEBER_*` e pagar título são mutações, fora do escopo |
| `/V1/CONTAS` | `contaCodigo`, empresa, descrição, `saldoAtual`, `usaOfx` | Cadastro/saldo ERP; sem identidade bancária completa ou certificado de origem |
| `/V1/MOVIMENTOS_CONTA` | Conta, valor/data, saldo, tipo/documento de origem, documento/lote, conciliação | Origens incluem manual/caixa/cartão/transferência; mesmo recurso aceita POST/PATCH. `conciliado` não prova banco |
| `/V2/TRANSFERENCIAS_BANCARIAS` | `transferenciaBancariaCodigo`, conta, venda/caixa, `contaOrigem`, documento, valor/data | Transferência registrada no ERP; não execução bancária ou crédito no destino |
| `/V1/OFXS` — somente POST | Modelo de entrada tem `dataCredito`, `extratoExterno`, contraparte | Não há GET segregado de OFX bancário importado nessa cópia; retorno de movimento não expõe essa linhagem como tal. Não importar |

Não foi localizada rota/nome/descrição Mais ou PAGPIX no contrato oficial examinado. O [script legado VIP](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/scripts/audit_vip_receipt_sources.py>) menciona `/INTEGRACAO/CNPJ_REDES_PAGPIX`: existência de tentativa de sondagem, não contrato ou operação bem-sucedida. O alias legado `PAGPIX → PagBank` é classificação de texto, não prova de conta ou custodiante; o dono registra PAGPIX desativada.

**Execução histórica limitada:** matriz antiga registra movimento 63005844 e transferência ERP 26245718, VIP/01/06/2026/R$ 50,00: **CONFIRMADO EM EXECUÇÃO REAL somente quanto ao vínculo interno registrado**, não ao recebimento bancário. A importação oficial OFX de 507 linhas do dia 10/10 foi registrada com débitos errados e exclusão posterior relatada; aceite HTTP não é validação financeira. Referências em [MAIS-BANK-01, §4.3](MAIS_BANK_01_SOURCE_GAP_MATRIX.md).

**Resposta:** há pagamentos/recebíveis e movimentos internos aproveitáveis; não foi comprovada sincronização independente das contas intermediárias. Para usar movimento importado como evidência, Quality deve demonstrar procedência, ID bancário, arquivo e regra de sincronização. Reimportar nosso OFX e relê-lo no ERP não cria segunda fonte.

## D. Reutilização e maturidade

| Componente existente | Decisão | Maturidade / condição para etapa futura |
|---|---|---|
| [extrato_reader.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py) | REUSE | PARCIAL: base oficial de leitura OFX/Decimal/sinais/hash/FITID; ADR-002 registra uso real para espécie. Não validado para cadeia Mais; revisar amostra, ausência de FITID e identidade da conta |
| [webposto_integration/http.py](../../WebPosto_API/src/modules/webposto_integration/http.py), [webposto_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py) | REUSE | PARCIAL: paginação GET e contexto de vendas oficiais; execução histórica ERP não supre prova bancária. Não invocados aqui |
| [modelos/proveniência](../../WebPosto_API/src/modules/cash_reconciliation/domain/models.py), [integridade da execução](../../WebPosto_API/src/modules/cash_reconciliation/domain/integridade_execucao.py) | ADAPT | IMPLEMENTADO NÃO VALIDADO para a nova cadeia: reutilizar Decimal, escopo/estado da fonte, cobertura e hash; faltam identidade CNPJ/conta e referências de cada etapa |
| [persistência](../../WebPosto_API/src/modules/cash_reconciliation/adapters/persistencia.py), [pendências](../../WebPosto_API/src/modules/cash_reconciliation/adapters/pendencias.py), [relatório diário](../../WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py) | REUSE / ADAPT | PARCIAL: JSON atômico/SQLite e apresentação já existentes; preservar fonte original/revisões, não declarar trilha imutável onde não existe |
| [pix_cnpj.py](../../WebPosto_API/src/modules/cash_reconciliation/application/pix_cnpj.py) | ADAPT | PARCIAL: conta/cobertura/deduplicação e conflito são úteis; hoje PagBank, com candidato valor/hora e exclusão de rótulos do grupo/provedores. Não aplicar diretamente a repasses |
| [ofx_reader.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/ofx_reader.py), [matching.py](../../WebPosto_API/src/modules/cash_reconciliation/rules/matching.py) | NÃO REUTILIZAR como conciliador eletrônico | PARCIAL: focados em espécie/depósitos, aproximação por valor/janela/somas. Podem servir de referência de apresentação, não provar composição de lote |
| [units.json](../../WebPosto_API/src/modules/cash_reconciliation/config/units.json), [total Mais humano](../../WebPosto_API/src/modules/cash_reconciliation/application/mais_pagamentos.py) | ADAPT | PARCIAL: escopo de unidade e declaração rotulada; não criar CNPJ, conta ou IDs a partir do nome. Total humano nunca virar captura autenticada |
| Clientes/autenticação Mais legados e baseline/sandbox | NÃO REUTILIZAR | IMPLEMENTADO NÃO VALIDADO: rotas divergentes, fallback fictício, risco de falso sucesso; testes não provam execução financeira |
| SDK [HTTP](../../WebPosto_API/src/webposto/http.py)/[financeiro](../../WebPosto_API/src/webposto/endpoints/financeiro.py), writers OFX/cartão e proxies | NÃO REUTILIZAR para o piloto somente leitura | PARCIAL: há mutações/retries e proteção não universal; não chamar envio/importação nem “preview” que consulte rede |
| Ligação de evidências intermediária → repasse → banco | CREATE apenas o complemento mínimo, após aprovação | NÃO ENCONTRADO hoje: normalização de amostra e referências no módulo existente; só depois avaliar conector oficial, sem arquitetura paralela |

Referência apenas, sem migração: o classificador Mais antigo mantém `PENDENTE_FONTE_EXTERNA`, inclusive quando há OFX; correto não promover isso a banco confirmado. Parsers/matchers legados não superam a base oficial nem resolvem a ausência de ID comum.

## E. Lacunas, riscos e mecanismo mínimo proposto

### Travas: inspeção estática, sem ler configuração nem executar funções

O dono informou `WEBPOSTO_WRITES=0` e `LOGOS_ERP_ESCRITA=0`. Isso é **declaração do dono**, não verificação deste diagnóstico. O status preexistente registra reprocessamentos; não foram reexecutados ou revalidados aqui.

| Caminho conhecido | Verifica ambas as flags solicitadas? | Risco / limite |
|---|---|---|
| [Cartão: verificar_travas_cartao, incluir/excluir](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_cartao.py) | Sim, ambas físicas exatamente `1`; ausentes/duplicadas/inválidas bloqueiam antes do POST/DELETE | Com valores declarados `0`, o caminho deveria bloquear; não testado nem arquivo lido |
| [OFX: verificar_travas_ambiente/enviar](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py) | Não: exige `WEBPOSTO_WRITES` + `LOGOS_OFX_IMPORTACAO`, não `LOGOS_ERP_ESCRITA` | `WEBPOSTO_WRITES=0` deveria bloquear envio; segunda flag geral não é kill-switch universal. Preview/envio pode fazer GET antes da barreira; não executar |
| SDK HTTP/financeiro | Não há essas guardas comuns nos métodos genéricos | POST/PUT/PATCH/DELETE disponíveis, inclusive retry no SDK; credencial não equivale a autorização |
| [Proxy da aplicação](../../WebPosto_API/src/presentation/app.py), [explorador](../../WebPosto_API/explorador_standalone.py) | Não nos encaminhamentos examinados | Corpo escolhe método/path, inclusive mutação; não assumir read-only nem afirmar exposição em produção sem evidência |
| [Job: gate de publicação](../../WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py) | Não: checa `WEBPOSTO_WRITES=0` e automático de cartão desligado | Gate de publicação/integridade não protege genericamente todos os clientes de escrita |
| Helper GET oficial | Só paginação GET, sem métodos mutantes | Reutilizável para consulta futura autorizada; executá-lo ainda acessaria configuração/rede |

Outros caminhos sem guarda compartilhada (produto CRUD e REST alternativo) estão inventariados na [auditoria, §9](LOGOS_CURRENT_CAPABILITY_AUDIT.md#9-escritas-existentes). **Não concluir que flags zeradas congelam todo o repositório.** Nada foi executado ou corrigido: endurecimento de escrita exige trabalho próprio aprovado; o piloto não deve depender dessas superfícies.

### O que impede comprovar e como tratar sem inventar vínculos

1. **Identidade/acesso:** falta CNPJ/titular/conta/subconta/custodiante de origem e destino, contrato e autorização por empresa. Sufixo OFX ou nome da unidade não é identidade global; conta compartilhada não autoriza misturar empresas.
2. **Amostras oficiais:** faltam resposta Mais, extrato intermediário, detalhe/débito de repasse e crédito destino do mesmo caso. API pública Asaas não assegura acesso BaaS da Mais; Matera/Fiserv ainda sem contrato aplicável. Não localizado cliente de API de extrato bancário final validado para essas contas.
3. **Vínculos mínimos futuros:** preservar fonte/arquivo/hash, empresa/CNPJ e conta, ID original, tipo/status, datas de criação/efetivação e precisão/fuso fornecidos, moeda/valor bruto/líquido/taxa. Relacionar venda ao pagamento por referência explícita; pagamento ao crédito por E2E e referências oficiais (`paymentId`, quando aplicável); débito ao repasse pelo ID; repasse ao crédito final por E2E/documento bancário e identidade das contas. E2E de entrada e de saída são distintos; FITID não é E2E; ID de lançamento não é ID de liquidação.
4. **Agrupamentos/fracionamentos:** relação N:N só com composição/referências oficiais e valores alocados sem dupla contagem. Dinheiro fungível em saldo e soma de PIX igual a um repasse não comprovam sua composição. Sem vínculo inequívoco: **pendente de conciliação**, mesmo que os dois créditos sejam individualmente comprovados.
5. **Tarifas/diferenças:** separar tarifa do recebimento, tarifa do repasse, bruto, líquido, valor enviado e valor creditado. Conferir semântica antes de calcular diferença, evitando descontar tarifa duas vezes. Devoluções/estornos parciais são eventos vinculados ao original, não apagamento do crédito.
6. **Tempo/status:** não presumir D+1; considerar dias posteriores, feriados/finais de semana, fuso e data de referência. Data sem hora continua sem hora. Pendente/agendado/processando/rejeitado/cancelado não é transferência realizada; `DONE` na origem não confirma crédito independente no destino.
7. **Banco final:** obter OFX oficial completo e detalhe do crédito com contraparte/E2E/documento quando o arquivo não trouxer. Hash preserva integridade do arquivo coletado, não autentica sozinho sua origem. Nome “Asaas/Matera/Fiserv” no histórico ou valor/data coincidentes só geram candidato, nunca certeza.
8. **Intercompany:** provar titularidade e autorização para transferência entre empresas; não inferir receita adicional nem misturar contas por pertencerem ao grupo. A 118508 não utiliza Mais e está fora desta investigação. Pendências e divergências devem aparecer explicitamente; fonte ausente não pode virar zero/sucesso.

## F. Um único piloto futuro recomendado

**Doze, empresa 74014; pagamentos de 14/10/2026 e observação financeira de 14/10/2026 a 16/10/2026.** Escolha pela declaração Mais já existente e caminho documental Asaas, não por transferência já comprovada. Nenhum repasse é presumido no intervalo. Se o ciclo real exceder 16/10, registrar a insuficiência e solicitar extensão, sem forçar D+1.

Antes de consulta/implementação, solicitar ao titular, por canal seguro: identidade CNPJ/conta Asaas e banco final, detalhe Mais de um PIX/E2E e venda correspondente, extrato financeiro Asaas com crédito, detalhe Pix/cobrança, eventual débito/tarifa e comprovante/composição de repasse, extrato oficial final e detalhe do crédito. Não solicitar segredos no relatório.

**Aceite:** evidência independente de cada etapa e vínculo verificável; se lote não revelar composição, confirmar apenas os movimentos demonstrados e manter alocação pendente. Rejeitado/estornado/fora do período e falta de extrato devem permanecer visíveis, sem sucesso parcial rotulado como cadeia completa.

**Menor implementação futura, não realizada:** com pacote oficial obtido, acesso definido e aprovação, adaptar modelos/proveniência e relatório no módulo existente, reutilizar leitor OFX e criar normalização/validação local das amostras, com testes de vínculos/ambiguidades/tarifas. Sem conector novo, importação ERP ou alteração do job nessa primeira entrega. Automatizar consulta GET apenas em etapa posterior autorizada, depois de provar a fonte.

## G. Perguntas externas — somente preparar, não enviar

| Destinatário | Dados/autorizações a solicitar |
|---|---|
| Mais Pagamentos | Mapa unidade/CNPJ → ID conta Mais → plataforma/custodiante/conta titular; diferença estabelecimento/parceiro e escopos; credencial própria de consulta, sem reutilizar a webPosto; detalhe transação/E2E; extrato consolidado do portal/layout; IDs de liquidação/repasse e composição de lotes; modalidade, frequência, calendário, taxas e acesso histórico |
| Asaas | Essa conta é direta, subconta ou BaaS gerida pela Mais/Quality? Quem pode exportar/consultar extrato/Pix/transferência? Há leitura restrita? Fornecer amostra oficial com `paymentId`/E2E, crédito, `transferId`/débito/tarifa e destino; confirmar exportações disponíveis e semântica de valor/líquido/efetivação |
| Matera | Qual unidade/produto usa Matera e quem mantém/custodia a conta (razão social/CNPJ/ISPB)? Conta de quem? Matera é tecnologia ou instituição responsável nessa operação? Canal oficial/portal/API/layout de extrato, Pix, saldo, repasses, tarifas, IDs, autenticação e permissões de estabelecimento/parceiro |
| Fiserv | Qual produto contratado por VIP/5555, instituição custodiante/PSP e titular/conta? Canal oficial de extrato/movimentos/repasses, destino, tarifas, IDs e datas; permissões e autenticação. Não responder apenas com documentação Hub Pix/SiTef/adquirência sem aplicabilidade comprovada |
| Quality/webPosto | Como a Mais integra vendas e baixas? Guarda E2E, conta, ID de repasse ou composição em algum recurso? Há sincronização de extrato externo? Demonstrar uma linha com origem, ID bancário, arquivo/hash e crédito; esclarecer CARTOES_REMESSA e antigas rotas PAGPIX. Qual contrato habilita API Mais? Não repetir login 401 sem instrução e autorização |
| Banco de destino | Confirmar banco/produto/titular/CNPJ/conta e período; obter OFX/extrato oficial completo e detalhe com contraparte, documento/E2E e data efetiva do crédito; explicar tarifas/estornos. API GET apenas se contratada/autorizada, sem consentimento ou segredo exposto |

**Encerramento:** hoje podemos comprovar contratos/código e evidências históricas limitadas de ERP/OFX, não dinheiro Mais chegando ao banco final. Asaas depende de acesso à conta específica; Matera/Fiserv de identificação e contrato; banco final de conta/titular e extrato oficial. Prioridade: pacote documental Doze/Asaas → banco final. **Parado no diagnóstico, aguardando aprovação específica.**
