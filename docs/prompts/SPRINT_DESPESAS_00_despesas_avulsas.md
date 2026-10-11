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
4. Resultado por débito: data (dd/mm/aaaa), banco, valor, favorecido (texto do extrato), tipo (PIX pessoa, QR Code, boleto, imposto) e **sugestão de classificação**: se o mesmo favorecido já tem título/movimento no webPosto → mesmo plano de contas, centro de custo e fornecedor; senão → "a classificar".
5. Saída: tabela no terminal + XLSX em `data/despesas_avulsas/`. Teste com dados sintéticos para cada caso (registrado, agrupado, interno ignorado, sem registro).

## PARTE B — Comprovante pelo Telegram (fila, sem gravar no webPosto)

1. O bot passa a aceitar **foto ou PDF** enviado **só pelo chat do diretor** (chat id já configurado). Arquivo salvo em `data/despesas_avulsas/comprovantes/`.
2. Leitura do comprovante com o **Gemini** (chave já no `.env`; autorizado pelo diretor; nomes e valores liberados): valor, data/hora, favorecido, CPF/CNPJ ou chave PIX, banco/conta de origem, descrição. Resultado validado com Pydantic; campo ilegível fica vazio (não inventar).
3. O diretor pode responder ao comprovante com uma palavra ("pedreiro", "gelo", "manutenção bomba") → vira a descrição/categoria sugerida.
4. Casar o comprovante com o débito do extrato da Parte A (valor + data + nome). Unidade = dona da conta que pagou.
5. Fila `data/despesas_avulsas/fila.json`: cada item com comprovante, débito casado (ou "aguardando extrato"), unidade, sugestão de fornecedor/plano/centro e status ("pronto para lançar", "a classificar", "sem extrato ainda").
6. Resposta do bot: "Recebi: R$ 650,00 · Leticia Malta Farias · 17/09/2026 · PagBank Doze · sugestão: PEDREIRO (198595). Vou deixar pronto para lançar." Nada é gravado no webPosto.

## Fora desta sprint (próxima: DESPESAS_01, com barreira)

Gravar no webPosto: `POST /V1/TITULOS_PAGAR` + `PATCH /V1/TITULOS_PAGAR/PAGAR` + anexo `POST /V1/ARQUIVOS/...`, cadastro de fornecedor (`POST /V1/FORNECEDORES`) para pessoa nova — com travas no `.env`, prévia, "ok" do diretor e auditoria (mesma barreira da BAIXA_00 Parte B).

Registrar no `REGRAS_DE_NEGOCIO.md` (RN-ERP-003: o que já existe) e no `STATUS.md`.
Commits: `feat(despesas): pagamentos sem lançamento pelo extrato` e `feat(despesas): comprovante pelo Telegram com leitura pela IA (fila local)`. Depois `git push`.
Ao final da Parte A, rodar a real do Doze de 01/08/2026 a 30/09/2026 e mostrar no chat o resumo (quantidade e total por tipo) e os 20 maiores.
