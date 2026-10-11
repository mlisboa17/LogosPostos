# Prompt — SPRINT 17 (EXTRATOS_00): local para anexar extratos bancários no Logos (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Somente leitura no ERP; `.env` só via `load_dotenv`; sem reescrever arquivos inteiros; **extratos e dados reais nunca no Git** (ficam em `WebPosto_API/data/extratos/`); testes com fixtures **sintéticas**; nada pelo Telegram. Datas `dd/mm/aaaa`. Conciliação de **depósitos em espécie continua fora do escopo** (RN-REDE-004): nesta sprint o extrato serve para **guardar e consultar** e para **confirmar PIX recebidos fora da maquininha** (RN-CARTAO-009).

## Decisão do diretor (11/10/2026)

"No Logos quero um local para poder anexar os extratos até nossos sistemas estarem integrados." Primeiros arquivos: **OFX do Banco do Brasil (Doze)** e **OFX do PagBank** — o OFX do PagBank **sempre dá problema de conversão no webPosto**, então o leitor do Logos tem de ser tolerante e, se o OFX falhar, aceitar a **planilha/CSV** do PagBank.

Já existe `adapters/ofx_reader.py` (SGML 1.02, cp1252, extrai **só depósitos em espécie** para o CASH-ARCH-01). **Não mudar o comportamento dele**; criar o leitor geral ao lado e reaproveitar funções.

@WebPosto_API/src/modules/cash_reconciliation/adapters/ofx_reader.py
@WebPosto_API/src/modules/cash_reconciliation/config/units.json
@WebPosto_API/src/modules/cash_reconciliation/interfaces/http.py
@WebPosto_API/src/modules/cash_reconciliation/application/classificar_recebimentos.py
@docs/regras-negocio/REGRAS_DE_NEGOCIO.md

## PARTE A — Leitor geral de extratos (todos os lançamentos)

1. `adapters/extrato_reader.py`: lê **OFX** (SGML 1.02 e XML 2.x; codificação utf-8/cp1252/latin-1 com detecção; tags sem fechamento; `DTPOSTED` com fuso `[-3:BRT]`/sem fuso/com hora; `TRNAMT` com vírgula ou ponto; BOM; linhas em branco no cabeçalho) e, como alternativa, **CSV/XLSX do PagBank** (detectar colunas por nome). Devolve `ExtratoBancario` (banco, agência/conta mascarada, período, saldo se houver) e `LancamentoBancario` (data, hora se houver, valor com sinal, tipo crédito/débito, descrição/memo, documento, FITID/identificador, categoria simples: PIX recebido, PIX enviado, TED/DOC, depósito, tarifa, rendimento, outros).
2. Quando o OFX não puder ser lido, **mensagem clara do motivo** (linha/tag) — não silenciar. Guardar uma cópia **anônima** do trecho problemático (sem nomes, CPF ou valores reais) para virar fixture de teste.
3. Deduplicação por (conta, FITID) e, sem FITID, por (conta, data, valor, descrição). Reenviar o mesmo arquivo não duplica.

## PARTE B — Onde anexar e consultar

1. Tela **"Extratos"** (menu do Painel; diretor e gerente da unidade): escolher unidade e banco/conta, **arrastar ou selecionar** arquivos `.ofx`, `.csv`, `.xlsx`; mostrar resultado da leitura (quantos lançamentos, período, saldo, avisos); lista dos extratos já anexados (unidade, banco, conta final, período, quem anexou, quando); visualizar lançamentos com filtro por período, tipo e valor.
2. API: `POST /cash-audit/extratos` (upload, limite de tamanho, só extensões permitidas, nome sanitizado) e `GET /cash-audit/extratos` / `GET /cash-audit/extratos/{id}/lancamentos`. Escopo do gerente respeitado.
3. Armazenamento: arquivo original em `data/extratos/<empresaCodigo>/<banco>/<aaaa-mm>/` + índice (SQLite em `data/extratos/`), com quem anexou e quando (histórico append-only). Contas mapeadas por unidade em `units.json` (banco e final da conta; sem número completo).

## PARTE C — Uso imediato: confirmar PIX fora da maquininha

1. Para itens do grupo **4 (Conferir à mão)** do tipo **PIX CNPJ** (RN-CARTAO-009): procurar no extrato da conta PagBank (ou outra conta configurada) um **PIX recebido de mesmo valor no mesmo dia (±1 dia)**. Achou único → marcar como **"conferido pelo extrato"** (sugestão automática com a evidência; o diretor confirma com 1 clique). Não achou com o extrato do período anexado → "não encontrado no extrato" (vira pendência do grupo 3). Sem extrato do período → continua no grupo 4 com o aviso "anexe o extrato de dd/mm a dd/mm".
2. Caso real para validar quando o diretor anexar o extrato PagBank do Doze: **PIX CNPJ R$ 800,00 em 10/10/2026** (lançado à mão às 16:00) e os 7 PIX CNPJ de 01–09/10 (R$ 2.480,41).
3. Atualizar `REGRAS_DE_NEGOCIO.md`: RN-CARTAO-009 (confirmação pelo extrato anexado) e nova RN-REDE-009 (extratos anexados: formatos, guarda, quem pode anexar); histórico.

## PARTE C2 — Sangrias do Banco 24h × depósitos no BB (incluída pelo diretor em 11/10/2026)

