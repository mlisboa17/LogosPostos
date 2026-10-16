"""Anexa evidências locais durante a coleta; renderizadores não fazem I/O."""
import logging

from ..adapters.webposto_http import WebPostoErro, paginar
from ..adapters.webposto_escrita_cartao import BarreiraCartaoErro, resolver_administradora_codigo
from ..domain.explicacao import ConferenciaPixCnpj
from .conciliar_cartoes import coletar_contexto_cartoes
from .pix_cnpj import conferir_pix_cnpj, ler_extratos_unidade
from . import mais_pagamentos

logger = logging.getLogger(__name__)


async def anexar_fontes_falta(registro, unidade):
    if any(adq.adquirente == "PAGBANK" and any(
        any(s in (inv.transacao.bandeira or "").upper() for s in ("PIX", "BACEN"))
        for inv in adq.a_maior) for adq in registro.recebimentos.adquirentes):
        try:
            admins = await paginar(unidade, "/INTEGRACAO/V1/ADMINISTRADORAS",
                                   {"empresaCodigo": unidade.empresa_codigo})
            codigo = resolver_administradora_codigo(unidade, "PAGBANK", "PIX BACEN", admins)
            descricao = next(a["descricao"] for a in admins
                             if int(a.get("administradoraCodigo") or a.get("codigo") or 0) == codigo)
            registro = registro.model_copy(update={"administradora_pix_pagbank": descricao})
        except BarreiraCartaoErro as exc:
            registro = registro.model_copy(update={"motivo_pix_pagbank": str(exc)})
        except (WebPostoErro, OSError, TimeoutError, ValueError) as exc:
            logger.warning("Administradora PIX unidade=%s tipo=%s", unidade.empresa_codigo, type(exc).__name__)
            registro = registro.model_copy(update={
                "motivo_pix_pagbank": "Não consegui consultar a administradora PIX PagBank; conferir à mão."
            })
    total = None
    erro_mais = None
    try:
        total = mais_pagamentos.carregar(unidade.empresa_codigo, registro.dia)
    except (OSError, ValueError) as exc:
        logger.warning("Mais Pagamentos unidade=%s tipo=%s", unidade.empresa_codigo, type(exc).__name__)
        erro_mais = mais_pagamentos.ConferenciaMais(total=None, webposto=None, aviso="Falha ao ler total Mais Pagamentos local.")
    cartoes, abastecimentos, itens = [], [], set()
    try:
        extratos = ler_extratos_unidade(unidade, registro.dia)
        if extratos or (total and total.pix):
            cartoes, abastecimentos, itens = await coletar_contexto_cartoes(unidade.empresa_codigo, registro.dia)
        if extratos:
            conferencia, partes = conferir_pix_cnpj(unidade, registro.dia, extratos, cartoes, abastecimentos, itens)
            caixas = {a.caixa.codigo for a in registro.fechamento.caixas} if registro.fechamento else set()
            if any(p.caixa_codigo not in caixas for p in partes):
                raise ValueError("Venda PIX fora dos caixas consultados.")
            registro = registro.model_copy(update={"pix_cnpj": conferencia, "partes_falta": partes})
    except (OSError, ValueError, TimeoutError, WebPostoErro) as exc:
        logger.warning("PIX CNPJ unidade=%s tipo=%s", unidade.empresa_codigo, type(exc).__name__)
        registro = registro.model_copy(update={"pix_cnpj": ConferenciaPixCnpj(
            erro="Falha ao conferir extrato PIX CNPJ; verificar conta, FITID e coleta de vendas."
        )})
    if total:
        conf, partes = mais_pagamentos.comparar(registro, unidade, total, abastecimentos, itens)
        registro = registro.model_copy(update={"mais_pagamentos": conf,
                                               "partes_falta": (*registro.partes_falta, *partes)})
    elif erro_mais:
        registro = registro.model_copy(update={"mais_pagamentos": erro_mais})
    return registro
