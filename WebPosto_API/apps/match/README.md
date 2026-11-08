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

## Pasta da rede (um posto em uma só máquina)
Em *Agenda > Pasta da rede* (só administrador) informe uma pasta que todas as máquinas com o
Logos Match enxergam e sincronizam, por exemplo `C:\Users\<você>\OneDrive\LogosMatch-Rede`
(OneDrive, Google Drive ou pasta de rede). "Salvar" confere que a pasta existe e aceita gravação
(cria `LogosMatch\postos`) e registra nela todos os postos ativos; os que já pertencem a outra
máquina são desativados e listados com o motivo. "Desligar" volta a valer só o aviso.

- Cada posto vira `<pasta>\LogosMatch\postos\<chave>.json` (chave = código do webPosto ou o CNPJ
  só com dígitos), com instalação, nome da máquina, usuário do Windows, nome do posto e data.
  **Nenhuma senha vai para a pasta.**
- Com a pasta ligada, cadastrar, editar ou reativar um posto exige o código do webPosto ou o CNPJ.
  Posto de outra máquina é recusado ("Este posto já está cadastrado na máquina X desde …").
  Pasta inacessível (OneDrive pausado, rede fora): o cadastro, a reativação e a importação são
  recusados sem gravar nada; a coleta segue e avisa "Não foi possível conferir a pasta da rede."
- Antes de cada coleta a máquina confere de novo: posto que passou a ser de outra máquina não é
  coletado ("O posto X agora é coletado pela máquina Y.").
- Importar configuração/units.json pula (e lista) os postos de outra máquina.
- *Postos* mostra a coluna **Proteção**: "Protegido (esta máquina)", "Sem proteção" ou
  "Pertence à máquina X".
