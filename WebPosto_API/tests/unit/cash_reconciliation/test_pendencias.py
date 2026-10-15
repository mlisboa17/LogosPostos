import hashlib
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.security.jwt_utils import create_access_token
from src.modules.cash_reconciliation.adapters import pendencias as repositorio
from src.modules.cash_reconciliation.application.gerar_pendencias import (
    pendencias_de_reincidencia,
    pendencias_do_dia,
)
from src.modules.cash_reconciliation.domain.execucao import ResultadoDiario
from src.modules.cash_reconciliation.domain.fechamento import (
    Alerta,
    AuditoriaCaixa,
    Caixa,
    ResultadoAuditoria,
    Severidade,
)
from src.modules.cash_reconciliation.domain.models import Proveniencia, Unidade
from src.modules.cash_reconciliation.domain.pendencias import NovaPendencia
from src.modules.cash_reconciliation.domain.recebimentos import ResultadoRecebimentos
from src.modules.cash_reconciliation.domain.tempo import FUSO
from src.modules.cash_reconciliation.interfaces import http

EMPRESA = 321
DIA = date(2026, 10, 6)


def criar_diario(dia: date, unidade: int = EMPRESA) -> ResultadoDiario:
    caixa = Caixa(
        codigo=100 + dia.day,
        empresa_codigo=unidade,
        data=dia,
        turno="Sintético",
        pdv_codigo=1,
        funcionario_codigo=7,
        abertura=datetime.combine(dia, datetime.min.time()),
        fechamento=datetime.combine(dia, datetime.min.time()),
        fechado=True,
        consolidado=True,
        bloqueado=False,
    )
    alerta = Alerta(
        codigo="QUEBRA",
        severidade=Severidade.VERMELHO,
        mensagem="Dinheiro: falta sintética",
        valor=Decimal("-25.00"),
        referencia=caixa.codigo,
    )
    proveniencia = Proveniencia(
        execucao_id=f"sintetica-{dia.isoformat()}",
        executado_em=datetime.combine(dia, datetime.min.time()),
        versao_regra="FECHAMENTO_V3",
        fonte_sangrias="sintética",
        extratos=(),
    )
    fechamento = ResultadoAuditoria(
        empresa_codigo=unidade,
        inicio=dia,
        fim=dia,
        caixas=(AuditoriaCaixa(caixa=caixa, modalidades=(), sangrias=(), alertas=(alerta,)),),
        proveniencia=proveniencia,
    )
    return ResultadoDiario(
        empresa_codigo=unidade,
        dia=dia,
        fechamento=fechamento,
        recebimentos=ResultadoRecebimentos(empresa_codigo=unidade, dia=dia, adquirentes=()),
        proveniencia=proveniencia,
        versoes_regras=("FECHAMENTO_V3", "CARTOES_V1"),
    )


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", tmp_path / "pendencias.sqlite3")
    monkeypatch.setattr(
        http,
        "carregar_unidades",
        lambda: {
            EMPRESA: Unidade(
                empresa_codigo=EMPRESA,
                nome="Unidade sintética",
                chave_env="CHAVE_TESTE",
                destinos=(),
            ),
            654: Unidade(
                empresa_codigo=654,
                nome="Outra unidade sintética",
                chave_env="OUTRA_CHAVE_TESTE",
                destinos=(),
            ),
        },
    )
    app = FastAPI()
    app.include_router(http.router)
    return TestClient(app)


def autenticar(
    client: TestClient, perfil: str, unidade: int | None = None, usuario: str | None = None
):
    client.cookies.clear()
    client.cookies.set(
        "access_token",
        create_access_token(
            usuario or f"{perfil}@example.invalid",
            extra={"role": perfil, "company_id": unidade, "token_type": "access"},
        ),
    )


def test_alertas_criam_pendencias_com_chave_idempotente_e_historico_append_only(tmp_path):
    banco = tmp_path / "data" / "pendencias.sqlite3"
    candidatas = pendencias_do_dia(criar_diario(DIA))

    assert len(candidatas) == 1
    assert candidatas[0].tipo == "fechamento_quebra"
    assert repositorio.registrar(candidatas, banco=banco) == 1
    assert repositorio.registrar(candidatas, banco=banco) == 0

    itens, total = repositorio.listar(unidade=EMPRESA, banco=banco)
    assert total == 1
    assert itens[0].status == "aberta"
    assert itens[0].historico[0].acao == "criada"
    assert itens[0].historico[0].status_novo == "aberta"

    with sqlite3.connect(banco) as conexao:
        with pytest.raises(sqlite3.IntegrityError, match="imutavel"):
            conexao.execute("UPDATE historico_pendencias SET usuario = 'alterado'")
        with pytest.raises(sqlite3.IntegrityError, match="imutavel"):
            conexao.execute("DELETE FROM historico_pendencias")


@pytest.mark.parametrize("menor", [True, False])
def test_cartoes_v3_pendencia_idempotente_e_nome(tmp_path, menor):
    from src.modules.cash_reconciliation.domain.cartoes import AlertaCartao, CartaoErp
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    cartao = CartaoErp(
        codigo=1,
        empresa_codigo=EMPRESA,
        venda_codigo=10,
        valor=Decimal("150"),
        momento=datetime(2026, 10, 6, 10),
        administradora="PAGSEGURO",
        nsu="1234",
        nsu_tef=None,
        autorizacao=None,
        frentista=7,
        nome_frentista="Funcionário Sintético",
        caixa_codigo=106,
    )
    alerta = AlertaCartao(
        codigo="CARTAO_VALOR_A_MENOR" if menor else "CARTAO_VALOR_A_MAIOR",
        severidade="vermelho" if menor else "laranja",
        mensagem="Lançado R$ 150, recebido R$ 100 — faltam R$ 50 — Funcionário Sintético (7)",
        valor=Decimal("50"),
        cartoes=(cartao,),
    )
    diario = diario_com_alertas(alertas_laranja())
    diario = diario.model_copy(
        update={
            "recebimentos": ResultadoRecebimentos(
                empresa_codigo=EMPRESA,
                dia=DIA,
                adquirentes=(
                    RecebimentoAdquirente(adquirente="PAGBANK", situacao="ok", alertas=(alerta,)),
                ),
            )
        }
    )
    entradas = pendencias_do_dia(diario)
    recebimento = next(
        p
        for p in entradas
        if p.tipo == ("recebimento_valor_a_menor" if menor else "caixa_alertas_laranja")
    )
    assert recebimento.severidade == ("vermelho" if menor else "laranja")
    if menor:
        assert recebimento.valor == Decimal("50")
    else:
        grupos = [p for p in entradas if p.tipo == "caixa_alertas_laranja"]
        assert len(grupos) == 1
        assert recebimento.referencia == "caixa:106:laranja"
        detalhes = json.loads(recebimento.mensagem)["alertas"]
        assert len(detalhes) == len(alertas_laranja()) + 1
        assert detalhes[-1]["codigo"] == "CARTAO_VALOR_A_MAIOR"
    assert "Funcionário Sintético (7)" in recebimento.mensagem
    banco = tmp_path / "pendencias.sqlite3"
    assert repositorio.registrar(entradas, banco=banco) == len(entradas)
    assert repositorio.registrar(entradas, banco=banco) == 0


