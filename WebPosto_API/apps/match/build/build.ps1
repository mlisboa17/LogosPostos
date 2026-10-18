# Gera dist\LogosMatch\ (PyInstaller onedir) e dist\LogosMatch-Setup-<VERSAO>.exe (Inno Setup).
# Uso: powershell -File apps\match\build\build.ps1 [-Venv <pasta>] [-UsarVenvAtual]
param(
    [string]$Venv = "build\venv-match",
    [switch]$UsarVenvAtual   # reaproveita .venv em vez de criar um venv limpo (mais rapido)
)
$ErrorActionPreference = "Stop"
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
Set-Location $raiz

$versao = & python -c "import re,pathlib;print(re.search(r'VERSAO\s*=\s*\"([^\"]+)\"',pathlib.Path('apps/match/__init__.py').read_text(encoding='utf-8')).group(1))"
if (-not $versao) { throw "Nao consegui ler a VERSAO de apps/match/__init__.py" }
Write-Host "Logos Match $versao"

if ($UsarVenvAtual) { $venv = Join-Path $raiz ".venv" } else { $venv = Join-Path $raiz $Venv }
if (-not $UsarVenvAtual) {
    if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
    & python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-match.txt
if ($LASTEXITCODE -ne 0) { throw "pip install falhou" }

& $py -m PyInstaller apps\match\build\match.spec --noconfirm --workpath build\pyi --distpath dist
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou" }
Write-Host "Onedir pronto em dist\LogosMatch"

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    foreach ($c in @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $c) { $iscc = Get-Item $c; break }
    }
}
if (-not $iscc) {
    Write-Error "Inno Setup (iscc) nao encontrado. Instale o Inno Setup 6 (jrsoftware.org) e rode de novo. O onedir ja esta em dist\LogosMatch; o instalador .exe NAO foi gerado."
    exit 1
}
$isccPath = if ($iscc.PSObject.Properties.Name -contains "Source") { $iscc.Source } else { $iscc.FullName }
& $isccPath "/DVersao=$versao" apps\match\build\instalador.iss
if ($LASTEXITCODE -ne 0) { throw "iscc falhou" }
Write-Host "Instalador: dist\LogosMatch-Setup-$versao.exe"
