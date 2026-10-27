"""Caso de uso: auditar o fechamento dos caixas de uma unidade num periodo (somente webPosto)."""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import Iterable

from ..adapters.webposto_caixas import PATH_APRESENTADO, PATH_CAIXAS, buscar_apresentados, buscar_caixas
from ..adapters.webposto_detalhes import PATH_MOVIMENTOS, PATH_VALES, buscar_despesas, buscar_vales
from ..adapters.webposto_sangrias import FONTE as FONTE_SANGRIAS, buscar_sangrias
from ..adapters.webposto_vendas import PATH_VENDAS, buscar_vendas_por_caixa
from ...webposto_integration.funcionarios import PATH_FUNCIONARIOS, buscar_nomes_funcionarios
from ..config import carregar_unidades, dias_tolerancia_consolidacao
from ..domain.fechamento import Caixa, LinhaModalidade, MovimentoDespesa, ResultadoAuditoria, ValeFuncionario
from ..domain.models import Proveniencia, Sangria
from ..domain.tempo import agora
from ..rules.fechamento import VERSAO, auditar_caixa


def auditar(
    empresa_codigo: int,
    caixas: Iterable[Caixa],
    apresentados: dict[int, tuple[LinhaModalidade, ...]],
    sangrias: Iterable[Sangria],
    inicio: date,
    fim: date,
    *,
    vales: Iterable[ValeFuncionario] = (),
    despesas: Iterable[MovimentoDespesa] = (),
    tolerancia_consolidacao: int = 2,
    hoje: date | None = None,
    repasse_sangria_para: int | None = None,
    nome_destino_repasse: str | None = None,
    destino_padrao: int | None = None,
    vendas: dict[int, dict[int, Decimal]] | None = None,
    nomes_funcionarios: dict[int, str] | None = None,
) -> ResultadoAuditoria:
    sangrias = [s for s in sangrias if s.empresa_codigo == empresa_codigo]
    vales = [v for v in vales if v.empresa_codigo == empresa_codigo]
    despesas = list(despesas)
    vendas_map = vendas or {}
    nomes_map = nomes_funcionarios or {}
    auditorias = tuple(
        auditar_caixa(
            c,
            apresentados.get(c.codigo, ()),
            sangrias,
            vales=vales,
            despesas=despesas,
            dias_tolerancia_consolidacao=tolerancia_consolidacao,
            hoje=hoje,
            repasse_sangria_para=repasse_sangria_para,
            nome_destino_repasse=nome_destino_repasse,
            destino_padrao=destino_padrao,
            vendas_operadores=vendas_map.get(c.codigo),
            nomes_funcionarios=nomes_map,
        )
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
            executado_em=agora(),
            versao_regra=VERSAO,
            fonte_sangrias=FONTE_SANGRIAS,
            extratos=(),
            outras_fontes=(
                f"webPosto{PATH_CAIXAS}",
                f"webPosto{PATH_APRESENTADO}",
                f"webPosto{PATH_VALES}",
                f"webPosto{PATH_MOVIMENTOS}",
                f"webPosto{PATH_VENDAS}",
                f"webPosto{PATH_FUNCIONARIOS}",
            ),
        ),
    )


async def auditar_unidade(empresa_codigo: int, inicio: date, fim: date) -> ResultadoAuditoria:
    unidades = carregar_unidades()
    unidade = unidades[empresa_codigo]
    destino_repasse = (
        unidades[unidade.repasse_sangria_para]
        if unidade.repasse_sangria_para is not None
        else None
    )
    caixas = await buscar_caixas(unidade, inicio, fim)
    caixas_codigos = {c.codigo for c in caixas}

    # Execução concorrente de todas as fontes de dados para alta performance em lote multi-dias
    (
        apresentados_res,
        sangrias_res,
        vales_res,
        despesas_res,
        vendas_res,
        nomes_res,
    ) = await asyncio.gather(
        buscar_apresentados(unidade, inicio, fim, caixas_codigos),
        buscar_sangrias(unidade, inicio, fim),
        buscar_vales(unidade, inicio, fim),
        buscar_despesas(unidade, caixas_codigos),
        buscar_vendas_por_caixa(unidade, inicio, fim),
        buscar_nomes_funcionarios(unidade, inicio, fim),
        return_exceptions=True,
    )

    apresentados = apresentados_res if not isinstance(apresentados_res, Exception) else {}
    sangrias = sangrias_res if not isinstance(sangrias_res, Exception) else []
    vales = vales_res if not isinstance(vales_res, Exception) else []
    despesas = despesas_res if not isinstance(despesas_res, Exception) else []
    vendas = vendas_res if not isinstance(vendas_res, Exception) else {}
    nomes_funcionarios = nomes_res if not isinstance(nomes_res, Exception) else {}

    return auditar(
        empresa_codigo,
        caixas,
        apresentados,
        sangrias,
        inicio,
        fim,
        vales=vales,
        despesas=despesas,
        tolerancia_consolidacao=dias_tolerancia_consolidacao(),
        repasse_sangria_para=unidade.repasse_sangria_para,
        nome_destino_repasse=destino_repasse.nome if destino_repasse is not None else None,
        destino_padrao=unidade.destino_padrao,
        vendas=vendas,
        nomes_funcionarios=nomes_funcionarios,
    )

