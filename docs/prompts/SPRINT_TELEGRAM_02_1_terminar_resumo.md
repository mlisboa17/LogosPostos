# Prompt — SPRINT TELEGRAM_02.1: terminar o resumo do diretor sem perder nada

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). Somente leitura no webPosto. `.env` só via `load_dotenv`. Sem reescrever arquivos inteiros. **Não enviar nada pelo Telegram** sem o "ok" do diretor. Meta: ~30 min.

Leia antes: `docs/prompts/SPRINT_TELEGRAM_02_resumo_do_diretor.md` (formato pedido).

## Situação (relatório de status de 14/10/2026)

A TELEGRAM_02 ficou **inacabada e sem commit**: `resumo_diario.py` (+202/−56), `noturno.py`, `conftest.py`, `test_comprovantes_fila.py` alterados; pasta `WebPosto_API/scratch/` com rascunho. **O robô noturno já está rodando esse código pela metade** (resumos de 12/10 e 13/10). **22 testes falham.** Continuar a partir dessas mudanças (não descartar).

## O que corrigir

1. **Nada que já existia pode sumir.** O diretor pediu antes (Sprint 09) **despesas com descrição, plano de contas e valor** e **vales de funcionários com nome**; também existem avisos do **Premmia** (data da última coleta), divergências de cartão (V3.2: quantidade, valor e forma; a maior com hora e NSU mascarado) e cobrança em duplicidade. Tudo isso continua, em blocos **compactos** depois de "PRECISA DE VOCÊ":
   - `💸 DESPESAS DO CAIXA` — até 8 linhas: posto · setor, descrição, plano de contas, valor ("SEM PLANO ⚠" quando faltar).
   - `🧾 VALES` — nome + código do funcionário e valor.
   - Avisos de fonte (Premmia, PagBank) só quando houver erro, com a data dos últimos dados.
2. **Limite da falta:** usar o limite já configurado por unidade (não R$ 100 fixo). **Falta sem desconto e caixa não consolidado nunca ficam em "EM ORDEM"**, qualquer que seja o valor.
3. **Tamanho:** a parte principal cabe em ~25 linhas; se a mensagem passar do limite do Telegram, **dividir** em várias (o teste existente de divisão continua valendo).
4. **Testes:** os 22 que falham — corrigir o código quando a informação sumiu de verdade; **atualizar o teste só quando a mudança for de formato pedida pelo diretor** (códigos → nomes, títulos novos). Listar no chat cada teste alterado e o porquê. Acrescentar os testes novos da TELEGRAM_02 (VIP com dois caixas por setor, caixa aberto fora das faltas, sem linhas R$ 0,00, ordem por valor).
5. **Limpeza:** apagar a pasta `WebPosto_API/scratch/` (rascunho) depois de aproveitar o que servir. O `scripts/probe_premmia_portal.py` fica como está (não mexer).
6. **Envio:** o comando `python -m src.jobs.telegram` hoje só descobre chat ou manda teste. Acrescentar a opção `--reenviar-resumo dd/mm/aaaa` (reenvia o resumo gravado daquele dia), usada só com o "ok" do diretor.

## Entrega

- Bateria completa verde (`python -m pytest tests/unit/cash_reconciliation -q`).
- Mostrar no chat o resumo novo de **13/10/2026** (dados gravados), sem enviar.
- Commit: `feat(telegram): resumo do diretor curto, por caixa, sem perder despesas, vales e avisos`. Depois `git push`.
