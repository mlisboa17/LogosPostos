# Logos Match — design (18/10/2026)

Status: aprovado pelo diretor em 18/10/2026 (nome final: Logos Match, definido 18/10/2026). Nada implementado.

## 1. Intenção
Hoje a coleta Premmia e PagBank EDI e a comparação com os caixas do webPosto rodam no robô noturno do LOGOS, preso a este PC, ao repo e ao `.env`. O diretor quer o mesmo trabalho num **app instalável em outras máquinas**, onde ele mesmo cadastra postos e credenciais e recebe o resultado (planilha + alertas) por canais grátis. Uso inicial: as máquinas da própria rede, com novos postos. Tem potencial de virar produto para outros revendedores — o design não pode fechar essa porta.

Sucesso: numa máquina nova, instalar, cadastrar posto + credenciais pelo painel e, no dia seguinte, receber no Telegram/e-mail a conferência Premmia × PagBank × webPosto por caixa, sem tocar em código, `.env` ou repo.

## 2. Objetivos, não objetivos, anti-objetivos
**Objetivos v1**
- Instalador Windows, sem admin, sem Python/repo na máquina.
- Cadastro de postos (nome, apelido, CNPJ, empresaCodigo webPosto opcional).
- Credenciais por posto pelo painel: Premmia (usuário/senha), PagBank EDI (usuário/token, API v3.00), webPosto (chave, opcional).
- Coleta diária automática D-1 + "Coletar agora".
- Comparação com webPosto por caixa quando houver chave.
- Envio: Telegram e e-mail com planilha .xlsx; notificação local do Windows.
- Níveis de acesso no painel (seção 7A): Administrador, Gerente e Conferente, com escopo por posto.

**Não objetivos v1** (vários estão planejados para a v2, seção 10): escrita no webPosto; EDI de outras administradoras (Cielo, Rede, Mais Pagamentos); coleta de extratos bancários; conciliação de depósito × extrato; licença/cobrança; auto-update; sincronização com LOGOS central; arquivos EDI PagBank (a coleta é só via API — decisão do diretor).

**Anti-objetivos (falhou mesmo se "funcionar")**
- Segredo em texto puro em disco, log, planilha, export ou repo.
- Coleta que falha calada (ex.: Premmia pedindo verificação humana sem ninguém saber).
- Divergência mostrada sem explicação em português simples e sem nome + código do frentista.
- Fork do código de coleta/conciliação: o app usa o módulo `cash_reconciliation`, não uma cópia.
- Datas fora do padrão: fuso America/Recife, exibição dd/mm/aaaa HH:mm.

## 3. Restrições e fatos
- Máquina alvo fica ligada com usuário logado no Windows (confirmado).
- Código reaproveitado em `WebPosto_API/src/modules/cash_reconciliation/`: `adapters/premmia_portal.py`, `adapters/pagbank_edi.py`, `adapters/webposto_cartoes.py`, `adapters/webposto_caixas.py`, `application/conciliar_cartoes.py`, `rules/cartoes.py`, `domain/cartoes.py` (`TransacaoAdquirente`), `domain/models.py` (`Unidade`), `domain/tempo.py`, `config/units.json`.
- Hoje esses adapters leem credencial com `os.getenv(<nome vindo do units.json>)` e o Premmia grava em `DIRETORIO = parents[4]/data/premmia` (dentro do repo). Os dois pontos precisam virar parâmetros.
- Suíte atual (635 testes de reconciliação) e o robô noturno existente não podem quebrar.
- Premmia: às vezes cai para navegador visível e pode pedir verificação humana (`PremmiaVerificacaoHumana`).
- "Código Transação" do Premmia = `nsu` do V1/CARTOES; forma "Desconto" é recebível pago pela Vibra.
- Identificação do caixa: posto + setor/centro de custo (ou nome do caixa), não frentista; VIP tem 2 caixas/dia.

## 4. Decisões de arquitetura (minha recomendação; aprovar)
**Forma**: app de bandeja ("Logos Match"), iniciado no logon do Windows (Agendador de Tarefas, gatilho "ao fazer logon", usuário atual), com agendador interno e painel web local. Não é serviço Windows: serviço roda sem área de trabalho e não consegue a verificação humana do Premmia.

