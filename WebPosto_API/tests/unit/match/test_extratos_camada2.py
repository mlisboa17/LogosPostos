import json
import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco, explicar
from apps.match.acesso import Perfil
from apps.match.extratos import aprovacoes, camada2
from apps.match.painel import criar_app
from src.modules.cash_reconciliation.application.despesas_sem_lancamento import (
    identificar_despesas_sem_lancamento as identificar_financeiro,
)
from src.modules.cash_reconciliation.application import despesas_sem_lancamento
from src.modules.cash_reconciliation.adapters.webposto_http import WebPostoErro

SENHA = "senha-forte-1"


@pytest.fixture
def fab(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    caminho = tmp_path / "camada2.db"
    banco.conectar(caminho).close()
    return lambda: banco.conectar(caminho)


@pytest.fixture
def con(fab):
    conexao = fab()
    yield conexao
    conexao.close()


@pytest.fixture
def cli(fab):
    return TestClient(criar_app(fab), base_url="http://127.0.0.1", follow_redirects=False)


def _conta(con, posto_id, sufixo="4068-X"):
    cur = con.execute(
        """INSERT INTO conta_bancaria
           (posto_id, banco, agencia, conta_sufixo, cd_conta_webposto)
           VALUES (?, 'BB', '0001', ?, 86248)""",
        (posto_id, sufixo),
    )
    con.commit()
    return cur.lastrowid


def _linha(con, conta_id, *, fitid="fit-1", valor="-125.50", data="2026-10-31",
           descricao="PIX ENVIADO - Loja Materiais"):
    cur = con.execute(
        """INSERT INTO extrato_arquivo(sha256, nome_original, recebido_em, situacao)
           VALUES (?, 'teste.ofx', '2026-11-01T10:00:00+00:00', 'lido')""",
        (f"sha-{fitid}",),
    )
    arquivo_id = cur.lastrowid
    cur = con.execute(
        """INSERT INTO extrato_linha
           (conta_bancaria_id, arquivo_id, chave, fitid, data, valor, tipo, descricao,
            documento, categoria)
           VALUES (?, ?, ?, ?, ?, ?, 'DEBIT', ?, 'doc', 'outros')""",
        (conta_id, arquivo_id, fitid, fitid, data, valor, descricao),
    )
    con.commit()
    return cur.lastrowid


def _despesa(*, fitid="fit-1", data=date(2026, 10, 31), valor=Decimal("125.50")):
    return SimpleNamespace(
        fitid=fitid,
        data=data,
        valor=valor,
        descricao_extrato="PIX ENVIADO - Loja Materiais",
        tipo="PIX pessoa",
        sugestao_plano_codigo=100,
        sugestao_plano_nome="Material de consumo",
        sugestao_centro_codigo=200,
        sugestao_centro_nome="Pista",
        observacao="Conferir fornecedor.",
    )


def _csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _login(cli, login="admin"):
    token = _csrf(cli.get("/entrar").text)
    resposta = cli.post(
        "/entrar",
        data={"csrf": token, "login": login, "senha": SENHA},
    )
    assert resposta.status_code == 303
    return _csrf(cli.get("/").text)


def test_linha_ja_lancada_nao_vira_proposta(con, monkeypatch):
    posto_id = banco.inserir_posto(con, "Posto", "Posto", None, 74014)
    conta_id = _conta(con, posto_id)
    _linha(con, conta_id)
    ativadas = []

    async def identificar(unidade, de, ate, *, extratos_mock, **kwargs):
        assert unidade.contas_extrato[0].cd_conta == 86248
        assert de == date(2026, 10, 31) and ate == date(2026, 10, 31)
        assert extratos_mock[0].lancamentos[0].fitid == "fit-1"
        return await identificar_financeiro(
            unidade, de, ate, extratos_mock=extratos_mock,
            titulos_mock=[], movimentos_mock=[{
                "codigo": 12, "tipo": "Débito", "dataMovimento": "2026-10-31",
                "valor": 125.50, "descricao": "Pagamento já lançado",
            }],
            planos_mock=[], centros_mock=[], fornecedores_mock=[], contas_mock=[],
        )

    monkeypatch.setattr(camada2, "identificar_despesas_sem_lancamento", identificar)
    monkeypatch.setattr(camada2.unidades, "ativar", lambda conexao: ativadas.append(conexao))

    propostas = camada2.analisar(con, conta_id, date(2026, 10, 31), date(2026, 10, 31))

    assert propostas == []
    assert ativadas == [con]
    assert con.execute("SELECT COUNT(*) FROM aprovacao").fetchone()[0] == 0


def test_proposta_unica_por_linha(con, monkeypatch):
    posto_id = banco.inserir_posto(con, "Posto", "Posto", None, 74014)
    conta_id = _conta(con, posto_id)
    _linha(con, conta_id)

    async def identificar(*args, **kwargs):
        return SimpleNamespace(despesas=[_despesa(), _despesa()])

    monkeypatch.setattr(camada2, "identificar_despesas_sem_lancamento", identificar)
    monkeypatch.setattr(camada2.unidades, "ativar", lambda _con: None)

    propostas = camada2.analisar(con, conta_id, date(2026, 10, 31), date(2026, 10, 31))

    assert len(propostas) == 1
    assert set(propostas[0]) == {
        "chave_linha", "data", "valor", "descricao", "tipo_sugerido",
        "plano_conta", "centro_custo", "explicacao_pt",
    }
    assert propostas[0]["chave_linha"] == "fit-1"
    assert con.execute(
        "SELECT COUNT(*) FROM aprovacao WHERE tipo='lancamento'"
    ).fetchone()[0] == 1
    resumo = json.loads(con.execute(
        "SELECT resumo_json FROM aprovacao WHERE tipo='lancamento'"
    ).fetchone()[0])
    assert resumo == propostas[0]


def test_aprovar_nao_chama_webposto(con, cli, monkeypatch):
    posto_id = banco.inserir_posto(con, "Posto", "Posto", None, 74014)
    conta_id = _conta(con, posto_id)
    resumo = {
        "chave_linha": "fit-1", "data": "2026-10-31", "valor": "125.50",
        "descricao": "PIX ENVIADO - Loja Materiais", "tipo_sugerido": "PIX pessoa",
        "plano_conta": {"codigo": 100, "nome": "Material de consumo"},
        "centro_custo": {"codigo": 200, "nome": "Pista"},
        "explicacao_pt": "Débito sem lançamento localizado.",
    }
    aprovacao = aprovacoes.criar(con, "lancamento", posto_id, conta_id, resumo)
    requisicoes = []
    def handle(request):
        requisicoes.append(request)
        assert request.method in ("GET", "HEAD"), "Camada 2 não pode escrever no webPosto."
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request",
        lambda self, request: transport.handle_request(request),
    )

    async def handle_async(self, request):
        return await transport.handle_async_request(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_async)
    with httpx.Client() as client:
        assert client.get("https://offline.invalid/prova-transporte").status_code == 200
    assert len(requisicoes) == 1
    requisicoes.clear()
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    csrf = _login(cli)
    monkeypatch.setattr(
        "apps.match.painel.rotas._em_segundo_plano",
        lambda *args: pytest.fail("A aprovação de lançamento não dispara importação."),
    )
    monkeypatch.setattr(
        "apps.match.extratos.camada1._executar_writer",
        lambda *args, **kwargs: pytest.fail("A camada 2 não escreve no webPosto."),
    )

    resposta = cli.post(
        f"/extratos/aprovacoes/{aprovacao['ticket']}",
        data={"csrf": csrf, "acao": "aprovar"},
    )

    assert resposta.status_code == 303
    assert requisicoes == []
    row = con.execute(
        "SELECT situacao, resultado FROM aprovacao WHERE id=?", (aprovacao["id"],)
    ).fetchone()
    assert row[:] == (
        "aprovada",
        "Aguardando liberação de lançamentos no webPosto (teste supervisionado pendente)."
    )


