"""Contrato publico dos recebimentos, sem comprovantes individuais dos casados."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .cartoes import (
    AlertaCartao,
    Casamento,
    CartaoErp,
    GrupoProvavel,
    Investigacao,
    ParProvavel,
    ResultadoCartoes,
    TransacaoAdquirente,
)
from .models import Proveniencia


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ResumoCasados(_Frozen):
    quantidade: int
    total: Decimal


class ResumoForma(_Frozen):
    forma: str
    portal: ResumoCasados
    webposto: ResumoCasados
    diferenca: Decimal


def forma_recebimento(descricao: str | None) -> str:
    texto = (descricao or "").strip().upper()
    if texto == "POS PREMMIA":
        return "POS"
    if "DESCONTO" in texto:
        return "Desconto"
    if "PIX" in texto:
        return "Pix"
    if "VALE" in texto:
        return "Vale"
    if texto == "CARTÃO APP" or "CREDITO" in texto or "CRÉDITO" in texto:
        return "Cartão APP"
    return descricao or "Forma não informada"


class RecebimentoAdquirente(_Frozen):
    adquirente: str
    situacao: Literal["ok", "pendente", "credencial inválida", "erro"]
    erro: str | None = None
    casados: ResumoCasados | None = None
    a_maior: tuple[Investigacao, ...] = ()
    a_menor: tuple[CartaoErp, ...] = ()
    pares_provaveis: tuple[ParProvavel, ...] = ()
    grupos_provaveis: tuple[GrupoProvavel, ...] = ()
    casados_valor_divergente: ResumoCasados = ResumoCasados(quantidade=0, total=Decimal(0))
    divergencias_valor: tuple[Casamento, ...] = ()
    cancelados: ResumoCasados = ResumoCasados(quantidade=0, total=Decimal(0))
    transacoes_canceladas: tuple[TransacaoAdquirente, ...] = ()
    alertas: tuple[AlertaCartao, ...] = ()
    proveniencia: Proveniencia | None = None
    formas: tuple[ResumoForma, ...] = ()
    codigos_conferidos: tuple[int, ...] = ()
    detalhes_casados: tuple[Casamento, ...] = ()
    sem_fonte: tuple[CartaoErp, ...] = ()
    evidencias_completas: bool = False

    @classmethod
    def de_resultado(cls, resultado: ResultadoCartoes) -> RecebimentoAdquirente:
        transacoes = {
            t.identificador: t for t in (
                *(c.transacao for c in resultado.casados),
                *(i.transacao for i in resultado.a_maior),
                *(p.investigacao.transacao for p in resultado.pares_provaveis),
                *(i.transacao for g in resultado.grupos_provaveis for i in g.investigacoes),
            )
        }
        cartoes = {
            c.codigo: c for c in (
                *(c.cartao for c in resultado.casados), *resultado.a_menor,
                *(p.cartao for p in resultado.pares_provaveis),
                *(g.cartao for g in resultado.grupos_provaveis),
            )
        }
        formas = sorted({
            *(forma_recebimento(t.bandeira) for t in transacoes.values()),
            *(forma_recebimento(c.administradora) for c in cartoes.values()),
        })
        resumos = []
        for forma in formas:
            portal = [t for t in transacoes.values() if forma_recebimento(t.bandeira) == forma]
            erp = [c for c in cartoes.values() if forma_recebimento(c.administradora) == forma]
            total_portal = sum((t.valor for t in portal), Decimal(0))
            total_erp = sum((c.valor for c in erp), Decimal(0))
            resumos.append(ResumoForma(
                forma=forma,
                portal=ResumoCasados(quantidade=len(portal), total=total_portal),
                webposto=ResumoCasados(quantidade=len(erp), total=total_erp),
                diferenca=total_portal - total_erp,
            ))
        return cls(
            adquirente=resultado.adquirente,
            situacao="ok",
            casados=ResumoCasados(
                quantidade=len(resultado.casados),
                total=sum((c.transacao.valor for c in resultado.casados), Decimal(0)),
            ),
            a_maior=resultado.a_maior,
            a_menor=resultado.a_menor,
            pares_provaveis=resultado.pares_provaveis,
            grupos_provaveis=resultado.grupos_provaveis,
            divergencias_valor=tuple(c for c in resultado.casados if c.valor_divergente),
            casados_valor_divergente=ResumoCasados(
                quantidade=sum(c.valor_divergente for c in resultado.casados),
                total=sum(
                    (c.diferenca for c in resultado.casados if c.valor_divergente), Decimal(0)
                ),
            ),
            cancelados=ResumoCasados(
                quantidade=len(resultado.cancelados),
                total=sum((c.valor for c in resultado.cancelados), Decimal(0)),
            ),
            transacoes_canceladas=resultado.cancelados,
            alertas=resultado.alertas,
            proveniencia=resultado.proveniencia,
            formas=tuple(resumos),
            codigos_conferidos=tuple(c.cartao.codigo for c in resultado.casados if not c.valor_divergente),
            detalhes_casados=resultado.casados,
            sem_fonte=resultado.sem_fonte,
            evidencias_completas=True,
        )


class ResultadoRecebimentos(_Frozen):
    empresa_codigo: int
    dia: date
    adquirentes: tuple[RecebimentoAdquirente, ...]
