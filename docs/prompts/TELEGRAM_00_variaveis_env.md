# Prompt — TELEGRAM_00: preparar as variáveis do Telegram no .env (Cursor / VS Code)

Repositório `C:\Projetos\LOGOS\LogosPostos`. Tarefa única, sem commit (o `.env` não é versionado).

1. No arquivo `WebPosto_API/.env`, **acrescente ao final** as linhas abaixo, cada uma **somente se a variável ainda não existir** no arquivo:
   ```
   # Telegram — resumo diário do robô
   TELEGRAM_ENVIO=0
   TELEGRAM_BOT_TOKEN=
   TELEGRAM_CHAT_IDS=
   ```
2. Regras obrigatórias:
   - **Não mostre, não imprima e não copie** nenhum valor que já esteja no `.env` (nem no chat, nem no terminal, nem em log). Para checar se a variável existe, procure só o nome no início da linha e informe apenas "existe" ou "não existe".
   - Não altere, não reordene e não apague nenhuma outra linha. Preserve a codificação e as quebras de linha do arquivo.
   - **Não preencha o token nem o chat id**: o diretor preenche à mão. Se alguém colar um token no chat, não use; avise que o token deve ir direto no arquivo.
   - Não faça `git add` do `.env`. Confirme com `git check-ignore WebPosto_API/.env` que ele está ignorado.
3. Ao terminar, responda só: quais das 3 variáveis foram adicionadas, quais já existiam, e o resultado do `git check-ignore`.
