import hashlib
import json
import sqlite3
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.match import banco
from apps.match.extratos import aprovacoes, camada1, camada2
from src.modules.cash_reconciliation.adapters.webposto_escrita_ofx import (
    registrar_envio_historico,
)
from src.modules.cash_reconciliation.domain.tempo import FUSO


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    monkeypatch.setattr(camada2, "analisar", lambda *args: [])
    c = banco.conectar(tmp_path / "camada1.db")
    yield c
    c.close()


def _posto_conta(con, *, enviar=False, banco_nome="BB", sufixo="4068-X"):
    posto_id = banco.inserir_posto(con, "Posto Teste", "Teste", None, 74014)
    con.execute("UPDATE posto SET enviar_extratos_webposto=? WHERE id=?",
                (int(enviar), posto_id))
    cur = con.execute(
        """INSERT INTO conta_bancaria
           (posto_id, banco, agencia, conta_sufixo, cd_conta_webposto)
           VALUES (?,?,?,?,?)""",
        (posto_id, banco_nome, "0001", sufixo, 86248),
    )
    con.commit()
    return posto_id, cur.lastrowid


def _linha(con, conta_id, dia, valor="10.00", fitid=None, *, importada=False):
    cur = con.execute(
        """INSERT INTO extrato_arquivo
           (sha256, nome_original, recebido_em, situacao)
           VALUES (?,?,?,'lido')""",
        (hashlib.sha256(f"{dia}-{fitid}".encode()).hexdigest(),
         f"{fitid or dia}.ofx", datetime(2026, 11, 1, tzinfo=FUSO).isoformat()),
    )
    arquivo_id = cur.lastrowid
    cur = con.execute(
        """INSERT INTO extrato_linha
           (conta_bancaria_id, arquivo_id, chave, fitid, data, valor, tipo, descricao,
            documento, categoria, importada_webposto)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (conta_id, arquivo_id, fitid or f"h:{dia}", fitid, dia, valor,
         "CREDIT" if Decimal(valor) >= 0 else "DEBIT", f"Transação {fitid or dia}",
         f"doc-{fitid or dia}", "outros", int(importada)),
    )
    con.commit()
    return cur.lastrowid


def _resumo_previa(con, monkeypatch):
    posto_id, conta_id = _posto_conta(con, enviar=True)
    hoje = date(2026, 11, 1)
    for offset in range(1, 17):
        dia = (hoje - timedelta(days=offset)).isoformat()
        _linha(con, conta_id, dia, fitid=f"fit-{offset}")
    _linha(con, conta_id, hoje.isoformat(), fitid="hoje")
    monkeypatch.setattr(camada1, "hoje", lambda: hoje)
    monkeypatch.setattr(
        camada1,
        "enviar_ofx_webposto",
        lambda *args, **kwargs: pytest.fail("A prévia não consulta o webPosto."),
    )
    return posto_id, conta_id


def test_previa_so_dias_novos_e_janelas_de_7(con, monkeypatch):
    _posto_id, conta_id = _resumo_previa(con, monkeypatch)

    previa = camada1.montar_previa(con, conta_id)

    assert previa is not None
    assert previa["total_linhas"] == 16
    periodos = previa["periodos"]
    assert [(p["de"], p["ate"], p["linhas"]) for p in periodos] == [
        ("2026-10-16", "2026-10-22", 7),
        ("2026-10-23", "2026-10-29", 7),
        ("2026-10-30", "2026-10-31", 2),
    ]
    assert all((date.fromisoformat(p["ate"]) - date.fromisoformat(p["de"])).days < 7
               for p in periodos)
    assert all(p["dias_ja_enviados"] == [] for p in periodos)


def _registrar_dias_enviados(tmp_path, dias):
    diretorio = tmp_path / "importacoes_ofx"
    for dia in dias:
        registrar_envio_historico(
            diretorio,
            74014,
            {
                "cd_conta": 86248,
                "data_inicial": dia,
                "data_final": dia,
                "data_envio": "2026-11-01T12:00:00+00:00",
                "status": "enviado_aguardando_conferencia",
            },
        )


def test_previa_sem_dias_novos_no_historico_nao_cria_aprovacao(con, tmp_path, monkeypatch):
    _posto_id, conta_id = _resumo_previa(con, monkeypatch)
    dias = [(date(2026, 11, 1) - timedelta(days=i)).isoformat() for i in range(1, 17)]
    _registrar_dias_enviados(tmp_path, dias)

    assert camada1.montar_previa(con, conta_id) is None
    assert con.execute("SELECT COUNT(*) FROM aprovacao").fetchone()[0] == 0


def test_previa_pula_dias_ja_enviados_no_historico(con, tmp_path, monkeypatch):
    _posto_id, conta_id = _resumo_previa(con, monkeypatch)
    dias = ["2026-10-25", "2026-10-26"]
    _registrar_dias_enviados(tmp_path, dias)

    previa = camada1.montar_previa(con, conta_id)

    assert previa is not None
    assert previa["total_linhas"] == 14
    periodo = next(p for p in previa["periodos"] if p["de"] == "2026-10-23")
    assert periodo["ate"] == "2026-10-29"
    assert periodo["linhas"] == 5
    assert periodo["entradas"] == "50.00"
    assert periodo["saidas"] == "0"
    assert periodo["dias_ja_enviados"] == dias
    assert "dias_existentes" not in periodo


def test_execucao_separa_dias_ja_enviados_do_historico(con, tmp_path, monkeypatch):
    posto_id, conta_id = _posto_conta(con, enviar=True)
    linha_ids = [
        _linha(con, conta_id, f"2026-10-{dia}", fitid=f"fit-{dia}")
        for dia in (29, 30, 31)
    ]
    _registrar_dias_enviados(tmp_path, ["2026-10-30"])
    monkeypatch.setattr(camada1, "hoje", lambda: date(2026, 11, 1))
    previa = camada1.montar_previa(con, conta_id)
    assert previa is not None
    assert previa["periodos"][0]["linha_ids"] == [linha_ids[0], linha_ids[2]]
    assert previa["periodos"][0]["dias_ja_enviados"] == ["2026-10-30"]
    assert aprovacoes.decidir(con, previa["ticket"], True, "teste", "painel")[0]
    chamadas = []

    async def writer(unidade, arquivo, **kwargs):
        chamadas.append((kwargs["data_inicial"], kwargs["data_final"]))
        return SimpleNamespace(sucesso=True, modo="enviado", mensagem="ok")

    monkeypatch.setattr(camada1, "enviar_ofx_webposto", writer)
    monkeypatch.setattr(camada1, "_notificar", lambda *args: None)

    ok, _mensagem = camada1.executar(con, previa["aprovacao_id"])

    assert ok
    assert chamadas == [
        (date(2026, 10, 29), date(2026, 10, 29)),
        (date(2026, 10, 31), date(2026, 10, 31)),
    ]


def test_previa_tem_aviso_de_dias_ignorados_pelo_webposto(con, monkeypatch):
    _posto_id, conta_id = _resumo_previa(con, monkeypatch)

    previa = camada1.montar_previa(con, conta_id)

    assert previa is not None
    assert previa["aviso"] == "Dias que o webPosto já tiver serão ignorados por ele na importação."


def test_sem_linhas_novas_nao_cria_aprovacao(con, monkeypatch):
    _posto_id, conta_id = _posto_conta(con, enviar=True)
    _linha(con, conta_id, "2026-10-31", fitid="feito", importada=True)
    monkeypatch.setattr(camada1, "hoje", lambda: date(2026, 11, 1))

    assert camada1.montar_previa(con, conta_id) is None
    assert con.execute("SELECT COUNT(*) FROM aprovacao").fetchone()[0] == 0


def test_uma_pendente_por_conta(con, monkeypatch):
    _posto_id, conta_id = _resumo_previa(con, monkeypatch)

    primeira = camada1.montar_previa(con, conta_id)
    segunda = camada1.montar_previa(con, conta_id)

    assert primeira is not None and segunda is not None
    assert con.execute(
        "SELECT COUNT(*) FROM aprovacao WHERE conta_bancaria_id=? AND situacao='pendente'",
        (conta_id,),
    ).fetchone()[0] == 1
    assert segunda["aprovacao_id"] == primeira["aprovacao_id"]
    row = con.execute(
        "SELECT resumo_json, hash, ticket FROM aprovacao WHERE id=?",
        (primeira["aprovacao_id"],),
    ).fetchone()
    assert len(row["ticket"]) == 12
    assert row["hash"] == hashlib.sha256(row["resumo_json"].encode("utf-8")).hexdigest()
    assert row["resumo_json"] == json.dumps(
        json.loads(row["resumo_json"]), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def test_previa_nao_duplica_aprovacao_ja_aprovada(con, monkeypatch):
    _posto_id, conta_id = _resumo_previa(con, monkeypatch)
    previa = camada1.montar_previa(con, conta_id)
    aprovacoes.decidir(con, previa["ticket"], True, "teste", "painel")

    assert camada1.montar_previa(con, conta_id) is None
    assert con.execute(
        "SELECT COUNT(*) FROM aprovacao WHERE conta_bancaria_id=?", (conta_id,)
    ).fetchone()[0] == 1


def test_aprovar_executa_e_marca_importadas(con, tmp_path, monkeypatch):
    posto_id, conta_id = _posto_conta(con, enviar=True)
    linha_id = _linha(con, conta_id, "2026-10-31", "12.35", "fit-1")
    resumo = {
        "conta_id": conta_id, "posto_id": posto_id,
        "periodos": [{
            "de": "2026-10-31", "ate": "2026-10-31", "linhas": 1,
            "linha_ids": [linha_id],
            "entradas": "12.35", "saidas": "0.00", "dias_ja_enviados": [],
        }],
        "total_linhas": 1,
    }
    aprovacao = aprovacoes.criar(con, "importar_extrato", posto_id, conta_id, resumo)
    assert aprovacoes.decidir(con, aprovacao["ticket"], True, "teste", "painel")[0]
    chamadas = []

    async def writer(unidade, arquivo, **kwargs):
        chamadas.append((unidade, Path(arquivo).read_text(encoding="utf-8"), kwargs))
        return SimpleNamespace(sucesso=True, modo="enviado", mensagem="Importado")

    monkeypatch.setattr(camada1, "enviar_ofx_webposto", writer)
    monkeypatch.setattr(camada1.caminhos, "raiz", lambda: tmp_path)
    notificacoes = []
    monkeypatch.setattr(camada1, "_notificar", lambda *args: notificacoes.append(args))

    ok, mensagem = camada1.executar(con, aprovacao["id"])

    assert ok is True
    assert mensagem == "Enviado ao webPosto; dias já existentes foram ignorados por ele."
    assert len(chamadas) == 1
    unidade, texto, kwargs = chamadas[0]
    assert unidade.contas_extrato[0].cd_conta == 86248
    assert all(tag in texto for tag in ("<TRNTYPE>CREDIT", "<DTPOSTED>20261031",
                                        "<TRNAMT>12.35", "<FITID>fit-1", "<MEMO>"))
    assert kwargs["confirmar"] is True
    assert kwargs["autorizacao"]() == (True, "")
    assert kwargs["diretorio_historico"] == tmp_path / "importacoes_ofx"
    assert con.execute("SELECT importada_webposto FROM extrato_linha WHERE id=?",
                       (linha_id,)).fetchone()[0] == 1
    assert con.execute("SELECT situacao FROM aprovacao WHERE id=?",
                       (aprovacao["id"],)).fetchone()[0] == "executada"
    assert con.execute("SELECT resultado FROM aprovacao WHERE id=?",
                       (aprovacao["id"],)).fetchone()[0] == mensagem
    assert camada1.AVISO_DIAS_IGNORADOS in notificacoes[0][2]


def _aprovacao_para_executar(con, posto_id, conta_id, linha_id):
    resumo = {
        "conta_id": conta_id, "posto_id": posto_id,
        "periodos": [{
            "de": "2026-10-31", "ate": "2026-10-31", "linhas": 1,
            "linha_ids": [linha_id],
            "entradas": "0.00", "saidas": "10.00", "dias_ja_enviados": [],
        }],
        "total_linhas": 1,
    }
    return aprovacoes.criar(con, "importar_extrato", posto_id, conta_id, resumo)


def test_falha_webposto_fica_falhou_e_nao_marca(con, monkeypatch):
    posto_id, conta_id = _posto_conta(con, enviar=True)
    linha_id = _linha(con, conta_id, "2026-10-31", "-10.00", "fit-falha")
    aprovacao = _aprovacao_para_executar(con, posto_id, conta_id, linha_id)
    aprovacoes.decidir(con, aprovacao["ticket"], True, "teste", "painel")

    async def writer(*args, **kwargs):
        raise TimeoutError("detalhe sensível")

    monkeypatch.setattr(camada1, "enviar_ofx_webposto", writer)
    monkeypatch.setattr(camada1, "_notificar", lambda *args: None)

    ok, mensagem = camada1.executar(con, aprovacao["id"])

    assert ok is False
    assert "TimeoutError" in mensagem
    assert "detalhe sensível" not in mensagem
    assert con.execute("SELECT situacao FROM aprovacao WHERE id=?",
                       (aprovacao["id"],)).fetchone()[0] == "falhou"
    assert con.execute("SELECT importada_webposto FROM extrato_linha WHERE id=?",
                       (linha_id,)).fetchone()[0] == 0


def test_trava_do_posto_desligada_bloqueia_envio(con, monkeypatch):
    posto_id, conta_id = _posto_conta(con, enviar=False)
    linha_id = _linha(con, conta_id, "2026-10-31", "-10.00", "fit-off")
    aprovacao = _aprovacao_para_executar(con, posto_id, conta_id, linha_id)
    aprovacoes.decidir(con, aprovacao["ticket"], True, "teste", "painel")
    observadas = []

    async def writer(unidade, arquivo, *, autorizacao, **kwargs):
        autorizado = autorizacao()
        observadas.append(autorizado)
        return SimpleNamespace(sucesso=autorizado[0], mensagem=autorizado[1])

    monkeypatch.setattr(camada1, "enviar_ofx_webposto", writer)
    monkeypatch.setattr(camada1, "_notificar", lambda *args: None)

    ok, mensagem = camada1.executar(con, aprovacao["id"])

    assert observadas == [(False, "Envio de extratos ao webPosto está desligado para este posto.")]
    assert ok is False and "desligado" in mensagem
    assert con.execute("SELECT importada_webposto FROM extrato_linha WHERE id=?",
                       (linha_id,)).fetchone()[0] == 0
    assert con.execute("SELECT situacao FROM aprovacao WHERE id=?",
                       (aprovacao["id"],)).fetchone()[0] == "falhou"


def test_decidir_duas_vezes_ja_resolvido_concorrente(con):
    posto_id, conta_id = _posto_conta(con)
    resumo = {"posto_id": posto_id, "conta_id": conta_id, "periodos": []}
    aprovacao = aprovacoes.criar(con, "importar_extrato", posto_id, conta_id, resumo)
    barreira = threading.Barrier(2)
    resultados = []
    caminho_db = Path(con.execute("PRAGMA database_list").fetchone()[2])

    def decidir(aprovar):
        conexao = banco.conectar(caminho_db)
        try:
            barreira.wait()
            resultados.append(aprovacoes.decidir(
                conexao, aprovacao["ticket"], aprovar, "thread", "painel"
            ))
        finally:
            conexao.close()

    t1 = threading.Thread(target=decidir, args=(True,))
    t2 = threading.Thread(target=decidir, args=(False,))
    t1.start()
    t2.start()
    t1.join(10)
    t2.join(10)

    assert not t1.is_alive() and not t2.is_alive()
    assert sorted(result[0] for result in resultados) == [False, True]
    assert (False, "Já resolvido.") in resultados
    assert con.execute("SELECT situacao FROM aprovacao WHERE id=?",
                       (aprovacao["id"],)).fetchone()[0] in ("aprovada", "recusada")


def test_migracao_7_preserva_dados_de_v6(tmp_path):
    caminho = tmp_path / "v6.db"
    raw = sqlite3.connect(caminho)
    raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    for versao, sql in banco._MIGRACOES[:6]:
        raw.executescript(sql)
        raw.execute("INSERT INTO schema_version(version) VALUES (?)", (versao,))
    raw.execute("INSERT INTO posto(nome, criado_em) VALUES ('Legado', 'x')")
    raw.commit()
    raw.close()

    c = banco.conectar(caminho)
    try:
        assert c.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 7
        assert c.execute("SELECT nome, enviar_extratos_webposto FROM posto").fetchone()[:] == (
            "Legado", 0,
        )
        assert "aprovacao" in {
            row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        c.close()
