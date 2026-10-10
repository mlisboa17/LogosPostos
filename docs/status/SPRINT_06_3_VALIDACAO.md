# Sprint 6.3 — validação do Painel do Diretor

## Entrega

- Painel escuro, primeira opção para diretor e gerente; o gerente recebe apenas a própria unidade.
- APIs do painel leem snapshots locais, estado do robô, fila SQLite em modo somente leitura e placares persistidos. Não recorrem ao ERP quando faltam dados.
- Métricas ausentes são apresentadas como indisponíveis, sem convertê-las em zero.
- Alertas da saúde cobrem ausência/atraso acima de 26 horas, falhas registradas e execução sem unidades processadas.
- Idade de caixas não consolidados é recalculada na data local de Recife; datas da tela seguem `dd/mm/aaaa`.
- O robô grava estado de execução e resumo Markdown agregado em `data/resumos/`, diretório ignorado pelo Git; o resumo não inclui nomes de funcionários ou credenciais.
- O link de pendências mantém a unidade selecionada e a rota continua aplicando a autorização no servidor.

## Verificação

- Backend: `python -m pytest tests/unit -q --no-cov` — **412 aprovados**.
- Frontend: `node --test tests/frontend/*.test.mjs` — **29 aprovados**.
- `git diff --check` sem erros.
- Painel aberto no navegador local com sessão de visualização isolada; cards, alerta, estilos, datas e navegação para pendências conferidos usando snapshots já gravados. Nenhum job foi executado para a conferência e nenhuma escrita foi feita no ERP.

## Números reais observados

Dados persistidos consultados em 10/10/2026:

- Quatro unidades com snapshot de fechamento; o último dia fechado disponível para todas foi 08/10/2026.
- Pendências abertas: unidade 74014 = 24; 11495 = 48; 5555 = 45; 118508 = 38; total = **155**.
- Quebra agregada no último fechamento por unidade: 74014 = -R$ 650,20; 11495 = -R$ 266,68; 5555 = -R$ 2,44; 118508 = R$ 9,15.
- Faltas sem desconto: 1 em 74014 (R$ 650,20), 1 em 11495 (R$ 270,93), nenhuma em 5555 ou 118508.
- Adquirentes: PagBank ativo em 74014 e 5555; PagBank com credencial inválida em 118508; demais configurações exibidas como pendentes. Nenhum adquirente pendente foi consultado.
- Placar do mês: três projeções persistidas; o posto 11495 projeta faixa Ouro. Os outros dois snapshots não têm faixa projetada.

O estado persistido do robô observado durante a validação registra uma execução em 10/10/2026 para o dia processado 02/10/2026, com **zero unidades processadas**, zero falhas listadas e resumo gerado. O painel sinaliza essa execução sem unidades como alerta operacional, em vez de exibir saúde verde. Esse registro foi lido, não corrigido nem reprocessado nesta sprint.
