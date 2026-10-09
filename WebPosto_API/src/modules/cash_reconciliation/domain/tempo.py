"""Compatibilidade com o relogio compartilhado de Data Integration."""
from src.modules.webposto_integration.tempo import (
    DataHoraLocal, FUSO, agora, formatar_data, formatar_data_hora, formatar_hora,
    hoje, ler_data, ler_data_hora, ontem, para_local,
)

__all__ = [
    "DataHoraLocal", "FUSO", "agora", "formatar_data", "formatar_data_hora",
    "formatar_hora", "hoje", "ler_data", "ler_data_hora", "ontem", "para_local",
]
