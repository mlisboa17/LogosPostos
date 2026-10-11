"""Conciliacao adquirente x webPosto e investigacao por abastecimento — CARTOES_V3_3.

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
6. Duas ou mais sobras a maior que somam o valor de uma sobra a menor no mesmo dia
   formam um "grupo provavel" se houver uma unica combinacao (ate 4 recebimentos).
Mudou alguma regra? Crie nova VERSAO.
7. Mesmo NSU/autorizacao exige conferir valor; cancelamentos nao casam.
8. Codigo repetido no portal: valor/dia e horario mais proximo, sem reutilizar ERP.
   Duplicidade sem usos correspondentes no portal conserva o alerta legado.
"""

from __future__ import annotations

from itertools import combinations
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from ..domain.cartoes import (
    Abastecimento, Atribuicao, Candidato, CartaoErp, Casamento, GrupoProvavel, Investigacao, ParProvavel,
    TransacaoAdquirente,
)

VERSAO = "CARTOES_V3_3"
logger = logging.getLogger(__name__)
CORTE_AUTOMATICO = 80
CORTE_SUGESTAO = 50
JANELA_ABASTECIMENTO = timedelta(minutes=15)
TOLERANCIA_RELOGIO = timedelta(minutes=2)   # relogio da maquininha x concentrador
JANELA_SEM_NSU = timedelta(minutes=10)
CENTAVO = Decimal("0.01")


def _chave(v: str | None) -> str:
    return str(v or "").strip().lstrip("0").upper()


def _codigo_corresponde(t: TransacaoAdquirente, c: CartaoErp) -> bool:
    codigo = str(t.nsu or "").strip().upper()
    return bool(codigo) and (
        _chave(codigo) in {_chave(c.nsu), _chave(c.nsu_tef)}
        or bool(c.nsu and "-" in c.nsu and c.nsu.rsplit("-", 1)[1].strip().upper() == codigo)
    )


def candidato_pos(t: TransacaoAdquirente, c: CartaoErp) -> bool:
    return (
        t.adquirente.upper() == "PREMMIA"
        and (
            c.administradora.strip().upper() == "POS PREMMIA"
            or (c.administradora.strip().upper() == "PREMMIA PIX" and (t.bandeira or "").strip().upper() == "PIX")
        )
        and c.valor == t.valor
        and c.momento.date() == t.momento.date()
        and abs(c.momento - t.momento) <= JANELA_SEM_NSU
    )


def grupos_nsu_repetido(
    cartoes: Iterable[CartaoErp], transacoes: Iterable[TransacaoAdquirente] = (),
) -> list[list[CartaoErp]]:
    transacoes = [t for t in transacoes if t.situacao is None]
    grupos: list[tuple[set[tuple], list[CartaoErp]]] = []
    autorizacoes: dict[str, set[tuple[Decimal, date]]] = {}
    for cartao in sorted(cartoes, key=lambda c: (c.momento, c.codigo)):
        chaves = {("nsu", _chave(k)) for k in (cartao.nsu, cartao.nsu_tef) if _chave(k)}
        autorizacao = _chave(cartao.autorizacao)
        if autorizacao:
            contexto = (cartao.valor, cartao.momento.date())
            anteriores = autorizacoes.setdefault(autorizacao, set())
            if anteriores and contexto not in anteriores:
                logger.debug(
                    "Autorizacao repetida com valor/dia diferentes ignorada cartao=%s",
                    cartao.codigo,
                )
            anteriores.add(contexto)
            chaves.add(("autorizacao", autorizacao, *contexto))
        if not chaves:
            continue
        relacionados = [grupo for grupo in grupos if grupo[0] & chaves]
        membros = [cartao]
        for grupo in relacionados:
            chaves |= grupo[0]
            membros.extend(grupo[1])
            grupos.remove(grupo)
        grupos.append((chaves, membros))
    repetidos = [
        sorted(membros, key=lambda c: (c.momento, c.codigo))
        for _, membros in grupos
        if len(membros) > 1
    ]
    saida = []
    for grupo in repetidos:
        livres = list(transacoes)
        validos = True
        for c in grupo:
            candidatos = [
                t for t in livres
                if _codigo_corresponde(t, c)
                and t.valor == c.valor and t.momento.date() == c.momento.date()
            ]
            if not candidatos:
                validos = False
                break
            livres.remove(min(candidatos, key=lambda t: abs(t.momento - c.momento)))
        if not validos:
            saida.append(grupo)
    return saida


