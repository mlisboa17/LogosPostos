"""Escopo empresarial permitido para novos processos LOGOS."""

from collections.abc import Iterable

NEW_PROCESS_COMPANY_CODES = frozenset({5555, 11495, 118508, 74014})
# A confirmacao legada do cadastro nao resolve as divergencias da F0-ID.
PENDING_IDENTITY_COMPANY_CODES = frozenset({118508, 74014})


def is_new_process_company(empresa_codigo: int) -> bool:
    return (
        isinstance(empresa_codigo, int)
        and not isinstance(empresa_codigo, bool)
        and empresa_codigo in NEW_PROCESS_COMPANY_CODES
    )


def validate_new_process_company_codes(empresa_codigos: Iterable[int]) -> None:
    fora_do_escopo = sorted(
        {codigo for codigo in empresa_codigos if not is_new_process_company(codigo)},
        key=str,
    )
    if fora_do_escopo:
        codigos = ", ".join(str(codigo) for codigo in fora_do_escopo)
        raise ValueError(f"Empresas fora do escopo de novos processos: {codigos}.")


def is_company_identity_validated(empresa_codigo: int, *, cadastro_confirmado: bool) -> bool:
    return cadastro_confirmado and empresa_codigo not in PENDING_IDENTITY_COMPANY_CODES


def validate_sensitive_company_restrictions(empresa_codigo: int) -> None:
    """Aplica bloqueios empresariais, sem conceder autorizacao para a operacao."""
    validate_new_process_company_codes([empresa_codigo])
    if empresa_codigo in PENDING_IDENTITY_COMPANY_CODES:
        raise ValueError(
            f"Empresa {empresa_codigo} com identidade pendente para operação sensível."
        )
