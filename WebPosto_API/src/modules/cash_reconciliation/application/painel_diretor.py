"""Composicao do painel a partir de snapshots locais, sem consulta ao ERP."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from ..adapters import pendencias as repositorio_pendencias
from ..adapters import persistencia
from ..domain.models import Unidade
from ..domain.recebimentos import ResultadoRecebimentos


class PainelDiretorErro(RuntimeError):
    pass


def _dias_com_snapshot(raiz: Path, unidade: int, ate: date) -> list[date]:
    try:
        pastas = list(raiz.iterdir())
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise PainelDiretorErro("Falha ao listar auditorias persistidas.") from exc
    dias = []
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        try:
            dia = date.fromisoformat(pasta.name)
        except ValueError:
            continue
        if dia > ate:
            continue
        try:
            if (pasta / f"{unidade}.json").is_file():
                dias.append(dia)
        except OSError as exc:
            raise PainelDiretorErro("Falha ao verificar snapshots persistidos.") from exc
    return sorted(dias, reverse=True)


def _resumo_recebimentos(resultado: ResultadoRecebimentos | None) -> dict[str, object]:
    if resultado is None:
        return {
            "a_maior_total": None,
            "a_menor_total": None,
            "adquirentes": [],
        }

    adquirentes = []
    itens_ok = []
    for item in resultado.adquirentes:
        situacao = item.situacao
        if situacao == "ok":
            situacao = "ativo"
            itens_ok.append(item)
        adquirentes.append({"nome": item.adquirente, "situacao": situacao})

    if not itens_ok:
        maior = menor = None
    else:
        maior = sum(
            (transacao.transacao.valor for item in itens_ok for transacao in item.a_maior),
            Decimal(0),
        )
        menor = sum(
            (cartao.valor for item in itens_ok for cartao in item.a_menor),
            Decimal(0),
        )
    return {
        "a_maior_total": maior,
        "a_menor_total": menor,
        "adquirentes": adquirentes,
    }


def _resumo_fechamento(resultado, hoje: date) -> dict[str, object] | None:
    if resultado is None:
        return None
    auditorias = [caixa for caixa in resultado.caixas]
    faltas = [
        alerta
        for caixa in auditorias
        for alerta in caixa.alertas
        if alerta.codigo == "FALTA_SEM_DESCONTO"
    ]
    parados = [
        alerta
        for caixa in auditorias
        for alerta in caixa.alertas
        if alerta.codigo == "NAO_CONSOLIDADO"
    ]
    dias_parados = [
        max((hoje - caixa.caixa.fechamento.date()).days, 0)
        for caixa in auditorias
        if not caixa.caixa.consolidado and caixa.caixa.fechamento is not None
    ]
    return {
        "dia": resultado.fim,
        "quebra_total": resultado.quebra_total,
        "faltas_sem_desconto": len(faltas),
        "faltas_sem_desconto_total": sum((falta.valor or Decimal(0) for falta in faltas), Decimal(0)),
        "caixas_parados": len(parados),
        "caixas_parados_dias": max(dias_parados, default=0),
    }


def obter_unidades_painel(
    unidades: Mapping[int, Unidade],
    *,
    escopo: set[int] | None,
    hoje: date,
    diretorio_snapshots: Path | None = None,
    diretorio_pendencias: Path | None = None,
) -> list[dict[str, object]]:
    """Retorna métricas reais disponíveis; ausência de snapshot permanece nula."""
    raiz_snapshots = persistencia.DIRETORIO if diretorio_snapshots is None else diretorio_snapshots
    resultado = []
    for codigo, unidade in unidades.items():
        if escopo is not None and codigo not in escopo:
            continue
        fechamento = None
        recebimentos = None
        for dia in _dias_com_snapshot(raiz_snapshots, codigo, hoje):
            registro = persistencia.carregar_dia(codigo, dia, diretorio=raiz_snapshots)
            if registro is None:
                continue
            if recebimentos is None:
                recebimentos = registro.recebimentos
            if fechamento is None and registro.fechamento is not None:
                fechamento = _resumo_fechamento(registro.fechamento, hoje)
            if recebimentos is not None and fechamento is not None:
                break
        resumo_recebimentos = _resumo_recebimentos(recebimentos)
        status_por_adquirente = {
            item["nome"]: item["situacao"] for item in resumo_recebimentos["adquirentes"]
        }
        adquirentes = [
            {
                "nome": adquirente.nome,
                "situacao": status_por_adquirente.get(
                    adquirente.nome,
                    adquirente.situacao.value,
                ),
            }
            for adquirente in unidade.adquirentes
        ]
        try:
            pendencias_abertas = repositorio_pendencias.contar_abertas_somente_leitura(
                unidade=codigo,
                banco=diretorio_pendencias,
            )
        except repositorio_pendencias.ErroPersistenciaPendencias as exc:
            raise PainelDiretorErro("Falha ao ler pendências persistidas.") from exc
        resultado.append({
            "empresa_codigo": codigo,
            "nome": unidade.nome,
            "fechamento": fechamento,
            "recebimentos_a_maior_total": resumo_recebimentos["a_maior_total"],
            "recebimentos_a_menor_total": resumo_recebimentos["a_menor_total"],
            "pendencias_abertas": pendencias_abertas,
            "adquirentes": adquirentes,
        })
    return resultado