**Stack**: Python (mesma versão do `pyproject.toml` do WebPosto_API), FastAPI + Uvicorn (painel em `127.0.0.1`, porta livre escolhida no início), HTML server-side simples (Jinja2) sem build de front, APScheduler, pystray, keyring, openpyxl, httpx, Playwright.

**Local do código**: `WebPosto_API/apps/match/` no repo canônico, importando `src.modules.cash_reconciliation`.

```
apps/match/
  __main__.py      inicia bandeja + painel + agendador; trava de instância única
  bandeja.py       Abrir painel · Coletar agora · Coletar agora (visível) · Sair
  agendador.py     coleta D-1 às 06:00 e repescagem às 10:00 (configurável)
  painel/          rotas FastAPI + templates
  credenciais.py   CredentialStore (keyring)
  banco.py         SQLite + migrações simples (tabela schema_version)
  coletas.py       chama premmia_portal / pagbank_edi / webposto_* com credenciais injetadas
  comparar.py      chama conciliar_cartoes
  relatorio_xlsx.py
  canais/          telegram.py · email_smtp.py · toast.py
```

**Refatoração mínima no módulo existente**: introduzir em `cash_reconciliation` um protocolo `FonteCredencial` (`obter(unidade, tipo) -> dict`). Implementação `EnvCredencial` mantém o comportamento atual (robô noturno e testes); o app passa `KeyringCredencial`. Premmia recebe `diretorio` por parâmetro (default atual preservado).

