"""Adaptador de propostas, aprovações e callbacks de despesas via Telegram (EXPENSE-02).

Implementa:
1. Autenticação estrita do usuário (apenas chat e user do diretor autorizado);
2. Tickets curtos e opacos (secrets.token_hex(8));
3. Controle de concorrência e idempotência atômica via SQLite (BEGIN IMMEDIATE);
4. Validação de versão e hash canônico da proposta (rejeita aprovação de versão defasada);
5. Bloqueio de aprovação com pendências (empresa indefinida, duplicidade, a classificar);
6. Fluxo de aprovação com um toque;
7. Fluxo de rejeição auditada;
8. Menu e fluxo de correção com mínima interação;
9. Nenhuma escrita no ERP (mantém status 'aprovado' para futura integração).
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from ..domain.comprovante import (
    ItemFilaDespesa,
    OperacaoFinanceira,
    StatusDespesa,
)
from ..domain.tempo import agora
from ..application.fila_despesas import (
    adicionar_item_fila,
    buscar_item_por_id,
    carregar_fila,
    obter_caminho_fila,
    transicionar_status,
)
from src.shared.notificacao.telegram import API_BASE

logger = logging.getLogger(__name__)

BANCO_PADRAO = (
    Path(__file__).resolve().parents[4] / "data" / "lancamentos_logos" / "telegram.sqlite3"
)

# Unidades autorizadas da rede
UNIDADES_AUTORIZADAS = {
    74014: {"nome": "POSTO DOZE FILIAL II", "apelido": "Doze"},
    11495: {"nome": "POSTO VIP LTDA", "apelido": "VIP"},
    5555: {"nome": "AP CASA CAIADA", "apelido": "Casa Caiada"},
    118508: {"nome": "CONVENIENCIA 24 HORAS", "apelido": "Conv 24h"},
}

# Categorias frequentes pré-configuradas para correção rápida
CATEGORIAS_RAPIDAS = {
    194968: "MANUTENCAO PISO/CANALETAS",
    198595: "PEDREIRO",
    29057: "FARDAS E UNIFORMES",
    29128: "H07 - DARF",
    29086: "ENCARGOS SOCIAIS / FGTS",
}


class DespesaTelegramErro(ValueError):
    """Erro em operações de aprovação e callbacks de despesas no Telegram."""

    pass


def obter_diretores_autorizados(caminho_env: Path | str | None = None) -> tuple[set[str], set[str]]:
    """Retorna conjuntos de (chat_ids_autorizados, user_ids_autorizados)."""
    # 1. Variáveis de ambiente padrão
    chat_ids = set()
    user_ids = set()

    raw_chats = os.getenv("TELEGRAM_CHAT_IDS", "")
    for c in raw_chats.split(","):
        c_clean = c.strip()
        if c_clean:
            chat_ids.add(c_clean)

    dir_chat = os.getenv("TELEGRAM_DIRETOR_CHAT_ID", "").strip()
    dir_user = os.getenv("TELEGRAM_DIRETOR_USER_ID", "").strip()
    if dir_chat:
        chat_ids.add(dir_chat)
    if dir_user:
        user_ids.add(dir_user)

    # Se nenhum user_id específico foi definido, aceita os próprios chat_ids privados
    if not user_ids and chat_ids:
        user_ids.update(chat_ids)

    return chat_ids, user_ids


def conectar_banco(banco: Path | str | None = None) -> sqlite3.Connection:
    """Conecta ao banco SQLite criando tabelas de controle se inexistentes."""
    p = Path(banco) if banco else BANCO_PADRAO
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS propostas_despesas (
            ticket TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            versao INTEGER NOT NULL,
            hash_conteudo TEXT NOT NULL,
            expira TEXT NOT NULL,
            estado TEXT NOT NULL,
            criado_em TEXT NOT NULL
        )""")
    return con


