"""Orquestrador para processamento de comprovantes e áudios enviados pelo Telegram (Parte B / EXPENSE-01).

Fluxo:
1. Calcula SHA-256 do arquivo original e impede documento duplicado;
2. Extrai campos com o Gemini (validado com Pydantic);
3. Casa com débitos dos extratos OFX da unidade com proteção de FITID e conta bancária;
4. Identifica empresa exclusivamente por evidência confiável (sem fallback cego);
5. Sugere Plano de Contas e Centro de Custo;
6. Aplica máquina de estados estrita (ADR-003: nenhum item nasce aprovado);
7. Persiste na fila local data/despesas_avulsas/fila.json;
8. Gera mensagem de resposta formatada para o diretor.
Nada é gravado no webPosto.
"""

from __future__ import annotations

import hashlib
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
    buscar_item_por_sha256,
    carregar_fila,
    obter_caminho_fila,
    salvar_arquivo_comprovante,
    transicionar_status,
)
from ..domain.comprovante import (
    DadosComprovante,
    ItemFilaDespesa,
    OperacaoFinanceira,
    StatusDespesa,
    TransicaoFila,
)
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
    alerta_duplicidade: str | None = None,
) -> str:
    """Monta a resposta amigável e concisa para o Telegram (Item 6 da RN-ERP-003)."""
    valor_txt = formatar_valor_br(comprovante.valor)
    favorecido_txt = comprovante.favorecido or "Favorecido não informado"
    data_txt = (
        comprovante.data.strftime("%d/%m/%Y") if comprovante.data else "Data não identificada"
    )

    b_limpo = banco_nome.strip() if banco_nome else ""
    if b_limpo.upper() == "PAGBANK":
        b_limpo = "PagBank"
    elif b_limpo.upper() in ("BB", "BANCO DO BRASIL"):
        b_limpo = "BB"

    apelido = unidade_apelido.strip() if unidade_apelido else "INDEFINIDA"
    if apelido == "INDEFINIDA":
        banco_unidade = f"{b_limpo} (empresa a definir)".strip() if b_limpo else "Empresa a definir"
    else:
        banco_unidade = f"{b_limpo} {apelido}".strip() if b_limpo else apelido

    alerta_txt = f" ⚠️ {alerta_duplicidade}" if alerta_duplicidade else ""

    if status in ("pronto para lançar", StatusDespesa.AGUARDANDO_APROVACAO.value):
        return (
            f"Recebi: {valor_txt} · {favorecido_txt} · {data_txt} · {banco_unidade} · "
            f"sugestão: {sugestao_plano_nome} ({sugestao_plano_codigo}). Vou deixar pronto para lançar.{alerta_txt}"
        )
    elif status in ("a classificar", StatusDespesa.AGUARDANDO_REVISAO.value):
        if apelido == "INDEFINIDA":
            return (
                f"Recebi: {valor_txt} · {favorecido_txt} · {data_txt} · Empresa não identificada · "
                f"Aguardando revisão da empresa e categoria.{alerta_txt}"
            )
        if sugestao_plano_nome == "A CLASSIFICAR" or not sugestao_plano_codigo:
            return (
                f"Recebi: {valor_txt} · {favorecido_txt} · {data_txt} · {banco_unidade} · "
                f"a classificar. Vou deixar na fila para definir a categoria.{alerta_txt}"
            )
        return (
            f"Recebi: {valor_txt} · {favorecido_txt} · {data_txt} · {banco_unidade} · "
            f"sugestão: {sugestao_plano_nome} ({sugestao_plano_codigo}). Aguardando extrato bancário para casar o débito.{alerta_txt}"
        )
    else:  # "sem extrato ainda"
        sug_txt = (
            f"sugestão: {sugestao_plano_nome} ({sugestao_plano_codigo}). "
            if sugestao_plano_codigo
            else ""
        )
        return (
            f"Recebi: {valor_txt} · {favorecido_txt} · {data_txt} · {banco_unidade} · "
            f"{sug_txt}Aguardando extrato bancário para casar o débito.{alerta_txt}"
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
    titulos_abertos: Sequence[Any] | None = None,
    gemini_extractor: GeminiExtractor | None = None,
    caminho_fila: Path | str | None = None,
    pasta_comprovantes: Path | str | None = None,
) -> ItemFilaDespesa:
    """Processa um comprovante (foto/PDF/áudio) ou resposta e registra na fila local."""
    extractor = gemini_extractor or GeminiExtractor()
    item_id = uuid.uuid4().hex[:12]
    agora_iso = agora().isoformat()

    # 1. Se for resposta a um comprovante anterior
    item_existente = None
    if telegram_reply_to_message_id:
        item_existente = buscar_item_por_msg_id(telegram_reply_to_message_id, caminho_fila)

    texto_complementar = texto.strip()

    # Se for apenas texto sem arquivo e responde a um item existente
    if not arquivo_bytes and not audio_bytes and texto_complementar and item_existente:
        # Atualiza o item existente com o texto ou classificação do diretor
        item_existente.audio_ou_texto_complementar = (
            f"{item_existente.audio_ou_texto_complementar} {texto_complementar}"
        ).strip()
        pl_cod, pl_nome, cc_cod, cc_nome, origem = sugerir_classificacao(
            item_existente.audio_ou_texto_complementar,
            item_existente.comprovante.favorecido,
        )
        item_existente.sugestao_plano_codigo = pl_cod
        item_existente.sugestao_plano_nome = pl_nome
        item_existente.sugestao_centro_codigo = cc_cod
        item_existente.sugestao_centro_nome = cc_nome
        item_existente.origem_sugestao = origem

        # Incrementa versão e invalida hashes/aprovações antigas
        item_existente.versao += 1
        item_existente.hash_conteudo = item_existente.calcular_hash_conteudo()

        # Avalia nova transição
        if (
            item_existente.debito_casado_fitid
            and pl_nome != "A CLASSIFICAR"
            and item_existente.unidade_codigo is not None
            and item_existente.unidade_nome != "EMPRESA_INDEFINIDA"
            and not item_existente.alerta_duplicidade
        ):
            transicionar_status(
                item_existente,
                StatusDespesa.AGUARDANDO_APROVACAO.value,
                motivo="Classificação fornecida pelo diretor; pronto para aprovação",
                origem="diretor_telegram",
                caminho_fila=caminho_fila,
            )
        else:
            transicionar_status(
                item_existente,
                StatusDespesa.AGUARDANDO_REVISAO.value,
                motivo="Texto complementar recebido, mas ainda pendente de revisão",
                origem="diretor_telegram",
                caminho_fila=caminho_fila,
            )

        resp = montar_resposta_bot(
            comprovante=item_existente.comprovante,
            unidade_apelido=item_existente.unidade_apelido,
            banco_nome=item_existente.debito_casado_banco
            or item_existente.comprovante.banco_origem,
            sugestao_plano_nome=pl_nome,
            sugestao_plano_codigo=pl_cod,
            status=item_existente.status,
            alerta_duplicidade=item_existente.alerta_duplicidade,
        )
        item_existente.resposta_bot = resp
        adicionar_item_fila(item_existente, caminho_fila)
        return item_existente

    # 2. Cálculo do SHA-256 e Verificação de Documento Duplicado (Anti-duplicidade de Comprovante)
    arquivo_sha256 = None
    if arquivo_bytes:
        arquivo_sha256 = hashlib.sha256(arquivo_bytes).hexdigest()
    elif audio_bytes:
        arquivo_sha256 = hashlib.sha256(audio_bytes).hexdigest()

    if arquivo_sha256:
        doc_duplicado = buscar_item_por_sha256(arquivo_sha256, caminho_fila)
        if doc_duplicado:
            logger.info(
                "Comprovante idêntico detectado (SHA256=%s, id=%s)",
                arquivo_sha256,
                doc_duplicado.id,
            )
            doc_duplicado.duplicado_de_id = doc_duplicado.id
            doc_duplicado.motivo_duplicidade = (
                f"Documento idêntico já recebido anteriormente (ID: {doc_duplicado.id})"
            )
            doc_duplicado.resposta_bot = (
                f"Comprovante já recebido anteriormente (ID: {doc_duplicado.id}, status: {doc_duplicado.status}). "
                f"O arquivo é idêntico e não foi duplicado na fila."
            )
            return doc_duplicado

    caminho_salvo = None
    arquivo_tipo = "texto"
    comprovante = DadosComprovante()

    # 3. Se veio arquivo (Foto ou PDF)
    if arquivo_bytes and mime_type:
        ext = Path(nome_arquivo or "comprovante").suffix or (
            ".pdf" if "pdf" in mime_type else ".jpg"
        )
        nome_disco = f"comp_{item_id}"
        salvo = salvar_arquivo_comprovante(
            nome_disco, arquivo_bytes, ext, pasta_dest=pasta_comprovantes
        )
        caminho_salvo = str(salvo)
        arquivo_tipo = "pdf" if "pdf" in mime_type else "imagem"

        comprovante = await extractor.extrair_comprovante(
            conteudo_bytes=arquivo_bytes,
            mime_type=mime_type,
            texto_adicional=texto_complementar,
        )

    # 4. Se veio áudio (mensagem de voz do diretor)
    if audio_bytes:
        nome_disco = f"audio_{item_id}"
        salvo_audio = salvar_arquivo_comprovante(
            nome_disco, audio_bytes, ".ogg", pasta_dest=pasta_comprovantes
        )
        if not caminho_salvo:
            caminho_salvo = str(salvo_audio)
            arquivo_tipo = "audio"

        transcricao, dados_audio = await extractor.extrair_audio(audio_bytes, mime_type="audio/ogg")
        texto_complementar = (f"{texto_complementar} {transcricao}").strip()

        if not comprovante.valor and dados_audio.valor:
            comprovante.valor = dados_audio.valor
        if not comprovante.favorecido and dados_audio.favorecido:
            comprovante.favorecido = dados_audio.favorecido
        if not comprovante.data and dados_audio.data:
            comprovante.data = dados_audio.data
        comprovante.observacao_diretor = (f"{comprovante.observacao_diretor} {transcricao}").strip()

    # 5. Carregar extratos para conciliação
    extratos_lista: list[ExtratoBancario] = []
    if extratos is not None:
        extratos_lista = list(extratos)
    else:
        base_extratos = Path("C:/Projetos/LOGOS/extratos")
        if base_extratos.is_dir():
            rotas = list(base_extratos.glob("extrato_bb_*.ofx")) + list(
                (base_extratos / "PAGBANK").glob("*.ofx")
            )
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

    # 6. Casamento com débitos dos extratos com PROTEÇÃO DE FITID E CONTA BANCÁRIA
    itens_atuais_fila = carregar_fila(caminho_fila)
    transacoes_em_uso: set[tuple[str, str, str]] = set()
    for it in itens_atuais_fila:
        if it.status_canonico != StatusDespesa.REJEITADO.value and it.chave_transacao_bancaria:
            transacoes_em_uso.add(it.chave_transacao_bancaria)

    debito_match: LancamentoBancario | None = None
    extrato_match: ExtratoBancario | None = None

    if comprovante.valor is not None:
        val_comp = comprovante.valor

        for ext in extratos_lista:
            # Proteção: conta sem identificação confiável não vincula automaticamente
            conta_sufixo_ext = (ext.conta_sufixo or "").strip()
            if not conta_sufixo_ext:
                continue

            for l in ext.lancamentos:
                if not l.eh_debito:
                    continue
                fitid_norm = (l.fitid or "").strip()
                if not fitid_norm:
                    continue

                # Proteção: transação já consumida por outro comprovante da mesma conta
                chave_tx = (ext.banco.upper().strip(), conta_sufixo_ext, fitid_norm)
                if chave_tx in transacoes_em_uso:
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

    # 7. Resolução da Unidade (SEM FALLBACK PARA O DOZE)
    unidade_encontrada: Unidade | None = None

    # Evidência confiável 1: conta bancária configurada na unidade
    if extrato_match and extrato_match.conta_sufixo:
        for u in unidades_map.values():
            for ce in getattr(u, "contas_extrato", ()):
                if (
                    ce.banco.upper() == extrato_match.banco.upper()
                    and ce.conta_sufixo in extrato_match.conta_sufixo
                ):
                    unidade_encontrada = u
                    break
            if unidade_encontrada:
                break

    # Evidência confiável 2: menção inequívoca e exclusiva no texto complementar do diretor
    if not unidade_encontrada and texto_complementar:
        t_norm = normalizar_texto(texto_complementar)
        candidatas = [
            u
            for u in unidades_map.values()
            if (u.apelido and normalizar_texto(u.apelido) in t_norm)
            or (u.nome and normalizar_texto(u.nome) in t_norm)
        ]
        if len(candidatas) == 1:
            unidade_encontrada = candidatas[0]

    # SE NÃO HOUVER EVIDÊNCIA CONFIÁVEL: NÃO APLICAR FALLBACK PARA O DOZE!
    # Posto Real (5558 / codWeb 7) está fora do escopo do Expense Hunter (CNPJ desativado)
    if unidade_encontrada and getattr(unidade_encontrada, "empresa_codigo", None) in (5558, 7):
        unidade_encontrada = None

    if unidade_encontrada:
        unidade_cod = unidade_encontrada.empresa_codigo
        unidade_nome = unidade_encontrada.nome
        unidade_apelido = unidade_encontrada.apelido
    else:
        unidade_cod = None
        unidade_nome = "EMPRESA_INDEFINIDA"
        unidade_apelido = "INDEFINIDA"

    # 8. Sugestão de Plano de Contas e Centro de Custo
    pl_cod, pl_nome, cc_cod, cc_nome, origem_sug = sugerir_classificacao(
        texto=f"{texto_complementar} {comprovante.descricao}",
        favorecido=comprovante.favorecido,
    )

    # 9. Verificação de Possível Duplicidade de Despesa (arquivos diferentes, mesma despesa)
    alerta_duplicidade = None
    if comprovante.valor is not None:
        for it in itens_atuais_fila:
            if it.status_canonico == StatusDespesa.REJEITADO.value:
                continue
            if it.comprovante.valor == comprovante.valor:
                data_bate = False
                if comprovante.data and it.comprovante.data:
                    data_bate = abs((it.comprovante.data - comprovante.data).days) <= 2
                fav_bate = bool(
                    comprovante.favorecido
                    and it.comprovante.favorecido
                    and texto_confere(comprovante.favorecido, it.comprovante.favorecido)
                )
                fitid_bate = bool(
                    debito_match
                    and debito_match.fitid
                    and it.debito_casado_fitid == debito_match.fitid
                )
                if data_bate and (fav_bate or fitid_bate):
                    alerta_duplicidade = f"Possível despesa duplicada: coincide com item {it.id} (R$ {comprovante.valor})."
                    break

    # Determinação da Operação Financeira e Conta (EXPENSE-02)
    titulo_match = None
    if titulos_abertos and comprovante.valor:
        for tit in titulos_abertos:
            tit_val = getattr(tit, "valor", None) or getattr(tit, "valor_aberto", None)
            if tit_val is not None and abs(Decimal(str(tit_val))) == abs(comprovante.valor):
                titulo_match = tit
                break

    if alerta_duplicidade:
        operacao_fin = OperacaoFinanceira.POSSIVEL_DUPLICIDADE.value
    elif titulo_match is not None:
        operacao_fin = OperacaoFinanceira.TITULO_EXISTENTE.value
    elif debito_match is not None:
        operacao_fin = OperacaoFinanceira.DESPESA_JA_PAGA.value
    elif comprovante.tipo_comprovante in ("PIX", "TED", "TRANSFERENCIA", "PAGAMENTO"):
        operacao_fin = OperacaoFinanceira.DESPESA_JA_PAGA.value
    elif comprovante.tipo_comprovante in (
        "Boleto",
        "BOLETO",
        "NOTA_FISCAL",
        "NF",
        "FATURA",
        "DUPLICATA",
    ):
        operacao_fin = OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value
    elif not comprovante.valor or unidade_cod is None:
        operacao_fin = OperacaoFinanceira.INDETERMINADO.value
    else:
        operacao_fin = OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value

    conta_cod = None
    conta_nome = ""
    if extrato_match:
        conta_cod = getattr(extrato_match, "cd_conta", None)
        conta_nome = f"{extrato_match.banco} {extrato_match.conta_sufixo or ''}".strip()
    elif comprovante.banco_origem:
        conta_nome = comprovante.banco_origem

    # Criação do item no estado inicial RECEBIDO com histórico de auditoria
    item = ItemFilaDespesa(
        id=item_id,
        telegram_message_id=telegram_message_id,
        telegram_chat_id=telegram_chat_id,
        criado_em=agora_iso,
        arquivo_comprovante=caminho_salvo,
        arquivo_tipo=arquivo_tipo,
        arquivo_sha256=arquivo_sha256,
        comprovante=comprovante,
        audio_ou_texto_complementar=texto_complementar,
        debito_casado_fitid=debito_match.fitid if debito_match else None,
        debito_casado_banco=extrato_match.banco.upper() if extrato_match else None,
        debito_casado_conta=extrato_match.conta_sufixo if extrato_match else None,
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
        operacao_financeira=operacao_fin,
        conta_financeira_codigo=conta_cod,
        conta_financeira_nome=conta_nome,
        numero_documento=comprovante.descricao or "",
        status=StatusDespesa.RECEBIDO.value,
        alerta_duplicidade=alerta_duplicidade,
        historico_transicoes=[
            TransicaoFila(
                de_status="",
                para_status=StatusDespesa.RECEBIDO.value,
                motivo="Comprovante recebido para processamento",
                origem="sistema",
                timestamp=agora_iso,
            )
        ],
    )
    item.hash_conteudo = item.calcular_hash_conteudo()

    # 10. Transição de Estado Explícita e Validação das Regras de Negócio
    if unidade_cod is None or unidade_nome == "EMPRESA_INDEFINIDA":
        transicionar_status(
            item,
            StatusDespesa.AGUARDANDO_REVISAO.value,
            motivo="Empresa não identificada; necessária revisão humana",
            origem="sistema",
        )
    elif alerta_duplicidade:
        transicionar_status(
            item,
            StatusDespesa.AGUARDANDO_REVISAO.value,
            motivo=f"Alerta de duplicidade detectado: {alerta_duplicidade}",
            origem="sistema",
        )
    elif debito_match is None and operacao_fin == OperacaoFinanceira.DESPESA_JA_PAGA.value:
        transicionar_status(
            item,
            StatusDespesa.AGUARDANDO_REVISAO.value,
            motivo="Aguardando extrato bancário para casar o débito",
            origem="sistema",
        )
    elif pl_nome == "A CLASSIFICAR" or pl_cod is None:
        transicionar_status(
            item,
            StatusDespesa.AGUARDANDO_REVISAO.value,
            motivo="Plano de contas pendente de classificação",
            origem="sistema",
        )
    elif item.pode_ser_aprovado:
        transicionar_status(
            item,
            StatusDespesa.AGUARDANDO_APROVACAO.value,
            motivo="Dados completos e conciliados; aguardando aprovação humana",
            origem="sistema",
        )
    else:
        transicionar_status(
            item,
            StatusDespesa.AGUARDANDO_REVISAO.value,
            motivo="Pendência identificada na proposta de despesa",
            origem="sistema",
        )

    # 11. Montagem da resposta para o Telegram
    resposta_txt = montar_resposta_bot(
        comprovante=comprovante,
        unidade_apelido=unidade_apelido,
        banco_nome=extrato_match.banco if extrato_match else comprovante.banco_origem,
        sugestao_plano_nome=pl_nome,
        sugestao_plano_codigo=pl_cod,
        status=item.status,
        alerta_duplicidade=alerta_duplicidade,
    )
    item.resposta_bot = resposta_txt

    # Persiste na fila local
    adicionar_item_fila(item, caminho_fila)
    return item
