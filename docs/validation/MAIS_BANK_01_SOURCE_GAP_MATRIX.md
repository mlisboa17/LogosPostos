# MAIS-BANK-01 — Matriz de fontes e lacunas

**Data:** 17/10/2026. **Resultado:** investigação local concluída; implementação e migração não iniciadas.

## 1. Escopo e critério de prova

**Correção de escopo — 17/10/2026, confirmação posterior do dono:** a Conveniência 24h (118508) **não utiliza Mais Pagamentos**. Escopo Mais: Doze (74014), VIP (11495, incluindo sua própria conveniência) e Casa Caiada (5555). A 118508 não é plataforma desconhecida/pendente e não deve ser associada a Asaas/Matera/Fiserv nesse contexto; permanece nos demais módulos aplicáveis, sem mudança operacional. Esta anotação atualiza o escopo sem reclassificar as evidências históricas. A associação operacional da Matera continua pendente de comprovação.

- Antigo: `C:\Users\mlisb\OneDrive\ProjetosAntigravy\LOGOS SPACE\Api_WebPosto\WebPosto_API`.
- Oficial: `C:\Projetos\LOGOS\LogosPostos`.
- Somente leitura dos projetos, com as duas entregas documentais autorizadas: este relatório e [STATUS.md](../../STATUS.md).
- Nenhuma chamada externa, execução de integração, import de módulos da aplicação, leitura de `.env`, alteração de configuração, teste com credenciais, migração, commit, push ou deploy.
- Dados pessoais, credenciais, números completos de contas e extratos brutos não foram copiados para a entrega.

**Conclusão de negócio:** não foi encontrada uma cadeia operacional comprovada que determine, para **cada** pagamento Mais, o crédito na conta recebedora e, havendo repasse, o crédito na conta bancária de destino.

Há código reaproveitável para classificação ERP, leitura de extratos e comparação bancária. Há também um contrato local da API Mais com consulta de transações e E2E. Isso **não equivale** a uma integração bancária funcionando.

Nesta investigação:

| Evidência | O que permite afirmar | O que não permite afirmar |
|---|---|---|
| Arquivo de código/contrato | Capacidade implementada ou interface documentada | Endpoint acessível, credencial válida ou execução real |
| Fixture/teste sintético | Regra exercitada com dados controlados | Pagamento, repasse ou crédito real |
| Relatório/snapshot histórico | Resultado registrado naquela ocasião, com suas limitações | Funcionamento atual, cobertura integral ou independência bancária |
| Transação concluída pelo provedor | Confirmação do pagamento segundo o provedor, quando houver resposta autêntica e semântica validada | Repasse posterior ou crédito no banco de destino |
| Crédito em extrato de procedência bancária validada | Movimento de crédito naquela conta/data/valor | Qual venda o originou, se faltar chave confiável de ligação |
| Duas entidades do mesmo ERP | Consistência e vínculo interno | Duas confirmações independentes do dinheiro |

O mapeamento **Doze = Posto Abreu e Lima/Asaas; Casa Caiada e VIP = Fiserv; PAGPIX desativada** vem da declaração de negócio registrada no [status vigente](../../STATUS.md), não de uma consulta bancária desta tarefa. IDs das contas Asaas/Fiserv e contas bancárias finais não foram comprovados.

## 2. Matriz de fontes, endpoints e força da evidência

URLs abaixo são referências estáticas extraídas do código/contrato local; **não foram acessadas**.

