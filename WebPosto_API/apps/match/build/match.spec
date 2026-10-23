# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir do Logos Match. Rodar a partir de WebPosto_API:
#   pyinstaller apps/match/build/match.spec --noconfirm --workpath build/pyi --distpath dist
# O Chromium do Playwright NAO e empacotado: o app usa o Microsoft Edge instalado.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

RAIZ = Path(SPECPATH).resolve().parents[2]  # WebPosto_API
MATCH = RAIZ / "apps" / "match"
CR = RAIZ / "src" / "modules" / "cash_reconciliation"

hidden = []
for pacote in ("apps.match", "src.modules.cash_reconciliation", "src.modules.webposto_integration",
                "src.modules.fiscal_docs",
               "src.shared", "uvicorn", "apscheduler", "keyring.backends"):
    hidden += collect_submodules(pacote)
pw_datas, pw_bins, pw_hidden = collect_all("playwright")  # driver node.exe + cli.js; sem Chromium
hidden += pw_hidden
# DANFE/DANFSe: inclui municipios_ibge.csv e o logo da NFS-e
bfr_datas, bfr_bins, bfr_hidden = collect_all("brazilfiscalreport")
hidden += bfr_hidden + collect_submodules("fpdf") + collect_submodules("pypdf")
hidden += ["windows_toasts", "pystray._win32", "keyring.backends.Windows"]

datas = [
    (str(MATCH / "painel" / "templates"), "apps/match/painel/templates"),
    (str(MATCH / "painel" / "static"), "apps/match/painel/static"),
    (str(MATCH / "assets"), "apps/match/assets"),
    (str(CR / "config" / "units.json"), "src/modules/cash_reconciliation/config"),
]

a = Analysis(
    [str(MATCH / "__main__.py")],
    pathex=[str(RAIZ)],
    binaries=pw_bins + bfr_bins,
    datas=datas + pw_datas + bfr_datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LogosMatch",
    console=False,
    icon=str(MATCH / "assets" / "icone.ico"),
    upx=False,
)
# Mesmo codigo, com console: --redefinir-admin, --apagar-credenciais, --verificar
exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LogosMatchCLI",
    console=True,
    icon=str(MATCH / "assets" / "icone.ico"),
    upx=False,
)
coll = COLLECT(exe, exe_cli, a.binaries, a.datas, name="LogosMatch", upx=False)
