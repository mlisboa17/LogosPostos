import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from apps.match import banco, credenciais
from apps.match.fiscal import conferencia, pacote, repositorio as repo
from src.modules.fiscal_docs import acervo
from src.modules.fiscal_docs.parser import ler
from src.modules.fiscal_docs.webposto_notas import EntradaWebposto, NotaListada

DADOS = Path(__file__).resolve().parents[1] / "fiscal_docs" / "dados"
CNPJ = "52308604000284"
AGORA = datetime(2026, 11, 5, 11, 0, tzinfo=timezone.utc)


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "p.db")
    yield c
    c.close()


def _empresa(con, chave=True):
    pid = banco.inserir_posto(con, "Doze", "doze", CNPJ, 74014)
    banco.salvar_fonte(con, pid, "webposto", True, {})
    if chave:
        credenciais.salvar(f"{pid}/webposto/chave", "K")
    return repo.salvar_empresa(con, CNPJ, "POSTO DOZE", "doze", "Abreu e Lima", "PE", pid)


def _gravar(con, eid, tmp_path, nome, entrada=None):
    xml = (DADOS / nome).read_bytes()
    doc = ler(xml)
    p = acervo.gravar(tmp_path / "acervo", CNPJ, doc, xml, "webposto")
    repo.gravar_documento(con, eid, doc, p, "h", "webposto", entrada)
    return doc


def _nomes(z: Path) -> list[str]:
    with zipfile.ZipFile(z) as f:
        return sorted(f.namelist())


def test_competencia_pelo_fuso_de_recife(con, tmp_path):
    eid = _empresa(con)
    doc = _gravar(con, eid, tmp_path, "nfe_combustivel.xml")  # 31/10 23:30 -03:00
    [z] = pacote.montar(con, eid, "2026-10", "separados", tmp_path / "out").partes
    assert f"xml/{doc.chave}.xml" in _nomes(z)
    assert pacote.montar(con, eid, "2026-11", "separados", tmp_path / "out2").partes == []


def test_modos_de_pdf(con, tmp_path):
    eid = _empresa(con)
    a = _gravar(con, eid, tmp_path, "nfe_combustivel.xml")
    b = _gravar(con, eid, tmp_path, "nfe_produto.xml")
    [z] = pacote.montar(con, eid, "2026-10", "unificado", tmp_path / "u").partes
    assert z.name == f"{CNPJ}_2026-10.zip"
    assert _nomes(z) == sorted([f"xml/{a.chave}.xml", f"xml/{b.chave}.xml",
                                f"pdf/{CNPJ}_2026-10_notas.pdf", "Resumo_doze_10-2026.xlsx"])
    [z] = pacote.montar(con, eid, "2026-10", "ambos", tmp_path / "a").partes
    assert {f"pdf/{a.chave}.pdf", f"pdf/{b.chave}.pdf", f"pdf/{CNPJ}_2026-10_notas.pdf"} <= set(_nomes(z))
    [z] = pacote.montar(con, eid, "2026-10", "separados", tmp_path / "s").partes
    assert f"pdf/{CNPJ}_2026-10_notas.pdf" not in _nomes(z)


def test_divide_em_partes(con, tmp_path, monkeypatch):
    eid = _empresa(con)
    _gravar(con, eid, tmp_path, "nfe_combustivel.xml")
    _gravar(con, eid, tmp_path, "nfe_produto.xml")
    monkeypatch.setattr(pacote, "LIMITE_BYTES", 8 * 1024)
    partes = pacote.montar(con, eid, "2026-10", "ambos", tmp_path / "d").partes
    assert len(partes) > 1
    assert [p.name for p in partes] == [f"{CNPJ}_2026-10_parte{i}.zip" for i in range(1, len(partes) + 1)]
    assert "Resumo_doze_10-2026.xlsx" in _nomes(partes[0])
    for p in partes:
        assert p.stat().st_size <= pacote.LIMITE_BYTES or len(_nomes(p)) == 1


def test_complementar_so_com_novos(con, tmp_path):
    eid = _empresa(con)
    _gravar(con, eid, tmp_path, "nfe_combustivel.xml")
    ja = {con.execute("SELECT id FROM documento").fetchone()[0]}
    b = _gravar(con, eid, tmp_path, "nfe_produto.xml")
    m = pacote.montar(con, eid, "2026-10", "separados", tmp_path / "c", complementar=True, excluir=ja)
    [z] = m.partes
    assert len(m.documentos) == 1
    assert z.name == f"{CNPJ}_2026-10_complementar_1.zip"
    assert [n for n in _nomes(z) if n.startswith("xml/")] == [f"xml/{b.chave}.xml"]


def _so_resumo(con, eid, horas):
    repo.registrar_so_resumo(con, eid, NotaListada(chave="9" * 44, emitente_cnpj="5", emitente_nome="X",
                                                   emissao=date(2026, 10, 5), valor=Decimal(1)))
    quando = (AGORA - timedelta(hours=horas)).isoformat()
    con.execute("UPDATE documento SET capturado_em=? WHERE chave=?", (quando, "9" * 44))
    con.commit()


def test_conferir_retem_so_resumo_antigo(con):
    eid = _empresa(con)
    _so_resumo(con, eid, 72)
    retem = [a for a in conferencia.conferir(con, eid, "2026-10", AGORA) if a.nivel == "retem"]
    assert len(retem) == 1 and "sem XML" in retem[0].texto


def test_conferir_nao_retem_so_resumo_recente(con):
    eid = _empresa(con)
    _so_resumo(con, eid, 24)
    assert [a for a in conferencia.conferir(con, eid, "2026-10", AGORA) if a.nivel == "retem"] == []


def test_conferir_retem_sem_chave_e_erro_recente(con):
    eid = _empresa(con, chave=False)
    repo.registrar_captura(con, eid, "webposto", (AGORA - timedelta(days=1)).isoformat(), "erro", 0, 0, "x")
    textos = [a.texto for a in conferencia.conferir(con, eid, "2026-10", AGORA) if a.nivel == "retem"]
    assert any("chave do webPosto" in t for t in textos)
    assert any("erro" in t.lower() for t in textos)


def test_conferir_avisos(con, tmp_path):
    eid = _empresa(con)
    _gravar(con, eid, tmp_path, "nfe_combustivel.xml",
            EntradaWebposto(chave="26261011111111000191550010000123451000012345", cte_numero="998"))
    avisos = [a.texto for a in conferencia.conferir(con, eid, "2026-10", AGORA) if a.nivel == "aviso"]
    assert any("998" in t for t in avisos)
    assert conferencia.AVISO_NFSE in avisos
