from apps.match import credenciais


def test_salvar_ler_apagar(keyring_falso):
    credenciais.salvar("1/premmia/senha", "abc")
    assert credenciais.ler("1/premmia/senha") == "abc"
    assert credenciais.tem("1/premmia/senha")
    credenciais.apagar("1/premmia/senha")
    assert credenciais.ler("1/premmia/senha") is None
    credenciais.apagar("1/premmia/senha")  # idempotente


def test_salvar_vazio_nao_apaga(keyring_falso):
    credenciais.salvar("1/pagbank/token", "tok")
    credenciais.salvar("1/pagbank/token", "")
    assert credenciais.ler("1/pagbank/token") == "tok"


def test_salvar_so_espacos_nao_grava(keyring_falso):
    credenciais.salvar("1/premmia/usuario", "u")
    credenciais.salvar("1/premmia/usuario", "   ")
    credenciais.salvar("2/premmia/senha", " \t ")
    assert credenciais.ler("1/premmia/usuario") == "u"
    assert credenciais.ler("2/premmia/senha") is None