| ID / instituição | Fonte e endpoint | Antigo versus oficial | Comprova pagamento, repasse ou crédito? | Evidência de funcionamento real / lacuna |
|---|---|---|---|---|
| M1 — Mais, cliente legado | `https://api.maispagamentos.com.br/v1/transactions` e `/v1/settlements`; `X-Account-ID`/`X-Account-Key` | Só no antigo: cliente, router e serviço de conciliação; não presentes nesses caminhos no oficial | **Não confiável como prova real.** Em falha HTTP, exceção ou falta de configuração, retorna transações/liquidações fabricadas | Testes esperam NSUs `MAIS-*`, PIX de R$ 95,00 e divergência MDR simulada. O status oficial já registra rotas/cabeçalhos adivinhados e 401 histórico. Não portar |
| M2 — Mais, transações; Asaas/Fiserv como instituições possíveis | Base `https://api.maispagamentos.com.br`; `POST /usuarios/v1/login-integracao`; `GET /transacoes/v1/{conta}`; detalhes `GET /transacoes/v1/{conta}/{transacao}`, `GET /transacoes/v2/{conta}` por `txId`, `GET /transacoes/v2/{conta}/{transacao}` | Oficial contém OpenAPI local de 11/10; não foi encontrado adaptador operacional correspondente nos fontes examinados | Contrato permite consultar pagamento e E2E; **não prova saldo, repasse ou crédito bancário final** | Só contrato disponível e histórico de login 401 em 11/10. Nenhuma resposta autenticada de transação real localizada nas evidências examinadas |
| M3 — Mais, PIX de saída / possível transferência | `GET /contas/v1/{id}/pagamento-chave-pix?idTransacao=...` e `GET /contas/v1/{id}/pagamento-qr-code?idPagamento=...` | Documentados no OpenAPI oficial; os POSTs equivalentes executam pagamentos e estão fora do escopo | Consultam pagamento de saída conhecido. Podem apoiar evidência de envio; **não são listagem de repasses nem extrato da conta de destino** | Sem execução real comprovada. Não há vínculo implementado entre recebimentos, lote de repasse e crédito no destino |
| M4 — Mais, monitor de confirmação por instituição | `GET /transacoes/v1/ultima-confirmacao-pagamento?tipoInstituicao=...`; enum inclui `ASAAS` e `FISERV` | Contrato oficial, sem coletor encontrado | Retorna `ultimaConfirmacaoPagamento`; **não identifica um pagamento nem comprova crédito** | A presença das instituições no enum não comprova integração direta com contas Asaas/Fiserv |
| B1 — Asaas / Fiserv diretos; bancos via API | Não encontrado cliente direto de movimentação, saldo, extrato ou repasse dessas contas nos fontes examinados | Ausência identificada tanto no antigo quanto no oficial; há referências no contrato Mais, não implementação bancária direta | **Não comprovado** | Não foi localizado endpoint bancário implementado nem evidência de consulta real dessas contas. Não inventar URLs ou presumir cobertura por APIs públicas conhecidas |
| W1 — webPosto, movimentos de conta | Legado `GET /INTEGRACAO/MOVIMENTO_CONTA`; contrato oficial `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA` | Antigo tem gateway, collector e centro financeiro; oficial mantém wrapper legado e usa V1 em despesas sem lançamento | Comprova registro ERP. **Não comprova que seja linha importada do banco ou independente da venda/transferência ERP** | Artefato antigo registra HTTP 200, 400 linhas coletadas em 01–07/06/2026. Uma amostra liga diretamente movimento a transferência interna. Nenhuma consulta nova |
| W2 — webPosto, transferências e cadastro de contas | Legado `GET /INTEGRACAO/TRANSFERENCIA_BANCARIA`, `/INTEGRACAO/CONTA`; contrato oficial `GET /INTEGRACAO/V2/TRANSFERENCIAS_BANCARIAS`, `GET /INTEGRACAO/V1/CONTAS` | Antigo tem classificação Mais e collector; oficial mantém wrappers/cadastro de contas usado pelo módulo de caixa | Confirma classificação/vínculo operacional no ERP. **Não confirma repasse bancário executado** | Artefato antigo registra 400 transferências e 17 contas em consultas distintas. São quantidades coletadas, não prova de completude |
| W3 — webPosto, importação de extrato | Antigo `POST /INTEGRACAO/INCLUIR_OFX`; oficial `POST /INTEGRACAO/V1/OFXS` | Ambos têm envio; oficial tem barreiras, prévia e histórico local | Importa dados fornecidos pelo usuário/LOGOS; **não consulta o banco nem cria prova independente** | Histórico local oficial registra 507 lançamentos de 10/10 enviados em 11/10, conta ERP 86188, com status de débitos errados. Envio aceito não certifica sinal nem crédito |
| F1 — OFX antigo, PagBank/Itaú e adquirentes | Arquivo local, sem endpoint bancário; parser `domain/reconciliation/ofx_parser.py` e motor `card_bank_matching_service.py` | Não encontrados nos mesmos caminhos no oficial; há parsers novos no módulo de caixa | Extrato de origem bancária validada evidencia crédito/débito. Casamento com venda é **heurístico**, não vínculo E2E | Existem arquivos OFX locais e script de validação real; testes do motor são sintéticos. Não foi localizado resultado persistido que comprove cadeia Mais → repasse → destino |
| F2 — OFX/XLSX antigo, BB/Santander | `BankStatementReader`; entrada local `POST /api/reconcile/bank-statement` | Presente no antigo, não encontrado no mesmo caminho no oficial | Leitura de arquivo, depósitos e alocação; **não coleta extrato via API** | Código e rota de upload existem; não comprovam integração remota nem recebimento Mais. A identidade da conta é também fornecida pelo chamador |
| F3 — OFX oficial, PagBank/BB/Bradesco/Itaú e outros | `extrato_reader.py`, `ofx_reader.py`; `pix_cnpj.py` lê OFX PagBank local | Oficial já possui leitura, hash, cobertura, sinal e comparação ERP | Pode evidenciar movimento na conta do arquivo; **não comprova repasse Mais sem identificação e ligação das duas pontas** | ADR-002 registra extratos reais de set/2026 e viabilidade sangria × depósito. Auditoria de capacidade registra PIX cliente positivo ainda sintético; isso não valida Mais/Asaas/Fiserv |
| P1 — PagBank EDI | `GET https://edi.api.pagbank.com.br/movement/v3.00/transactional/{dia}` | Antigo tem cliente; oficial já o adaptou com hora e paginação corrigidas | Confirma evento transacional da adquirente; **não substitui extrato de crédito da conta ou repasse posterior** | Código oficial documenta resposta real Doze 05/10 e validações anteriores. Não é integração Mais/Asaas/Fiserv |
| D1 — Mais declarado pelo diretor | JSON local por unidade/dia; CLI e entrada Telegram; comparação com `transfBanc` | Implementação oficial da Sprint 19 | **Declaração humana**, não coleta de pagamento, repasse ou crédito | Registro local observado: Doze, 14/10, R$ 10.741,86, informado em 16/10, zero detalhes PIX. Não contém prova bancária |

