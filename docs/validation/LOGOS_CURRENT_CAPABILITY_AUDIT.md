# LOGOS — auditoria de capacidades atuais (somente leitura)

## 1. Resumo executivo

**Data:** 16/10/2026, America/Recife. **Base:** `feature/cash-audit-fechamento`,
commit `76cd8e2a9774d1a8d718b83c89de945bcdd1a616`.
Fonte de verdade: `C:\Projetos\LOGOS\LogosPostos`; código principal em
[WebPosto_API](../../WebPosto_API). Não houve importação da aplicação, execução de
jobs, chamadas HTTP externas, leitura do `.env`, alterações funcionais, commit ou
push nesta auditoria. Apenas este relatório e [STATUS.md](../../STATUS.md) foram
alterados. Arquivo experimental preexistente não versionado foi preservado.

### Método e limites

- Inventário estático AST dos Python versionados: **685 arquivos rastreados**,
  incluindo testes; **200 declarações de rota em 30 arquivos** fora dos testes.
  Não são 200 endpoints simultaneamente publicados: há aplicações alternativas,
  aliases, exemplos e routers não montados. A aplicação `src.main` monta
  **101 declarações** identificadas; seu Swagger automático não integra essa conta.
- Comparação com **156 paths** na
  [OpenAPI oficial](../external/webposto/openapi_integracao_2026-10-06.json).
  SHA-256: `8bdbe8ed58a46e8e9eed26ff8045476b8defd436877d9ac4a27e6279ef675583`.
  Path no contrato não prova permissão da credencial nem funcionamento operacional.
- **23 registros** do registry antigo analisados por AST, sem importá-lo. Não
  se copiou código nem se adotaram suas regras de unidades/maturidade.
- Leitura direcionada dos adapters, serviços, testes, ADRs, scripts de execução,
  metadados de persistência e tarefa Windows. Logs inspecionados por contagem de
  marcadores; payloads, documentos, credenciais e dados pessoais não reproduzidos.
- Testes **localizados, não reexecutados**: esta é uma alteração documental.
  Última evidência registrada da Sprint 19: **824 backend e 72 frontend aprovados**,
  em [STATUS.md](../../STATUS.md); não se apresenta esse histórico como execução
  nova. Referência textual de teste/UI no inventário significa ligação estática,
  não cobertura integral, aprovação nem uso por usuário real.
- Sem consultar APIs reais não é possível confirmar disponibilidade atual de
  todas as rotas, credenciais, valores financeiros ou processo HTTP em execução.
  A tarefa Windows e seus metadados, ao contrário, foram consultados diretamente.

### Classificação única por capacidade

| Sigla | Categoria exata | Interpretação aplicada |
|---|---|---|
| V | VALIDADA EM OPERAÇÃO | Evidência real anterior + conferência registrada + testes; restrita ao caso/fluxo indicado |
| I | IMPLEMENTADA, NÃO VALIDADA | Código e integração identificados, sem prova operacional suficiente |
| P | PARCIAL | Existe parte da cadeia, mas faltam integração, campos, prova ou uso |
| L | LEGADO / EXPERIMENTAL | Superfície antiga/alternativa, incompleta ou sem vínculo ao entrypoint principal |
| A | AUSENTE | Não encontrada implementação atual para a capacidade específica |

As marcações de cobertura exigidas correspondem a: V = IMPLEMENTADA E VALIDADA;
I = JÁ IMPLEMENTADA; P = PARCIAL; A = NÃO ENCONTRADA. A anotação adicional
“implementada mas não usada pelo Logos” identifica alcance, não cria uma sexta
categoria. Maturidades do catálogo antigo nunca promovem uma capacidade atual a V.

### Conclusões principais

1. O projeto não está vazio para uma auditoria de conveniência: há vendas por item,
   custo/desconto/cancelamento no contrato V1, catálogo, estoques legados e
   serviços financeiros. Falta fechar e validar a cadeia, não criar outro cliente.
2. O módulo vertical de caixa é a base mais comprovada: unidade explícita,
   proveniência, valores Decimal, relatório, fila e testes. A camada analítica
   paralela usa endpoints e normalizações diferentes.
3. O registry antigo conhece principalmente rotas legadas; o projeto atual já usa
   várias V1 que ele classifica apenas como descobertas. Não portar seu bloqueio
   de unidades: ele inclui como proibida uma unidade configurada no Logos atual.
4. **Não há congelamento universal de escrita no código inteiro.** As travas de
   cartão/OFX não protegem todos os wrappers e proxies alternativos. Nada foi
   executado nem habilitado; inventário não é autorização.
5. Produção ainda roda do workspace. A tarefa das 03:00 falhou em 16/10/2026;
   logs indicam bloqueio por exigência de `WEBPOSTO_WRITES=0`, mas há marcador de
   envio Telegram no mesmo dia. Não se leu a configuração nem se alterou seu valor.
6. Próxima implementação recomendada: **release operacional isolada + evidência
   de execução/frescor**, reutilizando os componentes existentes, antes de ampliar
   auditoria física de combustível ou habilitar qualquer nova escrita.

## 2. Mapa atual do sistema

### Composição e aplicações

| Superfície | Arquivo | Montagem observada | Situação |
|---|---|---|---|
| Aplicação modular principal | [src/main.py](../../WebPosto_API/src/main.py), [interfaces/http/app.py](../../WebPosto_API/src/interfaces/http/app.py) | Auth, clientes, sync, enterprise, analytics, finance, caixa, comercial, frontend | I; inicializa bancos no startup; não iniciada nesta auditoria |
| Gateway unificado alternativo | [presentation/app.py](../../WebPosto_API/src/presentation/app.py) | UI/proxy/produtos, CRUD, auditoria antiga, caixa e comercial; imports opcionais | L; montagem não equivale à principal |
| Minimal | [main_minimal.py](../../WebPosto_API/src/main_minimal.py) | CRUD + enterprise, health/sync | L; scripts RUN_API_WINDOWS ainda apontam para ele, com reload |
| Gateway aninhado | [logos-webposto-gateway](../../WebPosto_API/logos-webposto-gateway) | Outro src.main, CRUD SQLModel, despesas/produtos | L; pacote independente, não confundir imports `src` |
| Explorador | [explorador_standalone.py](../../WebPosto_API/explorador_standalone.py) | Catálogo/proxy/UI | L; não usar para executar auditoria |
| Árvores da raiz | [src](../../src), [servicos_auditoria.py](../../servicos_auditoria.py), [PASSO_4_EXEMPLO_ROUTES.py](../../PASSO_4_EXEMPLO_ROUTES.py) | APIs antigas, SSE, métricas, impostos, exemplos Mongo | L; não montadas por WebPosto_API/src.main |

### Capacidades por domínio

| Domínio | Capacidade | Arquivo | Status | Leitura/Escrita | Testes | Evidência |
|---|---|---|---|---|---|---|
| Caixa | Auditoria por modalidade, desconto, fechamento, consolidação | [auditar_fechamento.py](../../WebPosto_API/src/modules/cash_reconciliation/application/auditar_fechamento.py) | V | GET ERP | test_fechamento, test_webposto_detalhes | Snapshots locais + validações registradas; não prova execução saudável hoje |
| Caixa | Explicação da falta e residual por caixa | [explicar_falta.py](../../WebPosto_API/src/modules/cash_reconciliation/application/explicar_falta.py) | V | Cálculo puro | test_explicar_falta | Caso 19 validado por GET anteriormente; snapshot antigo não reproduz sozinho |
| Venda / item / forma | Contexto V1 para pagamentos | [webposto_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py) | V | GET | test_cartoes, test_piloto_cartao | Usado no caso de caixa da Sprint 19; não valida todos os produtos/setores |
| Funcionário / PDV | Nomes, operador e rótulo de caixa | [funcionarios.py](../../WebPosto_API/src/modules/webposto_integration/funcionarios.py), [resumo_diario.py](../../WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py) | V | GET/cálculo | test_identificacao_caixa, test_resumo_diario | Nome+código nas ocorrências; operador do caixa não é automaticamente frentista da venda |
| Cartão / adquirente | PagBank EDI x ERP, NSU/autorização, candidatos | [conciliar_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/application/conciliar_cartoes.py) | V | GET | test_cartoes, test_recebimentos | Conferências anteriores e caso 19 |
| Cartão | Inclusão, conferência e compensação do piloto | [piloto_cartao.py](../../WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py) | P | POST/DELETE ERP | test_piloto_cartao, test_ajustes_19d | Auditoria real local termina em nao_entrou; não há sucesso real comprovado |
| PIX | CNPJ direto na conta, filtro grupo/fornecedor | [pix_cnpj.py](../../WebPosto_API/src/modules/cash_reconciliation/application/pix_cnpj.py) | V | OFX local + GET | test_pix_cnpj | Dia real coberto com zero PIX cliente; casamento positivo só sintético |
| PIX | Casamento positivo com venda/transferência | [pix_cnpj.py](../../WebPosto_API/src/modules/cash_reconciliation/application/pix_cnpj.py) | I | Local/GET | test_pix_cnpj | Testes de valor/hora/ambiguidade; falta caso real positivo conferido |
| Mais Pagamentos | Total local declarado e diferença | [mais_pagamentos.py](../../WebPosto_API/src/modules/cash_reconciliation/application/mais_pagamentos.py) | V | JSON local + GET | test_mais_pagamentos | CLI e comparação real registrados no 19C/D |
| Mais Pagamentos | Mensagem privada/detalhe hora+valor | [telegram_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/telegram_cartoes.py) | I | Telegram/local/GET ERP | test_mais_pagamentos | Sem teste operacional real do receptor registrado |
| Premmia | Portal, XLSX mensal e conciliação | [premmia_portal.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/premmia_portal.py) | V | Browser/exportação; sem lançamento ERP | test_premmia_portal | XLSX/evidências locais e Sprint 13/14.1; sujeito a verificação humana |
| Sangria / banco | Sangria x depósito/cofre por OFX | [conciliar.py](../../WebPosto_API/src/modules/cash_reconciliation/application/conciliar.py) | V | GET/local | test_conciliar, test_matching | ADR-002 registra conferência de viabilidade; saldo da conta ERP não representa cofre |
| Vale / despesa | Integração à auditoria de caixa | [webposto_detalhes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_detalhes.py) | V | GET | test_webposto_detalhes, test_fechamento | Snapshots com auditoria de caixa; não prova todos os cenários de desconto |
| Despesa | Extrato sem lançamento e fila de comprovantes | [despesas_sem_lancamento.py](../../WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py), [processar_comprovante.py](../../WebPosto_API/src/modules/cash_reconciliation/application/processar_comprovante.py) | P | GET/local; Gemini externo quando acionado | test_despesas_sem_lancamento, test_comprovantes_fila | Planilha local existe; cadeia de recepção/fila/lançamento não validada inteira |
| Títulos | Pagos no banco sem baixa, agrupamentos | [titulos_pagos_sem_baixa.py](../../WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py) | P | GET/local | test_titulos_pagos_sem_baixa | Candidatos e testes; não é baixa automática |
| OFX | Parser SGML/XML, encoding, sinal e hash | [extrato_reader.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py) | V | Arquivos locais | test_extrato_reader, test_ofx_reader | Extratos usados em conferências reais; deduplicação global não é universal |
| OFX | Importação no ERP | [webposto_escrita_ofx.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py) | P | POST ERP | test_webposto_escrita_ofx | Incidente registrado; aceitação HTTP não validou sinal de débito |
| Produtos | Catálogo/preço/custo por empresa | [fetch_produtos_catalog.py](../../WebPosto_API/src/application/usecases/fetch_produtos_catalog.py), [produto_catalog.py](../../WebPosto_API/src/services/produto_catalog.py) | P | GET | test_fetch_produtos_catalog, test_get_cobertura_total | Duas cadeias; equivalência de versões/contagem não validada por completo |
| Estoque / inventário | Saldo e período legados; wrapper de itens | [webposto_client.py](../../WebPosto_API/src/gateway/webposto_client.py), [produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) | P | GET; wrappers de escrita separados | test_client, test_get_cobertura_total | Não há auditoria física/contagem V1 integrada |
| Compras / fornecedor | NF entrada e fornecedores para conciliar despesas | [integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py), [titulos_pagos_sem_baixa.py](../../WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py) | P | GET; pedido POST separado | test_titulos_pagos_sem_baixa | Faltam itens de entrada V1 no fluxo de estoque |
| Conveniência | Venda/item/custo/desconto/caixa | [network_financial_overview_service.py](../../WebPosto_API/src/services/network_financial_overview_service.py) | P | GET | testes financeiros/normalização | Consulta/visão financeira não constitui auditoria completa de inventário |
| Combustível | Analytics de LMC e resumo de vendas | [fuel_analytics_service.py](../../WebPosto_API/src/services/fuel_analytics_service.py) | P | GET legado | testes de cobertura/serviços | Agregação não compara encerrante e medição física de forma auditável |
| Bombas / bicos / tanques | Grafo V1 de equipamento | OpenAPI, sem adapter dedicado localizado | A | GET no contrato | Nenhum teste dedicado localizado | Não confundir campo bico no abastecimento com cadastro integrado |
| LMC | Wrappers e visão executiva legados | [combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py), [fuel_analytics_service.py](../../WebPosto_API/src/services/fuel_analytics_service.py) | P | GET | Testes não provam leitura V1 | Falta validação de LMCS/medição/entrada V1 |
| Comercial | Litros/aditivado/metas por frentista | [placar.py](../../WebPosto_API/src/modules/commercial_performance/application/placar.py) | V | GET/local | commercial_performance/test_placar | Snapshots de placar e histórico de entrega; metas não generalizadas para loja |
| Cielo / Rede | Integração de adquirente | [recebimentos.py](../../WebPosto_API/src/modules/cash_reconciliation/application/recebimentos.py), units.json | A | Sem coletor | test_recebimentos cobre pendência | Nome/configuração pendente não é integração |
| Telegram | Resumo/documento e controle por dia | [noturno.py](../../WebPosto_API/src/jobs/noturno.py), [telegram.py](../../WebPosto_API/src/shared/notificacao/telegram.py) | V | POST externo | test_telegram, test_telegram_resumo | Registros locais de envio; não garantem frescor da coleta nem leitura pelo diretor |
| Jobs | Composição caixa + placar + resumo | [noturno.py](../../WebPosto_API/src/jobs/noturno.py) | P | GET/browser/local e envio condicionado | test_noturno | Agendado, porém falhou hoje; ver seção 10 |
| Autenticação | JWT/cookie, perfis, acesso por unidade | [auth.py](../../WebPosto_API/src/interfaces/http/routes/auth.py), [dependencies.py](../../WebPosto_API/src/interfaces/http/dependencies.py) | I | Sessão/local | test_auth_routes, test_auth_access | Testes não certificam proteção de todos os entrypoints legados |
| Administração | Saúde, métricas, caches, sync, CRUDs locais | [interfaces/http/routes](../../WebPosto_API/src/interfaces/http/routes) | P | GET e mutações locais | Testes específicos + inventário abaixo | APIs de mesma função em entrypoints diferentes |

### Inventário exaustivo das declarações de rota

Cada linha do apêndice A identifica método/path, controller/router, função,
serviços/chamadas, schemas, domínio, leitura/escrita, classificação, testes e
evidência estática de ligação. Os mounts foram conferidos no código, sem iniciar
servidor. Aliases de `presentation/app.py` para `/api/v1/audit/*` reutilizam as
três declarações de `/v1/audit/*`; não foram contados como novas funções.
StaticFiles e Swagger/Redoc/OpenAPI automáticos não são operações de negócio.

#### Apêndice A — 200 declarações / 30 controllers

Status da **superfície HTTP**, não do serviço interno: I = declarada/montada no app principal, sem certificação operacional de cada rota; L = alternativa, exemplo ou não montada no principal. Ler GET pode gerar caches/propostas/arquivos locais: a coluna de efeito não promete ausência de I/O. Request/response são anotações do código; `dict`/sem anotação não constituem schema de negócio fechado.

Serviços listados são chamadas lexicais do handler (até oito, com indicação das demais no próprio fonte), não call graph executado. Teste indica apenas referência textual ao handler/path; ausência não exclui teste indireto. UI conta arquivos com path literal: paths interpolados podem não ser encontrados.

##### [PASSO_4_EXEMPLO_ROUTES.py](../../PASSO_4_EXEMPLO_ROUTES.py)

Domínio: **Gateway/administração**. 9 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /auditoria/despesas/{unidade_id}` | `router.get_despesas_unidade` (L68) | `datetime.combine`, `datetime.max.time`, `datetime.min.time`, `repo.get_despesas_by_unidade` | `str, date, Optional[StatusJustificativa], AuditoriaRepository` → `List[DespesaCaixa]` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /auditoria/despesas` | `router.create_despesa` (L122) | `repo.create_despesa` | `DespesaCaixa, AuditoriaRepository` → `DespesaCaixa` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `PATCH /auditoria/despesas/{despesa_id}/status` | `router.update_despesa_status` (L164) | `repo.update_despesa_status` | `str, StatusJustificativa, Optional[str], AuditoriaRepository` → `dict` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/fechamentos/{unidade_id}` | `router.get_fechamentos_unidade` (L218) | `ListaFechamentos`, `datetime.combine`, `datetime.min.time`, `repo.get_fechamentos_consolidated` | `str, date, AuditoriaRepository` → `ListaFechamentos` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /auditoria/fechamentos` | `router.create_fechamento` (L272) | `repo.create_fechamento` | `FechamentoCaixa, AuditoriaRepository` → `FechamentoCaixa` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `PATCH /auditoria/fechamentos/{fechamento_id}/flag-auditoria` | `router.flag_closure_for_audit` (L305) | `repo.flag_fechamento_for_audit` | `str, AuditoriaRepository` → `dict` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/resumo/{unidade_id}` | `router.get_resumo_auditoria` (L356) | `datetime.combine`, `datetime.min.time`, `repo.get_auditoria_resumo_unidade` | `str, date, AuditoriaRepository` → `ResumoAuditoriaUnidade` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/insights` | `router.get_auditoria_insights` (L405) | `datetime.combine`, `datetime.max.time`, `datetime.min.time`, `repo.calculate_auditoria_insights` | `date, Optional[str], AuditoriaRepository` → `List[dict]` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/health` | `router.health_check` (L450) | `datetime.utcnow`, `datetime.utcnow().isoformat` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | [conftest.py](../../tests/conftest.py); [test_parallel_ias.py](../../tests/integration/multi_tenant/test_parallel_ias.py); refs testes=2, UI=0; fonte AST |

##### [WebPosto_API/explorador_standalone.py](../../WebPosto_API/explorador_standalone.py)

Domínio: **Gateway/administração**. 11 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/explorer/catalog` | `app.catalog` (L99) | Handler direto | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/explorer/config` | `app.explorer_config` (L104) | `(_env('WEBPOSTO_API_KEY') or _env('WEBPOSTO_CHAVE') or '').strip`, `_env`, `normalize_base` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/explorer/stats` | `app.stats` (L122) | `e.get` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/explorer/proxy` | `app.proxy` (L140) | `(req.chave or _env('WEBPOSTO_API_KEY') or _env('WEBPOSTO_CHAVE') or '').strip`, `_env`, `base.lower`, `base.lower().startswith`, `client.delete`, `client.get`, `client.patch`, `client.post`; +11 no fonte | `ProxyBody` → `sem anotação` | ERP GET/POST/PUT/PATCH/DELETE | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /` | `app.root` (L200) | `FileResponse`, `HTMLResponse`, `index.is_file` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /tecnico` | `app.tecnico` (L211) | `FileResponse`, `HTMLResponse`, `path.is_file` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /app/vendas` | `app.app_dashboard_vendas` (L231) | `_root_html` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /app/abastecimento` | `app.app_dashboard_abastecimento` (L236) | `_root_html` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /app/despesas` | `app.app_dashboard_despesas` (L241) | `_root_html` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /app/filtros` | `app.app_dashboard_filtros` (L246) | `_root_html` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /app/landing` | `app.app_landing` (L251) | `_root_html` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/logos-webposto-gateway/src/presentation/crud_routes.py](../../WebPosto_API/logos-webposto-gateway/src/presentation/crud_routes.py)

