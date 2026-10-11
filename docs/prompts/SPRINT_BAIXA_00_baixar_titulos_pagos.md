# Prompt — SPRINT BAIXA_00: o Logos dá baixa em títulos já pagos no banco (com barreira)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). `.env` só via `dotenv_values`/`load_dotenv`, **nunca imprimir nem editar**. Sem reescrever arquivos inteiros. Testes sintéticos com cliente falso (nenhum teste chama o webPosto real). Extratos reais em `C:\Projetos\LOGOS\extratos\` (somente leitura, nunca no Git); relatórios em `WebPosto_API/data/` (fora do Git). Rodar só os testes novos durante o trabalho e a bateria completa no final. Meta: ~30 min.

## Decisão do diretor (11/10/2026)

O arquiteto cruzou (somente leitura) os títulos a pagar do Doze 74014 com os extratos OFX: **12 títulos "Aberto" já foram pagos no BB (R$ 181.365,28)** — mesmo valor, nome do fornecedor no extrato, data perto do vencimento. O diretor pediu que **o Logos** dê a baixa. Regra: RN-ERP-003 em `docs/regras-negocio/REGRAS_DE_NEGOCIO.md` (ler inteira, inclusive "pagamento agrupado" e "mapa de contas do Doze").

@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py
@docs/regras-negocio/REGRAS_DE_NEGOCIO.md

## A API (spec oficial `docs/external/webposto/openapi_integracao_2026-10-06.json`)

- Leitura: `GET /INTEGRACAO/V1/TITULOS_PAGAR` (`empresaCodigo`, `dataInicial`, `dataFinal`, `tituloPagarCodigo`, `apenasPendente`, …). Campos úteis: `situacao` ("Aberto"/"Pago"), `valor`, `vencimento`, `nomeFornecedor`, `cpfCnpjFornecedor`, `pagamento[]` (`detalhe` = conta, `valor`, `dataPagamento`). `GET /INTEGRACAO/V1/CONTAS` para o `contaCodigo`.
- Escrita: `PATCH /INTEGRACAO/V1/TITULOS_PAGAR/PAGAR` com `PagarTituloDto` = `tituloPagarCodigo` (**array**), `contaCodigo`, `dataPagamento` (date). Resposta **204 sem corpo**. **Não há campo de valor** (paga o valor do título) e **não há rota para estornar baixa** (o `DELETE` apaga o título inteiro — **proibido**). `dataValida` e `pagamentoDataPosterior` não são documentados → **não enviar**.

## PARTE A — Encontrar os candidatos (somente leitura)

`application/titulos_pagos_sem_baixa.py` + comando `python -m src.jobs.baixar_titulos --unidade 74014` (padrão = **só prévia**):
1. Ler títulos (últimos 120 dias) e os OFX da unidade informados por `--extrato` (um ou mais arquivos).
2. Débitos já usados por títulos **pagos** (mesmo valor, `dataPagamento` ±1 dia) saem da disputa.
3. Candidato = título "Aberto", vencido, com **um único** débito de **valor exato**, data entre vencimento −10 e +40 dias e **nome do fornecedor no texto do extrato** (palavras ≥ 4 letras, sem acento). Valor exato sem nome → "conferir à mão" (não baixa). Dois títulos para o mesmo débito, ou dois débitos para o mesmo título → "ambíguo" (não baixa).
4. Conta da baixa pelo mapa da unidade em `units.json` (Doze: BB → conta "BANCO 24H - DOZE FILIAL"; PagBank → "PAGBANK DOZE FILIAL"), conferido com `V1/CONTAS`; sem correspondência única → não baixa. Data da baixa = data do débito no extrato.
5. Prévia no chat: título, fornecedor, plano de contas, vencimento, valor, banco, data e texto do débito, conta da baixa. Totais por grupo (pronto para baixar / conferir à mão / ambíguo). Pagamento agrupado (1 débito = vários títulos) **só aparece como "agrupado — conferir à mão"** nesta sprint.

## PARTE B — A barreira (tudo com teste)

1. Módulo isolado `adapters/webposto_escrita_titulos.py` com **uma única** função: `baixar_titulo`. Nenhuma outra escrita. `DELETE` de título proibido (teste falha se a rota aparecer no módulo).
2. Travas lidas **só do arquivo `.env`** (reaproveitar a função da 17B.1, generalizando o nome da trava): `WEBPOSTO_WRITES=1` **e** `LOGOS_BAIXA_TITULOS=1`; nome duplicado no arquivo → recusa. Acrescentar `LOGOS_BAIXA_TITULOS=0` só no `.env.example`.
3. **Um título por chamada** (array com exatamente 1 código). Envio só com `--confirmar --titulo <código>` (um título por comando) ou `--confirmar --todos` (só os "prontos para baixar", e **só depois** de um título ter sido baixado e conferido com sucesso — registrar isso no histórico).
4. **Antes de cada baixa**, reler o título: se não estiver mais "Aberto" ou o valor mudou → não baixa.
5. **Depois de cada baixa**, reler o título: tem de estar "Pago", com `pagamento[]` na conta e data enviadas e valor igual. Se não → **parar tudo** (não seguir para o próximo), registrar e mostrar "BAIXA COM DIVERGÊNCIA — CONFERIR NA TELA".
6. Anti-repetição: histórico append-only em `data/baixas_titulos/<empresa>/historico.json` (título, conta, data, débito do extrato usado, resposta, releitura); título ou débito já usados nunca são enviados de novo.
7. Limite por execução: no máximo **15 títulos** e **R$ 200.000,00**.

## PARTE C — Teste com o diretor

1. Rodar a prévia real do Doze com os extratos `C:\Projetos\LOGOS\extratos\BB\BB_Doze_Agosto_2026.ofx`, `...\BB\bancoBrasil_DozeFilial_Setembro_2026.ofx`, `...\BB\BB_Doze_Outubro2026.ofx.ofx` e `...\PAGBANK\PagBank_Doze_Outubro2026.ofx.ofx` e mostrar no chat. (Referência do arquiteto com agosto incluído: 12 prontos, R$ 181.365,28. Dois casos de mesmo valor com outro destinatário — frete Vibra R$ 300 × PIX para o Casa Caiada e SulAmérica R$ 3.500 × transferência — **não** podem ficar como prontos.)
2. **Parar e pedir ao diretor** para ligar `WEBPOSTO_WRITES=1` e `LOGOS_BAIXA_TITULOS=1` no `.env` e dizer **qual título** baixar primeiro (sugerir o de menor valor). Só enviar depois do "ok" dele no chat.
3. Baixar **1 título**, reler e mostrar o antes/depois. Se a resposta for 401/403 → parar e informar (pedir permissão à Quality).
4. Só com novo "ok" do diretor: `--todos` para os demais prontos.
5. No final, lembrar o diretor de **voltar as duas travas para 0**.

Registrar na RN-ERP-003 o que foi implementado (status "vigente — baixa de títulos já pagos, Doze") e na ADR-003 a decisão. Atualizar o `STATUS.md`.
Commits: `feat(titulos): candidatos a baixa por extrato (somente leitura)` e `feat(titulos): baixa de título pago com barreira`. Depois `git push`.