## 3. Matriz dos campos financeiros disponíveis

“Ausente” significa não exposto pelo modelo/contrato examinado ou não comprovado no artefato local; não é valor zero.

| Fonte | Conta de origem e destino | Data / valor do pagamento | Data / valor do crédito | PIX/E2E ou referência de repasse | Taxas / diferenças | Saldo / movimentação |
|---|---|---|---|---|---|---|
| M1 cliente legado | `empresa_codigo`, não conta financeira; nenhuma conta origem/destino | `data_hora`, `valor_bruto`, `nsu`, `autorizacao` | Settlement tem `data_venda`, `data_pagamento`, `valor_liquido`; descrição mistura data prevista/efetiva. Não há crédito bancário independente | NSU; sem E2E, ID de repasse ou conta destino | `desconto_taxa_mdr`, `taxa_efetiva_pct`; serviço calcula divergências | Sem saldo ou extrato bancário |
| M2 lista Mais | `{conta}` é identificador lógico a obter; não mapeado a conta bancária | `dataHoraCriacao`, `dataHoraModificacao`, `valor`, situação/tipo; PDV, turno e funcionário opcionais | Sem campo separado de data/valor do crédito | `id`, `transacaoId`; lista não expõe E2E | Lista não expõe líquido/taxa | Sem saldo/movimentação bancária |
| M2 detalhe Mais V1/V2 | Recebedor tem razão social/fantasia/CNPJ; `instituicao` é descrita como banco que realizou o pagamento; há `agencia` e `conta` sem papel suficientemente explicado. Não assumir que sejam a conta recebedora | `dataHora`, `valorBruto`, `valorPago`, `status` (0 aberta, 1 concluída, 2 devolvida no contrato V2) | `valorLiquido` disponível, mas **sem data autônoma de crédito**; `dataHora` é momento da transação | `endToEndId`, `id`, `transacaoId`, `cnpjInstituicaoIntermediadora`; `informacoesGerador` é conteúdo livre, não vínculo garantido | `taxa`, bruto/pago/líquido; diferenças calculáveis somente após validar semântica e resposta real | Sem saldo ou histórico de lançamentos da conta |
| M3 saída Mais | `{id}` identifica conta lógica; recebedor chave PIX inclui instituição, agência, conta e chave; retorno QR tem identificação mais limitada. Pagador tem nome/documento, não necessariamente conta bancária completa | `dataPagamento`, `valor`, `status`, `statusExterno` | Nenhum lançamento/data de crédito do banco destino | `idPagamento`, `e2eId`; consulta por ID conhecido | Sem taxa de repasse documentada nesses retornos | Sem saldo ou extrato |
| M4 confirmação / B1 direto | Nenhuma conta consultada comprovada | Apenas timestamp de última confirmação em M4; demais ausentes | Ausente | Sem ID de pagamento individual em M4 | Ausente | Ausente |
| W1 movimentos webPosto | `empresaCodigo`, `contaCodigo`; conta é cadastro ERP, não identificação bancária suficiente | `dataMovimento`, `valor`, `tipo`, documento de origem; não separa data do pagamento | Sem data de crédito independente no retorno `MovimentoConta`; `evento`/conciliação não são timestamp bancário | `movimentoContaCodigo`, `documentoOrigemCodigo`, `documento`, `lote`; sem E2E/FITID dedicado no retorno | Origens como `TAXA_TRANSFERENCIA`, `ACRESCIMO_TRANSFERENCIA_BANCARIA`, `DESCONTO_TRANSFERENCIA_BANCARIA`; valores ERP | `saldo` opcional; V1 aceita `mostraSaldo`. Saldo ERP, não certificado bancário |
| W2 transferências / contas webPosto | `contaCodigo`; V2 acrescenta `contaOrigem` textual; cadastro tem descrição, `usaOfx`, `saldoAtual`. Não presume par bancário origem/destino | `dataMovimento`, `valor`, `vendaCodigo`, `caixaCodigo`, `tipoInclusao` | Ausente como crédito bancário independente | `transferenciaBancariaCodigo`; V2 `documentoReferencia`. Legado tem `documento` | Plano/centro de custo, não extrato de taxas reais | Cadastro pode ter `saldoAtual`; `usaOfx` só informa uso de OFX |
| W3 envio OFX ao ERP | `cdConta`, `cdFilial`; oficial resolve banco/sufixo contra cadastro | Derivado do arquivo, não consulta do pagamento | Payload tem `dataCredito`, mas o adaptador oficial **a preenche com a mesma data do lançamento**, sem confirmação separada do banco | `extratoExterno` recebe FITID truncado a 30 caracteres; `numeroDocumento` também é limitado | Tipos/sinais derivados do arquivo; incidente de débito impede confiar só no aceite HTTP | Movimentos enviados; nenhum saldo bancário consultado |
| F1 OFX antigo | `bankId`, `acctId`; `counterparty` extraída do histórico, geralmente sem conta completa da contraparte | Data da venda vem do ERP; pagamento não identificado automaticamente em cada linha OFX | `postedAt`, `amount`, `trnType`, `memo` do banco; crédito só na conta do arquivo | `fitId`; `settlementCode` guarda AT/DB/CD, **não ID único de lote**; sem E2E estruturado | Delta crédito − venda; classificação de tarifas e rendimentos. Delta não é automaticamente MDR | `transactions`; modelo não preserva `LEDGERBAL`/`AVAILBAL` |
| F2 leitor antigo BB/Santander | `conta_bancaria_id`, empresa/filial fornecidos; contraparte sem contrato completo | Ausente como evento de pagamento | `data_lancamento`, `data_compensacao`, `valor`, natureza; no caminho OFX a compensação é copiada da data de lançamento, não prova separada | `documento`, `identificador_bancario`, hash do arquivo, fingerprint/ocorrência | Classificação de tarifa/estorno; sem ligação automática a MDR Mais | Lista de transações; não consulta saldo bancário |
| F3 OFX oficial | Banco, agência, sufixo de conta; configuração por unidade. Não há conta destino estruturada para toda transferência | Venda/hora vêm do ERP quando houver candidato único | `data`, `momento`, `valor`, tipo original/normalizado do lançamento; sem data de compensação separada | FITID, documento, hash SHA-256; E2E não é extraído em campo próprio | Categorias tarifa/PIX/cartão; totais de crédito/débito | `saldo_liquido` = créditos − débitos do arquivo; **não saldo disponível/contábil da conta** |
| P1 EDI PagBank | Credencial por unidade; modelo transacional não preserva conta destino | Momento, valor bruto, NSU, autorização, identificador, evento/status | Não preserva crédito bancário no modelo oficial | NSU/autorização/TID ou identificador; sem cadeia de repasse bancário | Cliente antigo calcula agregado MDR/líquido; isso não vira crédito comprovado | Sem saldo/extrato bancário no adaptador transacional |
| D1 total Mais local | Unidade; nenhuma conta financeira comprovada | Dia e total; detalhes opcionais só momento/valor | Ausente | Sem E2E, NSU ou referência de repasse | Diferença total declarado − `transfBanc` ERP | Ausente |

