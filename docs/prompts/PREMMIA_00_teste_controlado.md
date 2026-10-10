# Prompt — PREMMIA-00: teste único e controlado do robô do portal Premmia (Vibra)

> Workspace: `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem push, merge ou troca de branch.
> Objetivo: descobrir **se** o robô consegue entrar no portal e exportar o relatório de **1 posto**, do **início do mês até ontem**, antes de qualquer porte para o sistema.

## Escopo fixo

- Posto: **VIP (11495)** — uma única empresa · Navegador **visível** (o sócio-diretor vai acompanhar).
- Período (decisão do diretor em 10/10/2026): **do dia 01 do mês corrente até ontem**, buscando **só os dias que ainda não têm dados salvos** em `WebPosto_API/data/premmia/<aaaa-mm-dd>/11495/`. Nada salvo (primeira vez) → 01/10/2026 até ontem. Se o filtro do portal aceitar intervalo, exporte o intervalo **uma vez** e separe por dia ao salvar; se só aceitar um dia, repita o filtro dia a dia **na mesma sessão** (um único login), no máximo 31 dias.
- Portal: `https://cn.vibraenergia.com.br/premmia/revendedor/login` → **Conferência → Pagamentos**.
- Credenciais: variáveis `PREMMIA_usuario_POSTO_VIP` e `PREMMIA_SENHA_POSTO_VIP` em `WebPosto_API/.env`, carregadas com `load_dotenv`. **Nunca** imprimir, logar, salvar em arquivo ou colar no chat; o script só preenche os campos de login.

## Filtro de datas pela URL (descoberto no teste de 10/10/2026)

O login passou sem CAPTCHA. Os campos de data do portal são lentos e o robô não conseguiu alterá-los. **Não use os seletores de data.** O portal aceita o filtro direto no endereço:
`/premmia/revendedor/conferencia/pagamentos?page=1&start=AAAA-MM-DD+00%3A00&end=AAAA-MM-DD+23%3A59&products=...`
1. Depois do login, abra Conferência → Pagamentos uma vez, leia `page.url` e guarde o valor de `products` **como veio** (não invente).
2. Para cada período, navegue direto para a URL trocando só `start`, `end` e `page`. Espere a tabela (linhas ou mensagem de vazio) com `wait_for_selector`, timeout 90 s; não use espera fixa.
3. Paginação: incremente `page` até não haver linhas novas; ou use **Exportar** se ele exportar o período inteiro.
4. A tela mostra CPF parcial e nome do cliente: **não** registrar no log nem no chat; no `.json` normalizado guarde só data/hora, valor, código, serviço e meio de pagamento.

## Referência (não portar ainda)

Leia com `git show resgate/conciliacao-4-vias:<caminho>` — sem checkout:
- `WebPosto_API/src/services/integrations/premmia_rpa.py` (fluxo de login, filtro de data, exportação, seletores)
- `WebPosto_API/src/services/financial/premmia_report_parser.py` e `premmia_parsing.py` (formato do relatório)
- testes `tests/unit/test_premmia_rpa_playwright.py`

Lembrete: o código resgatado tem bugs silenciosos em outras integrações; trate seletores e formato como **hipótese** a confirmar no portal real.

## Tarefa

1. Crie `WebPosto_API/scripts/probe_premmia_portal.py` (script de sondagem, autocontido, Playwright **síncrono**, `headless=False`, `slow_mo` ~300 ms, timeout 60 s por etapa). Parâmetros: `--posto 11495` (período automático: dias faltantes de 01 do mês até ontem) e opcional `--inicio dd/mm/aaaa --fim dd/mm/aaaa`.
2. Fluxo, com **parada imediata** em qualquer ponto não previsto:
   1. Abrir a página de login e preencher usuário/senha.
   2. **Se aparecer CAPTCHA, reCAPTCHA, "não sou um robô", código por SMS/e-mail, 2FA ou qualquer verificação humana: PARE.** Não tente resolver, contornar, esperar o usuário resolver por você, nem usar serviço de terceiros. Tire 1 captura da tela (sem dados pessoais visíveis, se possível), feche o navegador e reporte.
   3. Se aparecer aviso de **aceite de termos, troca de senha, alteração de cadastro ou qualquer confirmação que mude a conta: PARE** e reporte (não clique).
   4. Login ok → ir a Conferência → Pagamentos, filtrar o período (dias faltantes), exportar o relatório.
   5. Só **navegar, filtrar e exportar**. Não clicar em nada que grave, envie, cancele ou altere.
3. Salve os dados de cada dia em `WebPosto_API/data/premmia/<aaaa-mm-dd>/11495/` (arquivo original exportado + um `.json` normalizado por dia) (pasta fora do Git). Capturas de tela, se houver, na mesma pasta.
4. Leia o arquivo e reporte **somente estrutura e agregados**: nome/tipo do arquivo, colunas, quantidade de linhas, formas de pagamento distintas (crédito/PIX/vale/desconto…), status distintos, faixa de horários, total de valores por forma. **Não** mostre CPF, nomes de clientes nem linhas individuais.
5. Comparação com o webPosto (somente leitura): para cada dia do período, no mesmo posto, conte e some os recebimentos Premmia do ERP (`V1/CARTOES` com administradora contendo "PREMMIA", e formas de pagamento Premmia em `V1/VENDAS_FORMA_PAGAMENTO`). Mostre uma tabela por dia: quantidade e total do portal × do webPosto, por forma de pagamento, e a diferença.

## Restrições

- Rode **uma vez** (no máximo uma nova tentativa se falhar por tempo de carregamento — nunca por senha errada: senha recusada → pare e reporte, para não bloquear a conta).
- Somente leitura no portal e no ERP. Sem dados fictícios.
- Não commite o script ainda; não altere o módulo `cash_reconciliation` nem o robô noturno.

## Entrega (no chat)

1. **Resultado do login:** passou / bloqueado por CAPTCHA ou 2FA / senha recusada / outro (descreva o que apareceu).
2. Se passou: estrutura do relatório e a comparação portal × webPosto.
3. Recomendação objetiva: **portar** (e o que muda em relação ao código resgatado) ou **parar** (e alternativa: pedir à Vibra acesso por API/EDI ou exportação manual).
