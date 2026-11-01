import json
import re
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco
from apps.match.acesso import Perfil
from apps.match.canais import envio
from apps.match.extratos import aprovacoes, autonomia
from apps.match.painel import criar_app


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    caminho = tmp_path / "revisao.db"
    con = banco.conectar(caminho)
    posto = banco.inserir_posto(con, "Posto", "P", None, 74014)
    conta = con.execute(
        """INSERT INTO conta_bancaria(posto_id,banco,conta_sufixo,cd_conta_webposto)
           VALUES (?, 'BB', '4068-X', 86248)""", (posto,),
    ).lastrowid
    con.commit()
    cli = TestClient(criar_app(lambda: banco.conectar(caminho)),
                     base_url="http://127.0.0.1", follow_redirects=False)
    yield con, cli, posto, conta
    cli.close()
    con.close()


def _csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _login(con, cli, perfil, postos):
    if perfil != Perfil.ADMINISTRADOR:
        acesso.criar_usuario(con, "Admin", "admin", "senha-forte-1", Perfil.ADMINISTRADOR, [])
    acesso.criar_usuario(con, "Usuário", "teste", "senha-forte-1", perfil, postos)
    csrf = _csrf(cli.get("/entrar").text)
    assert cli.post("/entrar", data={
        "csrf": csrf, "login": "teste", "senha": "senha-forte-1",
    }).status_code == 303
    return _csrf(cli.get("/extratos").text)


def test_quality_config_admin_csrf_validacao_e_log(ambiente):
    con, cli, posto, conta = ambiente
    csrf = _login(con, cli, Perfil.ADMINISTRADOR, [])
    pagina = cli.get("/extratos")
    assert "Formato de débito confirmado pela Quality" in pagina.text
    assert "Não confirmado" in pagina.text
    rota = "/extratos/formato-debito"
    assert cli.post(rota, data={"formato": "D"}).status_code == 403
    assert cli.post(rota, data={"csrf": csrf, "formato": "Débito"}).status_code == 400
    assert cli.post(rota, data={"csrf": csrf, "formato": "D"}).status_code == 303
    assert banco.formato_debito(con) == "D"
    assert con.execute("SELECT acao FROM log_acesso ORDER BY id DESC").fetchone()[0] == (
        "configurar_formato_debito"
    )
    assert cli.post(rota, data={"csrf": csrf, "formato": ""}).status_code == 303
    assert banco.formato_debito(con) is None


def test_quality_config_gerente_nao_pode(ambiente):
    con, cli, posto, conta = ambiente
    csrf = _login(con, cli, Perfil.GERENTE, [posto])
    assert cli.post("/extratos/formato-debito", data={
        "csrf": csrf, "formato": "D",
    }).status_code == 403
    assert "Formato de débito confirmado pela Quality" not in cli.get("/extratos").text


def test_conta_tela_mostra_bloqueios(ambiente):
    con, cli, posto, conta = ambiente
    _login(con, cli, Perfil.ADMINISTRADOR, [])
    assert "Envio ao webPosto desligado para este posto." in cli.get("/extratos").text
    con.execute("UPDATE posto SET enviar_extratos_webposto=1")
    con.execute(
        """INSERT INTO extrato_arquivo(sha256,situacao) VALUES ('hash','lido')"""
    )
    con.execute(
        """INSERT INTO extrato_linha(conta_bancaria_id,arquivo_id,chave,data,valor)
           VALUES (?,1,'debito','2026-10-31','-5')""", (conta,),
    )
    con.commit()
    assert ("Extrato com débitos aguardando a Quality confirmar o formato de débito "
            "do webPosto. Nada foi enviado.") in cli.get("/extratos").text