## 4. Achados determinantes

### 4.1 Cliente Mais antigo: aparência de integração não é funcionamento real

No [cliente antigo](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/gateway/mais_pagamentos_client.py>):

- `fetch_transactions` e `fetch_settlements` terminam em geradores sandbox quando não conseguem consultar a fonte.
- Modelos predefinem `APROVADA` e `LIQUIDADO`; não carregam proveniência que distinga resposta remota de fabricação.
- Os caminhos `/v1/transactions` e `/v1/settlements` **não constam** da cópia OpenAPI Mais examinada.
- O [serviço de conciliação](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/services/bank_reconciliation/mais_pagamentos_reconciliation_service.py>) ainda substitui totais ERP ausentes/zerados pelos da adquirente como “baseline”. Soma settlements sem exigir status efetivo de liquidação. Pode produzir igualdade sem fonte ERP.
- O [router](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/interfaces/http/routes/mais_pagamentos.py>) está montado no app antigo; expor endpoint local não elimina esses problemas.
- A [esteira de quatro vias](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/services/finance/cashier_multiway_reconciler_service.py>) procura `consultar_extrato_pix`, método que esse cliente não implementa, e sinaliza integração não habilitada.

Os [testes antigos](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/tests/unit/test_mais_pagamentos_integration.py>) esperam dados sandbox e poderiam acionar rede/configuração se executados. Foram apenas lidos.