- **Assumir posto** (administrador, com a confirmação "Confirmo que a outra máquina não coleta
  mais este posto"; fica no log de acesso): use quando a outra máquina quebrou, foi trocada ou
  este PC foi reinstalado (a reinstalação gera outra instalação, então os postos antigos aparecem
  como "Pertence à máquina <o mesmo nome>").
- Desativar um posto ou desinstalar com "Apagar também os dados" remove da pasta os registros
  desta instalação (`LogosMatchCLI.exe --liberar-postos` faz o mesmo à mão).
- Desligar ou trocar a Pasta da rede não remove os registros desta máquina; use 'Assumir posto' na outra máquina se precisar.

## Extratos OFX

1. **Pasta de entrada**: com a Pasta da rede ligada, coloque os arquivos em
   `C:\Users\<usuario>\OneDrive\LogosMatch-Rede\Extratos\Entrada` (ajuste o caminho à pasta
   compartilhada configurada). Sem Pasta da rede, use
   `%LOCALAPPDATA%\LogosMatch\Extratos\Entrada`. O Match verifica essa pasta periodicamente,
   reconhece OFX e arquiva os recebidos.
2. **Baixar o OFX**: no internet banking, abra a conta e o período desejado, escolha
   *Exportar/Download*, selecione o formato **OFX** e salve o arquivo na pasta de entrada. O
   nome do menu varia por banco; não converta o arquivo para CSV ou Excel.
3. **Vincular conta**: em *Extratos > Aguardando vínculo*, escolha o posto e informe o código da
   conta correspondente no webPosto. Essa associação é feita por um administrador.
4. **Importar no webPosto**: um administrador deve habilitar **Enviar extratos ao webPosto** para
   cada posto autorizado. Arquivos vinculados geram uma prévia para aprovação no painel ou nos
   botões de um canal Telegram inscrito. Para aprovações, configure um bot próprio do Logos Match,
   diferente do bot usado pelo robô LOGOS; não compartilhe o mesmo bot com outro programa.
   Débitos só podem ser propostos depois que um administrador registrar, em *Extratos*,
   o **Formato de débito confirmado pela Quality**. O padrão é **Não confirmado**: o lote
   com débitos fica bloqueado inteiro, sem enviar apenas os créditos daquele período.
   Use exclusivamente o formato confirmado pela Quality, nunca por tentativa.
   Extratos recusados não são propostos novamente automaticamente; use **Propor de novo**
   no histórico para liberá-los. Depois de uma falha, há uma espera de uma hora, que esse
   botão também permite dispensar. Janelas já enviadas com sucesso não são reenviadas.
5. **Autonomia gradual**: cinco aprovações limpas consecutivas tornam aquele tipo elegível para
   automação. Correção, recusa ou falha da importação zera a sequência e desliga a automação.
   A camada 1 importa automaticamente apenas para contas elegíveis. Na camada 2, somente débitos
   de até R$ 500 por lançamento e até R$ 2.000 no dia por conta podem ser marcados como
   **Pronto para lançar sozinho**; entradas e transferências próprias não se qualificam. A camada
   2 não cria lançamentos no webPosto: qualquer escrita permanece desabilitada. O administrador
   pode desligar ou religar cada tipo em *Extratos > Autonomia*.
   O limite diário considera as propostas automáticas criadas no dia local
   (America/Recife), mesmo que os lançamentos do extrato sejam de dias anteriores.
   Uma importação automática aguardando execução não é exibida como importada; o
   agendador retenta a execução quando ela não conseguiu iniciar.

## Notas de serviço (v0.5): comece por aqui

Abra **Buscar notas** no menu. São três passos:

1. **Enviar o certificado:** escolha o arquivo A1 (.pfx/.p12) e digite a senha. O Match lê o CNPJ e a razão social do certificado e cria a empresa. Repita para cada CNPJ. O arquivo fica cifrado (DPAPI) e a senha fica no Credential Manager.
2. **Buscar notas de serviço:** consulta o sistema nacional (ADN) somente para leitura. Depois disso a busca roda sozinha todo dia às 07:00. Sem nota nova, a consulta seguinte só acontece depois de 1 hora.
3. **Ver e baixar:** em **Notas fiscais**, use os atalhos de período e baixe PDF único, XMLs ou planilha.

Prefeitura que não envia ao sistema nacional: baixe o XML no portal dela e use **Importar**. Só entram notas em que a empresa é a tomadora.

## Notas fiscais (v0.3)

Captura as NF-e recebidas por cada empresa e manda o pacote do mês para a contabilidade.

1. **Empresas**: cadastre CNPJ, razão social e o posto do Logos Match ligado a ela. As NF-e vêm do
   webPosto (somente leitura) pela chave do webPosto desse posto. Todo dia às 07:00 o Match busca as notas;
   de hora em hora (08:30–20:30) tenta de novo as que ainda não têm XML.
2. **Escritórios**: nome, e-mails, empresas atendidas, dia do envio (padrão 5), modo (*enviar* ou *só gerar*)
   e PDFs (separados, um arquivo só ou os dois). Usa o servidor do canal de e-mail cadastrado em **Canais**.
3. No dia do envio, às 08:00 (ou quando o Match abrir depois disso), sai o pacote do mês anterior:
   `<CNPJ>_<AAAA-MM>.zip` com `xml/`, `pdf/` e `Resumo_<apelido>_<mm-aaaa>.xlsx`. Acima de 20 MB vai em partes.
   Se faltar algo (erro de captura, nota sem XML há mais de 48 h, empresa sem chave), o pacote fica **retido**
   em **Pacotes** com o motivo e o botão "Enviar mesmo assim". Nota que chega depois do envio vai num pacote
   complementar.
4. **Importar**: XML ou ZIP de NF-e/NFS-e do padrão nacional (ex.: notas de serviço baixadas na prefeitura).
5. Perfil **Contabilidade**: vê só Notas fiscais e Pacotes das empresas dos seus postos.

Os XMLs ficam em `<pasta da rede>\fiscal\<CNPJ>\` (ou `%LOCALAPPDATA%\LogosMatch\fiscal\` sem pasta da rede).
Ainda não captura sozinho: CT-e de frete e NFS-e pelo sistema nacional (próxima versão, com certificado A1).

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

## Liberar postos na pasta da rede
`LogosMatchCLI.exe --liberar-postos` remove da pasta da rede os postos registrados por esta
instalação e mostra "N posto(s) liberado(s) na pasta da rede." (sem pasta configurada: "Pasta da
rede não configurada."; pasta inacessível: sai com código 1). O desinstalador roda isso antes de
apagar as credenciais quando você marca "Apagar também os dados"; se falhar, a desinstalação segue.

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
