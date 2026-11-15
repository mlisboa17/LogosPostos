from decimal import Decimal

import pytest

from apps.match import banco, caminhos, credenciais, importar_env
from src.modules.cash_reconciliation.domain.tempo import ontem

LISTA = [
    {"empresa_codigo": 74014, "apelido": "Doze", "chave_env": "K_DOZE",
     "premmia_usuario_env": "PU_DOZE", "premmia_senha_env": "PS_DOZE"},
    {"empresa_codigo": 5555, "apelido": "Casa Caiada", "chave_env": "K_CC",
     "premmia_usuario_env": "PU_CC", "premmia_senha_env": "PS_CC"},
    {"empresa_codigo": 118508, "apelido": "Conv. 24h", "chave_env": "K_CONV"},
]
ENV = {"PU_DOZE": "doze-user", "PS_DOZE": "doze-pass", "K_DOZE": "kd",
       "PU_CC": "70001", "PS_CC": "cc-pass", "K_CC": "kc", "K_CONV": "kv",
       "PAGBANK_USER_118508": "pb-conv", "PAGBANK_TOKEN_118508": "pb-tok"}


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "t.db")
    yield c
    c.close()


def test_importa_premmia_e_chaves_e_corrige_login_trocado(con):
    doze = banco.inserir_posto(con, "Posto Doze", "Doze", None, 74014)
    cc = banco.inserir_posto(con, "Casa Caiada", "Casa Caiada", None, None)  # sem código: acha pelo apelido
    conv = banco.inserir_posto(con, "Conveniência", "Conv. 24h", None, 118508)
    f = banco.salvar_fonte(con, doze, "premmia", True, {})
    credenciais.salvar(f"{doze}/premmia/usuario", "70001")  # o login errado (do Casa Caiada)
    banco.registrar_coleta(con, f, ontem(), "ok", 15, Decimal("1640.79"), None)
    (caminhos.premmia(doze) / "postodoze_11_2026.xlsx").write_bytes(b"x")

    linhas = importar_env.importar(con, ENV, LISTA)
    texto = "\n".join(linhas)
    assert "Doze: Premmia ligado, usuário do Premmia trocado" in texto and "ATENÇÃO" not in texto
    assert credenciais.ler(f"{doze}/premmia/usuario") == "doze-user"
    assert credenciais.ler(f"{cc}/premmia/usuario") == "70001" and credenciais.ler(f"{cc}/webposto/chave") == "kc"
    assert banco.obter_posto(con, cc)["empresa_codigo_webposto"] == 5555
    assert credenciais.ler(f"{conv}/webposto/chave") == "kv" and "sem Premmia no .env" in texto
    assert "Conv. 24h: chave do webPosto (sem Premmia no .env), PagBank ligado" in texto
    assert credenciais.ler(f"{conv}/pagbank/token") == "pb-tok"
    assert con.execute("SELECT COUNT(*) FROM coleta").fetchone()[0] == 0  # vendas do login antigo apagadas
    for segredo in ENV.values():
        assert segredo not in texto
