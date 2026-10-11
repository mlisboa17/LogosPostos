import os
import sys
from pathlib import Path

# Garante que src.modules seja resolvido apontando para WebPosto_API/src/modules
webposto_src = str(Path(__file__).resolve().parents[2] / "WebPosto_API" / "src")
webposto_dir = str(Path(__file__).resolve().parents[2] / "WebPosto_API")

if webposto_dir not in sys.path:
    sys.path.insert(0, webposto_dir)

import src
if webposto_src not in src.__path__:
    src.__path__.append(webposto_src)

import importlib.util
webposto_job = Path(__file__).resolve().parents[2] / "WebPosto_API" / "src" / "jobs" / "importar_ofx.py"
spec = importlib.util.spec_from_file_location("webposto_importar_ofx", str(webposto_job))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

if __name__ == "__main__":
    mod.main()