Domínio: **Gateway/administração**. 5 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /v1/crud/{resource}` | `router.list_resource` (L106) | `_resolve_model`, `count_stmt.where`, `db.execute`, `func.count`, `getattr(model, col).ilike`, `item.model_dump`, `or_`, `result.scalars`; +7 no fonte | `str, None, AsyncSession, int, Optional[str]` → `sem anotação` | Leitura DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/crud/{resource}/{record_id}` | `router.get_resource` (L152) | `_resolve_model`, `db.get`, `record.model_dump` | `str, int, None, AsyncSession` → `sem anotação` | Leitura DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /v1/crud/{resource}` | `router.create_resource` (L166) | `_resolve_model`, `_validate_payload`, `db.add`, `db.commit`, `db.refresh`, `entity.model_dump`, `model` | `str, Dict[str, Any], None, AsyncSession` → `sem anotação` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `PUT /v1/crud/{resource}/{record_id}` | `router.update_resource` (L187) | `_resolve_model`, `_validate_payload`, `db.add`, `db.commit`, `db.get`, `db.refresh`, `entity.model_dump`, `payload.items`; +1 no fonte | `str, int, Dict[str, Any], None, AsyncSession` → `sem anotação` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `DELETE /v1/crud/{resource}/{record_id}` | `router.delete_resource` (L215) | `_resolve_model`, `db.commit`, `db.delete`, `db.get` | `str, int, None, AsyncSession` → `sem anotação` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/logos-webposto-gateway/src/presentation/routes.py](../../WebPosto_API/logos-webposto-gateway/src/presentation/routes.py)

Domínio: **Gateway/administração**. 5 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /ready` | `router.ready` (L52) | Handler direto | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=0; fonte AST |
| `GET /health` | `router.health` (L57) | `db.execute`, `perf_counter`, `text` | `AsyncSession` → `sem anotação` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=2; fonte AST |
| `GET /v1/expenses` | `router.get_expenses` (L84) | `Header`, `consulta.isoformat`, `datetime.utcnow`, `expense.model_dump`, `use_case.execute` | `Annotated[FetchExpensesUseCase, Depends(get_fetch_expenses_use_case)], Annotated[None, Depends(require_consumer_token)], Annotated[str, Header(alias='X-Posto-ID')], Annotated[Optional[datetime], Query()]` → `sem anotação` | Consulta; I/O local possível | L | [test_finance_center_service.py](../../WebPosto_API/tests/unit/test_finance_center_service.py); refs testes=1, UI=0; fonte AST |
| `GET /v1/` | `router.v1_root` (L108) | Handler direto | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=1, UI=5; fonte AST |
| `GET /v1/products` | `router.get_products` (L127) | `Header`, `use_case.execute` | `Annotated[FetchProductsUseCase, Depends(get_fetch_products_use_case)], Annotated[None, Depends(require_consumer_token)], Annotated[str, Header(alias='X-Posto-ID')], Annotated[bool, Query()]` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/app.py](../../WebPosto_API/src/interfaces/http/app.py)

Domínio: **Gateway/administração**. 1 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /app/financial` | `app.financial_frontend` (L71) | `FileResponse` | `sem anotação` → `FileResponse` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/analytics.py](../../WebPosto_API/src/interfaces/http/routes/analytics.py)

Domínio: **Analytics**. 18 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/v1/kpis` | `router.get_kpis` (L99) | `build_cache_key`, `empresa_codigo_cache_key`, `fetch_kpis_multiselect`, `get_cache`, `set_cache` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/sales/fuel-summary` | `router.get_sales_fuel_summary` (L151) | `build_cache_key`, `empresa_codigo_cache_key`, `fetch_fuel_summary_multiselect`, `get_cache`, `set_cache` | `str, str  /  None` → `list[dict]` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/fuel/executive` | `router.get_fuel_executive` (L205) | `build_cache_key`, `empresa_codigo_cache_key`, `fetch_fuel_executive_multiselect`, `get_cache`, `set_cache` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/products/catalog` | `router.get_products_catalog` (L251) | `_product_catalog.get_catalog`, `chunk.strip`, `company_codes.append`, `empresaCodigo.split`, `resp.to_dict`, `value.isdigit` | `str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/dre` | `router.get_dre` (L281) | `build_cache_key`, `empresa_codigo_cache_key`, `fetch_dre_multiselect`, `get_cache`, `set_cache` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/data-quality` | `router.get_data_quality` (L327) | `build_cache_key`, `empresa_codigo_cache_key`, `fetch_data_quality_multiselect`, `get_cache`, `set_cache` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/filiais` | `router.get_filiais` (L397) | `_overview.get_companies`, `resp.to_dict` | `sem anotação` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/network/coverage` | `router.get_network_coverage` (L409) | `_overview.get_companies`, `build_network_coverage` | `sem anotação` → `dict` | Consulta; I/O local possível | I | [test_network_coverage.py](../../WebPosto_API/tests/unit/test_network_coverage.py); refs testes=1, UI=0; fonte AST |
| `GET /api/v1/executive/snapshot` | `router.get_executive_snapshot` (L423) | `_executive_snapshot.get_snapshot` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/executive/refresh` | `router.post_executive_refresh` (L447) | `_executive_snapshot.start_refresh_background` | `str, str  /  None` → `dict` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/fuel/snapshot` | `router.get_fuel_snapshot` (L481) | `_fuel_snapshot.get_snapshot` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/fuel/refresh` | `router.post_fuel_refresh` (L499) | `_fuel_snapshot.start_refresh_background` | `str, str  /  None` → `dict` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/financial/snapshot` | `router.get_financial_snapshot` (L517) | `_financial_snapshot.get_snapshot` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/financial/refresh` | `router.post_financial_refresh` (L543) | `_financial_snapshot.start_refresh_background` | `str, str  /  None` → `dict` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/sync/control` | `router.get_sync_control` (L569) | `sync_control_service.get_all` | `sem anotação` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/sync/logs` | `router.get_integration_logs` (L587) | `integration_log_service.list_recent` | `int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/sync/errors` | `router.get_integration_errors` (L605) | `integration_log_service.list_errors` | `int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/sync/control/{endpoint}/reset` | `router.reset_sync_control` (L623) | `sync_control_service.reset` | `str` → `dict` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/auditoria.py](../../WebPosto_API/src/interfaces/http/routes/auditoria.py)

Domínio: **Auditoria**. 5 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /auditoria/health` | `router.health_check` (L41) | `datetime.now`, `datetime.now().isoformat`, `log.error` | `AuditoriaService` → `dict` | Consulta; I/O local possível | L | [conftest.py](../../tests/conftest.py); [test_parallel_ias.py](../../tests/integration/multi_tenant/test_parallel_ias.py); refs testes=2, UI=0; fonte AST |
| `GET /auditoria/despesas/{unidade_id}` | `router.get_despesas_unidade` (L91) | `datetime.fromisoformat`, `log.error`, `log.info`, `service.extrair_despesas_por_unidade` | `str, Optional[str], AuditoriaService` → `List[DespesaCaixa]` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/fechamentos/{unidade_id}` | `router.get_fechamentos_unidade` (L146) | `datetime.fromisoformat`, `log.error`, `log.info`, `service.get_fechamentos_com_resumo` | `str, Optional[str], AuditoriaService` → `ListaFechamentos` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/resumo/{unidade_id}` | `router.get_resumo_auditoria` (L199) | `datetime.fromisoformat`, `log.error`, `log.info`, `service.calcular_resumo_unidade`, `service.extrair_despesas_por_unidade`, `service.extrair_fechamentos` | `str, Optional[str], AuditoriaService` → `ResumoAuditoriaUnidade` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /auditoria/registrar-despesa` | `router.registrar_despesa` (L256) | `log.error`, `log.info`, `log.warning`, `service.registrar_despesa` | `DespesaCaixa, AuditoriaService` → `DespesaCaixa` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/auth.py](../../WebPosto_API/src/interfaces/http/routes/auth.py)

Domínio: **Autenticação**. 5 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `POST /auth/login` | `router.login` (L68) | `_access_token`, `_public_user`, `_set_access_cookie`, `_set_refresh_cookie`, `authenticate_user`, `create_refresh_token` | `LoginPayload, Response` → `sem anotação` | Interno/local ou dispara coleta | I | [test_noturno.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_noturno.py); [test_auth_access.py](../../WebPosto_API/tests/unit/test_auth_access.py); refs testes=3, UI=0; fonte AST |
| `POST /auth/refresh` | `router.refresh` (L91) | `_access_token`, `_public_user`, `_set_access_cookie`, `decode_token`, `find_auth_user`, `payload.get`, `request.cookies.get` | `Request, Response` → `sem anotação` | Interno/local ou dispara coleta | I | [test_executive_snapshot.py](../../WebPosto_API/scripts/test_executive_snapshot.py); [test_auth_access.py](../../WebPosto_API/tests/unit/test_auth_access.py); refs testes=2, UI=0; fonte AST |
| `POST /auth/tv-token` | `router.create_display_token` (L118) | `create_access_token`, `response.delete_cookie`, `response.set_cookie`, `timedelta` | `DisplayTokenPayload, Response, dict` → `sem anotação` | Interno/local ou dispara coleta | I | [test_auth_access.py](../../WebPosto_API/tests/unit/test_auth_access.py); refs testes=1, UI=0; fonte AST |
| `GET /auth/me` | `router.get_session` (L152) | `_public_user`, `current_user.get` | `dict` → `sem anotação` | Consulta; I/O local possível | I | [test_empresa_repository.py](../../tests/integration/test_empresa_repository.py); [test_performance_stress.py](../../tests/integration/test_performance_stress.py); refs testes=2, UI=0; fonte AST |
| `POST /auth/logout` | `router.logout` (L161) | `response.delete_cookie` | `Response` → `sem anotação` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/cash_flow.py](../../WebPosto_API/src/interfaces/http/routes/cash_flow.py)

Domínio: **Fluxo de caixa**. 6 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/v1/finance/cash-flow` | `router.cash_flow_all` (L22) | `(await _cash_flow.build(filters, empresaCodigo)).to_dict`, `_cash_flow.build`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/cash-flow/daily` | `router.cash_flow_daily` (L32) | `cash_flow_all`, `data.get`, `resp.get` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/cash-flow/weekly` | `router.cash_flow_weekly` (L43) | `cash_flow_all`, `data.get`, `resp.get` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/cash-flow/monthly` | `router.cash_flow_monthly` (L54) | `cash_flow_all`, `data.get`, `resp.get` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/cash-flow/snapshot` | `router.cash_flow_snapshot` (L65) | `_snapshot.get_snapshot` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/finance/cash-flow/refresh` | `router.cash_flow_refresh` (L74) | `_snapshot.refresh_background`, `asyncio.create_task` | `str, str  /  None` → `dict` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/clientes.py](../../WebPosto_API/src/interfaces/http/routes/clientes.py)

Domínio: **Clientes**. 5 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `POST /clientes/` | `router.criar_cliente` (L19) | `service.criar_cliente` | `ClienteCreateDTO, ClienteService` → `ClienteResponseDTO` | Escrita DB local | I | [test_cliente_service.py](../../WebPosto_API/tests/unit/application/test_cliente_service.py); refs testes=1, UI=0; fonte AST |
| `GET /clientes/{cliente_id}` | `router.obter_cliente` (L27) | `service.obter_cliente` | `str, ClienteService` → `ClienteResponseDTO` | Leitura DB local | I | [test_cliente_service.py](../../WebPosto_API/tests/unit/application/test_cliente_service.py); refs testes=1, UI=0; fonte AST |
| `GET /clientes/` | `router.listar_clientes` (L40) | `service.listar_ativos`, `service.listar_clientes` | `int, bool, ClienteService` → `List[ClienteResponseDTO]` | Leitura DB local | I | [test_cliente_service.py](../../WebPosto_API/tests/unit/application/test_cliente_service.py); refs testes=1, UI=0; fonte AST |
| `PUT /clientes/{cliente_id}` | `router.atualizar_cliente` (L53) | `service.atualizar_cliente` | `str, ClienteUpdateDTO, ClienteService` → `ClienteResponseDTO` | Escrita DB local | I | [test_cliente_service.py](../../WebPosto_API/tests/unit/application/test_cliente_service.py); refs testes=1, UI=0; fonte AST |
| `DELETE /clientes/{cliente_id}` | `router.deletar_cliente` (L68) | `service.deletar_cliente` | `str, ClienteService` → `sem anotação` | Escrita DB local | I | [test_cliente_service.py](../../WebPosto_API/tests/unit/application/test_cliente_service.py); refs testes=1, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/expenses.py](../../WebPosto_API/src/interfaces/http/routes/expenses.py)

Domínio: **Despesas**. 1 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `POST /expenses/extract` | `router.extract_expenses` (L14) | `item.model_dump`, `use_case.execute` | `Dict[str, Any], ExtractExpensesFromCashMovement` → `sem anotação` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/fechamento_enterprise.py](../../WebPosto_API/src/interfaces/http/routes/fechamento_enterprise.py)

Domínio: **Caixa**. 18 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /v1/permissions` | `router.permissions` (L38) | `_client.discover_permissions` | `sem anotação` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/abastecimento` | `router.abastecimento` (L44) | `_abastecimento.get_periodo`, `resp.to_dict` | `str` → `dict` | Consulta; I/O local possível | I | [test_endpoints_bi.py](../../WebPosto_API/test_endpoints_bi.py); [test_endpoints_bi_v2.py](../../WebPosto_API/test_endpoints_bi_v2.py); refs testes=22, UI=0; fonte AST |
| `GET /v1/expenses` | `router.expenses` (L50) | `_expenses.get_periodo`, `resp.to_dict` | `str` → `dict` | Consulta; I/O local possível | I | [test_financial_expenses_real.py](../../WebPosto_API/tests/integration/test_financial_expenses_real.py); [test_data_quality_service.py](../../WebPosto_API/tests/services/test_data_quality_service.py); refs testes=2, UI=0; fonte AST |
| `GET /v1/financeiro` | `router.financeiro` (L56) | `_financeiro.get_periodo`, `resp.to_dict` | `str` → `dict` | Consulta; I/O local possível | I | [test_enterprise_real_endpoints.py](../../WebPosto_API/tests/integration/test_enterprise_real_endpoints.py); [test_financial_expenses_real.py](../../WebPosto_API/tests/integration/test_financial_expenses_real.py); refs testes=10, UI=0; fonte AST |
| `GET /v1/caixa` | `router.caixa` (L62) | `_caixa.get_caixa`, `resp.to_dict` | `str` → `dict` | Consulta; I/O local possível | I | [test_enterprise_real_endpoints.py](../../WebPosto_API/tests/integration/test_enterprise_real_endpoints.py); [test_financial_expenses_real.py](../../WebPosto_API/tests/integration/test_financial_expenses_real.py); refs testes=17, UI=0; fonte AST |
| `GET /v1/caixa-apresentado` | `router.caixa_apresentado` (L68) | `_caixa.get_caixa_apresentado`, `resp.to_dict` | `str` → `dict` | Consulta; I/O local possível | I | [test_enterprise_real_endpoints.py](../../WebPosto_API/tests/integration/test_enterprise_real_endpoints.py); refs testes=1, UI=0; fonte AST |
| `GET /v1/vendas-combustivel` | `router.vendas_combustivel` (L74) | `_vendas_combustivel.get_periodo`, `resp.to_dict` | `str` → `dict` | Consulta; I/O local possível | I | [test_endpoints_bi.py](../../WebPosto_API/test_endpoints_bi.py); [test_endpoints_bi_v2.py](../../WebPosto_API/test_endpoints_bi_v2.py); refs testes=5, UI=0; fonte AST |
| `GET /v1/box-closure` | `router.box_closure` (L80) | `Header`, `_fechamento.get_fechamento`, `resp.to_dict` | `str` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/operacao-inteligente` | `router.operacao_inteligente` (L90) | `Header`, `_operacao_inteligente.get_visao_unificada`, `resp.to_dict` | `str` → `dict` | Consulta; I/O local possível | I | [test_enterprise_real_endpoints.py](../../WebPosto_API/tests/integration/test_enterprise_real_endpoints.py); refs testes=1, UI=0; fonte AST |
| `GET /v1/observability` | `router.observability` (L100) | `get_metrics_snapshot` | `sem anotação` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/network/financial-overview` | `router.network_financial_overview` (L112) | `FinancialOverviewFilters`, `_network_financial_overview.get_financial_overview`, `resp.to_dict` | `str, int  /  None, str  /  None, Decimal  /  None` → `dict` | Consulta; I/O local possível | I | [test_financial_expenses_real.py](../../WebPosto_API/tests/integration/test_financial_expenses_real.py); [test_network_financial_overview_real.py](../../WebPosto_API/tests/integration/test_network_financial_overview_real.py); refs testes=2, UI=0; fonte AST |
| `GET /v1/financial/overview` | `router.financial_overview` (L149) | `FinancialOverviewFilters`, `_network_financial_overview.get_financial_overview_only`, `build_overview_filters`, `resp.to_dict` | `str, str  /  None, Decimal  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/financial/companies` | `router.financial_companies` (L179) | `_network_financial_overview.get_companies`, `resp.to_dict` | `sem anotação` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/financial/expenses` | `router.financial_expenses` (L185) | `FinancialOverviewFilters`, `_network_financial_overview.get_financial_expenses`, `build_overview_filters`, `resp.to_dict` | `str, str  /  None, Decimal  /  None, int` → `dict` | Consulta; I/O local possível | I | [test_financial_expenses_real.py](../../WebPosto_API/tests/integration/test_financial_expenses_real.py); refs testes=1, UI=0; fonte AST |
| `GET /v1/financial/accounts-payable` | `router.financial_accounts_payable` (L216) | `FinancialOverviewFilters`, `_network_financial_overview.get_accounts_payable`, `build_overview_filters`, `resp.to_dict` | `str, str  /  None, int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/financial/accounts-receivable` | `router.financial_accounts_receivable` (L243) | `FinancialOverviewFilters`, `_network_financial_overview.get_accounts_receivable`, `build_overview_filters`, `resp.to_dict` | `str, str  /  None, int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/sales` | `router.sales` (L262) | `FinancialOverviewFilters`, `_network_financial_overview.get_sales`, `build_overview_filters`, `resp.to_dict` | `str, str  /  None, int` → `dict` | Consulta; I/O local possível | I | [test_fuel_summary.py](../../WebPosto_API/test_fuel_summary.py); [test_data_quality_service.py](../../WebPosto_API/tests/services/test_data_quality_service.py); refs testes=3, UI=0; fonte AST |
| `GET /v1/stock` | `router.stock` (L281) | `FinancialOverviewFilters`, `_network_financial_overview.get_stock`, `build_overview_filters`, `resp.to_dict` | `str, str  /  None, int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/finance_center.py](../../WebPosto_API/src/interfaces/http/routes/finance_center.py)

Domínio: **Financeiro**. 8 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/v1/finance/center/summary` | `router.finance_center_summary` (L38) | `(await _finance_center.get_summary(filters, empresaCodigo)).to_dict`, `_finance_center.get_summary`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/center/expenses` | `router.finance_center_expenses` (L48) | `(await _finance_center.get_expenses(filters, empresaCodigo, page, limit)).to_dict`, `_common_params`, `_finance_center.get_expenses` | `str, str  /  None, int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/center/payables` | `router.finance_center_payables` (L63) | `(await _finance_center.get_payables(filters, empresaCodigo, page, limit)).to_dict`, `_finance_center.get_payables`, `build_finance_center_filters` | `str, str  /  None, int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/center/receivables` | `router.finance_center_receivables` (L75) | `(await _finance_center.get_receivables(filters, empresaCodigo, page, limit)).to_dict`, `_finance_center.get_receivables`, `build_finance_center_filters` | `str, str  /  None, int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/center/bank-movements` | `router.finance_center_bank_movements` (L87) | `(await _finance_center.get_bank_movements(filters, empresaCodigo, page, limit)).to_dict`, `_finance_center.get_bank_movements`, `build_finance_center_filters` | `str, str  /  None, int` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/center/cash` | `router.finance_center_cash` (L99) | `(await _finance_center.get_cash(filters, empresaCodigo)).to_dict`, `_finance_center.get_cash`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/center/snapshot` | `router.finance_center_snapshot` (L109) | `_snapshot.get_snapshot` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/finance/center/refresh` | `router.finance_center_refresh` (L118) | `_snapshot.refresh_background`, `asyncio.create_task` | `str, str  /  None` → `dict` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/financial_intelligence.py](../../WebPosto_API/src/interfaces/http/routes/financial_intelligence.py)

Domínio: **Financeiro**. 8 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/v1/finance/intelligence` | `router.financial_intelligence` (L34) | `(await _intelligence.build(filters, empresaCodigo)).to_dict`, `_intelligence.build`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/intelligence/health-score` | `router.financial_health_score` (L44) | `(await _health.build(filters, empresaCodigo)).to_dict`, `_health.build`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/intelligence/advanced` | `router.financial_intelligence_advanced` (L54) | `(await _advanced.build(filters, empresaCodigo)).to_dict`, `_advanced.build`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/intelligence/health-score-v3` | `router.financial_health_score_v3` (L64) | `(await _health_v3.build(filters, empresaCodigo)).to_dict`, `_health_v3.build`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/intelligence/segmentation` | `router.financial_supplier_segmentation` (L74) | `(await _segmentation.build(filters, empresaCodigo)).to_dict`, `_segmentation.build`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/intelligence/suppliers` | `router.financial_supplier_intelligence` (L84) | `(await _suppliers.build(filters, empresaCodigo)).to_dict`, `_suppliers.build`, `build_finance_center_filters` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/finance/intelligence/snapshot` | `router.financial_intelligence_snapshot` (L94) | `_snapshot.get_snapshot` | `str, str  /  None` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/finance/intelligence/refresh` | `router.financial_intelligence_refresh` (L103) | `_snapshot.refresh_background`, `asyncio.create_task` | `str, str  /  None` → `dict` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/gateway_expenses.py](../../WebPosto_API/src/interfaces/http/routes/gateway_expenses.py)