def test_telegram_v3_diferencas_e_evento_desconhecido():
    from src.modules.cash_reconciliation.application import resumo_diario
    from src.modules.cash_reconciliation.application.conciliar_cartoes import conciliar
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente
    from .test_cartoes import C, T, DIA as DIA_CARTOES

    resultado = conciliar(
        74014, "PAGBANK", DIA_CARTOES,
        [
            T("100", "10:00", nsu="1234"),
            T("20", "12:00", nsu="9999").model_copy(update={"situacao": "cancelada"}),
            T("30", "13:00", nsu="8888").model_copy(update={"situacao": "tipo_evento=X"}),
        ],
        [C(1, "150", "10:00", nsu="1234")], [], set(),
    )
    diario = criar_diario(DIA_CARTOES, unidade=74014).model_copy(update={
        "recebimentos": ResultadoRecebimentos(
            empresa_codigo=74014, dia=DIA_CARTOES,
            adquirentes=(RecebimentoAdquirente.de_resultado(resultado),),
        ),
    })
    mensagem = "\n".join(resumo_diario.gerar_mensagem_curta(
        DIA_CARTOES, [diario], [74014], set(), {74014: 0},
    ))
    assert "PagBank: portal R$ 100,00 · webPosto R$ 150,00 · ❌ diferença R$ -50,00" in mensagem
    assert "A menor: R$ 50,00 · 10:00" in mensagem
    assert "1 cancelados no PagBank" in mensagem
    assert "1 eventos não aprovados/ajustes no PagBank" in mensagem
    assert "frentista não identificado" in mensagem
    assert "tipoInclusao=" in mensagem


def test_v3_1_manuais_no_grupo_laranja_idempotente(tmp_path, monkeypatch):
    from src.modules.cash_reconciliation.application.conciliar_cartoes import conciliar
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente
    from .test_cartoes import C

    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", tmp_path / "pendencias.sqlite3")
    cartoes = [
        C(codigo, valor, "01:00", aut="1234", dia=DIA.isoformat()).model_copy(
            update={
                "empresa_codigo": EMPRESA,
                "tipo_inclusao": "Manualmente",
                "venda_codigo": 0,
                "caixa_codigo": 106,
                "frentista": 7,
                "nome_frentista": "Funcionário Sintético",
            }
        )
        for codigo, valor in ((1, "150.04"), (2, "20"))
    ]
    resultado = conciliar(EMPRESA, "PAGBANK", DIA, [], cartoes, [], set())
    diario = diario_com_alertas(alertas_laranja()).model_copy(
        update={
            "recebimentos": ResultadoRecebimentos(
                empresa_codigo=EMPRESA,
                dia=DIA,
                adquirentes=(RecebimentoAdquirente.de_resultado(resultado),),
            ),
        }
    )
    entradas = pendencias_do_dia(diario)
    grupos = [p for p in entradas if p.tipo == "caixa_alertas_laranja"]
    assert len(grupos) == 1
    manuais = [
        a
        for a in json.loads(grupos[0].mensagem)["alertas"]
        if a["codigo"] == "CARTAO_MANUAL_SEM_VENDA"
    ]
    assert len(manuais) == 2
    assert sum(Decimal(a["valor"]) for a in manuais) == Decimal("170.04")
    assert repositorio.registrar(entradas) == len(entradas)
    assert repositorio.registrar(pendencias_do_dia(diario)) == 0


@pytest.mark.parametrize("disponivel", [True, False])
def test_v3_1_aprova_so_duplicidades_abertas_invalidas(tmp_path, monkeypatch, disponivel):
    from src.modules.cash_reconciliation.domain.cartoes import AlertaCartao, CartaoErp
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", tmp_path / "pendencias.sqlite3")
    referencias = [f"PAGBANK:CARTAO_NSU_REPETIDO:{i}" for i in range(1, 6)]
    entradas = [
        NovaPendencia(
            unidade=EMPRESA,
            dia=DIA,
            tipo="recebimento_nsu_repetido",
            severidade="vermelho",
            valor=Decimal("30"),
            referencia=ref,
            mensagem="Autorização sintética repetida",
        )
        for ref in referencias
    ]
    repositorio.registrar(entradas)
    antigas, _ = repositorio.listar(unidade=EMPRESA)
    por_ref = {p.referencia: p for p in antigas}
    for ref, status in zip(referencias[2:4], ("justificada", "recusada")):
        repositorio.transicionar(
            por_ref[ref].id,
            status_esperado="aberta",
            status_novo=status,
            acao=status,
            usuario="diretor",
            justificativa="Decisão sintética",
        )
    diario = criar_diario(DIA)
    cartao = CartaoErp(
        codigo=5,
        empresa_codigo=EMPRESA,
        venda_codigo=11,
        valor=Decimal("30"),
        momento=datetime(2026, 10, 6, 23, 9),
        administradora="PAGSEGURO",
        nsu="uuid-sintetico",
        nsu_tef=None,
        autorizacao=None,
    )
    alerta = AlertaCartao(
        codigo="CARTAO_NSU_REPETIDO",
        severidade="vermelho",
        valor=Decimal("30"),
        mensagem="Duplicidade real sintética",
        cartoes=(cartao,),
    )
    item = RecebimentoAdquirente(
        adquirente="PAGBANK",
        situacao="ok" if disponivel else "erro",
        alertas=(alerta,) if disponivel else (),
        proveniencia=diario.proveniencia.model_copy(update={"versao_regra": "CARTOES_V3_1"}),
    )
    diario = diario.model_copy(
        update={
            "recebimentos": ResultadoRecebimentos(
                empresa_codigo=EMPRESA,
                dia=DIA,
                adquirentes=(item,),
            ),
        }
    )
    pendencias_do_dia(diario)
    pendencias_do_dia(diario)
    for ref in referencias:
        atual = repositorio.obter(por_ref[ref].id)
        if ref in referencias[:2] and disponivel:
            assert atual.status == "aprovada"
            assert len(atual.historico) == 2
            assert atual.historico[-1].usuario == "robo"
            assert atual.historico[-1].justificativa == (
                "Regra CARTOES_V3_1: autorização repetida com valor/dia "
                "diferentes não indica duplicidade"
            )
        elif ref in referencias[2:4]:
            assert atual.status == ("justificada" if ref == referencias[2] else "recusada")
            assert len(atual.historico) == 2
        else:
            assert atual.status == "aberta"
            assert len(atual.historico) == 1


