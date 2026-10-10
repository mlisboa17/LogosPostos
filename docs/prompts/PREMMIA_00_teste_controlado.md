# Prompt — PREMMIA-00: teste único e controlado do robô do portal Premmia (Vibra)

> Workspace: `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Sem push, merge ou troca de branch.
> Objetivo: descobrir **se** o robô consegue entrar no portal e exportar o relatório de **1 posto, 1 dia**, antes de qualquer porte para o sistema.

## Escopo fixo

- Posto: **VIP (11495)** · Dia: **07/10/2026** · Navegador **visível** (o sócio-diretor vai acompanhar).
- Portal: `https://cn.vibraenergia.com.br/premmia/revendedor/login` → **Conferência → Pagamentos**.
- Credenciais: variáveis `PREMMIA_usuario_POSTO_VIP` e `PREMMIA_SENHA_POSTO_VIP` em `WebPosto_API/.env`, carregadas com `load_dotenv`. **Nunca** imprimir, logar, salvar em arquivo ou colar no chat; o script só preenche os campos de login.

## Referência (não portar ainda)

Leia com `git show resgate/conciliacao-4-vias:<caminho>` — sem checkout:
- `WebPosto_API/src/services/integrations/premmia_rpa.py` (fluxo de login, filtro de data, exportação, seletores)
- `WebPosto_API/src/services/financial/premmia_report_parser.py` e `premmia_parsing.py` (formato do relatório)
- testes `tests/unit/test_premmia_rpa_playwright.py`

Lembrete: o código resgatado tem bugs silenciosos em outras integrações; trate seletores e formato como **hipótese** a confirmar no portal real.

## Tarefa

1. Crie `WebPosto_API/scripts/probe_premmia_portal.py` (script de sondagem, autocontido, Playwright **síncrono**, `headless=False`, `slow_mo` ~300 ms, timeout 60 s por etapa). Parâmetros: `--posto 11495 --dia 07/10/2026`.
2. Fluxo, com **parada imediata** em qualquer ponto não previsto:
   1. Abrir a página de login e preencher usuário/senha.
   2. **Se aparecer CAPTCHA, reCAPTCHA, "não sou um robô", código por SMS/e-mail, 2FA ou qualquer verificação humana: PARE.** Não tente resolver, contornar, esperar o usuário resolver por você, nem usar serviço de terceiros. Tire 1 captura da tela (sem dados pessoais visíveis, se possível), feche o navegador e reporte.
   3. Se aparecer aviso de **aceite de termos, troca de senha, alteração de cadastro ou qualquer confirmação que mude a conta: PARE** e reporte (não clique).
   4. Login ok → ir a Conferência → Pagamentos, filtrar **07/10/2026**, exportar o relatório.
   5. Só **navegar, filtrar e exportar**. Não clicar em nada que grave, envie, cancele ou altere.
3. Salve o arquivo exportado em `WebPosto_API/data/premmia/2026-10-07/11495/` (pasta fora do Git). Capturas de tela, se houver, na mesma pasta.
4. Leia o arquivo e reporte **somente estrutura e agregados**: nome/tipo do arquivo, colunas, quantidade de linhas, formas de pagamento distintas (crédito/PIX/vale/desconto…), status distintos, faixa de horários, total de valores por forma. **Não** mostre CPF, nomes de clientes nem linhas individuais.
5. Comparação rápida com o webPosto (somente leitura): no mesmo dia e posto, conte e some os recebimentos Premmia do ERP (`V1/CARTOES` com administradora contendo "PREMMIA", e formas de pagamento Premmia em `V1/VENDAS_FORMA_PAGAMENTO`). Mostre lado a lado: quantidade e total do portal × do webPosto, por forma de pagamento.

## Restrições

- Rode **uma vez** (no máximo uma nova tentativa se falhar por tempo de carregamento — nunca por senha errada: senha recusada → pare e reporte, para não bloquear a conta).
- Somente leitura no portal e no ERP. Sem dados fictícios.
- Não commite o script ainda; não altere o módulo `cash_reconciliation` nem o robô noturno.

## Entrega (no chat)

1. **Resultado do login:** passou / bloqueado por CAPTCHA ou 2FA / senha recusada / outro (descreva o que apareceu).
2. Se passou: estrutura do relatório e a comparação portal × webPosto.
3. Recomendação objetiva: **portar** (e o que muda em relação ao código resgatado) ou **parar** (e alternativa: pedir à Vibra acesso por API/EDI ou exportação manual).
