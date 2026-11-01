import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from apps.match import acesso, banco
from apps.match.fiscal import repositorio as repo
from src.modules.fiscal_docs.parser import ler
from src.modules.fiscal_docs.webposto_notas import EntradaWebposto, NotaListada

DADOS = Path(__file__).resolve().parents[1] / "fiscal_docs" / "dados"


@pytest.fixture
def con(tmp_path):
    c = banco.conectar(tmp_path / "f.db")
    yield c
    c.close()


def _empresa(con):
    pid = banco.inserir_posto(con, "Doze Filial II", "doze", "52308604000284", 74014)
    return repo.salvar_empresa(con, "52.308.604/0002-84", "POSTO DOZE", "doze", "Abreu e Lima", "PE", pid)


def _doc(nome):
    return ler((DADOS / nome).read_bytes())


def test_banco_novo_na_versao_5(con):
    assert con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 9


def test_migra_v4_preserva_usuarios_e_aceita_contabilidade(tmp_path):
    caminho = tmp_path / "v4.db"
    raw = sqlite3.connect(str(caminho))
    raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    raw.executescript(banco._SCHEMA_V1 + banco._SCHEMA_V2 + banco._SCHEMA_V3 + banco._SCHEMA_V4)
    raw.executemany("INSERT INTO schema_version(version) VALUES (?)", [(1,), (2,), (3,), (4,)])
    raw.execute("INSERT INTO posto(nome, criado_em) VALUES ('Doze', 'x')")
    raw.execute("INSERT INTO usuario(nome, login, senha_hash, perfil, criado_em) "
                "VALUES ('Adm', 'adm', 'h', 'administrador', 'x')")
    raw.execute("INSERT INTO usuario_posto VALUES (1, 1)")
    raw.execute("INSERT INTO log_acesso(usuario_id, momento, acao) VALUES (1, 'x', 'login')")
    raw.commit()
    raw.close()
    con = banco.conectar(caminho)
    try:
        assert con.execute("SELECT login FROM usuario").fetchone()[0] == "adm"
        assert con.execute("SELECT COUNT(*) FROM usuario_posto").fetchone()[0] == 1
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        uid = acesso.criar_usuario(con, "Contadora", "conta", "senha-forte-1",
                                   acesso.Perfil("contabilidade"), [1])
        assert con.execute("SELECT perfil FROM usuario WHERE id=?", (uid,)).fetchone()[0] == "contabilidade"
    finally:
        con.close()


def test_gravar_documento_idempotente(con):
    eid = _empresa(con)
    d = _doc("nfe_combustivel.xml")
    assert repo.gravar_documento(con, eid, d, Path("x.xml"), "h1", "webposto") is True
    assert repo.gravar_documento(con, eid, d, Path("x.xml"), "h1", "importado") is False
    assert con.execute("SELECT COUNT(*) FROM documento").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM documento_item").fetchone()[0] == 2
    t = con.execute("SELECT * FROM documento_transporte").fetchone()
    assert (t["mod_frete_texto"], t["placa"]) == ("FOB", "ABC1D23")


def test_so_resumo_promovido(con):
    eid = _empresa(con)
    d = _doc("nfe_combustivel.xml")
    nota = NotaListada(chave=d.chave, emitente_cnpj="11111111000191", emitente_nome="DISTRIB",
                       emissao=date(2026, 10, 31), valor=Decimal("43617.28"))
    assert repo.registrar_so_resumo(con, eid, nota) is True
    assert repo.registrar_so_resumo(con, eid, nota) is False
    entrada = EntradaWebposto(chave=d.chave, tipo_frete="F", valor_frete=Decimal("350"), cte_numero="998")
    assert repo.gravar_documento(con, eid, d, Path("x.xml"), "h", "webposto", entrada) is True
    row = con.execute("SELECT situacao, cte_numero, xml_path FROM documento").fetchone()
    assert tuple(row) == ("autorizada", "998", "x.xml")


def test_buscar_por_fornecedor_e_cnpj(con):
    eid = _empresa(con)
    repo.gravar_documento(con, eid, _doc("nfe_combustivel.xml"), Path("a"), "a", "webposto")
    repo.gravar_documento(con, eid, _doc("nfe_produto.xml"), Path("b"), "b", "webposto")
    por_nome = repo.buscar_documentos(con, repo.FiltroDocs(empresas=[eid], fornecedor="distrib"))
    assert [r["numero"] for r in por_nome] == ["12345"]
    por_cnpj = repo.buscar_documentos(con, repo.FiltroDocs(empresas=[eid], fornecedor="33.333.333/0001-91"))
    assert [r["numero"] for r in por_cnpj] == ["77"]
    comb = repo.buscar_documentos(con, repo.FiltroDocs(empresas=[eid], combustivel=True))
    assert len(comb) == 1
    periodo = repo.buscar_documentos(con, repo.FiltroDocs(empresas=[eid], inicio=date(2026, 10, 1),
                                                          fim=date(2026, 10, 15)))
    assert [r["numero"] for r in periodo] == ["77"]
    assert repo.buscar_documentos(con, repo.FiltroDocs(empresas=[])) == []


def test_escritorio_e_empresas(con):
    eid = _empresa(con)
    oid = repo.salvar_escritorio(con, "Contab A", ["a@x.com"], 5, "enviar", "ambos", [eid])
    assert [e["id"] for e in repo.empresas_do_escritorio(con, oid)] == [eid]
    with pytest.raises(sqlite3.IntegrityError):
        repo.salvar_escritorio(con, "Ruim", ["a@x.com"], 31, "enviar", "ambos", [])
