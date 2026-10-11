from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from src.modules.cash_reconciliation.adapters import pagbank_edi
from src.modules.cash_reconciliation.adapters.webposto_cartoes import para_abastecimento, para_cartao
from src.modules.cash_reconciliation.application.conciliar_cartoes import conciliar
from src.modules.cash_reconciliation.domain.cartoes import Abastecimento, Atribuicao, CartaoErp, TransacaoAdquirente
from src.modules.cash_reconciliation.domain.tempo import FUSO
from src.modules.cash_reconciliation.rules.cartoes import VERSAO, agrupar_sobras, casar, investigar

DIA = date(2026, 10, 5)


def T(valor, hora, nsu=None, aut=None, dia="2026-10-05", ident=None):
    return TransacaoAdquirente(adquirente="PAGBANK", identificador=ident or f"{hora}-{valor}", nsu=nsu, autorizacao=aut,
                               valor=Decimal(valor), momento=datetime.fromisoformat(f"{dia}T{hora}"))


def C(cod, valor, hora, nsu=None, aut=None, adm="VISA CREDITO PAGSEGURO", dia="2026-10-05"):
    return CartaoErp(codigo=cod, empresa_codigo=74014, venda_codigo=None, valor=Decimal(valor),
                     momento=datetime.fromisoformat(f"{dia}T{hora}"), administradora=adm,
                     nsu=nsu, nsu_tef=None, autorizacao=aut)


def A(cod, valor, hora, frentista=7, item=None):
    return Abastecimento(codigo=cod, empresa_codigo=74014, momento=datetime.fromisoformat(f"2026-10-05T{hora}"),
                         bico=1, valor=Decimal(valor), frentista=frentista, venda_item_codigo=item)


def test_sete_cupons_sinteticos_casam_pelo_final_do_nsu():
    codigos = [f"CUPOM{i:03d}" for i in range(7)]
    transacoes = [
        T(str(5 + i), f"{i:02d}:45:22", nsu=codigo, dia="2026-10-06")
        for i, codigo in enumerate(codigos)
    ]
    cartoes = [
        C(i, str(5 + i), f"{i:02d}:45:54", nsu=f"uuid-sintetico-{codigo.lower()}",
          adm="PREMMIA DESCONTO CUPOM", dia="2026-10-06")
        for i, codigo in enumerate(codigos)
    ]
    casados, maior, menor = casar(transacoes, cartoes)
    assert len(casados) == 7 and not maior and not menor
    assert all(c.chave == "cupom" for c in casados)


@pytest.mark.parametrize("nsu,valor,dia", [
    ("prefixo-CUPOM001-outro", "10", "2026-10-05"),
    ("prefixo-CUPOM001", "11", "2026-10-05"),
    ("prefixo-CUPOM001", "10", "2026-10-06"),
])
def test_cupom_exige_sufixo_valor_e_dia(nsu, valor, dia):
    casados, maior, menor = casar(
        [T("10", "10:00", nsu="CUPOM001")],
        [C(1, valor, "10:00", nsu=nsu, dia=dia)],
    )
    assert not casados and len(maior) == len(menor) == 1


def test_cupom_ambiguo_nao_casa():
    assert not casar(
        [T("10", "10:00", nsu="CUPOM001")],
        [C(i, "10", "10:00", nsu=f"{i}-CUPOM001") for i in (1, 2)],
    )[0]
    t = T("10", "10:00", nsu="CUPOM001")
    assert len(casar([t, t.model_copy(update={"identificador": "outro"})], [
        C(1, "10", "10:00", nsu="uuid-CUPOM001"),
    ])[0]) == 1


@pytest.mark.parametrize("sufixo", [True, False])
def test_v33_tres_usos_cupom_casam_por_dia_valor_e_horario_mais_proximo(sufixo):
    ts = [
        T("7", hora, nsu="CUPOM777", dia=dia, ident=str(i))
        for i, (dia, hora) in enumerate([
            ("2026-10-04", "14:28:35"), ("2026-10-04", "14:55:41"),
            ("2026-10-07", "14:17:33"),
        ])
    ]
    cs = [
        C(i, "7", hora, nsu=f"prefixo-{i}-CUPOM777" if sufixo else "CUPOM777",
          adm="PREMMIA DESCONTO CUPOM", dia=dia)
        for i, (dia, hora) in enumerate([
            ("2026-10-04", "14:30:08"), ("2026-10-04", "16:01:22"),
            ("2026-10-07", "14:18:00"),
        ])
    ]
    casados, maior, menor = casar(ts, list(reversed(cs)))
    assert len(casados) == 3 and not maior and not menor
    assert [(c.transacao.identificador, c.cartao.codigo) for c in casados] == [("0", 0), ("1", 1), ("2", 2)]
    assert all(c.chave == ("cupom" if sufixo else "nsu") for c in casados)
    resultado = conciliar(74014, "PREMMIA", date(2026, 10, 4), ts, cs, [], set())
    assert not any(a.codigo == "CARTAO_NSU_REPETIDO" for a in resultado.alertas)