def test_fragmentacao_alerta_preserva_entidades_html():
    from html import escape, unescape
    from src.modules.cash_reconciliation.application.resumo_diario import _quebrar_linha

    texto = escape("A" * 3998 + "& <Funcionário Sintético>")
    partes = _quebrar_linha(texto, 4000)
    assert all(len(p) <= 4000 for p in partes)
    assert unescape("".join(partes)) == "A" * 3998 + "& <Funcionário Sintético>"
    assert all(not p.endswith("&a") for p in partes)


def test_sangrias_repassadas_aprovam_abertas_e_preservam_justificadas_recusadas(
    tmp_path,
    monkeypatch,
):
    banco = tmp_path / "pendencias.sqlite3"
    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", banco)
    monkeypatch.setattr(
        "src.modules.cash_reconciliation.application.gerar_pendencias.carregar_unidades",
        lambda: {
            118508: Unidade(
                empresa_codigo=118508,
                nome="CONVENIENCIA 24 HORAS",
                chave_env="CHAVE_TESTE",
                destinos=(),
                repasse_sangria_para=5555,
            ),
            5555: Unidade(
                empresa_codigo=5555,
                nome="AP CASA CAIADA",
                chave_env="CHAVE_CASA_CAIADA",
                destinos=(),
                destino_padrao=17837,
            ),
        },
    )
    antigas = [
        NovaPendencia(
            unidade=118508,
            dia=DIA,
            tipo="fechamento_sangria_sem_destino",
            severidade="vermelho",
            valor=Decimal("25.00"),
            referencia=f"caixa:1:sangria:{indice}",
            mensagem="Sangria sem conta de destino",
        )
        for indice in range(1, 4)
    ]
    repositorio.registrar(antigas, banco=banco)
    abertas, _ = repositorio.listar(unidade=118508, status="aberta", banco=banco)
    repositorio.transicionar(
        abertas[0].id,
        status_esperado="aberta",
        status_novo="justificada",
        acao="justificada",
        usuario="gerente",
        justificativa="Conferida.",
        banco=banco,
    )
    repositorio.transicionar(
        abertas[1].id,
        status_esperado="aberta",
        status_novo="recusada",
        acao="recusada",
        usuario="diretor",
        justificativa="Não procede.",
        banco=banco,
    )

    resultado = criar_diario(DIA, unidade=118508)
    assert all(
        pendencia.tipo != "fechamento_sangria_sem_destino"
        for pendencia in pendencias_do_dia(resultado)
    )
    itens, total = repositorio.listar(
        unidade=118508, tipo="fechamento_sangria_sem_destino", banco=banco
    )
    assert total == 3
    por_status = {item.status: item for item in itens}
    aprovada = por_status["aprovada"]
    assert aprovada.historico[-1].acao == "aprovada"
    assert aprovada.historico[-1].usuario == "robo"
    assert aprovada.historico[-1].justificativa == (
        "Regra FECHAMENTO_V4: sangria da Conveniência 24h repassada ao Casa Caiada "
        "(decisão do diretor em 10/10/2026)"
    )
    historico_final = len(aprovada.historico)

    pendencias_do_dia(resultado)
    novamente, _ = repositorio.listar(
        unidade=118508, tipo="fechamento_sangria_sem_destino", banco=banco
    )
    assert (
        len(next(item for item in novamente if item.status == "aprovada").historico)
        == historico_final
    )
    assert {item.status for item in novamente} == {"aprovada", "justificada", "recusada"}

    antiga_casa_caiada = NovaPendencia(
        unidade=5555,
        dia=DIA,
        tipo="fechamento_sangria_sem_destino",
        severidade="vermelho",
        valor=Decimal("25.00"),
        referencia="caixa:1:sangria:10",
        mensagem="Sangria sem conta de destino",
    )
    repositorio.registrar([antiga_casa_caiada], banco=banco)
    pendencias_do_dia(criar_diario(DIA, unidade=5555))
    casa_caiada, total_casa_caiada = repositorio.listar(
        unidade=5555,
        tipo="fechamento_sangria_sem_destino",
        banco=banco,
    )
    assert total_casa_caiada == 1
    assert casa_caiada[0].status == "aprovada"
    assert casa_caiada[0].historico[-1].usuario == "robo"
    assert casa_caiada[0].historico[-1].justificativa == (
        "Regra FECHAMENTO_V4: sangria assumida no cofre "
        "(destino padrão 17837), conforme decisão do diretor em 10/10/2026"
    )


def diario_com_alertas(alertas):
    resultado = criar_diario(DIA)
    auditoria = resultado.fechamento.caixas[0].model_copy(update={"alertas": tuple(alertas)})
    fechamento = resultado.fechamento.model_copy(update={"caixas": (auditoria,)})
    return resultado.model_copy(update={"fechamento": fechamento})


