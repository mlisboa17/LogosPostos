# Prompt — SPRINT DESPESAS_00: o Logos encontra e prepara as despesas pagas "na rua" (somente leitura)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). **Nesta sprint NADA é gravado no webPosto.** `.env` só via `load_dotenv`, nunca imprimir nem editar. Sem reescrever arquivos inteiros. Testes sintéticos (nenhum teste chama webPosto, Telegram ou Gemini reais). Extratos em `C:\Projetos\LOGOS\extratos\` (somente leitura); resultados em `WebPosto_API/data/despesas_avulsas/` (fora do Git). Nomes de pessoas permitidos no chat. Meta: ~30 min por parte; testes focados durante o trabalho, bateria completa no final.

## Decisão do diretor (11/10/2026)

"As despesas que pago quando estou na rua (pedreiro, manutenção, compra aleatória), preciso que lancem." Hoje o diretor manda o comprovante e depende de uma pessoa lançar; falha com frequência. **Melhor lançado com menos informação do que não lançado** (RN-ERP-003). Os títulos com nota fiscal não se perdem; o foco são os **pagamentos avulsos**.

## O que o arquiteto mediu (Doze 74014, ago–set/2026, somente leitura)

Débitos do BB + PagBank sem **nenhum** registro no webPosto (nem título/baixa em `V1/TITULOS_PAGAR`, nem lançamento em `V1/MOVIMENTOS_CONTA`), já tirando transferências entre as empresas do grupo, aplicações e tarifas: **69 débitos, ≈ R$ 81.585,21** — PIX para pessoas físicas (ex.: R$ 1.000,00, R$ 800,00, R$ 650,00), QR Code PIX (Karleal, Alentejo, Bete Serviços), pagamentos de conta (Petrosystem, Virtualnet, VR), impostos (DARF, ICMS, FGTS). Os FGTS podem estar lançados por outro caminho (folha) → tratar como "conferir".

Regras e mapas: `docs/regras-negocio/REGRAS_DE_NEGOCIO.md` RN-ERP-003 (inteira: pagamento agrupado, mapa de contas do Doze).

@WebPosto_API/src/modules/cash_reconciliation/adapters/extrato_reader.py
@WebPosto_API/src/jobs/telegram.py
@docs/regras-negocio/REGRAS_DE_NEGOCIO.md

## PARTE A — "Pagamentos sem lançamento" pelo extrato

`application/despesas_sem_lancamento.py` + `python -m src.jobs.despesas_avulsas --unidade 74014 --de dd/mm/aaaa --ate dd/mm/aaaa`:
1. Ler os OFX da unidade (BB e todos da pasta PAGBANK; **deduplicar por FITID**).
2. Débito está "registrado" se casar (valor igual ou até +10% de juros; data ±3 dias do pagamento) com: baixa de título (`pagamento[]` de `V1/TITULOS_PAGAR`), título em aberto (vencimento −10/+40 dias), ou débito de `V1/MOVIMENTOS_CONTA` da conta. Cada registro casa **uma vez**.
3. Ignorar (configurável em `units.json`, por grupo): transferências para empresas do grupo (Posto VIP, Casa Caiada, Igarassu, Posto Real, Loja de Conveniência, Posto Doze/"C C D"), aplicações/resgates (Renda Fixa, CDB, Rende Fácil, Ourocap), tarifas bancárias, vendas/antecipações da adquirente.
4. Resultado por débito: data (dd/mm/aaaa), banco, valor, favorecido (texto do extrato), tipo (PIX pessoa, QR Code, boleto, imposto) e **sugestão obrigatória de PLANO DE CONTAS e CENTRO DE CUSTO** (código + descrição de `V1/PLANOS_CONTA_GERENCIAL` e `V1/CENTROS_CUSTO`), nesta ordem: (a) o mesmo favorecido já tem título/movimento no webPosto → mesmo plano e centro; (b) palavra-chave da descrição/áudio do diretor (tabela de apelidos: "pedreiro" → PEDREIRO 198595, "piso" → MANUTENÇÃO PISO/CANALETAS 194968, "farda" → plano usado em "FARDAS", rescisão/FGTS → planos já usados nesses lançamentos), aprendida dos **lançamentos manuais existentes** de `V1/MOVIMENTOS_CONTA` (tipo MANUAL); (c) senão → "a classificar" (o diretor escolhe). Mostrar sempre de onde veio a sugestão ("igual ao lançamento de 06/08/2026 PEDREIRO"). **Nenhum lançamento futuro sai sem plano de contas e centro de custo.**
5. Saída: tabela no terminal + XLSX em `data/despesas_avulsas/`. Teste com dados sintéticos para cada caso (registrado, agrupado, interno ignorado, sem registro).