def test_v33_codigo_repetido_nao_casa_outro_dia_ou_valor():
    ts = [
        T("7", "10:00", nsu="CUPOM777", ident="a"),
        T("7", "12:00", nsu="CUPOM777", ident="b"),
    ]
    cs = [C(1, "8", "10:00", nsu="CUPOM777"), C(2, "7", "12:00", nsu="x-CUPOM777", dia="2026-10-06")]
    casados, maior, menor = casar(ts, cs)
    assert not casados and len(maior) == len(menor) == 2


def test_v33_repetido_nao_reutiliza_erp_nem_casa_por_autorizacao_fora_do_dia():
    ts = [T("7", hora, nsu="CUPOM777", aut="AUT", ident=str(i)) for i, hora in enumerate(["10:00", "11:00"])]
    cs = [C(1, "7", "10:00", nsu="CUPOM777"), C(2, "7", "11:00", aut="AUT", dia="2026-10-06")]
    casados, maior, menor = casar(ts, cs)
    assert len(casados) == 1 and casados[0].cartao.codigo == 1
    assert len(maior) == len(menor) == 1


def test_v33_dois_usos_com_tres_lancamentos_casam_dois_e_preservam_sobra():
    ts = [T("7", hora, nsu="CUPOM777", ident=str(i)) for i, hora in enumerate(["10:00", "11:00"])]
    cs = [C(i, "7", hora, nsu="CUPOM777") for i, hora in enumerate(["10:00", "11:00", "12:00"])]
    casados, maior, menor = casar(ts, cs)
    assert [c.cartao.codigo for c in casados] == [0, 1]
    assert not maior and [c.codigo for c in menor] == [2]
    resultado = conciliar(74014, "PREMMIA", DIA, ts, cs, [], set())
    assert next(a.valor for a in resultado.alertas if a.codigo == "CARTAO_NSU_REPETIDO") == Decimal("7")


@pytest.mark.parametrize("administradora", ["POS PREMMIA", "PREMMIA PIX"])
def test_pos_premmia_unico_casa_e_ambiguo_fica_provavel(administradora):
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    t = T("200.02", "10:00", nsu="portal-sintetico").model_copy(update={"adquirente": "PREMMIA", "bandeira": "Pix"})
    cartoes = [C(i, "200.02", "10:05", nsu=f"erp-{i}", adm=administradora) for i in (1, 2)]
    unico = conciliar(74014, "PREMMIA", DIA, [t], cartoes[:1], [], set())
    assert unico.casados[0].chave == "valor_hora"
    ambiguo = conciliar(74014, "PREMMIA", DIA, [t], cartoes, [], set())
    assert not ambiguo.casados and not ambiguo.a_maior and not ambiguo.a_menor
    assert {p.cartao.codigo for p in ambiguo.pares_provaveis} == {1, 2}
    formas = RecebimentoAdquirente.de_resultado(ambiguo).formas
    assert sum(f.portal.quantidade for f in formas) == 1
    assert sum((f.portal.total for f in formas), Decimal(0)) == Decimal("200.02")
    assert sum(f.webposto.quantidade for f in formas) == 2


@pytest.mark.parametrize("administradora", ["POS PREMMIA", "PREMMIA PIX"])
def test_pos_exige_janela_dia_adquirente_e_unicidade_reversa(administradora):
    t = T("10", "10:00", nsu="portal").model_copy(update={"adquirente": "PREMMIA", "bandeira": "Pix"})
    for c in [C(1, "10", "10:11", nsu="erp", adm=administradora),
              C(1, "10", "10:00", nsu="erp", adm=administradora, dia="2026-10-06")]:
        assert not casar([t], [c])[0]
    c = C(1, "10", "10:00", nsu="erp", adm=administradora)
    assert not casar([t.model_copy(update={"adquirente": "PAGBANK"})], [c])[0]
    if administradora == "PREMMIA PIX":
        assert not casar([t.model_copy(update={"bandeira": "Desconto"})], [c])[0]
    assert not casar([t, t.model_copy(update={"identificador": "segundo", "nsu": "outro"})], [c])[0]
    limite = c.model_copy(update={"momento": t.momento + timedelta(minutes=10)})
    assert casar([t], [limite])[0][0].chave == "valor_hora"


