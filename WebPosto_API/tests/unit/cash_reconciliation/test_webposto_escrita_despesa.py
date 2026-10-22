"""Testes unitários offline para o adaptador de escrita de despesas no webPosto (EXPENSE-03).

Valida integralmente e offline:
1. Conta a pagar válida (POST /TITULOS_PAGAR -> 201 + ID)
2. Movimento de débito válido (POST /MOVIMENTOS_CONTA -> 201 + confirmação via GET)
3. Baixa de título válida (PATCH /TITULOS_PAGAR/PAGAR -> 204 + confirmação via GET)
4. Empresa errada (99999 / não autorizada)
5. Empresa indefinida (None / EMPRESA_INDEFINIDA)
6. Conta financeira errada (sem conta ou <= 0)
7. Fornecedor inexistente (para conta a pagar)
8. Plano de contas inválido
9. Aprovação ausente (não aprovado)
10. Aprovação de versão antiga (versão defasada)
11. Hash diferente (dados alterados pós-aprovação)
12. Operação diferente da aprovada
13. Registro já existente no ERP / idempotência
14. Timeout em POST (sem retry automático, RESULTADO_DESCONHECIDO)
15. Timeout em PATCH (sem retry automático, RESULTADO_DESCONHECIDO)
16. Retry bloqueado
17. Duas tentativas simultâneas (concorrência)
18. HTTP 201 sem identificador
19. HTTP 204 sem payload (confirmação via GET)
20. Consulta posterior inconclusiva
21. Anexo preparado corretamente (Base64)
22. Falha de anexo sem repetir lançamento
23. Flags em zero bloqueiam escrita
24. Ausência de chamadas externas
25. Nenhuma operação financeira real
26. Compatibilidade com EXPENSE-01 e EXPENSE-02
27. Regressão dos testes de cash_reconciliation
"""

from __future__ import annotations

import base64
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
import pytest
import httpx

from src.modules.cash_reconciliation.domain.comprovante import (
    DadosComprovante,
    ItemFilaDespesa,
    OperacaoFinanceira,
    StatusDespesa,
)
from src.modules.cash_reconciliation.domain.models import Unidade
from src.modules.cash_reconciliation.adapters.webposto_escrita_despesa import (
    BarreiraDespesaErro,
    WebPostoErro,
    IdempotenciaDespesas,
    calcular_chave_idempotencia,
    executar_lancamento_despesa,
    montar_payload_anexo,
    montar_payload_baixa_titulo,
    montar_payload_movimento_conta,
    montar_payload_titulo_pagar,
    validar_aprovacao_para_escrita,
    validar_unidade_autorizada,
    verificar_travas_despesa,
)


@pytest.fixture
def unidade_doze() -> Unidade:
    return Unidade(
        empresa_codigo=74014,
        nome="POSTO DOZE FILIAL II",
        chave_env="WEBPOSTO_KEY_DOZE",
        destinos=(),
        apelido="Doze",
    )


@pytest.fixture
def unidade_casa_caiada() -> Unidade:
    return Unidade(
        empresa_codigo=5555,
        nome="AP CASA CAIADA",
        chave_env="WEBPOSTO_KEY_CC",
        destinos=(),
        apelido="Casa Caiada",
    )


@pytest.fixture
def env_liberado(tmp_path: Path) -> Path:
    env_file = tmp_path / ".env.liberado"
    env_file.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n", encoding="utf-8")
    return env_file


@pytest.fixture
def env_travado(tmp_path: Path) -> Path:
    env_file = tmp_path / ".env.travado"
    env_file.write_text("WEBPOSTO_WRITES=0\nLOGOS_ERP_ESCRITA=0\n", encoding="utf-8")
    return env_file