def alertas_laranja(sufixo=""):
    return (
        Alerta(
            codigo="SANGRIA_ALTERADA",
            severidade=Severidade.LARANJA,
            mensagem=f"Sangria alterada A{sufixo}",
            valor=Decimal("10.00"),
            referencia=1,
        ),
        Alerta(
            codigo="DESPESA_SEM_PLANO",
            severidade=Severidade.LARANJA,
            mensagem=f"Despesa sem plano B{sufixo}",
            valor=Decimal("12.50"),
            referencia=2,
        ),
        Alerta(
            codigo="VALE_DIVERGENTE",
            severidade=Severidade.LARANJA,
            mensagem=f"Vale divergente C{sufixo}",
            valor=Decimal("2.50"),
            referencia=3,
        ),
    )


def test_alertas_laranja_do_caixa_agrupados_e_vermelho_individual():
    resultado = diario_com_alertas(
        (
            Alerta(
                codigo="QUEBRA",
                severidade=Severidade.VERMELHO,
                mensagem="Dinheiro: quebra",
                valor=Decimal("-25.00"),
                referencia=106,
            ),
            *alertas_laranja(),
        )
    )

    novas = pendencias_do_dia(resultado)
    assert [pendencia.tipo for pendencia in novas] == [
        "fechamento_quebra",
        "caixa_alertas_laranja",
    ]
    grupo = novas[1]
    assert grupo.valor == Decimal("25.00")
    assert grupo.referencia == "caixa:106:laranja"
    assert len(json.loads(grupo.mensagem)["alertas"]) == 3


def test_reprocessar_atualiza_detalhe_aberto_sem_duplicar(tmp_path):
    banco = tmp_path / "pendencias.sqlite3"
    primeira = pendencias_do_dia(diario_com_alertas(alertas_laranja()))
    segunda = pendencias_do_dia(diario_com_alertas(alertas_laranja("-atualizado")))

    assert repositorio.registrar(primeira, banco=banco) == 1
    assert repositorio.registrar(segunda, banco=banco) == 0
    itens, total = repositorio.listar(unidade=EMPRESA, banco=banco)
    agrupada = next(item for item in itens if item.tipo == "caixa_alertas_laranja")
    assert total == 1
    assert agrupada.valor == Decimal("25.00")
    assert "atualizado" in agrupada.mensagem
    assert [evento.acao for evento in agrupada.historico] == ["criada", "detalhe_atualizado"]


def diario_com_recebimentos_a_maior():
    from src.modules.cash_reconciliation.domain.cartoes import (
        Abastecimento, Atribuicao, Candidato, Investigacao, TransacaoAdquirente,
    )
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    diario = criar_diario(DIA)
    auditoria = diario.fechamento.caixas[0]
    caixa = auditoria.caixa.model_copy(update={
        "fechamento": datetime(2026, 10, 6, 23, 59, tzinfo=FUSO),
    })
    diario = diario.model_copy(update={
        "fechamento": diario.fechamento.model_copy(update={
            "caixas": (auditoria.model_copy(update={"caixa": caixa, "alertas": ()}),),
        }),
    })
    itens = []
    for indice, adquirente in enumerate(("PAGBANK", "PREMMIA", "PREMMIA")):
        transacao = TransacaoAdquirente(
            adquirente=adquirente, identificador=f"transacao-{indice}",
            nsu=f"12345678{indice}", autorizacao=None, valor=Decimal("10"),
            momento=datetime(2026, 10, 6, 10, indice), bandeira="Pix",
        )
        candidato = Candidato(
            abastecimento=Abastecimento(
                codigo=indice, empresa_codigo=EMPRESA, momento=transacao.momento,
                bico=1, valor=transacao.valor, frentista=7, venda_item_codigo=indice,
                nome_frentista="Funcionário Sintético",
            ),
            pontos=70 if indice else 90, motivos=("valor e hora compatíveis",),
            venda_em_dinheiro=False,
        )
        itens.append(Investigacao(
            transacao=transacao,
            atribuicao=Atribuicao.SUGESTAO if indice else Atribuicao.ATRIBUIDO,
            frentista=None if indice else 7,
            nome_frentista=None if indice else "Funcionário Sintético",
            candidatos=(candidato,), troca_de_forma=False,
        ))
    return diario.model_copy(update={
        "recebimentos": ResultadoRecebimentos(
            empresa_codigo=EMPRESA, dia=DIA,
            adquirentes=tuple(
                RecebimentoAdquirente(
                    adquirente=nome, situacao="ok",
                    a_maior=tuple(i for i in itens if i.transacao.adquirente == nome),
                ) for nome in ("PAGBANK", "PREMMIA")
            ),
        ),
    })


@pytest.mark.parametrize("sem_caixa", [False, True])
def test_tres_a_maior_geram_um_grupo_idempotente_com_detalhes(tmp_path, sem_caixa):
    diario = diario_com_recebimentos_a_maior()
    if sem_caixa:
        diario = diario.model_copy(update={"fechamento": None})
    novas = pendencias_do_dia(diario)
    assert len(novas) == 1
    grupo = novas[0]
    assert grupo.tipo == "caixa_alertas_laranja"
    assert grupo.referencia == f"caixa:{'sem caixa' if sem_caixa else 106}:laranja"
    assert grupo.valor == Decimal("30")
    detalhes = json.loads(grupo.mensagem)["alertas"]
    assert len(detalhes) == 3
    for indice, item in enumerate(detalhes):
        assert item["valor"] == "10"
        assert item["hora"] == f"10:0{indice}:00"
        assert item["forma"] == "Pix"
        assert item["nsu"] == f"12345678{indice}"
        assert "Funcionário Sintético (7)" in item["mensagem"]
    assert detalhes[1]["atribuicao"] == "sugestao"
    assert detalhes[1]["frentista"] is None
    assert detalhes[1]["candidatos"][0]["nome"] == "Funcionário Sintético"
    banco = tmp_path / "pendencias.sqlite3"
    assert repositorio.registrar(novas, banco=banco) == 1
    assert repositorio.registrar(pendencias_do_dia(diario), banco=banco) == 0
    itens, total = repositorio.listar(banco=banco)
    assert total == 1
    assert [e.acao for e in itens[0].historico] == ["criada"]


