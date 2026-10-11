"""Classificacao de evidencias existentes, sem consultas nem outro motor de casamento."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Iterable, Mapping

from ..domain.acoes_recebimentos import AcaoRecebimento, ConferenciaRecebimentos, DiaConferencia, FormaConferencia, TotalAdquirente, PagamentoAcao, ResponsavelRecebimento
from ..domain.cartoes import CartaoErp, Investigacao
from ..domain.fechamento import Caixa
from ..domain.tempo import formatar_data_hora
from ..domain.execucao import ResultadoDiario
from ..domain.recebimentos import ResultadoRecebimentos, ResumoCasados, ResumoForma, forma_recebimento
from ..rules.cartoes import agrupar_sobras, investigar

JANELA_CRUZADA = timedelta(minutes=30)


def classificar_recebimentos(
    resultado: ResultadoRecebimentos,
    *,
    caixas: Iterable[Caixa] = (),
    nomes: Mapping[int, str] | None = None,
) -> tuple[AcaoRecebimento, ...]:
    caixas = tuple(caixas)
    nomes = nomes or {}
    itens = []
    vistos_cartoes = set()
    consumidas = set()
    adquirentes = resultado.adquirentes
    cobertura = bool(adquirentes) and all(a.situacao == "ok" and a.evidencias_completas for a in adquirentes)

    def responsaveis(origem, momento):
        if isinstance(origem, Investigacao) and origem.candidatos:
            pontos = max(c.pontos for c in origem.candidatos)
            melhores = [c for c in origem.candidatos if c.pontos == pontos]
            return tuple(ResponsavelRecebimento(
                codigo=c.abastecimento.frentista, nome=c.abastecimento.nome_frentista or nomes.get(c.abastecimento.frentista),
                identificacao="empate" if len(melhores) > 1 else "atribuído" if origem.frentista is not None else "provável: sugestão",
                nota=min(100, c.pontos), motivos=c.motivos,
            ) for c in melhores)
        if origem.frentista is not None:
            return (ResponsavelRecebimento(codigo=origem.frentista, nome=origem.nome_frentista or nomes.get(origem.frentista),
                identificacao="atribuído ao lançamento", motivos=(origem.motivo_frentista,)),)
        abertos = [c for c in caixas if c.abertura <= momento and (c.fechamento is None or momento <= c.fechamento)]
        return tuple(ResponsavelRecebimento(codigo=c.funcionario_codigo, nome=nomes.get(c.funcionario_codigo),
            identificacao="provável: responsável pelo caixa no horário", caixa=c.codigo,
            motivos=(f"caixa {c.codigo}, aberto {formatar_data_hora(c.abertura)}",)) for c in abertos)

    def pagamento(inv):
        t = inv.transacao
        melhores = [c for c in inv.candidatos if c.pontos == max(x.pontos for x in inv.candidatos)] if inv.candidatos else []
        candidato = melhores[0] if len(melhores) == 1 else None
        return PagamentoAcao(
            adquirente=t.adquirente, momento=t.momento, valor=t.valor, forma=t.bandeira,
            nsu=f"…{t.nsu[-4:]}" if t.nsu else None, terminal=f"…{t.terminal[-4:]}" if t.terminal else None,
            abastecimento=candidato.abastecimento if candidato else None,
            forma_venda="Dinheiro" if candidato and candidato.venda_em_dinheiro else None,
            responsaveis=responsaveis(inv, t.momento),
        )

    def incluir(adquirente, origem, grupo, motivo, de=None, para=None, *, chave=None, troca=False, evidencias=(), nota=0, investigacoes=()):
        inv = origem if isinstance(origem, Investigacao) else None
        t = inv.transacao if inv else None
        c = origem if isinstance(origem, CartaoErp) else None
        if c and c.codigo in vistos_cartoes:
            return
        if c:
            vistos_cartoes.add(c.codigo)
        identidade = chave or (f"cartao:{c.codigo}" if c else f"transacao:{t.identificador}")
        momento, valor = (c.momento, c.valor) if c else (t.momento, t.valor)
        frentista, nome, motivo_f = origem.frentista, origem.nome_frentista, origem.motivo_frentista
        venda, caixa = (c.venda_codigo, c.caixa_codigo) if c else (None, None)
        pagamentos = tuple(pagamento(i) for i in investigacoes) if investigacoes else (pagamento(inv),) if inv else ()
        representantes = tuple(dict.fromkeys(r for p in pagamentos for r in p.responsaveis)) if pagamentos else responsaveis(origem, momento)
        pessoas = {r.codigo for r in representantes}
        if len(pessoas) == 1 and representantes:
            frentista, nome = representantes[0].codigo, representantes[0].nome
        if inv and inv.candidatos:
            candidato = inv.candidatos[0]
            a = candidato.abastecimento
            if inv.frentista is None and len(pessoas) == 1:
                motivo_f = "sugestão do motor; confirmar antes de retificar"
            venda = a.venda_codigo if len(pessoas) == 1 else None
            nota = min(100, candidato.pontos)
            evidencias = (*evidencias, f"Abastecimento {a.codigo}; item de venda {a.venda_item_codigo}; {candidato.pontos} pontos",
                          "Frentista sugerido; não é atribuição confirmada" if inv.frentista is None else "Frentista atribuído pelo motor")
        if caixa is None:
            elegiveis = {c.codigo for c in caixas if c.abertura <= momento and (c.fechamento is None or momento <= c.fechamento)}
            caixa = next(iter(elegiveis)) if len(elegiveis) == 1 else None
        itens.append(AcaoRecebimento(
            id=hashlib.sha256(f"{resultado.empresa_codigo}|{resultado.dia}|{adquirente}|{identidade}".encode()).hexdigest(),
            unidade=resultado.empresa_codigo, grupo=grupo, motivo=motivo, de=de, para=para,
            valor=valor, momento=momento, adquirente=adquirente,
            forma=c.administradora if c else t.bandeira or "Forma não informada",
            nsu=c.nsu if c else t.nsu, venda=venda, caixa=caixa,
            frentista=frentista, nome_frentista=nome, motivo_frentista=motivo_f,
            troca_de_forma=troca, evidencias=tuple(evidencias), lancamento=c.codigo if c else None,
            referencias_legadas=(f"{adquirente}:cartao:{c.codigo}",) if c else (f"{adquirente}:transacao:{t.identificador}",),
            nota_certeza=nota, pagamentos=pagamentos, responsaveis=representantes,
            tipo_inclusao=c.tipo_inclusao if c else None, momento_lancamento=c.momento if c else None,
            valor_lancamento=c.valor if c else None,
        ))

    for a in adquirentes:
        for alerta in a.alertas:
            if alerta.codigo == "CARTAO_POS_SEM_DETALHE":
                for cartao in alerta.cartoes:
                    adquirente_provavel = alerta.transacoes[0] if alerta.transacoes else None
                    incluir(
                        a.adquirente,
                        cartao,
                        2,
                        f"Detalhar cartão da venda {cartao.venda_codigo}",
                        cartao.administradora,
                        (
                            f"{adquirente_provavel.adquirente} {adquirente_provavel.bandeira or ''}".strip()
                            if adquirente_provavel else "adquirente a confirmar"
                        ),
                        evidencias=(alerta.codigo, alerta.mensagem),
                    )
                continue
            if alerta.codigo != "CARTAO_COBRANCA_DUPLICADA":
                continue
            cartao = alerta.cartoes[0] if alerta.cartoes else None
            casamento = next(
                (
                    item for item in a.detalhes_casados
                    if cartao is not None and item.cartao.codigo == cartao.codigo
                ),
                None,
            )
            extra = next(
                (
                    transacao for transacao in alerta.transacoes
                    if casamento is None or transacao.identificador != casamento.transacao.identificador
                ),
                None,
            )
            if extra is not None:
                incluir(
                    a.adquirente,
                    investigar(extra, (), set()),
                    3,
                    "Cobrança em duplicidade; verificar estorno ao cliente (não lançar)",
                    evidencias=(alerta.codigo, alerta.mensagem),
                )
        for c in a.sem_fonte:
            incluir(a.adquirente, c, 4, "Fonte não disponível; conferir com extrato/comprovante",
                    evidencias=("RN-CARTAO-009",))
    # Uma transacao cruzada pode justificar apenas um registro ERP.
    for a in adquirentes:
        for c in a.a_menor:
            if c.codigo in vistos_cartoes:
                continue
            if "PIX CNPJ" in c.administradora.upper() or a.situacao != "ok":
                incluir(a.adquirente, c, 4, "Sem fonte transacional para conferir; exige comprovante/extrato",
                        evidencias=("RN-CARTAO-009" if "PIX CNPJ" in c.administradora.upper() else a.erro or a.situacao,))
                continue
            candidatos = [
                (outro, inv) for outro in adquirentes if outro.situacao == "ok"
                for inv in outro.a_maior
                if (outro.adquirente, inv.transacao.identificador) not in consumidas
                and inv.transacao.valor == c.valor and inv.transacao.momento.date() == c.momento.date()
                and abs(inv.transacao.momento - c.momento) <= JANELA_CRUZADA
            ]
            ocupados = [
                par for outro in adquirentes for par in outro.detalhes_casados
                if par.cartao.codigo != c.codigo and par.transacao.valor == c.valor
                and par.transacao.momento.date() == c.momento.date()
                and abs(par.transacao.momento - c.momento) <= JANELA_CRUZADA
            ]
            if len(candidatos) == 1 and not ocupados:
                outro, inv = candidatos[0]
                # Unicidade reversa: nao escolher arbitrariamente entre dois ERP.
                reversos = [
                    cartao for fonte in adquirentes for cartao in fonte.a_menor
                    if cartao.valor == inv.transacao.valor and cartao.momento.date() == inv.transacao.momento.date()
                    and abs(cartao.momento - inv.transacao.momento) <= JANELA_CRUZADA
                ]
                if len(reversos) == 1:
                    consumidas.add((outro.adquirente, inv.transacao.identificador))
                    incluir(a.adquirente, c, 2, "Pago em outra adquirente/forma; retificar o registro existente",
                            c.administradora, f"{outro.adquirente} {inv.transacao.bandeira or ''}".strip(),
                            troca=True, nota=70, investigacoes=(inv,), evidencias=(f"Busca cruzada: {outro.adquirente}, {formatar_data_hora(inv.transacao.momento)}, NSU final {(inv.transacao.nsu or '')[-4:]}",))
                    continue
            combinacoes = []
            for outro in adquirentes:
                if outro.situacao != "ok" or outro.adquirente == a.adquirente:
                    continue
                livres = [
                    inv for inv in outro.a_maior
                    if (outro.adquirente, inv.transacao.identificador) not in consumidas
                    and inv.transacao.momento.date() == c.momento.date()
                    and abs(inv.transacao.momento - c.momento) <= JANELA_CRUZADA
                ]
                _, _, grupos = agrupar_sobras(livres, [c.model_copy(update={"motivo": None})])
                if grupos:
                    combinacoes.append((outro, grupos[0]))
            if len(combinacoes) == 1 and not candidatos and not ocupados:
                outro, grupo = combinacoes[0]
                outros_cartoes = [
                    cartao for fonte in adquirentes for cartao in fonte.a_menor
                    if cartao.codigo != c.codigo and cartao.momento.date() == c.momento.date()
                    and (
                        any(cartao.valor == inv.transacao.valor and abs(cartao.momento - inv.transacao.momento) <= JANELA_CRUZADA
                            for inv in grupo.investigacoes)
                        or agrupar_sobras(
                            [inv for inv in grupo.investigacoes if abs(cartao.momento - inv.transacao.momento) <= JANELA_CRUZADA],
                            [cartao.model_copy(update={"motivo": None})],
                        )[2]
                    )
                ]
                if not outros_cartoes:
                    consumidas.update((outro.adquirente, inv.transacao.identificador) for inv in grupo.investigacoes)
                    incluir(a.adquirente, c, 2, "Compensação por combinação única; confirmar desmembramento e adquirente",
                            f"1 {c.administradora}", f"{len(grupo.investigacoes)} pagamentos {outro.adquirente}",
                            troca=True, nota=60, investigacoes=grupo.investigacoes, evidencias=tuple(
                                f"{outro.adquirente} · R$ {inv.transacao.valor} · {formatar_data_hora(inv.transacao.momento)} · NSU final {(inv.transacao.nsu or '')[-4:]}"
                                for inv in grupo.investigacoes))
                    continue
            if candidatos or ocupados or combinacoes or not cobertura:
                incluir(a.adquirente, c, 4, "Busca cruzada ambígua ou evidência incompleta; não presumir ausência de pagamento",
                        evidencias=("Busca cruzada requer fontes completas e candidato único, sem reutilização",))
            else:
                incluir(a.adquirente, c, 3, "SUSPEITA DE LANÇAMENTO SEM LASTRO — apurar; só após apuração considerar exclusão",
                        evidencias=("Nenhuma transação livre de mesmo valor/dia em até 30 minutos nas fontes gravadas",))
    for a in adquirentes:
        for inv in a.a_maior:
            if (a.adquirente, inv.transacao.identificador) in consumidas:
                continue
            top = inv.candidatos[0] if inv.candidatos else None
            dinheiro = inv.troca_de_forma or bool(
                top and top.venda_em_dinheiro and top.pontos >= 80
                and (len(inv.candidatos) == 1 or top.pontos > inv.candidatos[1].pontos)
            )
            if a.situacao != "ok":
                incluir(a.adquirente, inv, 4, "Fonte indisponível; conferir à mão")
            elif dinheiro:
                incluir(a.adquirente, inv, 2, "Venda em dinheiro com pagamento eletrônico; confirmar evidência e retificar, sem duplicar",
                        "Dinheiro", f"{a.adquirente} {inv.transacao.bandeira or ''}".strip(),
                        troca=True, evidencias=("RN-CARTAO-004", "Troca de forma indicada pelo motor existente"))
            elif inv.candidatos or any(
                c.valor == inv.transacao.valor and c.momento.date() == inv.transacao.momento.date()
                and abs(c.momento - inv.transacao.momento) <= JANELA_CRUZADA
                for fonte in adquirentes for c in fonte.a_menor
            ):
                incluir(a.adquirente, inv, 4, "Há venda candidata em outra forma, mas vínculo não é inequívoco; conferir antes de lançar",
                        evidencias=("Candidatos do motor existentes; não afirmar ausência de lançamento",))
            else:
                incluir(a.adquirente, inv, 1, "Recebido sem lançamento nem venda candidata nos dados consultados",
                        para=f"{a.adquirente} {inv.transacao.bandeira or ''}".strip())
        for p in a.pares_provaveis:
            incluir(a.adquirente, p.cartao, 2, "Par provável; confirmar e corrigir hora/NSU/vínculo do lançamento existente",
                    f"{p.cartao.administradora} {p.cartao.momento:%H:%M:%S}",
                    f"{a.adquirente} {p.investigacao.transacao.bandeira or ''} {p.investigacao.transacao.momento:%H:%M:%S}",
                    nota=50, investigacoes=(p.investigacao,), evidencias=("RN-CARTAO-002", "Mesmo valor/dia; associação provável, não confirmação automática"))
        for g in a.grupos_provaveis:
            incluir(a.adquirente, g.cartao, 2, "Grupo provável; confirmar desmembramento sem duplicar o total",
                    f"1 {g.cartao.administradora}", f"{len(g.investigacoes)} pagamentos",
                    nota=50, investigacoes=g.investigacoes, evidencias=tuple(f"{formatar_data_hora(i.transacao.momento)} · R$ {i.transacao.valor}" for i in g.investigacoes))
        for p in (*a.detalhes_casados, *a.divergencias_valor):
            c, t = p.cartao, p.transacao
            forma_errada = a.adquirente == "PREMMIA" and forma_recebimento(c.administradora) != forma_recebimento(t.bandeira)
            if a.adquirente != "PREMMIA" and t.bandeira:
                portal = t.bandeira.upper().replace("É", "E")
                erp = c.administradora.upper().replace("É", "E")
                forma_errada = any(tipo in portal and tipo not in erp for tipo in ("PIX", "CREDITO", "DEBITO"))
            hora_errada = (
                c.tipo_inclusao == "Manualmente" and c.momento != t.momento
                and (c.venda_codigo is None or (c.momento.hour, c.momento.minute, c.momento.second) == (1, 0, 0))
            )
            if p.valor_divergente or forma_errada or hora_errada:
                incluir(a.adquirente, c, 2, "Pagamento identificado; corrigir forma, valor ou hora/vínculo, não criar outro",
                        f"{c.administradora} · R$ {c.valor} · {c.momento:%H:%M:%S}",
                        f"{a.adquirente} {t.bandeira or ''} · R$ {t.valor} · {t.momento:%H:%M:%S}",
                        troca=forma_errada, nota=100 if p.chave in {"nsu", "autorizacao", "cupom"} else 80,
                        investigacoes=(Investigacao(transacao=t, atribuicao="sem_abastecimento", frentista=c.frentista,
                            nome_frentista=c.nome_frentista, motivo_frentista=c.motivo_frentista, candidatos=(), troca_de_forma=False),),
                        evidencias=(f"Casamento {p.chave}; NSU final {(t.nsu or '')[-4:]}",))
        for c in a.sem_fonte:
            incluir(a.adquirente, c, 4, "Fonte não disponível; conferir com extrato/comprovante",
                    evidencias=("RN-CARTAO-009",))
        for alerta in a.alertas:
            if alerta.codigo in {
                "CARTAO_COBRANCA_DUPLICADA",
                "CARTAO_COBRANCA_DUPLICADA_ESTORNADA",
                "CARTAO_POS_SEM_DETALHE",
            }:
                continue
            for c in alerta.cartoes:
                if c.codigo not in vistos_cartoes and not any(p.cartao.codigo == c.codigo for p in a.detalhes_casados):
                    incluir(a.adquirente, c, 4, "Alerta sem comprovante individual gravado; conferir antes de recomendar alteração",
                            evidencias=(alerta.codigo,))
    return tuple(sorted(itens, key=lambda i: (i.grupo, i.momento, i.id)))


def aplicar_reincidencia(itens: Iterable[AcaoRecebimento]) -> tuple[AcaoRecebimento, ...]:
    itens = tuple(itens)
    grupos = defaultdict(dict)
    for i in itens:
        if i.frentista is not None and (i.grupo == 3 or (i.grupo == 2 and i.troca_de_forma)):
            grupos[(i.unidade, i.momento.year, i.momento.month, i.frentista)][i.id] = i
    saida = []
    for i in itens:
        ocorrencias = grupos.get((i.unidade, i.momento.year, i.momento.month, i.frentista), {})
        if i.id in ocorrencias and len(ocorrencias) >= 3:
            i = i.model_copy(update={"reincidente": True, "reincidencia_quantidade": len(ocorrencias),
                                     "reincidencia_total": sum((a.valor for a in ocorrencias.values()), Decimal(0))})
        saida.append(i)
    return tuple(saida)


def montar_conferencia(
    unidade, inicio, fim, registros: Iterable[ResultadoDiario],
    eventos: Mapping[str, dict] | None = None,
) -> ConferenciaRecebimentos:
    registros = tuple(registros)
    eventos = eventos or {}
    itens, avisos, formas = [], [], defaultdict(lambda: [0, Decimal(0), 0, Decimal(0)])
    qtd, valor = 0, Decimal(0)
    ja_conferidos = set()
    diario = []
    nomes_adquirentes = sorted({a.adquirente for r in registros for a in r.recebimentos.adquirentes})
    nomes = {}
    for r in registros:
        for a in r.recebimentos.adquirentes:
            investigacoes = (*a.a_maior, *(p.investigacao for p in a.pares_provaveis),
                            *(i for g in a.grupos_provaveis for i in g.investigacoes))
            for inv in investigacoes:
                if inv.frentista is not None and inv.nome_frentista:
                    nomes[inv.frentista] = inv.nome_frentista
                for c in inv.candidatos:
                    if c.abastecimento.frentista is not None and c.abastecimento.nome_frentista:
                        nomes[c.abastecimento.frentista] = c.abastecimento.nome_frentista
            for c in (*a.a_menor, *a.sem_fonte, *(p.cartao for p in a.detalhes_casados)):
                if c.frentista is not None and c.nome_frentista:
                    nomes[c.frentista] = c.nome_frentista
    for r in registros:
        if r.empresa_codigo != unidade:
            raise ValueError("Resultado fora do escopo da conferência.")
        caixas = tuple(c.caixa for c in r.fechamento.caixas) if r.fechamento else ()
        classificados = classificar_recebimentos(r.recebimentos, caixas=caixas, nomes=nomes)
        for a in r.recebimentos.adquirentes:
            ja_conferidos.update(i.id for i in classificados
                if i.adquirente == a.adquirente and i.lancamento in a.codigos_conferidos)
        itens.extend(classificados)
        if inicio <= r.dia <= fim:
            totais_dia = []
            for a in r.recebimentos.adquirentes:
                if a.situacao == "ok" and a.casados:
                    qtd += a.casados.quantidade - a.casados_valor_divergente.quantidade
                    valor += a.casados.total - sum((p.transacao.valor for p in a.divergencias_valor), Decimal(0))
                if not a.evidencias_completas or a.situacao != "ok":
                    avisos.append(f"{r.dia:%d/%m/%Y} · {a.adquirente}: {a.erro or 'detalhes individuais/fontes incompletos; totais não comprovam forma/hora'}")
                for f in a.formas:
                    v = formas[(a.adquirente, f.forma)]
                    v[0] += f.portal.quantidade
                    v[1] += f.portal.total
                    v[2] += f.webposto.quantidade
                    v[3] += f.webposto.total
                if a.sem_fonte:
                    avisos.append(f"{r.dia:%d/%m/%Y} · {a.adquirente}: parte dos recebimentos exige extrato/conferência manual; diferença diária pendente")
                    totais_dia.append(TotalAdquirente(adquirente=a.adquirente, situacao="fonte parcial"))
                elif a.situacao != "ok" or not a.formas:
                    totais_dia.append(TotalAdquirente(adquirente=a.adquirente, situacao=a.situacao if a.situacao != "ok" else "sem totais por forma"))
                else:
                    recebido = sum((f.portal.total for f in a.formas), Decimal(0))
                    webposto = sum((f.webposto.total for f in a.formas), Decimal(0))
                    totais_dia.append(TotalAdquirente(adquirente=a.adquirente, situacao="ok",
                                                     recebido=recebido, webposto=webposto, diferenca=recebido-webposto))
            presentes = {t.adquirente for t in totais_dia}
            totais_dia.extend(TotalAdquirente(adquirente=n, situacao="sem resultado") for n in nomes_adquirentes if n not in presentes)
            compensacao = any((t.diferenca or 0) > 0 for t in totais_dia) and any((t.diferenca or 0) < 0 for t in totais_dia)
            pendentes = any(i.grupo in {1, 3, 4} for i in classificados)
            diario.append(DiaConferencia(
                dia=r.dia, adquirentes=tuple(sorted(totais_dia, key=lambda t: t.adquirente)),
                diferenca=sum((t.diferenca for t in totais_dia), Decimal(0)) if all(t.diferenca is not None for t in totais_dia) else None,
                compensacao=("compensação a apurar" if pendentes else "compensacao identificada") if compensacao else "sem compensacao",
            ))
    faltantes = (fim - inicio).days + 1 - sum(inicio <= r.dia <= fim for r in registros)
    if faltantes:
        avisos.append(f"{faltantes} dias sem resultado gravado no período; sem consulta externa")
        dias_gravados = {d.dia for d in diario}
        for indice in range((fim-inicio).days + 1):
            dia = inicio + timedelta(days=indice)
            if dia not in dias_gravados:
                diario.append(DiaConferencia(dia=dia, adquirentes=tuple(
                    TotalAdquirente(adquirente=n, situacao="sem resultado") for n in nomes_adquirentes)))
    com_eventos = []
    for i in itens:
        evento = eventos.get(i.id)
        if evento and evento.get("tipo", "manual") == "manual" and i.grupo == 4:
            i = i.model_copy(update={"conferencia": evento["decisao"], "observacao": evento["observacao"],
                                     "grupo": 3 if evento["decisao"] == "nao_encontrado" else 4,
                                     "motivo": "SUSPEITA DE LANÇAMENTO SEM LASTRO — não encontrado na conferência manual; apurar"
                                     if evento["decisao"] == "nao_encontrado" else i.motivo})
            if evento["decisao"] == "conferido" and i.id not in ja_conferidos and inicio <= i.momento.date() <= fim:
                qtd += 1
                valor += i.valor
            elif evento["decisao"] == "nao_encontrado" and i.id in ja_conferidos and inicio <= i.momento.date() <= fim:
                qtd -= 1
                valor -= i.valor
        elif evento and evento.get("tipo") == "proposta" and i.grupo == 2:
            i = i.model_copy(update={"proposta_status": evento["decisao"], "observacao": evento["observacao"]})
        com_eventos.append(i)
    itens = aplicar_reincidencia(com_eventos)
    totais_periodo = []
    for nome in nomes_adquirentes:
        totais = [a for d in diario for a in d.adquirentes if a.adquirente == nome]
        completo = all(t.diferenca is not None for t in totais) and len(totais) == (fim-inicio).days + 1
        totais_periodo.append(TotalAdquirente(
            adquirente=nome, situacao="ok" if completo else "pendente",
            recebido=sum((t.recebido for t in totais), Decimal(0)) if completo else None,
            webposto=sum((t.webposto for t in totais), Decimal(0)) if completo else None,
            diferenca=sum((t.diferenca for t in totais), Decimal(0)) if completo else None,
        ))
    return ConferenciaRecebimentos(
        unidade=unidade, inicio=inicio, fim=fim,
        conferidos=ResumoCasados(quantidade=qtd, total=valor),
        itens=tuple(i for i in itens if inicio <= i.momento.date() <= fim),
        formas=tuple(FormaConferencia(adquirente=a, resumo=ResumoForma(
            forma=f, portal=ResumoCasados(quantidade=v[0], total=v[1]),
            webposto=ResumoCasados(quantidade=v[2], total=v[3]), diferenca=v[1]-v[3],
        )) for (a, f), v in sorted(formas.items())),
        avisos=tuple(dict.fromkeys(avisos)),
        diario=tuple(sorted(diario, key=lambda d: d.dia)), totais_adquirentes=tuple(totais_periodo),
        diferenca_periodo=sum((d.diferenca for d in diario), Decimal(0)) if all(d.diferenca is not None for d in diario) else None,
    )
