from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.security.jwt_utils import create_access_token
from src.modules.cash_reconciliation.adapters import pagbank_edi, webposto_cartoes
from src.modules.cash_reconciliation.adapters.webposto_http import WebPostoErro
from src.modules.cash_reconciliation.application import recebimentos
from src.modules.cash_reconciliation.application.conciliar_cartoes import conciliar
from src.modules.cash_reconciliation.domain.cartoes import Abastecimento, CartaoErp, TransacaoAdquirente
from src.modules.cash_reconciliation.domain.models import AdquirenteConfigurada, Unidade
from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente, ResultadoRecebimentos
from src.modules.cash_reconciliation.domain.tempo import FUSO
from src.modules.cash_reconciliation.interfaces import http

DIA = date(2026, 1, 2)
EMPRESA = 321


def configurada(nome="PAGBANK", situacao="ativo"):
    return AdquirenteConfigurada(nome=nome, situacao=situacao, modalidades=("pix",))


def unidade(*adquirentes):
    return Unidade(
        empresa_codigo=EMPRESA, nome="Unidade Sintetica", chave_env="CHAVE_SINTETICA",
        destinos=(), adquirentes=adquirentes,
    )


def resultado():
    transacoes = [
        TransacaoAdquirente(
            adquirente="PAGBANK", identificador=f"t{indice}", valor=valor,
            momento=datetime(2026, 1, 2, hora), nsu=None, autorizacao=None, bandeira="PIX",
        )
        for indice, valor, hora in [(1, "10.15", 10), (2, "20.25", 11), (3, "30.35", 12)]
    ]
    cartoes = [
        CartaoErp(
            codigo=indice, empresa_codigo=EMPRESA, venda_codigo=indice, valor=valor,
            momento=datetime(2026, 1, 2, hora), administradora="PIX PAGBANK",
            nsu=None, nsu_tef=None, autorizacao=None,
        )
        for indice, valor, hora in [(1, "10.15", 10), (2, "30.35", 18), (3, "40.45", 19)]
    ]
    abastecimento = Abastecimento(
        codigo=1, empresa_codigo=EMPRESA, momento=datetime(2026, 1, 2, 10, 59),
        bico=1, valor=Decimal("20.25"), frentista=7, venda_item_codigo=9,
    )
    return conciliar(EMPRESA, "PAGBANK", DIA, transacoes, cartoes, [abastecimento], {9})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(http, "carregar_unidades", lambda: {EMPRESA: unidade(configurada())})
    app = FastAPI()
    app.include_router(http.router)
    with TestClient(app) as client:
        client.cookies.set(
            "access_token",
            create_access_token("director@example.invalid", extra={"role": "diretor", "token_type": "access"}),
        )
        yield client


def test_rota_resumo_casados_e_detalhes_com_proveniencia(client, monkeypatch):
    async def buscar(empresa_codigo, dia):
        assert (empresa_codigo, dia) == (EMPRESA, DIA)
        return ResultadoRecebimentos(
            empresa_codigo=EMPRESA, dia=DIA,
            adquirentes=(RecebimentoAdquirente.de_resultado(resultado()),),
        )

    monkeypatch.setattr(http, "conciliar_recebimentos", buscar)
    response = client.get("/api/v1/cash-audit/recebimentos", params={"unidade": EMPRESA, "dia": DIA})
    assert response.status_code == 200
    item = response.json()["adquirentes"][0]
    assert item["casados"] == {"quantidade": 1, "total": "10.15"}
    assert len(item["a_maior"]) == len(item["a_menor"]) == len(item["pares_provaveis"]) == 1
    assert item["a_maior"][0]["frentista"] == 7
    assert item["a_maior"][0]["candidatos"][0]["pontos"] >= 80
    assert item["a_maior"][0]["candidatos"][0]["motivos"]
    assert item["proveniencia"]["versao_regra"] == "CARTOES_V3_4"
    assert "t1" not in response.text


