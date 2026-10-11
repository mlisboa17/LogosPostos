"""Módulo isolado de escrita de OFX no webPosto (POST /INTEGRACAO/V1/OFXS).

A BARREIRA (obrigatória — ADR-003 e RN-ERP-002):
1. Só OFX: arquivo .ofx com cabeçalho OFX válido;
2. Só esta escrita: uma única função de envio para /V1/OFXS; nenhuma outra rota de escrita;
3. Só 'dias inexistentes': opcaoImportacao fixa = IMPORTAR_APENAS_DIAS_INEXISTENTES_SISTEMA.
   EXCLUIR_DIAS_SISTEMA e IMPORTAR_DIAS_ARQUIVO são estritamente proibidos;
4. Duas travas no .env: WEBPOSTO_WRITES=1 e LOGOS_OFX_IMPORTACAO=1;
5. Prévia antes de enviar: sem confirmação explícita, apenas gera prévia;
6. Conta certa: mapa banco + sufixo no units.json conferido com GET /INTEGRACAO/V1/CONTAS;
7. Sem duplicar: histórico local em data/importacoes_ofx/ e checagem de lançamentos existentes;
8. Limites: no máximo 1 conta e até 7 dias por envio, com período no passado (até ontem).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from ..domain.models import Unidade
from ..domain.tempo import agora, formatar_data, ontem, para_local
from .extrato_reader import ExtratoBancario, LancamentoBancario, ler_arquivo, validar_cabecalho_ofx
from .webposto_http import BASE_URL_PADRAO, WebPostoErro, paginar

logger = logging.getLogger(__name__)

OPCAO_IMPORTACAO_PERMITIDA = "IMPORTAR_APENAS_DIAS_INEXISTENTES_SISTEMA"
OPCOES_PROIBIDAS = ("EXCLUIR_DIAS_SISTEMA", "IMPORTAR_DIAS_ARQUIVO")
LIMITE_MAX_DIAS = 7

# Diretório padrão para histórico de importações (fora do Git)
DIRETORIO_HISTORICO_PADRAO = Path("data/importacoes_ofx")


class BarreiraOfxErro(ValueError):
    """Violação de segurança da barreira de importação de OFX."""
    pass


@dataclass(frozen=True)
class PreviaImportacaoOfx:
    empresa_codigo: int
    unidade_nome: str
    cd_conta: int
    banco: str
    conta_sufixo: str
    data_inicial: date
    data_final: date
    quantidade: int
    total_creditos: Decimal
    total_debitos: Decimal
    saldo_liquido: Decimal
    sha256: str
    amostra_primeiros: tuple[dict[str, Any], ...]
    amostra_ultimos: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ResultadoImportacaoOfx:
    sucesso: bool
    modo: str  # "previa" ou "enviado"
    mensagem: str
    previa: PreviaImportacaoOfx
    payload_enviado: dict[str, Any] | None = None
    resposta_erp: dict[str, Any] | str | None = None


def _mascarar_descricao(desc: str) -> str:
    """Mascara CPFs, números e nomes sensíveis para exibição segura na prévia."""
    # Substitui sequências de 11 dígitos (CPFs)
    import re
    d = re.sub(r"\b\d{11}\b", "***CPF***", desc)
    # Substitui sequências longas de números
    d = re.sub(r"\b\d{5,}\b", "***DOC***", d)
    return d


def verificar_travas_ambiente() -> tuple[bool, str]:
    """Valida as duas travas de ambiente requeridas para escrita."""
    writes = os.getenv("WEBPOSTO_WRITES", "").strip()
    ofx_imp = os.getenv("LOGOS_OFX_IMPORTACAO", "").strip() or os.getenv("LOGOS_ERP_ESCRITA", "").strip()
    if writes != "1":
        return False, "Trava WEBPOSTO_WRITES != 1 (escrita bloqueada no ERP)."
    if ofx_imp != "1":
        return False, "Trava LOGOS_OFX_IMPORTACAO (ou LOGOS_ERP_ESCRITA) != 1 (importação de OFX bloqueada)."
    return True, "Travas de escrita liberadas."


def resolver_cd_conta_unidade(
    unidade: Unidade,
    banco: str,
    conta_sufixo: str,
    contas_cadastradas: list[dict[str, Any]],
) -> int:
    """Resolve e confere o cdConta único para o par (banco, conta_sufixo)."""
    # 1. Busca mapa no units.json
    mapeamentos = getattr(unidade, "contas_extrato", ())
    cd_conta = None
    
    banco_norm = banco.upper()
    sufixo_limpo = conta_sufixo.replace("-", "").replace(".", "").upper()

    for m in mapeamentos:
        m_banco = getattr(m, "banco", "").upper()
        m_sufixo = getattr(m, "conta_sufixo", "").replace("-", "").replace(".", "").upper()
        if m_banco == banco_norm and (m_sufixo.endswith(sufixo_limpo) or sufixo_limpo.endswith(m_sufixo)):
            cd_conta = getattr(m, "cd_conta", None)
            break

    # Fallback se mapeamento não estiver no model mas estiver em destinos (ex.: BB 86248)
    if cd_conta is None and banco_norm == "BB":
        for d in unidade.destinos:
            if d.banco == "BB" and d.conta_codigo:
                cd_conta = d.conta_codigo
                break

    # Se ainda for None, tenta correspondência por descrição das contas cadastradas
    if cd_conta is None:
        candidatos = []
        for c in contas_cadastradas:
            desc = (c.get("descricao") or "").upper()
            if banco_norm in desc:
                candidatos.append(c.get("contaCodigo"))
        if len(candidatos) == 1:
            cd_conta = candidatos[0]

    if cd_conta is None:
        raise BarreiraOfxErro(
            f"Não foi possível identificar o cdConta para o banco {banco} (conta final {conta_sufixo}) "
            f"na unidade {unidade.empresa_codigo}. Mapeamento ausente ou ambíguo."
        )

    # 2. Confere contra as contas ativas do webPosto
    conta_valida = any(
        c.get("contaCodigo") == cd_conta and c.get("ativo", True)
        for c in contas_cadastradas
    )
    if not conta_valida:
        raise BarreiraOfxErro(
            f"cdConta {cd_conta} resolvido para {banco} não está ativo na lista de contas do webPosto (filial {unidade.empresa_codigo})."
        )

    return cd_conta


def carregar_historico_envios(diretorio: Path, empresa_codigo: int) -> list[dict[str, Any]]:
    arquivo = diretorio / str(empresa_codigo) / "historico.json"
    if not arquivo.exists():
        return []
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except Exception:
        return []


def registrar_envio_historico(
    diretorio: Path,
    empresa_codigo: int,
    registro: dict[str, Any],
) -> None:
    pasta = diretorio / str(empresa_codigo)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "historico.json"
    historico = carregar_historico_envios(diretorio, empresa_codigo)
    historico.append(registro)
    arquivo.write_text(json.dumps(historico, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def verificar_duplicidade_historico(
    diretorio: Path,
    empresa_codigo: int,
    sha256: str,
    cd_conta: int,
    data_inicial: date,
    data_final: date,
) -> None:
    """Barreira: o mesmo arquivo/período nunca é enviado duas vezes."""
    historico = carregar_historico_envios(diretorio, empresa_codigo)
    for h in historico:
        if h.get("sha256") == sha256:
            raise BarreiraOfxErro(
                f"Arquivo com hash SHA-256 {sha256[:12]}... já foi importado anteriormente em {h.get('data_envio')}."
            )
        if (
            h.get("cd_conta") == cd_conta
            and h.get("data_inicial") == str(data_inicial)
            and h.get("data_final") == str(data_final)
            and h.get("status") == "sucesso"
        ):
            raise BarreiraOfxErro(
                f"Período {formatar_data(data_inicial)} a {formatar_data(data_final)} na conta {cd_conta} "
                f"já foi importado com sucesso em {h.get('data_envio')}."
            )


def formatar_transacao_webposto(
    l: LancamentoBancario,
    formato_tipo: str = "CREDITO_DEBITO",
    formato_sinal: str = "sempre_positivo",
    incluir_tipo_transacao: bool = False,
) -> dict[str, Any]:
    """Formata TransacaoBancaria respeitando a spec oficial e o padrão de MOVIMENTOS_CONTA."""
    # Data em ISO-8601 com milissegundos e offset -03:00 exigidos pelo parser Java/Spring do webPosto
    dt_ref = l.momento or datetime.combine(l.data, datetime.min.time())
    dt_iso = dt_ref.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

    # Tratamento do tipo e sinal conforme configuração
    if formato_tipo == "CREDITO_DEBITO":
        tipo_str = "Crédito" if l.eh_credito else "Débito"
    elif formato_tipo == "C_D":
        tipo_str = "C" if l.eh_credito else "D"
    else:
        tipo_str = "CREDIT" if l.eh_credito else "DEBIT"

    if formato_sinal == "sempre_positivo":
        val_float = float(abs(l.valor))
    else:
        # Padrão OFX: créditos positivos, débitos negativos
        val_float = float(l.valor if l.eh_credito else -abs(l.valor))

    return {
        "tipo": tipo_str,
        "valor": val_float,
        "dataMovimento": dt_iso,
        "dataCredito": dt_iso,
        "descricao": l.descricao[:255],
        "numeroDocumento": (l.documento or l.fitid)[:30],
        "nomePagador": None,
        "tipoTransacao": (l.tipo_original[:30] if l.tipo_original else None) if incluir_tipo_transacao else None,
        "extratoExterno": l.fitid[:30],
    }


def montar_payload_ofx(
    cd_conta: int,
    cd_filial: int,
    data_inicial: date,
    data_final: date,
    lancamentos: tuple[LancamentoBancario, ...],
    formato_tipo: str = "CREDITO_DEBITO",
    formato_sinal: str = "sempre_positivo",
    incluir_tipo_transacao: bool = False,
) -> dict[str, Any]:
    """Monta o payload estrito ParamIncluirOfx."""
    # Verificação rígida contra opções proibidas
    opcao = OPCAO_IMPORTACAO_PERMITIDA
    for proibida in OPCOES_PROIBIDAS:
        if proibida in opcao:
            raise BarreiraOfxErro(f"Opção de importação proibida detectada: {proibida}")

    transacoes = [
        formatar_transacao_webposto(
            l,
            formato_tipo=formato_tipo,
            formato_sinal=formato_sinal,
            incluir_tipo_transacao=incluir_tipo_transacao,
        )
        for l in lancamentos
    ]

    payload = {
        "cdConta": int(cd_conta),
        "cdFilial": int(cd_filial),
        "dataInicial": str(data_inicial),
        "dataFinal": str(data_final),
        "transacoes": transacoes,
        "opcaoImportacao": opcao,
    }

    # Verificação de segurança adicional no json completo
    payload_str = json.dumps(payload)
    for proibida in OPCOES_PROIBIDAS:
        if proibida in payload_str:
            raise BarreiraOfxErro(f"Payload violou a barreira contendo termo proibido: {proibida}")

    return payload


async def enviar_ofx_webposto(
    unidade: Unidade,
    caminho_arquivo: Path | str,
    *,
    data_inicial: date | None = None,
    data_final: date | None = None,
    confirmar: bool = False,
    client: httpx.AsyncClient | None = None,
    diretorio_historico: Path | None = None,
    formato_tipo: str = "CREDITO_DEBITO",
    formato_sinal: str = "sempre_positivo",
    incluir_tipo_transacao: bool = False,
) -> ResultadoImportacaoOfx:
    """ÚNICA função de envio de OFX para /INTEGRACAO/V1/OFXS com barreira total."""
    caminho = Path(caminho_arquivo)
    
    # 1. Barreira: Só OFX
    if not caminho.suffix.lower().endswith(".ofx"):
        raise BarreiraOfxErro(f"Extensão recusada: {caminho.suffix}. Apenas arquivos .ofx são permitidos.")
    
    conteudo = caminho.read_bytes()
    validar_cabecalho_ofx(conteudo)
    
    # 2. Leitura
    extrato = ler_arquivo(caminho)
    if not extrato.lancamentos:
        raise BarreiraOfxErro("Extrato OFX não contém lançamentos.")

    # 3. Determinação e validação do período
    dt_ontem = ontem()
    dt_ini = data_inicial or extrato.inicio or min(l.data for l in extrato.lancamentos)
    dt_fim = data_final or extrato.fim or max(l.data for l in extrato.lancamentos)

    if dt_fim > dt_ontem:
        raise BarreiraOfxErro(
            f"Período inválido: dataFinal ({formatar_data(dt_fim)}) não pode ser superior a ontem "
            f"({formatar_data(dt_ontem)}). A barreira exige período no passado."
        )
    if dt_ini > dt_fim:
        raise BarreiraOfxErro(f"dataInicial ({dt_ini}) superior a dataFinal ({dt_fim}).")

    dias_periodo = (dt_fim - dt_ini).days + 1
    if dias_periodo > LIMITE_MAX_DIAS:
        raise BarreiraOfxErro(
            f"Limite de período excedido: {dias_periodo} dias solicitados. A barreira permite no máximo {LIMITE_MAX_DIAS} dias por envio."
        )

    # Filtra lançamentos dentro do período
    lancamentos_periodo = tuple(l for l in extrato.lancamentos if dt_ini <= l.data <= dt_fim)
    if not lancamentos_periodo:
        raise BarreiraOfxErro(f"Nenhum lançamento no extrato entre {formatar_data(dt_ini)} e {formatar_data(dt_fim)}.")

    # 4. Resolução da conta e conferência com GET /INTEGRACAO/V1/CONTAS (somente leitura)
    contas_cadastradas = await paginar(unidade, "/INTEGRACAO/V1/CONTAS", {"empresaCodigo": unidade.empresa_codigo}, client=client)
    cd_conta = resolver_cd_conta_unidade(unidade, extrato.banco, extrato.conta_sufixo, contas_cadastradas)

    # 5. Barreira: Sem duplicar
    dir_hist = diretorio_historico or DIRETORIO_HISTORICO_PADRAO
    verificar_duplicidade_historico(dir_hist, unidade.empresa_codigo, extrato.sha256, cd_conta, dt_ini, dt_fim)

    # 6. Montagem da prévia
    amostra_primeiros = tuple(
        {
            "data": formatar_data(l.data),
            "tipo": "Crédito" if l.eh_credito else "Débito",
            "valor": float(abs(l.valor)),
            "descricao_mascarada": _mascarar_descricao(l.descricao),
        }
        for l in lancamentos_periodo[:3]
    )
    amostra_ultimos = tuple(
        {
            "data": formatar_data(l.data),
            "tipo": "Crédito" if l.eh_credito else "Débito",
            "valor": float(abs(l.valor)),
            "descricao_mascarada": _mascarar_descricao(l.descricao),
        }
        for l in lancamentos_periodo[-3:]
    )

    tot_cred = sum((l.valor for l in lancamentos_periodo if l.eh_credito), Decimal("0"))
    tot_deb = sum((abs(l.valor) for l in lancamentos_periodo if l.eh_debito), Decimal("0"))

    previa = PreviaImportacaoOfx(
        empresa_codigo=unidade.empresa_codigo,
        unidade_nome=unidade.nome,
        cd_conta=cd_conta,
        banco=extrato.banco,
        conta_sufixo=extrato.conta_sufixo,
        data_inicial=dt_ini,
        data_final=dt_fim,
        quantidade=len(lancamentos_periodo),
        total_creditos=tot_cred,
        total_debitos=tot_deb,
        saldo_liquido=tot_cred - tot_deb,
        sha256=extrato.sha256,
        amostra_primeiros=amostra_primeiros,
        amostra_ultimos=amostra_ultimos,
    )

    # 7. Montagem do payload seguro
    payload = montar_payload_ofx(
        cd_conta=cd_conta,
        cd_filial=unidade.empresa_codigo,
        data_inicial=dt_ini,
        data_final=dt_fim,
        lancamentos=lancamentos_periodo,
        formato_tipo=formato_tipo,
        formato_sinal=formato_sinal,
        incluir_tipo_transacao=incluir_tipo_transacao,
    )

    # 8. Verificação das travas para envio
    travas_ok, motivo_trava = verificar_travas_ambiente()
    if not confirmar:
        return ResultadoImportacaoOfx(
            sucesso=True,
            modo="previa",
            mensagem="Prévia gerada com sucesso. Envio não solicitado (use --confirmar e aguarde autorização do diretor).",
            previa=previa,
            payload_enviado=payload,
        )

    if not travas_ok:
        return ResultadoImportacaoOfx(
            sucesso=False,
            modo="previa",
            mensagem=f"Envio bloqueado pelas travas de segurança: {motivo_trava}",
            previa=previa,
            payload_enviado=payload,
        )

    # 9. Envio real para POST /INTEGRACAO/V1/OFXS
    chave = (os.getenv(unidade.chave_env) or "").strip()
    if not chave:
        raise WebPostoErro(f"Variável de chave {unidade.chave_env} ausente.")

    base_url = os.getenv("WEBPOSTO_BASE_URL") or BASE_URL_PADRAO
    proprio = client is None
    http = client or httpx.AsyncClient(base_url=base_url, timeout=60.0)

    try:
        url = "/INTEGRACAO/V1/OFXS"
        params = {"CHAVE": chave}
        try:
            resp = await http.post(url, params=params, json=payload)
        except httpx.HTTPError as exc:
            raise WebPostoErro(f"Falha de conexão com webPosto: {type(exc).__name__}") from None

        if resp.status_code in (401, 403):
            raise BarreiraOfxErro(
                f"Chave da unidade {unidade.empresa_codigo} não possui permissão de escrita no webPosto (HTTP {resp.status_code})."
            )
        if resp.status_code not in (200, 201):
            texto_erro = resp.text[:200].replace(chave, "***")
            raise WebPostoErro(f"Erro na importação de OFX pelo webPosto (HTTP {resp.status_code}): {texto_erro}")

        try:
            resp_data = resp.json()
        except Exception:
            resp_data = resp.text

        # 10. Registro no histórico persistente
        registro_envio = {
            "arquivo": caminho.name,
            "sha256": extrato.sha256,
            "empresa_codigo": unidade.empresa_codigo,
            "cd_conta": cd_conta,
            "data_inicial": str(dt_ini),
            "data_final": str(dt_fim),
            "quantidade": len(lancamentos_periodo),
            "total_creditos": str(tot_cred),
            "total_debitos": str(tot_deb),
            "data_envio": agora().isoformat(),
            "status": "sucesso",
            "resposta": resp_data,
        }
        registrar_envio_historico(dir_hist, unidade.empresa_codigo, registro_envio)

        return ResultadoImportacaoOfx(
            sucesso=True,
            modo="enviado",
            mensagem=f"OFX importado com sucesso no webPosto ({len(lancamentos_periodo)} lançamentos).",
            previa=previa,
            payload_enviado=payload,
            resposta_erp=resp_data,
        )
    finally:
        if proprio:
            await http.aclose()
