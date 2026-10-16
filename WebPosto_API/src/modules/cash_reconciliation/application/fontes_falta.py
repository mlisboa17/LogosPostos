"""Anexa evidências locais durante a coleta; renderizadores não fazem I/O."""
import logging

from ..adapters.webposto_http import WebPostoErro
from ..domain.explicacao import ConferenciaPixCnpj
from .conciliar_cartoes import coletar_contexto_cartoes
from .pix_cnpj import conferir_pix_cnpj, ler_extratos_unidade

logger = logging.getLogger(__name__)


async def anexar_fontes_falta(registro, unidade):
    try:
        extratos = ler_extratos_unidade(unidade, registro.dia)
        if not extratos:
            return registro
        cartoes, abastecimentos, itens = await coletar_contexto_cartoes(unidade.empresa_codigo, registro.dia)
        conferencia, partes = conferir_pix_cnpj(unidade, registro.dia, extratos, cartoes, abastecimentos, itens)
        caixas = {a.caixa.codigo for a in registro.fechamento.caixas} if registro.fechamento else set()
        partes = tuple(p for p in partes if p.caixa_codigo in caixas)
        return registro.model_copy(update={"pix_cnpj": conferencia, "partes_falta": partes})
    except (OSError, ValueError, TimeoutError, WebPostoErro) as exc:
        logger.warning("PIX CNPJ unidade=%s tipo=%s", unidade.empresa_codigo, type(exc).__name__)
        return registro.model_copy(update={"pix_cnpj": ConferenciaPixCnpj(
            erro="Falha ao conferir extrato PIX CNPJ; verificar conta, FITID e coleta de vendas."
        )})