def test_resultado_v31_antigo_abre_e_formas_novas_tem_valores():
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    t = T("10", "10:00", nsu="CUPOM001").model_copy(update={"bandeira": "Desconto", "adquirente": "PREMMIA"})
    resultado = conciliar(74014, "PREMMIA", DIA, [t], [
        C(1, "10", "10:01", nsu="uuid-CUPOM001", adm="PREMMIA DESCONTO CUPOM"),
    ], [], set())
    item = RecebimentoAdquirente.de_resultado(resultado)
    assert item.formas[0].portal.quantidade == item.formas[0].webposto.quantidade == 1
    assert item.formas[0].portal.total == Decimal("10") and item.formas[0].diferenca == 0
    antigo = item.model_dump(mode="json")
    antigo.pop("formas")
    antigo["proveniencia"]["versao_regra"] = "CARTOES_V3_1"
    assert RecebimentoAdquirente.model_validate(antigo).formas == ()


# ---------- casamento ----------

def test_casa_por_nsu_com_zeros_a_esquerda_e_por_autorizacao():
    casados, st, sc = casar([T("10", "10:00", nsu="00123"), T("20", "11:00", aut="m0031")],
                            [C(1, "10", "10:01", nsu="123"), C(2, "20", "11:00", aut="M0031")])
    assert [(c.cartao.codigo, c.chave) for c in casados] == [(1, "nsu"), (2, "autorizacao")] and not st and not sc


def test_pix_sem_nsu_casa_por_valor_e_hora():
    casados, st, sc = casar([T("1000", "07:14:07")], [C(9, "1000", "07:16:00", adm="PIX PAGBANK")])
    assert [c.chave for c in casados] == ["valor_hora"] and not st and not sc


def test_cartao_com_nsu_nunca_casa_so_por_valor():
    casados, st, sc = casar([T("50", "10:00", nsu="777")], [C(1, "50", "10:01", adm="PIX (venda) PIX")])
    assert not casados and len(st) == 1 and len(sc) == 1


def test_mesmo_valor_mesmo_dia_vira_par_provavel():
    from src.modules.cash_reconciliation.rules.cartoes import parear_sobras
    inv = investigar(T("1000", "07:14"), [], set())
    m, n, pares = parear_sobras([inv], [C(1, "1000", "01:00", adm="PIX PAGBANK"), C(2, "30", "05:00")])
    assert not m and [c.codigo for c in n] == [2] and pares[0].cartao.codigo == 1


def test_sobras_dos_dois_lados():
    casados, st, sc = casar([T("87.43", "10:00", nsu="1")], [C(1, "50", "12:00", nsu="2")])
    assert not casados and len(st) == 1 and [c.codigo for c in sc] == [1]


def test_agrupar_quatro_recebimentos_que_somam_lancamento_a_menor():
    investigacoes = [
        investigar(T("40.00", "10:00"), [], set()),
        investigar(T("45.00", "10:01"), [], set()),
        investigar(T("50.00", "10:02"), [], set()),
        investigar(T("44.45", "10:03"), [], set()),
    ]
    maior, menor, grupos = agrupar_sobras(investigacoes, [C(1, "179.45", "10:05")])
    assert not maior and not menor
    assert len(grupos) == 1
    assert grupos[0].investigacoes == tuple(investigacoes)


def test_agrupar_sobras_sem_combinacao_valida_nao_altera_itens():
    investigacoes = [investigar(T("40.00", "10:00"), [], set()), investigar(T("45.00", "10:01"), [], set())]
    cartao = C(1, "86.00", "10:05")
    maior, menor, grupos = agrupar_sobras(investigacoes, [cartao])
    assert maior == investigacoes and menor == [cartao] and not grupos


def test_agrupar_sobras_com_duas_combinacoes_validas_e_ambiguo():
    investigacoes = [
        investigar(T("10.00", "10:00"), [], set()),
        investigar(T("20.00", "10:01"), [], set()),
        investigar(T("30.00", "10:02"), [], set()),
        investigar(T("40.00", "10:03"), [], set()),
    ]
    cartao = C(1, "50.00", "10:05")
    maior, menor, grupos = agrupar_sobras(investigacoes, [cartao])
    assert maior == investigacoes and menor == [cartao] and not grupos


