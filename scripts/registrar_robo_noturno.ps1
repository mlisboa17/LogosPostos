param(
    [string]$PythonExe = "",
    [string]$NomeTarefa = "LOGOS - Auditoria de Caixa"
)

$ErrorActionPreference = "Stop"
$FusoWindows = [System.TimeZoneInfo]::Local
if ($FusoWindows.BaseUtcOffset -ne [TimeSpan]::FromHours(-3) -or $FusoWindows.SupportsDaylightSavingTime) {
    Write-Warning "O fuso do Windows nao e UTC-03:00 fixo. Ajuste para o horario de Brasilia/Recife antes de agendar: 03:00 segue o relogio do Windows."
}
$Repositorio = Split-Path -Parent $PSScriptRoot
$DiretorioApi = Join-Path $Repositorio "WebPosto_API"
if (-not $PythonExe) {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
}
$PythonExe = (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath (Join-Path $DiretorioApi "src\modules\cash_reconciliation\jobs\noturno.py"))) {
    throw "Modulo do robo noturno nao encontrado."
}

$Acao = New-ScheduledTaskAction -Execute $PythonExe `
    -Argument "-B -m src.modules.cash_reconciliation.jobs.noturno" `
    -WorkingDirectory $DiretorioApi
$Gatilho = New-ScheduledTaskTrigger -Daily -At "03:00"
$Configuracao = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName $NomeTarefa -Action $Acao -Trigger $Gatilho `
    -Settings $Configuracao -Principal $Principal -ErrorAction Stop | Out-Null
Write-Host "Tarefa registrada para 03:00: $NomeTarefa"