def criar_ticket_proposta(
    item: ItemFilaDespesa,
    *,
    banco: Path | str | None = None,
    validade_horas: int = 48,
) -> str:
    """Cria e armazena atomicamente um novo ticket opaco para a proposta."""
    ticket = secrets.token_hex(8)
    expira = (agora() + timedelta(hours=validade_horas)).isoformat()
    agora_iso = agora().isoformat()
    h_conteudo = item.calcular_hash_conteudo()

    with conectar_banco(banco) as con:
        con.execute(
            """INSERT INTO propostas_despesas
               (ticket, item_id, versao, hash_conteudo, expira, estado, criado_em)
               VALUES (?, ?, ?, ?, ?, 'pendente', ?)""",
            (ticket, item.id, item.versao, h_conteudo, expira, agora_iso),
        )
    return ticket


def formatar_moeda_br(val: Decimal | float | None) -> str:
    """Formata valor em formato de moeda real brasileira R$ 1.234,56."""
    if val is None:
        return "R$ ?"
    d = Decimal(str(val))
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def formatar_data_br(dt: date | None) -> str:
    """Formata objeto date para dd/mm/aaaa."""
    if not dt:
        return "Não informada"
    return dt.strftime("%d/%m/%Y")


def formatar_conta_legivel(banco: str | None, conta: str | None) -> str:
    """Apresenta conta bancária legível sem expor número completo de forma arriscada."""
    b_limpo = (banco or "").strip()
    c_limpo = (conta or "").strip()
    if not b_limpo and not c_limpo:
        return "Não identificada"
    if b_limpo.upper() in ("PAGBANK", "PAGSEGURO"):
        b_nome = "PagBank"
    elif b_limpo.upper() in ("BB", "BANCO DO BRASIL"):
        b_nome = "Banco do Brasil"
    else:
        b_nome = b_limpo
    if c_limpo:
        return f"{b_nome} final {c_limpo}"
    return b_nome


def montar_mensagem_proposta_telegram(item: ItemFilaDespesa) -> str:
    """Gera o texto curto, claro e orientado à decisão para o Telegram (EXPENSE-02)."""
    linhas = ["*LOGOS — Despesa reconhecida*", ""]

    # Empresa
    if item.unidade_codigo and item.unidade_nome != "EMPRESA_INDEFINIDA":
        empresa_txt = item.unidade_apelido or item.unidade_nome
    else:
        empresa_txt = "⚠️ INDEFINIDA (escolha uma unidade)"
    linhas.append(f"Empresa: {empresa_txt}")

    # Favorecido / Fornecedor
    favorecido_txt = item.comprovante.favorecido or "Não informado / Desconhecido"
    linhas.append(f"Fornecedor: {favorecido_txt}")

    # Valor
    linhas.append(f"Valor: {formatar_moeda_br(item.comprovante.valor)}")

    # Documento / Tipo
    doc_txt = item.numero_documento or item.comprovante.tipo_comprovante or "Comprovante avulso"
    linhas.append(f"Documento: {doc_txt}")

    # Data e Vencimento
    data_txt = formatar_data_br(item.comprovante.data)
    linhas.append(f"Data: {data_txt}")
    if item.data_vencimento:
        linhas.append(f"Vencimento: {formatar_data_br(item.data_vencimento)}")

    linhas.append("")
    # Classificação e Centro de Custo
    plano_txt = item.sugestao_plano_nome or "A CLASSIFICAR"
    if item.sugestao_plano_codigo:
        plano_txt = f"{plano_txt} ({item.sugestao_plano_codigo})"
    linhas.append(f"Classificação: {plano_txt}")

    cc_txt = item.sugestao_centro_nome or "PISTA"
    linhas.append(f"Centro de custo: {cc_txt}")

    # Situação / Conta Financeira
    linhas.append("")
    if item.operacao_financeira == OperacaoFinanceira.DESPESA_JA_PAGA.value:
        conta_txt = formatar_conta_legivel(
            item.debito_casado_banco or item.comprovante.banco_origem, item.debito_casado_conta
        )
        situacao_txt = f"Despesa quitada no banco — débito confirmado ({conta_txt})"
    elif item.operacao_financeira == OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value:
        situacao_txt = "Conta a pagar — pagamento não identificado"
    elif item.operacao_financeira == OperacaoFinanceira.TITULO_EXISTENTE.value:
        situacao_txt = "Título existente no webPosto — candidato a baixa"
    elif item.operacao_financeira == OperacaoFinanceira.POSSIVEL_DUPLICIDADE.value:
        situacao_txt = f"Possível duplicidade ({item.alerta_duplicidade or 'coincidência na fila'})"
    else:
        situacao_txt = "Indeterminado — dados insuficientes"
    linhas.append(f"Situação: {situacao_txt}")

    # Conferências
    conferencias = []
    if item.comprovante.valor is not None:
        conferencias.append("Documento reconhecido.")
    if item.comprovante.favorecido:
        conferencias.append(f"Fornecedor identificado: {item.comprovante.favorecido}.")
    else:
        conferencias.append("Fornecedor não identificado no cadastro.")

    if item.unidade_codigo and item.unidade_nome != "EMPRESA_INDEFINIDA":
        conferencias.append(f"Empresa identificada: {item.unidade_apelido}.")
    else:
        conferencias.append("Empresa não identificada (bloqueio de aprovação).")

    if item.alerta_duplicidade:
        conferencias.append(f"⚠️ {item.alerta_duplicidade}")
    else:
        conferencias.append("Nenhuma duplicidade comprovada.")

    if item.debito_casado_fitid:
        conferencias.append(f"Débito casado no extrato: FITID {item.debito_casado_fitid}.")

    linhas.append("")
    linhas.append("Conferências:")
    for c in conferencias:
        linhas.append(f"• {c}")

    # Ação sugerida
    linhas.append("")
    if item.operacao_financeira == OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value:
        acao = "preparar conta a pagar no webPosto"
    elif item.operacao_financeira == OperacaoFinanceira.DESPESA_JA_PAGA.value:
        acao = "preparar lançamento de débito em conta"
    elif item.operacao_financeira == OperacaoFinanceira.TITULO_EXISTENTE.value:
        acao = "preparar baixa de título a pagar existente"
    else:
        acao = "revisar informações antes de integrar ao ERP"
    linhas.append(f"Ação sugerida: {acao}.")

    # Status / Bloqueios
    bloqueios = item.verificar_bloqueios_aprovacao()
    if bloqueios:
        linhas.append("")
        linhas.append("⚠️ Pendências para aprovação:")
        for b in bloqueios:
            linhas.append(f"  - {b}")

    return "\n".join(linhas)


