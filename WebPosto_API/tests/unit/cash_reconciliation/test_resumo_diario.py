from datetime import date
from decimal import Decimal

from src.modules.cash_reconciliation.application import resumo_diario
from src.modules.cash_reconciliation.domain.execucao import ResultadoDiario
from src.modules.cash_reconciliation.domain.fechamento import (
    Alerta,
    MovimentoDespesa,
    Severidade,
    ValeFuncionario,
)
from src.modules.cash_reconciliation.domain.models import Unidade
from src.modules.cash_reconciliation.domain.recebimentos import ResultadoRecebimentos

from .test_http import resultado_sintetico

DIA = date(2026, 10, 9)
EMPRESA = 321


def _registro(*, alertas=None, despesas=(), vales=(), adquirentes=()):
    base = resultado_sintetico()
    auditoria = base.caixas[0].model_copy(
        update={
            "caixa": base.caixas[0].caixa.model_copy(update={"data": DIA}),
            "alertas": tuple(alertas if alertas is not None else base.caixas[0].alertas),
            "despesas": tuple(despesas),
            "vales": tuple(vales),
        }
    )
    fechamento = base.model_copy(update={"inicio": DIA, "fim": DIA, "caixas": (auditoria,)})
    return ResultadoDiario(
        empresa_codigo=EMPRESA,
        dia=DIA,
        fechamento=fechamento,
        recebimentos=ResultadoRecebimentos(
            empresa_codigo=EMPRESA,
            dia=DIA,
            adquirentes=tuple(adquirentes),
        ),
        proveniencia=base.proveniencia,
        versoes_regras=("FECHAMENTO_V4",),
    )


def _unidade(apelido=None):
    return Unidade(
        empresa_codigo=EMPRESA,
        nome="Unidade sintética",
        apelido=apelido,
        chave_env="NAO_USADA",
        destinos=(),
    )


def test_unidade_sem_problema_exibe_check_e_nome_de_fallback(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade()})
    registro = _registro(alertas=())

    mensagem = resumo_diario.gerar_mensagem_curta(
        DIA,
        [registro],
        [EMPRESA],
        set(),
        {EMPRESA: 0},
        {EMPRESA: 0},
    )[0]

    assert "✓ Unidade sintética: sem falta" in mensagem
    assert "LOGOS — Caixas de 09/10/2026 (robô ok)" in mensagem
    assert "Pendências: 0 abertas · 0 vencidas" in mensagem


def test_falta_em_caixa_nao_consolidado_mostra_aviso(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade("Doze")})
    alertas = (
        Alerta(
            codigo="FALTA_SEM_DESCONTO",
            severidade=Severidade.VERMELHO,
            mensagem="falta sintética",
            valor=Decimal("2263.18"),
            referencia=10,
        ),
        Alerta(
            codigo="NAO_CONSOLIDADO",
            severidade=Severidade.LARANJA,
            mensagem="não consolidado",
            referencia=10,
        ),
    )
    registro = _registro(alertas=alertas)
    mensagem = resumo_diario.gerar_mensagem_curta(
        DIA,
        [registro],
        [EMPRESA],
        set(),
        {EMPRESA: 0},
        {EMPRESA: 0},
    )[0]

    assert "⚠ Doze: 1 falta, R$ 2.263,18 sem desconto; (caixa ainda não consolidado)" in mensagem


def test_despesa_sem_plano_e_limite_de_oito(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade("Doze")})
    despesas = tuple(
        MovimentoDespesa(
            codigo=codigo,
            caixa_codigo=10,
            tipo="D",
            valor=Decimal(str(10 - codigo)),
            plano_conta_codigo=None,
            descricao="Lanche equipe",
        )
        for codigo in range(1, 10)
    )
    registro = _registro(alertas=(), despesas=despesas)

    mensagem = resumo_diario.gerar_mensagem_curta(
        DIA,
        [registro],
        [EMPRESA],
        set(),
        {EMPRESA: 0},
        {EMPRESA: 0},
    )[0]

    assert "SEM PLANO ⚠" in mensagem
    assert "+1 outras (R$ 1,00)" in mensagem
    assert mensagem.count("\n- R$ ") == 8


def test_descricoes_nao_expoem_nome_pessoal(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade("Doze")})
    descricoes = (
        "extra de Ronaldo",
        "gasolina Henrique",
        "pagamento do Uber Daniel",
        "NSU 1234567 CPF 123.456.789-00 conta 45678",
    )
    despesas = tuple(
        MovimentoDespesa(
            codigo=codigo,
            caixa_codigo=10,
            tipo="D",
            valor=Decimal("40"),
            plano_conta_codigo="7",
            descricao=descricao,
        )
        for codigo, descricao in enumerate(descricoes, start=1)
    )

    mensagem = resumo_diario.gerar_mensagem_curta(
        DIA,
        [_registro(alertas=(), despesas=despesas)],
        [EMPRESA],
        set(),
        {EMPRESA: 0},
        {EMPRESA: 0},
    )[0]

    assert "extra [omitido]" in mensagem
    assert "gasolina [omitido]" in mensagem
    assert "Uber [omitido]" in mensagem
    assert all(nome not in mensagem for nome in ("Ronaldo", "Henrique", "Daniel"))
    assert all(
        identificador not in mensagem for identificador in ("1234567", "123.456.789-00", "45678")
    )


def test_vale_mostra_codigo_sem_nome_de_funcionario(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade("VIP")})
    vale = ValeFuncionario.model_construct(
        codigo=1,
        empresa_codigo=EMPRESA,
        caixa_codigo=10,
        funcionario_codigo=302036,
        origem="D",
        valor=Decimal("300"),
        nome_funcionario="Nome Privado Sintético",
    )
    mensagem = resumo_diario.gerar_mensagem_curta(
        DIA,
        [_registro(alertas=(), vales=(vale,))],
        [EMPRESA],
        set(),
        {EMPRESA: 0},
        {EMPRESA: 0},
    )[0]

    assert "func. 302036 R$ 300,00 (falta de caixa)" in mensagem
    assert "Nome Privado Sintético" not in mensagem


def test_mensagem_longa_e_dividida_abaixo_do_limite(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade("Doze")})
    vales = tuple(
        ValeFuncionario(
            codigo=codigo,
            empresa_codigo=EMPRESA,
            caixa_codigo=10,
            funcionario_codigo=codigo,
            origem="V",
            valor=Decimal("1"),
        )
        for codigo in range(1, 150)
    )
    mensagens = resumo_diario.gerar_mensagem_curta(
        DIA,
        [_registro(alertas=(), vales=vales)],
        [EMPRESA],
        set(),
        {EMPRESA: 0},
        {EMPRESA: 0},
    )

    assert len(mensagens) > 1
    assert all(len(mensagem) <= 4000 for mensagem in mensagens)