O diretor autorizou conferir **sangria para o Banco 24h × depósito em dinheiro no caixa eletrônico** (muda a RN-REDE-004 só para esse caso; depósitos de outras origens continuam fora).
1. Para cada unidade com conta de **depósito direto** em `units.json` (Doze: conta 86248 "Banco 24h", terminal "POSTO REAL FOSFATO ATMR"), casar cada sangria com um depósito do extrato anexado: **mesmo valor**, depósito de até 8 h antes a 24 h depois (preferir o mais próximo; um para um). O horário real do depósito está no MEMO do BB (`dd/mm hh:mm`).
2. **Sangria depois da meia-noite:** o webPosto grava com a data do caixa (ex.: "10/10 00:01" feita em 11/10 00:01); se o horário for anterior à abertura do caixa, somar 1 dia.
3. Classificar: **sangria sem depósito** (vermelho, com frentista); **sangria lançada na conta errada** (lançada como cofre 86081 e depositada no Banco 24h — laranja, "corrigir conta"); **depósito sem sangria** (lotes seguidos em poucos minutos = provável **depósito do cofre** — informativo "confirmar com o diretor"; isolado = laranja).
4. Caso real (Doze, 01–10/10, conferido pelo arquiteto): 160 sangrias Banco 24h · R$ 125.757,00; 159 depositadas; **sem depósito: 05/10 23:06 R$ 267,00 — Alberis Henrique da Silva Massa (299240)**; **conta errada:** 07/10 16:26 R$ 600 (299240), 09/10 22:56 R$ 850 (299240), 10/10 13:46 R$ 1.070 (Almir Carlos Ferreira 302093), 10/10 18:31 R$ 1.050 (Jeymerson Vitor Medeiros da Siva 299241); **depósitos sem sangria R$ 12.170,00** em lotes (01/10 R$ 3.200; 03/10 R$ 1.300; 06/10 R$ 2.850; 08/10 R$ 150 e R$ 4.670). O teste tem de reproduzir isso.
5. Atualizar RN-REDE-004 (exceção: Banco 24h) e criar RN-SANGRIA-006 no `REGRAS_DE_NEGOCIO.md`.

## Diagnóstico do OFX real do PagBank (arquiteto, 11/10/2026 — `C:\Projetos\LOGOS\extratos\PAGBANK\PagBank_Doze_Outubro2026.ofx.ofx`)

- Cabeçalho `OFXHEADER:100 / DATA:OFXSGML / VERSION:100` mas `ENCODING:UTF-8` (OFX 1.0 SGML espera USASCII/1252) e todas as tags **com fechamento** (estilo XML) → mistura de padrões.
- `TRNTYPE` **`IN`/`OUT`** (fora do padrão OFX: CREDIT/DEBIT/…) — causa provável da falha no webPosto. Mapear IN→crédito, OUT→débito.
- `DTPOSTED` `AAAAMMDDHHMMSS[-3:BRT]` (com hora); `TRNAMT` com ponto; `FITID` UUID; sem `NAME`, só `MEMO`.
- **3.566 lançamentos** em 01–11/10: cada venda aparece como "Vendas - Disponivel <DEBITO|CREDITO> <BANDEIRA>" (3.451), mais "Pix recebido" (64), "Pix enviado" (46), "QR Code Pix enviado" (3), "Rendimento da conta" (2). Alguns caracteres especiais e um `\xa0`.
- Fixture sintética deve reproduzir exatamente isso (sem dados reais).

Resultado já conferido pelo arquiteto com esse extrato (PIX CNPJ do Doze): **encontrados** 04/10 R$ 100,00 e R$ 50,00; 05/10 R$ 142,71; 06/10 R$ 1.614,64; 08/10 R$ 417,00; **10/10 R$ 800,00**. Os dois que não batiam por valor único **são somas de vários PIX do dia** (correção do diretor, conferida pelo arquiteto): **05/10 R$ 96,28 = 30,00 (18:29) + 55,28 (18:41) + 11,00 (18:17)** e **07/10 R$ 59,78 = 33,00 (13:10) + 26,78 (17:24)**. Ou seja, **todos os 8 PIX CNPJ têm lastro**.
**Regra para a Parte C:** um PIX CNPJ lançado à mão pode ser a **soma de vários PIX recebidos no mesmo dia** → se não houver PIX de valor único, procurar **combinação única de até 4 PIX recebidos** do mesmo dia (não usados por outro lançamento) que some o valor; achou → "conferido pelo extrato (soma de N PIX)" com a lista; mais de uma combinação → "conferir à mão" mostrando as opções. O teste da Parte C tem de reproduzir os 8 casos acima.

## PARTE D — Testes

Fixtures sintéticas: OFX BB SGML cp1252; OFX XML; OFX "estilo PagBank" com defeitos comuns (sem fechamento de tags, vírgula decimal, fuso no DTPOSTED, BOM); CSV PagBank; reenvio sem duplicar; upload com extensão proibida recusado; PIX CNPJ achado/não achado/sem extrato; escopo do gerente. Nenhum dado real nos testes.

Validação real: ler os OFX já existentes em `C:\Projetos\LOGOS\extratos\BB\` (somente leitura, sem copiar para o Git) e os que o diretor anexar pela tela; mostrar no chat só **agregados** (quantidade de lançamentos, período, total de créditos/débitos, PIX recebidos) e, para o PagBank, **o motivo de qualquer falha de leitura**.

Rodar os testes de sempre. Commits: `feat(extratos): leitor geral de OFX/CSV tolerante`, `feat(extratos): tela e API para anexar extratos`, `feat(extratos): PIX CNPJ conferido pelo extrato`. Depois `git push`.
