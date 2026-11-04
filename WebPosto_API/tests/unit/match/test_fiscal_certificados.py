from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from apps.match import banco, credenciais
from apps.match.fiscal import certificados as cert
from apps.match.fiscal import repositorio as repo

SENHA = "senha-do-teste"
CNPJ = "52308604000284"


def gerar_pfx(cn: str, *, dias: int = 200, senha: str = SENHA) -> bytes:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    agora = datetime.now(timezone.utc)
    c = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(agora - timedelta(days=200))
         .not_valid_after(agora + timedelta(days=dias)).sign(chave, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(
        b"t", chave, c, None, serialization.BestAvailableEncryption(senha.encode()))


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_MATCH_DIR", str(tmp_path / "dados"))
    c = banco.conectar(tmp_path / "c.db")
    yield c
    c.close()


def _empresa(con, cnpj=CNPJ):
    return repo.salvar_empresa(con, cnpj, "POSTO DOZE", "doze", "Abreu e Lima", "PE", None)


def test_valida_e_guarda_cifrado(con, tmp_path):
    eid = _empresa(con)
    pfx = gerar_pfx(f"POSTO DOZE COMERCIO:{CNPJ}")
    info = cert.salvar(con, eid, pfx, SENHA)
    assert (info.cnpj, info.titular, info.da_matriz) == (CNPJ, "POSTO DOZE COMERCIO", False)
    assert 198 <= info.dias_restantes <= 200
    guardado = next((tmp_path / "dados" / "certificados").glob("*.bin")).read_bytes()
    assert pfx not in guardado and guardado != pfx  # nunca em claro no disco
    assert credenciais.ler(f"empresa/{eid}/a1") == SENHA
    pfx_lido, senha_lida = cert.carregar(con, eid)
    assert (pfx_lido, senha_lida) == (pfx, SENHA)
    linha = con.execute("SELECT * FROM certificado WHERE empresa_id=?", (eid,)).fetchone()
    assert SENHA not in str(dict(linha)) and linha["ativo"] == 1


def test_senha_errada(con):
    eid = _empresa(con)
    with pytest.raises(cert.CertificadoInvalido) as exc:
        cert.salvar(con, eid, gerar_pfx(f"X:{CNPJ}"), "outra")
    assert str(exc.value) == "Senha errada ou arquivo que não é certificado A1 (.pfx/.p12)."


def test_cnpj_de_outra_empresa_e_recusado(con):
    eid = _empresa(con)
    with pytest.raises(cert.CertificadoInvalido) as exc:
        cert.salvar(con, eid, gerar_pfx("CASA CAIADA:04284939000186"), SENHA)
    assert "04.284.939/0001-86" in str(exc.value) and "52.308.604/0002-84" in str(exc.value)


def test_certificado_da_matriz_vale_para_filial(con):
    eid = _empresa(con)
    info = cert.salvar(con, eid, gerar_pfx("POSTO DOZE:52308604000101"), SENHA)
    assert info.da_matriz is True


def test_vencido_e_ecpf_recusados(con):
    eid = _empresa(con)
    with pytest.raises(cert.CertificadoInvalido, match="venceu"):
        cert.salvar(con, eid, gerar_pfx(f"X:{CNPJ}", dias=-1), SENHA)
    with pytest.raises(cert.CertificadoInvalido, match="e-CPF"):
        cert.salvar(con, eid, gerar_pfx("ELIANE:12345678909"), SENHA)


def test_troca_mantem_historico(con):
    eid = _empresa(con)
    cert.salvar(con, eid, gerar_pfx(f"A:{CNPJ}", dias=10), SENHA)
    cert.salvar(con, eid, gerar_pfx(f"A:{CNPJ}", dias=300), SENHA)
    linhas = con.execute("SELECT ativo FROM certificado WHERE empresa_id=? ORDER BY id", (eid,)).fetchall()
    assert [r[0] for r in linhas] == [0, 1]
    assert cert.situacao(con, eid).dias_restantes >= 299


def test_sem_certificado(con):
    assert cert.situacao(con, _empresa(con)) is None