def _item_aprovado_base(
    operacao: OperacaoFinanceira,
    empresa_cod: int = 74014,
    empresa_nome: str = "POSTO DOZE FILIAL II",
    valor: Decimal = Decimal("350.00"),
    versao: int = 1,
) -> ItemFilaDespesa:
    item = ItemFilaDespesa(
        id="item-teste-01",
        numero_documento="NF-1001",
        versao=versao,
        criado_em="2026-10-18T10:00:00",
        unidade_codigo=empresa_cod,
        unidade_nome=empresa_nome,
        unidade_apelido="Doze" if empresa_cod == 74014 else "Casa Caiada",
        operacao_financeira=operacao.value,
        comprovante=DadosComprovante(
            valor=valor,
            data=date(2026, 10, 18),
            favorecido="Fornecedor Teste",
            descricao="Manutenção de pista",
        ),
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        sugestao_fornecedor_codigo=9012,
        sugestao_fornecedor_nome="Oficina ABC",
        conta_financeira_codigo=86248,
        debito_casado_fitid="FIT-12345",
        titulo_casado_codigo=55001,
        status=StatusDespesa.APROVADO.value,
        aprovado_por="diretor:123",
        aprovado_em="2026-10-18T10:05:00",
        aprovado_versao=versao,
        aprovado_operacao=operacao.value,
    )
    item.hash_conteudo = item.calcular_hash_conteudo()
    item.aprovado_hash = item.hash_conteudo
    return item