def test_a_maior_legadas_so_abertas_substituidas_com_historico(tmp_path):
    diario = diario_com_recebimentos_a_maior()
    grupo = pendencias_do_dia(diario)[0]
    detalhes = json.loads(grupo.mensagem)["alertas"]
    banco = tmp_path / "pendencias.sqlite3"
    for item in detalhes:
        repositorio.registrar([NovaPendencia(
            unidade=EMPRESA, dia=DIA, tipo="recebimento_a_maior",
            severidade="laranja", valor=Decimal(item["valor"]),
            referencia=item["referencia"], mensagem="Pendência legada sintética",
        )], banco=banco)
    antigas, _ = repositorio.listar(banco=banco)
    for antiga, status in zip(antigas[1:], ("justificada", "recusada")):
        repositorio.transicionar(
            antiga.id, status_esperado="aberta", status_novo=status,
            acao=status, usuario="diretor", justificativa="Decisão sintética", banco=banco,
        )
    assert repositorio.registrar([grupo], banco=banco) == 1
    assert repositorio.registrar([grupo], banco=banco) == 0
    itens, total = repositorio.listar(banco=banco)
    assert total == 4
    agrupada = next(i for i in itens if i.tipo == "caixa_alertas_laranja")
    substituida = repositorio.obter(antigas[0].id, banco=banco)
    assert substituida.status == "substituida"
    assert substituida.referencia == agrupada.referencia
    assert [e.acao for e in substituida.historico] == ["criada", "substituida"]
    assert agrupada.id in substituida.historico[-1].justificativa
    assert repositorio.obter(antigas[1].id, banco=banco).status == "justificada"
    assert repositorio.obter(antigas[2].id, banco=banco).status == "recusada"


def test_estorno_confirmado_fecha_apuracao_duplicada_com_historico(tmp_path, monkeypatch):
    from src.modules.cash_reconciliation.domain.cartoes import AlertaCartao, TransacaoAdquirente
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    banco = tmp_path / "pendencias.sqlite3"
    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", banco)
    extra_id = "transacao-extra"
    acao_id = hashlib.sha256(
        f"{EMPRESA}|{DIA}|PAGBANK|transacao:{extra_id}".encode()
    ).hexdigest()
    repositorio.registrar(
        [NovaPendencia(
            unidade=EMPRESA,
            dia=DIA,
            tipo="recebimento_apurar",
            severidade="vermelho",
            valor=Decimal("250.07"),
            referencia=acao_id,
            mensagem="Cobrança duplicada — verificar estorno ao cliente.",
        )],
        banco=banco,
    )
    transacoes = (
        TransacaoAdquirente(
            adquirente="PAGBANK", identificador="transacao-venda", nsu=None,
            autorizacao="024956", valor=Decimal("250.07"),
            momento=datetime(2026, 10, 6, 19, 13), bandeira="VISA",
        ),
        TransacaoAdquirente(
            adquirente="PAGBANK", identificador=extra_id, nsu=None,
            autorizacao="018845", valor=Decimal("250.07"),
            momento=datetime(2026, 10, 6, 19, 12), bandeira="VISA",
        ),
        TransacaoAdquirente(
            adquirente="PAGBANK", identificador=extra_id, nsu=None,
            autorizacao="018845", valor=Decimal("250.07"),
            momento=datetime(2026, 10, 7, 8), bandeira="VISA", situacao="estornada",
        ),
    )
    resolvido = criar_diario(DIA).model_copy(update={
        "conferencia_recebimentos": True,
        "recebimentos": ResultadoRecebimentos(
            empresa_codigo=EMPRESA,
            dia=DIA,
            adquirentes=(RecebimentoAdquirente(
                adquirente="PAGBANK",
                situacao="ok",
                alertas=(AlertaCartao(
                    codigo="CARTAO_COBRANCA_DUPLICADA_ESTORNADA",
                    severidade="informativo",
                    mensagem="Estorno confirmado no dia seguinte.",
                    valor=Decimal("250.07"),
                    transacoes=transacoes,
                ),),
            ),),
        ),
    })

    pendencias_do_dia(resolvido)
    pendencia = next(
        item for item in repositorio.listar(unidade=EMPRESA, limite=100)[0]
        if item.referencia == acao_id
    )
    assert pendencia.status == "aprovada"
    assert [evento.acao for evento in pendencia.historico] == ["criada", "estorno_confirmado"]


def test_a_maior_caixas_sobrepostos_nao_inventa_vinculo():
    diario = diario_com_recebimentos_a_maior()
    auditoria = diario.fechamento.caixas[0]
    outra = auditoria.model_copy(update={
        "caixa": auditoria.caixa.model_copy(update={"codigo": 999}),
    })
    diario = diario.model_copy(update={
        "fechamento": diario.fechamento.model_copy(update={"caixas": (auditoria, outra)}),
    })
    assert pendencias_do_dia(diario)[0].referencia == "caixa:sem caixa:laranja"


def test_a_maior_telegram_preserva_detalhes_e_mascara_nsu():
    from src.modules.cash_reconciliation.application.resumo_diario import gerar_mensagem_curta

    diario = diario_com_recebimentos_a_maior()
    mensagem = "\n".join(gerar_mensagem_curta(
        DIA, [diario], [EMPRESA], set(), {EMPRESA: 1},
    ))
    assert "10:01" in mensagem and "Pix" in mensagem
    assert "NSU 6781" in mensagem
    assert "123456781" not in mensagem
    assert "Sugestão: Funcionário Sintético (7)" in mensagem


