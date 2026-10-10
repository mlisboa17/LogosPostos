# Prompt — COMERCIAL-01: Placar diário de metas dos postos (gestão à vista)

> Executar **depois** das fases CASH-AUDIT-03 e CASH-AUDIT-04 (recebimentos, robô noturno, datas padrão Brasil) estarem commitadas.
> Workspace: `C:\Projetos\LOGOS\LogosPostos`. Fase a fase, com testes e commit em cada uma. Sem push/merge/troca de branch.

## Objetivo

Substituir a planilha manual "Placar Diário" (exemplo: `acompanhamento_diario_posto_vip_outubro_2026.xlsx`, **só referência de layout/conceito — os números dela não são reais**) por um acompanhamento **100% automático** a partir do webPosto.

## Regras de negócio (decididas pelo sócio-diretor Marcio Lisboa, 2026-10-07)

- **Escopo:** somente **postos** — VIP (11495), Doze Filial (74014), Casa Caiada (5555). **Conveniências não entram** (Conveniência 24h 118508 fica fora).
- **Volume da meta = litros de todos os combustíveis** (gasolina comum, gasolina aditivada, etanol, diesel…), somando `quantidade` de `GET /INTEGRACAO/V1/ABASTECIMENTOS`, **excluindo aferição** (`afericao = true`).
- **Quem define as metas:** o sócio-diretor. Metas mensais por posto em 3 níveis — **Bronze (oficial), Prata (desafio), Ouro (excelência)** — e **meta de ticket médio (litros/atendimento) por frentista**.
- **Frentista** = `codigoFrentista` do abastecimento (identfid); nome via `GET /INTEGRACAO/V1/FUNCIONARIOS`.
- **Atendimento:** venda distinta com combustível (abastecimento → `vendaItemCodigo` → `VENDAS/ITENS.vendaCodigo`). Reporte também a contagem por abastecimento e explique a diferença no resumo; se a venda não estiver disponível, use o abastecimento como atendimento.
- **Datas no padrão Brasil** (prompt CASH_AUDIT_04): fuso `America/Recife`, exibição `dd/mm/aaaa`; volumes exibidos `12.345 L`, ticket `7,84 L/carro`, percentuais `82,4%`.

## Cálculos — regra versionada `PLACAR_V1` (funções puras + testes)

Para cada posto e mês, com dia de referência D (padrão: hoje no fuso de Recife):

| Indicador | Cálculo |
|---|---|
| Realizado do dia / acumulado | litros por dia; acumulado do dia 1 até D |
| % de cada meta | acumulado ÷ meta (Bronze, Prata, Ouro) |
| Faltante por meta | max(0, meta − acumulado) |
| Dias restantes | **calendário**: dias de D até o fim do mês, incluindo D se D ainda não fechou (não usar "dias preenchidos" como a planilha) |
| **Meta viva do dia** (por nível) | faltante (até D−1) ÷ dias restantes |
| Média diária exigida | meta ÷ dias do mês (calculado — a planilha tinha `5903` fixo) |
| Status do dia | realizado vs média exigida e vs meta viva (acima/abaixo) |
| Meta viva por frentista | meta viva do dia ÷ frentistas ativos (com abastecimento nos últimos 7 dias) — a planilha tinha `÷12` fixo |
| **Projeção de fechamento** | acumulado + média diária realizada × dias restantes → qual nível será atingido |
| Mix por combustível | litros por produto; % de aditivados no total e por frentista |
| Por frentista (mês) | atendimentos, litros, **ticket médio (L/atendimento)**, meta de ticket, **ganho exigido no bico** = meta − realizado, impacto projetado = atendimentos projetados × meta de ticket |
| Ranking | por ticket médio e por volume; destaque de quem está abaixo da meta individual |

Mês parcial, mês sem meta cadastrada (mostrar só realizado, sem erro) e frentista sem meta individual devem ser tratados e testados.

## Arquitetura

- Contexto **Commercial Intelligence** (`LOGOS_CONTEXT_MAP.md` § 2.5) → **módulo novo** `WebPosto_API/src/modules/commercial_performance/` (`domain/`, `rules/`, `adapters/`, `application/`, `interfaces/`, `config/`).
- **Não importar de `cash_reconciliation`.** Extraia o acesso ao webPosto (`adapters/webposto_http.py` → `paginar`, `WebPostoErro`) e os helpers de data (`domain/tempo.py`) para um módulo compartilhado `src/modules/webposto_integration/` (contexto Data Integration § 2.2). Mantenha em `cash_reconciliation` reexportações finas para não quebrar nada; todos os testes existentes devem continuar verdes.
- **Metas (dado do negócio, sensível):** arquivo por mês em `WebPosto_API/data/metas/AAAA-MM.json` (pasta já fora do Git via `.gitignore` de `data/`). Versione apenas um **exemplo sintético** `config/metas_exemplo.json` documentando o formato:
  ```json
  {"mes": "2026-10", "definido_por": "Marcio Lisboa (sócio-diretor)",
   "postos": {"11495": {"bronze": 183000, "prata": 190000, "ouro": 198000,
                         "frentistas": {"<funcionarioCodigo>": {"meta_ticket": 7.5}}}}}
  ```
  Frentistas identificados por **código** (não versionar nomes de funcionários). Validar com Pydantic (níveis crescentes, valores positivos).
- **Tela de cadastro de metas:** fora deste prompt — exige login e restrição ao sócio-diretor (tarefa de autenticação pendente). Por ora o arquivo é preenchido com o diretor.

## Fases

1. **Domínio + regra `PLACAR_V1` + adapters** (abastecimentos, funcionários, produtos, vendas/itens) + leitura das metas. Testes sintéticos. Rodar com dados reais do VIP em out/2026 e reportar realizado diário, atendimentos e ticket por frentista (sem nomes no relatório: use código).
2. **API:** `GET /api/v1/commercial/placar?posto=&mes=AAAA-MM&dia=` e `GET /api/v1/commercial/postos` (só os 3 postos). Testes sem rede.
3. **Tela "Placar de Metas"** em `frontend/pages/` (novo item de menu), mesmo estilo dark da Auditoria de Caixa:
   - cabeçalho: seletor de posto e mês;
   - cards: acumulado, % Bronze/Prata/Ouro com **barras de progresso**, meta viva de hoje por nível, projeção de fechamento ("no ritmo atual: Prata ✔");
   - tabela diária (dia, litros, acumulado, status, meta viva recalculada) — como a planilha, mas automática;
   - tabela de frentistas (nome, atendimentos, litros, ticket, meta, ganho no bico, posição no ranking);
   - mix por combustível;
   - **modo TV** (`?view=placar&tv=1`): tela cheia, fontes grandes, atualização automática a cada 10 min, para gestão à vista na pista.
4. **Robô noturno:** acrescentar a etapa do placar (persistir em `data/placar/<mes>/<posto>.json`); a tela lê o persistido e completa o dia corrente ao vivo.

## Restrições

Somente leitura no ERP · `.env` só via `load_dotenv`, nunca imprimir valores · nada de dados fictícios quando a fonte falhar ("fonte indisponível") · testes só com dados sintéticos · regra nova = versão nova · sem push/merge/troca de branch.

## Entrega por fase

Saída do pytest · commit `feat(commercial): ...` · resumo com arquivos, números reais (VIP out/2026) e decisões.
