# Prompt — SPRINT 18b: piloto — o Logos lança no webPosto o cartão que faltou (com o diretor acompanhando)

**Só começar depois que a TELEGRAM_02.1 estiver com commit e testes verdes.**

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). `.env` só via `load_dotenv`/`dotenv_values`, nunca imprimir nem editar. Sem reescrever arquivos inteiros. Testes sintéticos com cliente falso. Nomes de funcionários permitidos no chat. Meta: ~30 min + teste com o diretor.

Leia antes: `docs/prompts/SPRINT_18_piloto_lancamento_cartao.md` (decisão do diretor e regra do piloto — Partes B, C e D) e `docs/prompts/SPRINT_18A_porta_escrita_cartao.md` (o que já existe).

@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_cartao.py
@WebPosto_API/src/jobs/lancar_cartao.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/propostas_lancamento.py

## Por que (rotina do diretor, 15/10/2026)

Hoje quem fecha o caixa confere à mão o **total dos cartões no site do PagBank × webPosto** (depois Premmia e Mais Pagamentos) e, se estiver errado, corrige à mão. O Logos já encontra o cartão que faltou; agora ele passa a **lançar**, com NSU, para o caixa fechar sem diferença.

## O que fazer

1. **Regra do piloto** (todas as condições; senão vira proposta "um toque" para o diretor): recebido no PagBank **sem cartão** no webPosto; venda/abastecimento identificado com **nota ≥ 90 e candidato único**; **caixa não consolidado**; valor ≤ **R$ 300,00**; soma do dia ≤ **R$ 1.000,00** por unidade; administradora resolvida sem ambiguidade (18a); **reconsultar antes de gravar** (o cartão ainda não existe; idempotência por NSU).
2. **Depois de gravar** (resposta 201 **não** basta — lição do OFX): reconsultar `V1/CARTOES` do caixa e o fechamento: o cartão tem de existir com o **NSU** enviado e o **dinheiro esperado tem de cair no valor do cartão**. Se não → `excluir_cartao` (desfazer), registrar e mostrar "LANÇAMENTO DESFEITO — CONFERIR NA TELA".
3. **`--confirmar` liberado só para UM cartão por comando** (`--nsu <nsu>`), com travas `WEBPOSTO_WRITES=1` e `LOGOS_ERP_ESCRITA=1` lidas só do arquivo `.env`. Modo automático no robô: **preparado e DESLIGADO** (nova trava `LOGOS_CARTAO_AUTOMATICO`, só no `.env.example` com 0).
4. **O Logos explica sozinho, em português simples (decisão do diretor, 15/10/2026: "isso é o que o sistema LOGOS – fechamento de caixa deve fazer, não o Claude").** Para cada cartão faltante, o Logos gera (tela, Telegram e comando) um texto como:
   > **Doze · Pista (caixa 4466831), 14/10/2026 11:26** — o PagBank recebeu um **Mastercard de R$ 34,75** do frentista **AILTON LUIZ DA SILVA (299239)**, venda 377600619, mas o cartão **não está lançado** no webPosto. Por isso o caixa mostra **R$ 34,75 a mais em dinheiro** do que deveria. **Posso lançar** (Mastercard PagSeguro, NSU final 0163). Depois de lançar, o dinheiro esperado cai R$ 34,75 e o cartão sobe R$ 34,75.
   E, para o que **não** pode lançar, diz o porquê em uma linha ("R$ 139,35 não é cartão — é PIX/BACEN, conferir à mão"; "nota baixa: dois abastecimentos possíveis"). Nada de jargão técnico (sem "nota ≥ 90", "candidato único", "idempotência") no texto ao diretor.
   **Aprovação em um toque:** no Telegram, botão **[Lançar]** / **[Não lançar]** abaixo da mensagem (só o chat do diretor), e o mesmo botão na tela. O toque executa o mesmo caminho do `--confirmar --nsu` (travas, reconsulta, conferência, desfazer). Com `LOGOS_CARTAO_AUTOMATICO=1` (desligado por padrão) o Logos lança sozinho os que cumprem a regra e só avisa.
5. **Tela e aviso:** aba "Lançamentos do Logos" no Painel (o que, quando, valor, caixa "posto · setor (nº)", frentista nome + código, evidências, botão **Desfazer** só para o diretor). No resumo do Telegram: "Lancei N cartões · R$ X" quando houver.

## Teste com o diretor

1. Rodar a prévia (`python -m src.jobs.lancar_cartao --unidade <cod> --dia dd/mm/aaaa`) no Doze e no Casa Caiada, dos últimos dias, e mostrar os elegíveis.
2. **Parar e pedir ao diretor** para ligar as duas travas no `.env` (lembrar: `WEBPOSTO_WRITES` está duplicada — deixar **uma** linha) e escolher **um** cartão.
3. Lançar esse cartão, mostrar antes/depois do caixa (dinheiro e cartão apurados) e a conciliação casando por NSU. Se a resposta for 401/403 → parar (pedir permissão à Quality).
4. No final, lembrar o diretor de **voltar as travas para 0**.

Atualizar RN-ERP-001 (`REGRAS_DE_NEGOCIO.md`), ADR-003 e `STATUS.md`.
Commit: `feat(erp): piloto de lançamento de cartão com conferência e desfazer`. Depois `git push`.