# ---------------------------------------------------------------------------
# 1. Conta a pagar válida (Operação A: POST /TITULOS_PAGAR -> 201 + ID)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_01_conta_a_pagar_valida(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        if request.url.path == "/INTEGRACAO/V1/TITULOS_PAGAR" and request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            assert body["empresaCodigo"] == 74014
            assert body["fornecedorCodigo"] == 9012
            assert body["valorParcela"] == 350.0
            assert body["numeroTitulo"] == "NF-1001"
            return httpx.Response(
                201, json={"tituloPagarCodigo": 88019, "mensagem": "Criado com sucesso"}
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        diretorio_auditoria=tmp_path / "auditoria",
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is True
    assert res["id_erp"] == 88019
    assert item.status == StatusDespesa.LANCADO_ERP.value
    assert item.resultado_erp_id == "88019"
    assert len(chamadas) == 1


# ---------------------------------------------------------------------------
# 2. Movimento de débito válido (Operação B: POST /MOVIMENTOS_CONTA -> 201 + confirmação)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_02_movimento_debito_valido(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.DESPESA_JA_PAGA)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/INTEGRACAO/V1/MOVIMENTOS_CONTA" and request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            assert body["contaMovimentoTipo"] == "DEBITO"
            assert body["conta"] == 86248
            assert body["valor"] == 350.0
            return httpx.Response(201, text="")  # OpenAPI: corpo pode ser vazio
        elif request.url.path == "/INTEGRACAO/V1/MOVIMENTOS_CONTA" and request.method == "GET":
            # Retorno de confirmação pós-escrita
            return httpx.Response(
                200,
                json={
                    "resultados": [
                        {
                            "movimentoContaCodigo": 99401,
                            "valor": 350.0,
                            "contaMovimentoTipo": "DEBITO",
                            "dataMovimento": "2026-10-18",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        diretorio_auditoria=tmp_path / "auditoria",
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is True
    assert res["id_erp"] == 99401
    assert item.status == StatusDespesa.LANCADO_ERP.value


# ---------------------------------------------------------------------------
# 3. Baixa de título válida (Operação C: PATCH /TITULOS_PAGAR/PAGAR -> 204 + confirmação)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_03_baixa_titulo_valida(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.TITULO_EXISTENTE)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/INTEGRACAO/V1/TITULOS_PAGAR/PAGAR" and request.method == "PATCH":
            body = json.loads(request.content.decode("utf-8"))
            assert body["tituloPagarCodigo"] == [55001]
            assert body["contaCodigo"] == 86248
            return httpx.Response(204)  # 204 No Content
        elif request.url.path == "/INTEGRACAO/V1/TITULOS_PAGAR" and request.method == "GET":
            # Confirmação pós-baixa
            return httpx.Response(
                200,
                json={
                    "resultados": [
                        {
                            "tituloPagarCodigo": 55001,
                            "situacao": "QUITADO",
                            "dataPagamento": "2026-10-18",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        diretorio_auditoria=tmp_path / "auditoria",
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is True
    assert res["id_erp"] == 55001
    assert item.status == StatusDespesa.LANCADO_ERP.value


# ---------------------------------------------------------------------------
# 4. Empresa errada (Não autorizada, Posto Real 5558/7 excluído ou códigos espúrios 12607/12705)
# ---------------------------------------------------------------------------
def test_04_empresa_errada_bloqueio():
    # Bloqueio explícito do Posto Real (5558 / codWeb 7) - fora do escopo do Expense Hunter
    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        validar_unidade_autorizada(5558)

    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        validar_unidade_autorizada(7)

    # Mesmo que seja passado via unidades_cadastradas externas, 5558 continua bloqueado
    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        validar_unidade_autorizada(5558, unidades_cadastradas={5558: {"nome": "POSTO REAL"}})

    # Códigos espúrios investigados continuam bloqueados
    with pytest.raises(
        BarreiraDespesaErro,
        match="Empresa 12607 não existe no webPosto. O código oficial de Casa Caiada é 5555.",
    ):
        validar_unidade_autorizada(12607)

    with pytest.raises(BarreiraDespesaErro, match="Empresa 12705 não existe no webPosto."):
        validar_unidade_autorizada(12705)

    with pytest.raises(BarreiraDespesaErro, match="não é autorizada"):
        validar_unidade_autorizada(99999)

    # Unidades autorizadas do escopo são aceitas
    assert validar_unidade_autorizada(74014) == 74014  # Doze
    assert validar_unidade_autorizada(11495) == 11495  # VIP
    assert validar_unidade_autorizada(5555) == 5555  # Casa Caiada oficial
    assert validar_unidade_autorizada(118508) == 118508  # Conv 24h


@pytest.mark.asyncio
async def test_04b_bloqueio_direto_escrita_posto_real(tmp_path: Path, env_liberado: Path):
    """Garante que chamadas diretas ao executor ou montadores com Posto Real (5558) são bloqueadas."""
    item = _item_aprovado_base(
        OperacaoFinanceira.NOVA_CONTA_A_PAGAR, empresa_cod=5558, empresa_nome="POSTO REAL"
    )
    unidade_real = Unidade(
        empresa_codigo=5558,
        nome="POSTO REAL",
        chave_env="WEBPOSTO_KEY_REAL",
        destinos=(),
        apelido="Real",
    )

    # Validação de aprovação recusa
    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        validar_aprovacao_para_escrita(item)

    # Montadores de payload recusam
    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        montar_payload_titulo_pagar(item, unidade_real)

    item_deb = _item_aprovado_base(
        OperacaoFinanceira.DESPESA_JA_PAGA, empresa_cod=5558, empresa_nome="POSTO REAL"
    )
    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        montar_payload_movimento_conta(item_deb, unidade_real)

    item_baixa = _item_aprovado_base(
        OperacaoFinanceira.TITULO_EXISTENTE, empresa_cod=5558, empresa_nome="POSTO REAL"
    )
    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        montar_payload_baixa_titulo(item_baixa, unidade_real)

    # Chamada direta ao executor bloqueia antes de qualquer requisição HTTP
    chamadas_feitas = []

    def mock_transport(request: httpx.Request) -> httpx.Response:
        chamadas_feitas.append(request)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))

    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        await executar_lancamento_despesa(
            item,
            unidade_real,
            caminho_env=env_liberado,
            banco_idempotencia=tmp_path / "idemp.sqlite3",
            client=client,
        )

    assert len(chamadas_feitas) == 0, "Nenhuma chamada externa pode ser efetuada para o Posto Real"


# ---------------------------------------------------------------------------
# 5. Empresa indefinida
# ---------------------------------------------------------------------------
def test_05_empresa_indefinida():
    with pytest.raises(BarreiraDespesaErro, match="Empresa não identificada"):
        validar_unidade_autorizada(None)

    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    item.unidade_codigo = None
    with pytest.raises(BarreiraDespesaErro, match="Empresa não identificada"):
        validar_aprovacao_para_escrita(item)


# ---------------------------------------------------------------------------
# 6. Conta financeira errada
# ---------------------------------------------------------------------------
def test_06_conta_financeira_errada():
    item = _item_aprovado_base(OperacaoFinanceira.DESPESA_JA_PAGA)
    item.conta_financeira_codigo = None
    item.hash_conteudo = item.calcular_hash_conteudo()
    item.aprovado_hash = item.hash_conteudo

    with pytest.raises(BarreiraDespesaErro, match="Conta financeira de débito não identificada"):
        validar_aprovacao_para_escrita(item)


# ---------------------------------------------------------------------------
# 7. Fornecedor inexistente
# ---------------------------------------------------------------------------
def test_07_fornecedor_inexistente():
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    item.sugestao_fornecedor_codigo = None
    item.hash_conteudo = item.calcular_hash_conteudo()
    item.aprovado_hash = item.hash_conteudo

    with pytest.raises(BarreiraDespesaErro, match="Fornecedor obrigatório não cadastrado"):
        validar_aprovacao_para_escrita(item)


# ---------------------------------------------------------------------------
# 8. Plano de contas inválido
# ---------------------------------------------------------------------------
def test_08_plano_de_contas_invalido():
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    item.sugestao_plano_codigo = None
    item.hash_conteudo = item.calcular_hash_conteudo()
    item.aprovado_hash = item.hash_conteudo

    with pytest.raises(BarreiraDespesaErro, match="Plano de contas obrigatório não informado"):
        validar_aprovacao_para_escrita(item)


# ---------------------------------------------------------------------------
# 9. Aprovação ausente
# ---------------------------------------------------------------------------
def test_09_aprovacao_ausente():
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    item.status = StatusDespesa.AGUARDANDO_APROVACAO.value

    with pytest.raises(BarreiraDespesaErro, match="Lançamento recusado: status atual é"):
        validar_aprovacao_para_escrita(item)


# ---------------------------------------------------------------------------
# 10. Aprovação de versão antiga
# ---------------------------------------------------------------------------
def test_10_aprovacao_versao_antiga():
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR, versao=2)
    item.aprovado_versao = 1  # Versão desatualizada

    with pytest.raises(
        BarreiraDespesaErro, match="Aprovação invalidada: o conteúdo da proposta foi alterado"
    ):
        validar_aprovacao_para_escrita(item)

    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value
    assert item.aprovado_por is None


# ---------------------------------------------------------------------------
# 11. Hash diferente (Alteração pós-aprovação)
# ---------------------------------------------------------------------------
def test_11_hash_diferente():
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    # Altera valor sem re-aprovação
    item.comprovante.valor = Decimal("999.00")

    with pytest.raises(
        BarreiraDespesaErro, match="Aprovação invalidada: o conteúdo da proposta foi alterado"
    ):
        validar_aprovacao_para_escrita(item)

    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value


# ---------------------------------------------------------------------------
# 12. Operação diferente da aprovada
# ---------------------------------------------------------------------------
def test_12_operacao_diferente_da_aprovada():
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    item.operacao_financeira = OperacaoFinanceira.DESPESA_JA_PAGA.value

    with pytest.raises(
        BarreiraDespesaErro, match="Operação financeira pretendida .* difere da operação aprovada"
    ):
        validar_aprovacao_para_escrita(item)

    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value


# ---------------------------------------------------------------------------
# 13. Registro já existente no ERP (Idempotência confirmada)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_registro_ja_existente_idempotencia(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path
):
    banco = tmp_path / "idemp.sqlite3"
    idemp = IdempotenciaDespesas(banco)

    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    chave = calcular_chave_idempotencia(item)

    # Simula operação previamente confirmada
    idemp.iniciar_operacao(chave, item)
    idemp.confirmar_operacao(chave, "ERP-7711", "Previamente lançado")

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))

    with pytest.raises(BarreiraDespesaErro, match="Operação já em andamento ou concluída"):
        await executar_lancamento_despesa(
            item,
            unidade_doze,
            caminho_env=env_liberado,
            banco_idempotencia=banco,
            client=client,
            anexar_arquivo=False,
        )


# ---------------------------------------------------------------------------
# 14. Timeout em POST (Sem retry automático, RESULTADO_DESCONHECIDO)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_timeout_em_post(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Timeout simulado durante POST")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(
        WebPostoErro, match="Timeout na comunicação com webPosto.*Reenvio automático proibido"
    ):
        await executar_lancamento_despesa(
            item,
            unidade_doze,
            caminho_env=env_liberado,
            banco_idempotencia=tmp_path / "idemp.sqlite3",
            client=client,
            anexar_arquivo=False,
        )

    assert item.status == StatusDespesa.RESULTADO_DESCONHECIDO.value


# ---------------------------------------------------------------------------
# 15. Timeout em PATCH (Sem retry automático, RESULTADO_DESCONHECIDO)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_15_timeout_em_patch(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.TITULO_EXISTENTE)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Timeout simulado durante PATCH")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(
        WebPostoErro, match="Timeout na comunicação com webPosto.*Reenvio automático proibido"
    ):
        await executar_lancamento_despesa(
            item,
            unidade_doze,
            caminho_env=env_liberado,
            banco_idempotencia=tmp_path / "idemp.sqlite3",
            client=client,
            anexar_arquivo=False,
        )

    assert item.status == StatusDespesa.RESULTADO_DESCONHECIDO.value


# ---------------------------------------------------------------------------
# 16. Retry bloqueado após timeout
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_retry_bloqueado_apos_timeout(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    banco = tmp_path / "idemp.sqlite3"
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    client_timeout = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: (_ for _ in ()).throw(httpx.TimeoutException("Timeout"))
        )
    )

    with pytest.raises(WebPostoErro):
        await executar_lancamento_despesa(
            item,
            unidade_doze,
            caminho_env=env_liberado,
            banco_idempotencia=banco,
            client=client_timeout,
            anexar_arquivo=False,
        )

    # Tentar novamente com cliente normal deve ser BLOQUEADO pelo estado RESULTADO_DESCONHECIDO / pendência
    client_normal = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(201, json={"id": 1}))
    )

    # Como o item agora está em RESULTADO_DESCONHECIDO, validar_aprovacao_para_escrita já bloqueia
    with pytest.raises(
        BarreiraDespesaErro, match="Lançamento recusado: status atual é 'resultado_desconhecido'"
    ):
        await executar_lancamento_despesa(
            item,
            unidade_doze,
            caminho_env=env_liberado,
            banco_idempotencia=banco,
            client=client_normal,
            anexar_arquivo=False,
        )