### 4.2 Contrato Mais oficial: caminho útil, mas ainda não prova bancária

Fonte: [OpenAPI local Mais de 11/10](../external/maispagamentos/openapi_integracao_2026-10-11.json).

- Lista de transações aceita filtros de período de transação/criação/modificação, tipo e situação.
- Para E2E, bruto/pago/líquido/taxa e identificação do recebedor, é necessário o detalhe V1/V2; a lista sozinha não basta.
- Há status de devolução; uma conciliação futura deve preservá-lo, não tratar todo registro como aprovado.
- `instituicao`, agência e conta não devem ser promovidas a conta recebedora sem confirmação de semântica. O banco pagador e o intermediador são papéis diferentes.
- Não foram encontrados no contrato endpoints dedicados de saldo, extrato completo de conta, lotes de liquidação ou listagem de repasses.
- Consultas PIX de saída são distintas de recebimentos. Para usá-las como repasse, será preciso obter o ID de saída e provar sua associação aos pagamentos/lote e ao crédito no banco final.
- `ultima-confirmacao-pagamento` permite `ASAAS`/`FISERV`, mas retorna somente uma última confirmação, não movimentos dessas contas.
- O [status anterior](../../STATUS.md) registra autenticação tentada em 11/10, todas 401, e orientação de **não repetir sem credencial nova**. É evidência histórica documental, não teste refeito aqui.
- O contrato declara `Authorization` no login e Bearer nas consultas; o procedimento Basic/client credentials/scope `events` é descrito no status histórico. Sua validade operacional continua pendente com a Quality/Mais.

### 4.3 webPosto: movimento disponível, independência bancária não demonstrada

O [contrato local webPosto](../external/webposto/openapi_integracao_2026-10-06.json) documenta:

- `GET /INTEGRACAO/V1/MOVIMENTOS_CONTA`: empresa, período, cursor, limite, `contaCodigo`, `mostraSaldo`, documento/tipo de origem e atualização.
- Retorno com `tipoDocumentoOrigem`, `documentoOrigemCodigo`, `conciliado`, `saldo`, `documento`, `lote`, usuário e horário de conciliação (o nome no contrato é `daraHoraConciliacao`).
- Origens incluem `MANUAL`, `CAIXA`, `CARTAO`, `TRANSFERENCIA_BANCARIA`, taxas e outras entidades internas. Não é um conjunto exclusivamente originado no banco.
- O mesmo recurso permite POST de movimento e PATCH de `conciliado`; logo, **`conciliado=true` não constitui certificação externa**.
- `GET /INTEGRACAO/V1/CONTAS` devolve `usaOfx` e `saldoAtual`: são atributos do cadastro/ERP, não prova de consulta ao banco.
- Existe `POST /INTEGRACAO/V1/OFXS`, mas não foi encontrado GET de extratos OFX/importados segregados nessa especificação. Os GETs com “EXTRATO” encontrados são de **estoque de produtos**, não bancários.
- `TransacaoBancaria`, modelo de **entrada** de OFX, tem `dataCredito`, `extratoExterno` e campos de contraparte. O retorno `MovimentoConta` não expõe esses campos como tais. Não se pode presumir sua recuperação íntegra pela consulta de movimentos.

