"""Gerenciamento da fila local de despesas avulsas (data/despesas_avulsas/fila.json)."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Sequence

from ..domain.comprovante import ItemFilaDespesa, StatusDespesa, TransicaoFila
from ..domain.tempo import agora

logger = logging.getLogger(__name__)


class TransicaoInvalidaErro(ValueError):
    """Erro lançado quando uma transição de estado da fila de despesas for inválida."""

    pass


# Tabela de transições permitidas (ADR-003 / EXPENSE-01)
TRANSICOES_VALIDAS: dict[str, set[str]] = {
    StatusDespesa.RECEBIDO.value: {
        StatusDespesa.AGUARDANDO_REVISAO.value,
        StatusDespesa.AGUARDANDO_APROVACAO.value,
        StatusDespesa.REJEITADO.value,
    },
    StatusDespesa.AGUARDANDO_REVISAO.value: {
        StatusDespesa.AGUARDANDO_APROVACAO.value,
        StatusDespesa.REJEITADO.value,
    },
    StatusDespesa.AGUARDANDO_APROVACAO.value: {
        StatusDespesa.AGUARDANDO_REVISAO.value,
        StatusDespesa.APROVADO.value,
        StatusDespesa.REJEITADO.value,
    },
    StatusDespesa.APROVADO.value: {
        StatusDespesa.AGUARDANDO_REVISAO.value,
        StatusDespesa.LANCAMENTO_SOLICITADO.value,
        StatusDespesa.REJEITADO.value,
    },
    StatusDespesa.LANCAMENTO_SOLICITADO.value: {
        StatusDespesa.LANCADO_ERP.value,
        StatusDespesa.FALHA.value,
        StatusDespesa.RESULTADO_DESCONHECIDO.value,
    },
    StatusDespesa.FALHA.value: {
        StatusDespesa.AGUARDANDO_REVISAO.value,
        StatusDespesa.REJEITADO.value,
    },
    StatusDespesa.RESULTADO_DESCONHECIDO.value: {
        StatusDespesa.AGUARDANDO_REVISAO.value,
        StatusDespesa.REJEITADO.value,
    },
    StatusDespesa.REJEITADO.value: {
        StatusDespesa.AGUARDANDO_REVISAO.value,  # Reabertura mediante revisão
    },
    StatusDespesa.LANCADO_ERP.value: set(),  # Estado terminal
}


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


def buscar_item_por_sha256(
    sha256: str,
    caminho_fila: Path | str | None = None,
) -> ItemFilaDespesa | None:
    """Busca comprovante ativo com o mesmo hash SHA-256 do arquivo original."""
    if not sha256:
        return None
    itens = carregar_fila(caminho_fila)
    for it in itens:
        if it.arquivo_sha256 == sha256 and it.status_canonico != StatusDespesa.REJEITADO.value:
            return it
    return None


def buscar_item_por_transacao_bancaria(
    banco: str,
    conta: str,
    fitid: str,
    caminho_fila: Path | str | None = None,
    ignorar_item_id: str | None = None,
) -> ItemFilaDespesa | None:
    """Verifica se uma transação bancária (banco + conta + fitid) já foi usada na fila."""
    if not banco or not conta or not fitid:
        return None
    b_norm = banco.upper().strip()
    c_norm = conta.strip()
    f_norm = fitid.strip()

    itens = carregar_fila(caminho_fila)
    for it in itens:
        if ignorar_item_id and it.id == ignorar_item_id:
            continue
        if it.status_canonico == StatusDespesa.REJEITADO.value:
            continue
        if it.debito_casado_banco and it.debito_casado_conta and it.debito_casado_fitid:
            if (
                it.debito_casado_banco.upper().strip() == b_norm
                and it.debito_casado_conta.strip() == c_norm
                and it.debito_casado_fitid.strip() == f_norm
            ):
                return it
    return None


def buscar_possiveis_duplicatas(
    item: ItemFilaDespesa,
    caminho_fila: Path | str | None = None,
) -> list[ItemFilaDespesa]:
    """Identifica despesas parecidas (mesmo valor e data próxima) de arquivos diferentes."""
    if item.comprovante.valor is None or item.comprovante.data is None:
        return []

    duplicatas: list[ItemFilaDespesa] = []
    itens = carregar_fila(caminho_fila)
    for it in itens:
        if it.id == item.id:
            continue
        if it.status_canonico == StatusDespesa.REJEITADO.value:
            continue
        if it.comprovante.valor == item.comprovante.valor:
            if it.comprovante.data and abs((it.comprovante.data - item.comprovante.data).days) <= 2:
                # Se arquivo for diferente, mas dados são idênticos
                if not item.arquivo_sha256 or it.arquivo_sha256 != item.arquivo_sha256:
                    duplicatas.append(it)
    return duplicatas


def transicionar_status(
    item: ItemFilaDespesa,
    novo_status: str,
    motivo: str,
    origem: str = "sistema",
    usuario: str | None = None,
    caminho_fila: Path | str | None = None,
) -> ItemFilaDespesa:
    """Executa transição explícita e validada de estado na fila, registrando auditoria."""
    status_atual = item.status_canonico

    # Validações de máquina de estados
    destinos_permitidos = TRANSICOES_VALIDAS.get(status_atual, set())
    if novo_status not in destinos_permitidos:
        raise TransicaoInvalidaErro(
            f"Transição proibida: de '{status_atual}' para '{novo_status}'. "
            f"Destinos permitidos: {sorted(list(destinos_permitidos))}."
        )

    # Regras de segurança de transição
    if novo_status == StatusDespesa.AGUARDANDO_APROVACAO.value:
        if item.unidade_codigo is None or item.unidade_nome == "EMPRESA_INDEFINIDA":
            raise TransicaoInvalidaErro(
                "Empresa indefinida não pode ir para aguardando_aprovacao. Exige revisão humana."
            )
        if item.alerta_duplicidade:
            raise TransicaoInvalidaErro(
                f"Item com alerta de duplicidade ({item.alerta_duplicidade}) exige revisão antes de aprovação."
            )

    # Nenhuma aprovação automática pelo sistema é autorizada
    if novo_status in (
        StatusDespesa.APROVADO.value,
        StatusDespesa.LANCAMENTO_SOLICITADO.value,
        StatusDespesa.LANCADO_ERP.value,
    ):
        if origem == "sistema" or not usuario:
            raise TransicaoInvalidaErro(
                "Aprovação automática ou de escrita pelo sistema é proibida. Exige autorização humana expressa."
            )

    agora_iso = agora().isoformat()
    if novo_status == StatusDespesa.APROVADO.value:
        item.aprovado_por = usuario
        item.aprovado_em = agora_iso
        item.aprovado_versao = item.versao
        item.aprovado_hash = item.calcular_hash_conteudo()
        item.aprovado_operacao = item.operacao_financeira
    elif novo_status == StatusDespesa.REJEITADO.value:
        item.motivo_rejeicao = motivo
    registro_transicao = TransicaoFila(
        de_status=status_atual,
        para_status=novo_status,
        motivo=motivo,
        origem=origem,
        timestamp=agora_iso,
        usuario=usuario,
    )
    item.historico_transicoes.append(registro_transicao)
    item.status = novo_status

    if caminho_fila:
        adicionar_item_fila(item, caminho_fila)

    return item


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