**Empacotamento**: PyInstaller (onedir) + Inno Setup → `LogosMatch-Setup-<versão>.exe`, instalação por usuário em `%LOCALAPPDATA%\Programs\LogosMatch`. Playwright usa `channel="msedge"` (Edge do Windows); se falhar, oferece baixar Chromium uma vez. Dados, logs e planilhas em `%LOCALAPPDATA%\LogosMatch\` (fora do OneDrive). Desinstalar mantém dados, com caixa "apagar dados".

**Preparado para produto (sem implementar licença)**: nada da rede do diretor no código; nome/marca em um arquivo de configuração; import do `units.json` é opcional (botão "Importar postos LOGOS"), não automático; `id_instalacao` (UUID) gerado na primeira execução para uso futuro em licença/sincronização.

## 5. Modelo de dados (SQLite)
- `instalacao(id_instalacao, criada_em, versao_app)`
- `posto(id, nome, apelido, cnpj, empresa_codigo_webposto NULL, ativo, criado_em)`
- `fonte(id, posto_id, tipo ∈ {premmia, pagbank_edi, webposto}, ativo, config_json, ref_credencial, ultimo_teste_em, ultimo_teste_ok)`
- `coleta(id, fonte_id, dia, iniciada_em, terminada_em, situacao ∈ {ok, sem_movimento, erro, verificacao_humana}, qtd, total, hash_arquivo, erro_texto)`
- `transacao(id, coleta_id, posto_id, fonte, identificador, nsu, autorizacao, valor, momento, bandeira, forma, terminal, situacao)` — único em (posto_id, fonte, identificador)
- `caixa_webposto(id, posto_id, dia, caixa_codigo, setor, centro_custo, frentista_codigo, frentista_nome, totais_json)`
- `divergencia(id, posto_id, dia, caixa_webposto_id NULL, fonte, tipo, valor_esperado, valor_encontrado, nsu, explicacao_pt, correcao_pt, situacao)`
- `canal(id, tipo ∈ {telegram, email, toast}, config_json, ref_credencial, ativo)`
- `envio(id, canal_id, dia, enviado_em, situacao, erro_texto)`
- `usuario(id, nome, login UNIQUE, senha_hash, perfil ∈ {administrador, gerente, conferente}, ativo, criado_em, ultimo_acesso_em, tentativas_falhas, bloqueado_ate)`
- `usuario_posto(usuario_id, posto_id)` — escopo de gerente/conferente
- `log_acesso(id, usuario_id NULL, momento, acao, detalhe)` — append-only (login, falha de login, troca de credencial, cadastro, coleta manual, reenvio, export)
Valores em Decimal (armazenados como texto). Datas armazenadas ISO com fuso; exibidas dd/mm/aaaa HH:mm America/Recife.

## 6. Segredos
- Somente Windows Credential Manager via `keyring` (DPAPI, amarrado ao usuário Windows). Nome da entrada: `LogosMatch/<posto_id>/<tipo>` e `LogosMatch/canal/<canal_id>`.
- Nunca em SQLite, xlsx, logs, export, mensagens. Painel mostra `••••` + "Trocar" e "Testar conexão".
- Exportar/importar configuração (JSON) sem segredos, para replicar postos em outra máquina.
- Painel só em 127.0.0.1. Acesso sempre por login (seção 7A); sessão em cookie HttpOnly/SameSite=Strict, formulários com token anti-CSRF.

## 7. Painel
1. **Hoje** — por posto: ✅/❌/⚠ por fonte, total coletado, divergências com explicação + correção em português simples + nome e código do frentista; botões "Coletar agora" e "Reenviar".
2. **Postos** — lista, adicionar/editar/desativar.
3. **Fontes do posto** — Premmia, PagBank EDI, webPosto: credenciais + "Testar conexão".
4. **Canais** — Telegram (token do bot + chat id + botão "Enviar teste"), E-mail SMTP (servidor, porta, usuário, senha de app, destinatários), notificação Windows.
5. **Agenda** — horário de coleta e repescagem.
6. **Histórico** — últimas coletas e envios com erro legível.
7. **Usuários** (só administrador) — criar, editar perfil e postos, desativar, redefinir senha; ver log de acesso.
0. **Entrar** — tela de login antes de qualquer outra; no primeiro uso, cria o administrador.

## 7A. Níveis de acesso
| Ação | Administrador | Gerente | Conferente |
|---|---|---|---|
| Ver "Hoje" e "Histórico", baixar planilha | todos os postos | só os seus postos | só os seus postos |
| Coletar agora / Coletar agora (visível) / Reenviar | sim | seus postos | seus postos |
| Trocar credenciais de fontes (Premmia, PagBank, webPosto) | sim | seus postos | não |
| Cadastrar/desativar postos, importar/exportar configuração | sim | não | não |
| Canais de envio e agenda | sim | não | não |
| Usuários e níveis de acesso, ver log de acesso | sim | não | não |
| Ver valor de segredo salvo | **ninguém** (só trocar) | — | — |

- Login com usuário e senha (mín. 8 caracteres), hash `scrypt` (biblioteca padrão). Primeiro uso: assistente cria o administrador.
- 5 senhas erradas → bloqueio de 15 min. Sessão expira após 12 h sem uso.
- Esqueceu a senha do administrador: `LogosMatch.exe --redefinir-admin`, executado pelo usuário Windows da máquina (quem tem a máquina já tem os segredos do Credential Manager).
- Canais podem ser limitados a postos (`canal.config_json["postos"]`, vazio = todos): o gerente de um posto recebe só o dele no Telegram/e-mail.
- Toda ação sensível vai para `log_acesso`.
- Preparado para produto: mesmos perfis servem depois para acesso remoto/multi-máquina (v3), sem mudar o modelo.

## 8. Fluxo diário
1. 06:00: para cada posto ativo, coleta D-1 de cada fonte ativa (Premmia invisível; PagBank via API).
2. Se o posto tem chave webPosto: busca V1/CARTOES e CAIXAS_APRESENTADO do dia e roda `conciliar_cartoes`.
3. Grava tudo, gera `Logos_<apelido>_<dd-mm-aaaa>.xlsx` (abas: Resumo, Premmia, PagBank, Divergências) e envia pelos canais ativos.
4. Falha/verificação humana: toast + Telegram "Premmia do <posto> pediu verificação — abra o Logos Match e clique Coletar agora (visível)".
5. 10:00: repescagem só do que falhou. Se ainda faltar, avisa que o dia ficou sem coleta.
Sem chave webPosto: envia só os totais coletados, marcando "sem comparação com webPosto".

## 9. Canais grátis
| Canal | v1 | Motivo |
|---|---|---|
| Telegram bot | Sim (principal) | grátis, arquivo anexo, já usado |
| E-mail SMTP | Sim | grátis (Gmail/Outlook com senha de app), planilha anexa |
| Notificação Windows | Sim | local, para verificação humana |
| ntfy.sh | v1.1 | push grátis no celular |
| Discord/Google Chat/Teams webhook | sob demanda | grátis, se a equipe usar |
| WhatsApp Cloud API | Não | mensagens iniciadas pela empresa são cobradas |
| WhatsApp não oficial (whatsapp-web.js/Baileys) | Não | viola termos, risco de banir o número |
| CallMeBot WhatsApp | talvez v1.1, só alertas sem valores | grátis, só para o próprio número, passa por terceiro |

## 10. Roadmap
- **v1**: itens da seção 2 (inclui níveis de acesso).
- **v1.1**: aviso "Logos Match não rodou" (heartbeat), ntfy, histórico 30 dias no painel, checagem de versão nova (aviso, não auto-update).
- **v2 — novas fontes** (cada fonte nova é um adapter que devolve `TransacaoAdquirente` ou lançamentos de extrato, e entra no painel como mais um tipo de fonte do posto):
  - **EDI das outras administradoras**:
    - **Cielo EDI** — VIP loja/conveniência e Conv 24h 118508; cadastro matriz 1050633722, arquivos CIELO03/04/16 (sem conciliador contratado).
    - **Rede EDI** — VIP pista; aguarda liberação da Rede.
    - **Mais Pagamentos** (PIX Doze, Casa Caiada, VIP) — API dá 401 sem client_id/secret; caminho provável é o OFX da conta.
    - Outras sob demanda quando entrarem clientes novos (Stone, GetNet, Sicredi etc.).
  - **Coleta de extratos bancários** — "por onde conseguirmos", em ordem de preferência:
    1. **APIs dos bancos** (extrato PJ: BB, Itaú, Bradesco, PagBank conta) — exigem convênio/certificado de cada banco.
    2. **E-mail**: caixa IMAP (Gmail/Outlook com senha de app) lendo extratos e avisos que os bancos/adquirentes mandam (OFX, CSV, PDF), com filtro por remetente.
    3. **Arquivo**: pasta monitorada + upload no painel para OFX/CSV baixado à mão — sempre disponível como plano B.
    4. **Open Finance via agregador** (Pluggy, Belvo) — avaliar custo; só entra se houver plano gratuito ou o cliente pagar.
    Reaproveitar `adapters/ofx_reader.py` e `adapters/extrato_reader.py`. Extratos reais nunca vão para o repo.
  - Com extratos: conferência de recebíveis (adquirente × crédito no banco) e, se o diretor liberar, sangria/espécie × depósito D+1 (hoje fora de escopo).
  - Auto-update; sincronizar com o LOGOS central; import de relatório do webPosto para posto sem chave; detecção de posto cadastrado em duas máquinas.
- **v3 — produto**: licença por `id_instalacao`, marca configurável, acesso remoto com os mesmos perfis; lançar cartão faltante com NSU (Sprint 18b, com travas e aprovação Telegram).

## 11. Decisões minhas (o construtor pode seguir; o diretor pode mudar)
- Horários 06:00 e 10:00.
- Jinja2 server-side em vez de React (sem build, instalador menor).
- Um posto deve ser cadastrado em uma só máquina na v1 (o painel avisa no cadastro); detecção automática fica para v2.
- Retenção: planilhas e dados por 13 meses, depois apaga.
- Níveis de acesso entram já na v1 (o pedido não disse a versão): 3 perfis fixos, sem perfis customizáveis.
- Testes: unitários offline para banco, credenciais (keyring falso), relatório e canais (HTTP mockado); os adapters já têm testes no módulo.

## 12. Deixado para o construtor
Layout das telas, estrutura interna dos templates, nomes de funções, detalhes do script Inno Setup, estratégia de logs rotativos.