def test_agrupar_sobras_nao_combina_dias_diferentes():
    investigacoes = [
        investigar(T("40.00", "23:58", dia="2026-10-05"), [], set()),
        investigar(T("45.00", "00:01", dia="2026-10-06"), [], set()),
    ]
    cartao = C(1, "85.00", "00:02", dia="2026-10-06")
    maior, menor, grupos = agrupar_sobras(investigacoes, [cartao])
    assert maior == investigacoes and menor == [cartao] and not grupos


# ---------- investigacao ----------

def test_valor_quebrado_perto_e_em_dinheiro_atribui_sozinho():
    inv = investigar(T("87.43", "10:05"), [A(1, "87.43", "10:01", frentista=42, item=500)], {500})
    assert inv.atribuicao is Atribuicao.ATRIBUIDO and inv.frentista == 42 and inv.troca_de_forma
    assert inv.candidatos[0].pontos >= 80


def test_valor_redondo_sem_outra_evidencia_vira_sugestao():
    inv = investigar(T("50", "10:05"), [A(1, "50", "10:04")], set())
    assert inv.atribuicao is Atribuicao.SUGESTAO and inv.frentista is None


def test_empate_nunca_escolhe_frentista():
    inv = investigar(T("87.43", "10:05"), [A(1, "87.43", "10:02", frentista=1), A(2, "87.43", "10:03", frentista=2)], set())
    assert inv.atribuicao is Atribuicao.SUGESTAO and inv.frentista is None and len(inv.candidatos) == 2


def test_fora_da_janela_ou_valor_diferente_sem_abastecimento():
    inv = investigar(T("87.43", "10:05"), [A(1, "87.43", "09:30"), A(2, "87.44", "10:04")], set())
    assert inv.atribuicao is Atribuicao.SEM_ABASTECIMENTO and inv.candidatos == ()


def test_tolerancia_de_relogio_aceita_abastecimento_registrado_logo_apos():
    inv = investigar(T("87.43", "10:05"), [A(1, "87.43", "10:06", item=1)], {1})
    assert inv.atribuicao is Atribuicao.ATRIBUIDO


# ---------- caso de uso ----------

def test_conciliar_filtra_adquirente_e_dia():
    trans = [T("10", "10:00", nsu="1"), T("87.43", "10:05", ident="x"), T("5", "23:59", nsu="9", dia="2026-10-04")]
    cartoes = [C(1, "10", "10:00", nsu="1"), C(2, "30", "12:00", nsu="3"), C(3, "15", "12:00", adm="PREMMIA CREDITO"),
               C(4, "5", "00:01", nsu="9", dia="2026-10-06")]
    r = conciliar(74014, "PAGBANK", DIA, trans, cartoes, [A(1, "87.43", "10:02", frentista=5, item=1)], {1})
    assert [c.cartao.codigo for c in r.casados] == [1]
    assert [i.frentista for i in r.a_maior] == [5]
    assert [c.codigo for c in r.a_menor] == [2]          # Premmia nao e PagBank; o de 06/10 nao entra
    assert r.proveniencia.versao_regra == VERSAO


def test_conciliar_retorna_grupo_provavel_e_versao_cartoes_v3():
    transacoes = [
        T("40.00", "10:00", ident="g1"),
        T("45.00", "10:01", ident="g2"),
        T("50.00", "10:02", ident="g3"),
        T("44.45", "10:03", ident="g4"),
    ]
    resultado = conciliar(74014, "PAGBANK", DIA, transacoes, [C(1, "179.45", "10:05")], [], set())
    assert len(resultado.grupos_provaveis) == 1
    assert not resultado.a_maior and not resultado.a_menor
    assert resultado.proveniencia.versao_regra == "CARTOES_V3_4"


# ---------- adapters ----------

def test_pagbank_transacao_real_data_e_hora_separadas_e_filtro_de_status():
    base = {"tid": "T1", "nsu": "100577524027", "codigo_autorizacao": "M00312", "valor_total_transacao": 87.43,
            "data_inicial_transacao": "2026-10-05", "hora_inicial_transacao": "00:29:25", "status_pagamento": "1",
            "tipo_evento": "1", "instituicao_financeira": "VISA", "numero_serie_leitor": "SN1"}
    t = pagbank_edi.para_transacao(base)
    assert t.momento == datetime(2026, 10, 5, 0, 29, 25, tzinfo=FUSO) and t.valor == Decimal("87.43") and t.terminal == "SN1"
    assert (
        pagbank_edi.para_transacao({**base, "status_pagamento": "3"}).situacao
        == "tipo_evento=1;status_pagamento=3"
    )
    assert (
        pagbank_edi.para_transacao({**base, "tipo_evento": "2"}).situacao
        == "tipo_evento=2;status_pagamento=1"
    )


