"""Gerenciamento da fila local de despesas avulsas (data/despesas_avulsas/fila.json)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

from ..domain.comprovante import ItemFilaDespesa

logger = logging.getLogger(__name__)


def _obter_base_data() -> Path:
    """Retorna o diretório base WebPosto_API/data."""
    return Path(__file__).resolve().parents[4] / "data"


def obter_caminho_fila() -> Path:
    """Retorna o caminho de data/despesas_avulsas/fila.json."""
    return _obter_base_data() / "despesas_avulsas" / "fila.json"


def obter_pasta_comprovantes() -> Path:
    """Retorna o diretório onde os comprovantes (fotos, PDFs, áudios) são salvos."""
    pasta = _obter_base_data() / "despesas_avulsas" / "comprovantes"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def carregar_fila(caminho_fila: Path | str | None = None) -> list[ItemFilaDespesa]:
    """Lê todos os itens persistidos na fila local."""
    p = Path(caminho_fila) if caminho_fila else obter_caminho_fila()
    if not p.is_file():
        return []
    try:
        conteudo = p.read_text(encoding="utf-8")
        if not conteudo.strip():
            return []
        dados = json.loads(conteudo)
        return [ItemFilaDespesa.model_validate(it) for it in dados]
    except Exception as exc:
        logger.warning("Falha ao carregar fila %s: %s", p, exc)
        return []


def salvar_fila(
    itens: Sequence[ItemFilaDespesa],
    caminho_fila: Path | str | None = None,
) -> Path:
    """Salva a lista completa de itens na fila local de forma atômica."""
    p = Path(caminho_fila) if caminho_fila else obter_caminho_fila()
    p.parent.mkdir(parents=True, exist_ok=True)
    dados = [it.model_dump(mode="json") for it in itens]

    temp_path = p.with_suffix(".tmp")
    temp_path.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(p)
    return p


def adicionar_item_fila(
    item: ItemFilaDespesa,
    caminho_fila: Path | str | None = None,
) -> ItemFilaDespesa:
    """Adiciona ou atualiza um item na fila local."""
    itens = carregar_fila(caminho_fila)
    # Substitui se já existe mesmo ID
    idx = next((i for i, x in enumerate(itens) if x.id == item.id), None)
    if idx is not None:
        itens[idx] = item
    else:
        itens.append(item)
    salvar_fila(itens, caminho_fila)
    return item


def buscar_item_por_id(
    item_id: str,
    caminho_fila: Path | str | None = None,
) -> ItemFilaDespesa | None:
    """Busca item por ID único."""
    itens = carregar_fila(caminho_fila)
    for it in itens:
        if it.id == item_id:
            return it
    return None


def buscar_item_por_msg_id(
    telegram_message_id: int,
    caminho_fila: Path | str | None = None,
) -> ItemFilaDespesa | None:
    """Busca o item que foi gerado por um message_id específico do Telegram."""
    itens = carregar_fila(caminho_fila)
    for it in reversed(itens):
        if it.telegram_message_id == telegram_message_id:
            return it
    return None


def salvar_arquivo_comprovante(
    nome_base: str,
    conteudo: bytes,
    extensao: str,
    pasta_dest: Path | str | None = None,
) -> Path:
    """Salva foto, PDF ou áudio do comprovante no disco."""
    pasta = Path(pasta_dest) if pasta_dest else obter_pasta_comprovantes()
    pasta.mkdir(parents=True, exist_ok=True)
    ext = extensao if extensao.startswith(".") else f".{extensao}"
    caminho = pasta / f"{nome_base}{ext}"
    caminho.write_bytes(conteudo)
    return caminho
