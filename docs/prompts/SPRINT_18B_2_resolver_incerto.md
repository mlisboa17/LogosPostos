# Prompt — SPRINT 18b.2 (correção rápida): descobrir por que o 1º lançamento falhou e permitir resolver "incerto"

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). `.env` só via `load_dotenv`/`dotenv_values`, nunca imprimir nem editar. Sem reescrever arquivos. **Nenhum lançamento nesta sprint** (travas em 0). Testes sintéticos. Meta: 20–30 min.

@WebPosto_API/src/modules/cash_reconciliation/application/piloto_cartao.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_cartao.py
@WebPosto_API/src/jobs/lancar_cartao.py

## O que aconteceu

`data/lancamentos_logos/74014/historico.json`: em **15/10/2026 16:44:58** houve uma execução com `--confirmar` do cartão Mastercard R$ 34,75 (NSU final 0163, Doze 14/10): estado `reservado` e, 4 segundos depois, `incerto` — o envio levantou erro e **o motivo não foi gravado**. Hoje o Logos bloqueia tudo no posto/dia ("Existe uma operação não conferida…") e **não existe comando para resolver**.
Conferência do arquiteto (somente leitura, 15/10 noite): `V1/CARTOES` do Doze 14–15/10 tem 599 cartões e **nenhum de R$ 34,75**; dinheiro e cartão do caixa iguais aos de antes → **nada entrou no webPosto**.

## Correções

1. **Gravar o motivo** em todo `incerto`/`falha_conferencia`: tipo do erro, status HTTP, mensagem do webPosto (sem chave/token), e a etapa (travas, envio, conferência). Mostrar ao diretor em português simples: "o webPosto recusou: sem permissão de escrita (403) — pedir à Quality" / "travas desligadas" / "sem resposta do webPosto".
2. **Descobrir o motivo de 16:44 sem enviar nada:** reproduzir com cliente falso e, se possível, pelos logs locais/stdout; dizer se foi trava, 401/403, 400 (campo inválido no payload — conferir o payload gravado contra `IncluirAlterarCartaoDto` da spec) ou rede. Se não for possível saber, dizer isso.
3. **Comando para resolver o incerto:** `python -m src.jobs.lancar_cartao --unidade 74014 --dia 14/10/2026 --resolver --nsu <nsu>`: o Logos **reconsulta** (somente leitura) `V1/CARTOES` e o caixa; se não houver cartão com o NSU e os saldos estiverem iguais aos de "antes" → registra `nao_entrou` (resolvido, autorizado pelo diretor) e libera o posto/dia; se o cartão existir → registra `entrou_sem_conferencia` e mostra o código para o diretor decidir (não apaga sozinho). Sempre explicando em português simples.
4. Testes: motivo gravado para cada tipo de erro; resolver com "não entrou"; resolver com "entrou"; bloqueio continua enquanto não resolver.

Ao final, rodar `--resolver` **real** (só leitura) para o NSU do cartão do Ailton e mostrar o texto do Logos. Não lançar.
Commit: `fix(erp): motivo do incerto e comando para resolver`. Depois `git push`.
