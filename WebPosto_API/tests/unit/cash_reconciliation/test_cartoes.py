from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest

from src.modules.cash_reconciliation.adapters import pagbank_edi
from src.modules.cash_reconciliation.adapters.webposto_cartoes import para_abastecimento, para_cartao
from src.modules.cash_reconciliation.application.conciliar_cartoes import conciliar
from src.modules.cash_reconciliation.domain.cartoes import Abastecimento, Atribuicao, CartaoErp, TransacaoAdquirente
from src.modules.cash_reconciliation.domain.tempo import FUSO
from src.modules.cash_reconciliation.rules.cartoes import VERSAO, casar, investigar

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


# ---------- adapters ----------

def test_pagbank_transacao_real_data_e_hora_separadas_e_filtro_de_status():
    base = {"tid": "T1", "nsu": "100577524027", "codigo_autorizacao": "M00312", "valor_total_transacao": 87.43,
            "data_inicial_transacao": "2026-10-05", "hora_inicial_transacao": "00:29:25", "status_pagamento": "1",
            "tipo_evento": "1", "instituicao_financeira": "VISA", "numero_serie_leitor": "SN1"}
    t = pagbank_edi.para_transacao(base)
    assert t.momento == datetime(2026, 10, 5, 0, 29, 25, tzinfo=FUSO) and t.valor == Decimal("87.43") and t.terminal == "SN1"
    assert pagbank_edi.para_transacao({**base, "status_pagamento": "3"}) is None
    assert pagbank_edi.para_transacao({**base, "tipo_evento": "2"}) is None


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


async def test_pagbank_sem_credencial(monkeypatch):
    monkeypatch.delenv("PAGBANK_USER_2", raising=False)
    with pytest.raises(pagbank_edi.PagBankErro, match="ausentes"):
        await pagbank_edi.buscar_transacoes(2, DIA)


def test_mapeia_cartao_e_abastecimento_do_webposto():
    c = para_cartao({"cartaoCodigo": 1, "empresaCodigo": 74014, "vendaCodigo": 9, "valor": 10.5,
                     "dataMovimento": "2026-10-05", "horaMovimento": "10:00:00",
                     "adiministradoraDescricao": "MAESTRO PAGSEGURO", "nsu": "1", "nsuTef": None, "autorizacao": "A"})
    a = para_abastecimento({"abastecimentoCodigo": 2, "empresaCodigo": 74014, "dataHoraAbastecimento": "2026-10-05T00:28:48-03:00",
                            "codigoBico": 3, "valorTotal": 50, "codigoFrentista": 7, "vendaItemCodigo": 11})
    assert c.administradora == "MAESTRO PAGSEGURO" and c.valor == Decimal("10.5")
    assert a.momento == datetime(2026, 10, 5, 0, 28, 48, tzinfo=FUSO) and a.frentista == 7
