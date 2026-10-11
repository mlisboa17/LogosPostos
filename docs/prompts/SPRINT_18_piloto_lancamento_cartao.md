# Prompt — SPRINT 18: piloto de lançamento automático de cartão no webPosto (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. **Primeira escrita do Logos no ERP** — siga a ADR-003 à risca. `.env` só via `load_dotenv`, nunca imprimir; sem reescrever arquivos; testes **sem chamar o webPosto real** (cliente falso). Nada pelo Telegram nesta sprint. Nomes de funcionários permitidos no chat.

## Decisão do diretor (11/10/2026)

"As vendas que ele reconheceu e teve um alto índice, ele pode já inserir, caso consiga." Autorizado **pular para a Fase 2 da ADR-003 (automático com limite)** **apenas** para o tipo **"cartão recebido na adquirente e ausente no webPosto, com venda/abastecimento identificado"**, depois de um **teste controlado com o diretor acompanhando**.

## O que já sabemos (observação real, Casa Caiada 09/10/2026, caixa 4462031)

O diretor lançou à mão 4 cartões que o Logos tinha apontado (tipo `Manualmente`, **sem venda e sem NSU**):
- Antes: dinheiro apurado **R$ 2.296,19**; cartão R$ 14.609,98. Depois: dinheiro apurado **R$ 2.167,44** (−R$ 128,75) e cartão **R$ 14.738,73** (+R$ 128,75). **Incluir o cartão no caixa reduz o dinheiro esperado — não conta em dobro.** (Confirmar isso no teste; pode depender de `vendaCodigo`.)
- Como foram lançados sem NSU/venda e com bandeira diferente (Elo R$ 30,00 lançado como Maestro; Amex R$ 34,75 como Elo Débito, 15:28 em vez de 15:26), o Logos só consegue casá-los como "par provável". **O lançamento automático deve gravar NSU, autorização, bandeira/administradora certa, venda e hora** para que a conciliação seguinte case por NSU.
- A administradora "AMERICAN EXPRESS" nessas unidades **é do PagBank** (confirmado pelo diretor em 11/10/2026): não é erro e não precisa de correção.

## API (spec oficial, `docs/external/webposto/openapi_integracao_2026-10-06.json`)

`POST /INTEGRACAO/V1/CARTOES` com `vendaCodigo, administradoraCodigo, caixaCodigo, dataMovimento, dataFiscal, vencimento, autorizacao, nsu, valor, valorTransacao, parcela, funcionarioCodigo, centroCustoCodigo, taxaPercentual`; `PATCH /INTEGRACAO/V1/CARTOES/{id}`; `DELETE /INTEGRACAO/V1/CARTOES/{id}` (para desfazer). Não existe rota para trocar a forma de pagamento da venda. **Não inventar campos** (ex.: hora): descobrir no teste como a hora é gravada.

## PARTE A — Porta de escrita isolada

1. `adapters/webposto_escrita.py` (separado dos adapters de leitura): só `incluir_cartao`, `excluir_cartao` (desfazer) e, preparado mas **desligado**, `alterar_cartao`. Bloqueia tudo se `LOGOS_ERP_ESCRITA != 1` **ou** `WEBPOSTO_WRITES != 1`. Teste prova que, desligado, **nenhuma** chamada de escrita sai.
2. Mapa **bandeira da adquirente → `administradoraCodigo`** por unidade, lido de `V1/ADMINISTRADORAS` (ex.: Mastercard PagBank → "MASTERCARD PAGSEGURO"); sem correspondência única → não lança.
3. Registro de auditoria append-only (`data/lancamentos_logos/`, fora do Git): o quê, por quê (evidências e nota), quem autorizou (diretor/automático), payload enviado (sem chave), resposta do ERP, id criado e **como desfazer**.

## PARTE B — Regra do piloto (todas as condições)

Lançar automaticamente só se: tipo = recebido na adquirente (PagBank) **sem cartão** no webPosto; **venda identificada** (venda/abastecimento do frentista com valor igual) e **nota ≥ 90 com candidato único**; **caixa não consolidado**; valor ≤ **R$ 300,00** e soma do dia ≤ **R$ 1.000,00** por unidade; cartão ainda inexistente no momento do lançamento (reconsultar antes de escrever; idempotência por NSU). Qualquer dúvida → vira proposta para o diretor (Fase 1, "um toque"), não lança.
Depois de lançar: reconsultar o caixa e a conciliação; se o cartão não casar por NSU ou o dinheiro esperado não cair no valor do cartão → **desfazer** (DELETE), registrar e avisar.

## PARTE C — Teste controlado (com o diretor acompanhando)

1. Antes: verificar se a chave da API tem **permissão de escrita** (primeira chamada; se 401/403 → parar e informar que é preciso pedir à Quality).
2. Escolher **um** caso real elegível de um caixa **não consolidado** (dia mais recente disponível), mostrar ao diretor o payload e as evidências e **só lançar após o "ok" dele no chat**.
3. Mostrar o antes e depois do caixa (dinheiro e cartão apurados) e o resultado da conciliação (deve casar por NSU). Se algo sair errado, desfazer e mostrar.
4. Não executar o modo automático no robô nesta sprint: deixar pronto e **desligado**; o diretor liga depois.

## PARTE D — Tela e avisos

Painel: aba "Lançamentos do Logos" (o que foi lançado, quando, valor, frentista, evidências, botão **Desfazer** só para o diretor). Resumo diário: "Lancei N cartões · R$ X" quando o modo estiver ligado.

Atualizar a ADR-003 (registro da decisão do diretor) e o `REGRAS_DE_NEGOCIO.md` (RN-ERP-001: tipo liberado e limites). Rodar os testes de sempre.
Commits: `feat(erp): porta de escrita isolada com interruptor e auditoria`, `feat(erp): piloto de lançamento automático de cartão`. Depois `git push`.
