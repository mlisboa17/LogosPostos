# Regras de Negócio — LOGOS Auditoria

> Documento vivo. Fonte única das regras operacionais, financeiras e de conciliação de cada unidade.
> **Só entram regras confirmadas pelo diretor ou comprovadas nos dados.** O que ainda não foi definido fica em "A definir" — nunca inventar valores.
> Última revisão: 10/10/2026 · Responsável pelas decisões: sócio-diretor (Marcio Lisboa).

## Sumário

1. [Como usar e manter](#1-como-usar-e-manter)
2. [Template de regra](#2-template-de-regra)
3. [Unidades](#3-unidades)
4. [Regras gerais da rede](#4-regras-gerais-da-rede-rn-rede)
5. [Caixa e fechamento](#5-caixa-e-fechamento-rn-caixa)
6. [Sangria e destino do dinheiro](#6-sangria-e-destino-do-dinheiro-rn-sangria)
7. [Cartões, PIX e adquirentes](#7-cartões-pix-e-adquirentes-rn-cartao)
8. [Premmia](#8-premmia-rn-premmia)
9. [Pendências e cobrança](#9-pendências-e-cobrança-rn-pend)
10. [Metas comerciais](#10-metas-comerciais-rn-meta)
11. [Escrita no ERP](#11-escrita-no-erp-rn-erp)
12. [A definir](#12-a-definir)
13. [Histórico](#13-histórico)

---

## 1. Como usar e manter

- **Arquivo único** enquanto houver até ~100 regras; depois, dividir em `docs/regras-negocio/<escopo>.md` mantendo os mesmos IDs.
- **ID estável:** `RN-<ESCOPO>-<NNN>`. Escopos: `REDE` (vale para todas), `CAIXA`, `SANGRIA`, `CARTAO`, `PREMMIA`, `PEND`, `META`, `ERP`. Regra só de uma unidade usa o campo **Unidades** — não cria escopo novo.
- **Nunca reaproveitar ID.** Regra que deixa de valer: status `revogada`, com data e motivo.
- **Toda regra cita onde está implementada** (arquivo e versão da regra no código, ex.: `FECHAMENTO_V4`). Mudou a regra → nova versão no código **e** nova linha no histórico da regra.
- **Quem pode mudar:** o diretor decide; o arquiteto (Claude) redige; o agente implementa. Agente que encontrar comportamento sem regra aqui **para e pergunta**, não inventa.
- **Agentes de IA:** os blocos de cada regra seguem o template abaixo, com campos fixos, para leitura automática. Prompts de sprint devem citar os IDs que implementam.
- **Dados sensíveis:** nada de CPF, nome de funcionário/cliente, número de conta completo, senha ou token neste arquivo.

## 2. Template de regra

```markdown
### RN-<ESCOPO>-<NNN> — <título curto>
| Campo | Valor |
|---|---|
| Unidades | Todas / Doze 74014 / VIP 11495 / Casa Caiada 5555 / Conv. 24h 118508 |
| Módulo | Caixa · Pista · Conveniência · TEF/Cartões · Premmia · Fiscal · Estoque/LMC · Metas · ERP |
| Padrão | <comportamento normal da rede> |
| Exceção | <o que muda para a(s) unidade(s), ou "—"> |
| Gatilho | <quando a regra dispara> |
| Ação no sistema | <alerta/cor/pendência/informativo/bloqueio> |
| Implementação | <arquivo · versão da regra> |
| Status | vigente · proposta · revogada |
| Vigência | dd/mm/aaaa — <origem: decisão do diretor / evidência nos dados> |
```

## 3. Unidades

| Unidade | empresaCodigo | Tipo | Observações |
|---|---|---|---|
| Posto Doze Filial II | 74014 | Posto | Substitui o antigo "Posto Real" (códigos 5558/7, CNPJ desativado — não usar) |
| Posto VIP | 11495 | Posto + conveniência | Conveniência VIP com centro de custo FOOD (24423) |
| AP Casa Caiada | 5555 | Posto | — |
| Conveniência 24 Horas | 118508 | Conveniência (empresa própria) | Não entra em metas de litros |

---

## 4. Regras gerais da rede (RN-REDE)

### RN-REDE-001 — Datas no padrão Brasil
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Todos |
| Padrão | Fuso America/Recife; exibição `dd/mm/aaaa HH:mm`; ISO só no transporte técnico |
| Exceção | — |
| Gatilho | Qualquer data exibida, gravada ou comparada |
| Ação no sistema | Helpers de `domain/tempo.py`; frontend com helper único `utils/datas.js` e campos de texto mascarados `dd/mm/aaaa`, nunca `input type=date`; CSV/PDF em português e Excel com datas reais |
| Implementação | `cash_reconciliation/domain/tempo.py` · frontend/utils/datas.js (format.js mantém aliases compatíveis) |
| Status | vigente |
| Vigência | 08/10/2026 — decisão do diretor |

### RN-REDE-002 — Nome do frentista em toda ocorrência
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Todos |
| Padrão | Toda ocorrência (pendência, tela, Telegram, planilha) mostra "Nome do frentista (código)". Na conferência: atribuído único (≥80); melhor sugestão (50–79) com nota e motivos; empate lista todos; sem abastecimento usa todos os responsáveis pelos caixas abertos no horário |
| Exceção | Só "frentista não identificado" quando não houver candidato nem caixa no horário; informar o motivo. Nome ausente nos dados gravados aparece como indisponível, nunca consultar o ERP no endpoint |
| Gatilho | Criação de alerta/pendência |
| Ação no sistema | Nome via `buscar_nomes_funcionarios`; nomes só em `data/` (fora do Git) |
| Implementação | `webposto_integration/funcionarios.py` · CARTOES_V3_1 |
| Status | vigente |
| Vigência | 10/10/2026 — decisão do diretor |

### RN-REDE-003 — Somente leitura no ERP
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | ERP |
| Padrão | O Logos só lê o webPosto (`WEBPOSTO_WRITES=0`) |
| Exceção | Autonomia gradual de escrita conforme RN-ERP-001 / ADR-003 |
| Gatilho | Qualquer chamada à API do webPosto |
| Ação no sistema | Chamadas de escrita bloqueadas |
| Implementação | `webposto_integration/http.py` |
| Status | vigente |
| Vigência | 06/10/2026 |

### RN-REDE-004 — Conciliação de depósitos fora do escopo
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Caixa |
| Padrão | Não conferir depósito bancário × extrato por enquanto (há depósitos de outras origens nas mesmas contas) |
| Exceção | — |
| Gatilho | — |
| Ação no sistema | Matriz de destino serve só para classificar a sangria (RN-SANGRIA) |
| Implementação | — |
| Status | vigente |
| Vigência | 07/10/2026 — decisão do diretor |

### RN-REDE-005 — Resumo diário pelo Telegram
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Robô |
| Padrão | Após o robô das 03:00, envia ao diretor resumo por filial (faltas com nome, despesas, vales, recebimentos, pendências) + planilha |
| Exceção | Reprocessamento manual não envia, salvo `--enviar-telegram` |
| Gatilho | Fim do robô noturno, `TELEGRAM_ENVIO=1` |
| Ação no sistema | Falha de envio = aviso, não falha do robô |
| Implementação | `src/jobs/noturno.py` · `resumo_diario.py` |
| Status | vigente |
| Vigência | 10/10/2026 |

### RN-REDE-006 — Período da conferência
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Conferência de recebimentos |
| Padrão | Fim máximo hoje − 2 dias (Recife); até 7 dias inclusivos; padrão hoje − 8 a hoje − 2 |
| Exceção | Relatório histórico local de 01–09/10 gerado da persistência, fora da consulta interativa |
| Gatilho | Consulta/exportação/decisão da conferência |
| Ação no sistema | Backend e tela recusam datas futuras/ontem/hoje ou mais de 7 dias, com mensagem clara |
| Implementação | interfaces/http.py · frontend/utils/datas.js · conferenciaRecebimentos.js |
| Status | vigente |
| Vigência | 11/10/2026 — decisão do diretor |

---

## 5. Caixa e fechamento (RN-CAIXA)

### RN-CAIXA-001 — Quebra de caixa
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Caixa |
| Padrão | Diferença por modalidade (apresentado × apurado) acima de **R$ 10,00** = alerta vermelho |
| Exceção | Caixa ainda aberto não tem quebra (só após o fechamento) |
| Gatilho | Caixa fechado |
| Ação no sistema | Pendência vermelha individual |
| Implementação | `rules/fechamento.py` · FECHAMENTO_V4 (`LIMITE_QUEBRA`) |
| Status | vigente |
| Vigência | 06/10/2026 |

### RN-CAIXA-002 — Falta de dinheiro sem desconto
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Caixa |
| Padrão | Falta em dinheiro > R$ 10,00 sem vale de origem "D" (falta de caixa) do operador no mesmo caixa = vermelho; vale com valor diferente da falta = laranja |
| Exceção | — |
| Gatilho | Caixa fechado com falta em dinheiro |
| Ação no sistema | Pendência; mensagem indica se o caixa ainda não foi consolidado |
| Implementação | `rules/fechamento.py` · FECHAMENTO_V4 |
| Status | vigente |
| Vigência | 08/10/2026 |

### RN-CAIXA-003 — Caixa parado (não consolidado)
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Caixa |
| Padrão | Fechado e não consolidado: até 2 dias = laranja; mais de 2 dias = vermelho |
| Exceção | — |
| Gatilho | Caixa fechado sem consolidação |
| Ação no sistema | Alerta `NAO_CONSOLIDADO` |
| Implementação | `rules/fechamento.py` · `dias_tolerancia_consolidacao` |
| Status | vigente |
| Vigência | 08/10/2026 |

### RN-CAIXA-004 — Despesa do caixa sem plano de contas
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Caixa |
| Padrão | Despesa lançada no caixa sem plano de contas = laranja |
| Exceção | — |
| Gatilho | Movimento de despesa (tipo D) |
| Ação no sistema | Alerta `DESPESA_SEM_PLANO`; aparece no Telegram como "SEM PLANO ⚠" |
| Implementação | `rules/fechamento.py` |
| Status | vigente |
| Vigência | 08/10/2026 |

### RN-CAIXA-005 — Conveniência VIP e o Food
| Campo | Valor |
|---|---|
| Unidades | VIP 11495 (conveniência) |
| Módulo | Conveniência |
| Padrão | — |
| Exceção | Food é centro de custo próprio (24423), "negócio à parte"; compras do Food entram como nota de entrada e são pagas com dinheiro da conveniência, com acerto que sai do Food. A espécie das vendas Food é guardada em reserva (não depositada) |
| Gatilho | Fechamento semanal da conveniência VIP |
| Ação no sistema | Referência para conferência futura: depósito esperado = espécie da conveniência sem o Food |
| Implementação | — (fora do escopo atual, ver RN-REDE-004) |
| Status | proposta |
| Vigência | 06/10/2026 — informado pelo diretor |

---

## 6. Sangria e destino do dinheiro (RN-SANGRIA)

### RN-SANGRIA-001 — Sangria sem conta de destino
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Caixa |
| Padrão | Sangria sem `contaCodigo` = vermelho |
| Exceção | Ver RN-SANGRIA-002 e 003 |
| Gatilho | Sangria do caixa |
| Ação no sistema | Alerta `SANGRIA_SEM_DESTINO` |
| Implementação | `rules/fechamento.py` · FECHAMENTO_V4 |
| Status | vigente |
| Vigência | 06/10/2026 |

### RN-SANGRIA-002 — Conveniência 24h repassa ao Casa Caiada
| Campo | Valor |
|---|---|
| Unidades | Conv. 24h 118508 |
| Módulo | Caixa |
| Padrão | RN-SANGRIA-001 |
| Exceção | Sangria sem conta é normal: o dinheiro vai para o Casa Caiada |
| Gatilho | Sangria sem conta na 118508 |
| Ação no sistema | Informativo "repassada ao Casa Caiada", sem pendência |
| Implementação | `units.json` (`repasse_sangria_para: 5555`) · FECHAMENTO_V4 |
| Status | vigente |
| Vigência | 10/10/2026 — decisão do diretor |

### RN-SANGRIA-003 — Casa Caiada: sangria vai para o cofre
| Campo | Valor |
|---|---|
| Unidades | Casa Caiada 5555 |
| Módulo | Caixa |
| Padrão | RN-SANGRIA-001 |
| Exceção | Sangria sem conta é normal: vai para o cofre (conta padrão 17837) |
| Gatilho | Sangria sem conta na 5555 |
| Ação no sistema | Informativo "assumida no cofre", sem pendência |
| Implementação | `units.json` (`destino_padrao`) · FECHAMENTO_V4 |
| Status | vigente |
| Vigência | 10/10/2026 — decisão do diretor |

### RN-SANGRIA-004 — Sangria alterada após o lançamento
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Caixa |
| Padrão | Sangria alterada depois de lançada = laranja (agrupada por caixa/dia) |
| Exceção | — |
| Gatilho | Flag de alteração na sangria |
| Ação no sistema | Alerta `SANGRIA_ALTERADA` |
| Implementação | `rules/fechamento.py` |
| Status | vigente |
| Vigência | 06/10/2026 |

### RN-SANGRIA-005 — Matriz de destino por unidade (referência)
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Caixa |
| Padrão | Doze: sangria 24h → BB; espécie do fechamento D+1 → BB. VIP pista: sangria 24h → Bradesco; espécie D+1 → Itaú. Conveniência VIP: semanal → Itaú. Casa Caiada: espécie D+1 → BB. Conv. 24h: semanal na conta BB do Casa Caiada |
| Exceção | Conta BB do Casa Caiada é compartilhada (Casa Caiada + Conv. 24h); depósitos no terminal "POSTO BR SHOPPING ATMR" são do Casa Caiada |
| Gatilho | — |
| Ação no sistema | Só referência (RN-REDE-004) |
| Implementação | `units.json` (`destinos`, `contas_compartilhadas`) |
| Status | vigente |
| Vigência | 06/10/2026 — informado pelo diretor |

---

## 7. Cartões, PIX e adquirentes (RN-CARTAO)

### RN-CARTAO-001 — Adquirentes por unidade
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | TEF/Cartões |
| Padrão | Doze e Casa Caiada: PagBank (cartões e PIX, EDI ativo) + Premmia. VIP: Rede (pista), Cielo (loja), Mais Pagamentos (PIX; no webPosto "Transferência Bancária"), Premmia. Conv. 24h: Cielo (cartões), PagBank (PIX — credencial inválida) |
| Exceção | VIP não usa PagBank |
| Gatilho | — |
| Ação no sistema | Adquirente sem integração = "pendente"; credencial inválida = aviso |
| Implementação | `units.json` (`adquirentes`) |
| Status | vigente |
| Vigência | 07/10/2026 |

### RN-CARTAO-002 — Casamento adquirente × webPosto
| Campo | Valor |
|---|---|
| Unidades | Unidades com adquirente ativo |
| Módulo | TEF/Cartões |
| Padrão | Chave exata NSU (ou NSU TEF) ou autorização. Cupom: NSU ERP termina em `-<código portal>`, sem diferenciar maiúsculas, mesmo valor e dia; chave `cupom`. POS PREMMIA ou Pix do portal × PREMMIA PIX: mesmo valor/dia e até 10 min, candidato único nos dois lados; chave `valor_hora`. Ambiguidade fica provável, nunca conferida automaticamente. Outros PIX sem NSU mantêm regra existente |
| Exceção | — |
| Gatilho | Robô noturno |
| Ação no sistema | Casado / a maior (na adquirente, não no ERP) / a menor (no ERP, não na adquirente). Código repetido no portal (NSU exato ou cupom): casar código + valor + dia, horário ERP mais próximo, um para um sem reutilizar |
| Implementação | `rules/cartoes.py` · CARTOES_V3_3 |
| Status | vigente |
| Vigência | 11/10/2026 |

### RN-CARTAO-003 — Lançado e não recebido
| Campo | Valor |
|---|---|
| Unidades | Unidades com adquirente ativo |
| Módulo | TEF/Cartões |
| Padrão | Cartão no webPosto sem transação na adquirente = **vermelho, prioridade máxima** (não será pago); se houver cancelamento na adquirente, mostra o motivo |
| Exceção | — |
| Gatilho | Sobra "a menor" |
| Ação no sistema | Pendência vermelha individual |
| Implementação | CARTOES_V3_1 |
| Status | vigente |
| Vigência | 08/10/2026 |

### RN-CARTAO-004 — Recebido e não lançado: atribuição ao frentista
| Campo | Valor |
|---|---|
| Unidades | Unidades com adquirente ativo |
| Módulo | TEF/Cartões |
| Padrão | Transação na adquirente sem lançamento no webPosto → procura o abastecimento: valor igual 35 + abastecimento 0–15 min antes até 30 + venda lançada como dinheiro 20 + valor não redondo 15. ≥ 80 e candidato único = atribui; 50–79 ou empate = sugestão |
| Exceção | — |
| Gatilho | Sobra "a maior" |
| Ação no sistema | Alerta laranja com frentista atribuído/sugerido |
| Implementação | CARTOES_V3_1 |
| Status | vigente |
| Vigência | 08/10/2026 |

### RN-CARTAO-005 — Par provável e grupo provável
| Campo | Valor |
|---|---|
| Unidades | Unidades com adquirente ativo |
| Módulo | TEF/Cartões |
| Padrão | Mesmo valor a maior e a menor no mesmo dia = par provável (lançamento com hora/NSU divergente). Até 4 transações a maior que somam um lançamento a menor, combinação única = grupo provável |
| Exceção | — |
| Gatilho | Sobras no mesmo dia |
| Ação no sistema | Sai dos alarmes e vai para conferência |
| Implementação | CARTOES_V2+ |
| Status | vigente |
| Vigência | 09/10/2026 — caso real Casa Caiada 07/10 (4 cartões = R$ 179,45) |

### RN-CARTAO-006 — Valor divergente com o mesmo NSU
| Campo | Valor |
|---|---|
| Unidades | Unidades com adquirente ativo |
| Módulo | TEF/Cartões |
| Padrão | Mesmo NSU, webPosto maior que a adquirente = vermelho (falta receber a diferença); adquirente maior = laranja |
| Exceção | — |
| Gatilho | Casamento com diferença ≥ R$ 0,01 |
| Ação no sistema | `CARTAO_VALOR_A_MENOR` / `CARTAO_VALOR_A_MAIOR` |
| Implementação | CARTOES_V3 |
| Status | vigente |
| Vigência | 10/10/2026 |

### RN-CARTAO-007 — NSU repetido no webPosto
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | TEF/Cartões |
| Padrão | Vermelho só com mesmo NSU, ou mesma autorização + mesmo valor + mesmo dia. Autorização repetida com valor ou dia diferente não é alerta |
| Exceção | — |
| Gatilho | 2+ lançamentos com a mesma chave |
| Ação no sistema | `CARTAO_NSU_REPETIDO`, com vendas, horários, valores e frentista |
| Implementação | CARTOES_V3_1 |
| Status | vigente |
| Vigência | 10/10/2026 — caso real VIP 05/10 (PIX Premmia R$ 30 em duas vendas) |

### RN-CARTAO-008 — Cartão lançado manualmente sem venda
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | TEF/Cartões |
| Padrão | `tipoInclusao = Manualmente` e sem venda = laranja (agrupado por caixa/dia) |
| Exceção | Prática atual tolerada: cliente a prazo quitando a fatura com cartão/PIX lançado à mão. Continua sinalizado até o Logos lançar corretamente (RN-ERP-001) |
| Gatilho | Cartão manual sem `vendaCodigo` |
| Ação no sistema | `CARTAO_MANUAL_SEM_VENDA`; mostra se há transação correspondente na adquirente |
| Implementação | CARTOES_V3_1 |
| Status | vigente |
| Vigência | 10/10/2026 — decisão do diretor |

### RN-CARTAO-009 — PIX CNPJ (chave do posto, fora da maquininha)
| Campo | Valor |
|---|---|
| Unidades | Doze 74014 |
| Módulo | TEF/Cartões |
| Padrão | — |
| Exceção | "PIX CNPJ" no webPosto = PIX feito pela **chave PIX do posto**, direto na conta PagBank do Doze, **sem maquininha**; por isso não aparece no EDI transacional do PagBank e é lançado à mão |
| Gatilho | Lançamento com administradora "PIX CNPJ" |
| Ação no sistema | Conferir à mão (grupo 4, RN-CARTAO-010); nunca presumir ausência no EDI. Conferido/Não encontrado com observação e histórico local; Não encontrado encaminha para apuração. Futuro: extrato recebido por e-mail (EXTRATOS_01) |
| Implementação | Sprint 14; EXTRATOS_01 ainda pendente |
| Status | vigente |
| Vigência | 11/10/2026 — informado pelo diretor (Doze 01–09/10: 7 lançamentos · R$ 2.480,41) |

### RN-CARTAO-010 — Classificação acionável dos recebimentos
| Campo | Valor |
|---|---|
| Unidades | Todas com recebimentos |
| Módulo | Conferência de recebimentos |
| Padrão | 1 LANÇAR: recebido sem lançamento/venda candidata; 2 ALTERAR: dinheiro recebido com forma/adquirente/hora/vínculo errado, par ou grupo provável; 3 APURAR: suspeita de lançamento sem lastro após busca cruzada; 4 CONFERIR À MÃO: fonte ausente ou evidência ambígua/incompleta |
| Exceção | Totais legados sem comprovantes individuais não permitem afirmar forma/hora nem concluir busca cruzada: sinalizar lacuna e conferir à mão. Nunca inventar valores de adquirente pendente |
| Gatilho | Resultados já calculados e gravados por unidade/dia; nenhuma consulta externa no endpoint de conferência |
| Ação no sistema | Busca cruzada por valor/dia até 30 min, única nos dois lados, sem reutilização. Combinação única de até 4 itens usa motor existente. Diferença positiva e negativa sem correspondência identificável: compensação a apurar. Três trocas de forma/apurações por frentista no mês: REINCIDENTE, com quantidade e valor |
| Pendências | Grupo 3 vermelho individual; grupos 1/2 laranja agrupados por caixa/dia (RN-PEND-001), sem somar alertas duplicados. Histórico append-only; justificadas/recusadas preservadas |
| Conferência manual | Diretor/gerente da unidade registra Conferido/Não encontrado e observação no SQLite; Não encontrado cria grupo 3. Conferido não modifica o ERP |
| Propostas | Grupo 2 gera proposta local com De → Para, lançamento/venda/caixa, evidências mascaradas e nota de certeza. Status proposta, executada pelo gerente ou descartada, com usuário/data/histórico. ADR-003 Fase 0: nenhum lançamento automático |
| Nota de certeza | Escore de evidência, não probabilidade: troca em dinheiro reaproveita pontos do motor; chave exata 100, valor/hora com unicidade 80, busca cruzada 70, combinação cruzada 60 e par/grupo provável 50. Medir decisões humanas no histórico antes de qualquer automação |
| Implementação | Sprint 14 · `application/classificar_recebimentos.py`, contratos Pydantic e motor CARTOES_V3_3 |
| Status | vigente |
| Vigência | 11/10/2026 |

---

## 8. Premmia (RN-PREMMIA)

### RN-PREMMIA-001 — Formas Premmia e desconto recebível
| Campo | Valor |
|---|---|
| Unidades | Todas com Premmia |
| Módulo | Premmia |
| Padrão | Formas no portal: Cartão APP, Pix, Desconto, Vale-Premmia. **"Desconto" é pago pela Vibra ao posto (recebível)** e é conciliado como as demais |
| Exceção | Lançamentos até 09/10/2026 podem estar em forma "não identificada"; forma própria `PREMMIA DESCONTO CUPOM` cadastrada no webPosto em 10/10/2026 |
| Gatilho | Conciliação Premmia |
| Ação no sistema | Casamento por NSU exato ou sufixo de cupom, mesmo valor/dia; POS PREMMIA por valor/hora com unicidade. Quantidades sempre acompanhadas de R$; por forma, portal × webPosto e diferença |
| Implementação | Sprint 13.1 · CARTOES_V3_2 |
| Status | vigente |
| Vigência | 10/10/2026 — decisão do diretor |

### RN-PREMMIA-002 — Coleta e armazenamento
| Campo | Valor |
|---|---|
| Unidades | Casa Caiada e Doze (VIP desligado até ter os demais EDIs) |
| Módulo | Premmia |
| Padrão | Coleta do dia 01 do mês até ontem, só dias faltantes; uma planilha por posto e mês (`data/premmia/posto<apelido>_<MM>_<AAAA>.xlsx`), acrescentando os dias |
| Exceção | CAPTCHA/2FA/termos/senha recusada → para e avisa; não tenta de novo na noite |
| Gatilho | Robô noturno |
| Ação no sistema | Planilha mensal; originais em `data/premmia/originais/`. Deduplicar somente código + data/hora + valor + forma; mesmo código em horários distintos permanece. A cada coleta, conferir as linhas por dia original × mensal; ausência gera aviso na unidade/Telegram e log, sem falha do robô |
| Implementação | Sprint 13 (PREMMIA_01) |
| Status | vigente |
| Vigência | 10/10/2026 — decisão do diretor |

---

## 9. Pendências e cobrança (RN-PEND)

### RN-PEND-001 — Vermelho individual, laranja agrupado
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Pendências |
| Padrão | Cada alerta vermelho = uma pendência; alertas laranja do mesmo caixa e dia = uma pendência agrupada |
| Exceção | — |
| Gatilho | Robô noturno |
| Ação no sistema | Idempotente; inclui recebimentos a maior de PagBank e Premmia, mantendo valor, hora, forma, NSU e frentista atribuído/sugerido em cada item (NSU só com os 4 últimos dígitos no chat). Caixa único no horário do recebimento; sem vínculo inequívoco, grupo por unidade/dia "sem caixa". Individuais `recebimento_a_maior` abertas ficam no histórico como `substituida`, apontando para o grupo; justificadas/recusadas são preservadas |
| Implementação | `application/gerar_pendencias.py`; individuais antigas agora prováveis são itens históricos do grupo, fora do valor ativo. Legada ausente do resultado atual fica histórica "sem caixa", com dados originais e lacunas explícitas, sem inferir hora/forma/NSU. Grupo só histórico nasce aprovado, sem novo alerta laranja |
| Status | vigente |
| Vigência | 10/10/2026 — decisão do diretor |

### RN-PEND-002 — Prazo e vencimento
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | Pendências |
| Padrão | Prazo a partir da criação: vermelho 2 dias, laranja 5 dias; passou = VENCIDA |
| Exceção | Pendência justificada nunca vence |
| Gatilho | Idade da pendência aberta (fuso Recife) |
| Ação no sistema | Selo VENCIDA, ordenação e contagem no Painel |
| Implementação | `units.json` (`prazo_pendencia_dias`) |
| Status | vigente (valores iniciais, ajustáveis pelo diretor) |
| Vigência | 10/10/2026 |

---

## 10. Metas comerciais (RN-META)

### RN-META-001 — Placar de litros
| Campo | Valor |
|---|---|
| Unidades | Postos (VIP, Doze, Casa Caiada); conveniências não entram |
| Módulo | Metas |
| Padrão | Todos os combustíveis somam na meta; faixas Bronze/Prata/Ouro definidas pelo diretor por posto e mês |
| Exceção | Out/2026: só VIP com metas; Doze e Casa Caiada adiados (METAS_02) |
| Gatilho | Robô noturno |
| Ação no sistema | Placar e projeção no Painel |
| Implementação | `commercial_performance` · PLACAR_V1 |
| Status | vigente |
| Vigência | 07/10/2026 — decisão do diretor |

---

## 11. Escrita no ERP (RN-ERP)

### RN-ERP-001 — Autonomia gradual de lançamento
| Campo | Valor |
|---|---|
| Unidades | Todas |
| Módulo | ERP |
| Padrão | Fases por tipo de lançamento: 0 Sombra → 1 Um toque → 2 Automático com limite → 3 Ampliação; interruptor `LOGOS_ERP_ESCRITA`; nunca alterar caixa consolidado |
| Exceção | — |
| Gatilho | Proposta de lançamento com nota de certeza calibrada |
| Ação no sistema | Ver ADR-003 |
| Implementação | `docs/architecture/adr/ADR-003-autonomia-gradual-de-escrita-no-erp.md` |
| Status | proposta (Fase 0 a implementar) |
| Vigência | 10/10/2026 — decisão do diretor |

---

## 12. A definir

Temas comuns em postos que **ainda não têm regra decidida** — não implementar sem decisão do diretor:

| Tema | Pergunta em aberto |
|---|---|
| LMC / perdas e sobras de combustível | Tolerância aceitável por produto e por tanque? |
| Clientes faturados (a prazo) | Como conferir o recebimento da fatura no caixa (título × cartão/PIX)? |
| Taxas de cartão | Taxa contratada por adquirente/bandeira para conferir a taxa cobrada (quando houver remessas EDI)? |
| Despesas do caixa | Valor máximo por despesa paga pelo caixa; planos de contas permitidos por tipo de despesa? |
| Vales de funcionários | Limite por funcionário/mês? |
| Conveniência (cigarro, padaria, combos) | Há exceções fiscais ou de preço a conferir? |
| Desconto não autorizado na bomba | `V1/ABASTECIMENTOS`: preço praticado (`valorUnitario`) abaixo do `precoCadastro` sem tabela A/B/C que justifique — qual tolerância e quem pode autorizar? |
| Sequência de encerrantes | `V1/ABASTECIMENTOS.encerrante`: buraco na sequência por bico indica abastecimento não registrado — tolerância? Usar também no LMC? |
| Placa | `V1/ABASTECIMENTOS.placa`: localizar abastecimentos de clientes empresa e repetição da mesma placa no dia — limites? |
| Rede / Cielo / Mais Pagamentos | Fonte dos dados: EDI via webPosto ou acesso direto? (aguarda Quality e TIVIT) |

## 13. Histórico

| Data | Mudança |
|---|---|
| 10/10/2026 | Criação do documento com as regras vigentes do projeto (Sprints 01 a 13) e ADR-003 |
| 11/10/2026 | CARTOES_V3_2: cupom no sufixo do NSU, POS PREMMIA com unicidade, forma PREMMIA DESCONTO CUPOM e valores junto às quantidades |
| 11/10/2026 | CARTOES_V3_3: preservar usos distintos de cupom repetido, casar por código/valor/dia e horário mais próximo; integridade original × mensal e encerramento de falsas pendências com histórico |
| 11/10/2026 | Ajuste autorizado: Pix do portal × PREMMIA PIX usa valor exato, mesmo dia, até 10 minutos e unicidade nos dois lados, como POS PREMMIA; ambiguidade permanece para conferência |
| 11/10/2026 | RN-CARTAO-009 (PIX CNPJ do Doze, pela chave do posto) — proposta, depende de EXTRATOS_01 |
| 11/10/2026 | Sprint 14: RN-CARTAO-010, quatro grupos acionáveis, conferência manual auditada, compensação diária e propostas locais; RN-CARTAO-009 conferência manual até integrar extrato |
| 11/10/2026 | Sprint 14: RN-REDE-002 com sugestão, empate e responsável do caixa; detalhes individuais dos pagamentos, RN-REDE-006 (D−2, 7 dias) e campo brasileiro compartilhado na conferência |
| 11/10/2026 | Sprint 14 B4: filtros gerais, fechamento, painéis, contas, vendas, despesas, estoque, exportações e snapshots usam o mesmo helper brasileiro, preservando ISO apenas no transporte técnico |