# ---------------------------------------------------------------------------
# 17. Duas tentativas simultâneas (Concorrência atômica)
# ---------------------------------------------------------------------------
def test_17_duas_tentativas_simultaneas(tmp_path: Path):
    banco = tmp_path / "idemp.sqlite3"
    idemp = IdempotenciaDespesas(banco)
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    chave = calcular_chave_idempotencia(item)

    # Primeira reserva: sucesso
    idemp.iniciar_operacao(chave, item)

    # Segunda reserva simultânea da mesma chave: BLOQUEADA
    with pytest.raises(BarreiraDespesaErro, match="Operação já em andamento ou concluída"):
        idemp.iniciar_operacao(chave, item)


# ---------------------------------------------------------------------------
# 18. HTTP 201 sem identificador
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_18_http_201_sem_identificador(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    # Retorna 201 mas corpo sem ID
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(201, json={"mensagem": "OK"}))
    )

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is False
    assert res["resultado_desconhecido"] is True
    assert item.status == StatusDespesa.RESULTADO_DESCONHECIDO.value


# ---------------------------------------------------------------------------
# 19. HTTP 204 sem payload (Confirmação via GET)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_19_http_204_confirmacao_get(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.TITULO_EXISTENTE)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            return httpx.Response(204)
        elif request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "resultados": [
                        {
                            "tituloPagarCodigo": 55001,
                            "situacao": "PAGO",
                            "dataPagamento": "2026-10-18",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is True
    assert item.status == StatusDespesa.LANCADO_ERP.value


# ---------------------------------------------------------------------------
# 20. Consulta posterior inconclusiva
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_20_consulta_posterior_inconclusiva(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.DESPESA_JA_PAGA)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, text="")
        elif request.method == "GET":
            # Retorna lista vazia: movimento não localizado
            return httpx.Response(200, json={"resultados": []})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is False
    assert res["resultado_desconhecido"] is True
    assert item.status == StatusDespesa.RESULTADO_DESCONHECIDO.value


# ---------------------------------------------------------------------------
# 21. Anexo preparado corretamente (Base64)
# ---------------------------------------------------------------------------
def test_21_anexo_preparado_corretamente():
    conteudo_teste = b"PDF_DO_COMPROVANTE_12345"
    payload = montar_payload_anexo("comprovante.pdf", conteudo_teste)

    assert payload["nome"] == "comprovante.pdf"
    b64_esperado = base64.b64encode(conteudo_teste).decode("ascii")
    assert payload["conteudo"] == b64_esperado


# ---------------------------------------------------------------------------
# 22. Falha de anexo sem repetir lançamento
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_22_falha_de_anexo_sem_repetir_lancamento(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    # Cria arquivo físico de comprovante
    arquivo_comp = tmp_path / "recibo.pdf"
    arquivo_comp.write_bytes(b"CONTEUDO_PDF_RECIBO")
    item.arquivo_comprovante = str(arquivo_comp)

    def handler(request: httpx.Request) -> httpx.Response:
        if "/TITULOS_PAGAR" in request.url.path:
            return httpx.Response(201, json={"tituloPagarCodigo": 77112})
        elif "/ARQUIVOS" in request.url.path:
            # Simula falha 500 no anexo
            return httpx.Response(500, text="Erro interno ao gravar arquivo")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        diretorio_auditoria=tmp_path / "auditoria",
        client=client,
        anexar_arquivo=True,
    )

    # Lançamento financeiro permanece bem-sucedido
    assert res["sucesso"] is True
    assert res["id_erp"] == 77112
    assert item.status == StatusDespesa.LANCADO_ERP.value
    # Anexo reporta falha sem reverter a operação financeira
    assert res["anexo"]["sucesso"] is False


# ---------------------------------------------------------------------------
# 23. Flags em zero bloqueiam escrita
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_23_flags_em_zero_bloqueiam_escrita(unidade_doze: Unidade, env_travado: Path):
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    with pytest.raises(BarreiraDespesaErro, match="Lançamento bloqueado pelas travas de escrita"):
        await executar_lancamento_despesa(
            item,
            unidade_doze,
            caminho_env=env_travado,
            client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
        )


# ---------------------------------------------------------------------------
# 24. Ausência de chamadas externas (Isolamento total com falha em request real)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_24_ausencia_chamadas_externas(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    chamadas_reais = []

    def mock_real_transport(*args, **kwargs):
        chamadas_reais.append((args, kwargs))
        raise RuntimeError("Chamada externa real de rede proibida!")

    monkeypatch.setattr("httpx.AsyncHTTPTransport.handle_async_request", mock_real_transport)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", mock_real_transport)

    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    # Executa usando MockTransport controlado localmente
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(201, json={"tituloPagarCodigo": 123})
        )
    )
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_secreta")

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        client=client,
        anexar_arquivo=False,
    )
    assert res["sucesso"] is True
    assert len(chamadas_reais) == 0  # 0 chamadas de rede reais efetuadas