def test_totais_pagbank_deduplicam_por_nsu_e_batem_109_transacoes():
    from src.modules.cash_reconciliation.domain.cartoes import AlertaCartao
    from src.modules.cash_reconciliation.application.relatorio_caixa_dia import gerar_relatorio_caixa_dia
    from src.modules.cash_reconciliation.domain.models import Unidade
    from .test_resumo_diario import _registro

    transacoes = []
    cartoes = []
    for indice in range(109):
        valor = Decimal("82.62") if indice == 108 else Decimal("82.42")
        momento = datetime(2026, 1, 2, 8) + timedelta(minutes=indice)
        nsu = f"NSU-{indice:04d}"
        transacoes.append(TransacaoAdquirente(
            adquirente="PAGBANK",
            identificador=f"transacao-{indice}",
            nsu=nsu,
            autorizacao=None,
            valor=valor,
            momento=momento,
            bandeira="VISA",
            tipo_evento="1",
            status_pagamento="1",
        ))
        cartoes.append(CartaoErp(
            codigo=indice + 1,
            empresa_codigo=74014,
            venda_codigo=indice + 1,
            valor=valor,
            momento=momento,
            administradora="VISA PAGSEGURO",
            nsu=nsu,
            nsu_tef=None,
            autorizacao=None,
        ))

    conciliado = conciliar(74014, "PAGBANK", DIA, transacoes, cartoes, [], set())
    duplicata = transacoes[0].model_copy(update={"identificador": "transacao-repetida"})
    conciliado = conciliado.model_copy(update={
        "alertas": (*conciliado.alertas, AlertaCartao(
            codigo="ALERTA_SINTETICO",
            severidade="informativo",
            mensagem="Mesmo NSU repetido numa evidência secundária.",
            valor=duplicata.valor,
            transacoes=(duplicata,),
        )),
    })
    recebimento = RecebimentoAdquirente.de_resultado(conciliado)

    assert recebimento.casados.quantidade == 109
    assert recebimento.casados.total == Decimal("8983.98")
    assert sum(f.portal.quantidade for f in recebimento.formas) == 109
    assert sum((f.portal.total for f in recebimento.formas), Decimal(0)) == Decimal("8983.98")
    assert sum(f.webposto.quantidade for f in recebimento.formas) == 109
    assert sum((f.webposto.total for f in recebimento.formas), Decimal(0)) == Decimal("8983.98")
    registro = _registro(alertas=()).model_copy(update={
        "recebimentos": ResultadoRecebimentos(
            empresa_codigo=EMPRESA,
            dia=DIA,
            adquirentes=(recebimento,),
        ),
    })
    relatorio = gerar_relatorio_caixa_dia(
        registro,
        Unidade(
            empresa_codigo=EMPRESA,
            nome="Unidade sintética",
            chave_env="NAO_USADA",
            destinos=(),
        ),
    )
    assert "- ✅ **PagBank (EDI):** 109 · R$ 8.983,98" in relatorio


