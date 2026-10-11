# Prompt — SPRINT 17B: o Logos importa extratos OFX no webPosto (Antigravity)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem trocar de branch, sem merge). `.env` só via `load_dotenv`, **nunca imprimir nem editar**; não reescrever arquivos inteiros; testes **sem chamar o webPosto real** (cliente falso); nada pelo Telegram. Extratos reais ficam em `C:\Projetos\LOGOS\extratos\` (somente leitura; nunca copiar para o Git). Meta: sprint curta (≈30 min), testes focados durante o trabalho e bateria completa no final.

## Decisão do diretor (11/10/2026)

"O Logos pega os extratos e implanta no webPosto. **Só vai entrar extrato OFX**, e **deve existir uma barreira**." O webPosto é o sistema principal dos 11 postos; o OFX do PagBank dá erro de conversão no webPosto — o Logos lê o arquivo, corrige e envia os lançamentos pela API.

## A API (spec oficial em `docs/external/webposto/openapi_integracao_2026-10-06.json`)

`POST /INTEGRACAO/V1/OFXS` — corpo `ParamIncluirOfx`: `cdConta`, `cdFilial`, `dataInicial`, `dataFinal`, `transacoes[]` (`TransacaoBancaria`: `tipo`, `valor`, `dataMovimento`, `dataCredito`, `descricao`, `numeroDocumento`, `nomePagador`, `tipoTransacao`, `extratoExterno`, …) e `opcaoImportacao` ∈ {`IMPORTAR_APENAS_DIAS_INEXISTENTES_SISTEMA`, **`EXCLUIR_DIAS_SISTEMA`**, **`IMPORTAR_DIAS_ARQUIVO`**}. Resposta 201. A spec **não documenta** os valores de `tipo`/`tipoTransacao` nem o sinal de `valor` — **não inventar**.

## A BARREIRA (obrigatória — tudo isto tem teste)

1. **Só OFX:** a função de importação aceita apenas arquivo `.ofx` (conteúdo começando por cabeçalho OFX); qualquer outro formato é recusado.
2. **Só esta escrita:** módulo isolado `adapters/webposto_escrita_ofx.py` com **uma única** função de envio para `/V1/OFXS`. Nenhuma outra rota de escrita.
3. **Só "dias inexistentes":** `opcaoImportacao` **fixo em código** = `IMPORTAR_APENAS_DIAS_INEXISTENTES_SISTEMA`. `EXCLUIR_DIAS_SISTEMA` e `IMPORTAR_DIAS_ARQUIVO` são **proibidos** (teste falha se aparecerem em qualquer lugar do payload).
4. **Duas travas no `.env`:** só envia se `WEBPOSTO_WRITES=1` **e** `LOGOS_OFX_IMPORTACAO=1` (nomes no `.env.example`; não alterar o `.env`). Desligado → apenas prévia.
5. **Prévia antes de enviar:** o comando padrão **não envia**; mostra o que seria importado (unidade, conta, período, quantidade, total de créditos e débitos, primeiros/últimos lançamentos com descrição mascarada). Envio só com `--confirmar` **e** depois de o diretor dizer "ok" no chat (nesta sprint).
6. **Conta certa:** mapa por unidade "banco + final da conta no OFX → `cdConta` do webPosto" em `units.json` (sem número completo), conferido contra `GET /INTEGRACAO/V1/CONTAS` (somente leitura). Sem correspondência única → recusa. `cdFilial` = `empresaCodigo` da unidade.
7. **Sem duplicar:** antes de enviar, consultar (somente leitura, `V1/MOVIMENTOS_CONTA` da conta/período, se trouxer os lançamentos de extrato) se o dia já tem lançamentos; registrar cada envio (arquivo, hash, conta, período, quantidade, total, resposta) em `data/importacoes_ofx/` (fora do Git); o mesmo arquivo/período nunca é enviado duas vezes.
8. **Limites:** no máximo **1 conta e até 7 dias** por envio; período deve estar **no passado** (até ontem).

## PARTE A — Ler o OFX (reaproveitar)

Se já existir o leitor geral da Sprint 17 (`adapters/extrato_reader.py`), usar. Senão, criar só o necessário (ver Sprint 17, Parte A e diagnóstico): SGML 1.02 e XML; utf-8/cp1252; `TRNTYPE` `IN/OUT` (PagBank) e `CREDIT/DEBIT` (BB); `DTPOSTED` com/sem fuso e hora; `TRNAMT` com ponto/vírgula; tags sem fechamento. Caso real: `C:\Projetos\LOGOS\extratos\PAGBANK\PagBank_Doze_Outubro2026.ofx.ofx` (3.566 lançamentos, 01–11/10) e `...\BB\BB_Doze_Outubro2026.ofx.ofx`.

## PARTE B — Descobrir o formato que o webPosto espera (somente leitura)

1. Ler `V1/CONTAS` do Doze (74014) e listar contas com código e descrição (sem número completo) para o diretor confirmar qual `cdConta` é o **BB do Doze** e qual é o **PagBank do Doze**.
2. Ler lançamentos de extrato já existentes no webPosto (se `V1/MOVIMENTOS_CONTA` os trouxer) para descobrir como ele grava `tipo`, `tipoTransacao` e o sinal do `valor`. Se não for possível descobrir, **parar** e informar ao diretor a pergunta exata para a Quality — não chutar.
3. Montar o payload a partir do OFX com esse formato; agrupar por conta e período.

## PARTE C — Teste controlado com o diretor

1. Escolher **uma conta e um dia** que **ainda não** esteja no webPosto (preferir PagBank do Doze, que hoje não importa).
2. Mostrar a prévia e o payload resumido; **enviar só após o "ok" do diretor**.
3. Depois, ler de novo (somente leitura) e mostrar o que entrou no webPosto: quantidade e total iguais ao OFX.
4. Se a chave do webPosto não tiver permissão de escrita (401/403) → parar e informar.

## PARTE D — Onde fica

Comando: `python -m src.jobs.importar_ofx --unidade 74014 --arquivo <caminho.ofx> [--confirmar]`. Registrar a regra **RN-ERP-002 — Importação de OFX no webPosto (barreira)** no `REGRAS_DE_NEGOCIO.md` e a decisão na ADR-003. (Tela de anexar fica para a Sprint 17.)

Rodar os testes de sempre. Commit: `feat(extratos): importação de OFX no webPosto com barreira`. Depois `git push`.