# ---------------------------------------------------------------------------
# 25. Nenhuma operação financeira real (Travas globais intactas no .env do repositório)
# ---------------------------------------------------------------------------
def test_25_nenhuma_operacao_financeira_real_travas_repositorio():
    # Verifica o .env físico real do projeto
    travas_ok, motivo = verificar_travas_despesa()
    # No repositório, WEBPOSTO_WRITES=0 e LOGOS_ERP_ESCRITA=0, logo travas_ok DEVE ser False!
    assert travas_ok is False
    assert "Trava" in motivo and "!= 1" in motivo


# ---------------------------------------------------------------------------
# 26. Compatibilidade com EXPENSE-01 e EXPENSE-02
# ---------------------------------------------------------------------------
def test_26_compatibilidade_itens_expense_01_02():
    item = _item_aprovado_base(OperacaoFinanceira.NOVA_CONTA_A_PAGAR)
    assert item.operacao_financeira == OperacaoFinanceira.NOVA_CONTA_A_PAGAR.value
    assert item.versao == 1
    assert item.aprovado_versao == 1
    assert item.aprovado_hash == item.calcular_hash_conteudo()
    assert item.status == StatusDespesa.APROVADO.value

    # Validação aceita o item aprovado pelo fluxo EXPENSE-02
    validar_aprovacao_para_escrita(item)


# ---------------------------------------------------------------------------
# 27. Casa Caiada oficial é 5555
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_27_casa_caiada_empresa_oficial_5555(
    tmp_path: Path, unidade_casa_caiada: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_CC", "chave_cc")
    item = _item_aprovado_base(
        OperacaoFinanceira.NOVA_CONTA_A_PAGAR,
        empresa_cod=5555,
        empresa_nome="AP CASA CAIADA",
    )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(201, json={"tituloPagarCodigo": 44102})
        )
    )

    res = await executar_lancamento_despesa(
        item,
        unidade_casa_caiada,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is True
    assert res["id_erp"] == 44102
    assert item.status == StatusDespesa.LANCADO_ERP.value
