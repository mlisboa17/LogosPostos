# Auditoria de caixa e recebimentos

As regras `FECHAMENTO_V3` e `CARTOES_V1` continuam no domínio do módulo.
O ERP é consultado somente por leitura; correções são humanas.

## FECHAMENTO_V3

- Falta em dinheiro acima de R$ 10 é comparada com vales `origem=D` do mesmo
  operador e caixa. Sem vale, o alerta é vermelho; valor divergente gera alerta
  laranja. O detalhe mostra o total descontado, sem persistir nomes de pessoas.
- Caixa fechado e não consolidado fica laranja até a tolerância e vermelho
  depois dela. O padrão é **2 dias corridos** (`CASH_AUDIT_DIAS_TOLERANCIA_CONSOLIDACAO`);
  esse padrão ainda aguarda confirmação do sócio-diretor.
- Despesas `tipo=D` de `MOVIMENTACOES_CAIXA` são exibidas no detalhe. Falta de
  plano de contas ou de descrição útil gera alerta laranja.
- `GET /api/v1/cash-audit/reincidencia?unidade=<empresaCodigo>&mes=AAAA-MM`
  agrega fechamentos e recebimentos PagBank dos snapshots noturnos existentes.
  A resposta explicita os dias cobertos e ausentes; nomes vêm de `FUNCIONARIOS`
  em tempo de consulta e não são persistidos.

## Pendências

- O robô noturno transforma alertas vermelhos/laranjas de fechamento e
  recebimentos em pendências; pares prováveis e adquirentes sem conciliação não
  geram pendência.
- `PENDENCIAS_V1` considera reincidência a partir de duas ocorrências no mesmo
  mês para quebras, sangrias alteradas e recebimentos a maior atribuídos. A
  pendência usa código do funcionário, sem persistir nome.
- O banco SQLite fica em `data/pendencias/pendencias.sqlite3` (fora do Git).
  Uma chave de identidade estável impede duplicação ao reexecutar o robô.
- A fila `GET /api/v1/cash-audit/pendencias` permite filtrar por unidade,
  status e tipo; `GET /api/v1/cash-audit/pendencias/contagem-abertas` alimenta
  o contador do menu. Gerentes veem e justificam somente a própria unidade;
  diretores aprovam ou recusam justificativas; auditores têm somente leitura.
- O histórico registra cada transição com usuário, data/hora local e
  justificativa/observação. Eventos são append-only; correções não sobrescrevem
  histórico nem alteram alertas na origem. O ERP continua somente leitura.
- Estados válidos: `aberta → justificada → aprovada | recusada`. A decisão do
  diretor só ocorre depois da justificativa do gerente.

## Recebimentos

- `GET /api/v1/cash-audit/recebimentos?unidade=<empresaCodigo>&dia=AAAA-MM-DD`
- Cada adquirente vem de `config/units.json`. Apenas o PagBank ativo é consultado.
- Casados expõem quantidade e total, não comprovantes individuais. Divergências
  incluem candidatos, motivos e proveniência.
- `pendente` e `credencial inválida` não significam zero transações: o resumo
  `casados` fica nulo. Falhas de uma adquirente não interrompem as demais.
- Mais Pagamentos está pausada até confirmação da documentação oficial.
  Rede, Cielo e Premmia permanecem pendentes; não há geradores fictícios.

Na aplicação, abra `/app/financial?view=cash-audit`, selecione unidade e período
(máximo de 31 dias inclusivos). A seção **Recebimentos eletrônicos** consulta os
dias do período com concorrência limitada. Dias indisponíveis são sinalizados;
totais e ranking são parciais nesses casos. Sugestões não confirmam autoria.
Cada recebimento conta uma vez por frentista candidato; pares prováveis entram
no ranking sem duplicar a mesma investigação.

O adaptador webPosto interpreta explicitamente o marcador de cancelamento
(`N`/`S`, booleano ou equivalente), preservando a hora das vendas PIX e
restringindo vendas, pagamentos e itens à unidade solicitada.

## Testes sintéticos

Execute a partir de `WebPosto_API`, sem carregar credenciais nos testes unitários:

