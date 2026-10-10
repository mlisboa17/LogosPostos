from unittest.mock import patch

from src.infrastructure.security.gerar_hash import main
from src.infrastructure.security.passwords import verify_password


def test_gerar_hash_solicita_confirmacao_e_imprime_somente_hash(capsys):
    with patch(
        "src.infrastructure.security.gerar_hash.getpass.getpass",
        side_effect=["synthetic-test-password", "synthetic-test-password"],
    ):
        assert main() == 0

    output = capsys.readouterr()
    encoded = output.out.strip()
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("synthetic-test-password", encoded)
    assert "synthetic-test-password" not in output.out


def test_gerar_hash_recusa_senhas_vazias_ou_divergentes():
    with patch(
        "src.infrastructure.security.gerar_hash.getpass.getpass",
        side_effect=["first", "second"],
    ):
        try:
            main()
        except SystemExit as exc:
            assert str(exc) == "As senhas estão vazias ou não conferem."
        else:
            raise AssertionError("A confirmação divergente deveria ser recusada.")