Domínio: **Despesas**. 1 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /v1/expenses` | `router.get_expenses` (L30) | `Header`, `data_consulta.isoformat`, `e.model_dump`, `usecase.execute` | `date, str, FetchExpensesUseCase` → `sem anotação` | Consulta; I/O local possível | I | [test_finance_center_service.py](../../WebPosto_API/tests/unit/test_finance_center_service.py); refs testes=1, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/health.py](../../WebPosto_API/src/interfaces/http/routes/health.py)

Domínio: **Saúde**. 2 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /health` | `router.health_check` (L56) | `(database_url or '').lower`, `RuntimeError`, `_cached_sqlite_write_probe`, `_sqlite_db_path`, `conn.execute`, `engine.connect`, `os.getenv`, `text` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | I | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=4, UI=2; fonte AST |
| `GET /ready` | `router.readiness_check` (L105) | Handler direto | `sem anotação` → `sem anotação` | Consulta; I/O local possível | I | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/metrics.py](../../WebPosto_API/src/interfaces/http/routes/metrics.py)

Domínio: **Métricas**. 2 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /metrics/executive` | `router.executive_metrics` (L12) | `RedisCacheFactory.criar_cache`, `cache.disconnect`, `get_executive_metrics` | `Request, Dict` → `sem anotação` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /metrics/stream` | `router.stream_metrics` (L24) | Handler direto | `sem anotação` → `sem anotação` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/interfaces/http/routes/sync.py](../../WebPosto_API/src/interfaces/http/routes/sync.py)

Domínio: **Sincronização**. 5 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `POST /sync/clientes` | `router.sync_clientes` (L10) | `service.sync_clientes` | `SyncService` → `sem anotação` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /sync/abastecimentos` | `router.sync_abastecimentos` (L16) | `service.sync_abastecimentos` | `SyncService` → `sem anotação` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /sync/financeiro` | `router.sync_financeiro` (L22) | `service.sync_financeiro` | `SyncService` → `sem anotação` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /sync/caixa` | `router.sync_caixa` (L28) | `service.sync_caixa` | `SyncService` → `sem anotação` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /sync/full` | `router.full_sync` (L34) | `service.full_sync` | `SyncService` → `sem anotação` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/main_minimal.py](../../WebPosto_API/src/main_minimal.py)

Domínio: **Gateway/administração**. 7 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /health` | `app.health` (L47) | `datetime.now`, `datetime.now().isoformat` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=2; fonte AST |
| `OPTIONS /{full_path:path}` | `app.options_handler` (L60) | Handler direto | `str` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /sync/financeiro` | `app.sync_financeiro` (L67) | `__import__`, `__import__('datetime').datetime.now`, `__import__('datetime').datetime.now().isoformat`, `client.get_financeiro` | `sem anotação` → `sem anotação` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /sync/financeiro` | `app.sync_financeiro` (L67) | `__import__`, `__import__('datetime').datetime.now`, `__import__('datetime').datetime.now().isoformat`, `client.get_financeiro` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /sync/caixa` | `app.sync_caixa` (L86) | `__import__`, `__import__('datetime').datetime.now`, `__import__('datetime').datetime.now().isoformat`, `client.get_caixa` | `sem anotação` → `sem anotação` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /sync/caixa` | `app.sync_caixa` (L86) | `__import__`, `__import__('datetime').datetime.now`, `__import__('datetime').datetime.now().isoformat`, `client.get_caixa` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /docs` | `app.swagger` (L104) | Handler direto | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/modules/cash_reconciliation/interfaces/http.py](../../WebPosto_API/src/modules/cash_reconciliation/interfaces/http.py)

Domínio: **Caixa/recebimentos**. 18 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/v1/cash-audit/lancamentos-logos` | `router.listar_lancamentos_logos` (L97) | `current_user.get`, `p.publica`, `piloto_cartao.historico`, `piloto_cartao.historico_publico`, `piloto_cartao.preparar`, `require_unit_access`, `ultimos.values` | `int, date, dict` → `dict` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/cash-audit/lancamentos-logos/{acao_id}/{decisao}` | `router.decidir_lancamento_logos` (L119) | `current_user.get`, `piloto_cartao.decidir`, `require_unit_access`, `type` | `str, Literal['aprovar', 'recusar', 'desfazer'], CartaoDecisaoPayload, dict` → `dict` | Pode escrever ERP; ver seção 9 | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/cash-audit/conferencia-recebimentos` | `router.obter_conferencia_recebimentos` (L151) | `_conferencia`, `conferencia.model_dump`, `i.model_dump` | `int, date, dict` → `dict` | Consulta; I/O local possível | I | [test_conferencia_recebimentos.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_conferencia_recebimentos.py); refs testes=1, UI=0; fonte AST |
| `GET /api/v1/cash-audit/conferencia-recebimentos.xlsx` | `router.exportar_conferencia_recebimentos` (L164) | `BytesIO`, `Response`, `Workbook`, `_conferencia`, `abas_conferencia_recebimentos`, `stream.getvalue`, `workbook.close`, `workbook.remove`; +1 no fonte | `int, date, dict` → `Response` | Consulta; I/O local possível | I | [test_conferencia_recebimentos.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_conferencia_recebimentos.py); refs testes=1, UI=0; fonte AST |
| `POST /api/v1/cash-audit/conferencia-recebimentos/{acao_id}` | `router.marcar_conferencia_recebimentos` (L185) | `_conferencia`, `current_user.get`, `decidir_proposta`, `next`, `repositorio_pendencias.registrar_conferencia` | `str, ConferenciaPayload, dict` → `dict` | Interno/local ou dispara coleta | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/cash-audit/relatorio-caixa` | `router.obter_relatorio_caixa_dia` (L383) | `_compor_relatorio_caixa_atual`, `_compor_relatorio_caixa_dia`, `carregar_unidades`, `current_user.get`, `dia.isoformat`, `relatorios.append`, `require_unit_access` | `date, int  /  None, bool, dict` → `dict` | Consulta; I/O local possível | I | [test_relatorio_caixa_dia.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_relatorio_caixa_dia.py); refs testes=1, UI=0; fonte AST |
| `POST /api/v1/cash-audit/sincronizar` | `router.sincronizar_relatorio_caixa` (L417) | `_compor_relatorio_caixa_atual`, `_ultima_sincronizacao.get`, `agora`, `carregar_unidades`, `current_user.get`, `dia.isoformat`, `formatar_data_hora`, `require_unit_access`; +1 no fonte | `int, date, dict` → `dict` | Interno/local ou dispara coleta | I | [test_relatorio_caixa_dia.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_relatorio_caixa_dia.py); refs testes=1, UI=0; fonte AST |
| `GET /api/v1/cash-audit/relatorio-caixa.xlsx` | `router.exportar_relatorio_caixa_dia` (L449) | `Response`, `_compor_relatorio_caixa_atual`, `_compor_relatorio_caixa_dia`, `carregar_unidades`, `dia.isoformat`, `planilha_relatorio_caixa_dia`, `require_unit_access` | `int, date, bool, dict` → `Response` | Consulta; I/O local possível | I | [test_relatorio_caixa_dia.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_relatorio_caixa_dia.py); refs testes=1, UI=0; fonte AST |
| `GET /api/v1/cash-audit/recebimentos` | `router.obter_recebimentos` (L474) | `carregar_dia`, `carregar_unidades`, `conciliar_recebimentos`, `require_unit_access` | `int, date, dict` → `ResultadoRecebimentos` | Consulta; I/O local possível | I | [test_noturno.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_noturno.py); [test_recebimentos.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_recebimentos.py); refs testes=2, UI=0; fonte AST |
| `GET /api/v1/cash-audit/fechamento` | `router.obter_fechamento` (L492) | `' + '.join`, `Proveniencia`, `ResultadoAuditoria`, `_auditar_com_limite`, `agora`, `asyncio.get_running_loop`, `asyncio.get_running_loop().time`, `bloco.append`; +11 no fonte | `int, date, dict` → `dict` | Consulta; I/O local possível | I | [test_http.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_http.py); [test_noturno.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_noturno.py); refs testes=3, UI=0; fonte AST |
| `GET /api/v1/cash-audit/reincidencia` | `router.obter_reincidencia` (L562) | `adquirente.adquirente.upper`, `agora`, `agora().date`, `agregar_reincidencia`, `agregar_reincidencia(unidade, mes, dias, resultados, {codigo: nome for codigo, nome in nomes.items() if codigo in codigos}).model_dump`, `buscar_nomes_funcionarios`, `calendar.monthrange`, `carregar_dia`; +7 no fonte | `int, str, dict` → `dict` | Consulta; I/O local possível | I | [test_reincidencia.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_reincidencia.py); refs testes=1, UI=0; fonte AST |
| `GET /api/v1/cash-audit/unidades` | `router.listar_unidades` (L637) | `carregar_unidades`, `carregar_unidades().values`, `current_user.get` | `dict` → `list[dict[str, int  /  str]]` | Consulta; I/O local possível | I | [test_http.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_http.py); [test_auth_access.py](../../WebPosto_API/tests/unit/test_auth_access.py); refs testes=2, UI=0; fonte AST |
| `GET /api/v1/cash-audit/painel-diretor` | `router.obter_painel_diretor` (L647) | `_carregar_prazos_pendencia`, `_listar_pendencias_com_prazo`, `agora`, `agora().date`, `carregar_unidades`, `current_user.get`, `obter_unidades_painel`, `saude_robo.carregar_estado`; +1 no fonte | `dict` → `dict[str, object]` | Consulta; I/O local possível | I | [test_painel_diretor.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_painel_diretor.py); refs testes=1, UI=0; fonte AST |
| `GET /api/v1/cash-audit/pendencias/contagem-abertas` | `router.contar_pendencias_abertas` (L734) | `_escopo_pendencias`, `repositorio_pendencias.contar_abertas` | `dict` → `dict[str, int]` | Consulta; I/O local possível | I | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/cash-audit/pendencias` | `router.listar_pendencias` (L743) | `_carregar_prazos_pendencia`, `_escopo_pendencias`, `_listar_pendencias_com_prazo`, `agora` | `int  /  None, Literal['aberta', 'justificada', 'aprovada', 'recusada', 'todas'], str  /  None, bool, int, dict` → `dict[str, object]` | Consulta; I/O local possível | I | [test_pendencias.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py); refs testes=1, UI=0; fonte AST |
| `POST /api/v1/cash-audit/pendencias/{pendencia_id}/justificar` | `router.justificar_pendencia` (L778) | `_ler_pendencia`, `_serializar_pendencia`, `repositorio_pendencias.transicionar`, `require_unit_access` | `str, JustificativaPayload, dict` → `dict` | Interno/local ou dispara coleta | I | [test_pendencias.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py); refs testes=1, UI=0; fonte AST |
| `POST /api/v1/cash-audit/pendencias/{pendencia_id}/aprovar` | `router.aprovar_pendencia` (L842) | `DecisaoPayload`, `_decidir_pendencia` | `str, DecisaoPayload, dict` → `dict` | Interno/local ou dispara coleta | I | [test_pendencias.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py); refs testes=1, UI=0; fonte AST |
| `POST /api/v1/cash-audit/pendencias/{pendencia_id}/recusar` | `router.recusar_pendencia` (L851) | `DecisaoPayload`, `_decidir_pendencia` | `str, DecisaoPayload, dict` → `dict` | Interno/local ou dispara coleta | I | [test_pendencias.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_pendencias.py); refs testes=1, UI=0; fonte AST |

##### [WebPosto_API/src/modules/commercial_performance/interfaces/http.py](../../WebPosto_API/src/modules/commercial_performance/interfaces/http.py)

Domínio: **Comercial**. 3 declarações. Montagem: principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/v1/commercial/placar` | `router.consultar_placar` (L20) | `obter_placar`, `require_unit_access` | `int, str, date  /  None, dict` → `Placar` | Consulta; I/O local possível | I | [test_http.py](../../WebPosto_API/tests/unit/commercial_performance/test_http.py); [test_auth_access.py](../../WebPosto_API/tests/unit/test_auth_access.py); refs testes=2, UI=0; fonte AST |
| `GET /api/v1/commercial/postos` | `router.listar_postos` (L46) | `POSTOS.values`, `current_user.get` | `dict` → `list[dict[str, int  /  str]]` | Consulta; I/O local possível | I | [test_http.py](../../WebPosto_API/tests/unit/commercial_performance/test_http.py); [test_auth_access.py](../../WebPosto_API/tests/unit/test_auth_access.py); refs testes=2, UI=0; fonte AST |
| `GET /api/v1/commercial/painel-resumo` | `router.obter_resumo_painel` (L55) | `POSTOS.values`, `agora`, `agora().strftime`, `carregar_placar`, `contagens.items`, `contagens.values`, `current_user.get`, `zip` | `dict` → `dict[str, object]` | Consulta; I/O local possível | I | [test_http.py](../../WebPosto_API/tests/unit/commercial_performance/test_http.py); refs testes=1, UI=0; fonte AST |

##### [WebPosto_API/src/presentation/app.py](../../WebPosto_API/src/presentation/app.py)

Domínio: **Gateway/administração**. 23 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /health` | `app.gateway_health` (L658) | `_env`, `_resolve_chave`, `cache.stats`, `cache.stats().get`, `normalize_base`, `run_health_checks` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=2; fonte AST |
| `GET /internal/logs/recent` | `app.internal_logs_recent` (L668) | `recent_logs` | `int` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/dashboard/filtros` | `app.dashboard_filtros_meta` (L675) | `build_filtros_meta` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /dashboard` | `app.dashboard_executivo` (L680) | `FileResponse`, `p.is_file` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=3; fonte AST |
| `GET /produtos` | `app.pagina_produtos_crud` (L687) | `FileResponse`, `p.is_file` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=4; fonte AST |
| `GET /api/v1/proxy/{endpoint:path}` | `app.webposto_proxy_v1` (L694) | `_env`, `_resolve_chave`, `_wp_http_timeout`, `cache.cache_key`, `cache.get_json`, `cache.set_json`, `client.get`, `endpoint.strip`; +10 no fonte | `str, Request, Optional[str]` → `sem anotação` | GET ERP | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/adelaide/overview` | `app.get_adelaide_executive_overview` (L762) | `_adelaide_overview_impl` | `str, Optional[str], Optional[date], bool` → `AdelaideDashboardMetrics` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/adelaide/metrics/async` | `app.fetch_adelaide_metrics_async` (L797) | `JSONResponse`, `_adelaide_overview_impl`, `_work`, `background_tasks.add_task`, `create_job` | `BackgroundTasks, PeriodoMetricas, Optional[str], str, Optional[date], bool` → `sem anotação` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/jobs/{job_id}` | `app.get_async_job` (L842) | `get_job`, `rec.result.model_dump` | `str` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/adelaide/metrics` | `app.fetch_adelaide_metrics` (L867) | `_adelaide_overview_impl` | `PeriodoMetricas, Optional[str], str, Optional[date], bool` → `AdelaideDashboardMetrics` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=1; fonte AST |
| `GET /api/v1/webposto/grupos-produto` | `app.get_webposto_grupos_produto` (L907) | `GruposProdutoResponse.model_validate`, `GruposProdutoResponse.model_validate(cached).model_copy`, `WebPostoClient`, `WebPostoConfig`, `_env`, `_resolve_chave`, `cache.cache_key`, `cache.get_json`; +5 no fonte | `Optional[str]` → `GruposProdutoResponse` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=1; fonte AST |
| `GET /api/v1/webposto/produtos` | `app.get_webposto_produtos` (L971) | `(situacao or 'todos').strip`, `(situacao or 'todos').strip().lower`, `PaginatedProdutosResponse.model_validate`, `WebPostoClient`, `WebPostoConfig`, `_env`, `_parse_grupos_csv`, `_resolve_chave`; +9 no fonte | `int, Optional[str], Optional[int], str, bool` → `PaginatedProdutosResponse` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=1; fonte AST |
| `GET /api/v1/webposto/produtos/{produto_id}` | `app.get_webposto_produto_por_id` (L1103) | `_make_webposto_client`, `_resolve_chave`, `obter_produto` | `int, Optional[str]` → `WebPostoProdutoSchema` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/webposto/produtos` | `app.post_webposto_produto` (L1128) | `_make_webposto_client`, `_resolve_chave`, `criar_produto` | `ProdutoCreateRequest, Optional[str]` → `ProdutoCrudResponse` | Pode escrever ERP; ver seção 9 | L | Referência direta não localizada; refs testes=0, UI=1; fonte AST |
| `PUT /api/v1/webposto/produtos/{produto_id}` | `app.put_webposto_produto` (L1152) | `_make_webposto_client`, `_resolve_chave`, `atualizar_produto` | `int, ProdutoUpdateRequest, Optional[str]` → `ProdutoCrudResponse` | Pode escrever ERP; ver seção 9 | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/config` | `app.api_config` (L1175) | `(_env('WEBPOSTO_API_KEY') or _env('WEBPOSTO_CHAVE') or settings.webposto_api_key or '').strip`, `_env`, `cache.stats`, `normalize_base` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/health/webposto` | `app.health_webposto_key` (L1195) | `(_env('WEBPOSTO_API_KEY') or _env('WEBPOSTO_CHAVE') or settings.webposto_api_key).strip`, `_env`, `_wp_http_timeout`, `client.get`, `httpx.AsyncClient`, `normalize_base`, `time.perf_counter` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=1; fonte AST |
| `POST /api/webposto/proxy` | `app.webposto_proxy` (L1221) | `_env`, `_resolve_chave`, `_wp_http_timeout`, `cache.cache_key`, `cache.get_json`, `cache.set_json`, `client.get`, `client.post`; +11 no fonte | `ProxyBody` → `sem anotação` | ERP GET/POST/PUT/PATCH/DELETE | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/executive/kpis` | `app.executive_kpis` (L1288) | `ExecutiveKpiSummary`, `FetchExecutiveKpisRequest`, `WebPostoClient`, `WebPostoConfig`, `_env`, `decode_token`, `decode_token(token).get`, `empty.model_dump`; +5 no fonte | `str, Request` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/cache/stats` | `app.cache_stats` (L1349) | `cache.stats` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /` | `app.dashboard_root` (L1354) | `FileResponse`, `p.is_file` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /app/vendas` | `app.dashboard_vendas` (L1361) | `dashboard_root` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api_hub_catalog.js` | `app.catalog_js` (L1375) | `FileResponse` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/presentation/routes/audit_routes.py](../../WebPosto_API/src/presentation/routes/audit_routes.py)

Domínio: **Auditoria**. 3 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `POST /v1/audit/process` | `router.process_audit` (L53) | `(os.getenv('WEBPOSTO_API_KEY') or os.getenv('WEBPOSTO_CHAVE') or '').strip`, `(posto_id or 'default').strip`, `AuditProcessResponse`, `AuditProcessResponse(job_id=job_id, poll_url=f'/v1/audit/jobs/{job_id}').model_dump`, `JSONResponse`, `_parse_filial_csv`, `background_tasks.add_task`, `create_audit_job`; +1 no fonte | `BackgroundTasks, date, SubCentroCusto, Optional[str]` → `sem anotação` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=1; fonte AST |
| `GET /v1/audit/faturamento` | `router.get_faturamento_subcentros` (L92) | `(os.getenv('WEBPOSTO_API_KEY') or os.getenv('WEBPOSTO_CHAVE') or '').strip`, `(posto_id or 'default').strip`, `FetchFaturamentoSubCentrosUseCase`, `_audit_http_error`, `_make_gateway`, `_parse_filial_csv`, `os.getenv`, `uc.execute` | `date, Optional[str]` → `FaturamentoConsolidadoResponse` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /v1/audit/jobs/{job_id}` | `router.get_audit_job` (L123) | `load_job_state` | `str` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [WebPosto_API/src/presentation/routes/health.py](../../WebPosto_API/src/presentation/routes/health.py)

