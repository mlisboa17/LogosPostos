# Prompt — SPRINT 14.1: correções da primeira madrugada com Premmia e Sprint 14 (VS Code / Cursor)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento`. Somente leitura no ERP e nos portais; `.env` só via `load_dotenv`; sem reescrever arquivos; testes sintéticos sem navegador/portal; nada pelo Telegram (o diretor reenvia depois).

## O que aconteceu em 11/10/2026 às 03:00 (log `data/cash_audit/noturno.log`)

```
03:02 ERROR Premmia unidade=74014 falha etapa=abrir login
03:08 ERROR Premmia unidade=5555  falha etapa=abrir login
03:11 INFO  Execucao terminada dia=10/10/2026 unidades_com_falha=2 unidades_com_aviso=1
03:11 WARNING Telegram envio=falhou motivo=KeyError
```

1. **Telegram — JÁ CORRIGIDO pelo arquiteto** (`src/jobs/noturno.py`, `_criar_planilha_telegram`: `formatos_monetarios[planilha.title]` dava `KeyError` com a aba nova "Ações de recebimento"; trocado por `.get(..., ())`). Falta: **teste de regressão** que gere a planilha com todas as abas atuais (inclusive "Ações de recebimento") e formate os valores em R$ também nessa aba.
2. **Premmia no modo invisível (headless) não abre o login.** Coleta visível funcionou (Sprint 13); o teste legado da Sprint 13 já tinha falhado em "abrir login" no modo headless. Hipóteses a verificar **sem novo login real**: o portal bloqueia/atrasa navegador headless (user agent "HeadlessChrome"), ou o tempo de carregamento é maior.
3. **Falha do Premmia contou como falha da unidade** (`unidades_com_falha=2`, código de saída 1). Pela RN-PREMMIA-002, problema no portal é **aviso**, não falha do robô.

@WebPosto_API/src/modules/cash_reconciliation/adapters/premmia_portal.py
@WebPosto_API/src/modules/cash_reconciliation/jobs/noturno.py
@WebPosto_API/src/jobs/noturno.py
@WebPosto_API/tests/unit/cash_reconciliation/test_noturno.py

## Correções

1. Premmia no robô: usar Chromium com o **novo modo headless** (`args=["--headless=new"]` com `headless=False` no launch, ou o canal equivalente da versão instalada), **user agent de navegador comum** (sem "Headless"), `locale pt-BR`, `timezone America/Recife`, viewport 1366×768 e timeout de 90 s para abrir o login. Se ainda assim falhar em "abrir login", **tentar uma vez com a janela visível** (a sessão do Windows está aberta, tarefa em modo Interactive) e registrar no log qual modo funcionou. Nunca mais de 1 login por unidade por noite.
2. Qualquer erro do Premmia (abrir login, CAPTCHA, tempo, exportação) → **aviso** na unidade ("Premmia: coleta não realizada — <etapa>"), não falha; código de saída só muda por falha real do fechamento/PagBank.
3. Mensagem do Telegram: linha "Premmia: coleta não realizada hoje (<etapa>) — dados até dd/mm" quando houver aviso.
4. Testes: aviso do Premmia não altera o código de saída; modo headless configurado com user agent sem "Headless"; fallback visível chamado só uma vez; planilha com todas as abas sem `KeyError`.

## Validação real (o diretor autoriza 1 execução por unidade, de dia, acompanhando)

Rodar `python -m src.modules.cash_reconciliation.jobs.noturno --dia 10/10/2026` **com o modo do robô (headless)** para Casa Caiada e Doze e informar se o login abriu no modo invisível. Não enviar Telegram.

Commit: `fix(premmia): coleta noturna em modo invisível e falha do portal como aviso`. Depois `git push`.
