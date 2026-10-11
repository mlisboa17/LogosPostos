# LOGOS Auditoria — contexto para qualquer IA que for ajudar (Gemini, ChatGPT, Copilot, Cursor, Antigravity)

Leia antes de sugerir qualquer coisa. Atualizado em 11/10/2026.

## O que é

O **LOGOS** é o "funcionário auditor" de uma rede de postos de combustível (dono: Marcio Lisboa, sócio-diretor). O **webPosto** (ERP da Quality Automação) é o **sistema principal** dos 11 postos; o LOGOS **lê** o webPosto e as adquirentes, **confere**, **aponta quem errou** e, com travas, **devolve ao webPosto** só o que tem certeza. O LOGOS não substitui o webPosto.

Hoje o LOGOS confere 4 unidades: **Doze 74014**, **VIP 11495** (pista + conveniência no mesmo CNPJ), **Casa Caiada 5555**, **Conveniência 24h 118508**. As outras 7 virão depois (de outros donos também — ADR-004).

## Onde fica e quem faz o quê

- Projeto oficial (o ÚNICO que vale): `C:\Projetos\LOGOS\LogosPostos` · GitHub `mlisboa17/LogosPostos` · branch `feature/cash-audit-fechamento`.
- A pasta antiga do OneDrive (`...\LOGOS SPACE\Api_WebPosto`) é **arquivo morto**: não trabalhar nela; serve só de consulta.
- **Arquiteto/revisor:** Claude (Claude Code). **Construtores:** um agente por vez (VS Code, Cursor ou Antigravity), **sempre a partir de um prompt de sprint em `docs/prompts/`**. **Decisões:** o diretor.
- **Regra de ouro: nenhuma IA implementa plano que não esteja numa sprint aprovada.** Ideias novas vêm como **proposta** (formato abaixo) para o arquiteto conferir com o que já existe.

## Documentos que mandam

| Documento | Para quê |
|---|---|
| `STATUS.md` | O que está pronto, em andamento, próximos passos e sprints futuras |
| `docs/regras-negocio/REGRAS_DE_NEGOCIO.md` | Todas as regras do negócio (IDs RN-...) decididas pelo diretor |
| `docs/architecture/adr/ADR-001..005` | Monólito modular; ordem do trabalho; **escrita no ERP só com travas (ADR-003)**; grupos/unidades/setores (ADR-004); aprendizado e IA só como assistente (ADR-005) |
| `docs/external/webposto/openapi_integracao_*.json` | **API oficial do webPosto** — não inventar rotas fora dela |
| `docs/external/maispagamentos/`, `docs/external/cielo/` | APIs oficiais das adquirentes |

## O que já existe (não refazer)

- Módulo `WebPosto_API/src/modules/cash_reconciliation/`: fechamento de caixa (FECHAMENTO_V4), conciliação de cartões (CARTOES_V3_4: NSU, troca de forma, duplicidade, Cartão POS), PagBank EDI, Premmia (robô do portal), pendências com prazo, relatório do caixa do dia com status ✅/❌/⏳, Painel do Diretor, Conferência de Recebimentos (Lançar / Alterar / Apurar / Conferir à mão), Telegram diário.
- Módulo `WebPosto_API/src/modules/commercial_performance/`: **placar de metas e litros por frentista** (base para qualquer ranking de frentistas — evoluir este, não criar outro).
- Robô noturno às 03:00 (`src/jobs/noturno.py`).

## Regras técnicas fixas

Python + FastAPI + **Pydantic** (sem Pandas no núcleo) · `.env` só via `load_dotenv`, nunca imprimir/versionar segredos · somente leitura no webPosto, exceto as escritas liberadas pela ADR-003 (cada uma com travas no `.env`, prévia, auditoria e desfazer) · datas `dd/mm/aaaa` (America/Recife) · toda ocorrência mostra **nome + código do frentista** · dados reais nunca no Git (`WebPosto_API/data/`) · testes sintéticos · sprints pequenas (20–30 min).

## Como propor uma ideia (formato)

```
IDEIA: <nome curto>
PROBLEMA QUE RESOLVE: <o que o diretor ganha>
O QUE JÁ EXISTE NO LOGOS QUE SERÁ REAPROVEITADO: <módulo/arquivo>
DADOS NECESSÁRIOS: <rotas OFICIAIS do webPosto/adquirentes que existem na spec>
ESCREVE NO WEBPOSTO? <não / sim — qual rota e quais travas (ADR-003)>
RISCOS:
TAMANHO: <pequena / média / grande>
```
Sem código nesta etapa. O arquiteto confere e transforma em sprint em `docs/prompts/`.

## Sprints futuras já anotadas (não começar sem ordem)

Piloto de lançamento de cartão (18a/18b) · Investigador IA com Gemini (16) · Extratos no Logos (17) · Importar OFX no webPosto com barreira (17B, em andamento) · Tela nova de conferência · Ranking de frentistas (vendas **e** qualidade: trocas de forma, faltas, duplicidades), evoluindo o placar existente · Mais Pagamentos, Cielo e Rede (aguardando credenciais) · Limpeza do código e telas antigas.