Domínio: **Saúde**. 2 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /ready` | `router.ready` (L57) | Handler direto | `sem anotação` → `dict[str, str]` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=0; fonte AST |
| `GET /health` | `router.health` (L62) | `(database_url or '').lower`, `RuntimeError`, `_cached_probe`, `_sqlite_db_path`, `conn.execute`, `engine.connect`, `os.getenv`, `text` | `sem anotação` → `dict[str, str]` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=2; fonte AST |

##### [WebPosto_API/src/routes_crud.py](../../WebPosto_API/src/routes_crud.py)

Domínio: **Gateway/administração**. 11 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/v1/financeiro` | `router.listar_financeiro` (L43) | `FinanceiroCRUD.listar`, `ListaResponse` | `Request, int, Optional[str], str` → `ListaResponse` | Leitura DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/financeiro/{titulo_id}` | `router.obter_financeiro` (L86) | `APIResponse`, `FinanceiroCRUD.obter_por_id` | `str` → `APIResponse` | Leitura DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/financeiro` | `router.criar_financeiro` (L105) | `APIResponse`, `FinanceiroCRUD.criar`, `get_client_ip`, `get_usuario`, `request.headers.get` | `Request, FinanceiroCreate` → `APIResponse` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `PUT /api/v1/financeiro/{titulo_id}` | `router.atualizar_financeiro` (L142) | `APIResponse`, `FinanceiroCRUD.atualizar`, `get_client_ip`, `get_usuario`, `request.headers.get` | `Request, str, FinanceiroUpdate` → `APIResponse` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `DELETE /api/v1/financeiro/{titulo_id}` | `router.deletar_financeiro` (L178) | `APIResponse`, `FinanceiroCRUD.deletar`, `get_client_ip`, `get_usuario`, `request.headers.get` | `Request, str` → `APIResponse` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/caixa` | `router.listar_caixa` (L206) | `CaixaCRUD.listar`, `ListaResponse` | `Request, int, Optional[int], Optional[str]` → `ListaResponse` | Leitura DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/caixa/{movimento_id}` | `router.obter_caixa` (L249) | `APIResponse`, `CaixaCRUD.obter_por_id` | `str` → `APIResponse` | Leitura DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/v1/caixa` | `router.criar_caixa` (L268) | `APIResponse`, `CaixaCRUD.criar`, `get_client_ip`, `get_usuario` | `Request, CaixaCreate` → `APIResponse` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `PUT /api/v1/caixa/{movimento_id}` | `router.atualizar_caixa` (L304) | `APIResponse`, `CaixaCRUD.atualizar`, `get_client_ip`, `get_usuario`, `request.headers.get` | `Request, str, CaixaUpdate` → `APIResponse` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `DELETE /api/v1/caixa/{movimento_id}` | `router.deletar_caixa` (L339) | `APIResponse`, `CaixaCRUD.deletar`, `get_client_ip`, `get_usuario`, `request.headers.get` | `Request, str` → `APIResponse` | Escrita DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/v1/auditoria` | `router.listar_auditoria` (L367) | `AuditoriaCRUD.listar`, `ListaResponse` | `Request, int, Optional[str]` → `ListaResponse` | Leitura DB local | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [servicos_auditoria.py](../../servicos_auditoria.py)

Domínio: **Auditoria**. 6 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /auditoria/despesas/{unidade_id}` | `app.get_despesas_unidade` (L192) | `AuditoriaService.extrair_despesas_por_unidade`, `_http_from_integration_exc`, `_parse_data_opcional` | `int, Optional[str]` → `List[DespesaCaixa]` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/fechamentos/{unidade_id}` | `app.get_fechamentos_unidade` (L206) | `AuditoriaService.calcular_resumo_unidade`, `AuditoriaService.extrair_despesas_por_unidade`, `AuditoriaService.extrair_fechamentos`, `ListaFechamentos`, `_http_from_integration_exc`, `_parse_data_opcional`, `datetime.now` | `int, Optional[str]` → `ListaFechamentos` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/resumo/{unidade_id}` | `app.get_resumo_auditoria` (L228) | `AuditoriaService.calcular_resumo_unidade`, `AuditoriaService.extrair_despesas_por_unidade`, `AuditoriaService.extrair_fechamentos`, `_http_from_integration_exc`, `_parse_data_opcional` | `int, Optional[str]` → `ResumoAuditoriaUnidade` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/despesas-por-categoria/{unidade_id}` | `app.get_despesas_categorizado` (L243) | `AuditoriaService.extrair_despesas_por_unidade`, `_http_from_integration_exc`, `_parse_data_opcional` | `int, Optional[str]` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /auditoria/registrar-despesa` | `app.registrar_despesa` (L267) | `_http_from_integration_exc`, `webposto_client.registrar_despesa` | `DespesaCaixa` → `DespesaCaixa` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /auditoria/health` | `app.health` (L277) | Handler direto | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=0; fonte AST |

##### [src/api/app.py](../../src/api/app.py)

Domínio: **Gateway/administração**. 4 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /health` | `app.health` (L267) | `JSONResponse`, `health_status.check` | `sem anotação` → `dict` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=2; fonte AST |
| `GET /ready` | `app.readiness` (L282) | `health_status.check` | `sem anotação` → `dict` | Consulta; I/O local possível | L | [test_health.py](../../WebPosto_API/logos-webposto-gateway/tests/test_health.py); [test_presentation.py](../../WebPosto_API/logos-webposto-gateway/tests/test_presentation.py); refs testes=2, UI=0; fonte AST |
| `GET /version` | `app.version` (L301) | `__import__`, `__import__('os').getenv` | `sem anotação` → `dict` | Consulta; I/O local possível | L | [test_noturno.py](../../WebPosto_API/tests/unit/cash_reconciliation/test_noturno.py); [frontend_integration_test.py](../../tests/frontend_integration_test.py); refs testes=3, UI=0; fonte AST |
| `POST /api/adelaide/run` | `app.run_adelaide` (L320) | `(product.ncm or '').startswith`, `AdelaideEngine`, `ProductAuditInput`, `SqlAlchemyTaxMatrixRepository`, `TaxContext`, `_default_products`, `_runner`, `asyncio.create_task`; +12 no fonte | `AdelaideRunRequest, SqlAlchemyTaxMatrixRepository` → `dict` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [src/infrastructure/sse.py](../../src/infrastructure/sse.py)

Domínio: **Eventos**. 2 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/stream` | `router.stream` (L44) | `StreamingResponse`, `event_generator`, `request.is_disconnected`, `streamer` | `Request` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/adelaide/stream/{job_id}` | `router.adelaide_stream` (L55) | `StreamingResponse`, `job_event_generator`, `request.is_disconnected`, `streamer` | `str, Request` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [src/interfaces/http/routes/metrics_api.py](../../src/interfaces/http/routes/metrics_api.py)

Domínio: **Métricas**. 3 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /api/metrics/stream` | `router.metrics_stream` (L37) | `StreamingResponse`, `sse_generator` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /api/metrics/publish` | `router.metrics_publish` (L43) | `JSONResponse`, `aioredis.from_url`, `audit_writer`, `json.dumps`, `payload.get`, `r.close`, `r.publish` | `dict` → `sem anotação` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `GET /api/margins` | `router.get_margins` (L57) | `JSONResponse`, `aioredis.from_url`, `compute_rateio`, `json.dumps`, `json.loads`, `r.close`, `r.get`, `r.set` | `str` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |

##### [src/interfaces/http/routes/tax_api.py](../../src/interfaces/http/routes/tax_api.py)

Domínio: **Fiscal**. 3 declarações. Montagem: alternativa/exemplo/não principal.

| Método / path | Router / função | Serviços / chamadas | Request → response | Efeito | Status | Testes / evidência de uso |
|---|---|---|---|---|---|---|
| `GET /tax/sync/stream` | `router.tax_sync_stream` (L34) | `StreamingResponse`, `sse_sync_generator` | `sem anotação` → `sem anotação` | Consulta; I/O local possível | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /tax/enqueue` | `router.tax_enqueue` (L39) | `JSONResponse`, `aioredis.from_url`, `json.dumps`, `r.close`, `r.rpush` | `List[dict]` → `sem anotação` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |
| `POST /tax/homologate` | `router.tax_homologate` (L51) | `JSONResponse`, `aioredis.from_url`, `r.close`, `r.sadd` | `List[str]` → `sem anotação` | Interno/local ou dispara coleta | L | Referência direta não localizada; refs testes=0, UI=0; fonte AST |


## 3. Cobertura webPosto

### Clientes e wrappers atuais

