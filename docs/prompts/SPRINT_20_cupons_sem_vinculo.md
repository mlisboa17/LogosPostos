# Prompt — SPRINT 20: cupons de cartão sem vínculo — padrão por frentista, PDV e horário (somente leitura)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). **Somente leitura** (escrita no ERP congelada). `.env` só via `load_dotenv`, nunca imprimir nem editar. Sem reescrever arquivos. **REUSE > ADAPT > CREATE.** A IA não calcula nada: contagens, janelas e classificações saem do código, com teste. Meta: uma entrega ponta a ponta, com critério de aceite abaixo.

Origem: proposta do Gemini (17/10/2026), **adaptada** às regras e aos dados reais do LOGOS.

## Contexto do diretor (17/10/2026)

As maquininhas PagBank são **integradas** ao webPosto. Às vezes a integração **não reconhece** a transação: o cartão é cobrado, a venda fica como **dinheiro** e o cupom do cartão fica **sem vínculo** (ex.: Doze 14/10/2026, Mastercard R$ 34,75, AILTON LUIZ DA SILVA (299239), 11:26). Os frentistas relatam falha de comunicação; **cada caso deve ser analisado individualmente** — pode haver outros fatores. Objetivo: separar **instabilidade técnica** de **padrão individual**, com evidência, sem acusar ninguém.

## O que JÁ existe (reaproveitar, não refazer)

@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/conciliar_cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/classificar_recebimentos.py
@WebPosto_API/src/modules/cash_reconciliation/application/explicar_falta.py

- Casamento EDI PagBank × `V1/CARTOES` por NSU (CARTOES_V3_4) e atribuição ao frentista pelo abastecimento (nota, "abastecido 1 min antes", "venda lançada como dinheiro"). Resultados diários gravados em `data/cash_audit/<dia>/<unidade>.json`.

## Correções em relação à proposta do Gemini (obrigatórias)

1. **Campos reais, não os inventados.** Abastecimento vem de `GET /INTEGRACAO/V1/ABASTECIMENTOS` (schema `AbastecimentoRede`): `dataHoraAbastecimento` (há **um** horário só — não existe "início/fim"), `codigoBico`, `codigoFrentista`, `valorTotal`, `quantidade`, `afericao`, `vendaItemCodigo`, `abastecimentoCodigo`. Cartões: `V1/CARTOES` (NSU, autorização, administradora, venda, caixa). PagBank: o EDI v3 que o adapter já lê. **Não usar** `CONSULTAR_ABASTECIMENTO_REDE` nem nomes como `id_abastecimento`/`data_hora_fim`. Se o EDI trouxer identificação do terminal/maquininha, usar; se não trouxer, dizer que não há.
2. **Identificação:** nossa regra é **nome + código** do frentista (não só nome). Caixa como na tela do webPosto ("Doze · Pista — 14/10, 1º turno (Wanderson, 00:01)").
3. **Sem rótulo de fraude.** "Cartão cobrado + venda de mesmo valor como dinheiro, mesmo frentista, minutos depois" é **exatamente a assinatura da falha de integração** — não pode, sozinho, virar "alerta vermelho / suspeita de retenção de dinheiro". Classificação neutra, por evidência e por padrão (abaixo).
4. **Janela de horário calibrada com dados, não chutada.** Medir, nos cartões **já casados por NSU** dos últimos 60 dias, a diferença real entre `dataHoraAbastecimento` e o horário do cartão; usar essa distribuição (ex.: percentil 95) como janela, por unidade. Mostrar os números.
5. **Aferição** (`afericao=true`) nunca entra no casamento.

## O que fazer

### A. Lista de cupons sem vínculo (por dia e período)
Cupom sem vínculo = transação do EDI PagBank aprovada **sem** cartão correspondente no webPosto. Para cada um: data/hora, valor, bandeira, NSU final, unidade e setor (posto/loja), abastecimento candidato (bico, frentista nome+código, horário, valor, forma em que a venda foi fechada) com a diferença de tempo, ou "nenhum abastecimento de mesmo valor na janela".

### B. Classificação (determinística, com regra escrita)
- **Sem abastecimento correspondente** — nenhum abastecimento/venda de mesmo valor na janela (na loja: nenhuma venda de mesmo valor no caixa).
- **Provável instabilidade** — no mesmo intervalo de 10 min (calibrável) há cupons sem vínculo de **3+ frentistas diferentes** ou do mesmo PDV/terminal em sequência.
- **Repetição individual — analisar** — mesmo frentista com cupons sem vínculo em **N+ dias diferentes** no período (N calibrável, começar com 3 em 30 dias) **fora** de janelas de instabilidade. É sinal para análise humana, **não conclusão**.
- **Caso isolado** — nenhuma das anteriores.
Cada classificação mostra a regra aplicada e os números que a sustentam.

### C. Padrão por período (30 e 60 dias)
Tabela por frentista (nome + código): nº de cupons sem vínculo, valor total, dias distintos, quantos em janela de instabilidade, % sobre o total de cartões dele. Também por PDV/terminal (se disponível) e por faixa de horário. Posto e loja separados (VIP: loja por centro de custo; Casa Caiada: Conveniência 24h 118508 é outro CNPJ).

### D. O Logos explica (sem jargão, sem acusação)
Ex.: "Doze · Pista, 14/10 11:26 — o PagBank cobrou um Mastercard de R$ 34,75 e o webPosto não registrou o cartão; a venda do AILTON LUIZ DA SILVA (299239) de R$ 34,75 ficou como dinheiro. Nenhum outro frentista teve cupom solto nesse horário (não parece queda geral). É o 1º caso dele em 30 dias." Na tela, no relatório do caixa e no resumo do Telegram (só os itens "repetição individual" e "sem abastecimento").

## Critério de aceite (o diretor confere)

1. **Golden case:** Doze 14/10/2026 — o cupom R$ 34,75 aparece com AILTON LUIZ DA SILVA (299239), venda como dinheiro, diferença de tempo calculada, e classificação coerente; teste fixo em `tests/` que falha se a explicação mudar.
2. Rodar real (somente leitura) para **Doze e Casa Caiada, últimos 30 dias**, e mostrar no chat: a janela calibrada (com os números), a tabela por frentista e os casos "repetição individual" e "sem abastecimento".
3. Testes sintéticos para cada classe (incluindo 3+ frentistas no mesmo intervalo e aferição excluída). Bateria completa verde.
4. Zero POST/PUT/PATCH/DELETE ao webPosto (comprovar no relatório).

Atualizar `REGRAS_DE_NEGOCIO.md` (nova RN para cupom sem vínculo e as classes) e `STATUS.md`. Commit: `feat(cartoes): cupons sem vinculo com padrao por frentista e instabilidade`. Depois `git push`.