def test_corrigir_guarda_classificacao(con):
    posto_id = banco.inserir_posto(con, "Posto", "Posto", None, 74014)
    conta_id = _conta(con, posto_id)
    resumo = {
        "chave_linha": "fit-1", "plano_conta": {"codigo": 100, "nome": "Material"},
        "centro_custo": {"codigo": 200, "nome": "Pista"},
    }
    aprovacao = aprovacoes.criar(con, "lancamento", posto_id, conta_id, resumo)

    sucesso, mensagem = camada2.decidir(
        con, aprovacao["ticket"], "corrigir", plano_conta="Combustível",
        centro_custo="Pista 2",
    )

    assert sucesso
    assert mensagem == "Corrigido."
    atual = con.execute("SELECT situacao, resultado, resumo_json FROM aprovacao").fetchone()
    assert atual["situacao"] == "aprovada"
    assert atual["resultado"] == "Corrigido."
    salvo = json.loads(atual["resumo_json"])
    assert salvo["plano_conta"] == {"codigo": None, "nome": "Combustível"}
    assert salvo["centro_custo"] == {"codigo": None, "nome": "Pista 2"}


def test_faltando_no_financeiro_escopo_e_csrf(cli, con, monkeypatch):
    meu = banco.inserir_posto(con, "Meu posto", "Meu posto", None, 1)
    outro = banco.inserir_posto(con, "Outro posto", "Outro posto", None, 2)
    conta_meu, conta_outro = _conta(con, meu), _conta(con, outro, "1234-X")
    resumo = {
        "chave_linha": "fit-other", "data": "2026-10-31", "valor": "10",
        "descricao": "débito", "tipo_sugerido": "outros",
        "plano_conta": None, "centro_custo": None, "explicacao_pt": "Falta lançamento.",
    }
    aprovacoes.criar(con, "lancamento", outro, conta_outro, resumo)
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    acesso.criar_usuario(con, "Gerente", "gerente", SENHA, Perfil.GERENTE, [meu])
    token = _login(cli, "gerente")
    _linha(con, conta_meu)
    chamadas = []
    monkeypatch.setattr(
        camada2, "analisar",
        lambda *args: chamadas.append(args) or [],
    )

    tela = cli.get("/extratos")
    assert tela.status_code == 200
    assert "Faltando no financeiro" in tela.text
    assert "fit-other" not in tela.text
    assert cli.post(
        "/extratos/analisar",
        data={"conta_id": conta_meu, "de": "2026-10-31", "ate": "2026-10-31"},
    ).status_code == 403
    resposta = cli.post(
        "/extratos/analisar",
        data={
            "csrf": token, "conta_id": conta_meu,
            "de": "2026-10-31", "ate": "2026-10-31",
        },
    )
    assert resposta.status_code == 200
    assert "0 proposta(s) nova(s)" in resposta.text
    assert len(chamadas) == 1 and chamadas[0][1] == conta_meu
    def falhar(*args, **kwargs):
        raise WebPostoErro("token secreto")

    monkeypatch.setattr(camada2, "analisar", falhar)
    resposta = cli.post(
        "/extratos/analisar",
        data={
            "csrf": token, "conta_id": conta_meu,
            "de": "2026-10-31", "ate": "2026-10-31",
        },
    )
    assert resposta.status_code == 200
    assert explicar.erro_pt(WebPostoErro("token secreto")) in resposta.text


def test_falha_leitura_webposto_nao_cria_proposta(con, monkeypatch):
    posto_id = banco.inserir_posto(con, "Posto", "Posto", None, 74014)
    conta_id = _conta(con, posto_id)
    _linha(con, conta_id)

    async def falhar(*args, **kwargs):
        raise WebPostoErro("token secreto")

    monkeypatch.setattr(despesas_sem_lancamento, "paginar", falhar)
    monkeypatch.setattr(camada2.unidades, "ativar", lambda _con: None)

    with pytest.raises(WebPostoErro):
        camada2.analisar(con, conta_id, date(2026, 10, 31), date(2026, 10, 31))

    assert con.execute("SELECT COUNT(*) FROM aprovacao").fetchone()[0] == 0
    assert explicar.erro_pt(WebPostoErro("token secreto")) == (
        "webPosto indisponível ou chave inválida."
    )
