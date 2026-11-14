"""Ação sugerida para cada divergência Premmia x webPosto (só sugere; nada é gravado no webPosto).

Ações: incluir (está no Premmia, falta no webPosto), excluir (está no webPosto, sem Premmia e sem
abastecimento), corrigir_forma (a venda existe, mas a forma de pagamento está errada), corrigir_valor
(mesmo cartão com valor diferente) e analisar (não dá para decidir com segurança: divergência não resolvida).
Cada ocorrência leva os critérios usados, para o log e para quem confere.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from apps.match.explicar import _ALERTAS_DE_VALOR, dinheiro
from src.modules.cash_reconciliation.domain.cartoes import (
    Abastecimento, Atribuicao, CartaoErp, Investigacao, ResultadoCartoes,
)
from src.modules.cash_reconciliation.domain.tempo import formatar_hora
from src.modules.cash_reconciliation.rules.cartoes import JANELA_ABASTECIMENTO, TOLERANCIA_RELOGIO

ACOES = {
    "incluir": "Incluir no webPosto",
    "excluir": "Excluir do webPosto",
    "corrigir_forma": "Corrigir a forma de pagamento",
    "corrigir_valor": "Corrigir o valor",
    "analisar": "Analisar manualmente",
}
_SEM_FRENTISTA = "funcionário não identificado"


@dataclass
class Ocorrencia:
    acao: str
    tipo: str
    valor: Decimal
    funcionario: str
    referencia: str
    explicacao: str
    correcao: str
    criterios: list[str] = field(default_factory=list)
    abastecimento: str | None = None
    nao_resolvida: bool = False
    nsu: str | None = None
    caixa_codigo: int | None = None
    valor_premmia: Decimal = Decimal(0)
    valor_webposto: Decimal = Decimal(0)

    def para_banco(self) -> dict:
        """Formato de `banco.gravar_divergencias` (mais ação, critérios e abastecimento)."""
        return {"tipo": self.tipo, "valor_esperado": self.valor_premmia, "valor_encontrado": self.valor_webposto,
                "nsu": self.nsu, "caixa_codigo": self.caixa_codigo, "responsavel": self.funcionario,
                "explicacao_pt": self.explicacao, "correcao_pt": self.correcao, "acao": self.acao,
                "criterios": self.criterios, "abastecimento": self.abastecimento, "referencia": self.referencia}


def _abast(a: Abastecimento) -> str:
    partes = [f"abastecimento {a.codigo}"]
    if a.bico is not None:
        partes.append(f"bico {a.bico}")
    partes.append(formatar_hora(a.momento))
    partes.append(dinheiro(a.valor))
    if a.frentista is not None:
        partes.append(f"{a.nome_frentista or 'frentista'} ({a.frentista})")
    return " · ".join(partes)


def _frentista_abast(a: Abastecimento) -> str:
    return f"{a.nome_frentista or 'nome indisponível'} ({a.frentista})" if a.frentista is not None else _SEM_FRENTISTA


def _funcionario_cartao(c: CartaoErp) -> str:
    return f"{c.nome_frentista or 'nome indisponível'} ({c.frentista})" if c.frentista is not None else _SEM_FRENTISTA


def _ref_cartao(c: CartaoErp) -> str:
    partes = [f"cartão {c.codigo}"]
    if c.venda_codigo:
        partes.append(f"venda {c.venda_codigo}")
    if c.nsu:
        partes.append(f"NSU {c.nsu}")
    partes.append(formatar_hora(c.momento))
    return " · ".join(partes)


def _a_maior(inv: Investigacao) -> Ocorrencia:
    t = inv.transacao
    ref = f"Premmia NSU {t.nsu or '—'} · {formatar_hora(t.momento)} · {dinheiro(t.valor)}"
    base = dict(tipo="falta_no_webposto", valor=t.valor, referencia=ref, nsu=t.nsu, valor_premmia=t.valor)
    melhor = inv.candidatos[0] if inv.candidatos else None
    if inv.atribuicao == Atribuicao.ATRIBUIDO and melhor is not None:
        criterios = [*melhor.motivos, f"{melhor.pontos} pontos", "único abastecimento compatível"]
        quem = inv.responsavel
        if inv.troca_de_forma:
            return Ocorrencia(acao="corrigir_forma", funcionario=quem, criterios=criterios,
                              abastecimento=_abast(melhor.abastecimento), **base,
                              explicacao=f"Venda de {dinheiro(t.valor)} paga com Premmia às {formatar_hora(t.momento)}"
                                         f" foi lançada como dinheiro no webPosto ({quem}).",
                              correcao="Trocar a forma de pagamento da venda de dinheiro para Premmia no webPosto.")
        return Ocorrencia(acao="incluir", funcionario=quem, criterios=criterios,
                          abastecimento=_abast(melhor.abastecimento), **base,
                          explicacao=f"Venda de {dinheiro(t.valor)} às {formatar_hora(t.momento)} está no Premmia"
                                     f" e não foi lançada no webPosto. Responsável: {quem}.",
                          correcao=f"Lançar o Premmia de {dinheiro(t.valor)} (NSU {t.nsu or '—'}) no caixa de {quem}.")
    if inv.candidatos:
        criterios = [f"{len(inv.candidatos)} abastecimentos possíveis, nenhum com certeza"] + [
            f"{_abast(c.abastecimento)} ({c.pontos} pontos)" for c in inv.candidatos[:3]]
    else:
        criterios = ["sem abastecimento de mesmo valor até "
                     f"{int(JANELA_ABASTECIMENTO / timedelta(minutes=1))} min antes da venda"]
    return Ocorrencia(acao="analisar", funcionario=_SEM_FRENTISTA, criterios=criterios, nao_resolvida=True, **base,
                      explicacao=f"Venda de {dinheiro(t.valor)} às {formatar_hora(t.momento)} está no Premmia e não"
                                 " foi lançada no webPosto, mas não dá para saber com certeza quem atendeu.",
                      correcao="Conferir com os frentistas do horário e lançar no caixa certo.")


def _abastecimentos_do_cartao(c: CartaoErp, abastecimentos: list[Abastecimento], janela, tolerancia):
    mesma_venda = [a for a in abastecimentos if c.venda_codigo and a.venda_codigo == c.venda_codigo]
    if mesma_venda:
        return mesma_venda, "mesma venda no webPosto"
    perto = [a for a in abastecimentos if a.valor == c.valor
             and -tolerancia <= c.momento - a.momento <= janela]
    return perto, f"mesmo valor até {int(janela / timedelta(minutes=1))} min antes do lançamento"


def _a_menor(c: CartaoErp, abastecimentos, janela, tolerancia) -> Ocorrencia:
    quem = _funcionario_cartao(c)
    base = dict(tipo="sobra_no_webposto", valor=c.valor, funcionario=quem, referencia=_ref_cartao(c), nsu=c.nsu,
                caixa_codigo=c.caixa_codigo, valor_webposto=c.valor)
    lancado = f"Premmia de {dinheiro(c.valor)} lançado no webPosto às {formatar_hora(c.momento)} ({quem})"
    if c.motivo and "não encontrado no portal" not in c.motivo:  # cancelado, estornado, NSU repetido
        return Ocorrencia(acao="excluir", criterios=[c.motivo], **base,
                          explicacao=f"{lancado}: {c.motivo}.",
                          correcao="Excluir o lançamento no webPosto (ou trocar para a forma realmente recebida).")
    achados, criterio = _abastecimentos_do_cartao(c, abastecimentos, janela, tolerancia)
    if len(achados) == 1:
        a = achados[0]
        return Ocorrencia(acao="corrigir_forma", criterios=["não está no portal Premmia", criterio],
                          abastecimento=_abast(a), **base,
                          explicacao=f"{lancado} não está no Premmia, mas o abastecimento existe"
                                     f" ({_frentista_abast(a)}). A venda aconteceu: o pagamento foi em outra forma.",
                          correcao="Conferir com o frentista como o cliente pagou e trocar a forma no webPosto.")
    if achados:
        return Ocorrencia(acao="analisar", nao_resolvida=True, **base,
                          criterios=["não está no portal Premmia",
                                     f"{len(achados)} abastecimentos possíveis ({criterio})"]
                          + [_abast(a) for a in achados[:3]],
                          explicacao=f"{lancado} não está no Premmia e há mais de um abastecimento que pode ser dele.",
                          correcao="Conferir com o frentista qual abastecimento é e como foi pago.")
    return Ocorrencia(acao="excluir", **base,
                      criterios=["não está no portal Premmia", f"sem abastecimento ({criterio})"],
                      explicacao=f"{lancado} não está no Premmia nem tem abastecimento correspondente:"
                                 " possível divergência de caixa.",
                      correcao="Excluir o lançamento no webPosto depois de conferir com o frentista.")


def ocorrencias(resultado: ResultadoCartoes, abastecimentos: Iterable[Abastecimento] = (), *,
                janela: timedelta = JANELA_ABASTECIMENTO,
                tolerancia: timedelta = TOLERANCIA_RELOGIO) -> list[Ocorrencia]:
    abastecimentos = list(abastecimentos)
    saida = [_a_maior(inv) for inv in resultado.a_maior]
    saida += [_a_menor(c, abastecimentos, janela, tolerancia) for c in resultado.a_menor]
    for par in resultado.pares_provaveis:
        t, c = par.investigacao.transacao, par.cartao
        saida.append(Ocorrencia(
            acao="analisar", tipo="par_provavel", valor=t.valor, funcionario=_funcionario_cartao(c),
            referencia=f"Premmia NSU {t.nsu or '—'} · {_ref_cartao(c)}", nsu=t.nsu, caixa_codigo=c.caixa_codigo,
            valor_premmia=t.valor, valor_webposto=c.valor, nao_resolvida=True,
            criterios=["mesmo valor e mesmo dia", "NSU e horário não batem"],
            explicacao=f"Premmia de {dinheiro(t.valor)} às {formatar_hora(t.momento)} e lançamento de"
                       f" {dinheiro(c.valor)} às {formatar_hora(c.momento)} no webPosto: provavelmente é a mesma"
                       " venda lançada à mão com outro horário ou NSU.",
            correcao="Confirmar e acertar o NSU/horário do lançamento no webPosto."))
    for cas in resultado.casados:
        if not cas.valor_divergente:
            continue
        t, c = cas.transacao, cas.cartao
        saida.append(Ocorrencia(
            acao="corrigir_valor", tipo="valor_diferente", valor=abs(t.valor - c.valor),
            funcionario=_funcionario_cartao(c), referencia=_ref_cartao(c), nsu=c.nsu or t.nsu,
            caixa_codigo=c.caixa_codigo, valor_premmia=t.valor, valor_webposto=c.valor,
            criterios=[f"mesmo cartão ({cas.chave})", "valor diferente"],
            explicacao=f"O Premmia registrou {dinheiro(t.valor)} e o webPosto tem {dinheiro(c.valor)}"
                       f" ({_funcionario_cartao(c)}).",
            correcao=f"Corrigir o valor do lançamento para {dinheiro(t.valor)} no webPosto."))
    for a in resultado.alertas:
        if a.codigo in _ALERTAS_DE_VALOR:
            continue
        c = a.cartoes[0] if a.cartoes else None
        saida.append(Ocorrencia(
            acao="analisar", tipo=a.codigo, valor=a.valor, funcionario=_funcionario_cartao(c) if c else _SEM_FRENTISTA,
            referencia=_ref_cartao(c) if c else "—", nsu=c.nsu if c else None,
            caixa_codigo=c.caixa_codigo if c else None, valor_webposto=a.valor, nao_resolvida=True,
            criterios=[a.codigo], explicacao=a.mensagem, correcao="Conferir o lançamento no webPosto."))
    return saida


@dataclass
class PorFuncionario:
    funcionario: str
    a_lancar: Decimal = Decimal(0)
    lancado_a_mais: Decimal = Decimal(0)
    ocorrencias: int = 0


@dataclass
class Consolidado:
    total_premmia: Decimal
    total_webposto: Decimal
    diferenca: Decimal
    pendentes: Decimal        # está no Premmia, falta lançar
    excedentes: Decimal       # lançado no webPosto sem Premmia
    nao_resolvidas: int
    por_funcionario: list[PorFuncionario]
    por_acao: dict[str, int]


def consolidar(oc: list[Ocorrencia], total_premmia: Decimal, total_webposto: Decimal) -> Consolidado:
    por: dict[str, PorFuncionario] = defaultdict(lambda: PorFuncionario(""))
    pendentes = excedentes = Decimal(0)
    for o in oc:
        f = por[o.funcionario]
        f.funcionario = o.funcionario
        f.ocorrencias += 1
        if o.tipo == "falta_no_webposto":
            pendentes += o.valor
            f.a_lancar += o.valor
        elif o.tipo == "sobra_no_webposto":
            excedentes += o.valor
            f.lancado_a_mais += o.valor
    acoes = defaultdict(int)
    for o in oc:
        acoes[o.acao] += 1
    return Consolidado(total_premmia, total_webposto, total_premmia - total_webposto, pendentes, excedentes,
                       sum(1 for o in oc if o.nao_resolvida),
                       sorted(por.values(), key=lambda f: -(f.a_lancar + f.lancado_a_mais)), dict(acoes))
