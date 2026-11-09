# Catálogo da API de Integração webPosto (Quality Automação)

Gerado por `WebPosto_API/scripts/webposto_catalogo.py` em 09/11/2026.
OpenAPI: `openapi_integracao_2026-11-09.json` (168 rotas). Sondagem: `sondagem_2026-11-09_74014.json`
(91 leituras responderam com dados ou vazio sem erro).

Este arquivo é para pessoas e para qualquer IA: leia as **Regras** antes de propor qualquer chamada.

## Regras (o que podemos e o que não podemos)

1. **Base:** `https://web.qualityautomacao.com.br`. Autenticação: parâmetro de query `CHAVE` em toda chamada. Não há header nem OAuth.
2. **A chave "Api Integração" vê a rede inteira.** Ela não fica restrita à empresa que a gerou: consulta qualquer
   `empresaCodigo` da rede (confirmado em 08/11/2026). Tratar como segredo da rede, nunca colocar em URL de log,
   planilha, chat ou repositório. Chaves restritas só existem para integrações específicas (Equals, GAIA).
3. **Leitura (GET) é livre** para integrações e BI. Use sempre `empresaCodigo`, período curto e paginação.
4. **Escrita (POST/PUT/PATCH/DELETE) mexe no ERP de produção.** No LOGOS e no Logos Match, a escrita está
   **congelada**: só com aprovação explícita do diretor, por operação. Não existe ambiente de homologação
   documentado; testar escrita significa gravar em produção.
5. **Paginação:** `ultimoCodigo` + `limite` (rotas V1; máximo usual 2.000). Envelope `{"ultimoCodigo", "resultados": []}`.
   Repetir a chamada passando o `ultimoCodigo` devolvido até vir lista vazia ou cursor nulo.
6. **Datas:** `AAAA-MM-DD` nos filtros. Fuso do negócio: America/Recife.
7. **Rotas legadas** (sem `/V1/`) usam outros nomes de parâmetro (`pagina`, `filial`). Prefira as `/V1/`.
8. **Documentação muda sem aviso:** entre 06/10 e 09/11/2026 entraram 21 rotas, saíram 9 e 14 mudaram.
   Rode `baixar` + `sondar` + `gerar` antes de começar uma integração nova.
9. A OpenAPI não documenta limite de requisições. Use pausa entre chamadas (a sondagem usa 0,4 s) e evite
   rodar sincronizações grandes em horário de pico do posto.

## Leituras (GET)

