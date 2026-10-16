"""Decompõe a diferença de dinheiro sem inventar pagamentos ou responsáveis."""
from decimal import Decimal

from ..domain.execucao import ResultadoDiario
from ..domain.explicacao import ExplicacaoCaixa, ParteFalta
from ..domain.models import Unidade
from .resumo_diario import identificar_caixa, moeda_br


def explicar_falta(registro: ResultadoDiario, unidade: Unidade, nomes=None) -> tuple[ExplicacaoCaixa, ...]:
    caixas = [a.caixa for a in registro.fechamento.caixas] if registro.fechamento else []
    partes = {p.referencia: p for p in registro.partes_falta}
    for adq in registro.recebimentos.adquirentes:
        if adq.adquirente != "PAGBANK":
            continue
        for inv in sorted(adq.a_maior, key=lambda i: i.transacao.momento):
            if not inv.troca_de_forma or len(inv.candidatos) != 1:
                continue
            candidato = inv.candidatos[0]
            ab, t = candidato.abastecimento, inv.transacao
            if (candidato.pontos < 90 or not candidato.venda_em_dinheiro or not ab.venda_codigo
                    or ab.empresa_codigo != registro.empresa_codigo or ab.valor != t.valor
                    or t.momento.date() != registro.dia or t.situacao is not None):
                continue
            caixa = next((c for c in caixas if c.codigo == ab.caixa_codigo), None)
            if caixa is None:
                continue
            pessoa = (
                f"{ab.nome_frentista or (nomes or {}).get(ab.frentista) or 'nome indisponível'} ({ab.frentista})"
                if ab.frentista is not None else "frentista não identificado"
            )
            forma = t.bandeira or "cartão"
            pix = any(n in forma.upper() for n in ("PIX", "BACEN"))
            dados_completos = bool(t.nsu and t.autorizacao and ab.frentista and t.valor <= 300)
            pix_lancavel = bool(registro.administradora_pix_pagbank and dados_completos)
            motivo_pix = registro.motivo_pix_pagbank
            if not motivo_pix:
                motivo_pix = (
                    "administradora PIX PagBank cadastrada, mas faltam NSU/autorização ou "
                    "os dados não atendem ao piloto — conferir e lançar à mão"
                    if registro.administradora_pix_pagbank else
                    "não há administradora de PIX PagBank cadastrada — lançar à mão"
                )
            descricao = f"{'PIX da maquininha' if pix else forma.title()} PagBank lançado como dinheiro — {pessoa}, {t.momento:%H:%M}"
            correcao = (
                (f"Posso lançar o PIX da maquininha ({registro.administradora_pix_pagbank}, "
                 f"NSU final {(t.nsu or '')[-4:]}) na venda {ab.venda_codigo} de {pessoa}. [Lançar]"
                 if pix_lancavel else
                 f"Na venda {ab.venda_codigo} de {pessoa}: "
                 f"{motivo_pix}.")
                if pix else
                f"Posso lançar o cartão ({forma.title()} PagSeguro, NSU final {(t.nsu or '')[-4:]}) "
                f"na venda {ab.venda_codigo} de {pessoa}. [Lançar]"
            )
            if not pix and not dados_completos:
                correcao = f"Na venda {ab.venda_codigo} de {pessoa}: faltam dados ou o valor não atende ao piloto; conferir à mão."
            ref = f"pagbank:{t.identificador}"
            partes[ref] = ParteFalta(referencia=ref, caixa_codigo=caixa.codigo, descricao=descricao,
                                    valor=t.valor, fonte="EDI PagBank × vendas", correcao=correcao,
                                    lancavel=pix_lancavel if pix else dados_completos)
    resultado = []
    for auditoria in registro.fechamento.caixas if registro.fechamento else ():
        dinheiro = [m for m in auditoria.modalidades if m.modalidade == "dinheiro"]
        if not auditoria.caixa.fechado or not dinheiro:
            continue
        falta = -sum((m.diferenca for m in dinheiro), Decimal(0))
        if not falta:
            continue
        cx = auditoria.caixa
        rotulo = identificar_caixa(unidade.apelido or unidade.nome, cx, caixas, nomes, curto=True)
        rotulo_sem_nomes = identificar_caixa(unidade.apelido or unidade.nome, cx, caixas, curto=True)
        evidencias = tuple(
            p.model_copy(update={"correcao": p.correcao.replace(rotulo_sem_nomes, rotulo)})
            for p in partes.values() if p.caixa_codigo == cx.codigo
        )
        resultado.append(ExplicacaoCaixa(
            caixa_codigo=cx.codigo,
            caixa=rotulo, consolidado=cx.consolidado,
            falta=falta, partes=tuple(sorted(evidencias, key=lambda p:
                                            0 if p.referencia.startswith("pagbank:") else 1)),
        ))
    return tuple(resultado)


def tabela_falta(explicacao: ExplicacaoCaixa) -> list[str]:
    def seguro(texto):
        return texto.replace("|", "/").replace("\n", " ")
    return [
        f"### {explicacao.caixa}", "",
        f"{'Falta' if explicacao.falta > 0 else 'Sobra'} de dinheiro: **{moeda_br(abs(explicacao.falta))}**.",
        *(["Provisório: caixa ainda não consolidado."] if not explicacao.consolidado else []),
        "", "| Parte | Valor | Fonte | O que corrigir |", "|---|---:|---|---|",
        *[f"| {seguro(p.descricao)} | {moeda_br(p.valor)} | {seguro(p.fonte)} | {seguro(p.correcao)} |" for p in explicacao.partes],
        f"| Sem explicação | {moeda_br(explicacao.sem_explicacao)} | — | Conferir na tela; não atribuir a um frentista sem evidência. |",
        f"| Total | {moeda_br(explicacao.falta)} | Dinheiro apresentado × apurado | Nenhuma correção executada. |",
    ]