@pytest.mark.parametrize("com_ativos", [True, False])
def test_legada_agora_provavel_vira_historico_sem_somar_ao_laranja(
    tmp_path, monkeypatch, com_ativos,
):
    from src.modules.cash_reconciliation.domain.cartoes import CartaoErp, ParProvavel

    banco = tmp_path / "pendencias.sqlite3"
    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", banco)
    diario = diario_com_recebimentos_a_maior()
    pagbank, premmia = diario.recebimentos.adquirentes
    inv = premmia.a_maior[0]
    repositorio.registrar([NovaPendencia(
        unidade=EMPRESA, dia=DIA, tipo="recebimento_a_maior",
        severidade="laranja", valor=inv.transacao.valor,
        referencia="PREMMIA:transacao:transacao-1", mensagem="Alerta legado",
    )])
    antiga = repositorio.listar()[0][0]
    par = ParProvavel(
        investigacao=inv,
        cartao=CartaoErp(
            codigo=5, empresa_codigo=EMPRESA, venda_codigo=None, valor=Decimal("10"),
            momento=inv.transacao.momento, administradora="PREMMIA PIX", nsu="outro",
            nsu_tef=None, autorizacao=None,
        ),
    )
    diario = diario.model_copy(update={
        "recebimentos": diario.recebimentos.model_copy(update={
            "adquirentes": (
                pagbank.model_copy(update={"a_maior": pagbank.a_maior if com_ativos else ()}),
                premmia.model_copy(update={
                    "a_maior": premmia.a_maior[1:] if com_ativos else (),
                    "pares_provaveis": (par,),
                }),
            ),
        }),
    })
    novas = pendencias_do_dia(diario)
    assert len(novas) == 1
    assert novas[0].valor == (Decimal("20") if com_ativos else None)
    assert repositorio.registrar(novas) == 1
    assert repositorio.registrar(pendencias_do_dia(diario)) == 0
    grupo = next(p for p in repositorio.listar()[0] if p.tipo == "caixa_alertas_laranja")
    assert grupo.status == ("aberta" if com_ativos else "aprovada")
    assert grupo.valor == (Decimal("20") if com_ativos else None)
    detalhes = json.loads(grupo.mensagem)
    assert len(detalhes["historicos"]) == 1
    assert detalhes["historicos"][0]["classificacao_atual"] == "par provável"
    assert detalhes["historicos"][0]["nsu"] == inv.transacao.nsu
    substituida = repositorio.obter(antiga.id)
    assert substituida.status == "substituida"
    assert "Agora par provável" in substituida.historico[-1].justificativa
    assert grupo.id in substituida.historico[-1].justificativa


def test_legada_ausente_arquivada_sem_inventar_detalhe(tmp_path, monkeypatch):
    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", tmp_path / "pendencias.sqlite3")
    repositorio.registrar([NovaPendencia(
        unidade=EMPRESA, dia=DIA, tipo="recebimento_a_maior",
        severidade="laranja", valor=Decimal("25"), referencia="PAGBANK:transacao:antiga",
        mensagem="Funcionário Sintético (7); alerta legado",
    )])
    diario = criar_diario(DIA).model_copy(update={
        "recebimentos": diario_com_recebimentos_a_maior().recebimentos.model_copy(update={
            "adquirentes": tuple(
                a.model_copy(update={"a_maior": ()})
                for a in diario_com_recebimentos_a_maior().recebimentos.adquirentes
            ),
        }),
    })
    novas = pendencias_do_dia(diario)
    assert len(novas) == 2  # Quebra vermelha e grupo somente histórico.
    grupo = next(p for p in novas if p.tipo == "caixa_alertas_laranja")
    assert grupo.referencia == "caixa:sem caixa:laranja"
    assert grupo.valor is None
    detalhe = json.loads(grupo.mensagem)["historicos"][0]
    assert detalhe["valor"] == "25"
    assert detalhe["hora"] is None and detalhe["forma"] is None and detalhe["nsu"] is None
    assert "Funcionário Sintético (7)" in detalhe["mensagem"]
    assert detalhe["classificacao_atual"] == "não consta na conciliação atual"
    repositorio.registrar(novas)
    assert repositorio.registrar(pendencias_do_dia(diario)) == 0
    itens = repositorio.listar()[0]
    assert next(p for p in itens if p.tipo == "recebimento_a_maior").status == "substituida"
    assert next(p for p in itens if p.tipo == "caixa_alertas_laranja").status == "aprovada"


@pytest.mark.parametrize("versao", ["CARTOES_V3_2", "CARTOES_V3_3"])
def test_v32_encerra_so_vermelhas_abertas_conferidas_e_grupo_resolvido(tmp_path, monkeypatch, versao):
    from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente

    monkeypatch.setattr(repositorio, "BANCO_PENDENCIAS", tmp_path / "pendencias.sqlite3")
    for codigo in (1, 2, 3):
        repositorio.registrar([NovaPendencia(
            unidade=EMPRESA, dia=DIA, tipo="recebimento_a_menor", severidade="vermelho",
            valor=Decimal("12"), referencia=f"PREMMIA:cartao:{codigo}", mensagem="Sintético",
        )])
    itens = repositorio.listar()[0]
    protegida = next(p for p in itens if p.referencia.endswith(":2"))
    repositorio.transicionar(
        protegida.id, status_esperado="aberta", status_novo="justificada",
        acao="justificada", usuario="gerente", justificativa="Justificativa sintética",
    )
    repositorio.registrar([NovaPendencia(
        unidade=EMPRESA, dia=DIA, tipo="caixa_alertas_laranja", severidade="laranja",
        valor=Decimal("12"), referencia="caixa:106:laranja",
        mensagem=json.dumps({"alertas": [{"codigo": "X", "valor": "12", "mensagem": "Sintético"}]}),
        identidade=f"{EMPRESA}|{DIA.isoformat()}|caixa:106|laranja",
    )])
    diario = criar_diario(DIA)
    auditoria = diario.fechamento.caixas[0].model_copy(update={"alertas": ()})
    diario = diario.model_copy(update={
        "fechamento": diario.fechamento.model_copy(update={"caixas": (auditoria,)}),
        "recebimentos": ResultadoRecebimentos(
            empresa_codigo=EMPRESA, dia=DIA, adquirentes=(RecebimentoAdquirente(
                adquirente="PREMMIA", situacao="ok", codigos_conferidos=(1, 2),
                proveniencia=diario.proveniencia.model_copy(update={"versao_regra": versao}),
            ),),
        ),
    })
    assert pendencias_do_dia(diario) == []
    assert pendencias_do_dia(diario) == []
    por_ref = {p.referencia: p for p in repositorio.listar()[0]}
    assert por_ref["PREMMIA:cartao:1"].status == "aprovada"
    assert len(por_ref["PREMMIA:cartao:1"].historico) == 2
    assert por_ref["PREMMIA:cartao:2"].status == "justificada"
    assert por_ref["PREMMIA:cartao:3"].status == "aberta"
    assert por_ref["caixa:106:laranja"].status == "aprovada"
    if versao == "CARTOES_V3_3":
        for referencia in ("PREMMIA:cartao:1", "caixa:106:laranja"):
            historico = por_ref[referencia].historico[-1]
            assert historico.usuario == "robo"
            assert historico.justificativa == "CARTOES_V3_3: cupom repetido estava sendo deduplicado indevidamente"

