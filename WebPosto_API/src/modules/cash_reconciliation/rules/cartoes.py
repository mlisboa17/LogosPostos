"""Conciliacao adquirente x webPosto e investigacao por abastecimento — CARTOES_V1.

1. Chave exata: NSU ou autorizacao (cartao). Evidencia Doze 05/10/2026: 255/255.
2. Sem NSU (PIX via adquirente): mesmo valor e |dt| <= 10 min.
3. Sobra na adquirente (a maior) -> procura o abastecimento e o frentista (identfid):
     valor igual ................................. 35
     abastecimento 0-15 min antes do pagamento ... ate 30 (linear)
     venda do abastecimento lancada como dinheiro  20  (indicio de troca de forma)
     valor "quebrado" (nao multiplo de R$ 5) ..... 15  (valores redondos se repetem)
   >= 80 e candidato unico -> atribui sozinho; 50-79 ou empate -> sugestao.
4. Sobra no webPosto (a menor) -> lancado e nao recebido (prioridade maxima).
5. Sobra a maior + sobra a menor com o mesmo valor no mesmo dia -> "par provavel"
   (lancamento manual com hora/NSU divergente): sai dos dois alarmes e vai para conferencia.
Mudou alguma regra? Crie nova VERSAO.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from ..domain.cartoes import (
    Abastecimento, Atribuicao, Candidato, CartaoErp, Casamento, Investigacao, ParProvavel, TransacaoAdquirente,
)

VERSAO = "CARTOES_V1"
CORTE_AUTOMATICO = 80
CORTE_SUGESTAO = 50
JANELA_ABASTECIMENTO = timedelta(minutes=15)
TOLERANCIA_RELOGIO = timedelta(minutes=2)   # relogio da maquininha x concentrador
JANELA_SEM_NSU = timedelta(minutes=10)
CENTAVO = Decimal("0.01")


def _chave(v: str | None) -> str:
    return str(v or "").strip().lstrip("0").upper()


def casar(
    transacoes: Iterable[TransacaoAdquirente], cartoes: Iterable[CartaoErp]
) -> tuple[list[Casamento], list[TransacaoAdquirente], list[CartaoErp]]:
    livres_t = list(transacoes)
    livres_c = list(cartoes)
    casados: list[Casamento] = []

    indice: dict[str, CartaoErp] = {}
    for c in livres_c:
        for k in (c.nsu, c.nsu_tef, c.autorizacao):
            if _chave(k):
                indice.setdefault(_chave(k), c)
    for t in list(livres_t):
        for nome, k in (("nsu", t.nsu), ("autorizacao", t.autorizacao)):
            c = indice.get(_chave(k)) if _chave(k) else None
            if c is not None and c in livres_c:
                livres_t.remove(t)
                livres_c.remove(c)
                casados.append(Casamento(transacao=t, cartao=c, chave=nome))
                break

    # so transacoes sem NSU/autorizacao (PIX): cartao com NSU nunca casa por valor (esconderia divergencia)
    for t in sorted((t for t in livres_t if not _chave(t.nsu) and not _chave(t.autorizacao)), key=lambda t: t.momento):
        cands = [c for c in livres_c
                 if abs(c.valor - t.valor) < CENTAVO and abs(c.momento - t.momento) <= JANELA_SEM_NSU]
        if cands:
            c = min(cands, key=lambda c: abs(c.momento - t.momento))
            livres_t.remove(t)
            livres_c.remove(c)
            casados.append(Casamento(transacao=t, cartao=c, chave="valor_hora"))
    return casados, livres_t, livres_c


def pontuar(t: TransacaoAdquirente, a: Abastecimento, venda_em_dinheiro: bool) -> Candidato | None:
    if abs(a.valor - t.valor) >= CENTAVO:
        return None
    antes = t.momento - a.momento
    if not (-TOLERANCIA_RELOGIO <= antes <= JANELA_ABASTECIMENTO):
        return None
    minutos = max(antes, timedelta(0)) / timedelta(minutes=1)
    pontos, motivos = 35, ["valor igual"]
    pts_hora = round(30 * (1 - minutos / 15))
    pontos += pts_hora
    motivos.append(f"abastecido {minutos:.0f} min antes")
    if venda_em_dinheiro:
        pontos += 20
        motivos.append("venda lançada como dinheiro")
    if t.valor % 5 != 0:
        pontos += 15
        motivos.append("valor não redondo")
    return Candidato(abastecimento=a, pontos=pontos, motivos=tuple(motivos), venda_em_dinheiro=venda_em_dinheiro)


def investigar(
    t: TransacaoAdquirente,
    abastecimentos: Iterable[Abastecimento],
    itens_em_dinheiro: set[int],
) -> Investigacao:
    candidatos = sorted(
        (c for a in abastecimentos
         if (c := pontuar(t, a, a.venda_item_codigo in itens_em_dinheiro)) and c.pontos >= CORTE_SUGESTAO),
        key=lambda c: -c.pontos,
    )
    unico = len(candidatos) == 1
    melhor = candidatos[0] if candidatos else None
    if melhor and unico and melhor.pontos >= CORTE_AUTOMATICO:
        atribuicao, frentista = Atribuicao.ATRIBUIDO, melhor.abastecimento.frentista
    elif melhor:
        atribuicao, frentista = Atribuicao.SUGESTAO, None   # nunca escolhe frentista no empate
    else:
        atribuicao, frentista = Atribuicao.SEM_ABASTECIMENTO, None
    return Investigacao(
        transacao=t,
        atribuicao=atribuicao,
        frentista=frentista,
        candidatos=tuple(candidatos[:5]),
        troca_de_forma=bool(melhor and unico and melhor.venda_em_dinheiro),
    )


def parear_sobras(
    a_maior: Iterable[Investigacao], a_menor: Iterable[CartaoErp]
) -> tuple[list[Investigacao], list[CartaoErp], list[ParProvavel]]:
    livres_m = list(a_menor)
    sobra_maior: list[Investigacao] = []
    pares: list[ParProvavel] = []
    for inv in a_maior:
        t = inv.transacao
        cands = [c for c in livres_m if abs(c.valor - t.valor) < CENTAVO and c.momento.date() == t.momento.date()]
        if cands:
            c = min(cands, key=lambda c: abs(c.momento - t.momento))
            livres_m.remove(c)
            pares.append(ParProvavel(investigacao=inv, cartao=c))
        else:
            sobra_maior.append(inv)
    return sobra_maior, livres_m, pares