def montar_teclado_proposta(item: ItemFilaDespesa, ticket: str) -> dict[str, Any]:
    """Monta os botões inline no Telegram (Aprovar, Corrigir, Rejeitar)."""
    if item.pode_ser_aprovado:
        teclado = [
            [
                {"text": "✅ Aprovar", "callback_data": f"desp:a:{ticket}"},
                {"text": "✏️ Corrigir", "callback_data": f"desp:c:{ticket}"},
                {"text": "❌ Rejeitar", "callback_data": f"desp:r:{ticket}"},
            ]
        ]
    else:
        # Quando há bloqueio, não apresenta o botão Aprovar até que a pendência seja sanada
        teclado = [
            [
                {"text": "✏️ Corrigir", "callback_data": f"desp:c:{ticket}"},
                {"text": "❌ Rejeitar", "callback_data": f"desp:r:{ticket}"},
            ]
        ]
    return {"inline_keyboard": teclado}


def montar_teclado_correcao(item: ItemFilaDespesa, ticket: str) -> dict[str, Any]:
    """Monta botões para correção de dados com o mínimo de digitação."""
    botoes = []

    # 1. Unidades autorizadas
    botoes.append(
        [
            {"text": "Doze (74014)", "callback_data": f"desp:u:{ticket}:74014"},
            {"text": "VIP (11495)", "callback_data": f"desp:u:{ticket}:11495"},
        ]
    )
    botoes.append(
        [
            {"text": "Casa Caiada (5555)", "callback_data": f"desp:u:{ticket}:5555"},
            {"text": "Conv 24h (118508)", "callback_data": f"desp:u:{ticket}:118508"},
        ]
    )

    # 2. Categorias frequentes
    botoes.append(
        [
            {"text": "Manutenção", "callback_data": f"desp:p:{ticket}:194968"},
            {"text": "Pedreiro", "callback_data": f"desp:p:{ticket}:198595"},
            {"text": "Fardas", "callback_data": f"desp:p:{ticket}:29057"},
        ]
    )

    # 3. Situação de pagamento
    botoes.append(
        [
            {"text": "Já foi paga", "callback_data": f"desp:pg:{ticket}:paga"},
            {"text": "Ainda a pagar", "callback_data": f"desp:pg:{ticket}:aberto"},
        ]
    )

    # 4. Botão de retorno
    botoes.append(
        [
            {"text": "🔙 Voltar ao Resumo", "callback_data": f"desp:v:{ticket}"},
        ]
    )

    return {"inline_keyboard": botoes}


