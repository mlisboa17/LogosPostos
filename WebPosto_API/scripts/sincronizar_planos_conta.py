"""Script CLI para sincronização manual do plano de contas gerencial do webPosto (LOGOS).

Uso:
  # Consulta status da última sincronização
  python WebPosto_API/scripts/sincronizar_planos_conta.py --status

  # Simulação (dry-run) a partir do artefato oficial versionado (offline)
  python WebPosto_API/scripts/sincronizar_planos_conta.py --dry-run --offline-file docs/validation/PLANOS_CONTA_MASTER_01.json

  # Aplicação local atômica (apply) a partir do artefato oficial versionado (offline)
  python WebPosto_API/scripts/sincronizar_planos_conta.py --apply --offline-file docs/validation/PLANOS_CONTA_MASTER_01.json

  # Sincronização via API oficial (somente leitura, exige autorização / credenciais em .env)
  python WebPosto_API/scripts/sincronizar_planos_conta.py --dry-run
  python WebPosto_API/scripts/sincronizar_planos_conta.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "WebPosto_API"
ENV_PATH = API_ROOT / ".env"
DEFAULT_OFFLINE_FILE = ROOT / "docs" / "validation" / "PLANOS_CONTA_MASTER_01.json"

sys.path.insert(0, str(API_ROOT))

from src.modules.master_data.adapters.sqlite_master_data_repository import (  # noqa: E402
    SqliteMasterDataRepository,
)
from src.modules.master_data.application.master_data_service import (  # noqa: E402
    MasterDataService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sincronizador do Plano de Contas Gerencial do webPosto."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Executa comparação sem gravar no SQLite.")
    group.add_argument("--apply", action="store_true", help="Aplica as alterações atomicamente no SQLite local.")
    group.add_argument("--status", action="store_true", help="Exibe o status da última sincronização bem-sucedida.")

    parser.add_argument(
        "--offline-file",
        type=Path,
        default=None,
        help="Caminho para arquivo JSON com payload oficial para execução offline.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Caminho customizado do banco SQLite master_data.",
    )

    args = parser.parse_args()

    repo = SqliteMasterDataRepository(db_path=args.db_path)
    service = MasterDataService(repository=repo)

    if args.status:
        ultima = service.obter_ultima_sincronizacao_planos()
        if not ultima:
            print("Nenhuma sincronização oficial registrada na tabela master_sincronizacao_log.")
            return
        print(json.dumps(ultima, ensure_ascii=False, indent=2))
        return

    modo = "apply" if args.apply else "dry-run"

    dados_oficiais = None
    origem = "webposto_api_v1"

    if args.offline_file:
        caminho_arquivo = args.offline_file if args.offline_file.is_absolute() else (ROOT / args.offline_file)
        if not caminho_arquivo.exists():
            raise FileNotFoundError(f"Arquivo offline não encontrado: {caminho_arquivo}")
        raw_json = json.loads(caminho_arquivo.read_text(encoding="utf-8"))
        dados_oficiais = raw_json.get("plans") if isinstance(raw_json, dict) and "plans" in raw_json else raw_json
        origem = f"arquivo_offline:{caminho_arquivo.name}"
    else:
        # Consulta API se autorizado e configurado
        load_dotenv(ENV_PATH, override=False)
        api_key = (os.getenv("WEBPOSTO_API_KEY_CASA_CAIADA") or "").strip()
        base_url = (os.getenv("WEBPOSTO_BASE_URL") or "https://web.qualityautomacao.com.br").rstrip("/")
        if not api_key:
            # Se não houver credencial na linha de comando/env, usa o arquivo padrão versionado como fallback seguro
            if DEFAULT_OFFLINE_FILE.exists():
                print(f"WEBPOSTO_API_KEY não informada. Utilizando artefato sanitizado padrão: {DEFAULT_OFFLINE_FILE.name}")
                raw_json = json.loads(DEFAULT_OFFLINE_FILE.read_text(encoding="utf-8"))
                dados_oficiais = raw_json.get("plans") if isinstance(raw_json, dict) and "plans" in raw_json else raw_json
                origem = f"artefato_padrao:{DEFAULT_OFFLINE_FILE.name}"
            else:
                raise RuntimeError("Credenciais não configuradas e artefato padrão ausente.")
        else:
            origem = "webposto_api_v1"

    resultado = service.sincronizar_planos_conta(
        modo=modo,
        dados_oficiais=dados_oficiais,
        base_url=base_url if not dados_oficiais else None,
        api_key=api_key if not dados_oficiais else None,
        origem=origem,
    )

    print(json.dumps(resultado.model_dump(), ensure_ascii=False, indent=2))

    if not resultado.sucesso:
        sys.exit(1)


if __name__ == "__main__":
    main()
