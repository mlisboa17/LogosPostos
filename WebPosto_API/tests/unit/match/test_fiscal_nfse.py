import base64
import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from apps.match import banco
from apps.match.fiscal import captura_nfse, certificados, conferencia, repositorio as repo
from tests.unit.match.test_fiscal_certificados import SENHA, gerar_pfx

DADOS = Path(__file__).resolve().parents[1] / "fiscal_docs" / "dados"
XML = (DADOS / "nfse_nacional.xml").read_bytes()
CNPJ = "52308604000284"
CHAVE = "26116062244444444000191000000000000126090000000001"
AGORA = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "n.db")
    yield c
    c.close()


def _gz(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode()


def _empresa(con):
    return certificados.criar_empresa_pelo_certificado(con, gerar_pfx(f"POSTO DOZE:{CNPJ}"), SENHA)[0]


class Adn:
    def __init__(self, lotes):
        self.lotes, self.pedidos = lotes, []

    def __call__(self, req):
        self.pedidos.append(int(req.url.path.rsplit("/", 1)[-1]))
        if not self.lotes:
            return httpx.Response(404, json={"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO"})
        item = self.lotes.pop(0)
        if isinstance(item, int):
            return httpx.Response(item, json={"StatusProcessamento": "REJEICAO"})
        return httpx.Response(200, json={"StatusProcessamento": "DOCUMENTOS_LOCALIZADOS", "LoteDFe": item})


def _buscar(con, eid, adn_falso, agora=AGORA):
    with httpx.Client(base_url="https://adn.teste/contribuintes", transport=httpx.MockTransport(adn_falso)) as c:
        return captura_nfse.buscar_empresa(con, eid, agora, client=c)


def _nota(nsu=1):
    return {"NSU": nsu, "ChaveAcesso": CHAVE, "TipoDocumento": "NFSE", "ArquivoXml": _gz(XML)}


def test_certificado_cria_a_empresa_sozinho(con):
    eid, info = certificados.criar_empresa_pelo_certificado(con, gerar_pfx(f"POSTO DOZE COMERCIO:{CNPJ}"), SENHA)
    e = repo.obter_empresa(con, eid)
    assert (e["cnpj"], e["razao_social"], e["posto_id"]) == (CNPJ, "POSTO DOZE COMERCIO", None)
    assert certificados.situacao(con, eid).cnpj == CNPJ and info.da_matriz is False
    assert certificados.criar_empresa_pelo_certificado(con, gerar_pfx(f"POSTO DOZE COMERCIO:{CNPJ}"), SENHA)[0] == eid


def test_busca_grava_nota_avanca_nsu_e_nao_duplica(con):
    eid = _empresa(con)
    a = Adn([[_nota(1)]])
    r = _buscar(con, eid, a)
    assert (r.situacao, r.novas) == ("ok", 1)
    doc = con.execute("SELECT tipo, origem, situacao, xml_path FROM documento WHERE chave=?", (CHAVE,)).fetchone()
    assert doc[:3] == ("nfse", "adn", "autorizada") and Path(doc[3]).exists()
    assert a.pedidos == [0, 1]  # segundo pedido parte do NSU gravado
    assert repo.nsu_de(con, eid)["ultimo_nsu"] == 1
    r2 = _buscar(con, eid, Adn([[_nota(1)]]), AGORA + timedelta(hours=2))
    assert r2.novas == 0 and con.execute("SELECT COUNT(*) FROM documento").fetchone()[0] == 1


def test_fila_vazia_espera_uma_hora_mesmo_clicando_de_novo(con):
    eid = _empresa(con)
    _buscar(con, eid, Adn([]))
    a = Adn([])
    r = _buscar(con, eid, a, AGORA + timedelta(minutes=10))
    assert a.pedidos == [] and r.situacao == "ok" and "tente de novo" in r.mensagem.lower()
    a2 = Adn([])
    _buscar(con, eid, a2, AGORA + timedelta(minutes=61))
    assert a2.pedidos == [0]


def test_nenhuma_nota_explica_o_que_fazer(con):
    r = _buscar(con, _empresa(con), Adn([]))
    assert r.novas == 0 and "Importar" in r.mensagem and "prefeitura" in r.mensagem


def test_nota_de_outro_cnpj_e_ignorada(con):
    eid = _empresa(con)
    outra = XML.replace(CNPJ.encode(), b"11111111000191")
    r = _buscar(con, eid, Adn([[{**_nota(1), "ArquivoXml": _gz(outra)}]]))
    assert r.novas == 0 and con.execute("SELECT COUNT(*) FROM documento").fetchone()[0] == 0
    assert repo.nsu_de(con, eid)["ultimo_nsu"] == 1


def test_arquivo_ilegivel_nao_trava_e_avisa(con):
    eid = _empresa(con)
    r = _buscar(con, eid, Adn([[{**_nota(1), "ArquivoXml": "@@"}, {**_nota(2)}]]))
    assert r.novas == 1 and "não" in r.mensagem and repo.nsu_de(con, eid)["ultimo_nsu"] == 2


def test_cancelamento_marca_a_nota(con):
    eid = _empresa(con)
    evento = b'<evento xmlns="http://www.sped.fazenda.gov.br/nfse"><infEvento><e101101/></infEvento></evento>'
    _buscar(con, eid, Adn([[_nota(1), {"NSU": 2, "ChaveAcesso": CHAVE, "TipoDocumento": "EVENTO", "ArquivoXml": _gz(evento)}]]))
    assert con.execute("SELECT situacao FROM documento WHERE chave=?", (CHAVE,)).fetchone()[0] == "cancelada"


def test_certificado_recusado_explica_e_nao_avanca(con):
    eid = _empresa(con)
    r = _buscar(con, eid, Adn([401]))
    assert r.situacao == "erro" and "certificado" in r.mensagem.lower()
    assert repo.nsu_de(con, eid)["ultimo_nsu"] == 0


def test_sem_certificado(con):
    eid = repo.salvar_empresa(con, CNPJ, "X", None, None, "PE", None)
    r = _buscar(con, eid, Adn([]))
    assert r.situacao == "sem_certificado" and "certificado" in r.mensagem.lower()


def test_conferencia_nao_exige_webposto_de_empresa_sem_posto(con):
    eid = _empresa(con)
    assert [a for a in conferencia.conferir(con, eid, "2026-10", AGORA) if a.nivel == "retem"] == []