**Vínculo interno concretamente observado:** o [artefato antigo de origem financeira](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/financial_origin_matrix.json>) registra, em 01/06/2026, unidade 11495, conta ERP 60536:

- Movimento 63005844, crédito R$ 50,00, origem `TRANSFERENCIA_BANCARIA`, `documentoOrigemCodigo=26245718`, `conciliado=false`, saldo nulo.
- Transferência 26245718, mesma conta, dia e valor.

Isso prova ligação **transferência ERP → movimento ERP**, não uma segunda evidência bancária. Datas e valores coincidentes não resolvem a lacuna.

O [BANKING_MODEL antigo](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/BANKING_MODEL.md>) registra 200 movimentos/200 transferências; a matriz de origem registra 400/400. São artefatos/coletas diferentes e não foram somados nem tratados como cobertura total. Descrições históricas de “banco”/“extrato” não certificam a procedência.

**Importação real registrada, mas problemática:** o histórico local oficial de importação, também descrito no [status](../../STATUS.md), contém unidade 74014, conta ERP 86188, dia 10/10/2026, envio em 11/10, 507 lançamentos, créditos R$ 67.956,78 e débitos R$ 64.847,35. Estado: **“importado com débitos errados — aguardando correção”**. O status relata exclusão posterior pelo diretor; o histórico não prova presença atual dessas linhas no ERP.

**Resposta à pergunta específica:** há suporte para importar OFX e consultar movimentos de conta do ERP. **Não foi comprovado que as consultas devolvam movimentos efetivamente importados do banco de forma segregada, rastreável e independente dos lançamentos internos.** Para admitir essa fonte como prova bancária, faltam um caso positivo pós-importação, o identificador da linha bancária, vínculo ao arquivo original e semântica confirmada pela Quality. Reimportar o próprio OFX e depois lê-lo no ERP também não cria uma segunda fonte independente.

### 4.4 OFX e comparação bancária: peças úteis, não cadeia Mais pronta

- No antigo, [modelos de extrato](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/domain/reconciliation/bank_statement.py>) e [parser](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/domain/reconciliation/ofx_parser.py>) reconhecem PagBank, PIX, tarifas, rendimentos, Itaú/Rede/Cielo e transferências automáticas.
- O [motor cartão × banco](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/services/bank_reconciliation/card_bank_matching_service.py>) declara explicitamente falta de NSU/FITID comum. Faz aproximação por bandeira/modalidade/data/valor ou agregação diária com defasagem. Não inclui conta/tenant na chave de comparação; exige segregação anterior pelo chamador. Não fornece certeza individual para repasses agregados.
- `settlementCode` preserva códigos de modalidade AT/DB/CD; significado de AT ainda não confirmado no próprio código. Não é identificador de repasse.
- O [script de validação](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/scripts/validate_card_bank_reconciliation.py>) prevê OFXs reais de três unidades e API ERP, mas sua existência não prova resultado. Não foi executado nem foram abertos os arquivos externos em Downloads.
- Na pasta antiga de extratos prontos existem três OFXs. Uma inspeção textual local encontrou BANKID 290, período 01–16/05/2026, 2.155 blocos de transação e `LEDGERBAL`. Isso comprova disponibilidade de arquivo, não autenticidade certificada, execução do parser nem vínculo Mais. O modelo antigo não preserva esse saldo.
- O [leitor antigo BB/Santander](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/services/finance/bank_statement_reader.py>) tem hashes/fingerprints e upload local via [router PWA](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/web/pwa/routers/reconcile.py>). Porém tem defaults de banco/data e tratamento monetário permissivo; não adotar integralmente como fonte financeira sem revisão.
- No oficial, [extrato_reader.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py) e [ofx_reader.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/ofx_reader.py) já atendem leitura local. [pix_cnpj.py](../../WebPosto_API/src/modules/cash_reconciliation/application/pix_cnpj.py) exige conta configurada, cobertura e FITID sem conflito, mas usa candidatos por valor/hora e restringe leitura a PagBank.
- [ADR-002](../architecture/adr/ADR-002-cash-arch-01-antes-do-arch-02.md) registra viabilidade real em espécie, não PIX Mais. Também refuta usar conta ERP “CAIXA(POSTO)” como saldo de cofre.
- A [auditoria de capacidade](LOGOS_CURRENT_CAPABILITY_AUDIT.md) distingue validação real de OFX/casos de caixa de casamento positivo PIX ainda sintético. O [relatório D02 antigo](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/docs/d02/D02_REAL_PARITY_RUNTIME_REPORT.md>) também avisa que paridade interna não comprova banco/adquirente.

