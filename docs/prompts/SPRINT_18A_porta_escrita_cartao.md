# Prompt — SPRINT 18a: porta de escrita de cartão (pronta e DESLIGADA, sem enviar nada)

**Só começar depois que a Sprint 17B.1 estiver concluída** (reaproveita a leitura das travas só do arquivo `.env`).

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). **Nesta sprint NADA é enviado ao webPosto.** `.env` só via `load_dotenv`/`dotenv_values`, nunca imprimir nem editar. Sem reescrever arquivos inteiros. Testes sintéticos com cliente falso; rodar só os testes novos durante o trabalho e a bateria completa no final. Meta: ~25 min.

Contexto completo e decisão do diretor: `docs/prompts/SPRINT_18_piloto_lancamento_cartao.md` (ler só como referência; esta sprint faz **apenas a Parte A** dele). Lição do incidente do OFX (STATUS.md): status 201 não é prova de sucesso; trava nunca vem do ambiente do processo.

@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/propostas_lancamento.py
@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_cartoes.py

## O que fazer

1. **`adapters/webposto_escrita_cartao.py`** (separado dos adapters de leitura): só `incluir_cartao` e `excluir_cartao` (desfazer). Rota `POST /INTEGRACAO/V1/CARTOES` e `DELETE /INTEGRACAO/V1/CARTOES/{id}` — campos **só os da spec oficial** (`docs/external/webposto/openapi_integracao_2026-10-06.json`), nada inventado. Sem `PATCH` nesta sprint.
2. **Travas:** usar a mesma função da 17B.1 (lida só do arquivo `.env`, recusa nome duplicado). Exige `WEBPOSTO_WRITES=1` **e** `LOGOS_ERP_ESCRITA=1`. Teste: com ambiente do processo = 1 e arquivo = 0 → **nenhuma** chamada sai do cliente falso.
3. **Montar o payload a partir de uma proposta** já existente (`propostas_lancamento.py`): NSU, autorização, administradora, venda, caixa, frentista, valor, data. Faltou qualquer um → não monta (motivo claro).
4. **Mapa bandeira da adquirente → `administradoraCodigo`** por unidade, a partir de `GET /INTEGRACAO/V1/ADMINISTRADORAS` (somente leitura; em teste, dados falsos). Amex nas unidades Doze e Casa Caiada = PagBank. Sem correspondência única → não monta.
5. **Prévia (comando padrão, não envia):** `python -m src.jobs.lancar_cartao --unidade <cod> --dia dd/mm/aaaa` lista as propostas elegíveis com frentista (nome + código), valor, NSU, administradora escolhida e o payload resumido. A opção `--confirmar` existe mas, **nesta sprint, recusa sempre** com "piloto não liberado (Sprint 18b)".
6. **Auditoria append-only** em `data/lancamentos_logos/<empresa>/` (fora do Git): o quê, por quê (evidências), quem autorizou, payload (sem chave), resposta, id criado e como desfazer. Teste grava e lê um registro sintético.
7. Documentar na RN-ERP-001 (`REGRAS_DE_NEGOCIO.md`) que a porta existe e está desligada; atualizar o `STATUS.md`.

Testes: travas só do arquivo; nenhuma escrita com travas desligadas; payload só com campos da spec; proposta incompleta não monta; administradora ambígua não monta; `--confirmar` recusado; auditoria append-only.

Ao final, rodar a prévia **real** (somente leitura) do Casa Caiada 5555 no dia 10/10/2026 e mostrar a lista no chat (`set PYTHONIOENCODING=utf-8`).
Commit: `feat(erp): porta de escrita de cartão isolada, desligada, com prévia e auditoria`. Depois `git push`.