@pytest.mark.parametrize(
    "erp,recebido,codigo,severidade,diferenca",
    [
        ("150", "100", "CARTAO_VALOR_A_MENOR", "vermelho", "50"),
        ("100", "150", "CARTAO_VALOR_A_MAIOR", "laranja", "-50"),
        ("100.01", "100", "CARTAO_VALOR_A_MENOR", "vermelho", "0.01"),
    ],
)
def test_valor_divergente_mesmo_nsu(erp, recebido, codigo, severidade, diferenca):
    cartao = C(1, erp, "10:00", nsu="1234").model_copy(
        update={
            "frentista": 7,
            "nome_frentista": "Funcionário Sintético",
            "tipo_inclusao": "PDV-TEF",
        }
    )
    resultado = conciliar(
        74014, "PAGBANK", DIA, [T(recebido, "10:00", nsu="1234")], [cartao], [], set()
    )
    assert resultado.casados[0].valor_divergente
    assert resultado.casados[0].diferenca == Decimal(diferenca)
    assert resultado.alertas[0].codigo == codigo
    assert resultado.alertas[0].severidade == severidade
    assert "Funcionário Sintético (7)" in resultado.alertas[0].mensagem
    assert "PDV-TEF" in resultado.alertas[0].mensagem


def test_mesmo_nsu_valor_igual_sem_alerta_e_v2_abre():
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    resultado = conciliar(
        74014,
        "PAGBANK",
        DIA,
        [T("100", "10:00", nsu="1234")],
        [C(1, "100", "10:00", nsu="1234")],
        [],
        set(),
    )
    assert not resultado.casados[0].valor_divergente and not resultado.alertas
    antigo = RecebimentoAdquirente.model_validate(
        {
            "adquirente": "PAGBANK",
            "situacao": "ok",
            "casados": {"quantidade": 1, "total": "100"},
        }
    )
    assert antigo.casados_valor_divergente.quantidade == 0
    assert antigo.cancelados.quantidade == 0


def test_cancelada_mesmo_nsu_explica_a_menor_e_nao_pareia():
    cancelada = T("100", "10:05", nsu="1234").model_copy(update={"situacao": "cancelada"})
    resultado = conciliar(
        74014,
        "PAGBANK",
        DIA,
        [cancelada, T("100", "11:00", nsu="9999")],
        [C(1, "100", "10:00", nsu="1234")],
        [],
        set(),
    )
    assert not resultado.casados and not resultado.pares_provaveis
    assert "cancelada no PagBank em 05/10/2026 10:05" == resultado.a_menor[0].motivo
    assert resultado.cancelados == (cancelada,)


def test_totais_v3_somam_diferencas_assinadas_e_eventos_separados():
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    transacoes = [
        T("100", "10:00", nsu="1234"),
        T("150", "11:00", nsu="5678"),
        T("20", "12:00", nsu="9999").model_copy(update={"situacao": "cancelada"}),
        T("30", "13:00", nsu="8888").model_copy(update={"situacao": "tipo_evento=X"}),
    ]
    resultado = conciliar(
        74014, "PAGBANK", DIA, transacoes,
        [C(1, "150", "10:00", nsu="1234"), C(2, "100", "11:00", nsu="5678")],
        [], set(),
    )
    recebimento = RecebimentoAdquirente.de_resultado(resultado)
    assert recebimento.casados_valor_divergente.quantidade == 2
    assert recebimento.casados_valor_divergente.total == Decimal("0")
    assert recebimento.cancelados.quantidade == 2
    assert recebimento.cancelados.total == Decimal("50")


def test_nsu_repetido_premmia_so_primeiro_casa_demais_nao_pareiam():
    cartoes = [
        C(1, "30", "23:04", nsu="1234", adm="PIX PREMMIA").model_copy(update={"venda_codigo": 11}),
        C(2, "30", "23:09", nsu="1234", adm="PIX PREMMIA").model_copy(update={"venda_codigo": 22}),
    ]
    resultado = conciliar(
        74014,
        "PAGBANK",
        DIA,
        [T("30", "23:04", nsu="1234"), T("30", "23:09", nsu="7777")],
        cartoes,
        [],
        set(),
    )
    assert len(resultado.casados) == 1
    assert resultado.casados[0].cartao.codigo == 1
    assert resultado.alertas[0].codigo == "CARTAO_NSU_REPETIDO"
    assert resultado.alertas[0].severidade == "vermelho"
    assert resultado.a_menor[0].motivo == "NSU já usado na venda 11"
    assert not resultado.pares_provaveis


