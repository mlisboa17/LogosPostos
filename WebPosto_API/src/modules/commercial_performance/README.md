# Placar comercial

Commercial Intelligence, regra `PLACAR_V1`; somente VIP (11495), Doze (74014)
e Casa Caiada (5555). Nenhuma importacao de Cash & Reconciliation. HTTP e tempo
sao contratos compartilhados em `webposto_integration`; o cash preserva reexports.

Fontes V1 sondadas em leitura: ABASTECIMENTOS, FUNCIONARIOS, PRODUTOS e
VENDAS/ITENS. Afericao e excluida. Volume inclui todos os produtos abastecidos.
Catalogo e funcionarios sao lidos com a chave do posto; funcionarios, itens e
abastecimentos tambem sao filtrados por empresa. Nomes ficam no resultado local;
CPF, email, telefone e outros dados pessoais nao sao mapeados.

Atendimento e venda distinta vinculada pelo vendaItemCodigo. Sem vinculo, conta
o abastecimento individual e informa a quantidade de fallbacks. Por frentista,
uma venda compartilhada conta uma vez para cada frentista envolvido; a soma pode
diferir do total do posto. Abastecimentos e atendimentos sao apresentados separados.
Fonte indisponivel nao vira volume zero; falhas sao explicitamente propagadas.

Hoje fica parcial ate meia-noite em Recife, conforme decisao do diretor.
Dias restantes sao calendario, incluindo hoje. Media realizada = acumulado / dia
do mes (inclui dia parcial); projecao segue a formula do prompt: acumulado +
media realizada x dias restantes. E uma estimativa, nao venda realizada.
Meta viva considera acumulado ate a vespera; fim de mes fechado tem meta viva
indisponivel, sem divisao por zero. Ativos = codigos com abastecimento nos 7 dias
inclusive D, mesmo atravessando a fronteira do mes.

Mix aditivado usa nome do catalogo contendo `ADITIV` (sem distinguir maiusculas).
Produto ausente aparece por codigo, sem nome inventado; percentual aditivado
fica indisponivel se a classificacao de qualquer produto estiver ausente.

Metas reais ficam apenas em `data/metas/AAAA-MM.json`, fora do Git. O diretor
preenche os tres niveis crescentes e os tickets por codigo. Nunca sao criadas
metas reais automaticamente. `config/metas_exemplo.json` e exclusivamente
sintetico e NAO e lido pela aplicacao. Arquivo ausente mostra so realizado;
arquivo invalido ou inacessivel gera erro explicito. Cadastro autenticado nao
faz parte desta entrega.