| Família | Arquivo / componente | Uso atual | Classificação / limite |
|---|---|---|---|
| V1 compartilhado | [webposto_integration/http.py](../../WebPosto_API/src/modules/webposto_integration/http.py): paginar | Caixa e comercial; CHAVE por unidade, cursor ultimoCodigo | V para os GET comprovados; sem retry automático, erro explícito |
| V1 de domínio | [adapters](../../WebPosto_API/src/modules/cash_reconciliation/adapters): caixas, cartões, sangrias, detalhes | Coleta vertical, filtro adicional por unidade/caixa | V no escopo das conferências; escrita isolada em outros adapters |
| Gateway enterprise | [gateway/webposto_client.py](../../WebPosto_API/src/gateway/webposto_client.py): WebPostoClient | Serviços analytics/finance/stock/LMC | P; mapa de endpoints legados, circuit breaker/cache de permissões/retry |
| SDK síncrono | [webposto/client.py](../../WebPosto_API/src/webposto/client.py), [http.py](../../WebPosto_API/src/webposto/http.py) | Catálogo, audit gateway, wrappers de sete grupos | P; 43 GET e 36 chamadas de escrita explícitas nos grupos; não tem trava global |
| AuditGateway ACL | [clients/webposto_client.py](../../WebPosto_API/src/infrastructure/clients/webposto_client.py): WebPostoAuditClient | Auditoria alternativa por subcentro | P; empacota SDK em thread, não é novo protocolo V1 |
| PostoGateway | [posto_client_v1.py](../../WebPosto_API/src/infrastructure/clients/posto_client_v1.py): PostoAPIClient | Usecases executivos/produtos | P; apesar do nome, chama VENDA/ESTOQUE/PRODUTO legados |
| Despesas gateway | [gateway_webposto_client.py](../../WebPosto_API/src/infrastructure/clients/gateway_webposto_client.py) | /v1/expenses | L; fallback de FINANCEIRO para abastecimentos não equivale a despesas |
| REST alternativo | [infrastructure/webposto/client.py](../../WebPosto_API/src/infrastructure/webposto/client.py) | SyncService e minimal | L; paths /api/v1/* não correspondem ao contrato /INTEGRACAO/V1 |
| Gateway aninhado e árvores da raiz | [logos-webposto-gateway](../../WebPosto_API/logos-webposto-gateway), [webposto_client.py](../../webposto_client.py), [webposto](../../webposto), [api_webposto](../../api_webposto) | Aplicações/compatibilidade separadas | L; não inferir uso na composição principal pela presença |

### Endpoints dinâmicos do gateway enterprise

Os **26 aliases** de `gateway/webposto_client.py::ENDPOINTS` complementam os
literais do apêndice B. `call_endpoint` usa GET; estes aliases não constam com
esses mesmos paths no contrato fornecido. Não equivale a API inexistente: são
rotas legadas, cuja tradução para V1 precisa ser conferida.

| Alias atual | Path legado | Capacidade / alcance |
|---|---|---|
| abastecimento | /INTEGRACAO/ABASTECIMENTO | Abastecimentos |
| financeiro | /INTEGRACAO/TITULO_PAGAR | Financeiro aqui significa título a pagar |
| titulo_receber | /INTEGRACAO/TITULO_RECEBER | Recebíveis |
| movimento_conta | /INTEGRACAO/MOVIMENTO_CONTA | Movimentos financeiros |
| transferencia_bancaria | /INTEGRACAO/TRANSFERENCIA_BANCARIA | Transferências |
| caixa | /INTEGRACAO/CAIXA | Caixa legado |
| caixa_apresentado | /INTEGRACAO/CAIXA_APRESENTADO | Modalidades apresentadas |
| analise_vendas_combustivel | /INTEGRACAO/CONSULTAR_ANALISE_VENDAS_COMBUSTIVEL | Analytics de combustível |
| despesas_financeiro_rede | /INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE | Despesas multiempresa |
| empresas | /INTEGRACAO/EMPRESAS | Empresas |
| conta | /INTEGRACAO/CONTA | Contas |
| venda | /INTEGRACAO/VENDA | Cabeçalho de venda |
| venda_item | /INTEGRACAO/VENDA_ITEM | Itens |
| venda_item_rede | /INTEGRACAO/CONSULTAR_VENDA_ITEM_REDE | Itens multiempresa |
| venda_forma_pagamento | /INTEGRACAO/VENDA_FORMA_PAGAMENTO | Formas por venda |
| venda_forma_pagamento_rede | /INTEGRACAO/CONSULTAR_VENDA_FORMA_PAGAMENTO_REDE | Formas multiempresa |
| nfce | /INTEGRACAO/NFCE | Fiscal |
| produto_estoque | /INTEGRACAO/PRODUTO_ESTOQUE | Estoque de produto |
| produto | /INTEGRACAO/PRODUTO | Cadastro |
| produto_empresa | /INTEGRACAO/PRODUTO_EMPRESA | Cadastro por empresa |
| produto_rede | /INTEGRACAO/PRODUTO_REDE | Cadastro multiempresa |
| produto_empresa_rede | /INTEGRACAO/PRODUTO_EMPRESA_REDE | Cadastro por empresa/rede |
| produto_combustivel | /INTEGRACAO/PRODUTO_COMBUSTIVEL | Combustível |
| tanque | /INTEGRACAO/TANQUE | Cadastro/saldo de tanque legado |
| estoque_periodo | /INTEGRACAO/ESTOQUE_PERIODO | Estoque por período |
| lmc_rede | /INTEGRACAO/CONSULTAR_LMC_REDE | LMC multiempresa |

Classe da família: **P**. Existência de alias não prova que cada consulta está
ativa ou foi conferida; consumidores principais são analytics/financial overview/
fuel analytics. Não há aliases CARTAO/COMPRA/COMPRA_ITEM no gateway enterprise
atual, embora existam no gateway da versão anterior.

### Matriz das capacidades prioritárias

V1 abaixo significa prefixo `/INTEGRACAO/V1/`; “não validada” não significa que
o endpoint não funciona, apenas ausência de prova suficiente para a capacidade.
Clientes genéricos capazes de receber qualquer path não contam como integração.

| Capacidade | OpenAPI | Código atual | Em uso | Validada | Gap |
|---|---|---|---|---|---|
| VENDAS | GET V1/VENDAS, VendaRede | webposto_cartoes; gateway VENDA legado | Caixa + analytics | V no contexto caixa | Equivalência legada e todos os setores não certificadas |
| VENDAS/ITENS | GET, VendaItemRede | webposto_cartoes + comercial; gateway VENDA_ITEM | Sim | V no vínculo abastecimento/venda | Item de loja e estoque ainda P |
| VENDAS_FORMA_PAGAMENTO | GET, VendaFormaPagamentoRede | webposto_cartoes + gateway legado | Sim | V no caso de caixa | Pagamento dividido e múltiplas formas exigem testes de atribuição |
| CARTOES | GET/POST; DELETE/PATCH por id | Leitura e piloto POST/DELETE | Sim | V leitura; P escrita | Não há confirmação real bem-sucedida; PATCH não implementado no piloto |
| ADMINISTRADORAS | GET V1 | piloto / fontes_falta; SDK singular legado | Sim | V leitura no caso 19 | PIX real sem NSU/autorização não lançável |
| CAIXAS | GET V1 | webposto_caixas | Sim | V | Acesso por empresa e data; rótulo compartilhado |
| CAIXAS_APRESENTADO | GET V1 | webposto_caixas | Sim | V | Filtro local por caixas autorizados; não assume filtro empresa na resposta |
| SANGRIAS_CAIXA | GET V1 | webposto_sangrias | Sim | V | Conta destino não é saldo físico de cofre |
| FUNCIONARIOS | GET V1 | webposto_integration/funcionarios | Sim | V | Não expor documento/contato; identfid não prova operador humano sem vínculo |
| PRODUTOS | GET/POST V1, PUT por id | comercial usa V1; SDK/gateway singular | Sim | V leitura comercial | Escrita/catálogo empresarial de todas as unidades não validados |
| PRODUTOS_EMPRESA | GET V1 | PRODUTO_EMPRESA legado em SDK/gateway | Sim, versão legada | P | Falta adapter V1 específico e conferência equivalência |
| PRODUTOS_ESTOQUES | GET V1 | PRODUTO_ESTOQUE legado no gateway | Sim, versão legada | P | Unidade, estoque e saldo precisam de validação |
| PRODUTOS_ESTOQUE_EXTRATO | GET V1 e V2 | Sem adapter correspondente localizado | Não | A | Histórico diário está no contrato, não na coleta auditável |
| ESTOQUES_PERIODO | GET V1 | ESTOQUE_PERIODO legado no gateway | Sim, versão legada | P | Falta prova de equivalência/saldo por instante |
| CONTAGEM_ESTOQUES | GET V1, ContagemEstoqueRede | Sem coleta dedicada | Não | A | Contagem -> notas -> itens e instante de referência |
| COMPRAS | Nome literal ausente | SDK NOTA_FISCAL_ENTRADA/PEDIDO_COMPRAS | Parcial | P | Reusar V1/NOTAS_ENTRADA, não inventar /V1/COMPRAS |
| COMPRA_ITENS | Nome literal ausente | Sem adapter V1 de itens de entrada | Não | A | Contrato correspondente: V1/NOTAS_ENTRADA/ITENS, compraCodigo |
| FORNECEDORES | GET/POST V1 | GET em baixa/despesas | Sim | P | Cadastro real conferido de ponta a ponta não localizado |
| NFCES | GET V1 + XML por id | Gateway NFCE legado | Sim na família financeira | P | Situação fiscal não valida sozinho cancelamento operacional/estoque |
| TITULOS_PAGAR | GET/POST, PATCH PAGAR, DELETE id | GET baixa/despesas e SDK legado POST | Sim, leitura | P | Baixa real não é implementada pelo job de candidatos |
| TITULOS_RECEBER | GET/POST V1 | Gateway/SDK singular legado | Sim, versão legada | P | Não confundir CRUD local com lançamento ERP |
| MOVIMENTOS_CONTA | GET/POST/PATCH V1 | GET despesas; gateway MOVIMENTO_CONTA legado | Sim, leitura | P | Não há writer V1 específico identificado para despesas avulsas |
| CONTAS | GET V1 | Resolução em configuração; gateway CONTA legado | Sim | V para destinos de sangria; P financeiro geral | Não usar conta de cofre ERP como verdade física |
| VALES | Nome literal ausente | V1/VALES_FUNCIONARIO em webposto_detalhes | Sim | V | Tipos/origens de vale e responsabilidade não intercambiáveis |
| ABASTECIMENTOS | GET V1 | Cartões + comercial; SDK legado | Sim | V | Dois parsers de aferição com tratamentos distintos |
| ABASTECIMENTOS_ENCERRANTE | GET array AbastecimentoEncerrante | SDK singular legado listar_encerrante | Wrapper antigo | P | V1 retorna array, não envelope com cursor; bico string/idVenda pedem conferência |
| BICOS | GET V1 | Não localizado adapter V1 | Não | A | Cadastro bicoNumero/bicoCodigo/bombaCodigo/tanqueCodigo |
| BOMBAS | GET V1 | Não localizado adapter V1 | Não | A | Identidade e histórico de equipamento |
| TANQUES | GET V1 | Gateway TANQUE legado e PostoGateway ESTOQUE | Parcial | P | Estoque agregado não substitui medição física |
| TANQUE_MEDIDA | GET array e POST V1 | Sem adapter dedicado | Não | A | dataMedida/horaMedida/volume; POST não autorizado |
| TANQUE_ENTRADA | GET array V1 | Sem adapter dedicado | Não | A | Janela de descarga e volumes de início/fim |
| LMCS | GET V1 + LMCS_REDE | SDK LMC, gateway CONSULTAR_LMC_REDE | Sim, legado | P | Não é auditoria física; arrays lmcBico/lmcTanque/lmcNota |

O apêndice B lista todos os wrappers com chamada literal identificada, além das
famílias dinâmicas explicitadas acima. Ausência de GET V1 específico é distinguida
de ausência total de capacidade legada.

#### Apêndice B — 176 chamadas com path /INTEGRACAO literal

Inclui chamadas em adapters, wrappers, scripts e árvores alternativas; não são 176 endpoints distintos. Métodos/path dinâmicos e mapas de constants são complementados pela tabela de clientes e escritores. “Não inferido” evita classificar verbo pelo nome da função. Paths f-string preservam o placeholder; comparação exata não presume equivalência semântica.

| Arquivo / função / linha | Chamada | Path | Correspondência no contrato fornecido |
|---|---|---|---|
| [WebPosto_API/INSPECIONAR_API.py](../../WebPosto_API/INSPECIONAR_API.py) · `main` L54 | `get` (GET) | `/INTEGRACAO/ABASTECIMENTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/INSPECIONAR_API.py](../../WebPosto_API/INSPECIONAR_API.py) · `main` L61 | `get` (GET) | `/INTEGRACAO/FINANCEIRO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/INSPECIONAR_API.py](../../WebPosto_API/INSPECIONAR_API.py) · `main` L68 | `get` (GET) | `/INTEGRACAO/CAIXA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/INSPECIONAR_API.py](../../WebPosto_API/INSPECIONAR_API.py) · `main` L75 | `get` (GET) | `/INTEGRACAO/TITULOS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/INSPECIONAR_API.py](../../WebPosto_API/INSPECIONAR_API.py) · `main` L82 | `get` (GET) | `/INTEGRACAO/VENDAS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/INSPECIONAR_API.py](../../WebPosto_API/INSPECIONAR_API.py) · `main` L89 | `get` (GET) | `/INTEGRACAO/PRODUTOS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L209 | `testar` (Não inferido) | `/INTEGRACAO/FILIAL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L234 | `testar` (Não inferido) | `/INTEGRACAO/USUARIO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L237 | `testar` (Não inferido) | `/INTEGRACAO/ADMINISTRADORA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L242 | `testar` (Não inferido) | `/INTEGRACAO/ABASTECIMENTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L251 | `testar` (Não inferido) | `/INTEGRACAO/ABASTECIMENTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L260 | `testar` (Não inferido) | `/INTEGRACAO/ABASTECIMENTO_ENCERRANTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L269 | `testar` (Não inferido) | `/INTEGRACAO/ABASTECIMENTO_DIVERGENCIA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L278 | `testar` (Não inferido) | `/INTEGRACAO/PEDIDO_COMBUSTIVEL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L287 | `testar` (Não inferido) | `/INTEGRACAO/LMC` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L299 | `testar` (Não inferido) | `/INTEGRACAO/VENDA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L308 | `testar` (Não inferido) | `/INTEGRACAO/VENDA_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L317 | `testar` (Não inferido) | `/INTEGRACAO/TITULO_RECEBER` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L326 | `testar` (Não inferido) | `/INTEGRACAO/TITULO_PAGAR` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L335 | `testar` (Não inferido) | `/INTEGRACAO/CAIXA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L344 | `testar` (Não inferido) | `/INTEGRACAO/TRANSFERENCIA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L353 | `testar` (Não inferido) | `/INTEGRACAO/ADIANTAMENTO_FORNECEDOR` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L365 | `testar` (Não inferido) | `/INTEGRACAO/CLIENTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L374 | `testar` (Não inferido) | `/INTEGRACAO/VEICULO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L383 | `testar` (Não inferido) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L392 | `testar` (Não inferido) | `/INTEGRACAO/COMBUSTIVEL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L396 | `testar` (Não inferido) | `/INTEGRACAO/PRECO_PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L398 | `testar` (Não inferido) | `/INTEGRACAO/ESTOQUE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L403 | `testar` (Não inferido) | `/INTEGRACAO/NOTA_FISCAL_ENTRADA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L412 | `testar` (Não inferido) | `/INTEGRACAO/NOTA_FISCAL_SAIDA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L421 | `testar` (Não inferido) | `/INTEGRACAO/PEDIDO_COMPRAS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/diagnostico_api.py](../../WebPosto_API/diagnostico_api.py) · `main` L221 | `testar` (Não inferido) | `/INTEGRACAO/FILIAL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/logos-webposto-gateway/src/application/fetch_products.py](../../WebPosto_API/logos-webposto-gateway/src/application/fetch_products.py) · `execute` L43 | `os.getenv` (Não inferido) | `/INTEGRACAO/PRODUTOS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/logos-webposto-gateway/src/infrastructure/bootstrap.py](../../WebPosto_API/logos-webposto-gateway/src/infrastructure/bootstrap.py) · `run_initial_vip_sync_pipeline` L79 | `os.getenv` (Não inferido) | `/INTEGRACAO/PRODUTOS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_a03_6_full.py](../../WebPosto_API/scripts/audit_a03_6_full.py) · `main_async` L645 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_a03_7_corporate_finance.py](../../WebPosto_API/scripts/audit_a03_7_corporate_finance.py) · `main_async` L616 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_a03_7_corporate_finance.py](../../WebPosto_API/scripts/audit_a03_7_corporate_finance.py) · `main_async` L626 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/MOVIMENTO_CONTA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_a03_7_corporate_finance.py](../../WebPosto_API/scripts/audit_a03_7_corporate_finance.py) · `main_async` L636 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/TRANSFERENCIA_BANCARIA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_a03_7_corporate_finance.py](../../WebPosto_API/scripts/audit_a03_7_corporate_finance.py) · `main_async` L662 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/TITULO_RECEBER` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_a03_7_corporate_finance.py](../../WebPosto_API/scripts/audit_a03_7_corporate_finance.py) · `main_async` L672 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/TITULO_PAGAR` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_a03_7_corporate_finance.py](../../WebPosto_API/scripts/audit_a03_7_corporate_finance.py) · `main_async` L648 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/{path}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_cobertura_real.py](../../WebPosto_API/scripts/audit_cobertura_real.py) · `main` L17 | `print` (Não inferido) | `=== TESTANDO /INTEGRACAO/EMPRESAS ===` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_cobertura_real.py](../../WebPosto_API/scripts/audit_cobertura_real.py) · `main` L35 | `print` (Não inferido) | `Códigos retornados na API real (/INTEGRACAO/EMPRESAS): {raw_codes}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_expense_intelligence_f01_3.py](../../WebPosto_API/scripts/audit_expense_intelligence_f01_3.py) · `main` L36 | `client.get` (GET) | `{cfg.webposto_base_url}/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_outros_expenses.py](../../WebPosto_API/scripts/audit_outros_expenses.py) · `main` L34 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_plano_contas_lineage_f01_4a.py](../../WebPosto_API/scripts/audit_plano_contas_lineage_f01_4a.py) · `main` L102 | `_fetch` (Não inferido) | `/INTEGRACAO/PLANO_CONTA_GERENCIAL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_plano_contas_lineage_f01_4a.py](../../WebPosto_API/scripts/audit_plano_contas_lineage_f01_4a.py) · `main` L106 | `_fetch` (Não inferido) | `/INTEGRACAO/CENTRO_CUSTO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_plano_contas_lineage_f01_4a.py](../../WebPosto_API/scripts/audit_plano_contas_lineage_f01_4a.py) · `main` L119 | `client.get` (GET) | `{cfg.webposto_base_url}/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_specific_companies.py](../../WebPosto_API/scripts/audit_specific_companies.py) · `run_audit` L28 | `print` (Não inferido) | `Target companies found in /INTEGRACAO/EMPRESAS: {found_in_empresas}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_specific_companies.py](../../WebPosto_API/scripts/audit_specific_companies.py) · `run_audit` L29 | `print` (Não inferido) | `All codes in /INTEGRACAO/EMPRESAS: {[r.get('empresaCodigo') or r.get('codigo') for r in rows]}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_specific_companies.py](../../WebPosto_API/scripts/audit_specific_companies.py) · `run_audit` L31 | `print` (Não inferido) | `Failed to fetch /INTEGRACAO/EMPRESAS: {empresas_resp.error}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/audit_webposto_rede_endpoints.py](../../WebPosto_API/scripts/audit_webposto_rede_endpoints.py) · `run_detailed_audit` L196 | `path.replace` (Não inferido) | `/INTEGRACAO/` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/build_account_category_mapping.py](../../WebPosto_API/scripts/build_account_category_mapping.py) · `main` L37 | `client.get` (GET) | `{cfg.webposto_base_url}/INTEGRACAO/PLANO_CONTA_GERENCIAL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/build_account_category_mapping.py](../../WebPosto_API/scripts/build_account_category_mapping.py) · `main` L46 | `client.get` (GET) | `{cfg.webposto_base_url}/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/financial_origin_mapping.py](../../WebPosto_API/scripts/financial_origin_mapping.py) · `write_financial_model_md` L472 | `lines.append` (Não inferido) | `- Campos esperados ('valorSangria', 'sangria') **ausentes** em '/INTEGRACAO/CAIXA' — apenas 'diferenca', 'apurado', 'fechamento'.` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/financial_origin_mapping.py](../../WebPosto_API/scripts/financial_origin_mapping.py) · `run_audit` L584 | `client.get` (GET) | `{config.webposto_base_url}/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts/validate_f01_4a_classification_v3.py](../../WebPosto_API/scripts/validate_f01_4a_classification_v3.py) · `main` L27 | `client.get` (GET) | `{cfg.webposto_base_url}/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/scripts_export_hub_catalog.py](../../WebPosto_API/scripts_export_hub_catalog.py) · `main` L75 | `p.startswith` (Não inferido) | `/INTEGRACAO/` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/application/usecases/fetch_produto_grupos.py](../../WebPosto_API/src/application/usecases/fetch_produto_grupos.py) · `_indexar_produtos_por_grupo` L95 | `webposto_client._http.get` (GET) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/application/usecases/fetch_produto_grupos.py](../../WebPosto_API/src/application/usecases/fetch_produto_grupos.py) · `fetch_codigos_produtos_grupos` L136 | `webposto_client._http.get` (GET) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/application/usecases/fetch_unidade_webposto.py](../../WebPosto_API/src/application/usecases/fetch_unidade_webposto.py) · `fetch_unidade_webposto` L31 | `asyncio.to_thread` (Não inferido) | `/INTEGRACAO/EMPRESAS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/gateway_webposto_client.py](../../WebPosto_API/src/infrastructure/clients/gateway_webposto_client.py) · `fetch_expenses` L39 | `client.get` (GET) | `/INTEGRACAO/FINANCEIRO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/gateway_webposto_client.py](../../WebPosto_API/src/infrastructure/clients/gateway_webposto_client.py) · `fetch_expenses` L42 | `client.get` (GET) | `/INTEGRACAO/ABASTECIMENTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/posto_client_v1.py](../../WebPosto_API/src/infrastructure/clients/posto_client_v1.py) · `get_vendas_recentes` L57 | `self._get_json` (GET) | `/INTEGRACAO/VENDA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/posto_client_v1.py](../../WebPosto_API/src/infrastructure/clients/posto_client_v1.py) · `get_volume_tanques` L69 | `self._get_json` (GET) | `/INTEGRACAO/ESTOQUE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/posto_client_v1.py](../../WebPosto_API/src/infrastructure/clients/posto_client_v1.py) · `get_produto` L73 | `self._get_json` (GET) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/posto_client_v1.py](../../WebPosto_API/src/infrastructure/clients/posto_client_v1.py) · `get_produto` L80 | `self._get_json` (GET) | `/INTEGRACAO/PRODUTO_EMPRESA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/posto_client_v1.py](../../WebPosto_API/src/infrastructure/clients/posto_client_v1.py) · `listar_produtos` L94 | `self._get_json` (GET) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/posto_client_v1.py](../../WebPosto_API/src/infrastructure/clients/posto_client_v1.py) · `listar_filiais` L101 | `self._get_json` (GET) | `/INTEGRACAO/EMPRESAS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/infrastructure/clients/posto_client_v1.py](../../WebPosto_API/src/infrastructure/clients/posto_client_v1.py) · `get_caixa_periodo` L105 | `self._get_json` (GET) | `/INTEGRACAO/CAIXA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py) · `buscar_cartoes` L70 | `paginar` (GET) | `/INTEGRACAO/V1/CARTOES` | /INTEGRACAO/V1/CARTOES [GET, POST] |
| [WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py) · `buscar_abastecimentos` L75 | `paginar` (GET) | `/INTEGRACAO/V1/ABASTECIMENTOS` | /INTEGRACAO/V1/ABASTECIMENTOS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py) · `buscar_contexto_vendas` L163 | `paginar` (GET) | `/INTEGRACAO/V1/VENDAS/ITENS` | /INTEGRACAO/V1/VENDAS/ITENS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py) · `buscar_contexto_vendas` L164 | `paginar` (GET) | `/INTEGRACAO/V1/VENDAS_FORMA_PAGAMENTO` | /INTEGRACAO/V1/VENDAS_FORMA_PAGAMENTO [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py) · `buscar_contexto_vendas` L165 | `paginar` (GET) | `/INTEGRACAO/V1/VENDAS` | /INTEGRACAO/V1/VENDAS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py) · `buscar_contexto_vendas` L184 | `paginar` (GET) | `/INTEGRACAO/V1/CAIXAS` | /INTEGRACAO/V1/CAIXAS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py) · `enviar_ofx_webposto` L524 | `paginar` (GET) | `/INTEGRACAO/V1/CONTAS` | /INTEGRACAO/V1/CONTAS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py](../../WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py) · `identificar_despesas_sem_lancamento` L358 | `paginar` (GET) | `/INTEGRACAO/V1/TITULOS_PAGAR` | /INTEGRACAO/V1/TITULOS_PAGAR [GET, POST] |
| [WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py](../../WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py) · `identificar_despesas_sem_lancamento` L400 | `paginar` (GET) | `/INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL` | /INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py](../../WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py) · `identificar_despesas_sem_lancamento` L414 | `paginar` (GET) | `/INTEGRACAO/V1/CENTROS_CUSTO` | /INTEGRACAO/V1/CENTROS_CUSTO [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py](../../WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py) · `identificar_despesas_sem_lancamento` L428 | `paginar` (GET) | `/INTEGRACAO/V1/FORNECEDORES` | /INTEGRACAO/V1/FORNECEDORES [GET, POST] |
| [WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py](../../WebPosto_API/src/modules/cash_reconciliation/application/despesas_sem_lancamento.py) · `identificar_despesas_sem_lancamento` L385 | `paginar` (GET) | `/INTEGRACAO/V1/MOVIMENTOS_CONTA` | /INTEGRACAO/V1/MOVIMENTOS_CONTA [GET, POST, PATCH] |
| [WebPosto_API/src/modules/cash_reconciliation/application/fontes_falta.py](../../WebPosto_API/src/modules/cash_reconciliation/application/fontes_falta.py) · `anexar_fontes_falta` L19 | `paginar` (GET) | `/INTEGRACAO/V1/ADMINISTRADORAS` | /INTEGRACAO/V1/ADMINISTRADORAS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py](../../WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py) · `preparar` L227 | `paginar` (GET) | `/INTEGRACAO/V1/ADMINISTRADORAS` | /INTEGRACAO/V1/ADMINISTRADORAS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py](../../WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py) · `preparar` L233 | `paginar` (GET) | `/INTEGRACAO/V1/VENDAS` | /INTEGRACAO/V1/VENDAS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py](../../WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py) · `_cartoes` L323 | `paginar` (GET) | `/INTEGRACAO/V1/VENDAS` | /INTEGRACAO/V1/VENDAS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py](../../WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py) · `encontrar_candidatos_baixa` L211 | `paginar` (GET) | `/INTEGRACAO/V1/TITULOS_PAGAR` | /INTEGRACAO/V1/TITULOS_PAGAR [GET, POST] |
| [WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py](../../WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py) · `encontrar_candidatos_baixa` L227 | `paginar` (GET) | `/INTEGRACAO/V1/CONTAS` | /INTEGRACAO/V1/CONTAS [GET] |
| [WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py](../../WebPosto_API/src/modules/cash_reconciliation/application/titulos_pagos_sem_baixa.py) · `encontrar_candidatos_baixa` L245 | `paginar` (GET) | `/INTEGRACAO/V1/FORNECEDORES` | /INTEGRACAO/V1/FORNECEDORES [GET, POST] |
| [WebPosto_API/src/presentation/app.py](../../WebPosto_API/src/presentation/app.py) · `create_unified_app` L917 | `cache.cache_key` (Não inferido) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/presentation/app.py](../../WebPosto_API/src/presentation/app.py) · `create_unified_app` L1015 | `cache.cache_key` (Não inferido) | `/INTEGRACAO/PRODUTO/v2` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/presentation/app.py](../../WebPosto_API/src/presentation/app.py) · `get_webposto_grupos_produto` L917 | `cache.cache_key` (Não inferido) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/presentation/app.py](../../WebPosto_API/src/presentation/app.py) · `get_webposto_produtos` L1015 | `cache.cache_key` (Não inferido) | `/INTEGRACAO/PRODUTO/v2` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/services/produto_catalog.py](../../WebPosto_API/src/services/produto_catalog.py) · `get_catalog` L146 | `current.get` (GET) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/client.py](../../WebPosto_API/src/webposto/client.py) · `healthcheck` L101 | `self._http.get` (GET) | `/INTEGRACAO/FILIAL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/abastecimento.py](../../WebPosto_API/src/webposto/endpoints/abastecimento.py) · `listar` L58 | `self._http.get` (GET) | `/INTEGRACAO/ABASTECIMENTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/abastecimento.py](../../WebPosto_API/src/webposto/endpoints/abastecimento.py) · `listar_encerrante` L79 | `self._http.get` (GET) | `/INTEGRACAO/ABASTECIMENTO_ENCERRANTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/abastecimento.py](../../WebPosto_API/src/webposto/endpoints/abastecimento.py) · `listar_divergencia` L95 | `self._http.get` (GET) | `/INTEGRACAO/ABASTECIMENTO_DIVERGENCIA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/abastecimento.py](../../WebPosto_API/src/webposto/endpoints/abastecimento.py) · `reajustar_estoque_combustivel` L104 | `self._http.put` (PUT) | `/INTEGRACAO/REAJUSTAR_ESTOQUE_PRODUTO_COMBUSTIVEL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `listar` L50 | `self._http.get` (GET) | `/INTEGRACAO/CLIENTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `criar` L59 | `self._http.post` (POST) | `/INTEGRACAO/CLIENTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `atualizar` L69 | `self._http.put` (PUT) | `/INTEGRACAO/CLIENTE/{cliente_id}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `listar_frota` L85 | `self._http.get` (GET) | `/INTEGRACAO/CLIENTE_FROTA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `atualizar_veiculo_frota` L94 | `self._http.put` (PUT) | `/INTEGRACAO/CLIENTE_FROTA_VEICULO/{cliente_codigo}/{cliente_veiculo_codigo}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `listar_grupos` L108 | `self._http.get` (GET) | `/INTEGRACAO/GRUPO_CLIENTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `criar_grupo` L112 | `self._http.post` (POST) | `/INTEGRACAO/GRUPO_CLIENTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `atualizar_grupo` L116 | `self._http.put` (PUT) | `/INTEGRACAO/GRUPO_CLIENTE/{grupo_id}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `vincular_unidade_negocio` L122 | `self._http.post` (POST) | `/INTEGRACAO/VINCULAR_CLIENTE_UNIDADE_NEGOCIO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `integrar_prazo` L126 | `self._http.post` (POST) | `/INTEGRACAO/INTEGRACAO_CLIENTE_PRAZO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `listar_prazos` L135 | `self._http.get` (GET) | `/INTEGRACAO/INTEGRACAO_LISTA_CLIENTE_PRAZO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `retorno_cadastro` L139 | `self._http.get` (GET) | `/INTEGRACAO/RETORNO_CADASTRO_CLIENTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) · `centro_custo` L143 | `self._http.post` (POST) | `/INTEGRACAO/CENTRO_CUSTO_CLIENTE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) · `criar_pedido` L36 | `self._http.post` (POST) | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO` | /INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO [POST] |
| [WebPosto_API/src/webposto/endpoints/combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) · `listar_pedidos` L52 | `self._http.get` (GET) | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO` | /INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO [POST] |
| [WebPosto_API/src/webposto/endpoints/combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) · `faturar_pedido` L62 | `self._http.post` (POST) | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO/{pedido_id}/FATURAR` | /INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO/{id}/FATURAR [POST] |
| [WebPosto_API/src/webposto/endpoints/combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) · `receber_titulo_cartao` L74 | `self._http.put` (PUT) | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO/{pedido_id}/RECEBER_TITULO_EM_CARTAO` | /INTEGRACAO/PEDIDO_COMBUSTIVEL/PEDIDO/{id}/RECEBER_TITULO_EM_CARTAO [PUT] |
| [WebPosto_API/src/webposto/endpoints/combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) · `vincular_cliente_pedido` L81 | `self._http.post` (POST) | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/CLIENTE` | /INTEGRACAO/PEDIDO_COMBUSTIVEL/CLIENTE [GET] |
| [WebPosto_API/src/webposto/endpoints/combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) · `listar_aprix_custo` L101 | `self._http.get` (GET) | `/INTEGRACAO/APRIX_CUSTO` | /INTEGRACAO/APRIX_CUSTO [GET] |
| [WebPosto_API/src/webposto/endpoints/combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) · `listar_lmc` L126 | `self._http.get` (GET) | `/INTEGRACAO/LMC` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) · `listar_distribuidoras` L135 | `self._http.get` (GET) | `/INTEGRACAO/DISTRIBUIDORA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `listar_titulos_receber` L67 | `self._http.get` (GET) | `/INTEGRACAO/TITULO_RECEBER` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `criar_titulo_receber` L71 | `self._http.post` (POST) | `/INTEGRACAO/TITULO_RECEBER` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `receber_titulo` L75 | `self._http.put` (PUT) | `/INTEGRACAO/RECEBER_TITULO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `receber_titulo_convertido` L79 | `self._http.put` (PUT) | `/INTEGRACAO/RECEBER_TITULO_CONVERTIDO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `receber_cheque` L84 | `self._http.put` (PUT) | `/INTEGRACAO/RECEBER_CHEQUE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `receber_cartao` L88 | `self._http.put` (PUT) | `/INTEGRACAO/RECEBER_CARTAO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `listar_titulos_pagar` L110 | `self._http.get` (GET) | `/INTEGRACAO/TITULO_PAGAR` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `criar_titulo_pagar` L114 | `self._http.post` (POST) | `/INTEGRACAO/TITULO_PAGAR` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `listar_movimentos_conta` L134 | `self._http.get` (GET) | `/INTEGRACAO/MOVIMENTO_CONTA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `listar_fechamento_caixa` L154 | `self._http.get` (GET) | `/INTEGRACAO/FECHAMENTO_CAIXA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `listar_caixa_apresentado` L172 | `self._http.get` (GET) | `/INTEGRACAO/CAIXA_APRESENTADO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `listar_caixa` L190 | `self._http.get` (GET) | `/INTEGRACAO/CAIXA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `listar_transferencias` L206 | `self._http.get` (GET) | `/INTEGRACAO/TRANSFERENCIA_BANCARIA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `criar_transferencia` L210 | `self._http.post` (POST) | `/INTEGRACAO/TRANSFERENCIA_BANCARIA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `incluir_lancamento_contabil` L216 | `self._http.post` (POST) | `/INTEGRACAO/INCLUIR_LANCAMENTO_CONTABIL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `incluir_lote_contabil` L220 | `self._http.post` (POST) | `/INTEGRACAO/INCLUIR_LOTE_CONTABIL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `incluir_ofx` L224 | `self._http.post` (POST) | `/INTEGRACAO/INCLUIR_OFX` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `plano_de_contas` L233 | `self._http.get` (GET) | `/INTEGRACAO/PLANO_DE_CONTAS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) · `financeiro_exclusao` L252 | `self._http.get` (GET) | `/INTEGRACAO/FINANCEIRO_EXCLUSAO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_vendas` L57 | `self._http.get` (GET) | `/INTEGRACAO/VENDA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_vendas_rede` L73 | `self._http.get` (GET) | `/INTEGRACAO/VENDA_REDE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_grupos_produto` L84 | `self._http.get` (GET) | `/INTEGRACAO/GRUPO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_grupos_produto_meta` L93 | `self._http.get` (GET) | `/INTEGRACAO/GRUPO_META` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_nf_entrada` L117 | `self._http.get` (GET) | `/INTEGRACAO/NOTA_FISCAL_ENTRADA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_nf_saida` L135 | `self._http.get` (GET) | `/INTEGRACAO/NOTA_FISCAL_SAIDA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_pedidos_compra` L153 | `self._http.get` (GET) | `/INTEGRACAO/PEDIDO_COMPRAS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `criar_pedido_compra` L157 | `self._http.post` (POST) | `/INTEGRACAO/PEDIDO_COMPRAS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_usuarios` L168 | `self._http.get` (GET) | `/INTEGRACAO/USUARIO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_filiais` L177 | `self._http.get` (GET) | `/INTEGRACAO/FILIAL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_administradoras` L186 | `self._http.get` (GET) | `/INTEGRACAO/ADMINISTRADORA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_veiculos` L195 | `self._http.get` (GET) | `/INTEGRACAO/VEICULO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_adiantamento_fornecedor` L209 | `self._http.get` (GET) | `/INTEGRACAO/ADIANTAMENTO_FORNECEDOR` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `listar_prazo_tabela_preco` L220 | `self._http.get` (GET) | `/INTEGRACAO/PRAZO_TABELA_PRECO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `criar_item_prazo_tabela_preco` L224 | `self._http.post` (POST) | `/INTEGRACAO/PRAZO_TABELA_PRECO/{tabela_id}/ITEM` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `autorizar_pagamento_abastecimento` L230 | `self._http.post` (POST) | `/INTEGRACAO/AUTORIZA_PAGAMENTO_ABASTECIMENTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) · `persistir_cartao` L234 | `self._http.post` (POST) | `/INTEGRACAO/PERSISTIR_CARTAO_DTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `listar` L58 | `self._http.get` (GET) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `listar_empresa` L72 | `self._http.get` (GET) | `/INTEGRACAO/PRODUTO_EMPRESA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `incluir` L76 | `self._http.post` (POST) | `/INTEGRACAO/INCLUIR_PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `criar` L80 | `self._http.post` (POST) | `/INTEGRACAO/PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `atualizar` L84 | `self._http.put` (PUT) | `/INTEGRACAO/ALTERAR_PRODUTO/{produto_id}` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `reajustar` L93 | `self._http.post` (POST) | `/INTEGRACAO/REAJUSTAR_PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `trocar_preco` L97 | `self._http.post` (POST) | `/INTEGRACAO/TROCA_PRECO_PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `trocar_preco_combustivel` L101 | `self._http.post` (POST) | `/INTEGRACAO/TROCA_PRECO_COMBUSTIVEL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `inventario` L105 | `self._http.post` (POST) | `/INTEGRACAO/PRODUTO_INVENTARIO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `listar_inventario_itens` L131 | `self._http.get` (GET) | `/INTEGRACAO/PRODUTO_INVENTARIO_ITENS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `ajuste_estoque` L135 | `self._http.post` (POST) | `/INTEGRACAO/AJUSTE_ESTOQUE_PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `comissao` L139 | `self._http.post` (POST) | `/INTEGRACAO/PRODUTO_COMISSAO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `tributos_icms` L148 | `self._http.get` (GET) | `/INTEGRACAO/INTEGRACAO_PRODUTO_TRIBUTO_ICMS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py) · `tributos_pis_confins` L157 | `self._http.get` (GET) | `/INTEGRACAO/INTEGRACAO_PRODUTO_TRIBUTO_PIS_CONFINS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/relatorios.py](../../WebPosto_API/src/webposto/endpoints/relatorios.py) · `vendas_produto` L50 | `self._http.get` (GET) | `/INTEGRACAO/RELATORIO/VENDA_PRODUTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/relatorios.py](../../WebPosto_API/src/webposto/endpoints/relatorios.py) · `vendas_combustivel` L68 | `self._http.get` (GET) | `/INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/relatorios.py](../../WebPosto_API/src/webposto/endpoints/relatorios.py) · `resumo_vendas` L82 | `self._http.get` (GET) | `/INTEGRACAO/RELATORIO/RESUMO_VENDAS` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [WebPosto_API/src/webposto/endpoints/relatorios.py](../../WebPosto_API/src/webposto/endpoints/relatorios.py) · `estoque` L98 | `self._http.get` (GET) | `/INTEGRACAO/RELATORIO/ESTOQUE` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [scripts/export_reports.py](../../scripts/export_reports.py) · `main` L109 | `report_path.upper().startswith` (Não inferido) | `/INTEGRACAO/CAIXA` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |
| [scripts/export_reports.py](../../scripts/export_reports.py) · `main` L111 | `report_path.upper().startswith` (Não inferido) | `/INTEGRACAO/ABASTECIMENTO` | Path exato não consta; legado/dinâmico, não concluir indisponibilidade |

### Registry antigo: apenas catálogo comparativo

Origem consultada: `C:\Users\mlisb\OneDrive\ProjetosAntigravy\LOGOS SPACE\Api_WebPosto\WebPosto_API\src\gateway\webposto_endpoint_registry.py`.
As 23 entradas e suas maturidades declaradas estão no apêndice C. Nenhuma
`PRODUCTION_READ_APPROVED` antiga vale como validação deste checkout/credencial.
O catálogo antigo proíbe uma unidade que consta de `units.json` atual: **não
reaproveitar restrições de identidade por cópia**.

- ABASTECIMENTO_DIVERGENCIA, PRODUTO_INVENTARIO_ITENS, CARTAO antigo e RELATORIO/*
  **não constam como entradas dos 23 registros**. Há wrappers atuais de
  divergência/inventário/relatórios; CARTAO antigo não é sinônimo provado de CARTOES.
- DESPESAS_FINANCEIRO_REDE está no registry como LEGACY_DISCOVERED; a OpenAPI
  contém V1/DESPESAS_FINANCEIRO_REDE, mas o gateway atual chama CONSULTAR_*.
- Dos RELATORIO/*, a OpenAPI lista MAPA_DESEMPENHO, PRODUTIVIDADE_FUNCIONARIO,
  RELATORIO_PERSONALIZADO/{relatorioCodigo}, VENDA_PERIODO. Os quatro wrappers do
  SDK usam VENDA_PRODUTO/VENDA_COMBUSTIVEL/RESUMO_VENDAS/ESTOQUE, ausentes com esses
  paths no contrato fornecido. Não substituir uns pelos outros sem conferir.
- A antiga entrada ABASTECIMENTOS_V1 é só OPENAPI_DISCOVERED; aqui já alimenta
  cartão/placar. Isso é ganho real do projeto atual sobre o catálogo.

Comparação direcionada de código antigo, sempre por leitura textual/AST:

| Prioridade | Versão anterior | Projeto oficial / OpenAPI | Classificação da capacidade atual |
|---|---|---|---|
| ABASTECIMENTO_DIVERGENCIA | SDK listar_divergencia: dataInicial/dataFinal/filial | Mesmo wrapper atual; path singular e equivalente V1 específico não constam da OpenAPI fornecida | L; IMPLEMENTADA MAS NÃO USADA PELO LOGOS no fluxo operacional principal localizado; chamadas encontradas em testes, não em services |
| PRODUTO_INVENTARIO_ITENS | SDK listar_inventario_itens: pagina/tamanhoPagina | Wrapper também atual; path antigo não consta; CONTAGEM_ESTOQUES GET e PRODUTOS_INVENTARIOS POST não são aliases automáticos | L; IMPLEMENTADA MAS NÃO USADA PELO LOGOS no fluxo principal localizado; testes sintéticos presentes |
| CARTAO | Gateway antigo tem alias /INTEGRACAO/CARTAO e serviços de taxa/recebível/centro de custo | Gateway atual não tem esse alias; caixa usa V1/CARTOES e CartaoRede, não prova equivalência integral de taxa/centroCustoDescricao | V leitura V1 no caixa; atributos e regras adicionais do legado não validados aqui |
| CONSULTAR_DESPESAS_FINANCEIRO_REDE | Alias/registry/serviços antigos | Alias atual também existe; contrato tem V1/DESPESAS_FINANCEIRO_REDE | P; versão/semântica precisa de conferência atual |
| RELATORIO/* | Antigo SDK tem quatro wrappers iguais em propósito/path aos atuais | Mesmos paths singulares ausentes do contrato fornecido; relatórios oficiais disponíveis têm outros nomes | L; wrappers/testes não comprovam uso operacional |

“Não usada” nesta tabela significa **sem consumidor no pipeline principal
localizado pela inspeção estática**, não prova de que nenhum script externo possa
chamar o SDK. Os testes atuais de divergência/inventário/relatórios estão em
[test_get_cobertura_total.py](../../WebPosto_API/tests/unit/test_get_cobertura_total.py).
O legado comenta limitação de BIN/pré-pago e oferece modelos de taxa por
vigência: isso é conhecimento de domínio a conferir, não integração atual
com Cielo/Rede nem autorização para transplantar o motor antigo.

#### Apêndice C — 23 entradas do catálogo antigo

Status abaixo é o enum **do projeto antigo**, não a classificação de capacidade atual. As notas não importam proibições, chaves nem evidência financeira.

| Nome / domínio | Método / path documentado | Ativo no antigo / V1 | Paginação / filtros obrigatórios | Maturidade antiga | Confronto atual |
|---|---|---|---|---|---|
| `ABASTECIMENTO` / pista | `GET` `/INTEGRACAO/ABASTECIMENTO` | `/INTEGRACAO/ABASTECIMENTO`; V1=`—` | CURSOR; dataInicial, dataFinal | `MaturityStatus.PRODUCTION_READ_APPROVED` | Legado: conferir versão/semântica, não validação atual |
| `ABASTECIMENTOS_V1` / pista | `GET` `/INTEGRACAO/V1/ABASTECIMENTOS` | `—`; V1=`/INTEGRACAO/V1/ABASTECIMENTOS` | CURSOR; — | `MaturityStatus.OPENAPI_DISCOVERED` | Path V1 no contrato atual; código vertical atual já usa V1 |
| `ABASTECIMENTO_REDE` / pista | `GET` `/INTEGRACAO/CONSULTAR_ABASTECIMENTO_REDE` | `/INTEGRACAO/CONSULTAR_ABASTECIMENTO_REDE`; V1=`—` | UNKNOWN; dataInicial, dataFinal | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `ABASTECIMENTO_ENCERRANTE` / pista | `GET` `/INTEGRACAO/ABASTECIMENTO_ENCERRANTE` | `—`; V1=`—` | NONE; — | `MaturityStatus.DOCUMENTED_ONLY` | Legado: conferir versão/semântica, não validação atual |
| `ABASTECIMENTOS_ENCERRANTE_V1` / pista | `GET` `/INTEGRACAO/V1/ABASTECIMENTOS_ENCERRANTE` | `—`; V1=`/INTEGRACAO/V1/ABASTECIMENTOS_ENCERRANTE` | NONE; — | `MaturityStatus.OPENAPI_DISCOVERED` | Path V1 no contrato atual |
| `AUTORIZA_PAGAMENTO_ABASTECIMENTOS_V1` / pista | `POST` `/INTEGRACAO/V1/AUTORIZA_PAGAMENTO_ABASTECIMENTOS` | `—`; V1=`/INTEGRACAO/V1/AUTORIZA_PAGAMENTO_ABASTECIMENTOS` | —; — | `MaturityStatus.WRITE_BLOCKED` | Path V1 no contrato atual |
| `VENDA` / vendas | `GET` `/INTEGRACAO/VENDA` | `/INTEGRACAO/VENDA`; V1=`—` | PAGE; dataInicial, dataFinal | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `VENDAS_V1` / vendas | `GET` `/INTEGRACAO/V1/VENDAS` | `—`; V1=`/INTEGRACAO/V1/VENDAS` | CURSOR; — | `MaturityStatus.OPENAPI_DISCOVERED` | Path V1 no contrato atual; código vertical atual já usa V1 |
| `VENDA_ITEM` / vendas | `GET` `/INTEGRACAO/VENDA_ITEM` | `/INTEGRACAO/VENDA_ITEM`; V1=`—` | PAGE; dataInicial, dataFinal | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `VENDA_ITEM_REDE` / vendas | `GET` `/INTEGRACAO/CONSULTAR_VENDA_ITEM_REDE` | `/INTEGRACAO/CONSULTAR_VENDA_ITEM_REDE`; V1=`—` | UNKNOWN; dataInicial, dataFinal | `MaturityStatus.UNAVAILABLE_FOR_CREDENTIAL` | Legado: conferir versão/semântica, não validação atual |
| `VENDA_REDE` / vendas | `GET` `/INTEGRACAO/VENDA_REDE` | `—`; V1=`—` | UNKNOWN; — | `MaturityStatus.UNAVAILABLE_FOR_CREDENTIAL` | Legado: conferir versão/semântica, não validação atual |
| `VENDA_FORMA_PAGAMENTO` / vendas | `GET` `/INTEGRACAO/VENDA_FORMA_PAGAMENTO` | `/INTEGRACAO/VENDA_FORMA_PAGAMENTO`; V1=`—` | PAGE; dataInicial, dataFinal | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `PRODUTO` / cadastro | `GET` `/INTEGRACAO/PRODUTO` | `/INTEGRACAO/PRODUTO`; V1=`—` | PAGE; — | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `PRODUTOS_V1` / cadastro | `GET` `/INTEGRACAO/V1/PRODUTOS` | `—`; V1=`/INTEGRACAO/V1/PRODUTOS` | CURSOR; — | `MaturityStatus.OPENAPI_DISCOVERED` | Path V1 no contrato atual; código vertical atual já usa V1 |
| `PRODUTOS_V1_CREATE` / cadastro | `POST` `/INTEGRACAO/V1/PRODUTOS` | `—`; V1=`/INTEGRACAO/V1/PRODUTOS` | —; — | `MaturityStatus.WRITE_BLOCKED` | Path V1 no contrato atual |
| `PRODUTO_EMPRESA` / cadastro | `GET` `/INTEGRACAO/PRODUTO_EMPRESA` | `/INTEGRACAO/PRODUTO_EMPRESA`; V1=`—` | PAGE; — | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `EMPRESAS` / cadastro | `GET` `/INTEGRACAO/EMPRESAS` | `/INTEGRACAO/EMPRESAS`; V1=`—` | UNKNOWN; — | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `EMPRESAS_V1` / cadastro | `GET` `/INTEGRACAO/V1/EMPRESAS` | `—`; V1=`/INTEGRACAO/V1/EMPRESAS` | CURSOR; — | `MaturityStatus.OPENAPI_DISCOVERED` | Path V1 no contrato atual |
| `GRUPO` / cadastro | `GET` `/INTEGRACAO/GRUPO` | `/INTEGRACAO/GRUPO`; V1=`—` | UNKNOWN; — | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `CAIXA` / caixa | `GET` `/INTEGRACAO/CAIXA` | `/INTEGRACAO/CAIXA`; V1=`—` | PAGE; dataInicial, dataFinal | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `DESPESAS_FINANCEIRO_REDE` / financeiro | `GET` `/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE` | `/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE`; V1=`—` | UNKNOWN; dataInicial, dataFinal | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `LMC_REDE` / combustivel | `GET` `/INTEGRACAO/CONSULTAR_LMC_REDE` | `/INTEGRACAO/CONSULTAR_LMC_REDE`; V1=`—` | UNKNOWN; dataInicial, dataFinal | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |
| `FUNCIONARIO` / rh | `GET` `/INTEGRACAO/FUNCIONARIO` | `/INTEGRACAO/FUNCIONARIO`; V1=`—` | UNKNOWN; — | `MaturityStatus.LEGACY_DISCOVERED` | Legado: conferir versão/semântica, não validação atual |

## 4. Identidade entre entidades

Os schemas de resposta analisados não declaram `required` para essas propriedades.
Por isso “presente no contrato” não significa preenchido/obrigatório em cada
registro. Obrigatoriedade abaixo é de negócio/adapter quando explicitada.

| Origem | Campo | Destino | Confiabilidade | Uso atual |
|---|---|---|---|---|
| Empresa | empresaCodigo + configuração Unidade | Unidade do Logos | Chave de escopo obrigatória no domínio; filtrar resposta além da consulta | Caixa/comercial; não usar índice fixo da lista de filiais |
| CaixaRede | pdvCodigo | PDV | Campo explícito; cadastro PDVS não é coletado pelo módulo | Armazenado em Caixa; rótulo usa setor/turno, não só PDV |
| VendaRede | caixaCodigo + empresaCodigo | CaixaRede.caixaCodigo | Vínculo oficial usado; validar unidade/dia | Contexto e piloto |
| CaixaRede | funcionarioCodigo | FuncionarioRede.funcionarioCodigo | Identifica operador/abertura, não necessariamente vendedor | Rótulo do caixa e fallback explícito |
| VendaRede | funcionarioCodigo / funcionarioNome | Funcionário da venda | Pode diferir de operador/frentista; não presumir equivalência | Contexto considera outras evidências |
| VendaItemRede | vendaCodigo | VendaRede.vendaCodigo | Usado com filtro empresa; join não é por hora aproximada | Cartões/comercial |
| AbastecimentoRede | vendaItemCodigo | VendaItemRede.vendaItemCodigo | Validado no código/caso; descrição OpenAPI menciona vendaCodigo de VENDA_ITEM, inconsistente com o nome do campo | Usa item -> venda; não seguir cegamente descrição textual |
| AbastecimentoRede | codigoFrentista | FuncionarioRede.funcionarioCodigo | Contrato declara ligação; código comenta identfid, mas não há resolução separada FUNCIONARIOS_IDENTFID aqui | Nomes por código; manter distinção de operador |
| VendaFormaPagamentoRede | vendaCodigo + empresaCodigo | VendaRede | Forte quando presentes; pode haver múltiplas formas por venda | Tipo D dinheiro, B transferência; venda inteira não deve ser presumida de forma única em todo cenário |
| VendaFormaPagamentoRede | formaPagamentoCodigo / tipoFormaPagamento | Forma de pagamento | Códigos e tipos não são administradora nem NSU | Usados para classificar dinheiro/PIX/POS |
| CartaoRede | vendaCodigo | VendaRede -> caixa | CARTOES não tem caixaCodigo no schema de leitura | Enriquecimento oficial via venda |
| CartaoRede | administradoraCodigo / adiministradoraDescricao | Administradora | Grafia adiministradoraDescricao é a da API; descrição não substitui código único | Texto/seleção do piloto; não hardcode de bandeira |
| CartaoRede | nsu / nsuTef / autorizacao | EDI PagBank | Strings opcionais, normalização e ambiguidade importam; valor/hora é evidência mais fraca | Matching + piloto; nsuTef não comprova TEF integrado |
| CartaoRede | cartaoCodigo | Registro criado no ERP | Identificador para conferência/DELETE; não chave universal de pagamento | Auditoria técnica; não expor como identidade do caixa |
| AbastecimentoRede | codigoBico | BicoRede.bicoCodigo | Contrato permite; ligação operacional por cadastro ainda não implementada | Campo bico preservado; sem grafo completo |
| BicoRede | bombaCodigo / tanqueCodigo / produtoCodigo | BombaRede / TanqueRede / Produto | Contrato explícito; sem histórico temporal de remapeamento integrado | Não usado em auditoria física |
| VendaItemRede | bicoCodigo / tanqueCodigo / produtoLmcCodigo | Equipamento/LMC | Disponível V1; projeção reduzida de Abastecimento perde parte destes campos | Potencial REUSE, não cadeia já validada |
| LmcRede | produtoCodigo / produtoLmcCodigo / lmcTanque / lmcBico / lmcNota | Produto/equipamento/notas | Agregados e arrays; não assumir chaves iguais entre versões | Analytics legado parcial |
| TanqueMedidaResult | tanqueCodigo + dataMedida/horaMedida | Tanque e instante físico | Array sem empresa no item; escopo deve vir da consulta/credencial | Não integrado |
| TanqueEntradaResult | tanqueCodigo + dataHoraInicio/Fim | Descarga no tanque | Volume de entrada medido; não garante identidade da NF | Não integrado |
| NotaEntradaRede | compraCodigo / notaEntradaCodigo / fornecedorCodigo | Compra, itens e fornecedor | Contrato fornece IDs; faltam coleta/join V1 na auditoria de estoque | Fornecedor usado na conciliação de despesas, não auditoria de recebimento |
| NotaEntradaItemRede | compraCodigo / notaEntradaCodigo / produtoCodigo | Cabeçalho e produto | SequencialItem e unidadeCompra exigem conversão/validação | Não integrado ao balanço de estoque |
| NfceRede | vendaCodigo / situacao / protocoloCancelamento | Venda fiscal | Documento fiscal não é prova isolada do efeito físico do cancelamento | Gateway legado; V1 ainda não validado |
| ContagemEstoqueRede | unidadeNegocio / estoqueCodigo / contagemNotas | Unidade, estoque e itens de contagem | Não usar empresaCodigo presumido: schema usa unidadeNegocio | Não integrado |
| Sangria | contaCodigo / caixaCodigo / funcionarioCodigo | Destino, caixa, responsável | Validação por unidade e contas configuradas | Conciliação de espécie |
| OFX | conta_sufixo + banco + FITID + hash | Conta e lançamento bancário | Sufixo não é conta global; FITID precisa de escopo por conta e conflito explícito | PIX usa conta configurada; despesas/baixa têm seleção mais ampla |

**Comunicação humana:** PDV, centroCusto, caixaCodigo, vendaItemCodigo,
administradoraCodigo, produtoLmcCodigo e códigos de bico/tanque sem descrição não
são rótulos suficientes. Reusar `identificar_caixa`: posto, setor, movimento,
turno, quem abriu e hora; ocorrências financeiras trazem nome+código do responsável
quando identificado. Fallback deve declarar ausência, não atribuir culpa ao abridor.
Não há prova de PIX dinâmico, integração TEF em produção ou equivalência NSU=nsuTef.

## 5. Conveniência

### O que já existe

- VendaRede: data/hora, caixa, funcionário, total, cancelada, data/hora e justificativa
  de cancelamento, nota; VendaItemRede: produto, quantidade, preço/custo unitário e
  total, desconto/acréscimo, valores brutos. São campos do contrato, não todos
  preservados na projeção reduzida de conciliação de cartões.
- SDK de produto/empresa e gateway com venda/item/forma, estoque atual/período e
  NFCE. Catálogo e tabelas de produto têm testes. Gateway consulta itens/formas com
  cursor limitado a dez páginas; completude não é automaticamente garantida.
- V1 já documenta histórico de estoque, contagem com notas/itens, notas de entrada
  com itens, fornecedor e unidades de compra. Não são capacidades “sem API”.
- CRUDs locais de NFeCompra/Produto/ContaPagar no gateway aninhado não comprovam
  coleta dessas entidades do webPosto nem movimentação real de estoque.

### O que conseguimos ligar

Empresa -> venda -> item -> produto; venda -> caixa -> operador; venda -> pagamento;
nota -> item de entrada -> produto e fornecedor (potencial do contrato, ainda sem
pipeline V1 integrado). Centro de custo distingue pista/loja/food quando configurado.

### O que falta para uma primeira auditoria confiável

1. Recorte de uma unidade/setor/dia, preservando item, custo, desconto, cancelamento,
   origem e instante da coleta, em vez de somente total de venda.
2. Completude de paginação, filtro unidade/estoque e equivalência das versões
   antigas com V1, conferidas em uma amostra autorizada.
3. Estoque inicial/final **no mesmo instante de corte**, entradas por item com
   conversão unidadeCompra -> unidade de venda e contagem física referenciada.
4. Separar cancelamento fiscal, cancelamento da venda, ajuste manual, devolução,
   perda e transferência. Não imputar qualquer diferença a desconto.
5. Evidência do ajuste manual: motivo, usuário, antes/depois, documento ou evento.
   Presença de ultimoUsuarioAlteracao no cadastro não fornece histórico inteiro.
6. Teste fechado de saldo inicial + entradas - saídas +/- ajustes = saldo final e
   inventário, com caso conferido na tela. **Não implementado nesta auditoria.**

## 6. Combustível

| Pergunta | O que há | O que falta | Conclusão |
|---|---|---|---|
| A. Encerrante/bico x volume vendido | ABASTECIMENTOS V1 tem quantidade, encerrante, afericao e item; wrapper legado de encerrante; V1 retorna idVenda/bico/encerrante/volume/valor | Cadastro BICOS/BOMBAS, abertura/fechamento temporal, remapeamento, idVenda e bico textual conferidos, rollover/manutenção e pendentes | **P: dados potenciais, cadeia atual insuficiente para conclusão confiável** |
| B. Teórico x medição física | LMC legado agregado, TANQUES no gateway, V1 LMCS/TANQUE_MEDIDA/TANQUE_ENTRADA documentados | Coletar e ligar medições, descargas e notas no mesmo intervalo, regra de cortes/transferências/temperatura conforme negócio | **P: não há auditoria física ponta a ponta validada** |

| Exceção | Campo/evidência disponível | Lacuna a registrar antes de criar regra |
|---|---|---|
| Aferição | AbastecimentoRede.afericao | Caixa filtra pelo valor Python; comercial usa parser explícito. Não reaproveitar indiscriminadamente a lista já filtrada para balanço físico |
| Venda teste | Não há flag inequívoca no modelo reduzido atual | Motivo/origem/documento conferido; afericao não é sinônimo universal |
| Abastecimento próprio | Venda/cliente/forma disponíveis no contrato | Classificação de consumo próprio por regra validada, sem heurística de nome isolada |
| Cancelamento | VendaRede.cancelada e campos fiscais NFC-e | Efeito físico, data do estorno e vínculo ao abastecimento |
| Descarga | TanqueEntradaResult: início/fim e volumes; notas/itens V1 | Vínculo da descarga à NF, tanque e janela operacional |
| Transferência | Fontes de movimentação/nota, não flag clara no modelo atual | Tanque origem/destino, volume e horário conferidos |
| Troca/manutenção de bico | Cadastro bico/bomba/tanque e último usuário | Histórico de configuração e encerrantes antes/depois |
| Virada de turno | Caixa dataMovimento/abertura/fechamento/turno | Corte real do equipamento, dias fiscais versus movimento |
| Pendente | Abastecimento com vendaItemCodigo ausente/sem vínculo | Momento de liquidação; não desaparecer por exigir venda fechada |

Não criar regra a partir de `FuelAnalyticsService._extract_litros` ou de totais do
LMC: são agregações executivas, não evidência suficiente de perda física.

## 7. Cartão / TEF / PIX

### Cadeia reconstruível e suas fronteiras

`VENDAS -> VENDAS_FORMA_PAGAMENTO` por empresa/venda; `CARTOES -> VENDAS` por
vendaCodigo; `ABASTECIMENTOS -> VENDAS/ITENS -> VENDAS` por item.
O cartão tem NSU/nsuTef/autorização e administradora; a forma tem
administradoraCodigo, mas não NSU. **Não há chave 1:1 universal declarada de
formaPagamento para cartaoCodigo.** Parcelas/divisão de pagamento podem exigir
valor, data e identificadores adicionais.

| Camada | Dado confirmado | O que não se pode inferir |
|---|---|---|
| API V1 | CartaoRede.nsu, nsuTef, autorizacao, administradoraCodigo; grafia adiministradoraDescricao; vendaCodigo | Campo nsuTef não prova TEF funcionando |
| Schemas/wrappers legados | PersistirCartaoDto, PERSISTIR_CARTAO_DTO e paths singulares | Não equivalem automaticamente ao DTO atual de POST CARTOES |
| Implementação Logos | CartaoErp.nsu_tef, enriquecimento por venda/caixa, matching NSU/autorização/valor-hora, candidatos | Score não substitui vínculo oficial nem aprova escrita |
| Ainda sem prova | TEF integrado, PIX dinâmico, integração Cielo/Rede, sucesso real de inclusão do piloto | Não promover pelo nome de coluna ou configuração |

PIX da maquininha é evento EDI separado de PIX CNPJ direto na conta e de Mais
Pagamentos. O caso real 19 tem administradora PIX PagBank, mas EDI BACEN não
informa NSU/autorização: **manual**, sem inventar identificador.
O relatório pode exibir proposta e `[Lançar]` abre somente a revisão existente;
`lancavel` no decompositor não reavalia sozinho todas as travas/histórico/limites
do piloto. Aprovação efetiva continua no serviço único.

### Golden case Doze — 14/10/2026

Valores abaixo são o contrato de aceitação solicitado e a evidência histórica
registrada, sem exportar linhas operacionais/pessoas/NSUs completos para o Git.
Caixa: **Doze · Pista — 14/10, 1º turno (quem abriu e hora no rótulo local)**,
não consolidado.

| Componente esperado | Valor |
|---|---:|
| Mastercard PagBank lançado como dinheiro | R$ 34,75 |
| PIX da maquininha PagBank lançado como dinheiro | R$ 139,35 |
| Mais Pagamentos acima de Transf. Crédito | R$ 500,00 |
| Sem explicação | R$ 12,61 |
| Total | R$ 686,71 |

- Lógica: `explicar_falta`, modelos `ParteFalta`/`ExplicacaoCaixa`,
  `fontes_falta.anexar_fontes_falta`, `mais_pagamentos.comparar`,
  `pix_cnpj.conferir_pix_cnpj`; relatório e resumo reutilizam o resultado.
- Teste sintético:
  [test_tabela_completa_mesmo_calculo_no_relatorio_e_resumo](../../WebPosto_API/tests/unit/cash_reconciliation/test_explicar_falta.py).
  Afirma 34,75 + 139,35 + 500,00, residual 12,61 e total 686,71.
  Usa fixtures sintéticas/model_copy e injeta parte Mais de 500: não é gravação
  anonimizada integral de todas as fontes nem teste end-to-end de coleta.
- Alimentação real anterior: CAIXAS/APRESENTADO, CARTOES, VENDAS/ITENS/FORMAS,
  ABASTECIMENTOS, FUNCIONARIOS, ADMINISTRADORAS, EDI, OFX e total do diretor.
  O teste de PIX verifica exclusão de grupo/Vibra, conflitos FITID e casamento.
- Resultado é **determinístico com entradas congeladas**; reconsultar ERP/EDI,
  trocar OFX ou sobrescrever o total pode alterar o resultado legitimamente.
- **Limite descoberto:** snapshot operacional salvo para esse dia ainda é
  pré-Sprint 19, sem partes_falta/pix_cnpj/mais_pagamentos, e candidatos sem
  caixa_codigo. Sua diferença de dinheiro é de outro instante, **não coincide**
  com o contrato acima. Não atualizar/corrigir esse snapshot nesta auditoria.
- Pode virar golden case formal por **ADAPT**, não nova regra: fixtures anonimizadas
  de todas as fontes, instante/versão, hashes, escopo e rótulo esperado; replay
  offline desde os adapters, conferência humana e distinção snapshot antigo x
  atualizado. Hoje existe golden **sintético do cálculo**, não replay raw completo.

## 8. Integrações externas

| Integração | Arquivo / função | Autenticação e fonte | Erro / retry | Persistência / testes | Estado real |
|---|---|---|---|---|---|
| webPosto V1 | [paginar](../../WebPosto_API/src/modules/webposto_integration/http.py) | CHAVE da variável indicada pela unidade; query HTTPS | Erro explícito, sem retry automático, cursor até vazio/repetido | ResultadoDiario/proveniência; tests unit cash/comercial | V para rotas conferidas |
| PagBank | [pagbank_edi.buscar_transacoes](../../WebPosto_API/src/modules/cash_reconciliation/adapters/pagbank_edi.py) | Basic por unidade, token/user via ambiente; transactional v3.00 | 401/403 = credencial inválida; 404 sem movimentos; paginação totalPages/dedup; sem retry explícito | Snapshot derivado; test_cartoes/test_recebimentos | V; não há raw universal versionado |
| Premmia | [premmia_portal.coletar](../../WebPosto_API/src/modules/cash_reconciliation/adapters/premmia_portal.py) | Login revendedor via browser/Playwright, credenciais por unidade | Uma tentativa; fallback visível antes de login; CAPTCHA/2FA/credencial -> parar/aviso | XLSX mensal, controle de coleta/integridade; test_premmia_portal | V nos casos anteriores; não garantia contínua |
| Mais Pagamentos | [carregar/salvar/comparar/interpretar](../../WebPosto_API/src/modules/cash_reconciliation/application/mais_pagamentos.py) | Declaração diretor; CLI ou chat/user privado | Erros formato/arquivo; sem retry de coleta/portal | JSON atômico unidade/dia; test_mais_pagamentos | V CLI/comparação; receptor I; API automática A |
| Bancos | [extrato_reader.ler_ofx](../../WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py) | Arquivos do negócio, sem conexão bancária | Barreira de formato/encoding; falhas de valores | Hash SHA-256, arquivos externos; test_extrato_reader | V parser; integração bancária online A |
| Telegram | [shared/notificacao](../../WebPosto_API/src/shared/notificacao/telegram.py), [telegram_cartoes](../../WebPosto_API/src/modules/cash_reconciliation/adapters/telegram_cartoes.py), [receber_comprovantes](../../WebPosto_API/src/jobs/receber_comprovantes.py) | Bot token; resumo para lista, aprovação/total para diretor privado | Envio genérico até 2 tentativas; bot privado sem retry cego de operação ERP; polling precisa consumidor único | envios_telegram.json, tickets SQLite, fila local; testes Telegram/19C | V envio histórico, I receptores novos/decisão real |
| Gemini | [GeminiExtractor](../../WebPosto_API/src/modules/cash_reconciliation/adapters/gemini_comprovantes.py) | API key ambiente; documento/áudio para serviço externo quando acionado | HTTP/JSON, fallback de modelo implementado | DadosComprovante e fila; test_comprovantes_fila usa mocks | I; não enviou documentos nesta auditoria |
| Cielo / Rede | [config](../../WebPosto_API/src/modules/cash_reconciliation/config/units.json), [recebimentos](../../WebPosto_API/src/modules/cash_reconciliation/application/recebimentos.py) | Apenas modalidades/situação pendente | Sem adapter ativo; fonte ativa sem adapter gera erro explícito | Testes de pendência | A como integração de adquirente |
| Automação browser | [premmia_portal](../../WebPosto_API/src/modules/cash_reconciliation/adapters/premmia_portal.py) | Browser local e exportação portal | Parada humana obrigatória | XLSX/artefatos locais | V Premmia; scripts probe são experimentais, não novo fluxo aprovado |

Não confundir Rede (adquirente) com endpoints “*_REDE” do webPosto (visão
multiempresa). Nenhuma autenticação real foi testada e nenhum segredo foi lido.

## 9. Escritas existentes

**Congeladas operacionalmente nesta auditoria.** Não se testou nenhuma operação,
nem mesmo POST local que possa disparar job, proxy, geração de documento ou envio.
Capacidade de escrever não significa que escrita está habilitada no ambiente.

| Operação | Arquivo / função / endpoint | Guardas / aprovação | Idempotência / retry / compensação / logging | Evidência / risco |
|---|---|---|---|---|
| Cartão incluir | [incluir_cartao](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_cartao.py), POST V1/CARTOES | WEBPOSTO_WRITES + LOGOS_ERP_ESCRITA físicos; piloto requer diretor, escopo, único candidato >=90, NSU/auth, admin única, caixa não consolidado/bloqueado, limites | Lock por unidade; reserva antes, histórico/NSU; sem retry cego; confirma GET e deltas dinheiro/cartão | P; histórico real reservado/incerto/nao_entrou; não há sucesso real comprovado |
| Cartão desfazer | excluir_cartao + [piloto_cartao](../../WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py), DELETE V1/CARTOES/{id} | Mesmas travas; serviço checa criação própria/estado e compatibilidade | Reconsulta, DELETE compensatório e conferência; falha deixa bloqueio | I como compensação real; só teste sintético suficiente localizado |
| Cartão nova tentativa | confirmar(... nova_tentativa=True), CLI --confirmar --nsu --nova-tentativa | Novo ok; todas anteriores nao_entrou; não exposta automaticamente ao robô | Novo acao_id, referência anterior, reservas brutas somadas; mantém bloqueio incerto | I; test_ajustes_19d; não executada realmente |
| OFX V1 | [enviar_ofx_webposto](../../WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py), POST V1/OFXS | WEBPOSTO_WRITES + LOGOS_OFX_IMPORTACAO físicas; --confirmar; conta/unidade, header/hash; débito bloqueado sem formato confirmado | Histórico conta/dia, sem retry explícito; conferência humana separada; não rollback automático | P; incidente de sinais no 17B; histórico não é garantia atômica contra concorrência/falha entre POST e persistência |
| Produto remoto | [produto_crud.criar_produto/atualizar_produto](../../WebPosto_API/src/application/usecases/produto_crud.py), POST INCLUIR_PRODUTO/PRODUTO, PUT ALTERAR_PRODUTO/{id} | Nenhuma trava cartão/OFX reutilizada no usecase | Fallback para segundo POST em exceção ampla; SDK pode repetir writes; sem reserva/rollback específico | L no entrypoint alternativo; não considerar protegido pelo piloto |
| SDK clientes/frota/grupo | [clientes.py](../../WebPosto_API/src/webposto/endpoints/clientes.py) | CHAVE; sem guardas físicas comuns | HTTPClient permite retry de POST/PUT/PATCH/DELETE; sem chave de operação/compensação própria | L wrappers de escrita; lista completa no apêndice B |
| SDK títulos/cheques/cartões/transferência/contábil/OFX legado | [financeiro.py](../../WebPosto_API/src/webposto/endpoints/financeiro.py) | CHAVE; não exige autorização física do piloto | Retry do SDK; sem idempotência/rollback universal | L; não confundir criar_titulo_pagar com job de candidatos à baixa |
| SDK produto/preço/inventário/ajuste/comissão | [produtos.py](../../WebPosto_API/src/webposto/endpoints/produtos.py), [abastecimento.py](../../WebPosto_API/src/webposto/endpoints/abastecimento.py) | CHAVE; sem congelamento central | Retry de escrita no SDK, sem compensação própria | L; inventário não é só GET |
| Pedido combustível/faturar/cliente/receber cartão | [combustivel.py](../../WebPosto_API/src/webposto/endpoints/combustivel.py) | CHAVE; aprovação/idempotência operacional não localizadas | SDK genérico; sem auditoria de operação do piloto | L; alguns paths constam da OpenAPI não V1 |
| Pedido compra/item prazo/autorizar abastecimento/PERSISTIR_CARTAO_DTO | [integracoes.py](../../WebPosto_API/src/webposto/endpoints/integracoes.py) | CHAVE; sem mesmas travas físicas | SDK genérico; sem rollback próprio | L; DTO/cartão legado não homologado como equivalente V1 |
| Proxy arbitrário | [presentation.app.webposto_proxy](../../WebPosto_API/src/presentation/app.py), POST /api/webposto/proxy; [explorador.proxy](../../WebPosto_API/explorador_standalone.py) | Corpo escolhe GET/POST/PUT/PATCH/DELETE e path; não usa trava do piloto | Sem idempotência/compensação da operação; retorno pode incluir URL da requisição | L; superfície alternativa não pode ser tratada como read-only por padrão |
| REST alternativo | [infrastructure/webposto/client.py](../../WebPosto_API/src/infrastructure/webposto/client.py), criar_cliente/abastecimento/lancamento e atualizar | CHAVE, /api/v1/* remoto; sem guardas físicas | Tenacity até 3 tentativas, inclusive métodos de escrita; sem rollback próprio | L; não corresponde ao contrato atual |
| CRUDs internos | [clientes](../../WebPosto_API/src/interfaces/http/routes/clientes.py), [routes_crud](../../WebPosto_API/src/routes_crud.py), [gateway CRUD](../../WebPosto_API/logos-webposto-gateway/src/presentation/crud_routes.py), auditoria Mongo | Repositórios/eventos/DB; regras variam por app | São mutações locais, não prova de criação no ERP | I/P conforme superfície; não executadas |
| Pendências/conferência/total Mais/propostas | [pendencias](../../WebPosto_API/src/modules/cash_reconciliation/adapters/pendencias.py), [mais_pagamentos](../../WebPosto_API/src/modules/cash_reconciliation/application/mais_pagamentos.py) | Perfis/escopo nas interfaces; comandos locais explícitos | SQLite transacional, JSON atômico; histórico e sobrescrita diferem | Escritas locais existem; total declarado não tem trilha imutável de revisões |
| Telegram/Gemini/browser | Arquivos seção 8 | Configuração e chamadas explícitas, regras próprias | Envios/retry podem duplicar mensagens, browser autentica externamente | Escrita externa de mensagem/consulta autenticada, não ERP; nada executado |

Para cada wrapper individual, método/path/função constam do apêndice B. Paths
montados dinamicamente são cobertos pelas famílias acima; inventário de literais
sozinho não provaria ausência de outras escritas.
Não há writer V1 específico integrado para baixa de títulos/despesa avulsa/estoque
no módulo de caixa. A API oficial ter POST/PATCH não significa implementação.

## 10. Produção / job 03:00

### Configuração real consultada em 16/10/2026

| Campo | Observação |
|---|---|
| Tarefa Windows | LOGOS - Auditoria de Caixa; habilitada, estado Ready |
| Executável | C:\Program Files\Python314\pythonw.exe |
| Argumentos reais | -B -m src.modules.cash_reconciliation.jobs.noturno |
| WorkingDirectory real | C:\Projetos\LOGOS\LogosPostos\WebPosto_API |
| Horário | Diariamente 03:00, boundary UTC-03:00 |
| Principal | Interactive, Limited: depende de sessão Windows aberta |
| Última execução | 16/10/2026 03:00:01; LastTaskResult = 1 |
| Próxima execução | 17/10/2026 03:00; sem execuções perdidas informadas |
| Python consultado no mesmo diretório | Python 3.14.4; não se abriu novo serviço |
| Produção isolada | C:\Projetos\LOGOS\production não existe |

[registrar_robo_noturno.ps1](../../scripts/registrar_robo_noturno.ps1) instala
`-B -m src.jobs.noturno`, **diferente do argumento atualmente registrado**.
O módulo antigo faz `main -> src.jobs.noturno.main`, portanto a diferença não
prova execução de uma versão antiga de toda a lógica. Contudo o código é lido
do checkout mutável, **não de tag aprovada**, a cada execução.

Fluxo: argparse/dia anterior Recife -> load_dotenv -> log ->
caixa.jobs.executar -> Premmia por unidade -> fechamento/adquirentes/fontes locais
-> opcional piloto automático -> placar -> persistência/fila/resumo/estado ->
`_tentar_envio_telegram` -> mensagens/planilha e propostas privadas se configuradas.
O automático depende de LOGOS_CARTAO_AUTOMATICO e das demais travas; não se
consultaram os valores correntes dessas variáveis.

### Evidência de falha e risco de frescor

- Em `data/cash_audit/noturno.log`, marcadores de hoje: uma ocorrência de
  “Execucao bloqueada” e “WEBPOSTO_WRITES deve ser 0”; zero “Execucao terminada”
  e um “Telegram envio=ok”. Isso é compatível com LastTaskResult=1.
- O código chama `_tentar_envio_telegram` após `executar` **mesmo com retorno 1**.
  O envio lê snapshots locais. Logo “Telegram ok” não comprova coleta concluída
  nem dados atuais; pode reusar evidência anterior. Não se afirma conteúdo exato
  recebido pelo diretor sem conferi-lo.
- O estado local de robô não acompanha a execução das 03:00 e tem escopo vazio/
  dia antigo. Não usar esse estado isoladamente como prova de saúde operacional.
- Registro de envio tem status ok para dias recentes; não comprova entrega do
  documento, porque sucesso principal é calculado pelas mensagens e documento
  é tratado separadamente.
- Saídas: `data/cash_audit/<dia>/<unidade>.json`, `data/placar`,
  `data/pendencias`, `data/resumos`, `data/premmia`, `data/conferencia_recebimentos`,
  `data/lancamentos_logos`, `data/mais_pagamentos`. Log no módulo, não em pasta
  `WebPosto_API/logs`.

### Deploy mínimo recomendado (não executado)

1. Definir commit/tag aprovada sem merge automático. Copiar/checkout **da release**
   para `C:\Projetos\LOGOS\production`, não apontar produção para working tree.
2. Reusar os entrypoints atuais; escolher explicitamente API principal e comando
   do job. Alinhar o argumento registrado com o script, sem perder compatibilidade.
3. Ambiente Python isolado com dependências aprovadas, browser Playwright se
   necessário e conta operacional apropriada; hoje não há venv no argumento real.
4. Separar dados/configuração/evidências da pasta substituível da release.
   Muitos paths usam `__file__.parents` ou são absolutos: decidir diretório de
   dados/backup e migração antes de copiar, não distribuir `.env`/dados no Git.
5. Referenciar extratos externos e preservar conta/unidade; não copiar OFX ao
   repositório. Ajustar permissões, capacidade de I/O, logs e retenção.
6. Smoke offline/read-only, replay de golden case anonimizado e checagem de
   frescor/exit code antes de reativar envio. Nenhuma escrita financeira liberada.
7. Agendamento/monitoramento com lock/single consumer, execução sem usuário
   quando aprovado, backup SQLite/JSON, rollback de release e evidência da versão.
8. Aprovação humana e janela de cutover. Nenhuma tarefa foi registrada/reiniciada,
   nenhuma variável/flag editada e nenhuma nova arquitetura foi criada.

## 11. Persistência / evidência

Metadados locais inspecionados em 16/10/2026; quantidade não é prova de qualidade.

| Artefato | Existência / formato | Reproduzibilidade / origem | Sobrescrita / versionamento |
|---|---|---|---|
| cash_audit | 56 JSON + noturno.log | ResultadoDiario, proveniência, regra, escopo; valores já transformados | salvar_dia usa temporário/fsync/replace; mesmo unidade/dia substituído, não histórico de todas as coletas |
| placar | 3 JSON | Produto/metas/abastecimentos derivados | Snapshot não é raw imutável |
| pendencias | 2 SQLite | Pendência e eventos/decisões | Transações e identidade; não arquivo raw da API |
| conferencia_recebimentos | 20 JSON + SQLite, MD e XLSX | Ações/conferência derivadas | Propostas não são confirmação financeira |
| lancamentos_logos | 1 histórico JSON | Ações e estados; payload/resposta técnica nos eventos apropriados | Append lógico com replace físico; lock de operação e lock em processo não tornam arquivo WORM |
| importacoes_ofx | 1 JSON | Histórico conta/dia/hash/estado de conferência | Não é extrato bruto nem prova automática do efeito do ERP |
| mais_pagamentos | 1 JSON | Declaração do diretor, data/unidade/total/detalhe | Atômico; sobrescreve por dia, não preserva todas as revisões |
| premmia | XLSX, JSON, SQLite e imagens | Exportações/controle de coleta, incluindo material de validação | Mensal é atualizado; hashes/controles ajudam, não cobrem raw universal |
| despesas_avulsas | Planilha local; fila JSON não localizada no estado inspecionado | Código sabe salvar fila e comprovantes | Implementação não prova recepção operacional em uso |
| propostas_lancamento | 23 JSON | Sugestões locais | Não demonstram POST no ERP |
| relatorios | 5 MD + 5 XLSX | Render de snapshots | Não conter única cópia do dado de origem |
| resumos | MD/XLSX + 2 JSON | Estado do robô e envios; saída derivada | Estado/resumo por dia substituíveis; risco de frescor |
| extratos externos | Pasta fora do repo | OFX raw com SHA-256, conta e FITID | Retenção externa necessária; o hash sozinho não recupera arquivo removido |
| caches/snapshots analytics | Memória + disco/TTL, Valkey em outras cadeias | SnapshotStore usa lastUpdated e chaves normalizadas | write_text direto, não mesmo protocolo atômico/proveniência do caixa |

**Raw evidence:** há extratos/exportações e alguns payloads/respostas, mas não um
arquivo bruto imutável por requisição para todas as fontes/páginas. ResultadoDiario
contém projeções filtradas: perde campos que poderiam explicar exceções futuras.
`Proveniencia` é bom ponto de REUSE, não prova de que toda fonte tem hash/raw.

Para rastrear “de onde veio este número” falta ligar **versão do código + regra +
instante/corte + parâmetros/página + hash do raw + transformação + revisão de
declaração manual + evidência de conferência**. Guardar raw fora do Git, minimizando
dados pessoais; fixtures sintéticas/anonimizadas no repositório. Não se criou novo
storage nem se editou qualquer dado real nesta auditoria.

## 12. Duplicidades

| Área | Duplicação/variação observada | Consequência | Reuso recomendado sem refatorar agora |
|---|---|---|---|
| Cliente HTTP | SDK requests, gateway async, V1 compartilhado, infra REST, PostoAPIClient e gateway aninhado | Auth/paginação/retry/erro diferentes | Preferir HTTP V1 compartilhado onde já serve; preservar diferenças comprovadas |
| Caixa | Módulo vertical, FechamentoService enterprise, AuditGateway/subcentro e CRUD Mongo | “Caixa” pode significar três modelos distintos | Módulo vertical como evidência operacional; não somar resultados paralelos |
| Conciliação | rules/matching/cartoes no módulo e financial_reconciliation_engine/analytics | Totais e hipóteses distintas | Não afirmar duplicatas byte a byte; comparar semântica e consumidores |
| Classificação despesas | logos_expense_classifier, v2, v3 | Versões coexistem; existência de v3 não prova que v1/v2 são código morto | Localizar imports antes de migrar |
| Health score/snapshot | health_score e v3; vários snapshot services/stores | Múltiplos conceitos de sucesso/frescor | Reusar metadados de saúde com contrato explícito |
| Tempo/moeda | Helper Recife/Decimal no vertical vs datetime.now/date.today e float/fallback zero em legados | Corte temporal e valor ausente divergem | Não promover fallback zero a dado conferido |
| Entrypoints | src.main, presentation.app, main_minimal, explorador e pacote aninhado | Rota existir não garante publicação | Fixar composição aprovada no deploy |
| Env | load_dotenv nas cadeias atuais; presentation.app tem leitor manual com read_text | Importar entrypoint alternativo pode ler `.env` fora do padrão | Não o importar durante auditoria; futura correção separada |
| Raiz x WebPosto_API | src/webposto/services/apps com nomes paralelos | Imports dependem do cwd/PYTHONPATH | Release com diretório/ambiente explícitos |
| Scripts de pesquisa | audits/probes e relatórios gerados coexistem com fluxos aprovados | Resultado de probe não é feature operacional | Manter como evidência exploratória, não worker de produção |

Varredura SHA-256 dos Python versionados não encontrou grupos de arquivos
não-`__init__` byte a byte idênticos. **Duplicação aqui é de responsabilidade/
semântica**, não alegação de cópias idênticas.
Cinco arquivos não passaram no parse AST: cópias `main-mlisboa17.py`,
`dependencies-mlisboa17.py`, exemplos da raiz e `src/presentation/components/charts.py`.
Não pertencem todos ao app principal; não foram corrigidos nem executados.
Não declarar código morto apenas por uma busca sem referências: há imports
dinâmicos e entrypoints alternativos. O inventário mostra “não montado no principal”
quando isso é o que a evidência realmente permite afirmar.

## 13. Top 10 REUSE

| Prioridade | Reusar | Por quê / condição |
|---|---|---|
| 1 | webposto_integration.http.paginar + configuração Unidade | Já serve caixa/comercial, escopo e paginação; adicionar só adapter específico após verificar contrato |
| 2 | ResultadoDiario / Proveniencia / persistência e saude_robo | Base para release/frescor/replay; adaptar retenção/revisão sem criar motor paralelo |
| 3 | buscar_contexto_vendas + identificar_caixa + nomes | Reconstrói item/venda/caixa/responsável e texto humano, evitando novo grafo heurístico |
| 4 | extrato_reader + ContaExtratoConfig + FITID | Parser comprovado; usar seleção segura por conta, não resolver amplo de arquivos |
| 5 | explicar_falta / tabela_falta | Aritmética única relatório/tela/resumo; ampliar evidência, não duplicar cálculo |
| 6 | mais_pagamentos.comparar e total declarado | Resolve o gap enquanto não há API; adaptar trilha de revisão e detalhe antes de atribuir |
| 7 | models/rules de recebimentos e CartaoErp | NSU/nsuTef/autorização e estados existentes; não presumir TEF/dinâmico |
| 8 | Repositório pendencias e conferência local | Eventos/escopo/decisão humana já existem |
| 9 | SDK catálogo + serviços item/estoque existentes | Material para conveniência; validar equivalente V1, completude e custos |
| 10 | Registry antigo como modelo conceitual de inventário/maturidade | Útil para documentação de contratos; adaptar catálogo atual, nunca transportar política/unidades/status sem prova |

## 14. Gaps reais

1. Release aprovada fora do workspace, alinhamento do agendamento, execução sem
   dependência de sessão quando aprovada, saúde vinculada ao exit code/frescor.
2. Replay offline de evidência congelada com cadeia de proveniência completa;
   snapshot diário substituível não basta para reproduzir toda conferência.
3. Conveniência: integração V1 de extrato/contagem/itens de entrada e regras
   conferidas de cancelamento, ajuste, unidade de compra e instante de estoque.
4. Combustível: cadastros e eventos físicos de bico/bomba/tanque, medições e
   descargas, exceções operacionais e histórico temporal. Não falta OpenAPI.
5. Integrações efetivas de Cielo/Rede e API automática Mais Pagamentos; configuração
   pendente não deve virar KPI zero.
6. Validação operacional positiva de casamento PIX CNPJ, dos receptores novos,
   de inclusão/compensação do piloto e nova tentativa; manter congelamento.
7. Revisão de fronteiras de escrita de superfícies legadas/proxies e seus retries,
   sem pressupor que flags do piloto as governam.
8. Mapas de campo oficiais com incongruências documentais resolvidas por amostra
   conferida: vendaItemCodigo, bico textual/idVenda, tipos e arrays.
9. Histórico de revisão de total manual e isolamento rigoroso de extratos por
   unidade nos fluxos de despesas/baixa.
10. Documento único de entrypoints efetivamente publicados e consumers de cada
    versão. Este inventário é a base, não prova de tráfego de todas as rotas.

Não são gaps: começar um novo parser OFX, outro reconciliador de caixa, outro
formatador de caixa ou outro cliente HTTP genérico. **REUSE > ADAPT > CREATE.**

## 15. Top 10 riscos

Riscos operacionais/de integridade; não é pentest nem classificação de
vulnerabilidades exploráveis. Evidência estática não significa exploração real.

| # | Risco | Evidência | Impacto / próximo passo, sem executar |
|---|---|---|---|
| 1 | Robô falha, envio pode parecer sucesso | Task result 1, bloqueio no log e fluxo main sem condicionar envio ao sucesso | Dado antigo apresentado como atual; primeiro corrigir contrato de execução/frescor em tarefa futura |
| 2 | Produção executa checkout em desenvolvimento | WorkingDirectory no workspace, sem pasta production | Mudança não aprovada entra no job; release/tag e rollback |
| 3 | Escrita não congelada globalmente | SDK/proxies/CRUD remoto sem guardas do piloto | Não iniciar superfícies alternativas; inventariar política central antes de qualquer liberação |
| 4 | Retry de escrita/fallback para segundo POST | HTTPClient allowed_methods e produto_crud except amplo | Duplicação potencial; não usar retry genérico para lançamento |
| 5 | Evidência substituível impede replay | JSON unidade/dia e total manual sobrescritos; raw incompleto | Guardar versão/instante/hash/revisões fora do Git |
| 6 | Importação OFX com sinal não homologado | Incidente registrado do 17B, débito bloqueado no fluxo atual | Não tratar 201 como conferência; aguardar contrato e validação humana |
| 7 | Seleção/normalização pode cruzar escopos | Despesas/baixa resolvem arquivos amplamente; múltiplos nomes/versions de clientes | Conta/unidade explícita e teste de isolamento antes de ampliar |
| 8 | Mesmo nome não é mesma entidade/semântica | Caixa operador x frentista; NSU x nsuTef; singular x V1; compra/nota | Falsa atribuição ou reconciliação; validar joins e exceções |
| 9 | Segurança operacional varia por entrypoint | Leitor manual de env no gateway alternativo; proxies retornam URL; SDK registra URL em erro | Não importar/executar durante auditoria; revisão específica futura, sem reproduzir segredos |
| 10 | Falsa conclusão de maturidade | 200 declarações não simultâneas; dados ausentes viram zero em partes legadas; snapshots velhos | Classificar por evidência, expor indisponibilidade, não inferir prontidão por código/teste isolado |

## 16. Achados que mudam nossa visão

**ACHADO QUE MUDA NOSSA VISÃO:** o job real já usa a composição nova por
encaminhamento, mas a tarefa continua registrada com o módulo antigo e roda
diretamente do workspace, não de produção isolada.

**ACHADO QUE MUDA NOSSA VISÃO:** “Telegram envio=ok” coexistiu com coleta bloqueada;
não comprova que a auditoria do dia rodou. Estado e envio têm contratos diferentes.

**ACHADO QUE MUDA NOSSA VISÃO:** o golden case já tem teste sintético preciso,
porém o snapshot operacional antigo do mesmo dia tem outro instante/valor e não
possui os campos de evidência da Sprint 19. Não é ainda replay raw formal.

**ACHADO QUE MUDA NOSSA VISÃO:** já há API V1 documentada para contagem, histórico
de estoque, notas/itens de entrada, bicos/bombas/medições/descargas; o gap é
integração e validação, não indisponibilidade presumida de API.

**ACHADO QUE MUDA NOSSA VISÃO:** COMPRAS, COMPRA_ITENS e VALES não são os nomes
literais dessa especificação; usar NOTAS_ENTRADA, NOTAS_ENTRADA/ITENS e
VALES_FUNCIONARIO, sem inventar aliases.

**ACHADO QUE MUDA NOSSA VISÃO:** o registry antigo não é mais maduro em todas as
áreas: classifica V1 só como descoberta e traz política de unidades incompatível
com a configuração atual. Reaproveitável como catálogo, não como fonte de verdade.

**ACHADO QUE MUDA NOSSA VISÃO:** cartão/OFX têm travas próprias, mas o repositório
contém outros writers e proxies que não passam por elas. “Somente leitura” é a
regra desta tarefa e dos fluxos específicos, não propriedade global demonstrada.

**ACHADO QUE MUDA NOSSA VISÃO:** PostoAPIClient “v1” usa paths legados, e
“*_REDE” no gateway não é integração com a adquirente Rede.

### Decisões não tomadas e próximo passo

Nenhuma nova arquitetura, refatoração, bugfix, alteração de flag, endpoint,
dependência, dado financeiro, job, cadastro de tarefa, deploy, tag, merge ou
autorização de escrita foi realizada. Não se copiou legado e não se promoveu
capacidade a validada somente por existir.

Próxima implementação proposta, sujeita a decisão do diretor: **isolar release e
provar saúde/frescor do job das 03:00**, com replay sintético/formal do golden case
e evidência de versão, reutilizando entrypoint, proveniência e testes existentes.
Depois, uma amostra read-only autorizada fecha os joins V1 de conveniência.

### Verificação documental final

- Inventário extraído sem executar/importar aplicação ou catálogo legado.
- Nenhum request real GET/POST/PUT/PATCH/DELETE efetuado nesta auditoria.
- Nenhum `.env` foi lido, impresso ou editado; nenhum segredo ou raw real foi
  copiado ao relatório. Casos financeiros acima são os critérios já fornecidos.
- Únicas alterações confirmadas: este relatório e STATUS; o diff final confirma
  a ausência de alteração funcional e preserva o untracked preexistente.
- Sem testes funcionais novos/reexecução, pois o escopo é exclusivamente
  documental; checagens finais: contagem dos inventários, links locais e diff.