async def test_pagbank_le_todas_as_paginas(monkeypatch):
    monkeypatch.setenv("PAGBANK_USER_1", "u")
    monkeypatch.setenv("PAGBANK_TOKEN_1", "t")

    def handler(req: httpx.Request) -> httpx.Response:
        pagina = int(req.url.params["pageNumber"])
        det = [{"tid": f"P{pagina}", "valor_total_transacao": 1, "data_inicial_transacao": "2026-10-05",
                "hora_inicial_transacao": "10:00:00", "status_pagamento": "1", "tipo_evento": "1"}]
        return httpx.Response(200, json={"pagination": {"totalPages": 3, "page": pagina}, "detalhes": det})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t") as c:
        r = await pagbank_edi.buscar_transacoes(1, DIA, client=c)
    assert [t.identificador for t in r] == ["P1", "P2", "P3"]


@pytest.mark.parametrize("caso", ["vip", "casa", "doze_dias", "manual"])
def test_v3_1_quatro_casos_do_diretor(caso, caplog):
    import logging

    caplog.set_level(logging.DEBUG, logger="src.modules.cash_reconciliation.rules.cartoes")
    if caso == "vip":
        cartoes = [
            C(1, "30", "23:04", nsu="uuid-sintetico", adm="PIX PREMMIA"),
            C(2, "30", "23:09", nsu="uuid-sintetico", adm="PIX PREMMIA"),
        ]
    elif caso == "casa":
        cartoes = [
            C(1, "20", "18:25", nsu="1111", aut="1234"),
            C(2, "30", "22:04", nsu="2222", aut="1234"),
        ]
    elif caso == "doze_dias":
        cartoes = [
            C(1, "207.67", "21:07", nsu="1111", aut="1234"),
            C(2, "200", "10:07", nsu="2222", aut="1234", dia="2026-10-06"),
        ]
    else:
        cartoes = [C(1, "150.04", "01:00", aut="1234"), C(2, "20", "01:00", aut="1234")]
    cartoes = [
        c.model_copy(
            update={
                "venda_codigo": 0 if caso == "manual" else c.codigo + 10,
                "tipo_inclusao": "Manualmente" if caso == "manual" else "PDV-TEF",
                "frentista": 7 if caso in {"vip", "manual"} else c.codigo + 7,
                "nome_frentista": "Funcionário Sintético",
                "caixa_codigo": 106,
            }
        )
        for c in cartoes
    ]
    resultado = conciliar(74014, "PAGBANK", DIA, [], cartoes, [], set())
    repetidos = [a for a in resultado.alertas if a.codigo == "CARTAO_NSU_REPETIDO"]
    manuais = [a for a in resultado.alertas if a.codigo == "CARTAO_MANUAL_SEM_VENDA"]
    assert len(repetidos) == (1 if caso == "vip" else 0)
    assert len(manuais) == (2 if caso == "manual" else 0)
    if repetidos:
        assert repetidos[0].valor == Decimal("30")
        assert repetidos[0].severidade == "vermelho"
        assert resultado.a_menor[0].motivo == "NSU já usado na venda 11"
    if manuais:
        assert sum(a.valor for a in manuais) == Decimal("170.04")
        assert all(
            a.severidade == "laranja"
            and "Funcionário Sintético (7)" in a.mensagem
            and "01:00" in a.mensagem
            and "PAGSEGURO" in a.mensagem
            for a in manuais
        )
    if caso != "vip":
        assert "valor/dia diferentes ignorada" in caplog.text


def test_v3_1_autorizacao_mesmo_valor_dia_e_nsu_tef():
    from src.modules.cash_reconciliation.rules.cartoes import grupos_nsu_repetido

    cartoes = [
        C(1, "30", "10:00", aut="1234"),
        C(2, "30", "11:00", aut="1234"),
        C(3, "40", "12:00", nsu="1234"),
        C(4, "50", "13:00").model_copy(update={"nsu_tef": "1234"}),
    ]
    grupos = grupos_nsu_repetido(cartoes)
    assert sorted(sorted(c.codigo for c in g) for g in grupos) == [[1, 2], [3, 4]]