def casar(
    transacoes: Iterable[TransacaoAdquirente], cartoes: Iterable[CartaoErp]
) -> tuple[list[Casamento], list[TransacaoAdquirente], list[CartaoErp]]:
    transacoes = list(transacoes)
    livres_t = [t for t in transacoes if t.situacao is None]
    cartoes = list(cartoes)
    repetidos = [
        c for grupo in grupos_nsu_repetido(cartoes, livres_t)
        if not any(
            sum(_chave(outro.nsu) == _chave(t.nsu) for outro in livres_t) > 1
            and any(_codigo_corresponde(t, membro) for membro in grupo)
            for t in livres_t if _chave(t.nsu)
        )
        for c in grupo[1:]
    ]
    livres_c = [c for c in cartoes if c not in repetidos]
    casados: list[Casamento] = []

    indice: dict[str, CartaoErp] = {}
    for c in livres_c:
        for k in (c.nsu, c.nsu_tef, c.autorizacao):
            if _chave(k):
                indice.setdefault(_chave(k), c)
    for t in list(livres_t):
        codigo_repetido = _chave(t.nsu) and sum(
            _chave(outro.nsu) == _chave(t.nsu)
            for outro in transacoes if outro.situacao is None
        ) > 1
        if codigo_repetido:
            candidatos = [
                c for c in livres_c
                if _codigo_corresponde(t, c) and c.valor == t.valor
                and c.momento.date() == t.momento.date()
            ]
            if candidatos:
                c = min(candidatos, key=lambda c: (abs(c.momento - t.momento), c.codigo))
                livres_t.remove(t)
                livres_c.remove(c)
                chave = "nsu" if _chave(t.nsu) in {_chave(c.nsu), _chave(c.nsu_tef)} else "cupom"
                casados.append(Casamento(transacao=t, cartao=c, chave=chave))
            continue
        for nome, k in (("nsu", t.nsu), ("autorizacao", t.autorizacao)):
            c = indice.get(_chave(k)) if _chave(k) else None
            if c is not None and c in livres_c:
                livres_t.remove(t)
                livres_c.remove(c)
                diferenca = c.valor - t.valor
                casados.append(
                    Casamento(
                        transacao=t,
                        cartao=c,
                        chave=nome,
                        valor_divergente=abs(diferenca) >= CENTAVO,
                        diferenca=diferenca,
                    )
                )
                break

    for t in list(livres_t):
        codigo = str(t.nsu or "").strip().upper()
        cands = [
            c for c in livres_c
            if codigo and c.nsu and "-" in c.nsu
            and c.nsu.rsplit("-", 1)[1].strip().upper() == codigo
            and c.valor == t.valor and c.momento.date() == t.momento.date()
        ]
        repetido = sum(
            str(outro.nsu or "").strip().upper() == codigo
            for outro in transacoes if outro.situacao is None
        ) > 1
        if cands and (repetido or (len(cands) == 1 and sum(
            str(outro.nsu or "").strip().upper() == codigo
            and outro.valor == t.valor and outro.momento.date() == t.momento.date()
            for outro in livres_t
        ) == 1)):
            c = min(cands, key=lambda candidato: (abs(candidato.momento - t.momento), candidato.codigo))
            livres_t.remove(t)
            livres_c.remove(c)
            casados.append(Casamento(transacao=t, cartao=c, chave="cupom"))

    elegiveis_pos = {
        t.identificador: [c for c in livres_c if candidato_pos(t, c)]
        for t in livres_t
    }
    for t in list(livres_t):
        cands = elegiveis_pos[t.identificador]
        if len(cands) != 1:
            continue
        c = cands[0]
        if sum(c in cs for cs in elegiveis_pos.values()) != 1:
            continue
        livres_t.remove(t)
        livres_c.remove(c)
        casados.append(Casamento(transacao=t, cartao=c, chave="valor_hora"))

    # Preserve o casamento legado de PIX sem NSU, exceto Premmia ambiguo.
    for t in sorted((t for t in livres_t if not _chave(t.nsu) and not _chave(t.autorizacao)), key=lambda t: t.momento):
        cands = [c for c in livres_c
                 if c.administradora.strip().upper() not in {"POS PREMMIA", "PREMMIA PIX"}
                 and abs(c.valor - t.valor) < CENTAVO and abs(c.momento - t.momento) <= JANELA_SEM_NSU]
        if cands:
            c = min(cands, key=lambda c: abs(c.momento - t.momento))
            livres_t.remove(t)
            livres_c.remove(c)
            casados.append(Casamento(transacao=t, cartao=c, chave="valor_hora"))
    return casados, livres_t, livres_c + repetidos


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
        nome_frentista=(
            melhor.abastecimento.nome_frentista if melhor and frentista is not None else None
        ),
        motivo_frentista="atribuição ambígua" if melhor else "sem abastecimento compatível",
    )


