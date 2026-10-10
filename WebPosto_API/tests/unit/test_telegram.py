import httpx

from src.shared.notificacao.telegram import enviar_mensagem


def test_envia_mensagem_com_sucesso_por_destinatario():
    pedidos = []

    def responder(request):
        pedidos.append(request)
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        resultados = enviar_mensagem(
            "LOGOS — teste",
            token="token-sintetico",
            chat_ids=["11", "22", "11"],
            cliente=cliente,
        )

    assert [item.chat_id for item in resultados] == ["11", "22"]
    assert all(item.sucesso and item.status_http == 200 for item in resultados)
    assert [pedido.url.path for pedido in pedidos] == [
        "/bottoken-sintetico/sendMessage",
        "/bottoken-sintetico/sendMessage",
    ]
    assert pedidos[0].read().find(b"LOGOS") >= 0


def test_erro_401_retem_somente_tipo_e_status():
    tentativas = []

    def responder(request):
        tentativas.append(request)
        return httpx.Response(401, json={"ok": False, "description": "unauthorized"})

    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        (resultado,) = enviar_mensagem(
            "teste",
            token="token-sintetico",
            chat_ids=["11"],
            cliente=cliente,
        )

    assert len(tentativas) == 2
    assert not resultado.sucesso
    assert resultado.status_http == 401
    assert resultado.tipo_erro == "HTTPStatusError"