def test_v3_1_nsu_entre_dias_alerta_so_no_dia_do_excedente():
    cartoes = [
        C(1, "30", "23:59", nsu="uuid-sintetico"),
        C(2, "30", "00:04", nsu="uuid-sintetico", dia="2026-10-06"),
    ]
    primeiro = conciliar(74014, "PAGBANK", DIA, [], cartoes, [], set())
    segundo = conciliar(74014, "PAGBANK", date(2026, 10, 6), [], cartoes, [], set())
    assert not primeiro.alertas
    assert len(segundo.alertas) == 1 and segundo.alertas[0].valor == Decimal("30")


async def test_pagbank_sem_credencial(monkeypatch):
    monkeypatch.delenv("PAGBANK_USER_2", raising=False)
    with pytest.raises(pagbank_edi.PagBankErro, match="ausentes"):
        await pagbank_edi.buscar_transacoes(2, DIA)


def test_mapeia_cartao_e_abastecimento_do_webposto():
    c = para_cartao({"cartaoCodigo": 1, "empresaCodigo": 74014, "vendaCodigo": 9, "valor": 10.5,
                     "dataMovimento": "2026-10-05", "horaMovimento": "10:00:00",
                     "adiministradoraDescricao": "MAESTRO PAGSEGURO", "nsu": "1", "nsuTef": None, "autorizacao": "A"})
    a = para_abastecimento({"abastecimentoCodigo": 2, "empresaCodigo": 74014, "dataHoraAbastecimento": "2026-10-05T00:28:48-03:00",
                            "codigoBico": 3, "valorTotal": 50, "quantidade": "31.25",
                            "codigoFrentista": 7, "vendaItemCodigo": 11})
    assert c.administradora == "MAESTRO PAGSEGURO" and c.valor == Decimal("10.5")
    assert a.momento == datetime(2026, 10, 5, 0, 28, 48, tzinfo=FUSO) and a.frentista == 7
    assert a.litros == Decimal("31.25")


def test_cartao_pos_sem_detalhe_classifica_grupo_2_sem_sugerir_lancamento():
    from src.modules.cash_reconciliation.application.classificar_recebimentos import classificar_recebimentos
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente, ResultadoRecebimentos

    transacao = T("250.07", "19:13:34", ident="pagbank-250").model_copy(
        update={"bandeira": "VISA", "terminal": "LEITOR-4038"}
    )
    venda = C(10294, "250.07", "19:13:34", adm="CARTÃO POS SEM DETALHE")
    venda = venda.model_copy(update={"venda_codigo": 10294})
    resultado = conciliar(74014, "PAGBANK", DIA, [transacao], [venda], [], set())
    recebimentos = ResultadoRecebimentos(
        empresa_codigo=74014,
        dia=DIA,
        adquirentes=(RecebimentoAdquirente.de_resultado(resultado),),
    )
    acoes = classificar_recebimentos(recebimentos)

    assert not resultado.a_maior and not resultado.a_menor
    assert any(alerta.codigo == "CARTAO_POS_SEM_DETALHE" for alerta in resultado.alertas)
    assert len(acoes) == 1 and acoes[0].grupo == 2
    assert acoes[0].motivo == "Detalhar cartão da venda 10294"


@pytest.mark.asyncio
async def test_adapter_detecta_cartao_pos_sem_registro_detalhado(monkeypatch):
    from src.modules.cash_reconciliation.adapters import webposto_cartoes
    from src.modules.cash_reconciliation.domain.models import Unidade

    unidade = Unidade(
        empresa_codigo=74014,
        nome="Doze",
        chave_env="NAO_USADA",
        destinos=(),
    )

    async def paginar(_unidade, path, _params, **_kwargs):
        if path.endswith("/VENDAS/ITENS"):
            return []
        if path.endswith("/VENDAS_FORMA_PAGAMENTO"):
            return [{
                "empresaCodigo": 74014,
                "vendaCodigo": 10294,
                "tipoFormaPagamento": "C",
                "nomeFormaPagamento": "Cartão POS",
                "valorPagamento": "250.07",
            }]
        if path.endswith("/VENDAS"):
            return [{
                "empresaCodigo": 74014,
                "vendaCodigo": 10294,
                "dataHora": "2026-10-05T19:13:34-03:00",
                "cancelada": False,
                "caixaCodigo": 10,
            }]
        if path.endswith("/CAIXAS"):
            return []
        raise AssertionError(f"endpoint não esperado: {path}")

    monkeypatch.setattr(webposto_cartoes, "paginar", paginar)
    _, pagamentos = await webposto_cartoes.buscar_contexto_vendas(
        unidade, DIA, DIA, contexto={}, cartoes_existentes=()
    )

    assert len(pagamentos) == 1
    assert pagamentos[0].venda_codigo == 10294
    assert pagamentos[0].valor == Decimal("250.07")
    assert "CARTÃO POS SEM DETALHE" in pagamentos[0].administradora


