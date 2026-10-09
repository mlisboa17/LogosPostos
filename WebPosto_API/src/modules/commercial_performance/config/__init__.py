from pathlib import Path
import logging

from pydantic import ValidationError

from ..domain.models import MetasMes, Posto

logger = logging.getLogger(__name__)
DIRETORIO_METAS = Path(__file__).resolve().parents[4] / "data" / "metas"
POSTOS = {
    11495: Posto(empresa_codigo=11495, nome="POSTO VIP", chave_env="WEBPOSTO_API_KEY_POSTO_VIP"),
    74014: Posto(empresa_codigo=74014, nome="POSTO DOZE FILIAL II", chave_env="WEBPOSTO_API_KEY_POSTO_DOZE_FILIAL_II"),
    5555: Posto(empresa_codigo=5555, nome="AP CASA CAIADA", chave_env="WEBPOSTO_API_KEY_CASA_CAIADA"),
}


class MetasErro(RuntimeError):
    pass


def ler_metas(mes: str, *, diretorio: Path | None = None) -> MetasMes | None:
    from ..rules.placar import primeiro_dia

    primeiro_dia(mes)
    caminho = (diretorio if diretorio is not None else DIRETORIO_METAS) / f"{mes}.json"
    try:
        texto = caminho.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        logger.error("Falha ao ler metas mes=%s", mes)
        raise MetasErro("Metas indisponiveis.") from None
    try:
        resultado = MetasMes.model_validate_json(texto)
        if resultado.mes != mes:
            raise ValueError("Mes divergente.")
        return resultado
    except (ValidationError, ValueError):
        logger.error("Metas invalidas mes=%s", mes)
        raise MetasErro("Arquivo de metas invalido.") from None
