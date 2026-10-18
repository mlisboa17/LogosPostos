; Inno Setup - Logos Match. Compilar via build.ps1 (passa /DVersao=x.y.z).
#ifndef Versao
  #define Versao "0.1.0"
#endif
#define Exe "LogosMatch.exe"
#define ExeCli "LogosMatchCLI.exe"

[Setup]
AppId={{5B7E1C52-3F0A-4D9B-9C61-4C6F0A7D2E81}
AppName=Logos Match
AppVersion={#Versao}
AppPublisher=Logos
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\LogosMatch
DefaultGroupName=Logos Match
DisableProgramGroupPage=yes
OutputDir=..\..\..\dist
OutputBaseFilename=LogosMatch-Setup-{#Versao}
SetupIconFile=..\assets\icone.ico
UninstallDisplayIcon={app}\{#Exe}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\..\..\dist\LogosMatch\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Logos Match"; Filename: "{app}\{#Exe}"
; Inicio automatico no logon do usuario (removido ao desinstalar).
Name: "{userstartup}\Logos Match"; Filename: "{app}\{#Exe}"

[Run]
Filename: "{app}\{#Exe}"; Description: "Abrir o Logos Match agora"; Flags: nowait postinstall skipifsilent

[Code]
var
  ApagarDados: Boolean;
  CredenciaisOk: Boolean;

function InitializeUninstall(): Boolean;
begin
  ApagarDados := MsgBox('Apagar também os dados do Logos Match (banco, logs e credenciais guardadas no Windows)?'
    + #13#10 + 'Escolha "Não" para manter os dados e poder reinstalar depois.',
    mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  CredenciaisOk := True;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Codigo: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Fecha o app em execucao (so o nosso exe); "nao encontrado" e ignorado.
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#Exe} /F', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
    if ApagarDados then
    begin
      // Antes de remover os arquivos: apaga as entradas LogosMatch do Credential Manager.
      if (not Exec(ExpandConstant('{app}\{#ExeCli}'), '--apagar-credenciais', '', SW_HIDE,
                   ewWaitUntilTerminated, Codigo)) or (Codigo <> 0) then
        CredenciaisOk := False;
    end;
  end;
  if (CurUninstallStep = usPostUninstall) and ApagarDados then
  begin
    if CredenciaisOk then
      DelTree(ExpandConstant('{localappdata}\LogosMatch'), True, True, True)
    else
      MsgBox('Não foi possível remover as credenciais guardadas no Windows. A pasta de dados '
        + '(%LOCALAPPDATA%\LogosMatch) foi mantida. Remova as entradas "LogosMatch" no '
        + 'Gerenciador de Credenciais do Windows e apague a pasta manualmente.', mbError, MB_OK);
  end;
end;