def parear_sobras(
    a_maior: Iterable[Investigacao], a_menor: Iterable[CartaoErp]
) -> tuple[list[Investigacao], list[CartaoErp], list[ParProvavel]]:
    livres_m = list(a_menor)
    sobra_maior: list[Investigacao] = []
    pares: list[ParProvavel] = []
    for inv in a_maior:
        t = inv.transacao
        cands = [
            c
            for c in livres_m
            if not c.motivo
            and abs(c.valor - t.valor) < CENTAVO
            and c.momento.date() == t.momento.date()
        ]
        if cands:
            c = min(cands, key=lambda c: abs(c.momento - t.momento))
            livres_m.remove(c)
            pares.append(ParProvavel(investigacao=inv, cartao=c))
        else:
            sobra_maior.append(inv)
    return sobra_maior, livres_m, pares


def agrupar_sobras(
    a_maior: Iterable[Investigacao],
    a_menor: Iterable[CartaoErp],
    max_itens: int = 4,
    max_candidatos: int = 20,
) -> tuple[list[Investigacao], list[CartaoErp], list[GrupoProvavel]]:
    sobra_maior = list(a_maior)
    sobra_menor = list(a_menor)
    grupos: list[GrupoProvavel] = []

    for cartao in list(sobra_menor):
        if cartao.motivo:
            continue
        candidatos = sorted(
            (
                (indice, investigacao)
                for indice, investigacao in enumerate(sobra_maior)
                if investigacao.transacao.momento.date() == cartao.momento.date()
            ),
            key=lambda candidato: abs(candidato[1].transacao.momento - cartao.momento),
        )[:max_candidatos]
        combinacao_unica: tuple[tuple[int, Investigacao], ...] | None = None
        quantidade_combinacoes = 0
        for tamanho in range(2, min(max_itens, len(candidatos)) + 1):
            for combinacao in combinations(candidatos, tamanho):
                total = sum((investigacao.transacao.valor for _, investigacao in combinacao), Decimal(0))
                if abs(total - cartao.valor) < CENTAVO:
                    quantidade_combinacoes += 1
                    if quantidade_combinacoes > 1:
                        break
                    combinacao_unica = combinacao
            if quantidade_combinacoes > 1:
                break
        if quantidade_combinacoes == 1 and combinacao_unica is not None:
            grupos.append(GrupoProvavel(
                investigacoes=tuple(
                    investigacao for _, investigacao in sorted(combinacao_unica, key=lambda item: item[0])
                ),
                cartao=cartao,
            ))
            indices_usados = {indice for indice, _ in combinacao_unica}
            sobra_maior = [
                investigacao for indice, investigacao in enumerate(sobra_maior)
                if indice not in indices_usados
            ]
            sobra_menor.remove(cartao)

    return sobra_maior, sobra_menor, grupos
