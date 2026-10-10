import httpx

from src.shared.notificacao.telegram import enviar_documento, enviar_mensagem


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


def test_enviar_documento_multipart_sem_expor_token_no_log(tmp_path, caplog):
    caminho = tmp_path / "resumo.xlsx"
    caminho.write_bytes(b"planilha-sintetica")
    pedidos = []

    def responder(request):
        pedidos.append(request)
        return httpx.Response(200, json={"ok": True})

    token = "token-sintetico-secreto"
    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        (resultado,) = enviar_documento(
            caminho,
            "Detalhe sintético",
            token=token,
            chat_ids=["11"],
            cliente=cliente,
        )

    assert resultado.sucesso
    assert pedidos[0].url.path == f"/bot{token}/sendDocument"
    corpo = pedidos[0].read()
    assert b"multipart/form-data" in pedidos[0].headers["content-type"].encode()
    assert b"Detalhe sint\xc3\xa9tico" in corpo
    assert b"planilha-sintetica" in corpo
    assert token not in caplog.text


def test_falha_send_document_nao_registra_token_ou_resposta(tmp_path, caplog):
    caminho = tmp_path / "resumo.xlsx"
    caminho.write_bytes(b"planilha-sintetica")
    token = "token-sintetico-secreto"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401,
                json={"ok": False, "description": f"falha {token}"},
            )
        )
    ) as cliente:
        (resultado,) = enviar_documento(
            caminho,
            "Detalhe sintético",
            token=token,
            chat_ids=["11"],
            cliente=cliente,
        )

    assert not resultado.sucesso
    assert resultado.status_http == 401
    assert token not in caplog.text
    assert f"falha {token}" not in caplog.text


def test_enviar_mensagem_inclui_parse_mode_html():
    def responder(request):
        assert request.read().find(b'"parse_mode":"HTML"') >= 0
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        (resultado,) = enviar_mensagem(
            "<b>Resumo</b>",
            token="token-sintetico",
            chat_ids=["11"],
            cliente=cliente,
            parse_mode="HTML",
        )

    assert resultado.sucesso
