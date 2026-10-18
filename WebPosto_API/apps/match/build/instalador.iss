; Inno Setup - Logos Match. Compilar via build.ps1 (passa /DVersao=x.y.z).
#ifndef Versao
  #define Versao "0.1.0"
#endif
#define Exe "LogosMatch.exe"

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

[Run]
; Tarefa do Agendador: ao fazer logon do usuario atual (sem admin).
Filename: "{sys}\schtasks.exe"; Parameters: "/Create /SC ONLOGON /TN ""Logos Match"" /TR ""\""{app}\{#Exe}\"""" /RL LIMITED /F"; Flags: runhidden; StatusMsg: "Registrando inicio automatico..."
Filename: "{app}\{#Exe}"; Description: "Abrir o Logos Match agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Logos Match"" /F"; Flags: runhidden; RunOnceId: "RemoverTarefa"

[Code]
var
  ApagarDados: Boolean;

function InitializeUninstall(): Boolean;
begin
  ApagarDados := MsgBox('Apagar também os dados do Logos Match (banco, logs e credenciais guardadas no Windows)?'
    + #13#10 + 'Escolha "Não" para manter os dados e poder reinstalar depois.',
    mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Codigo: Integer;
begin
  if (CurUninstallStep = usUninstall) and ApagarDados then
  begin
    // Antes de remover os arquivos: o exe apaga as entradas LogosMatch do Credential Manager.
    Exec(ExpandConstant('{app}\{#Exe}'), '--apagar-credenciais', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  end;
  if (CurUninstallStep = usPostUninstall) and ApagarDados then
    DelTree(ExpandConstant('{localappdata}\LogosMatch'), True, True, True);
end;