```powershell
python -m pytest tests/unit/cash_reconciliation -q -o addopts=""
node --test tests/frontend/cashAudit.test.mjs
```

## Robô noturno

Execute a partir de `WebPosto_API`:

```powershell
python -B -m src.modules.cash_reconciliation.jobs.noturno
python -B -m src.modules.cash_reconciliation.jobs.noturno --dia 2026-10-06
```

Sem `--dia`, coleta ontem no fuso de Recife; também aceita `--dia 06/10/2026`.
O próprio processo carrega as variáveis locais com
`load_dotenv` e recusa executar se `WEBPOSTO_WRITES` não for `0`.
Fechamento e cada adquirente têm timeout de 180 segundos. Falhas são isoladas;
pendências e credenciais inválidas configuradas não geram consultas externas.
Código de saída `1` indica falha de coleta/processamento/persistência; estados
pendentes ou credenciais inválidas permanecem explícitos nos resultados.

Os arquivos ficam em `data/cash_audit/<dia>/<empresaCodigo>.json`, ignorados pelo
Git, com id de execução, versões das regras e fontes. Uma nova execução substitui
atomicamente o mesmo dia/unidade. O log resumido é `data/cash_audit/noturno.log`,
sem valores de cliente ou mensagens brutas dos fornecedores.

As rotas de recebimentos e fechamento usam o registro persistido quando existe.
Um arquivo corrompido retorna erro explícito, sem consulta ao vivo silenciosa.
Para períodos de fechamento parcialmente persistidos, apenas os dias ausentes
são consultados ao vivo; `execucoes` preserva a proveniência de cada dia.
Falhas persistidas continuam visíveis até uma nova execução substituir o registro.

### Agendador do Windows

O script não é executado automaticamente. Para registrar a tarefa às 03:00,
rode a partir da raiz do repositório, com um Python que contenha as dependências:

```powershell
.\scripts\registrar_robo_noturno.ps1 -PythonExe "C:\caminho\python.exe"
```

A tarefa usa a conta Windows atual com logon S4U, diretório de trabalho
`WebPosto_API`, impede instâncias sobrepostas e termina após no máximo 3 horas.
Não depende de compartilhamentos de rede nem de autenticação integrada Windows;
usa arquivos locais e HTTPS com credenciais do fornecedor. A conta precisa ter
permissão de execução, leitura da configuração local e escrita no diretório `data`.
O registro não sobrescreve tarefa existente: para substituí-la, remova a anterior
explicitamente no Agendador. Credenciais não são incluídas nos argumentos da tarefa.
O script avisa quando o fuso do Windows não é UTC−03:00 fixo.

## Datas e fuso

Na consulta de fechamento, a API limita o total das consultas ao ERP a 180 segundos
(inclusive em períodos com cache parcial). A tela aguarda até 200 segundos para
receber esse resultado; em caso de limite excedido, a API retorna HTTP 504 com
orientação para reduzir o período, sem apresentar resultados incompletos como sucesso.
Os recebimentos são consultados após o fechamento, um dia por vez, com botões
para os dias do período. Os KPIs e o ranking dessa seção são do dia selecionado,
não do período inteiro; isso evita iniciar várias conciliações pesadas simultâneas.

O fuso único do módulo é `America/Recife`, centralizado em `domain/tempo.py`.
Horários sem fuso (incluindo JSONs antigos) são interpretados como horário local;
horários UTC ou com outro offset são convertidos, nunca truncados. Campos
temporais dos modelos são normalizados na validação, evitando misturar datetimes
com e sem fuso. A dependência `tzdata` também é necessária no Windows.

A tela e os logs do robô exibem `dd/mm/aaaa` e `HH:mm`, sem depender do fuso da
máquina do usuário. Os campos nativos de data têm `lang="pt-BR"`; o período padrão
é calculado em Recife. JSON, parâmetros de API, pastas e consultas aos fornecedores
permanecem em ISO; timestamps serializados carregam `-03:00`.
A proveniência de conciliação de depósitos apenas passou a usar o relógio local;
suas regras e o fluxo de conciliação não foram alterados.