async def _api(http: httpx.AsyncClient, token: str, metodo: str, dados: dict[str, Any]) -> Any:
    """Chama a API do Telegram via HTTP."""
    resp = await http.post(f"{API_BASE}/bot{token}/{metodo}", json=dados)
    if resp.status_code != 200 or resp.json().get("ok") is not True:
        raise DespesaTelegramErro(f"Falha na API do Telegram: {resp.text}")
    return resp.json().get("result")


async def processar_callback_despesa(
    callback: dict[str, Any],
    *,
    caminho_env: Path | str | None = None,
    banco: Path | str | None = None,
    caminho_fila: Path | str | None = None,
    diretores_autorizados: tuple[set[str], set[str]] | None = None,
    usuario_override: str | None = None,
) -> dict[str, Any]:
    """Processa um callback_query iniciado por 'desp:'."""
    # 1. Autenticação estrita do usuário
    mensagem = callback.get("message") or {}
    conversa = mensagem.get("chat") or {}
    chat_id = str(conversa.get("id", ""))
    from_user = callback.get("from") or {}
    user_id = usuario_override or str(from_user.get("id", ""))

    if diretores_autorizados is not None:
        chats_aut, users_aut = diretores_autorizados
    else:
        chats_aut, users_aut = obter_diretores_autorizados(caminho_env)

    if not chats_aut or not users_aut:
        raise DespesaTelegramErro(
            "Aprovação bloqueada: diretor autorizado não configurado integralmente."
        )
    if chat_id not in chats_aut:
        raise DespesaTelegramErro(
            "Aprovação permitida somente a partir de chat autorizado do diretor."
        )
    if user_id not in users_aut:
        raise DespesaTelegramErro("Aprovação permitida somente ao diretor autorizado.")

    # 2. Parse do callback_data
    raw_data = str(callback.get("data", ""))
    partes = raw_data.split(":")
    if len(partes) < 3 or partes[0] != "desp":
        raise DespesaTelegramErro("Comando Telegram inválido.")

    acao = partes[1]
    ticket = partes[2]

    # 3. Transação Atômica no SQLite
    with conectar_banco(banco) as con:
        con.execute("BEGIN IMMEDIATE")
        reg = con.execute("SELECT * FROM propostas_despesas WHERE ticket = ?", (ticket,)).fetchone()
        if not reg:
            raise DespesaTelegramErro("Esta proposta não foi encontrada ou já expirou.")

        agora_iso = agora().isoformat()
        if reg["expira"] < agora_iso:
            raise DespesaTelegramErro(
                "Esta proposta expirou. Envie novamente o comprovante se necessário."
            )

        if acao in ("a", "r"):
            if reg["estado"] != "pendente":
                raise DespesaTelegramErro("Esta proposta já foi decidida. Consulte o painel.")
            con.execute(
                "UPDATE propostas_despesas SET estado = 'executando' WHERE ticket = ?", (ticket,)
            )

    item = buscar_item_por_id(reg["item_id"], caminho_fila)
    if not item:
        with conectar_banco(banco) as con:
            con.execute(
                "UPDATE propostas_despesas SET estado = 'pendente' WHERE ticket = ?", (ticket,)
            )
        raise DespesaTelegramErro("Item não encontrado na fila de despesas.")

    # 4. Tratamento por Ação
    if acao == "a":  # Aprovar com um toque
        # Validação de versão e hash canônico
        if item.versao != reg["versao"] or item.calcular_hash_conteudo() != reg["hash_conteudo"]:
            with conectar_banco(banco) as con:
                con.execute(
                    "UPDATE propostas_despesas SET estado = 'pendente' WHERE ticket = ?", (ticket,)
                )
            raise DespesaTelegramErro(
                "Esta proposta foi alterada e requer nova conferência antes de aprovar."
            )

        bloqueios = item.verificar_bloqueios_aprovacao()
        if bloqueios:
            with conectar_banco(banco) as con:
                con.execute(
                    "UPDATE propostas_despesas SET estado = 'pendente' WHERE ticket = ?", (ticket,)
                )
            raise DespesaTelegramErro(f"Aprovação bloqueada: {bloqueios[0]}")

        # Transiciona para APROVADO (NÃO executa escrita ERP!)
        transicionar_status(
            item,
            StatusDespesa.APROVADO.value,
            motivo="Aprovado pelo diretor via Telegram para futura integração ERP",
            origem="diretor_telegram",
            usuario=f"diretor:{user_id}",
            caminho_fila=caminho_fila,
        )

        with conectar_banco(banco) as con:
            con.execute(
                "UPDATE propostas_despesas SET estado = 'aprovado' WHERE ticket = ?", (ticket,)
            )

        return {
            "sucesso": True,
            "acao": "aprovar",
            "mensagem": "✅ Despesa aprovada com sucesso! Aguardando futura integração ERP.",
            "remover_teclado": True,
        }

    elif acao == "r":  # Rejeitar
        transicionar_status(
            item,
            StatusDespesa.REJEITADO.value,
            motivo="Rejeitado pelo diretor via Telegram",
            origem="diretor_telegram",
            usuario=f"diretor:{user_id}",
            caminho_fila=caminho_fila,
        )
        with conectar_banco(banco) as con:
            con.execute(
                "UPDATE propostas_despesas SET estado = 'rejeitado' WHERE ticket = ?", (ticket,)
            )

        return {
            "sucesso": True,
            "acao": "rejeitar",
            "mensagem": "❌ Despesa rejeitada. Registro arquivado sem lançamento.",
            "remover_teclado": True,
        }

    elif acao == "c":  # Menu Corrigir
        teclado_corr = montar_teclado_correcao(item, ticket)
        return {
            "sucesso": True,
            "acao": "menu_correcao",
            "mensagem": "Selecione a informação que deseja corrigir:",
            "novo_teclado": teclado_corr,
        }

    elif acao == "v":  # Voltar ao resumo
        teclado_prop = montar_teclado_proposta(item, ticket)
        return {
            "sucesso": True,
            "acao": "voltar",
            "mensagem": "Resumo da despesa:",
            "novo_teclado": teclado_prop,
        }

    elif acao in ("u", "p", "pg"):  # Correções específicas
        if len(partes) < 4:
            raise DespesaTelegramErro("Parâmetro de correção ausente.")
        val_param = partes[3]

        # Invalida o ticket anterior no banco
        with conectar_banco(banco) as con:
            con.execute(
                "UPDATE propostas_despesas SET estado = 'substituida' WHERE ticket = ?", (ticket,)
            )

        if acao == "u":  # Corrige Empresa
            try:
                cod_u = int(val_param)
            except (ValueError, TypeError):
                raise DespesaTelegramErro(f"Código de empresa inválido no callback: {val_param}")
            if cod_u in (5558, 7):
                raise DespesaTelegramErro(
                    "Posto Real (empresaCodigo 5558 / codWeb 7) não faz parte do escopo do Expense Hunter (CNPJ desativado/inativo)."
                )
            if cod_u in (12607, 12705):
                raise DespesaTelegramErro(
                    f"Empresa {cod_u} não existe no cadastro oficial do webPosto (Casa Caiada é 5555)."
                )
            info_u = UNIDADES_AUTORIZADAS.get(cod_u)
            if not info_u:
                raise DespesaTelegramErro(f"Unidade {cod_u} não é autorizada no cadastro oficial.")
            item.unidade_codigo = cod_u
            item.unidade_nome = info_u["nome"]
            item.unidade_apelido = info_u["apelido"]

        elif acao == "p":  # Corrige Plano de Contas
            try:
                cod_p = int(val_param)
            except (ValueError, TypeError):
                raise DespesaTelegramErro(f"Código de categoria inválido no callback: {val_param}")
            nome_p = CATEGORIAS_RAPIDAS.get(cod_p, "OUTROS")
            item.sugestao_plano_codigo = cod_p
            item.sugestao_plano_nome = nome_p
            item.origem_sugestao = "correcao_diretor_telegram"

        elif acao == "pg":  # Corrige se já está paga ou aberta
            if val_param == "paga":
                item.operacao_financeira = OperacaoFinanceira.DESPESA_JA_PAGA.value
            else:
                item.operacao_financeira = OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value

        # Incrementa versão e invalida aprovações/hashes anteriores
        item.versao += 1
        item.hash_conteudo = item.calcular_hash_conteudo()

        # Re-avalia estado após correção
        if item.pode_ser_aprovado and item.status == StatusDespesa.AGUARDANDO_REVISAO.value:
            transicionar_status(
                item,
                StatusDespesa.AGUARDANDO_APROVACAO.value,
                motivo="Pendências resolvidas pelo diretor; pronto para aprovação",
                origem="diretor_telegram",
                usuario=f"diretor:{user_id}",
                caminho_fila=caminho_fila,
            )
        else:
            adicionar_item_fila(item, caminho_fila)

        # Gera novo ticket atômico para a nova versão
        novo_ticket = criar_ticket_proposta(item, banco=banco)
        novo_texto = montar_mensagem_proposta_telegram(item)
        novo_teclado = montar_teclado_proposta(item, novo_ticket)

        return {
            "sucesso": True,
            "acao": "corrigido",
            "mensagem": "✅ Proposta atualizada.",
            "novo_texto": novo_texto,
            "novo_teclado": novo_teclado,
        }

    raise DespesaTelegramErro(f"Ação desconhecida: {acao}")


