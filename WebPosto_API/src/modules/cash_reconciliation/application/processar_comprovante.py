"""Orquestrador para processamento de comprovantes e áudios enviados pelo Telegram (Parte B).

Fluxo:
1. Salva foto, PDF ou áudio em data/despesas_avulsas/comprovantes/;
2. Extrai campos com o Gemini (validado com Pydantic);
3. Casa com débitos dos extratos OFX da unidade (reaproveitando Parte A);
4. Sugere Plano de Contas e Centro de Custo;
5. Persiste na fila local data/despesas_avulsas/fila.json;
6. Gera mensagem de resposta formatada para o diretor.
Nada é gravado no webPosto.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from ..adapters.extrato_reader import ExtratoBancario, LancamentoBancario, ler_arquivo
from ..adapters.gemini_comprovantes import GeminiExtractor
from ..application.despesas_sem_lancamento import (
    extrair_favorecido,
    normalizar_texto,
    resolver_caminhos_extratos_padrao,
    texto_confere,
)
from ..application.fila_despesas import (
    adicionar_item_fila,
    buscar_item_por_msg_id,
    obter_caminho_fila,
    salvar_arquivo_comprovante,
)
from ..config import carregar_unidades
from ..domain.comprovante import DadosComprovante, ItemFilaDespesa
from ..domain.models import Unidade
from ..domain.tempo import agora, hoje

logger = logging.getLogger(__name__)


def formatar_valor_br(val: Decimal | None) -> str:
    """Formata valor decimal no formato monetário R$ 1.234,56."""
    if val is None:
        return "Valor não informado"
    s = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def sugerir_classificacao(
    texto: str,
    favorecido: str = "",
) -> tuple[int | None, str, int | None, str, str]:
    """Sugere plano de contas e centro de custo a partir de palavras-chave ou regras."""
    t_norm = normalizar_texto(f"{texto} {favorecido}")

    # Centro de custo padrão: PISTA (7295)
    cc_cod = 7295
    cc_nome = "PISTA"

    # Regras aprendidas e apelidos da rede
    if "PEDREIRO" in t_norm:
        return 198595, "PEDREIRO", cc_cod, cc_nome, "palavra-chave 'pedreiro'"
    if "PISO" in t_norm:
        return 194968, "MANUTENCAO PISO/CANALETAS", cc_cod, cc_nome, "palavra-chave 'piso'"
    if "FARDA" in t_norm:
        return 29057, "FARDAS E UNIFORMES", cc_cod, cc_nome, "palavra-chave 'farda'"
    if "DARF" in t_norm or "RECEITA FEDERAL" in t_norm:
        return 29128, "H07 - DARF", cc_cod, cc_nome, "imposto federal DARF"
    if "FGTS" in t_norm or "CEF MATRIZ" in t_norm:
        return 29086, "ENCARGOS SOCIAIS / FGTS", cc_cod, cc_nome, "guia CEF Matriz / FGTS"

    return None, "A CLASSIFICAR", cc_cod, cc_nome, "a classificar"


def montar_resposta_bot(
    comprovante: DadosComprovante,
    unidade_apelido: str,
    banco_nome: str,
    sugestao_plano_nome: str,
    sugestao_plano_codigo: int | None,
    status: str,
) -> str:
    """Monta a resposta amigável e concisa para o Telegram (Item 6 da RN-ERP-003)."""
    valor_txt = formatar_valor_br(comprovante.valor)
    favorecido_txt = comprovante.favorecido or "Favorecido não informado"
    data_txt = comprovante.data.strftime("%d/%m/%Y") if comprovante.data else "Data não identificada"

    # Nome do banco com unidade, ex.: "PagBank Doze" ou "BB Doze"
    b_limpo = banco_nome.strip() if banco_nome else ""
    if b_limpo.upper() == "PAGBANK":
        b_limpo = "PagBank"
    elif b_limpo.upper() in ("BB", "BANCO DO BRASIL"):
        b_limpo = "BB"

    apelido = unidade_apelido.strip() if unidade_apelido else "Doze"
    banco_unidade = f"{b_limpo} {apelido}".strip() if b_limpo else apelido

    if status == "pronto para lançar":
        return (
            f"Recebi: {valor_txt} · {favorecido_txt} · {data_txt} · {banco_unidade} · "
            f"sugestão: {sugestao_plano_nome} ({sugestao_plano_codigo}). Vou deixar pronto para lançar."
        )
    elif status == "a classificar":
        return (
            f"Recebi: {valor_txt} · {favorecido_txt} · {data_txt} · {banco_unidade} · "
            f"a classificar. Vou deixar na fila para definir a categoria."
        )
    else:  # "sem extrato ainda"
        sug_txt = (
            f"sugestão: {sugestao_plano_nome} ({sugestao_plano_codigo}). "
            if sugestao_plano_codigo else ""
        )
        return (
            f"Recebi: {valor_txt} · {favorecido_txt} · {data_txt} · {banco_unidade} · "
            f"{sug_txt}Aguardando extrato bancário para casar o débito."
        )


async def processar_comprovante_recebido(
    *,
    arquivo_bytes: bytes | None = None,
    nome_arquivo: str | None = None,
    mime_type: str | None = None,
    texto: str = "",
    audio_bytes: bytes | None = None,
    telegram_message_id: int | None = None,
    telegram_reply_to_message_id: int | None = None,
    telegram_chat_id: str | None = None,
    extratos: Sequence[ExtratoBancario] | None = None,
    unidades: Sequence[Unidade] | None = None,
    gemini_extractor: GeminiExtractor | None = None,
    caminho_fila: Path | str | None = None,
    pasta_comprovantes: Path | str | None = None,
) -> ItemFilaDespesa:
    """Processa um comprovante (foto/PDF/áudio) ou resposta e registra na fila local."""
    extractor = gemini_extractor or GeminiExtractor()
    item_id = uuid.uuid4().hex[:12]
    agora_iso = agora().isoformat()

    # Se for resposta a um comprovante anterior
    item_existente = None
    if telegram_reply_to_message_id:
        item_existente = buscar_item_por_msg_id(telegram_reply_to_message_id, caminho_fila)

    caminho_salvo = None
    arquivo_tipo = "texto"
    comprovante = DadosComprovante()
    texto_complementar = texto.strip()

    # 1. Se veio arquivo (Foto ou PDF)
    if arquivo_bytes and mime_type:
        ext = Path(nome_arquivo or "comprovante").suffix or (".pdf" if "pdf" in mime_type else ".jpg")
        nome_disco = f"comp_{item_id}"
        salvo = salvar_arquivo_comprovante(nome_disco, arquivo_bytes, ext, pasta_dest=pasta_comprovantes)
        caminho_salvo = str(salvo)
        arquivo_tipo = "pdf" if "pdf" in mime_type else "imagem"

        comprovante = await extractor.extrair_comprovante(
            conteudo_bytes=arquivo_bytes,
            mime_type=mime_type,
            texto_adicional=texto_complementar,
        )

    # 2. Se veio áudio (mensagem de voz do diretor)
    if audio_bytes:
        nome_disco = f"audio_{item_id}"
        salvo_audio = salvar_arquivo_comprovante(nome_disco, audio_bytes, ".ogg", pasta_dest=pasta_comprovantes)
        if not caminho_salvo:
            caminho_salvo = str(salvo_audio)
            arquivo_tipo = "audio"

        transcricao, dados_audio = await extractor.extrair_audio(audio_bytes, mime_type="audio/ogg")
        texto_complementar = (f"{texto_complementar} {transcricao}").strip()

        # Se não tínhamos dados do comprovante em arquivo, preenche com os do áudio
        if not comprovante.valor and dados_audio.valor:
            comprovante.valor = dados_audio.valor
        if not comprovante.favorecido and dados_audio.favorecido:
            comprovante.favorecido = dados_audio.favorecido
        if not comprovante.data and dados_audio.data:
            comprovante.data = dados_audio.data
        comprovante.observacao_diretor = (
            f"{comprovante.observacao_diretor} {transcricao}"
        ).strip()

    # Se for apenas texto sem arquivo
    if not arquivo_bytes and not audio_bytes and texto_complementar:
        if item_existente:
            # Atualiza o item existente com o texto ou classificação do diretor
            item_existente.audio_ou_texto_complementar = (
                f"{item_existente.audio_ou_texto_complementar} {texto_complementar}"
            ).strip()
            # Reclassifica com base no novo texto
            pl_cod, pl_nome, cc_cod, cc_nome, origem = sugerir_classificacao(
                item_existente.audio_ou_texto_complementar,
                item_existente.comprovante.favorecido,
            )
            item_existente.sugestao_plano_codigo = pl_cod
            item_existente.sugestao_plano_nome = pl_nome
            item_existente.sugestao_centro_codigo = cc_cod
            item_existente.sugestao_centro_nome = cc_nome
            item_existente.origem_sugestao = origem
            if item_existente.debito_casado_fitid and pl_nome != "A CLASSIFICAR":
                item_existente.status = "pronto para lançar"
            elif item_existente.debito_casado_fitid:
                item_existente.status = "a classificar"

            resp = montar_resposta_bot(
                comprovante=item_existente.comprovante,
                unidade_apelido=item_existente.unidade_apelido,
                banco_nome=item_existente.debito_casado_banco or item_existente.comprovante.banco_origem,
                sugestao_plano_nome=pl_nome,
                sugestao_plano_codigo=pl_cod,
                status=item_existente.status,
            )
            item_existente.resposta_bot = resp
            adicionar_item_fila(item_existente, caminho_fila)
            return item_existente

    # 3. Carregar extratos para casamento
    extratos_lista: list[ExtratoBancario] = []
    if extratos is not None:
        extratos_lista = list(extratos)
    else:
        # Carrega extratos padrão da pasta local
        base_extratos = Path("C:/Projetos/LOGOS/extratos")
        if base_extratos.is_dir():
            rotas = list(base_extratos.glob("extrato_bb_*.ofx")) + list((base_extratos / "PAGBANK").glob("*.ofx"))
            for r in rotas:
                try:
                    extratos_lista.append(ler_arquivo(r))
                except Exception as exc:
                    logger.warning("Falha ao ler extrato %s: %s", r, exc)

    # Carregar cadastro de unidades
    unidades_map: dict[int, Unidade] = {}
    if unidades is not None:
        unidades_map = {u.empresa_codigo: u for u in unidades}
    else:
        try:
            unidades_map = carregar_unidades()
        except Exception:
            pass

    # 4. Casamento com débitos dos extratos bancários
    debito_match: LancamentoBancario | None = None
    extrato_match: ExtratoBancario | None = None

    if comprovante.valor is not None:
        val_comp = comprovante.valor

        for ext in extratos_lista:
            for l in ext.lancamentos:
                if not l.eh_debito:
                    continue
                v_deb = abs(l.valor)
                # Valor exato ou até +10% de juros/multa
                if val_comp <= v_deb <= (val_comp * Decimal("1.10")):
                    if comprovante.data is not None:
                        if abs((l.data - comprovante.data).days) > 3:
                            continue

                    # Se temos favorecido, confere nome
                    if comprovante.favorecido:
                        if texto_confere(comprovante.favorecido, l.descricao):
                            debito_match = l
                            extrato_match = ext
                            break
                    else:
                        debito_match = l
                        extrato_match = ext
                        break
            if debito_match:
                break

    if debito_match and not comprovante.data:
        comprovante.data = debito_match.data

    # 5. Resolução da Unidade
    unidade_encontrada: Unidade | None = None
    banco_encontrado = extrato_match.banco.upper() if extrato_match else (comprovante.banco_origem or "")

    if extrato_match:
        for u in unidades_map.values():
            for ce in getattr(u, "contas_extrato", ()):
                if ce.banco.upper() == extrato_match.banco.upper() and ce.conta_sufixo in extrato_match.conta_sufixo:
                    unidade_encontrada = u
                    break
            if unidade_encontrada:
                break

    # Fallback de unidade se não identificada pelo extrato
    if not unidade_encontrada:
        # Se comprovante menciona PagBank ou Doze
        if "PAGBANK" in banco_encontrado.upper() or "DOZE" in normalizar_texto(texto_complementar):
            unidade_encontrada = unidades_map.get(74014)
        elif unidades_map:
            unidade_encontrada = next(iter(unidades_map.values()))

    unidade_cod = unidade_encontrada.empresa_codigo if unidade_encontrada else 74014
    unidade_nome = unidade_encontrada.nome if unidade_encontrada else "POSTO DOZE FILIAL II"
    unidade_apelido = unidade_encontrada.apelido if unidade_encontrada else "Doze"

    # 6. Sugestão de Plano de Contas e Centro de Custo
    pl_cod, pl_nome, cc_cod, cc_nome, origem_sug = sugerir_classificacao(
        texto=f"{texto_complementar} {comprovante.descricao}",
        favorecido=comprovante.favorecido,
    )

    # 7. Definição do status
    if debito_match is None:
        status = "sem extrato ainda"
    elif pl_nome == "A CLASSIFICAR":
        status = "a classificar"
    else:
        status = "pronto para lançar"

    # 8. Montagem da resposta para o Telegram
    resposta_txt = montar_resposta_bot(
        comprovante=comprovante,
        unidade_apelido=unidade_apelido,
        banco_nome=extrato_match.banco if extrato_match else comprovante.banco_origem,
        sugestao_plano_nome=pl_nome,
        sugestao_plano_codigo=pl_cod,
        status=status,
    )

    item = ItemFilaDespesa(
        id=item_id,
        telegram_message_id=telegram_message_id,
        telegram_chat_id=telegram_chat_id,
        criado_em=agora_iso,
        arquivo_comprovante=caminho_salvo,
        arquivo_tipo=arquivo_tipo,
        comprovante=comprovante,
        audio_ou_texto_complementar=texto_complementar,
        debito_casado_fitid=debito_match.fitid if debito_match else None,
        debito_casado_banco=extrato_match.banco.upper() if extrato_match else None,
        debito_casado_data=debito_match.data.isoformat() if debito_match else None,
        debito_casado_valor=abs(debito_match.valor) if debito_match else None,
        debito_casado_descricao=debito_match.descricao if debito_match else None,
        unidade_codigo=unidade_cod,
        unidade_nome=unidade_nome,
        unidade_apelido=unidade_apelido,
        sugestao_plano_codigo=pl_cod,
        sugestao_plano_nome=pl_nome,
        sugestao_centro_codigo=cc_cod,
        sugestao_centro_nome=cc_nome,
        sugestao_fornecedor_codigo=None,
        sugestao_fornecedor_nome="",
        origem_sugestao=origem_sug,
        status=status,
        resposta_bot=resposta_txt,
    )

    # Persiste na fila local
    adicionar_item_fila(item, caminho_fila)
    return item