def test_cartao_pos_nao_duplica_cartao_detalhado_da_mesma_venda():
    from src.modules.cash_reconciliation.domain.cartoes import AlertaCartao

    momento = datetime(2026, 1, 2, 10)
    transacao = TransacaoAdquirente(
        adquirente="PAGBANK",
        identificador="pagbank-150",
        nsu="NSU-150",
        autorizacao=None,
        valor=Decimal("150.00"),
        momento=momento,
        bandeira="VISA",
        tipo_evento="1",
        status_pagamento="1",
    )
    cartao_detalhado = CartaoErp(
        codigo=1,
        empresa_codigo=74014,
        venda_codigo=9001,
        valor=Decimal("150.00"),
        momento=momento,
        administradora="VISA PAGSEGURO",
        nsu="NSU-150",
        nsu_tef=None,
        autorizacao=None,
    )
    cartao_pos = cartao_detalhado.model_copy(update={
        "codigo": 2,
        "administradora": "CARTÃO POS SEM DETALHE",
    })
    pix_venda = cartao_detalhado.model_copy(update={
        "codigo": 3,
        "administradora": "PIX (venda) PIX PAGBANK",
    })
    cheque_a_vista = cartao_detalhado.model_copy(update={
        "codigo": 4,
        "venda_codigo": 9002,
        "administradora": "CARTÃO POS SEM DETALHE CHEQUE A-VISTA",
    })
    conciliado = conciliar(
        74014, "PAGBANK", DIA, [transacao], [cartao_detalhado], [], set()
    )
    conciliado = conciliado.model_copy(update={
        "alertas": (*conciliado.alertas, AlertaCartao(
            codigo="CARTAO_POS_SEM_DETALHE",
            severidade="laranja",
            mensagem="Pagamento Cartão POS da venda 9001.",
            valor=cartao_pos.valor,
            cartoes=(cartao_pos,),
            transacoes=(transacao,),
        )),
        "a_menor": (*conciliado.a_menor, pix_venda, cheque_a_vista),
    })

    recebimento = RecebimentoAdquirente.de_resultado(conciliado)

    assert recebimento.casados.quantidade == 1
    assert sum(f.webposto.quantidade for f in recebimento.formas) == 1
    assert sum((f.webposto.total for f in recebimento.formas), Decimal(0)) == Decimal("150.00")


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"unidade": 999, "dia": "2026-01-02"}, 404),
        ({"unidade": EMPRESA, "dia": "invalido"}, 422),
        ({"unidade": EMPRESA}, 422),
        ({"dia": "2026-01-02"}, 422),
    ],
)
def test_rota_valida_escopo_e_data(client, params, status):
    assert client.get("/api/v1/cash-audit/recebimentos", params=params).status_code == status


async def test_consulta_apenas_adquirente_ativa(monkeypatch):
    confs = (configurada(), configurada("MAIS_PAGAMENTOS", "pendente"),
             configurada("CIELO", "pendente"), configurada("REDE", "pendente"))
    monkeypatch.setattr(recebimentos, "carregar_unidades", lambda: {EMPRESA: unidade(*confs)})
    chamadas = []

    async def buscar(empresa, dia):
        chamadas.append((empresa, dia))
        return resultado()

    monkeypatch.setattr(recebimentos, "conciliar_pagbank", buscar)
    resposta = await recebimentos.conciliar_recebimentos(EMPRESA, DIA)
    assert chamadas == [(EMPRESA, DIA)]
    assert [item.situacao for item in resposta.adquirentes] == ["ok", "pendente", "pendente", "pendente"]
    assert all(item.casados is None for item in resposta.adquirentes[1:])


def test_rota_credencial_invalida_isolada_e_sem_segredo(client, monkeypatch, caplog):
    monkeypatch.setattr(
        recebimentos, "carregar_unidades",
        lambda: {EMPRESA: unidade(configurada(), configurada("REDE", "pendente"))},
    )

    async def falhar(*args):
        raise pagbank_edi.PagBankCredencialInvalida("segredo URL corpo bruto")

    monkeypatch.setattr(recebimentos, "conciliar_pagbank", falhar)
    response = client.get("/api/v1/cash-audit/recebimentos", params={"unidade": EMPRESA, "dia": DIA})
    assert response.status_code == 200
    items = response.json()["adquirentes"]
    assert items[0]["erro"] == items[0]["situacao"] == "credencial inválida"
    assert items[0]["casados"] is None
    assert items[1]["situacao"] == "pendente"
    assert "segredo" not in response.text + caplog.text


async def test_credencial_invalida_configurada_nao_consulta(monkeypatch):
    async def proibido(*args):
        pytest.fail("Adquirente desabilitada nao pode consultar rede.")

    monkeypatch.setattr(recebimentos, "conciliar_pagbank", proibido)
    item = await recebimentos.conciliar_adquirente(EMPRESA, DIA, configurada(situacao="credencial inválida"))
    assert item.situacao == "credencial inválida" and item.casados is None


@pytest.mark.parametrize(
    ("erro", "mensagem"),
    [(WebPostoErro("segredo"), "falha ao consultar dados operacionais"),
     (ValueError("segredo"), "falha ao processar recebimentos")],
)
async def test_erros_nao_expoem_detalhe(monkeypatch, caplog, erro, mensagem):
    async def falhar(*args):
        raise erro

    monkeypatch.setattr(recebimentos, "conciliar_pagbank", falhar)
    item = await recebimentos.conciliar_adquirente(EMPRESA, DIA, configurada())
    assert item.erro == mensagem and item.situacao == "erro"
    assert "segredo" not in item.model_dump_json() + caplog.text


