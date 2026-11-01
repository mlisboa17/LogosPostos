import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.match import acesso, banco
from apps.match.acesso import Perfil
from apps.match.canais import envio
from apps.match.extratos import aprovacoes, autonomia, camada1, camada2
from apps.match.painel import criar_app

SENHA = "senha-forte-1"


@pytest.fixture
def fab(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    caminho = tmp_path / "autonomia.db"
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


def _posto_conta(con):
    posto_id = banco.inserir_posto(con, "Posto", "Posto", None, 74014)
    cur = con.execute(
        """INSERT INTO conta_bancaria
           (posto_id, banco, agencia, conta_sufixo, cd_conta_webposto)
           VALUES (?, 'BB', '0001', '4068-X', 86248)""",
        (posto_id,),
    )
    con.commit()
    return posto_id, cur.lastrowid


def _csfr(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _login(cli):
    csrf = _csfr(cli.get("/entrar").text)
    resposta = cli.post(
        "/entrar", data={"csrf": csrf, "login": "admin", "senha": SENHA}
    )
    assert resposta.status_code == 303
    return _csfr(cli.get("/").text)


def _linha(con, conta_id, *, valor="-100.00", descricao="PIX ENVIADO Loja 123"):
    cur = con.execute(
        """INSERT INTO extrato_arquivo(sha256, nome_original, recebido_em, situacao)
           VALUES (?, 'lancamento.ofx', ?, 'lido')""",
        (hashlib.sha256(f"{conta_id}-{valor}-{descricao}".encode()).hexdigest(),
         datetime.now(timezone.utc).isoformat()),
    )
    arquivo_id = cur.lastrowid
    cur = con.execute(
        """INSERT INTO extrato_linha
           (conta_bancaria_id, arquivo_id, chave, fitid, data, valor, tipo, descricao,
            documento, categoria)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'doc', 'outros')""",
        (
            conta_id, arquivo_id, f"fit-{conta_id}-{abs(int(Decimal(valor)))}",
            f"fit-{conta_id}-{abs(int(Decimal(valor)))}", date.today().isoformat(),
            valor, "DEBIT" if Decimal(valor) < 0 else "CREDIT", descricao,
        ),
    )
    con.commit()
    return cur.lastrowid


def _resumo_lancamento(chave, valor="-100.00", descricao="PIX ENVIADO Loja 123"):
    return {
        "chave_linha": chave,
        "data": date.today().isoformat(),
        "valor": format(abs(Decimal(valor)), "f"),
        "descricao": descricao,
        "tipo_sugerido": "PIX pessoa",
        "plano_conta": {"codigo": 12, "nome": "Materiais"},
        "centro_custo": {"codigo": 34, "nome": "Pista"},
        "explicacao_pt": "Débito sem lançamento localizado.",
    }


def test_cinco_aprovacoes_viram_automatico(con):
    chave = "importar:7"

    for _ in range(5):
        autonomia.registrar_decisao(con, chave, aprovada=True, corrigida=False)

    row = con.execute("SELECT * FROM autonomia WHERE chave_tipo=?", (chave,)).fetchone()
    assert row["aprovacoes_seguidas"] == 5
    assert row["automatico"] == 1
    assert row["desligado_por_admin"] == 0


def test_correcao_zera(con):
    chave = "lanc:7:pix loja:materiais:pista"
    autonomia.registrar_decisao(con, chave, aprovada=True, corrigida=False)
    autonomia.registrar_decisao(con, chave, aprovada=True, corrigida=True)

    row = con.execute("SELECT * FROM autonomia WHERE chave_tipo=?", (chave,)).fetchone()
    assert row["aprovacoes_seguidas"] == 0
    assert row["automatico"] == 0


def test_falha_camada1_zera(con, monkeypatch):
    posto_id, conta_id = _posto_conta(con)
    chave = f"importar:{conta_id}"
    for _ in range(5):
        autonomia.registrar_decisao(con, chave, True, False)
    aprovacao = aprovacoes.criar(
        con, "importar_extrato", posto_id, conta_id,
        {"periodos": [], "total_linhas": 0},
    )
    monkeypatch.setattr(camada1, "_notificar", lambda *args: None)

    sucesso, _ = camada1._falhar(con, aprovacao["id"], "webPosto indisponível.")

    assert sucesso is False
    row = con.execute("SELECT * FROM autonomia WHERE chave_tipo=?", (chave,)).fetchone()
    assert row["aprovacoes_seguidas"] == 0
    assert row["automatico"] == 0


def test_limites_valor_e_diario(con):
    _posto_id, conta_id = _posto_conta(con)
    chave = autonomia.chave_lancamento(
        conta_id, "PIX ENVIADO Loja 123", {"codigo": 12}, {"codigo": 34}
    )
    autonomia.registrar_decisao(con, chave, True, False)
    for _ in range(4):
        autonomia.registrar_decisao(con, chave, True, False)
    assert autonomia.pode_automatico(con, chave, Decimal("-500.00"), conta_id)
    assert not autonomia.pode_automatico(con, chave, Decimal("-500.01"), conta_id)
    assert not autonomia.pode_automatico(con, chave, Decimal("10.00"), conta_id)

    resumo = _resumo_lancamento("daily-1", "-1750.00")
    aprovacao = aprovacoes.criar(con, "lancamento", _posto_id, conta_id, resumo)
    con.execute(
        "UPDATE aprovacao SET situacao='automatica', resultado='Pronto para lançar sozinho' WHERE id=?",
        (aprovacao["id"],),
    )
    con.commit()
    assert autonomia.pode_automatico(con, chave, Decimal("-250.00"), conta_id)
    assert not autonomia.pode_automatico(con, chave, Decimal("-250.01"), conta_id)


def test_transferencia_propria_nunca_automatica(con):
    _posto_id, conta_id = _posto_conta(con)
    chave = autonomia.chave_lancamento(
        conta_id, "Transferência entre minhas contas próprias",
        {"codigo": 12}, {"codigo": 34}
    )
    for _ in range(5):
        autonomia.registrar_decisao(con, chave, True, False)

    assert not autonomia.pode_automatico(con, chave, Decimal("-30.00"), conta_id)


def test_admin_desliga(con, cli):
    _posto_id, conta_id = _posto_conta(con)
    chave_tipo = f"importar:{conta_id}"
    for _ in range(5):
        autonomia.registrar_decisao(con, chave_tipo, True, False)
    acesso.criar_usuario(con, "Admin", "admin", SENHA, Perfil.ADMINISTRADOR, [])
    csrf = _login(cli)

    pagina = cli.get("/extratos/autonomia")
    assert pagina.status_code == 200 and "Desligar automático" in pagina.text
    resposta = cli.post(
        "/extratos/autonomia",
        data={"csrf": csrf, "chave_tipo": chave_tipo, "acao": "desligar"},
    )

    assert resposta.status_code == 303
    row = con.execute("SELECT * FROM autonomia WHERE chave_tipo=?", (chave_tipo,)).fetchone()
    assert row["automatico"] == 0 and row["desligado_por_admin"] == 1
    assert con.execute(
        "SELECT acao FROM log_acesso ORDER BY id DESC LIMIT 1"
    ).fetchone()[0] == "desligar_automatico_extrato"


def test_camada1_automatica_executa_e_avisa(con, monkeypatch):
    posto_id, conta_id = _posto_conta(con)
    chave = f"importar:{conta_id}"
    for _ in range(5):
        autonomia.registrar_decisao(con, chave, True, False)
    dia = date.today().isoformat()
    cur = con.execute(
        """INSERT INTO extrato_arquivo(sha256, nome_original, recebido_em, situacao)
           VALUES ('auto-hash', 'auto.ofx', ?, 'lido')""",
        (datetime.now(timezone.utc).isoformat(),),
    )
    arquivo_id = cur.lastrowid
    con.execute(
        """INSERT INTO extrato_linha
           (conta_bancaria_id, arquivo_id, chave, fitid, data, valor, tipo, descricao)
           VALUES (?, ?, 'auto-fit', 'auto-fit', ?, '-10.00', 'DEBIT', 'Teste')""",
        (conta_id, arquivo_id, dia),
    )
    con.commit()
    monkeypatch.setattr(camada1, "hoje", lambda: date.fromordinal(date.today().toordinal() + 1))
    monkeypatch.setattr(camada1, "_dias_ja_enviados", lambda *args: set())
    avisos = []

    monkeypatch.setattr(
        camada1, "_executar_writer",
        lambda *args, **kwargs: type("Resultado", (), {"sucesso": True})(),
    )
    monkeypatch.setattr(camada1, "_notificar", lambda _con, _posto, texto: avisos.append(texto))
    monkeypatch.setattr(camada2, "analisar", lambda *args: [])

    previa = camada1.montar_previa(con, conta_id)

    assert previa is None
    row = con.execute(
        "SELECT situacao, resultado FROM aprovacao WHERE tipo='importar_extrato'"
    ).fetchone()
    assert row["situacao"] == "automatica"
    assert con.execute(
        "SELECT importada_webposto FROM extrato_linha WHERE fitid='auto-fit'"
    ).fetchone()[0] == 1
    assert any("Importado automaticamente" in texto for texto in avisos)


def test_camada2_automatico_nao_chama_webposto(con, monkeypatch):
    posto_id, conta_id = _posto_conta(con)
    descricao = "PIX ENVIADO Loja 123"
    chave = autonomia.chave_lancamento(
        conta_id, descricao, {"codigo": 12}, {"codigo": 34}
    )
    for _ in range(5):
        autonomia.registrar_decisao(con, chave, True, False)
    _linha(con, conta_id, valor="-100.00", descricao=descricao)
    assert autonomia.pode_automatico(con, chave, Decimal("-100.00"), conta_id)
    monkeypatch.setattr(camada2.unidades, "ativar", lambda _con: None)
    from types import SimpleNamespace
    elegibilidades = []
    pode_original = autonomia.pode_automatico

    def verificar(conexao, chave_tipo, valor, conta):
        elegibilidades.append(chave_tipo)
        return pode_original(conexao, chave_tipo, valor, conta)

    monkeypatch.setattr(autonomia, "pode_automatico", verificar)

    monkeypatch.setattr(
        camada2, "_resultado_financeiro",
        lambda *args: SimpleNamespace(despesas=[SimpleNamespace(
            fitid=f"fit-{conta_id}-100", data=date.today(), valor=Decimal("100.00"),
            descricao_extrato=descricao, tipo="PIX pessoa", sugestao_plano_codigo=12,
            sugestao_plano_nome="Materiais", sugestao_centro_codigo=34,
            sugestao_centro_nome="Pista", observacao="",
        )]),
    )
    escritor = []
    monkeypatch.setattr(
        camada1, "_executar_writer",
        lambda *args, **kwargs: escritor.append(args),
    )

    propostas = camada2.analisar(con, conta_id, date.today(), date.today())

    assert elegibilidades == [chave]
    assert propostas == []
    auto = con.execute(
        "SELECT situacao, resultado FROM aprovacao WHERE tipo='lancamento'"
    ).fetchone()
    assert auto["situacao"] == "automatica"
    assert auto["resultado"] == "Pronto para lançar sozinho"
    assert escritor == []


def test_resumo_diario_extratos(con):
    posto_id, conta_id = _posto_conta(con)
    dia = date.today().isoformat()
    for tipo, situacao in (
        ("importar_extrato", "executada"),
        ("importar_extrato", "pendente"),
        ("lancamento", "pendente"),
        ("lancamento", "pendente"),
    ):
        aprovacao = aprovacoes.criar(
            con, tipo, posto_id, conta_id,
            {"data": dia, "valor": "10", "chave_linha": f"{tipo}-{situacao}-{id(tipo)}"},
        )
        con.execute("UPDATE aprovacao SET situacao=? WHERE id=?", (situacao, aprovacao["id"]))
    con.commit()
    posto = banco.obter_posto(con, posto_id)

    texto = envio.texto_resumo([], posto, date.today(), con=con)

    assert "Extratos: 1 importados, 1 aguardando aprovação, 2 faltando no financeiro." in texto


def test_migracao_7_para_8_preserva_dados(tmp_path):
    caminho = tmp_path / "v7.db"
    raw = sqlite3.connect(caminho)
    raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    for version, sql in banco._MIGRACOES[:7]:
        raw.executescript(sql)
        raw.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
    raw.execute("INSERT INTO posto(nome, criado_em) VALUES ('Posto Legado', 'ontem')")
    raw.commit()
    raw.close()

    migrado = banco.conectar(caminho)
    try:
        assert migrado.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 8
        assert migrado.execute("SELECT nome FROM posto").fetchone()[0] == "Posto Legado"
        assert migrado.execute("SELECT COUNT(*) FROM autonomia").fetchone()[0] == 0
        colunas = {row["name"] for row in migrado.execute("PRAGMA table_info(autonomia)")}
        assert colunas == {
            "id", "chave_tipo", "aprovacoes_seguidas", "automatico",
            "desligado_por_admin", "atualizado_em",
        }
    finally:
        migrado.close()