async def atender_callback_despesa(
    callback: dict[str, Any],
    *,
    token: str,
    client: httpx.AsyncClient,
    caminho_env: Path | str | None = None,
    banco: Path | str | None = None,
    caminho_fila: Path | str | None = None,
) -> bool:
    """Ponto de entrada chamado pelo worker de polling para callbacks de despesas."""
    try:
        resultado = await processar_callback_despesa(
            callback,
            caminho_env=caminho_env,
            banco=banco,
            caminho_fila=caminho_fila,
        )
        texto_feedback = resultado.get("mensagem", "Operação realizada.")
        sucesso = True
    except DespesaTelegramErro as exc:
        texto_feedback = str(exc)
        sucesso = False
        resultado = {}

    # Emite feedback instantâneo no Telegram (alerta/toast)
    callback_id = callback.get("id")
    if callback_id:
        try:
            await _api(
                client,
                token,
                "answerCallbackQuery",
                {
                    "callback_query_id": callback_id,
                    "text": texto_feedback[:200],
                    "show_alert": not sucesso,
                },
            )
        except Exception as exc:
            logger.warning("Falha ao responder callback Telegram: %s", exc)

    # Atualiza a mensagem na conversa privada
    msg = callback.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")

    if chat_id and message_id:
        try:
            if resultado.get("remover_teclado"):
                await _api(
                    client,
                    token,
                    "editMessageReplyMarkup",
                    {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "reply_markup": {"inline_keyboard": []},
                    },
                )
            elif resultado.get("novo_texto") and resultado.get("novo_teclado"):
                await _api(
                    client,
                    token,
                    "editMessageText",
                    {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "text": resultado["novo_texto"],
                        "parse_mode": "Markdown",
                        "reply_markup": resultado["novo_teclado"],
                    },
                )
            elif resultado.get("novo_teclado"):
                await _api(
                    client,
                    token,
                    "editMessageReplyMarkup",
                    {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "reply_markup": resultado["novo_teclado"],
                    },
                )
        except Exception as exc:
            logger.warning("Falha ao atualizar teclado/mensagem Telegram: %s", exc)

    return sucesso
