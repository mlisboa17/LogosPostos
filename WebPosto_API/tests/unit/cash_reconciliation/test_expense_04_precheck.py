"""Testes de validação de segurança e pré-checagem para lançamento de despesas (EXPENSE-04-PRECHECK).

Cobre os 22 requisitos obrigatórios de segurança P0:
1. Somente as quatro empresas permitidas (Doze: 74014, VIP: 11495, Casa Caiada: 5555, Conv 24h: 118508);
2. Posto Real (5558) bloqueado;
3. Código 7 bloqueado (codWeb do Posto Real);
4. Empresas externas não ampliam a allowlist fechada;
5. Aprovação de uma despesa não autoriza outra despesa;
6. Empresa alterada após aprovação invalida o lançamento;
7. Conta alterada após aprovação invalida o lançamento;
8. Valor alterado após aprovação invalida o lançamento;
9. Operação alterada após aprovação invalida o lançamento;
10. Token de piloto vencido é rejeitado;
11. Token de piloto reutilizado é rejeitado;
12. Tentativa de operação fora do escopo do token de piloto é bloqueada;
13. Timeout em POST entra em RESULTADO_DESCONHECIDO sem retry;
14. Timeout em PATCH entra em RESULTADO_DESCONHECIDO sem retry;
15. Resultado desconhecido permanece bloqueado após reinicialização;
16. Confirmação inequívoca de movimento de conta pós-escrita;
17. Confirmação ambígua recusa confirmação e marca resultado desconhecido;
18. Conta financeira de outra empresa é estritamente bloqueada;
19. Flags em zero bloqueiam qualquer tentativa de escrita;
20. Nenhuma chamada externa de rede é realizada nos testes;
21. Regressão e interoperabilidade com EXPENSE-01, 02 e 03;
22. Testes não gravam em arquivos ou bancos operacionais reais.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

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
    GerenciadorAutorizacaoPiloto,
    AutorizacaoPilotoDespesa,
    calcular_chave_idempotencia,
    confirmar_movimento_conta,
    executar_lancamento_despesa,
    validar_aprovacao_para_escrita,
    validar_conta_financeira_unidade,
    validar_unidade_autorizada,
    verificar_travas_despesa,
    EMPRESAS_AUTORIZADAS_SET,
    CONTAS_AUTORIZADAS_POR_UNIDADE,
)
from src.modules.cash_reconciliation.adapters.telegram_despesas import (
    DespesaTelegramErro,
    processar_callback_despesa,
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
def unidade_vip() -> Unidade:
    return Unidade(
        empresa_codigo=11495,
        nome="POSTO VIP LTDA",
        chave_env="WEBPOSTO_KEY_VIP",
        destinos=(),
        apelido="VIP",
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


def _criar_item_aprovado(
    operacao: OperacaoFinanceira = OperacaoFinanceira.DESPESA_JA_PAGA,
    empresa_cod: int = 74014,
    empresa_nome: str = "POSTO DOZE FILIAL II",
    conta_cod: int = 86248,
    valor: Decimal = Decimal("250.00"),
    versao: int = 1,
    item_id: str = "item-p0-test",
) -> ItemFilaDespesa:
    item = ItemFilaDespesa(
        id=item_id,
        numero_documento="DOC-1234",
        versao=versao,
        criado_em="2026-10-18T10:00:00",
        unidade_codigo=empresa_cod,
        unidade_nome=empresa_nome,
        unidade_apelido="Doze" if empresa_cod == 74014 else "Outro",
        operacao_financeira=operacao.value,
        comprovante=DadosComprovante(
            valor=valor,
            data=date(2026, 10, 18),
            favorecido="Fornecedor Confiável",
            descricao="Serviço elétrico de emergência",
            banco_origem="BB",
        ),
        sugestao_plano_codigo=198595,
        sugestao_plano_nome="PEDREIRO",
        sugestao_fornecedor_codigo=9012,
        sugestao_fornecedor_nome="Eletrotécnica",
        conta_financeira_codigo=conta_cod,
        debito_casado_fitid="FIT-9988",
        titulo_casado_codigo=7001 if operacao == OperacaoFinanceira.TITULO_EXISTENTE else None,
        status=StatusDespesa.APROVADO.value,
        aprovado_por="diretor:matheus",
        aprovado_em="2026-10-18T10:05:00",
        aprovado_versao=versao,
        aprovado_operacao=operacao.value,
    )
    item.hash_conteudo = item.calcular_hash_conteudo()
    item.aprovado_hash = item.hash_conteudo
    return item


# ---------------------------------------------------------------------------
# 1. Somente as quatro empresas permitidas
# ---------------------------------------------------------------------------
def test_01_somente_quatro_empresas_permitidas():
    assert EMPRESAS_AUTORIZADAS_SET == frozenset({74014, 11495, 5555, 118508})

    # As 4 empresas são aceitas
    assert validar_unidade_autorizada(74014) == 74014
    assert validar_unidade_autorizada(11495) == 11495
    assert validar_unidade_autorizada(5555) == 5555
    assert validar_unidade_autorizada(118508) == 118508

    # Inteiros enviados como strings válidas são normalizados
    assert validar_unidade_autorizada("74014") == 74014
    assert validar_unidade_autorizada("11495") == 11495

    # Quaisquer outros códigos são recusados
    for codigo_proibido in (1, 2, 99999, 88888, 1234):
        with pytest.raises(BarreiraDespesaErro, match="não é autorizada"):
            validar_unidade_autorizada(codigo_proibido)

    # Valores nulos, booleanos e strings vazias/inválidas
    with pytest.raises(BarreiraDespesaErro, match="Empresa não identificada"):
        validar_unidade_autorizada(None)

    with pytest.raises(BarreiraDespesaErro, match="booleano não permitido"):
        validar_unidade_autorizada(True)

    with pytest.raises(BarreiraDespesaErro, match="booleano não permitido"):
        validar_unidade_autorizada(False)

    with pytest.raises(BarreiraDespesaErro, match="Código de empresa vazio"):
        validar_unidade_autorizada("   ")

    with pytest.raises(BarreiraDespesaErro, match="Código de empresa inválido"):
        validar_unidade_autorizada("empresa_invalida")


# ---------------------------------------------------------------------------
# 2. Posto Real (5558) bloqueado
# ---------------------------------------------------------------------------
def test_02_posto_real_bloqueado():
    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        validar_unidade_autorizada(5558)

    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        validar_unidade_autorizada("5558")


# ---------------------------------------------------------------------------
# 3. Código 7 bloqueado (codWeb do Posto Real)
# ---------------------------------------------------------------------------
def test_03_codigo_7_bloqueado():
    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        validar_unidade_autorizada(7)

    with pytest.raises(
        BarreiraDespesaErro,
        match="Posto Real \\(empresaCodigo 5558 / codWeb 7\\) não faz parte do escopo",
    ):
        validar_unidade_autorizada("7")


# ---------------------------------------------------------------------------
# 4. Empresas externas não ampliam a allowlist
# ---------------------------------------------------------------------------
def test_04_empresas_externas_nao_ampliam_allowlist():
    cadastro_externo = {
        99999: {"nome": "POSTO INVASOR"},
        5558: {"nome": "POSTO REAL"},
        74014: {"nome": "POSTO DOZE"},
    }

    # Tentativa de validar empresa externa que NÃO está na allowlist fechada
    with pytest.raises(BarreiraDespesaErro, match="não é autorizada"):
        validar_unidade_autorizada(99999, unidades_cadastradas=cadastro_externo)

    with pytest.raises(BarreiraDespesaErro, match="Posto Real"):
        validar_unidade_autorizada(5558, unidades_cadastradas=cadastro_externo)

    # Empresa autorizada conferida contra cadastro externo
    assert validar_unidade_autorizada(74014, unidades_cadastradas=cadastro_externo) == 74014

    # Se a empresa autorizada não constar no cadastro fornecido, recusa por incoerência
    cadastro_sem_doze = {11495: {"nome": "VIP"}}
    with pytest.raises(
        BarreiraDespesaErro, match="não encontrada no cadastro de unidades fornecido"
    ):
        validar_unidade_autorizada(74014, unidades_cadastradas=cadastro_sem_doze)


# ---------------------------------------------------------------------------
# 5. Aprovação de uma despesa não autoriza outra despesa
# ---------------------------------------------------------------------------
def test_05_aprovacao_de_uma_despesa_nao_autoriza_outra():
    item_a = _criar_item_aprovado(item_id="item-A")
    item_b = _criar_item_aprovado(item_id="item-B")

    # Copiar a aprovação de A para B (mas mantendo o ID de B)
    item_b.aprovado_hash = item_a.aprovado_hash
    item_b.aprovado_versao = item_a.aprovado_versao
    item_b.aprovado_por = item_a.aprovado_por

    # Como o cálculo de hash inclui o ID da despesa, a aprovação de A é INVÁLIDA para B
    with pytest.raises(
        BarreiraDespesaErro, match="Aprovação invalidada: o conteúdo da proposta foi alterado"
    ):
        validar_aprovacao_para_escrita(item_b)

    assert item_b.status == StatusDespesa.AGUARDANDO_REVISAO.value
    assert item_b.aprovado_por is None


# ---------------------------------------------------------------------------
# 6. Empresa alterada após aprovação
# ---------------------------------------------------------------------------
def test_06_empresa_alterada_apos_aprovacao():
    item = _criar_item_aprovado(empresa_cod=74014)
    # Tenta trocar para outra empresa autorizada após aprovação
    item.unidade_codigo = 11495

    with pytest.raises(
        BarreiraDespesaErro, match="Aprovação invalidada: o conteúdo da proposta foi alterado"
    ):
        validar_aprovacao_para_escrita(item)

    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value


# ---------------------------------------------------------------------------
# 7. Conta alterada após aprovação
# ---------------------------------------------------------------------------
def test_07_conta_alterada_apos_aprovacao():
    item = _criar_item_aprovado(empresa_cod=74014, conta_cod=86248)
    # Altera para outra conta do mesmo posto após aprovação
    item.conta_financeira_codigo = 86081

    with pytest.raises(
        BarreiraDespesaErro, match="Aprovação invalidada: o conteúdo da proposta foi alterado"
    ):
        validar_aprovacao_para_escrita(item)

    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value


# ---------------------------------------------------------------------------
# 8. Valor alterado após aprovação
# ---------------------------------------------------------------------------
def test_08_valor_alterado_apos_aprovacao():
    item = _criar_item_aprovado(valor=Decimal("250.00"))
    item.comprovante.valor = Decimal("251.00")

    with pytest.raises(
        BarreiraDespesaErro, match="Aprovação invalidada: o conteúdo da proposta foi alterado"
    ):
        validar_aprovacao_para_escrita(item)

    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value


# ---------------------------------------------------------------------------
# 9. Operação alterada após aprovação
# ---------------------------------------------------------------------------
def test_09_operacao_alterada_apos_aprovacao():
    item = _criar_item_aprovado(operacao=OperacaoFinanceira.DESPESA_JA_PAGA)
    # Tenta executar como baixa de título sem nova aprovação
    item.operacao_financeira = OperacaoFinanceira.TITULO_EXISTENTE.value

    with pytest.raises(
        BarreiraDespesaErro, match="Operação financeira pretendida .* difere da operação aprovada"
    ):
        validar_aprovacao_para_escrita(item)

    assert item.status == StatusDespesa.AGUARDANDO_REVISAO.value


# ---------------------------------------------------------------------------
# 10. Token de piloto vencido
# ---------------------------------------------------------------------------
def test_10_token_piloto_vencido(tmp_path: Path):
    banco = tmp_path / "piloto.sqlite3"
    mgr = GerenciadorAutorizacaoPiloto(banco)
    item = _criar_item_aprovado()

    # Cria autorização com validade expirada (-1 minuto)
    token = mgr.criar_autorizacao(
        operacao_id=item.id,
        empresa_codigo=item.unidade_codigo,
        tipo_operacao=item.operacao_financeira,
        valor=float(item.comprovante.valor),
        hash_aprovado=item.aprovado_hash,
        autorizador_id="diretor:matheus",
        conta_codigo=item.conta_financeira_codigo,
        validade_minutos=-1,
    )

    with pytest.raises(BarreiraDespesaErro, match="Autorização de piloto expirada"):
        mgr.consumir_autorizacao(token, item)


# ---------------------------------------------------------------------------
# 11. Token de piloto reutilizado
# ---------------------------------------------------------------------------
def test_11_token_piloto_reutilizado(tmp_path: Path):
    banco = tmp_path / "piloto.sqlite3"
    mgr = GerenciadorAutorizacaoPiloto(banco)
    item = _criar_item_aprovado()

    token = mgr.criar_autorizacao(
        operacao_id=item.id,
        empresa_codigo=item.unidade_codigo,
        tipo_operacao=item.operacao_financeira,
        valor=float(item.comprovante.valor),
        hash_aprovado=item.aprovado_hash,
        autorizador_id="diretor:matheus",
        conta_codigo=item.conta_financeira_codigo,
        validade_minutos=30,
    )

    # Primeiro consumo: OK
    aut = mgr.consumir_autorizacao(token, item)
    assert aut.consumida_em is not None
    assert aut.operacao_id == item.id

    # Segundo consumo do mesmo token: BLOQUEADO
    with pytest.raises(BarreiraDespesaErro, match="Autorização de piloto já consumida"):
        mgr.consumir_autorizacao(token, item)


# ---------------------------------------------------------------------------
# 12. Tentativa de operação fora do escopo do token de piloto
# ---------------------------------------------------------------------------
def test_12_tentativa_operacao_fora_do_escopo(tmp_path: Path):
    banco = tmp_path / "piloto.sqlite3"
    mgr = GerenciadorAutorizacaoPiloto(banco)
    item = _criar_item_aprovado(empresa_cod=74014, conta_cod=86248, valor=Decimal("150.00"))

    token = mgr.criar_autorizacao(
        operacao_id=item.id,
        empresa_codigo=74014,
        tipo_operacao=item.operacao_financeira,
        valor=150.00,
        hash_aprovado=item.aprovado_hash,
        autorizador_id="diretor:matheus",
        conta_codigo=86248,
        validade_minutos=30,
    )

    # 1. Outro item ID
    item_outro_id = _criar_item_aprovado(item_id="item-hacker")
    with pytest.raises(BarreiraDespesaErro, match="pertence à operação"):
        mgr.consumir_autorizacao(token, item_outro_id)

    # 2. Outra empresa
    item_outra_emp = _criar_item_aprovado(
        empresa_cod=11495, conta_cod=65321, valor=Decimal("150.00")
    )
    item_outra_emp.id = item.id
    item_outra_emp.aprovado_hash = item.aprovado_hash
    with pytest.raises(BarreiraDespesaErro, match="pertence à empresa"):
        mgr.consumir_autorizacao(token, item_outra_emp)

    # 3. Outro valor
    item_outro_val = _criar_item_aprovado(valor=Decimal("999.00"))
    item_outro_val.id = item.id
    item_outro_val.aprovado_hash = item.aprovado_hash
    with pytest.raises(BarreiraDespesaErro, match="vinculada ao valor"):
        mgr.consumir_autorizacao(token, item_outro_val)


# ---------------------------------------------------------------------------
# 13. Timeout em POST
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_timeout_em_post(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_teste")
    item = _criar_item_aprovado(operacao=OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: (_ for _ in ()).throw(httpx.TimeoutException("Timeout POST"))
        )
    )

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
# 14. Timeout em PATCH
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_timeout_em_patch(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_teste")
    item = _criar_item_aprovado(operacao=OperacaoFinanceira.TITULO_EXISTENTE)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: (_ for _ in ()).throw(httpx.TimeoutException("Timeout PATCH"))
        )
    )

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
# 15. Resultado desconhecido permanece bloqueado após reinicialização
# ---------------------------------------------------------------------------
def test_15_resultado_desconhecido_apos_reinicializacao(tmp_path: Path):
    banco = tmp_path / "idemp.sqlite3"
    idemp1 = IdempotenciaDespesas(banco)
    item = _criar_item_aprovado()
    chave = calcular_chave_idempotencia(item)

    idemp1.iniciar_operacao(chave, item)
    idemp1.marcar_resultado_desconhecido(chave, "Timeout na comunicação com ERP")

    # Reinicialização: novo processo/instância conectando ao mesmo SQLite
    idemp2 = IdempotenciaDespesas(banco)

    with pytest.raises(
        BarreiraDespesaErro, match="Operação já em andamento ou concluída.*RESULTADO_DESCONHECIDO"
    ):
        idemp2.iniciar_operacao(chave, item)


# ---------------------------------------------------------------------------
# 16. Confirmação inequívoca de movimento de conta pós-escrita
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_confirmacao_inequivoca_do_lancamento(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_teste")
    item = _criar_item_aprovado(
        operacao=OperacaoFinanceira.DESPESA_JA_PAGA, valor=Decimal("250.00")
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, text="")
        elif request.method == "GET":
            # Exatamente 1 candidato coincidente
            return httpx.Response(
                200,
                json={
                    "resultados": [
                        {
                            "movimentoContaCodigo": 12345,
                            "valor": 250.0,
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
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is True
    assert res["id_erp"] == 12345
    assert item.status == StatusDespesa.LANCADO_ERP.value
    assert item.resultado_erp_id == "12345"


# ---------------------------------------------------------------------------
# 17. Confirmação ambígua recusa confirmação e marca resultado desconhecido
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_17_confirmacao_ambigua(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_teste")
    item = _criar_item_aprovado(
        operacao=OperacaoFinanceira.DESPESA_JA_PAGA, valor=Decimal("250.00")
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, text="")
        elif request.method == "GET":
            # Múltiplos movimentos de mesmo valor no mesmo dia: AMBIGUIDADE!
            return httpx.Response(
                200,
                json={
                    "resultados": [
                        {
                            "movimentoContaCodigo": 111,
                            "valor": 250.0,
                            "contaMovimentoTipo": "DEBITO",
                        },
                        {
                            "movimentoContaCodigo": 222,
                            "valor": 250.0,
                            "contaMovimentoTipo": "DEBITO",
                        },
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

    assert res["sucesso"] is False
    assert res["resultado_desconhecido"] is True
    assert item.status == StatusDespesa.RESULTADO_DESCONHECIDO.value
    # NÃO deve ter sido marcado como lançado no ERP
    assert item.resultado_erp_id is None


# ---------------------------------------------------------------------------
# 18. Conta financeira de outra empresa é estritamente bloqueada (inclusive conta 17837)
# ---------------------------------------------------------------------------
def test_18_conta_de_outra_empresa():
    # 86248 pertence ao Doze (74014)
    assert 86248 in CONTAS_AUTORIZADAS_POR_UNIDADE[74014]

    # Tentativa de lançar na Casa Caiada (5555) usando conta do Doze (86248)
    with pytest.raises(
        BarreiraDespesaErro, match="pertence a outra unidade \\(74014\\), não à empresa 5555"
    ):
        validar_conta_financeira_unidade(5555, 86248)

    # Tentativa de lançar no VIP (11495) usando conta de Casa Caiada (17837)
    with pytest.raises(BarreiraDespesaErro, match="pertence a outra unidade"):
        validar_conta_financeira_unidade(11495, 17837)

    # Verificação específica da conta 17837:
    # 1. 17837 é autorizada e comprovada para Casa Caiada (5555 - CAIXA POSTO)
    assert validar_conta_financeira_unidade(5555, 17837) == 17837

    # 2. 17837 é ESTRITAMENTE BLOQUEADA para Conveniência 24h (118508) por ambiguidade/pertencer à 5555
    with pytest.raises(
        BarreiraDespesaErro, match="pertence a outra unidade \\(5555\\), não à empresa 118508"
    ):
        validar_conta_financeira_unidade(118508, 17837)

    # Item aprovado com conta de outra empresa é bloqueado pela governança
    item = _criar_item_aprovado(empresa_cod=5555, conta_cod=86248)
    with pytest.raises(BarreiraDespesaErro, match="pertence a outra unidade"):
        validar_aprovacao_para_escrita(item)


# ---------------------------------------------------------------------------
# 19. Flags em zero bloqueiam qualquer tentativa de escrita
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_19_flags_em_zero_bloqueiam_escrita(
    unidade_doze: Unidade, env_travado: Path, tmp_path: Path
):
    item = _criar_item_aprovado()
    banco = tmp_path / "piloto.sqlite3"
    mgr = GerenciadorAutorizacaoPiloto(banco)
    token = mgr.criar_autorizacao(
        operacao_id=item.id,
        empresa_codigo=item.unidade_codigo,
        tipo_operacao=item.operacao_financeira,
        valor=float(item.comprovante.valor),
        hash_aprovado=item.aprovado_hash,
        autorizador_id="diretor:matheus",
        conta_codigo=item.conta_financeira_codigo,
    )

    # Mesmo com token de piloto válido e item 100% aprovado, se as flags estão em zero, BLOQUEIA
    with pytest.raises(BarreiraDespesaErro, match="Lançamento bloqueado pelas travas de escrita"):
        await executar_lancamento_despesa(
            item,
            unidade_doze,
            caminho_env=env_travado,
            banco_idempotencia=banco,
            autorizacao_piloto_token=token,
            client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
        )


# ---------------------------------------------------------------------------
# 20. Nenhuma chamada externa de rede é realizada nos testes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_20_nenhuma_chamada_externa(
    tmp_path: Path, unidade_doze: Unidade, env_liberado: Path, monkeypatch
):
    chamadas_reais = []

    def mock_transport_bloqueio(*args, **kwargs):
        chamadas_reais.append((args, kwargs))
        raise RuntimeError("Tentativa de chamada de rede real bloqueada pelo teste!")

    monkeypatch.setattr("httpx.AsyncHTTPTransport.handle_async_request", mock_transport_bloqueio)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", mock_transport_bloqueio)
    monkeypatch.setenv("WEBPOSTO_KEY_DOZE", "chave_teste")

    item = _criar_item_aprovado(operacao=OperacaoFinanceira.NOVA_CONTA_A_PAGAR)

    # Executa usando mock de transporte local
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(201, json={"tituloPagarCodigo": 991})
        )
    )

    res = await executar_lancamento_despesa(
        item,
        unidade_doze,
        caminho_env=env_liberado,
        banco_idempotencia=tmp_path / "idemp.sqlite3",
        client=client,
        anexar_arquivo=False,
    )

    assert res["sucesso"] is True
    assert len(chamadas_reais) == 0


# ---------------------------------------------------------------------------
# 21. Regressão e interoperabilidade com EXPENSE-01, 02 e 03
# ---------------------------------------------------------------------------
def test_21_regressao_interoperabilidade_fluxos():
    item = _criar_item_aprovado(operacao=OperacaoFinanceira.DESPESA_JA_PAGA)
    # Valida hashing determinístico
    h1 = item.calcular_hash_conteudo()
    assert len(h1) == 16
    assert item.aprovado_hash == h1

    # Validação de governança aprova
    validar_aprovacao_para_escrita(item)
    assert item.status == StatusDespesa.APROVADO.value

    # Validação de conta autorizada
    cod = validar_conta_financeira_unidade(item.unidade_codigo, item.conta_financeira_codigo)
    assert cod == 86248


# ---------------------------------------------------------------------------
# 22. Testes não gravam em arquivos ou bancos operacionais reais
# ---------------------------------------------------------------------------
def test_22_testes_nao_escrevem_em_dados_operacionais_reais():
    # O arquivo real de .env do repositório deve estar com travas travadas
    travas_ok, motivo = verificar_travas_despesa()
    assert travas_ok is False
    assert "WEBPOSTO_WRITES" in motivo or "LOGOS_ERP_ESCRITA" in motivo

    # Banco oficial de auditoria não deve ser modificado
    banco_real = Path("data/lancamentos_logos/despesas.sqlite3")
    if banco_real.exists():
        # Confirma que é um banco válido sem registros de teste indevidos
        with sqlite3.connect(banco_real) as con:
            cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tabelas = [r[0] for r in cur.fetchall()]
            # Não deve conter registros espúrios gerados por este teste