## 5. Componentes reutilizáveis e restrições

| Componente | Recomendação para uma etapa futura aprovada | Condições / o que não reutilizar |
|---|---|---|
| [MaisPagamentoMappingResolver antigo](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/services/financial/mais_pagamento_mapping.py>) | Reaproveitar regras de classificação por conta/plano/origem e separação captura × liquidação | `bankSettlementStatus` permanece `PENDENTE_FONTE_EXTERNA`, mesmo com `ofx_available=True`; flag não valida linha bancária. “Confirmado tecnicamente” é classificação ERP, não dinheiro creditado. Rever isolamento por tenant e uso de float antes de adaptar |
| [CashReceiptLiveCollector antigo](<C:/Users/mlisb/OneDrive/ProjetosAntigravy/LOGOS SPACE/Api_WebPosto/WebPosto_API/src/services/financial/cash_receipt_live_collector.py>) | Referência para cursor, checkpoints e completude das consultas | Adaptar ao contrato V1/V2 atual e ao escopo explícito. Não portar permissividade com linhas sem empresa nem falhas como vazio válido |
| Parser/modelos OFX e motor cartão × banco antigos | Reaproveitar padrões de histórico, classificação de transferências/rendimentos e comparação de lotes como **candidatos** | Não migrar um segundo parser inteiro por padrão; preferir estender o oficial após aprovação. Rever float, identidade da conta, calendário, colisões, agrupamento e ausência de identificador comum |
| Leitor antigo BB/Santander | Referência para fingerprint com índice de ocorrência e suporte de arquivo XLSX | Não portar defaults silenciosos de banco/data, identidade de conta fornecida sem validação ou normalização monetária permissiva |
| [OpenAPI Mais local](../external/maispagamentos/openapi_integracao_2026-10-11.json) | Base para um adaptador transacional read-only novo, não para consertar rotas adivinhadas | Obter credencial e ID de conta corretos; definir semântica dos campos e política sem sandbox/fallback financeiro |
| [Leitor oficial OFX](../../WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py) e [PIX CNPJ](../../WebPosto_API/src/modules/cash_reconciliation/application/pix_cnpj.py) | Priorizar como base já existente para proveniência/hash/cobertura/conta e ambiguidade | Adicionar Asaas/Fiserv somente com formatos e exemplos autorizados. FITID não é E2E; delta de arquivo não é saldo bancário |
| [Mais declarado oficial](../../WebPosto_API/src/modules/cash_reconciliation/application/mais_pagamentos.py) | Preservar como declaração humana separada durante transição | Não transformar total declarado em resposta da API ou crédito bancário |
| [PagBank EDI oficial](../../WebPosto_API/src/modules/cash_reconciliation/adapters/pagbank_edi.py) | Manter caminho existente; referência de paginação e erros explícitos | Já portado/corrigido; não substituir pelo cliente antigo. Não usar autorização como crédito |
| Cliente Mais sandbox, baseline ERP e [envio OFX oficial](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py) | **Não reutilizar como comprovação bancária nem executar nesta investigação** | Sandbox não pode virar fonte real. Importação é escrita congelada e tem incidente; nenhum piloto ou correção autorizados aqui |

## 6. Lacunas para cumprir o objetivo de negócio