def test_laranjas_individuais_abertas_sao_substituidas_com_historico(tmp_path):
    banco = tmp_path / "pendencias.sqlite3"
    resultado = diario_com_alertas(alertas_laranja())
    caixa = resultado.fechamento.caixas[0].caixa.codigo
    with sqlite3.connect(banco) as conexao:
        conexao.executescript("""
            CREATE TABLE pendencias (
                id TEXT PRIMARY KEY,
                identidade TEXT NOT NULL UNIQUE,
                unidade INTEGER NOT NULL,
                dia TEXT NOT NULL,
                tipo TEXT NOT NULL,
                severidade TEXT NOT NULL CHECK (severidade IN ('vermelho', 'laranja')),
                valor TEXT,
                referencia TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('aberta', 'justificada', 'aprovada', 'recusada')),
                responsavel TEXT,
                criada_em TEXT NOT NULL
            );
            CREATE TABLE historico_pendencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pendencia_id TEXT NOT NULL REFERENCES pendencias(id),
                acao TEXT NOT NULL,
                status_anterior TEXT,
                status_novo TEXT NOT NULL,
                usuario TEXT NOT NULL,
                justificativa TEXT,
                registrado_em TEXT NOT NULL
            );
            """)
    antigas = [
        NovaPendencia(
            unidade=EMPRESA,
            dia=DIA,
            tipo="fechamento_sangria_alterada",
            severidade="laranja",
            valor=Decimal("10.00"),
            referencia=f"caixa:{caixa}:sangria:{indice}",
            mensagem=f"Alerta individual {indice}",
        )
        for indice in range(1, 4)
    ]
    with sqlite3.connect(banco) as conexao:
        for indice, antiga in enumerate(antigas, start=1):
            identidade = hashlib.sha256(
                f"{antiga.unidade}|{antiga.dia.isoformat()}|{antiga.tipo}|{antiga.referencia}".encode()
            ).hexdigest()
            conexao.execute(
                """
                INSERT INTO pendencias
                    (id, identidade, unidade, dia, tipo, severidade, valor, referencia,
                     mensagem, status, responsavel, criada_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'aberta', NULL, ?)
                """,
                (
                    f"legada-{indice}",
                    identidade,
                    antiga.unidade,
                    antiga.dia.isoformat(),
                    antiga.tipo,
                    antiga.severidade,
                    str(antiga.valor),
                    antiga.referencia,
                    antiga.mensagem,
                    datetime(2026, 10, 7).isoformat(),
                ),
            )
            conexao.execute(
                """
                INSERT INTO historico_pendencias
                    (pendencia_id, acao, status_anterior, status_novo, usuario, registrado_em)
                VALUES (?, 'criada', NULL, 'aberta', 'robô-noturno', ?)
                """,
                (f"legada-{indice}", datetime(2026, 10, 7).isoformat()),
            )

    agrupadas = pendencias_do_dia(resultado)
    assert repositorio.registrar(agrupadas, banco=banco) == 1
    itens, _ = repositorio.listar(unidade=EMPRESA, banco=banco)
    antiga_substituida = [item for item in itens if item.tipo == "fechamento_sangria_alterada"]
    agrupada = next(item for item in itens if item.tipo == "caixa_alertas_laranja")
    assert len(antiga_substituida) == 3
    assert all(item.status == "substituida" for item in antiga_substituida)
    assert all(item.referencia == agrupada.referencia for item in antiga_substituida)
    assert all(item.historico[-1].acao == "substituida" for item in antiga_substituida)
    assert all(agrupada.id in item.historico[-1].justificativa for item in antiga_substituida)
    with sqlite3.connect(banco) as conexao:
        assert conexao.execute("PRAGMA foreign_key_check").fetchall() == []


def test_reincidencia_gera_um_alerta_so_apos_duas_ocorrencias():
    primeiro = criar_diario(DIA)
    segundo = criar_diario(date(2026, 10, 7))

    assert pendencias_de_reincidencia(EMPRESA, "2026-10", [primeiro]) == []
    reincidencias = pendencias_de_reincidencia(EMPRESA, "2026-10", [primeiro, segundo])

    assert len(reincidencias) == 1
    assert reincidencias[0].tipo == "reincidencia_quebra"
    assert reincidencias[0].dia == date(2026, 10, 7)
    assert reincidencias[0].referencia == "funcionario:7"


def test_gerente_justifica_e_diretor_decide_sem_alterar_historico(client, tmp_path):
    candidatas = pendencias_do_dia(criar_diario(DIA))
    repositorio.registrar(candidatas, banco=tmp_path / "pendencias.sqlite3")

    autenticar(client, "gerente", EMPRESA, "gerente@example.invalid")
    fila = client.get("/api/v1/cash-audit/pendencias", params={"unidade": EMPRESA})
    assert fila.status_code == 200
    pendencia_id = fila.json()["items"][0]["id"]
    assert client.get("/api/v1/cash-audit/pendencias", params={"unidade": 654}).status_code == 403
    assert (
        client.post(f"/api/v1/cash-audit/pendencias/{pendencia_id}/aprovar", json={}).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/cash-audit/pendencias/{pendencia_id}/justificar",
            json={"justificativa": "   "},
        ).status_code
        == 422
    )

    justificada = client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/justificar",
        json={"justificativa": "Conferido com o responsável da unidade."},
    )
    assert justificada.status_code == 200
    assert justificada.json()["status"] == "justificada"
    assert justificada.json()["responsavel"] == "gerente@example.invalid"
    assert len(justificada.json()["historico"]) == 2

    corrigida = client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/justificar",
        json={"justificativa": "Complemento da justificativa registrado."},
    )
    assert corrigida.status_code == 200
    assert [evento["justificativa"] for evento in corrigida.json()["historico"]] == [
        None,
        "Conferido com o responsável da unidade.",
        "Complemento da justificativa registrado.",
    ]

    autenticar(client, "diretor", usuario="diretor@example.invalid")
    aprovada = client.post(
        f"/api/v1/cash-audit/pendencias/{pendencia_id}/aprovar",
        json={"observacao": "A justificativa foi aceita."},
    )
    assert aprovada.status_code == 200
    assert aprovada.json()["status"] == "aprovada"
    assert [evento["acao"] for evento in aprovada.json()["historico"]] == [
        "criada",
        "justificada",
        "justificativa_corrigida",
        "aprovada",
    ]
    assert (
        client.post(f"/api/v1/cash-audit/pendencias/{pendencia_id}/recusar", json={}).status_code
        == 409
    )


