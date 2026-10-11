# Prompt — SPRINT 13 (PREMMIA_01): Premmia no robô noturno — Casa Caiada e Doze (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem merge na main e sem troca de branch. **Somente leitura** no ERP (`WEBPOSTO_WRITES=0`) e no portal Premmia (só login, filtrar, exportar). `.env` só via `load_dotenv`, nunca imprimir nem editar. Altere SOMENTE o que está listado; não reescreva arquivos inteiros. Datas no padrão Brasil. Testes sintéticos, nunca gravam no banco real, nunca acessam o portal nem enviam Telegram. No chat: sem CPF, sem nome de cliente, nomes de funcionários trocados por "Funcionário A...".

**Regra fixa:** toda ocorrência mostra **"Nome do frentista (código)"**; sem frentista identificável → "frentista não identificado" + motivo.

## Decisões do diretor (10/10/2026)

- Começar por **Casa Caiada (5555)** e **Doze (74014)** — as unidades que já têm o PagBank conciliado. O VIP fica para depois (configurável, desligado).
- Armazenamento: **uma planilha por posto e por mês**, ex.: `data/premmia/postocasacaiada_10_2026.xlsx` e `data/premmia/postodoze_10_2026.xlsx`; cada coleta **acrescenta só os dias novos**. Sem cópias por dia.
- Coleta: do **dia 01 do mês até ontem**, só os **dias que ainda não estão na planilha**. Na virada do mês, completar os dias que faltarem do mês anterior.
- **"Desconto" do Premmia é recebível** (a Vibra paga ao posto): conciliar como as outras formas.

## O que já foi validado (teste controlado VIP, 01 a 09/10/2026)

- Login sem CAPTCHA. Filtro de datas **pela URL** (`/premmia/revendedor/conferencia/pagamentos?page=1&start=AAAA-MM-DD+00%3A00&end=AAAA-MM-DD+23%3A59&products=...`, `products` lido da própria página). **Exportar** gera `.xlsx` com `expect_download` (180 s), **sem exigir a tabela**.
- Colunas do .xlsx: CPF, Nome, Produto, Valor líquido, Data/Hora da transação, Código Transação, Forma de Pagamento (Cartão APP, Pix, Desconto, Vale-Premmia), Status (Processada).
- **"Código Transação" do portal = `nsu` do `V1/CARTOES`** (UUID). No ERP: administradoras `PREMMIA`, `PREMMIA CREDITO`, `PREMMIA PIX`, `PREMMIA VALE` e a forma nova de desconto que o diretor cadastrou em 10/10 (descobrir o nome em `V1/ADMINISTRADORAS` com "PREMMIA" na descrição; não inventar).
- Crédito bateu 100%; o único problema real foi o NSU repetido do VIP em 05/10 (já tratado pela CARTOES_V3_1).
- Referência de código: `WebPosto_API/scripts/probe_premmia_portal.py` (ainda sem commit).

Arquivos:
@WebPosto_API/scripts/probe_premmia_portal.py
@WebPosto_API/src/modules/cash_reconciliation/config/units.json
@WebPosto_API/src/modules/cash_reconciliation/domain/models.py
@WebPosto_API/src/modules/cash_reconciliation/domain/cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/conciliar_cartoes.py
@WebPosto_API/src/modules/cash_reconciliation/application/recebimentos.py
@WebPosto_API/src/modules/cash_reconciliation/application/resumo_diario.py
@WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py
@WebPosto_API/pyproject.toml
@WebPosto_API/frontend/pages/cashAudit.js

## PARTE A — Coletor do portal

1. Novo `adapters/premmia_portal.py`, portando a lógica **validada** do probe (não a do código resgatado): login, `products` da URL, navegação por URL, exportação `.xlsx`. Playwright síncrono rodando em thread (`asyncio.to_thread`). Declarar `playwright` no `pyproject.toml`.
2. Credenciais por unidade no `units.json` (só os **nomes** das variáveis): Casa Caiada `PREMMIA_usuario_CASA_CAIADA` / `PREMMIA_SENHA_CASA_CAIADA`; Doze `PREMMIA_usuario_DOZE_REAL` / `PREMMIA_SENHA_DOZE_REAL`; VIP `PREMMIA_usuario_POSTO_VIP` / `PREMMIA_SENHA_POSTO_VIP`. Campo `premmia_ativo`: `true` para 5555 e 74014, `false` para 11495. Atualizar a situação do adquirente PREMMIA para `ativo` só nas duas unidades.
3. **Um login por unidade por execução**; exporta o intervalo de dias faltantes de uma vez (se falhar por tempo, tenta 1 dia, uma vez). No robô noturno, `headless=True`; no modo manual `--visivel`.
4. **Paradas obrigatórias** (sem tentar contornar): CAPTCHA, código por SMS/e-mail, 2FA, aceite de termos, troca de senha, senha recusada → **aviso** "Premmia pediu verificação humana / credencial recusada" na unidade (não é falha do robô) e não tenta de novo naquela noite.
5. Planilha mensal `data/premmia/posto<apelido>_<MM>_<AAAA>.xlsx` (apelido em minúsculas sem espaço: `postocasacaiada`, `postodoze`): aba **Transações** com as colunas do portal + `Dia` e `Coletado em`; deduplicar por **Código Transação**; aba **Coletas** com dia, quantidade, total e data/hora da coleta. O arquivo exportado original vai para `data/premmia/originais/` (para auditoria). Tudo fora do Git.
6. Conversão para `TransacaoAdquirente` (adquirente `PREMMIA`, `nsu` = Código Transação, valor, momento, forma) **lendo da planilha mensal**, não do portal — reprocessar um dia não exige novo login. CPF e nome do cliente **não** entram no resultado nem no log.

## PARTE B — Conciliação, pendências, tela e Telegram

1. Reusar o motor da **CARTOES_V3_1** (casamento por NSU, valor divergente, NSU repetido, a maior / a menor, nome do frentista) com os cartões do ERP cujas administradoras são Premmia. Resultado aparece como um adquirente a mais em `recebimentos` da unidade.
2. Pendências pelas regras existentes (vermelho individual, laranja agrupado). **Lançado no webPosto e não encontrado no portal** = vermelho (não será pago).
3. Tela de recebimentos: bloco "Premmia" igual ao do PagBank.
4. Telegram, por filial: "Premmia: N conferidos · R$ X · M divergências" e a linha de cada divergência vermelha com o nome do frentista.

## PARTE C — Validação real (uma execução por unidade, com o diretor autorizando)

1. Testes sintéticos: deduplicação na planilha mensal; dias faltantes (inclusive virada de mês); parada por CAPTCHA vira aviso; desconto conciliado; lançamento sem par no portal → vermelho; CPF/nome ausentes do resultado.
2. Rodar **uma vez Casa Caiada e uma vez Doze**, de 01/10/2026 até ontem (`--visivel`), gerar as planilhas mensais e reprocessar os dias com a conciliação.
3. Informe por unidade e por dia: portal × webPosto (quantidade e R$) por forma, divergências (com tipo) e o nome da forma de desconto encontrada no ERP.

## Ao terminar

```
cd C:\Projetos\LOGOS\LogosPostos\WebPosto_API; python -m pytest tests/unit/cash_reconciliation tests/unit/commercial_performance tests/unit/test_auth_access.py -q -o addopts=""; node --test tests/frontend/*.test.mjs
```
Commits: `feat(premmia): coletor do portal e planilha mensal por posto` e `feat(premmia): conciliação Premmia no robô noturno`. Depois `git push`. **Não envie nada pelo Telegram.**