| Prioridade | Lacuna | Evidência necessária antes de concluir “dinheiro entrou” |
|---|---|---|
| 1 | Conta Mais/Asaas/Fiserv não vinculada tecnicamente ao titular/unidade e à conta de destino | Mapa autorizado unidade/CNPJ → instituição → ID de conta lógica → conta recebedora → conta final, com origem e validade do mapeamento |
| 1 | Autenticação Mais indisponível no histórico | Credencial nova de integração e confirmação do protocolo/scope/conta pela Quality/Mais; **não repetir testes antigos** |
| 1 | Transação consultada não é extrato da conta recebedora | Resposta real sanitizada com E2E/status e significado de bruto/pago/líquido/taxa; linha de crédito na conta recebedora ou evidência de ledger cuja semântica seja formalmente validada |
| 1 | Ausência de fonte de repasses/listagem de liquidações Asaas/Fiserv | Referência de repasse/lote, data efetiva, valor bruto, taxas, líquido, conta debitada e destinatário; incluir reversões/devoluções |
| 1 | Ausência de prova no banco final | Linha de crédito da conta destino com conta/data/valor e referência/E2E que permita associar ao repasse. Débito na origem não basta |
| 2 | Movimentos webPosto sem proveniência bancária segregada | Quality indicar se há recurso/campos que retornem OFX importado ou Open Finance, preservando ID original, arquivo/lote, data de crédito e contraparte, separado dos lançamentos internos; confirmar em amostra posteriormente autorizada |
| 2 | Repasse pode agregar vários pagamentos e descontar taxas | Relação N pagamentos → lote → N créditos/débitos, sem dupla contagem; diferenças justificadas individualmente e resíduos explícitos |
| 2 | Cobertura, saldo e frescor não demonstrados para essas contas | Período completo, paginação, timezone, saldo inicial/final quando existente, instante de coleta e documento/hash. Não confundir ausência de fonte com zero |
| 2 | Casamentos heurísticos não individualizam pagamentos repetidos | Chave externa forte; se faltar, marcar candidato/ambíguo, sem promover aproximação por valor/data a confirmação |

### Perguntas concretas à Quality/Mais, sem contato nesta tarefa

1. Qual usuário de integração, scope e código de conta correspondem a Doze/Asaas e Casa Caiada/VIP/Fiserv?
2. `dataHora` no detalhe é criação, pagamento ou confirmação? De quem são `agencia`/`conta`? Qual unidade monetária e semântica de `taxa`?
3. Onde consultar ledger/saldo da conta recebedora, data efetiva de crédito e devoluções?
4. Existe API/exportação de repasses com ID de lote, taxas, conta destinatária e E2E/ID de saída? As consultas de saída cobrem repasses automáticos?
5. No webPosto, quais movimentos vêm do banco e quais do ERP? É possível recuperar `extratoExterno`/FITID e `dataCredito` enviados em OFX? Há fonte importada segregada e imutável?
6. Qual retorno comprova sinal/tipo correto de débito e conciliação com o OFX original, considerando o incidente da conta 86188?

## 7. Próxima etapa proposta — depende de aprovação

Não implementar ou migrar agora. Após aprovação específica, propor um slice read-only que:

1. Defina os contratos de **pagamento confirmado pelo provedor**, **crédito na conta recebedora**, **repasse identificado** e **crédito na conta final** como fatos distintos.
2. Use fixtures sanitizadas e casos reais autorizados, preservando IDs, contas, datas, bruto/taxa/líquido e proveniência.
3. Priorize contrato Mais oficial e leitor OFX já existente; aproveite regras antigas somente onde acrescentem capacidade real.
4. Deixe pagamentos sem extrato/repasse correspondente como **não comprovados**, não como perda nem como recebidos.
5. Só execute consultas externas com autorização adicional explícita e credenciais novas adequadas. Aprovar desenvolvimento não libera escrita ERP, leitura de `.env` ou chamadas externas.

Critério de aceite futuro: um caso com recebimento direto e outro com repasse devem mostrar as duas pontas necessárias; incluir pagamento aprovado sem crédito, devolução, taxa, atraso e ambiguidade. Não basta total igual no ERP.

## 8. Verificação desta entrega

- Inspeção estática de código, testes como texto, contratos OpenAPI e evidências locais; aplicações e scripts não executados.
- Comparação dos componentes antigos com os caminhos correspondentes no oficial e com o módulo atual de caixa.
- Investigação concentrada em fontes de integração/serviços/rotas/scripts, contratos e relatórios relevantes; caches de ferramentas, dependências e diretório de testes temporários com acesso negado não foram usados como evidência. “Não encontrado” não pretende certificar sistemas externos ou artefatos fora do escopo.
- Testes de aplicação e linters de código não executados: alteração exclusivamente documental e execução poderia ler configuração/rede/estado. Validação documental por diff e links locais.
- Única alteração preexistente observada no worktree: probe Premmia não rastreado, preservado sem leitura/execução/alteração.
- **Parada antes da implementação. Aprovação humana pendente.**
