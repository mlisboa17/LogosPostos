# Logos Match

App de bandeja do Windows que coleta Premmia, PagBank e webPosto, concilia por posto e
mostra o resultado num painel local (`http://127.0.0.1:<porta>/`).

## Instalar
1. Execute `LogosMatch-Setup-<versão>.exe` (não precisa de administrador).
2. Instala em `%LOCALAPPDATA%\Programs\LogosMatch`, cria atalho no Menu Iniciar e um atalho na pasta
   Inicializar do usuário, que abre o app a cada logon.
3. Requer o Microsoft Edge instalado (usado pela coleta do Premmia).

## Primeiro acesso
Abra o ícone da bandeja (ou o atalho) e crie o administrador na tela inicial. Login do
administrador: `admin`; senha com no mínimo 8 caracteres.

## Perfis
`administrador` (tudo), e os demais perfis definidos em *Usuários* (cada um enxerga apenas os
postos atribuídos). Ações sensíveis ficam no log de acesso.

## Cadastrar posto
*Postos > Novo*: nome, apelido, CNPJ e `empresaCodigo` do webPosto. Em seguida informe as
fontes (Premmia, PagBank, webPosto). O botão "Importar postos LOGOS" lê `units.json` do módulo
de conciliação.

## Onde ficam dados e segredos
- Dados e logs: `%LOCALAPPDATA%\LogosMatch` (banco SQLite, `logs\match.log`; mude com `LOGOS_MATCH_DIR`).
- Segredos (senhas, tokens, chaves): Credential Manager do Windows, serviço `LogosMatch`.
  Nunca vão para o banco nem para o log.

## Redefinir a senha do administrador
Num terminal, na pasta de instalação (o `LogosMatchCLI.exe` tem console; o `LogosMatch.exe` não):

    LogosMatchCLI.exe --redefinir-admin

Informe a nova senha duas vezes (mín. 8 caracteres). Login: `admin`.

## Apagar credenciais
`LogosMatchCLI.exe --apagar-credenciais` remove do Windows todas as credenciais conhecidas
(postos ativos e inativos, canais) e sai. O desinstalador chama isso quando você marca
"Apagar também os dados".

## Diagnóstico
`LogosMatchCLI.exe --verificar` confere templates, static, ícone, units.json, driver do Playwright e backend do keyring (exit 0 se tudo ok).

## Gerar o instalador
Pré-requisitos: Python 3.12+ no PATH e [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`iscc`).

    cd WebPosto_API
    powershell -File apps\match\build\build.ps1            # venv limpo (padrão)
    powershell -File apps\match\build\build.ps1 -UsarVenvAtual   # reaproveita .venv

Saídas (ignoradas pelo Git): `dist\LogosMatch\` (onedir) e `dist\LogosMatch-Setup-<versão>.exe`.
Sem `iscc` o script termina após o onedir com uma mensagem clara. O Chromium do Playwright
não é empacotado.

## Verificação em máquina limpa
Pendente (rodar num Windows limpo ou em outro usuário Windows) e registrar o resultado aqui:
- [ ] Instalar o `.exe` sem administrador; atalho no Menu Iniciar criado.
- [ ] Reiniciar/fazer logon: o app sobe sozinho (ícone na bandeja; atalho em Inicializar).
- [ ] Criar o administrador no primeiro acesso e cadastrar um posto.
- [ ] Coleta do Premmia abre o Microsoft Edge.
- [ ] `LogosMatchCLI.exe --redefinir-admin` redefine a senha.
- [ ] Desinstalar marcando "Apagar também os dados": some `%LOCALAPPDATA%\LogosMatch`, as entradas
      `LogosMatch` do Credential Manager e o atalho de Inicializar. Com o app aberto, o desinstalador o fecha antes.
