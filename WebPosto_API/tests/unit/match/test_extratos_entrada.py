import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.match import agendador, banco, caminhos, relatorio_xlsx, unidades
from apps.match.extratos import entrada
from src.modules.cash_reconciliation.domain.tempo import FUSO


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    c = banco.conectar(tmp_path / "logos.db")
    yield c
    c.close()


def _ofx(banco_id="001", conta="1234564068-X", transacoes=None):
    transacoes = transacoes or [
        ("CREDIT", "10.00", "fit-1", "Venda", "doc-1"),
        ("DEBIT", "-2.50", "fit-2", "Tarifa", "doc-2"),
    ]
    linhas = "\n".join(
        f"""<STMTTRN><TRNTYPE>{tipo}</TRNTYPE><DTPOSTED>20261029120000[-3:BRT]</DTPOSTED>
<TRNAMT>{valor}</TRNAMT><FITID>{fitid}</FITID><MEMO>{descricao}</MEMO><CHECKNUM>{documento}</CHECKNUM></STMTTRN>"""
        for tipo, valor, fitid, descricao, documento in transacoes
    )
    return f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:UTF-8
CHARSET:NONE
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM>
<BANKID>{banco_id}</BANKID><BRANCHID>0001</BRANCHID><ACCTID>{conta}</ACCTID>
</BANKACCTFROM><BANKTRANLIST><DTSTART>20261001000000</DTSTART>
<DTEND>20261031120000</DTEND>{linhas}</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>""".encode()


def _colocar_entrada(con, nome, conteudo):
    pasta = caminhos.extratos(con) / "Entrada"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_bytes(conteudo)
    return arquivo


def _conta(con, posto_id, banco_nome="BB", sufixo="4068-X", cd_conta=86248):
    cur = con.execute(
        "INSERT INTO conta_bancaria"
        "(posto_id, banco, agencia, conta_sufixo, cd_conta_webposto) VALUES (?,?,?,?,?)",
        (posto_id, banco_nome, "0001", sufixo, cd_conta),
    )
    con.commit()
    return cur.lastrowid


def test_caminhos_extratos_prefere_rede_e_faz_fallback(con, tmp_path):
    rede = tmp_path / "rede"
    rede.mkdir()
    banco.salvar_pasta_rede(con, str(rede))
    assert caminhos.extratos(con) == rede / "Extratos"

    banco.salvar_pasta_rede(con, str(rede / "inexistente"))
    assert caminhos.extratos(con) == tmp_path / "Extratos"


def test_ofx_invalido_vai_para_recusados(con):
    arquivo = _colocar_entrada(con, "invalido.ofx", b"nao e ofx")

    [resultado] = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 0, tzinfo=FUSO))

    assert resultado.situacao == "recusado"
    assert resultado.mensagem == "Arquivo não é um extrato OFX válido."
    assert not arquivo.exists()
    assert (caminhos.extratos(con) / "Recusados" / "invalido.ofx").exists()
    row = con.execute("SELECT situacao, motivo FROM extrato_arquivo").fetchone()
    assert tuple(row) == ("recusado", "Arquivo não é um extrato OFX válido.")


def test_mesmo_arquivo_duas_vezes_vai_para_duplicados(con):
    posto_id = banco.inserir_posto(con, "Posto A", "Posto A", None, 74014)
    _conta(con, posto_id)
    conteudo = _ofx()
    _colocar_entrada(con, "primeiro.ofx", conteudo)
    [primeiro] = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 0, tzinfo=FUSO))
    assert primeiro.situacao == "lido"

    _colocar_entrada(con, "copia.ofx", conteudo)
    resultados = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 1, tzinfo=FUSO))

    assert len(resultados) == 1
    assert resultados[0].situacao == "duplicado"
    assert (caminhos.extratos(con) / "Duplicados" / "copia.ofx").exists()
    assert con.execute("SELECT COUNT(*) FROM extrato_arquivo").fetchone()[0] == 1


def test_periodo_sobreposto_so_conta_linhas_novas(con):
    posto_id = banco.inserir_posto(con, "Posto A", "Posto A", None, 74014)
    conta_id = _conta(con, posto_id)
    primeira = [
        ("CREDIT", "10.00", "a", "Linha A", "doc-a"),
        ("CREDIT", "20.00", "b", "Linha B", "doc-b"),
        ("DEBIT", "-3.00", "c", "Linha C", "doc-c"),
    ]
    segunda = primeira + [("DEBIT", "-4.00", "d", "Linha D", "doc-d")]
    _colocar_entrada(con, "outubro.ofx", _ofx(transacoes=primeira))
    [r1] = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 0, tzinfo=FUSO))
    _colocar_entrada(con, "sobreposto.ofx", _ofx(transacoes=segunda))
    [r2] = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 1, tzinfo=FUSO))

    assert r1.novas_linhas == 3
    assert r2.novas_linhas == 1
    assert con.execute(
        "SELECT COUNT(*) FROM extrato_linha WHERE conta_bancaria_id=?", (conta_id,)
    ).fetchone()[0] == 4


def test_fitid_vazio_usa_hash(con):
    posto_id = banco.inserir_posto(con, "Posto A", "Posto A", None, 74014)
    conta_id = _conta(con, posto_id)
    _colocar_entrada(con, "sem-fitid.ofx", _ofx(transacoes=[
        ("CREDIT", "10.00", "", "Venda sem identificador", "doc-9"),
    ]))

    [resultado] = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 0, tzinfo=FUSO))

    row = con.execute(
        "SELECT chave, fitid FROM extrato_linha WHERE conta_bancaria_id=?", (conta_id,)
    ).fetchone()
    esperado = hashlib.sha256(
        "2026-10-29|10.00|Venda sem identificador|doc-9".encode()
    ).hexdigest()
    assert resultado.novas_linhas == 1
    assert row["chave"] == f"h:{esperado}"
    assert row["fitid"] in (None, "")


def test_conta_desconhecida_aguarda_vinculo_e_vincular_processa(con):
    _colocar_entrada(con, "desconhecido.ofx", _ofx(
        banco_id="290",
        conta="12345",
        transacoes=[
            ("IN", "10.00", "pag-1", "Crédito PagBank", "doc-1"),
            ("OUT", "-2.50", "pag-2", "Débito PagBank", "doc-2"),
        ],
    ))

    [resultado] = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 0, tzinfo=FUSO))

    assert resultado.situacao == "aguardando_vinculo"
    row = con.execute("SELECT id, situacao FROM extrato_arquivo").fetchone()
    assert row["situacao"] == "aguardando_vinculo"
    assert (caminhos.extratos(con) / "Aguardando" / "desconhecido.ofx").exists()

    posto_id = banco.inserir_posto(con, "Posto Pag", "Pag", None, 74015)
    novas = entrada.vincular(con, row["id"], posto_id, 96123)

    assert novas == 2
    conta = con.execute("SELECT banco, conta_sufixo, cd_conta_webposto FROM conta_bancaria").fetchone()
    assert tuple(conta) == ("PAGBANK", "12345", 96123)
    assert con.execute("SELECT situacao FROM extrato_arquivo").fetchone()[0] == "lido"
    assert con.execute("SELECT COUNT(*) FROM extrato_linha").fetchone()[0] == 2
    assert [r[0] for r in con.execute("SELECT tipo FROM extrato_linha ORDER BY id")] == [
        "CREDIT", "DEBIT",
    ]


def test_arquivado_na_pasta_do_posto_conta_mes(con):
    posto_id = banco.inserir_posto(con, "Posto A", "Açúcar / Sul", None, 74014)
    _conta(con, posto_id)
    _colocar_entrada(con, "banco.ofx", _ofx())

    [resultado] = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 5, tzinfo=FUSO))

    pasta_posto = relatorio_xlsx.nome_seguro("Açúcar / Sul", posto_id)
    destino = (caminhos.extratos(con) / pasta_posto / "BB-4068-X" / "2026-10")
    arquivado = list(destino.glob("20261101-1005_banco.ofx"))
    assert resultado.situacao == "lido"
    assert len(arquivado) == 1
    row = con.execute("SELECT caminho_arquivado FROM extrato_arquivo").fetchone()
    assert Path(row["caminho_arquivado"]) == arquivado[0]


def test_arquivo_invalido_nao_interrompe_outros(con):
    _colocar_entrada(con, "01-invalido.ofx", b"texto")
    posto_id = banco.inserir_posto(con, "Posto A", "A", None, 74014)
    _conta(con, posto_id)
    _colocar_entrada(con, "02-valido.ofx", _ofx())

    resultados = entrada.processar_pasta(con, datetime(2026, 11, 1, 10, 0, tzinfo=FUSO))

    assert [r.situacao for r in resultados] == ["recusado", "lido"]
    assert con.execute("SELECT COUNT(*) FROM extrato_linha").fetchone()[0] == 2


@pytest.mark.parametrize("modo", ["mudanca_tamanho", "permissao"])
def test_arquivo_em_escrita_fica_para_depois(con, monkeypatch, modo):
    arquivo = _colocar_entrada(con, "gravando.ofx", _ofx())
    monkeypatch.setattr(entrada.time, "sleep", lambda _: None)
    original_stat = Path.stat
    chamadas = 0

    def stat(path, *args, **kwargs):
        nonlocal chamadas
        if path == arquivo:
            if modo == "permissao":
                raise PermissionError
            chamadas += 1
            resultado = original_stat(path, *args, **kwargs)
            return SimpleNamespace(st_size=resultado.st_size + (chamadas > 1))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    assert entrada.processar_pasta(
        con, datetime(2026, 11, 1, 10, 0, tzinfo=FUSO)
    ) == []
    assert arquivo.exists()
    assert con.execute("SELECT COUNT(*) FROM extrato_arquivo").fetchone()[0] == 0


def test_montar_preenche_contas_extrato(con):
    posto_id = banco.inserir_posto(con, "Posto A", "A", None, 74014)
    _conta(con, posto_id, "PAGBANK", "9048-8", 86188)

    unidade = unidades.montar(con)[74014]

    assert len(unidade.contas_extrato) == 1
    assert unidade.contas_extrato[0].banco == "PAGBANK"
    assert unidade.contas_extrato[0].conta_sufixo == "9048-8"
    assert unidade.contas_extrato[0].cd_conta == 86188


def test_importar_units_json_cria_contas_bancarias(con, tmp_path):
    arquivo = tmp_path / "units.json"
    arquivo.write_text(json.dumps({"unidades": [{
        "empresa_codigo": 74014,
        "nome": "Posto Pag",
        "apelido": "Pag",
        "contas_extrato": [{
            "banco": "PAGBANK", "agencia": "0001", "conta_sufixo": "9048-8", "cd_conta": 86188,
        }],
    }]}), encoding="utf-8")

    assert unidades.importar_units_json(con, arquivo) == 1
    row = con.execute(
        "SELECT p.id AS posto_id, banco, agencia, conta_sufixo, cd_conta_webposto "
        "FROM conta_bancaria JOIN posto p ON p.id=conta_bancaria.posto_id"
    ).fetchone()
    assert row["posto_id"] is not None
    assert tuple(row)[1:] == ("PAGBANK", "0001", "9048-8", 86188)


def test_migracao_6_de_banco_v5_preserva_dados(tmp_path):
    caminho = tmp_path / "v5.db"
    bruto = sqlite3.connect(caminho)
    bruto.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    for versao, sql in banco._MIGRACOES[:5]:
        bruto.executescript(sql)
        bruto.execute("INSERT INTO schema_version(version) VALUES (?)", (versao,))
    bruto.execute(
        "INSERT INTO posto(nome, apelido, criado_em) VALUES ('Posto legado', 'Legado', '2026-01-01')"
    )
    bruto.execute("INSERT INTO empresa(cnpj, razao_social, criado_em) VALUES ('1', 'Empresa', 'x')")
    bruto.commit()
    bruto.close()

    migrado = banco.conectar(caminho)
    try:
        assert migrado.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 8
        assert migrado.execute("SELECT nome FROM posto").fetchone()[0] == "Posto legado"
        assert migrado.execute("SELECT razao_social FROM empresa").fetchone()[0] == "Empresa"
        tabelas = {r[0] for r in migrado.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert {"conta_bancaria", "extrato_arquivo", "extrato_linha"} <= tabelas
    finally:
        migrado.close()


def test_job_extratos_agendado_e_isolado(con, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path))
    monkeypatch.setattr(agendador, "agora", lambda: datetime(2026, 11, 1, 5, 0, tzinfo=FUSO))
    sched = agendador.iniciar(lambda: banco.conectar(tmp_path / "agenda.db"), pausado=True)
    try:
        jobs = {job.id: job for job in sched.get_jobs()}
        assert "extratos" in jobs
        assert jobs["extratos"].trigger.interval.total_seconds() == 60
        assert "extratos_inicio" in jobs
    finally:
        sched.shutdown(wait=False)

    def explode(*args, **kwargs):
        raise RuntimeError("erro detalhado não deve entrar no log")

    monkeypatch.setattr(entrada, "processar_pasta", explode)
    agendador._job_extratos(lambda: banco.conectar(tmp_path / "agenda.db"))
    assert "tipo=RuntimeError" in caplog.text
    assert "erro detalhado" not in caplog.text