def test_auditor_le_mas_nao_altera_e_anonimo_nao_lista(client):
    assert client.get("/api/v1/cash-audit/pendencias").status_code == 401
    autenticar(client, "auditor")
    assert client.get("/api/v1/cash-audit/pendencias").status_code == 200


def test_prazo_vencida_por_severidade_justificada_e_filtro(client, monkeypatch, tmp_path):
    agora_local = datetime.fromisoformat("2026-10-10T12:00:00-03:00")
    criada = datetime.fromisoformat("2026-10-07T12:00:00-03:00")
    monkeypatch.setattr(repositorio, "agora", lambda: criada)
    monkeypatch.setattr(http, "agora", lambda: agora_local)
    configuracao = tmp_path / "units.json"
    configuracao.write_text(
        json.dumps({"prazo_pendencia_dias": {"vermelho": 2, "laranja": 5}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(http, "ARQUIVO_CONFIG_UNIDADES", configuracao)

    candidatas = [
        NovaPendencia(
            unidade=EMPRESA,
            dia=DIA,
            tipo="prazo_teste",
            severidade=severidade,
            referencia=referencia,
            mensagem="Pendência de teste temporária",
        )
        for severidade, referencia in (
            ("vermelho", "vermelha-vencida"),
            ("laranja", "laranja-no-prazo"),
            ("vermelho", "justificada-antiga"),
        )
    ]
    repositorio.registrar(candidatas)
    itens, _ = repositorio.listar(unidade=EMPRESA, tipo="prazo_teste")
    antiga_justificada = next(item for item in itens if item.referencia == "justificada-antiga")
    repositorio.transicionar(
        antiga_justificada.id,
        status_esperado="aberta",
        status_novo="justificada",
        acao="justificada",
        usuario="gerente",
        justificativa="Conferida com os comprovantes disponíveis.",
    )

    autenticar(client, "diretor")
    resposta = client.get(
        "/api/v1/cash-audit/pendencias",
        params={"unidade": EMPRESA, "tipo": "prazo_teste", "status": "todas", "limite": 200},
    )
    assert resposta.status_code == 200
    por_referencia = {item["referencia"]: item for item in resposta.json()["items"]}
    assert por_referencia["vermelha-vencida"]["aberta_ha_dias"] == 3
    assert por_referencia["vermelha-vencida"]["vencida"] is True
    assert por_referencia["laranja-no-prazo"]["vencida"] is False
    assert por_referencia["justificada-antiga"]["status"] == "justificada"
    assert por_referencia["justificada-antiga"]["vencida"] is False
    assert resposta.json()["items"][0]["referencia"] == "vermelha-vencida"

    vencidas = client.get(
        "/api/v1/cash-audit/pendencias",
        params={"unidade": EMPRESA, "tipo": "prazo_teste", "vencidas": "true"},
    )
    assert vencidas.status_code == 200
    assert vencidas.json()["total"] == 1
    assert [item["referencia"] for item in vencidas.json()["items"]] == ["vermelha-vencida"]


def test_idade_da_pendencia_considera_virada_de_dia_em_recife(client, monkeypatch):
    criada = datetime.fromisoformat("2026-10-01T23:30:00-03:00")
    agora_local = datetime.fromisoformat("2026-10-02T00:15:00-03:00")
    monkeypatch.setattr(repositorio, "agora", lambda: criada)
    monkeypatch.setattr(http, "agora", lambda: agora_local)
    repositorio.registrar(
        [
            NovaPendencia(
                unidade=EMPRESA,
                dia=DIA,
                tipo="virada_dia",
                severidade="vermelho",
                referencia="virada",
                mensagem="Pendência de teste temporária",
            )
        ]
    )

    autenticar(client, "diretor")
    resposta = client.get(
        "/api/v1/cash-audit/pendencias",
        params={"unidade": EMPRESA, "tipo": "virada_dia"},
    )
    assert resposta.status_code == 200
    pendencia = resposta.json()["items"][0]
    assert pendencia["aberta_ha_dias"] == 1
    assert pendencia["vencida"] is False


def test_conta_pendencias_vencidas_somente_leitura(tmp_path):
    banco = tmp_path / "pendencias.sqlite3"
    instante = datetime.fromisoformat("2026-10-10T12:00:00-03:00")
    novas = [
        NovaPendencia(
            unidade=EMPRESA,
            dia=date(2026, 10, 6),
            tipo="resumo_teste",
            severidade=severidade,
            referencia=referencia,
            mensagem="Pendência sintética",
        )
        for severidade, referencia in (
            ("vermelho", "vermelha-antiga"),
            ("laranja", "laranja-no-prazo"),
            ("vermelho", "justificada"),
        )
    ]
    repositorio.registrar(novas, banco=banco)
    itens, _ = repositorio.listar(unidade=EMPRESA, tipo="resumo_teste", banco=banco)
    justificada = next(item for item in itens if item.referencia == "justificada")
    repositorio.transicionar(
        justificada.id,
        status_esperado="aberta",
        status_novo="justificada",
        acao="justificada",
        usuario="teste",
        banco=banco,
    )
    with sqlite3.connect(banco) as conexao:
        conexao.execute(
            "UPDATE pendencias SET criada_em = ? WHERE tipo = ?",
            ("2026-10-07T12:00:00-03:00", "resumo_teste"),
        )
        conexao.commit()

    assert (
        repositorio.contar_vencidas_somente_leitura(
            unidade=EMPRESA,
            prazos_dias={"vermelho": 2, "laranja": 5},
            instante=instante,
            banco=banco,
        )
        == 1
    )