async def test_timeout_cancela_etapa(monkeypatch):
    import asyncio

    async def lento(*args):
        await asyncio.sleep(1)
        return resultado()

    monkeypatch.setattr(recebimentos, "conciliar_pagbank", lento)
    item = await recebimentos.conciliar_adquirente(EMPRESA, DIA, configurada(), timeout=0.001)
    assert item.erro == "tempo limite excedido"


async def test_resultado_de_outro_tenant_rejeitado(monkeypatch):
    async def buscar(*args):
        return resultado().model_copy(update={"empresa_codigo": 999})

    monkeypatch.setattr(recebimentos, "conciliar_pagbank", buscar)
    item = await recebimentos.conciliar_adquirente(EMPRESA, DIA, configurada())
    assert item.situacao == "erro" and item.casados is None


@pytest.mark.parametrize("status", [401, 403])
async def test_pagbank_classifica_credencial_invalida(monkeypatch, status):
    monkeypatch.setenv("PAGBANK_USER_321", "usuario-sintetico")
    monkeypatch.setenv("PAGBANK_TOKEN_321", "token-sintetico")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(status, text="segredo")),
        base_url="https://sintetico.invalid",
    ) as client:
        with pytest.raises(pagbank_edi.PagBankCredencialInvalida, match="credencial inválida") as exc:
            await pagbank_edi.buscar_transacoes(EMPRESA, DIA, client=client)
    assert "segredo" not in str(exc.value)


async def test_pix_preserva_hora_venda_nao_cancelada_e_isolamento(monkeypatch):
    monkeypatch.setenv("CHAVE_SINTETICA", "chave-sintetica")
    vendas = [
        {"empresaCodigo": EMPRESA, "vendaCodigo": 1, "dataHora": "2026-01-02T10:12:13", "cancelada": "N"},
        {"empresaCodigo": EMPRESA, "vendaCodigo": 2, "dataHora": "2026-01-02T11:00:00", "cancelada": "S"},
        {"empresaCodigo": 999, "vendaCodigo": 3, "dataHora": "2026-01-02T12:00:00", "cancelada": "N"},
    ]
    formas = [
        {"empresaCodigo": empresa, "vendaCodigo": codigo, "tipoFormaPagamento": tipo,
         "valorPagamento": "10.15", "nomeFormaPagamento": "PIX PAGBANK"}
        for empresa, codigo, tipo in [(EMPRESA, 1, "B"), (EMPRESA, 1, "D"), (EMPRESA, 2, "B"),
                                     (EMPRESA, 2, "D"), (999, 3, "B"), (999, 3, "D")]
    ]
    itens = [{"empresaCodigo": empresa, "vendaCodigo": codigo, "vendaItemCodigo": codigo + 100}
             for empresa, codigo in [(EMPRESA, 1), (EMPRESA, 2), (999, 3)]]

    def handler(req):
        if req.url.path.endswith("/VENDAS/ITENS"):
            rows = itens
        elif req.url.path.endswith("/VENDAS_FORMA_PAGAMENTO"):
            rows = formas
        else:
            rows = vendas
        return httpx.Response(200, json={"resultados": rows, "ultimoCodigo": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://sintetico.invalid") as client:
        dinheiro, pix = await webposto_cartoes.buscar_contexto_vendas(unidade(), DIA, DIA, client=client)
    assert dinheiro == {101}
    assert len(pix) == 1 and pix[0].momento == datetime(2026, 1, 2, 10, 12, 13, tzinfo=FUSO)
    assert pix[0].empresa_codigo == EMPRESA and pix[0].valor == Decimal("10.15")


def test_cancelamento_desconhecido_nao_e_silencioso():
    with pytest.raises(ValueError, match="Marcador"):
        webposto_cartoes._cancelada("desconhecido")
