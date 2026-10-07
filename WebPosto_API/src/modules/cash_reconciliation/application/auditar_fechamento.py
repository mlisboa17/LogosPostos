"""Caso de uso: auditar o fechamento dos caixas de uma unidade num periodo (somente webPosto)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Iterable

from ..adapters.webposto_caixas import PATH_APRESENTADO, PATH_CAIXAS, buscar_apresentados, buscar_caixas
from ..adapters.webposto_sangrias import FONTE as FONTE_SANGRIAS, buscar_sangrias
from ..config import carregar_unidades
from ..domain.fechamento import Caixa, LinhaModalidade, ResultadoAuditoria
from ..domain.models import Proveniencia, Sangria
from ..rules.fechamento import VERSAO, auditar_caixa


def auditar(
    empresa_codigo: int,
    caixas: Iterable[Caixa],
    apresentados: dict[int, tuple[LinhaModalidade, ...]],
    sangrias: Iterable[Sangria],
    inicio: date,
    fim: date,
) -> ResultadoAuditoria:
    sangrias = [s for s in sangrias if s.empresa_codigo == empresa_codigo]
    auditorias = tuple(
        auditar_caixa(c, apresentados.get(c.codigo, ()), sangrias)
        for c in sorted(caixas, key=lambda c: (c.data, c.abertura))
        if c.empresa_codigo == empresa_codigo and inicio <= c.data <= fim
    )
    return ResultadoAuditoria(
        empresa_codigo=empresa_codigo,
        inicio=inicio,
        fim=fim,
        caixas=auditorias,
        proveniencia=Proveniencia(
            execucao_id=uuid.uuid4().hex,
            executado_em=datetime.now(),
            versao_regra=VERSAO,
            fonte_sangrias=FONTE_SANGRIAS,
            extratos=(),
            outras_fontes=(f"webPosto{PATH_CAIXAS}", f"webPosto{PATH_APRESENTADO}"),
        ),
    )


async def auditar_unidade(empresa_codigo: int, inicio: date, fim: date) -> ResultadoAuditoria:
    unidade = carregar_unidades()[empresa_codigo]
    caixas = await buscar_caixas(unidade, inicio, fim)
    apresentados = await buscar_apresentados(unidade, inicio, fim, {c.codigo for c in caixas})
    sangrias = await buscar_sangrias(unidade, inicio, fim)
    return auditar(empresa_codigo, caixas, apresentados, sangrias, inicio, fim)
