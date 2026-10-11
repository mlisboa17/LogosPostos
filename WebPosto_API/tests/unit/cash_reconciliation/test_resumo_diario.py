from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from src.jobs import noturno
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


def test_resumo_v32_quantidade_valor_e_forma():
    from src.modules.cash_reconciliation.application.conciliar_cartoes import conciliar
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente
    from .test_cartoes import T, DIA as DIA_CARTOES
    from .test_pendencias import criar_diario

    t = T("12", "10:00", nsu="CUPOM001").model_copy(update={
        "adquirente": "PREMMIA", "bandeira": "Desconto",
    })
    resultado = conciliar(74014, "PREMMIA", DIA_CARTOES, [t], [], [], set())
    diario = criar_diario(DIA_CARTOES, 74014).model_copy(update={
        "recebimentos": ResultadoRecebimentos(
            empresa_codigo=74014, dia=DIA_CARTOES,
            adquirentes=(RecebimentoAdquirente.de_resultado(resultado),),
        ),
    })
    mensagem = "\n".join(resumo_diario.gerar_mensagem_curta(
        DIA_CARTOES, [diario], [74014], set(), {74014: 1},
    ))
    assert "0 conferidos · R$ 0,00 · 1 divergências · R$ 12,00" in mensagem
    assert "A maior: 1 · R$ 12,00" in mensagem
    assert "Desconto: portal 1 · R$ 12,00 / webPosto 0 · R$ 0,00 · diferença R$ 12,00" in mensagem


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

    assert "<b>✓ UNIDADE SINTÉTICA</b>" in mensagem
    assert "<b>LOGOS — Caixas de 09/10/2026</b>" in mensagem
    assert "Sem falta" in mensagem
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
        {EMPRESA: {3: "Operador Sintético"}},
    )[0]

    assert "<b>⚠ DOZE</b>" in mensagem
    assert (
        "Falta sem desconto: R$ 2.263,18 — Operador Sintético (caixa ainda não consolidado)"
        in mensagem
    )


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
    assert mensagem.count("\n• R$ ") == 8


def test_descricoes_nao_expoem_nome_pessoal(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade("Doze")})
    descricoes = (
        "extra de Ronaldo <b>",
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
    assert "&lt;b&gt;" in mensagem
    assert "<b> <b>" not in mensagem


def test_vale_mostra_nome_de_funcionario(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade("VIP")})
    vale = ValeFuncionario.model_construct(
        codigo=1,
        empresa_codigo=EMPRESA,
        caixa_codigo=10,
        funcionario_codigo=302036,
        origem="D",
        valor=Decimal("300"),
    )
    mensagem = resumo_diario.gerar_mensagem_curta(
        DIA,
        [_registro(alertas=(), vales=(vale,))],
        [EMPRESA],
        set(),
        {EMPRESA: 0},
        {EMPRESA: 0},
        {EMPRESA: {302036: "Funcionário Sintético"}},
    )[0]

    assert "Funcionário Sintético R$ 300,00 (falta de caixa)" in mensagem
    assert "302036" not in mensagem


def test_mensagem_longa_e_dividida_abaixo_do_limite(monkeypatch):
    monkeypatch.setattr(resumo_diario, "carregar_unidades", lambda: {EMPRESA: _unidade("Doze")})
    mensagens = resumo_diario.gerar_mensagem_curta(
        DIA,
        [_registro(alertas=())],
        [EMPRESA] * 100,
        set(),
        {EMPRESA: 0},
        {EMPRESA: 0},
    )

    assert len(mensagens) == 100
    assert all(len(mensagem) <= 4000 for mensagem in mensagens)
    assert mensagens[0].startswith("<b>LOGOS — Caixas de 09/10/2026</b>")
    assert "<b>✓ DOZE</b>" in mensagens[0]
    assert all("LOGOS — Caixas" not in mensagem for mensagem in mensagens[1:])


def test_filiais_em_alerta_antes_das_sem_alerta(monkeypatch):
    segunda = 654
    monkeypatch.setattr(
        resumo_diario,
        "carregar_unidades",
        lambda: {EMPRESA: _unidade("Normal"), segunda: _unidade("Alerta")},
    )
    mensagem = resumo_diario.gerar_mensagem_curta(
        DIA,
        [_registro(alertas=())],
        [EMPRESA, segunda],
        set(),
        {EMPRESA: 0, segunda: 0},
        {EMPRESA: 0, segunda: 0},
    )[0]

    assert mensagem.index("<b>⚠ ALERTA</b>") < mensagem.index("<b>✓ NORMAL</b>")


def test_planilha_com_quatro_abas_valores_numericos_e_nome(tmp_path):
    despesa = MovimentoDespesa(
        codigo=1,
        caixa_codigo=10,
        tipo="D",
        valor=Decimal("12.50"),
        plano_conta_codigo="7",
        descricao="Despesa sintética",
        plano_conta_nome="Plano sintético",
    )
    vale = ValeFuncionario(
        codigo=1,
        empresa_codigo=EMPRESA,
        caixa_codigo=10,
        funcionario_codigo=3,
        origem="D",
        valor=Decimal("5.25"),
    )
    registro = _registro(alertas=(), despesas=(despesa,), vales=(vale,))
    dados = {
        "unidades": {EMPRESA: _unidade("Filial Sintética")},
        "resultados": [registro],
        "nomes_funcionarios": {EMPRESA: {3: "Funcionário Planilha Sintético"}},
        "abertas": {EMPRESA: 2},
        "vencidas": {EMPRESA: 1},
    }
    caminho = noturno._criar_planilha_telegram(DIA, dados, tmp_path)
    workbook = load_workbook(caminho, data_only=True)

    assert workbook.sheetnames == ["Resumo", "Caixas", "Despesas", "Vales"]
    assert isinstance(workbook["Resumo"]["F2"].value, (int, float))
    assert "R$" in workbook["Resumo"]["F2"].number_format
    assert isinstance(workbook["Despesas"]["C2"].value, (int, float))
    assert workbook["Caixas"]["C2"].value == "Funcionário Planilha Sintético"
    assert workbook["Vales"]["C2"].value == "Funcionário Planilha Sintético"
