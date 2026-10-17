# ENTREGA 21 — Robô autônomo (recupera dias, avisa travas) + versão de produção

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem merge). **Somente leitura no webPosto** (escrita congelada). `.env` só via `load_dotenv`/`dotenv_values`, nunca imprimir nem editar. **REUSE > ADAPT > CREATE.** Uma entrega ponta a ponta, com o critério de aceite no fim. Leia antes: topo do `STATUS.md`, `docs/validation/PROD_SAFE_01_RUN_INTEGRITY_VALIDATION.md`, `docs/validation/PROD_RELEASE_01_VALIDATION.md`.

## Princípio do diretor (17/10/2026)

"Tudo deve fazer parte do LOGOS; isso será expandido para outras filiais; estamos construindo um produto." Nada pode depender de alguém (Claude, agente ou diretor) rodar comando à mão para o sistema se recuperar. Toda regra vale para qualquer unidade cadastrada em `units.json` — nada fixo por código de unidade.

## O que aconteceu e o produto precisa resolver sozinho

1. Travas de escrita ficaram em `1` após um teste (15/10). O robô das 03:00 bloqueou corretamente (gate PROD-SAFE-01), mas **ninguém foi avisado** e ficaram **2 noites sem auditoria** (16 e 17/10). Os dias só foram recuperados à mão.
2. Reprocessar um dia fez o Premmia não coletar ("login já tentado" — regra de 1 login por noite), deixando 16/10 sem Premmia.
3. O robô roda direto da pasta onde se desenvolve; versão inacabada já rodou em produção.

## O que fazer

### A. Aviso de bloqueio (Telegram, diretor)
- Se a execução das 03:00 for BLOCKED/FAILED (ex.: trava de escrita ligada, configuração inválida), enviar **aviso operacional curto** ao diretor: o que bloqueou, desde quando, o que fazer ("volte WEBPOSTO_WRITES e LOGOS_ERP_ESCRITA para 0 no .env"). Sem números financeiros (regra do gate).
- Se uma trava de escrita estiver em `1` por mais de 2 horas fora de uma ação aprovada (auditoria do piloto), avisar uma vez.

### B. Recuperação automática de dias
- A cada execução, o robô verifica os **últimos 7 dias** (D-2, regra RN-REDE-006): dia sem execução, ou com fonte obrigatória FAILED/BLOCKED/NOT_COLLECTED por motivo transitório → **reprocessa sozinho** (do mais antigo ao mais novo), registrando no estado/ledger por `run_id`.
- Premmia: a coleta de uma noite cobre todos os dias pendentes daquela unidade (planilha mensal) — **um único login por noite** atende os dias atrasados; nunca tentar segundo login.
- No resumo do dia, uma linha: "Recuperei 15 e 16/10 (estavam sem auditoria por trava de escrita)".
- Limite: máximo de reprocessamentos por noite (configurável) para não estourar a API.

### C. Versão de produção (cutover isolado, sem infraestrutura nova)
Comando do próprio Logos: `python -m src.jobs.publicar_versao --versao 1.0.0`:
1. Exige árvore limpa e **bateria completa verde**; cria tag `logos-v1.0.0`.
2. Copia a versão para `C:\Projetos\LOGOS\producao\v1.0.0\` (somente código), cria `venv` próprio e instala dependências travadas.
3. **Dados, `.env` e logs ficam fora da versão** (pasta compartilhada já existente `WebPosto_API\data` ou `C:\Projetos\LOGOS\dados\` — escolher e documentar; não duplicar dados reais nem copiar `.env` para dentro do git).
4. Smoke test somente leitura da versão nova (sem Telegram) e marca `producao\ATUAL` → `v1.0.0`.
5. `--rollback` volta para a versão anterior.
6. A tarefa agendada do Windows deve chamar `producao\ATUAL`. **Mudar a tarefa exige o "ok" do diretor**: o comando mostra exatamente o que vai mudar e só aplica com `--aplicar-tarefa` + confirmação; sem isso, apenas imprime as instruções.
- Testes nunca gravam em dados reais: guarda global que falha o teste se algo escrever fora de `tmp_path` (pendência do PROD-RELEASE-01).
- Aceitar a reconstrução semântica do estado local citada no PROD-RELEASE-01 (é estado do robô, regenerado a cada noite) e registrar a decisão.

### D. Multi-filial
- Conferir que nenhuma regra usa código de unidade fixo no código (só `units.json`); listar e remover o que existir. Documentar em `docs/` "Como cadastrar uma filial nova" (campos do `units.json`, chaves no `.env`, fontes por unidade, posto × loja por CNPJ ou centro de custo).

## Critério de aceite (o diretor confere)

1. Teste: trava em 1 às 03:00 → aviso no Telegram (simulado) e, na noite seguinte com trava em 0, **os dias perdidos são reprocessados sozinhos**, com a linha "Recuperei …" no resumo.
2. Teste: Premmia de dias atrasados coletado com **um** login.
3. `publicar_versao` cria `producao\v1.0.0`, roda o smoke e mostra a mudança da tarefa **sem aplicar**; `--rollback` funciona (teste em pasta temporária).
4. Guarda de testes ativa: nenhum teste grava fora de temporários.
5. Documento "Como cadastrar uma filial nova".
6. Bateria completa verde; zero escrita no webPosto; nada enviado ao Telegram real durante o desenvolvimento.

Atualizar `STATUS.md` (topo) e `REGRAS_DE_NEGOCIO.md` (recuperação automática). Commits por parte; depois `git push`.