| Rota | Para que serve | Filtros | Teste real |
|---|---|---|---|
| `/INTEGRACAO/APRIX_CUSTO` |  | DATA_INICIAL, DATA_FINAL | ❌ HTTP 500: Filial não utiliza o Aprix. |
| `/INTEGRACAO/APRIX_MOVIMENTO` |  | DATA_INICIAL, DATA_FINAL | ❌ HTTP 500: Filial não utiliza o Aprix. |
| `/INTEGRACAO/APRIX_PRECO_CLIENTE` |  |  | ❌ HTTP 500: Filial não utiliza o Aprix. |
| `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/CLIENTES` |  | cnpjCpf | ⏸ precisa de cnpjCpf |
| `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/ENVIAR_PENDENTE/{unidade}` |  |  | ⚠ GET com nome de ação, não testado |
| `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/STATUS` |  | pedidos | ✅ 0 reg · 191 ms |
| `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/{id}` |  |  | ⏸ precisa de id |
| `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/{id}/XML` |  |  | ⏸ precisa de id |
| `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/{id}/XML_DIRETO` |  |  | ⏸ precisa de id |
| `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PRODUTOS` |  |  | ✅ 5 reg · 210 ms |
| `/INTEGRACAO/RELATORIO/MAPA_DESEMPENHO` |  | dataInicial, dataFinal, funcionario, grupoProduto, subGrupoProduto, produto, usaDadoPremiacao, baseComissao, referenciaF | ❌ HTTP 500: Tipo não suportado. |
| `/INTEGRACAO/RELATORIO/PRODUTIVIDADE_FUNCIONARIO` |  | tipoRelatorio, tipoData, funcionario, produto, caixa, dataInicial, dataFinal, ordenacao, referenciaFuncionario, grupoPro | ❌ HTTP 500: Tipo não suportado. |
| `/INTEGRACAO/RELATORIO/RELATORIO_PERSONALIZADO/{relatorioCodigo}` |  | cliente, dataInicial, dataFinal, caixa, funcionario, grupoProduto, administradora, situacaoReceber, filial, produto, dis | ⏸ precisa de relatorioCodigo |
| `/INTEGRACAO/RELATORIO/VENDA_PERIODO` |  | cupomCancelado, ordenacaoPor, agrupamentoPor, prazo, turno, horaAcompanhaData, dataInicial, dataFinal, horaInicial, hora | ❌ HTTP 500: Tipo não suportado. |
| `/INTEGRACAO/V1/ABASTECIMENTOS` |  | dataInicial, dataFinal, dataHoraAtualizacao, tipoData, ultimoCodigo, afericao, limite, empresaCodigo | ✅ 5 reg · 396 ms |
| `/INTEGRACAO/V1/ABASTECIMENTOS_ENCERRANTE` |  | encerrante, data | ⏸ precisa de encerrante |
| `/INTEGRACAO/V1/ADIANTAMENTOS_FORNECEDORES` |  | fornecedorCodigo, empresaCodigo, tipoAdiantamento, dataInicial, dataFinal, ultimoCodigo, limite | ✅ 0 reg · 187 ms |
| `/INTEGRACAO/V1/ADMINISTRADORAS` |  | administradoraCodigo, empresaCodigo, administradoraCodigoExterno, ativo, remessaIndividual, ultimoCodigo, limite | ✅ 5 reg · 195 ms |
| `/INTEGRACAO/V1/AUDITORIA` |  | dataInicial, dataFinal, filiais, usuarios, operacao, origens, limite | ❌ HTTP 400: ["Failed to convert value of type 'java.lang.String' to requ |
| `/INTEGRACAO/V1/BICOS` |  | bicoCodigo, empresaCodigo, ultimoCodigo, limite | ✅ 5 reg · 188 ms |
| `/INTEGRACAO/V1/BOMBAS` |  | bombaCodigo, empresaCodigo | ✅ 5 reg · 163 ms |
| `/INTEGRACAO/V1/BRINDES` |  | brindeCodigo, ultimoCodigo, limite | ✅ 0 reg · 155 ms |
| `/INTEGRACAO/V1/CAIXAS` |  | dataInicial, dataFinal, turno, empresaCodigo, individual, ultimoCodigo, limite, dataHoraAtualizacao | ✅ 5 reg · 162 ms |
| `/INTEGRACAO/V1/CAIXAS_APRESENTADO` |  | dataInicial, dataFinal, dataHoraAtualizacao, tipoData, ultimoCodigo, limite | ✅ 5 reg · 165 ms |
| `/INTEGRACAO/V1/CARTOES` |  | turno, empresaCodigo, dataInicial, dataFinal, apenasPendente, dataFiltro, dataHoraAtualizacao, ultimoCodigo, limite, ven | ✅ 5 reg · 286 ms |
| `/INTEGRACAO/V1/CARTOES_CLUBGAS` |  | nomeTabela | ⏸ precisa de nomeTabela |
| `/INTEGRACAO/V1/CARTOES_COMPRA` |  | cartaoCompraCodigo, empresaCodigo, ultimoCodigo, limite | ✅ 0 reg · 180 ms |
| `/INTEGRACAO/V1/CARTOES_PAGAR` |  | empresaCodigo, dataInicial, dataFinal, tipoData, cartaoCompraCodigo, situacao, autorizacao, ultimoCodigo, limite | ❌ HTTP 400: ["Tipo de data não informado."] |
| `/INTEGRACAO/V1/CARTOES_REMESSA` |  | empresaCodigo, dataInicial, dataFinal, vendaCodigo, ultimoCodigo, limite, quitado, dataHoraAtualizacao, origem, cartaoRe | ✅ 0 reg · 350 ms |
| `/INTEGRACAO/V1/CENTROS_CUSTO` |  | centroCustoCodigoExterno, ultimoCodigo, limite | ✅ 5 reg · 156 ms |
| `/INTEGRACAO/V1/CHEQUES` |  | turno, empresaCodigo, dataInicial, dataFinal, apenasPendente, dataFiltro, ultimoCodigo, limite, dataHoraAtualizacao, ven | ✅ 0 reg · 282 ms |
| `/INTEGRACAO/V1/CHEQUES_PAGAR` |  | empresaCodigo, dataInicial, dataFinal, tipoData, situacao, chequeTroco, chequeCodigo, contaCodigo, caixaCodigo, tipoIncl | ❌ HTTP 400: ["Tipo de data não informado."] |
| `/INTEGRACAO/V1/CLIENTES` |  | clienteCodigoExterno, clienteCodigo, empresaCodigo, retornaObservacoes, dataHoraAtualizacao, frota, faturamento, limites | ✅ 5 reg · 249 ms |
| `/INTEGRACAO/V1/CLIENTES_EMPRESA` |  | ultimoCodigo, limite | ✅ 5 reg · 224 ms |
| `/INTEGRACAO/V1/CLIENTES_FROTA` |  | clienteCodigoExterno, clienteCodigo, motoristaCodigo, ultimoCodigo, limite | ✅ 5 reg · 245 ms |
| `/INTEGRACAO/V1/CONSUMO_CLIENTES` |  | token, dataInicial, dataFinal, ultimoCodigo, limite | ⏸ precisa de token |
| `/INTEGRACAO/V1/CONTAGEM_ESTOQUES` |  | dataContagem, contagemReferencia, ultimoCodigo, limite | ✅ 0 reg · 145 ms |
| `/INTEGRACAO/V1/CONTAS` |  | empresaCodigo, ultimoCodigo, limite | ✅ 5 reg · 165 ms |
| `/INTEGRACAO/V1/DESPESAS_FINANCEIRO_REDE` |  | dataInicial, dataFinal, apuracaoCaixa | ✅ 447 reg · 695 ms |
| `/INTEGRACAO/V1/DFE_XMLS` |  | modeloDocumento, numeroDocumento, empresaCodigo, serieDocumento | ❌ HTTP 400: ["Obrigatório informar o número da DANFE.","Obrigatório info |
| `/INTEGRACAO/V1/DRES` |  | apuracaoCaixa, dataInicial, dataFinal, cfopOutrasSaidas, apurarJurosDescontos, filiais, centroCustoCodigo, apurarCentroC | ✅ None reg · 588 ms |
| `/INTEGRACAO/V1/DUPLICATAS` |  | dataInicial, dataFinal, dataHoraAtualizacao, apenasPendente, dataFiltro, ultimoCodigo, limite, empresaCodigo, notaEntrad | ✅ 0 reg · 242 ms |
| `/INTEGRACAO/V1/EMPRESAS` |  | empresaCodigoExterno, ultimoCodigo, limite | ✅ 2 reg · 240 ms |
| `/INTEGRACAO/V1/ESTOQUES` |  | empresaCodigo, estoqueCodigoExterno, dataHoraAtualizacao, estoqueCodigo, ultimoCodigo, limite | ✅ 2 reg · 153 ms |
| `/INTEGRACAO/V1/ESTOQUES_PERIODO` |  | dataFinal, empresaCodigo, dataHoraAtualizacao, ultimoCodigo, limite | ✅ 5 reg · 186 ms |
| `/INTEGRACAO/V1/FINANCEIROS_EXCLUSAO` |  | empresaCodigo, dataHoraInicial, dataHoraFinal, ultimoCodigo, limite | ✅ 12 reg · 191 ms |
| `/INTEGRACAO/V1/FORMAS_PAGAMENTO` |  | ultimoCodigo, limite | ✅ 5 reg · 238 ms |
| `/INTEGRACAO/V1/FORNECEDORES` |  | retornaObservacoes, dataHoraAtualizacao, fornecedorCodigoExterno, fornecedorCodigo, cnpjCpf, empresaCodigo, ultimoCodigo | ✅ 5 reg · 155 ms |
| `/INTEGRACAO/V1/FUNCIONARIOS` |  | funcionarioCodigo, empresaCodigo, ultimoCodigo, limite | ✅ 5 reg · 163 ms |
| `/INTEGRACAO/V1/FUNCIONARIOS_IDENTFID` |  |  | ✅ 13 reg · 244 ms |
| `/INTEGRACAO/V1/FUNCIONARIOS_META` |  | grupoMetaCodigo, ultimoCodigo, limite | ✅ 0 reg · 322 ms |
| `/INTEGRACAO/V1/FUNCOES` |  | ultimoCodigo, limite | ✅ 5 reg · 209 ms |
| `/INTEGRACAO/V1/GRUPOS` |  | grupoCodigoExterno, ultimoCodigo, limite | ✅ 5 reg · 162 ms |
| `/INTEGRACAO/V1/GRUPOS_CLIENTE` |  | grupoCodigo, grupoCodigoExterno, ultimoCodigo, limite | ✅ 2 reg · 145 ms |
| `/INTEGRACAO/V1/GRUPOS_META` |  | ultimoCodigo, limite | ✅ 0 reg · 212 ms |
| `/INTEGRACAO/V1/ICMS` |  | ultimoCodigo, limite | ✅ 5 reg · 438 ms |
| `/INTEGRACAO/V1/LANCAMENTOS_CONTABEIS` |  | empresaCodigo, dataInicial, dataFinal, dataHoraAtualizacao, ultimoCodigo, limite, loteContabil | ✅ 0 reg · 410 ms |
| `/INTEGRACAO/V1/LMCS` |  | empresaCodigo, dataInicial, dataFinal, dataHoraAtualizacao, ultimoCodigo, limite | ✅ 5 reg · 155 ms |
| `/INTEGRACAO/V1/LMCS_REDE` |  | empresaCodigo, dataInicial, dataFinal, dataHoraAtualizacao, ultimoCodigo, limite | ✅ 5 reg · 208 ms |
| `/INTEGRACAO/V1/MAPAS_DESEMPENHO` |  | empresaCodigo, dataInicial, dataFinal, vendaCodigo, ultimoCodigo, limite, quitado, dataHoraAtualizacao, origem, cartaoRe | ✅ 74 reg · 291 ms |
| `/INTEGRACAO/V1/MOVIMENTACOES_CAIXA` |  | caixaCodigo, empresaCodigo, funcionarioCodigo, tipo, ultimoCodigo, limite | ❌ HTTP 400: ["Caixa não informado."] |
| `/INTEGRACAO/V1/MOVIMENTOS_CONTA` |  | empresaCodigo, dataInicial, dataFinal, ultimoCodigo, limite, mostraSaldo, dataHoraAtualizacao, documentoOrigemCodigo, ti | ✅ 5 reg · 176 ms |
| `/INTEGRACAO/V1/NFCES` |  | empresaCodigo, dataInicial, dataFinal, vendaCodigo, ultimoCodigo, limite, situacao | ✅ 5 reg · 219 ms |
| `/INTEGRACAO/V1/NFCES/{id}/XMLS` |  | modeloDocumento, numeroDocumento, empresaCodigo, serieDocumento | ⏸ precisa de id |
| `/INTEGRACAO/V1/NOTAS_ENTRADA` |  | turno, empresaCodigo, dataInicial, dataFinal, tipoData, notaSerie, notaNumero, ultimoCodigo, limite, vendaCodigo, situac | ✅ 5 reg · 240 ms |
| `/INTEGRACAO/V1/NOTAS_ENTRADA/ITENS` |  | turno, empresaCodigo, usaProdutoLmc, compraCodigo, notaEntradaCodigo, dataInicial, dataFinal, tipoData, ultimoCodigo, li | ✅ 5 reg · 202 ms |
| `/INTEGRACAO/V1/NOTAS_ENTRADA/XML/{chaveNfe}` |  |  | ⏸ precisa de chaveNfe |
| `/INTEGRACAO/V1/NOTAS_MANIFESTACAO` |  | dataInicial, dataFinal, compraCodigo, empresaCodigo, manifestacaoCodigo, ultimoCodigo, limite | ✅ 5 reg · 285 ms |
| `/INTEGRACAO/V1/NOTAS_SAIDA` |  | chaveDocumento, dataInicial, dataFinal, empresaCodigo, ultimoCodigo, limite, situacao, numeroDocumento, serieDocumento,  | ✅ 1 reg · 152 ms |
| `/INTEGRACAO/V1/NOTAS_SAIDA/XMLS` |  | id, modeloDocumento, numeroDocumento, empresaCodigo, serieDocumento, situacao | ❌ HTTP 400: Quando o ID da nota não for informado, é necessário informar |
| `/INTEGRACAO/V1/NOTAS_SAIDA_ITENS` |  | dataInicial, dataFinal, empresaCodigo, ultimoCodigo, limite, notaCodigo, notaItemCodigo | ✅ 1 reg · 253 ms |
| `/INTEGRACAO/V1/NOTAS_SERVICO` |  | empresaCodigo, dataInicial, dataFinal, fornecedorCodigo, clienteCodigo, nfseCodigo, rps, tipoNota, ultimoCodigo, limite | ✅ 0 reg · 207 ms |
| `/INTEGRACAO/V1/NOTAS_SERVICOS/ITENS` |  | empresaCodigo, dataInicial, dataFinal, nfseCodigo, produtoCodigo, ultimoCodigo, limite | ✅ 0 reg · 201 ms |
| `/INTEGRACAO/V1/PDVS` |  | pdvReferencia, pdvCodigo, empresaCodigo, ultimoCodigo, limite | ✅ 5 reg · 161 ms |
| `/INTEGRACAO/V1/PDVS_CONFIGURACAO` |  | cdPdv | ⏸ precisa de cdPdv |
| `/INTEGRACAO/V1/PEDIDOS_TRR` |  | empresaCodigo, dataInicial, dataFinal, ultimoCodigo, limite, pedidoCodigo | ✅ 0 reg · 237 ms |
| `/INTEGRACAO/V1/PIS_COFINS` |  | ultimoCodigo, limite | ✅ 5 reg · 160 ms |
| `/INTEGRACAO/V1/PLACARES` |  | dataInicial, dataFinal | ✅ 0 reg · 648 ms |
| `/INTEGRACAO/V1/PLANOS_CONTA_CONTABIL` |  | ultimoCodigo, limite | ✅ 0 reg · 264 ms |
| `/INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL` |  | planoContaCodigo, ultimoCodigo, limite | ✅ 5 reg · 159 ms |
| `/INTEGRACAO/V1/PRAZOS` |  | prazoCodigo, prazoCodigoExterno | ✅ 21 reg · 156 ms |
| `/INTEGRACAO/V1/PRECOS_IDENTIFID` |  |  | ✅ None reg · 156 ms |
| `/INTEGRACAO/V1/PREMIACOES` |  | codigoPremiacao | ✅ 1 reg · 167 ms |
| `/INTEGRACAO/V1/PREMIACOES/MOVIMENTOS` |  | dataInicial, dataFinal, clienteCodigo, empresaCodigo, ultimoCodigo, limite | ✅ 0 reg · 174 ms |
| `/INTEGRACAO/V1/PREMIACOES_CLIENTES` |  | premiacaoCodigo, clienteCodigo, empresaCodigo | ✅ 0 reg · 163 ms |
| `/INTEGRACAO/V1/PRODUTOS` |  | empresaCodigo, produtoCodigo, produtoCodigoExterno, grupoCodigo, ativo, usaProdutoLmc, ultimoCodigo, limite | ✅ 5 reg · 150 ms |
| `/INTEGRACAO/V1/PRODUTOS_EMPRESA` |  | dataHoraAtualizacao, ativo, empresaCodigo, produtoCodigo, usaProdutoLmc, ultimoCodigo, limite | ✅ 5 reg · 197 ms |
| `/INTEGRACAO/V1/PRODUTOS_ESTOQUES` |  | empresaCodigo, dataHora, grupoCodigo, produtoCodigo, ultimoCodigo, limite | ✅ 5 reg · 313 ms |
| `/INTEGRACAO/V1/PRODUTOS_ESTOQUE_EXTRATO` |  | produtoCodigo, empresaCodigo, dataInicial, dataInicialCompra, exibeHistoricoCompra | ✅ 4809 reg · 342 ms |
| `/INTEGRACAO/V1/PRODUTOS_ESTOQUE_PARADO` |  | empresaCodigo, dataInicial | ✅ 8 reg · 353 ms |
| `/INTEGRACAO/V1/PRODUTOS_LMC_LMP` |  | codigoProdutLmc | ✅ 8 reg · 271 ms |
| `/INTEGRACAO/V1/PRODUTOS_META` |  | grupoMetaCodigo, ultimoCodigo, limite | ✅ 0 reg · 210 ms |
| `/INTEGRACAO/V1/RELATORIOS_PERSONALIZADOS` |  | ultimoCodigo, limite | ✅ 1 reg · 166 ms |
| `/INTEGRACAO/V1/SANGRIAS_CAIXA` |  | dataInicial, dataFinal, dataHoraAtualizacao, empresaCodigo, caixaCodigo, funcionarioCodigo, ultimoCodigo, limite | ✅ 5 reg · 244 ms |
| `/INTEGRACAO/V1/SATS` |  | empresaCodigo, dataInicial, dataFinal, vendaCodigo, ultimoCodigo, limite, quitado, dataHoraAtualizacao, origem, cartaoRe | ❌ HTTP 400:  |
| `/INTEGRACAO/V1/SUB_GRUPOS_REDE` |  |  | ✅ 30 reg · 373 ms |
| `/INTEGRACAO/V1/TABELA_PRECOS_PRAZO` |  | tabelaPrecoPrazoCodigo, ultimoCodigo, limite | ✅ 1 reg · 301 ms |
| `/INTEGRACAO/V1/TANQUES` |  | tanqueCodigo, empresaCodigo, ultimoCodigo, limite | ✅ 5 reg · 219 ms |
| `/INTEGRACAO/V1/TANQUE_ENTRADA` |  | data, tanqueCodigo | ✅ 4 reg · 256 ms |
| `/INTEGRACAO/V1/TANQUE_MEDIDA` |  | data, tanqueCodigo | ✅ 4 reg · 294 ms |
| `/INTEGRACAO/V1/TITULOS_PAGAR` |  | dataInicial, dataFinal, dataHoraAtualizacao, apenasPendente, dataFiltro, ultimoCodigo, limite, empresaCodigo, notaEntrad | ✅ 5 reg · 230 ms |
| `/INTEGRACAO/V1/TITULOS_PAGAR_UNIFICADOS` |  | dataInicial, dataFinal, dataFiltro, tituloPagarOrigemCodigo, tituloPagarCodigo, ultimoCodigo, limite | ✅ 0 reg · 168 ms |
| `/INTEGRACAO/V1/TITULOS_RECEBER` |  | turno, empresaCodigo, dataInicial, dataFinal, dataHoraAtualizacao, apenasPendente, codigoDuplicata, dataFiltro, ultimoCo | ✅ 2 reg · 371 ms |
| `/INTEGRACAO/V1/TROCAR_PRECOS` |  | dataInicial, dataFinal, realizada, tipoProduto, empresaCodigo, ultimoCodigo, limite | ✅ 5 reg · 276 ms |
| `/INTEGRACAO/V1/USUARIOS` |  | ultimoCodigo, limite | ✅ 5 reg · 211 ms |
| `/INTEGRACAO/V1/USUARIOS_EMPRESA` |  | ultimoCodigo, limite | ✅ 5 reg · 162 ms |
| `/INTEGRACAO/V1/VALES_CLIENTES` |  | dataInicial, dataFinal, empresaCodigo, dataHoraAtualizacao, ultimoCodigo, limite | ✅ 0 reg · 411 ms |
| `/INTEGRACAO/V1/VALES_FUNCIONARIO` |  | empresaCodigo, dataInicial, dataFinal, vendaCodigo, ultimoCodigo, limite, quitado, dataHoraAtualizacao, origem, cartaoRe | ✅ 5 reg · 166 ms |
| `/INTEGRACAO/V1/VENDAS` |  | turno, empresaCodigo, dataInicial, dataFinal, dataHoraAtualizacao, modeloDocumento, tipoData, ultimoCodigo, limite, vend | ✅ 5 reg · 260 ms |
| `/INTEGRACAO/V1/VENDAS/ITENS` |  | empresaCodigo, usaProdutoLmc, dataInicial, dataFinal, tipoData, ultimoCodigo, limite, vendaCodigo, dataHoraAtualizacao | ✅ 5 reg · 181 ms |
| `/INTEGRACAO/V1/VENDAS/ITENS/FIDELIDADE` |  | vendaItemVoucherCodigo, vendaItemCodigo, tipoIntegracaoVoucher, ultimoCodigo, limite | ❌ HTTP 400: [" Informe o vendaItemVoucherCodigo ou listaVendaItemCodigo. |
| `/INTEGRACAO/V1/VENDAS/{idList}` |  | vendasComDfe | ⏸ precisa de idList |
| `/INTEGRACAO/V1/VENDAS_FORMA_PAGAMENTO` |  | turno, empresaCodigo, dataInicial, dataFinal, dataHoraAtualizacao, modeloDocumento, tipoData, ultimoCodigo, limite, vend | ✅ 5 reg · 229 ms |
| `/INTEGRACAO/V1/VENDAS_RESUMO` |  | empresaCodigo, dataInicial, dataFinal, situacao | ✅ 8 reg · 322 ms |
| `/INTEGRACAO/V1/VENDA_CLIENTE` |  | clienteCodigo, dataInicial, dataFinal | ✅ 910 reg · 241 ms |
| `/INTEGRACAO/V1/VENDA_PRODUTO` |  | produtoCodigo, dataInicial, dataFinal | ✅ 2235 reg · 310 ms |
| `/INTEGRACAO/V1/WEBHOOKS` | Lista os webhooks configurados para a filial |  | ❌ HTTP 412: Para utilizar webhooks, entre em contato com o comercial. |
| `/INTEGRACAO/V2/PRODUTOS_ESTOQUE_EXTRATO` |  | produtoCodigo, empresaCodigo, dataInicialMovimentacao, dataInicialCompra, exibeHistoricoMovimentacao, exibeHistoricoComp | ✅ 5 reg · 237 ms |
| `/INTEGRACAO/V2/TRANSFERENCIAS_BANCARIAS` |  | empresaCodigo, dataInicial, dataFinal, vendaCodigo, tipoInclusao, contaCodigo, ultimoCodigo, limite | ✅ 5 reg · 257 ms |
| `/INTEGRACAO/V2/VENDAS/{idList}` |  | vendasComDfe | ⏸ precisa de idList |

## Escritas (não chamar sem aprovação)

| Método | Rota | Para que serve |
|---|---|---|
| POST | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS` |  |
| DELETE | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/{id}` |  |
| POST | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/{id}/DANFE` |  |
| POST | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/{id}/FATURAR` |  |
| PUT | `/INTEGRACAO/PEDIDO_COMBUSTIVEL/V1/PEDIDOS/{id}/RECEBER_TITULO_EM_CARTAO` |  |
| POST | `/INTEGRACAO/V1/ALTERACOES_PRECO_COMBUSTIVEL` |  |
| DELETE | `/INTEGRACAO/V1/ARQUIVOS/{id}` |  |
| POST | `/INTEGRACAO/V1/ARQUIVOS/{tipoOrigem}/{origem}` |  |
| POST | `/INTEGRACAO/V1/AUTORIZAR_NFES_SAIDA/{notaCodigo}` |  |
| POST | `/INTEGRACAO/V1/AUTORIZA_PAGAMENTO_ABASTECIMENTOS` |  |
| POST | `/INTEGRACAO/V1/BRINDES` |  |
| POST | `/INTEGRACAO/V1/CARTOES` |  |
| DELETE | `/INTEGRACAO/V1/CARTOES/{id}` |  |
| PATCH | `/INTEGRACAO/V1/CARTOES/{id}` |  |
| POST | `/INTEGRACAO/V1/CARTOES_EDI_ARQUIVO_WEBPOSTO` |  |
| POST | `/INTEGRACAO/V1/CLIENTES` |  |
| POST | `/INTEGRACAO/V1/CLIENTES/{codigoCliente}/PRAZOS` |  |
| PUT | `/INTEGRACAO/V1/CLIENTES/{id}` |  |
| POST | `/INTEGRACAO/V1/CLIENTES_FROTA_VEICULO/{clienteCodigo}` |  |
| PUT | `/INTEGRACAO/V1/CLIENTES_FROTA_VEICULO/{clienteCodigo}/{clienteVeiculoCodigo}` |  |
| POST | `/INTEGRACAO/V1/CLIENTES_UNIDADE_NEGOCIO` |  |
| POST | `/INTEGRACAO/V1/DUPLICATAS/{duplicataCodigo}/RECEBER` |  |
| POST | `/INTEGRACAO/V1/ENVIOS_EMAIL` |  |
| POST | `/INTEGRACAO/V1/ENVIOS_WHATSAPP` |  |
| POST | `/INTEGRACAO/V1/FORNECEDORES` |  |
| POST | `/INTEGRACAO/V1/FORNECEDORES_UNIDADE_NEGOCIO` |  |
| POST | `/INTEGRACAO/V1/GRUPOS_CLIENTE` |  |
| PUT | `/INTEGRACAO/V1/GRUPOS_CLIENTE/{id}` |  |
| POST | `/INTEGRACAO/V1/IMENDES/CORRIGIR_PRODUTOS` |  |
| POST | `/INTEGRACAO/V1/LANCAMENTOS_CONTABEIS` |  |
| POST | `/INTEGRACAO/V1/MOVIMENTOS_CONTA` |  |
| PATCH | `/INTEGRACAO/V1/MOVIMENTOS_CONTA` |  |
| POST | `/INTEGRACAO/V1/OFXS` |  |
| POST | `/INTEGRACAO/V1/PEDIDOS_COMPRAS` |  |
| POST | `/INTEGRACAO/V1/PEDIDO_COMBUSTIVEL/CLIENTES` |  |
| POST | `/INTEGRACAO/V1/PRAZO_TABELA_PRECOS/{id}/ITENS` |  |
| DELETE | `/INTEGRACAO/V1/PRAZO_TABELA_PRECOS_ITENS/{id}` |  |
| POST | `/INTEGRACAO/V1/PRODUTOS` |  |
| PUT | `/INTEGRACAO/V1/PRODUTOS/{id}` |  |
| POST | `/INTEGRACAO/V1/PRODUTOS_COMISSAO` |  |
| POST | `/INTEGRACAO/V1/PRODUTOS_INVENTARIOS` |  |
| PUT | `/INTEGRACAO/V1/REAJUSTAR_ESTOQUES_PRODUTOS_COMBUSTIVEL` |  |
| POST | `/INTEGRACAO/V1/REAJUSTAR_PRODUTOS` |  |
| PUT | `/INTEGRACAO/V1/RECEBER_CARTOES` |  |
| PUT | `/INTEGRACAO/V1/RECEBER_CHEQUES` |  |
| PUT | `/INTEGRACAO/V1/RECEBER_TITULOS` |  |
| PUT | `/INTEGRACAO/V1/RECEBER_TITULOS_CONVERTIDOS` |  |
| PATCH | `/INTEGRACAO/V1/TABELA_PRECOS_PRAZO/{id}` |  |
| POST | `/INTEGRACAO/V1/TANQUE_MEDIDA` |  |
| POST | `/INTEGRACAO/V1/TITULOS_PAGAR` |  |
| PATCH | `/INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` |  |
| DELETE | `/INTEGRACAO/V1/TITULOS_PAGAR/{id}` |  |
| POST | `/INTEGRACAO/V1/TITULOS_RECEBER` |  |
| POST | `/INTEGRACAO/V1/TRANSFERENCIAS_BANCARIAS` |  |
| DELETE | `/INTEGRACAO/V1/TRANSFERENCIAS_BANCARIAS/{id}` |  |
| POST | `/INTEGRACAO/V1/TROCA_PRECOS_COMBUSTIVEIS` |  |
| POST | `/INTEGRACAO/V1/TROCA_PRECOS_PRODUTOS` |  |
| POST | `/INTEGRACAO/V1/VALES_CLIENTE` |  |
| POST | `/INTEGRACAO/V1/VERIFICAR_LANCAMENTO_CONTABIL_EXCLUIDO` |  |
| POST | `/INTEGRACAO/V1/WEBHOOKS` | Cadastra um novo webhook para a filial |
| PUT | `/INTEGRACAO/V1/WEBHOOKS/{id}` | Altera um webhook da filial |
| DELETE | `/INTEGRACAO/V1/WEBHOOKS/{id}` | Remove um webhook da filial |
| POST | `/INTEGRACAO/V2/PEDIDOS_COMPRAS` |  |
| PATCH | `/INTEGRACAO/V2/TITULOS_PAGAR/{id}` |  |
