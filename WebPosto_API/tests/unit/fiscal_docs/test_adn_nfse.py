import base64
import gzip
from pathlib import Path

import httpx
import pytest

from src.modules.fiscal_docs import adn_nfse as adn

XML = (Path(__file__).parent / "dados" / "nfse_nacional.xml").read_bytes()


def _doc(nsu, arquivo=None, tipo="NFSE", chave="1" * 50):
    return {"NSU": nsu, "ChaveAcesso": chave, "TipoDocumento": tipo,
            "ArquivoXml": arquivo if arquivo is not None else base64.b64encode(gzip.compress(XML)).decode()}


def _cliente(tratar):
    return httpx.Client(base_url="https://adn.teste/contribuintes", transport=httpx.MockTransport(tratar))


def test_lote_com_documentos_e_parametros():
    def tratar(req):
        assert req.url.path == "/contribuintes/DFe/7"
        assert req.url.params["lote"] == "true"
        assert req.url.params["cnpjConsulta"] == "52308604000284"
        return httpx.Response(200, json={"StatusProcessamento": "DOCUMENTOS_LOCALIZADOS", "LoteDFe": [_doc(8), _doc(9)]})

    lote = adn.distribuir(_cliente(tratar), 7, "52308604000284")
    assert [d.nsu for d in lote.documentos] == [8, 9] and lote.vazio is False
    assert lote.documentos[0].xml == XML and lote.documentos[0].chave == "1" * 50


def test_sem_cnpj_consulta_nao_envia_parametro():
    def tratar(req):
        assert "cnpjConsulta" not in req.url.params
        return httpx.Response(404, json={"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO"})

    assert adn.distribuir(_cliente(tratar), 0).vazio is True


def test_arquivo_corrompido_nao_derruba_o_lote():
    resp = {"StatusProcessamento": "DOCUMENTOS_LOCALIZADOS", "LoteDFe": [_doc(8, "@@nao-e-base64@@"), _doc(9)]}
    lote = adn.distribuir(_cliente(lambda r: httpx.Response(200, json=resp)), 7)
    assert lote.documentos[0].xml is None and lote.documentos[1].xml == XML


@pytest.mark.parametrize("status,tipo", [(401, "certificado"), (403, "certificado"), (500, "indisponivel"),
                                         (503, "indisponivel"), (400, "resposta")])
def test_erros_http(status, tipo):
    with pytest.raises(adn.AdnErro) as exc:
        adn.distribuir(_cliente(lambda r: httpx.Response(status, json={"StatusProcessamento": "REJEICAO"})), 0)
    assert exc.value.tipo == tipo


def test_rede_fora_do_ar():
    def tratar(req):
        raise httpx.ConnectError("sem rede")

    with pytest.raises(adn.AdnErro) as exc:
        adn.distribuir(_cliente(tratar), 0)
    assert exc.value.tipo == "indisponivel"


def test_contexto_ssl_carrega_pfx_e_nao_deixa_arquivo(tmp_path, monkeypatch):
    from tests.unit.match.test_fiscal_certificados import gerar_pfx
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    ctx = adn.contexto_ssl(gerar_pfx("X:52308604000284"), "senha-do-teste")
    assert ctx is not None and list(tmp_path.iterdir()) == []


def test_recusa_traz_codigo_e_descricao_do_sistema_nacional():
    corpo = {"StatusProcessamento": "REJEICAO",
             "Erros": [{"Codigo": "E2213", "Descricao": "NSU informado inválido."}]}
    with pytest.raises(adn.AdnErro) as exc:
        adn.distribuir(_cliente(lambda r: httpx.Response(400, json=corpo)), 0)
    assert exc.value.tipo == "resposta"
    assert exc.value.detalhe == "HTTP 400 · REJEICAO · E2213 NSU informado inválido."


def test_recusa_sem_json_mostra_o_inicio_do_texto():
    with pytest.raises(adn.AdnErro) as exc:
        adn.distribuir(_cliente(lambda r: httpx.Response(415, text="Unsupported Media Type\n\n")), 0)
    assert exc.value.detalhe == "HTTP 415 · Unsupported Media Type"


@pytest.mark.parametrize("corpo", [
    {"StatusProcessamento": "REJEICAO", "Erros": [{"Codigo": "E2230", "Descricao": "Nenhum documento localizado."}]},
    {"erros": [{"codigo": "E9999", "descricao": "NENHUM DOCUMENTO LOCALIZADO para o NSU"}]},
])
def test_400_de_nenhum_documento_e_fila_vazia(corpo):
    assert adn.distribuir(_cliente(lambda r: httpx.Response(400, json=corpo)), 0).vazio is True