@pytest.mark.parametrize("outro_posto", [False, True])
def test_repropor_painel_escopo_csrf_e_log(ambiente, outro_posto):
    con, cli, posto, conta = ambiente
    outro = banco.inserir_posto(con, "Outro", "Outro", None, 74015)
    csrf = _login(con, cli, Perfil.GERENTE, [outro if outro_posto else posto])
    a = aprovacoes.criar(con, "importar_extrato", posto, conta, {
        "posto": {"nome": "Posto"}, "conta": {}, "periodos": [],
    })
    aprovacoes.decidir(con, a["ticket"], False, "teste", "painel")
    rota = f"/extratos/aprovacoes/{a['ticket']}/repropor"
    assert cli.post(rota).status_code == 403
    resposta = cli.post(rota, data={"csrf": csrf})
    assert resposta.status_code == (403 if outro_posto else 303)
    row = con.execute("SELECT reproposta_em FROM aprovacao").fetchone()
    assert bool(row[0]) is not outro_posto
    if not outro_posto:
        assert "Propor de novo" in cli.get("/extratos").text
        assert con.execute("SELECT acao FROM log_acesso ORDER BY id DESC").fetchone()[0] == (
            "repropor_extrato"
        )


def test_limite_diario_por_criacao_local_com_extratos_passados(ambiente, monkeypatch):
    con, cli, posto, conta = ambiente
    monkeypatch.setattr(autonomia, "hoje", lambda: date(2026, 11, 1))
    chave = autonomia.chave_lancamento(conta, "Tarifa", "Plano", "Centro")
    for _ in range(5):
        autonomia.registrar_decisao(con, chave, True, False)
    for indice, (criada_em, valor) in enumerate([
        ("2026-11-01T02:59:59+00:00", "2000"),
        ("2026-11-01T03:00:00+00:00", "1000"),
        ("2026-11-02T02:59:59+00:00", "750"),
        ("2026-11-02T03:00:00+00:00", "2000"),
    ]):
        a = aprovacoes.criar(con, "lancamento", posto, conta, {
            "chave_linha": str(indice), "data": "2026-10-20", "valor": valor,
        })
        con.execute("UPDATE aprovacao SET situacao='automatica', criada_em=? WHERE id=?",
                    (criada_em, a["id"]))
    con.commit()
    assert autonomia.pode_automatico(con, chave, Decimal("-250"), conta)
    assert not autonomia.pode_automatico(con, chave, Decimal("-250.01"), conta)


def test_resumo_diario_data_local_e_automatica_nao_enviada(ambiente):
    con, cli, posto, conta = ambiente
    for indice, (situacao, criada, decidida) in enumerate([
        ("executada", "2026-10-31T12:00:00+00:00", "2026-11-01T03:00:00+00:00"),
        ("automatica", "2026-11-02T02:59:59+00:00", "2026-11-02T02:59:59+00:00"),
        ("automatica", "2026-11-01T12:00:00+00:00", None),
        ("executada", "2026-11-01T02:59:59+00:00", "2026-11-01T02:59:59+00:00"),
    ]):
        a = aprovacoes.criar(con, "importar_extrato", posto, conta, {})
        con.execute(
            "UPDATE aprovacao SET situacao=?,criada_em=?,decidida_em=? WHERE id=?",
            (situacao, criada, decidida, a["id"]),
        )
    con.commit()
    texto = envio.texto_resumo([], banco.obter_posto(con, posto), date(2026, 11, 1), con=con)
    assert "Extratos: 2 importados, 0 aguardando aprovação, 0 faltando no financeiro." in texto


def test_migracao_8_para_9_preserva_dados(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    caminho = tmp_path / "v8.db"
    raw = sqlite3.connect(caminho)
    raw.execute("CREATE TABLE schema_version(version INTEGER PRIMARY KEY)")
    for versao, sql in banco._MIGRACOES[:8]:
        raw.executescript(sql)
        raw.execute("INSERT INTO schema_version VALUES (?)", (versao,))
    raw.execute("INSERT INTO posto(nome,criado_em) VALUES ('Legado','ontem')")
    raw.commit()
    raw.close()
    con = banco.conectar(caminho)
    try:
        assert con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 9
        assert con.execute("SELECT nome FROM posto").fetchone()[0] == "Legado"
        assert banco.formato_debito(con) is None
    finally:
        con.close()