## PARTE B — Comprovante pelo Telegram (fila, sem gravar no webPosto)

1. O bot passa a aceitar **foto ou PDF** enviado **só pelo chat do diretor** (chat id já configurado). Arquivo salvo em `data/despesas_avulsas/comprovantes/`.
2. Leitura do comprovante com o **Gemini** (chave já no `.env`; autorizado pelo diretor; nomes e valores liberados): valor, data/hora, favorecido, CPF/CNPJ ou chave PIX, banco/conta de origem, descrição. Resultado validado com Pydantic; campo ilegível fica vazio (não inventar).
3. O diretor pode responder ao comprovante com uma palavra **ou um áudio** do Telegram ("paguei 350 ao seu Antônio pedreiro pelo piso da pista") → o Gemini (que lê áudio direto, sem Whisper) extrai valor, favorecido, categoria e histórico. Áudio sozinho, sem comprovante, também entra na fila (casado depois pelo extrato). Apelidos falados → entidades do webPosto em configuração ("pedreiro" → plano PEDREIRO 198595; "BB" → conta da unidade em `V1/CONTAS`).
4. Casar o comprovante com o débito do extrato da Parte A (valor + data + nome). Unidade = dona da conta que pagou.
5. Fila `data/despesas_avulsas/fila.json`: cada item com comprovante, débito casado (ou "aguardando extrato"), unidade, sugestão de fornecedor/plano/centro e status ("pronto para lançar", "a classificar", "sem extrato ainda").
6. Resposta do bot: "Recebi: R$ 650,00 · Leticia Malta Farias · 17/09/2026 · PagBank Doze · sugestão: PEDREIRO (198595). Vou deixar pronto para lançar." Nada é gravado no webPosto.

## Fora desta sprint (próxima: DESPESAS_01, com barreira)

Gravar no webPosto. **Avulso (sem título)** → `POST /V1/MOVIMENTOS_CONTA` (`ParametrosIncluirMovimentoConta`: `descricao`, `data`, `valor`, `conta`, `filial`, `contaMovimentoTipo`="DEBITO", `planoConta`, `centroCusto`, `documento`, `tipoPessoa` — "NAO_IDENTIFICADO" para pessoa sem cadastro —, `pessoa`) + anexo `POST /V1/ARQUIVOS/MOVIMENTO_CONTA_MANUAL/{id}`. É o mesmo tipo "Débito MANUAL" que o webPosto já usa. **Com título em aberto** → baixa (`PATCH /V1/TITULOS_PAGAR/PAGAR`), nunca movimento (senão conta em dobro). **Não há rota para excluir movimento** → correção só pela tela: por isso, no início, tudo passa pelo "Confirma? [Sim] [Editar]" do diretor; lançamento direto só para favorecido já aprendido + débito casado no extrato (regra objetiva, não "confiança da IA"). Travas no `.env`, prévia, auditoria (mesma barreira da BAIXA_00 Parte B).

Registrar no `REGRAS_DE_NEGOCIO.md` (RN-ERP-003: o que já existe) e no `STATUS.md`.
Commits: `feat(despesas): pagamentos sem lançamento pelo extrato` e `feat(despesas): comprovante pelo Telegram com leitura pela IA (fila local)`. Depois `git push`.
Ao final da Parte A, rodar a real do Doze de 01/08/2026 a 30/09/2026 e mostrar no chat o resumo (quantidade e total por tipo) e os 20 maiores.