def test_administradora_american_express_da_unidade_faz_parte_do_pagbank():
    from src.modules.cash_reconciliation.application.conciliar_cartoes import da_adquirente
    from src.modules.cash_reconciliation.config import carregar_unidades

    cartao = C(1, "100", "10:00", adm="AMERICAN EXPRESS")
    mapa_doze = carregar_unidades()[74014].administradoras
    mapa_casa_caiada = carregar_unidades()[5555].administradoras

    assert da_adquirente(cartao, "PAGBANK", mapa_doze)
    assert da_adquirente(cartao, "PAGBANK", mapa_casa_caiada)


def test_cobranca_duplicada_mesmo_terminal_e_so_uma_venda_vira_apurar():
    from src.modules.cash_reconciliation.application.classificar_recebimentos import classificar_recebimentos
    from src.modules.cash_reconciliation.domain.recebimentos import (
        RecebimentoAdquirente,
        ResultadoRecebimentos,
    )

    primeira = T("250.07", "19:12:26", aut="018845", ident="transacao-duplicada").model_copy(
        update={"terminal": "LEITOR-4038", "bandeira": "VISA"}
    )
    segunda = T("250.07", "19:13:21", aut="024956", ident="transacao-da-venda").model_copy(
        update={"terminal": "LEITOR-4038", "bandeira": "VISA"}
    )
    cartao = C(10294, "250.07", "19:13:34", aut="024956").model_copy(
        update={
            "venda_codigo": 10294,
            "frentista": 302036,
            "nome_frentista": "Matheus Gomes da Silva",
        }
    )
    resultado = conciliar(74014, "PAGBANK", DIA, [primeira, segunda], [cartao], [], set())

    alerta = next(a for a in resultado.alertas if a.codigo == "CARTAO_COBRANCA_DUPLICADA")
    acoes = classificar_recebimentos(
        ResultadoRecebimentos(
            empresa_codigo=74014,
            dia=DIA,
            adquirentes=(RecebimentoAdquirente.de_resultado(resultado),),
        )
    )
    assert alerta.transacoes == (segunda, primeira)
    assert "19:12" in alerta.mensagem and "19:13" in alerta.mensagem
    assert "…8845" in alerta.mensagem and "…4956" in alerta.mensagem
    assert "…4038" in alerta.mensagem and "Matheus Gomes da Silva (302036)" in alerta.mensagem
    assert not resultado.a_maior
    assert len(resultado.casados) == 1
    assert len(acoes) == 1 and acoes[0].grupo == 3
    assert acoes[0].motivo.endswith("(não lançar)")


def test_estorno_da_cobranca_extra_no_dia_seguinte_remove_acao_de_apuracao():
    from src.modules.cash_reconciliation.application.classificar_recebimentos import classificar_recebimentos
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente, ResultadoRecebimentos

    primeira = T("250.07", "19:12:26", aut="018845", ident="transacao-extra").model_copy(
        update={"terminal": "LEITOR-4038"}
    )
    segunda = T("250.07", "19:13:21", aut="024956", ident="transacao-venda").model_copy(
        update={"terminal": "LEITOR-4038"}
    )
    estorno = T("250.07", "08:00:00", aut="018845", dia="2026-10-06", ident="transacao-extra").model_copy(
        update={"situacao": "estornada", "terminal": "LEITOR-4038"}
    )
    cartao = C(10294, "250.07", "19:13:34", aut="024956").model_copy(update={"venda_codigo": 10294})
    resultado = conciliar(74014, "PAGBANK", DIA, [primeira, segunda, estorno], [cartao], [], set())
    recebimentos = ResultadoRecebimentos(
        empresa_codigo=74014,
        dia=DIA,
        adquirentes=(RecebimentoAdquirente.de_resultado(resultado),),
    )

    assert any(a.codigo == "CARTAO_COBRANCA_DUPLICADA_ESTORNADA" for a in resultado.alertas)
    assert not any(a.grupo == 3 for a in classificar_recebimentos(recebimentos))
    assert sum(f.portal.quantidade for f in recebimentos.adquirentes[0].formas) == 1
    assert sum((f.portal.total for f in recebimentos.adquirentes[0].formas), Decimal(0)) == Decimal("250.07")
    assert sum((f.webposto.total for f in recebimentos.adquirentes[0].formas), Decimal(0)) == Decimal("250.07")
