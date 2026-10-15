from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.modules.cash_reconciliation.adapters import telegram_cartoes, webposto_escrita_cartao as escrita
from src.modules.cash_reconciliation.application import piloto_cartao as piloto
from src.modules.cash_reconciliation.domain.cartoes import Candidato, Investigacao, Atribuicao
from src.modules.cash_reconciliation.domain.models import Unidade
from src.modules.cash_reconciliation.domain.fechamento import Caixa
from src.modules.cash_reconciliation.domain.tempo import agora
from .test_cartoes import A, C, T, DIA


@pytest.fixture(autouse=True)
def sem_rede_real(monkeypatch):
    async def bloquear(*args, **kwargs):
        pytest.fail("Os testes do piloto só podem usar transporte falso.")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", bloquear)


@pytest.fixture
def caso():
    unidade = Unidade(empresa_codigo=74014, nome="Posto Sintético", apelido="Doze",
                      chave_env="CHAVE_SINTETICA", adquirentes=(), destinos=())
    t = T("34.75", "11:26:18", nsu="TESTE0163", aut="AUT-SINTETICA").model_copy(update={"bandeira": "MASTERCARD"})
    ab = A(1, "34.75", "11:26", frentista=7, item=2).model_copy(update={
        "venda_codigo": 101, "nome_frentista": "Frentista Sintético",
    })
    cand = Candidato(abastecimento=ab, pontos=99, motivos=("valor igual", "venda em dinheiro"), venda_em_dinheiro=True)
    inv = Investigacao(transacao=t, atribuicao=Atribuicao.ATRIBUIDO, frentista=7,
                       candidatos=(cand,), troca_de_forma=True)
    caixa = Caixa(codigo=201, empresa_codigo=74014, data=DIA, turno="1", pdv_codigo=1,
                  centro_custo=7295, funcionario_codigo=7, abertura=t.momento - timedelta(hours=2),
                  fechamento=t.momento + timedelta(hours=2), fechado=True, consolidado=False, bloqueado=False)
    venda = {"vendaCodigo": 101, "empresaCodigo": 74014, "caixaCodigo": 201, "cancelada": "N"}
    admins = [{"codigo": 301, "descricao": "MASTERCARD PAGSEGURO", "ativo": True}]
    return SimpleNamespace(unidade=unidade, inv=inv, caixa=caixa, venda=venda, admins=admins)


def proposta(caso, **kwargs):
    return piloto.avaliar(caso.unidade, DIA, caso.inv, venda=caso.venda, caixas=[caso.caixa],
                          administradoras=caso.admins, total_dia=kwargs.get("total", Decimal(0)),
                          nomes_funcionarios={7: "WANDERSON DA SILVA"},
                          saldos=(Decimal("15855.41"), Decimal("23439.22")))


def test_texto_comum_sem_jargao_e_payload(caso):
    p = proposta(caso)
    assert p.elegivel
    assert "Doze · Pista — caixa de" in p.texto
    assert "201" not in p.texto and "caixaCodigo" not in p.texto
    assert "aberto por WANDERSON DA SILVA" in p.texto
    assert "(único caixa do dia)" in p.texto
    assert "Antes: dinheiro R$ 15.855,41 · cartão R$ 23.439,22." in p.texto
    assert "Depois de lançar: dinheiro R$ 15.820,66 · cartão R$ 23.473,97." in p.texto
    assert "Mastercard de R$ 34,75" in p.texto
    assert "Frentista Sintético (7)" in p.texto
    assert "NSU final 0163" in p.texto and "TESTE0163" not in p.texto
    assert "dinheiro esperado cai R$ 34,75 e o cartão sobe R$ 34,75" in p.texto
    assert all(j not in p.texto for j in ("nota", "candidato", "idempotência", "≥"))
    assert set(p.payload) <= escrita.CAMPOS_PERMITIDOS_SPEC
    assert p.payload["vendaCodigo"] == 101
    assert p.payload["centroCustoCodigo"] == 7295


@pytest.mark.parametrize("alteracao,motivo", [
    ("pix", "não é cartão"), ("sem_candidato", "não encontrei"),
    ("dois", "dois ou mais"), ("nota", "segurança"),
    ("valor", "R$ 300,00"), ("consolidado", "consolidado"),
    ("bloqueado", "bloqueado"), ("sem_venda", "faltam dados"),
    ("cancelada", "cancelada"), ("sem_nsu", "NSU"),
    ("sem_autorizacao", "autorização"), ("sem_admin", "administradora"),
    ("admin_inativa", "administradora"), ("ambigua", "administradora"),
    ("valor_abastecimento", "não confirma"), ("nao_dinheiro", "não confirma"),
])
def test_todas_condicoes_do_piloto(caso, alteracao, motivo):
    inv = caso.inv
    cand = inv.candidatos[0]
    if alteracao == "pix":
        inv = inv.model_copy(update={"transacao": inv.transacao.model_copy(update={"bandeira": "BACEN"})})
    elif alteracao in {"sem_candidato", "dois"}:
        inv = inv.model_copy(update={"candidatos": () if alteracao == "sem_candidato" else (cand, cand)})
    elif alteracao == "nota":
        inv = inv.model_copy(update={"candidatos": (cand.model_copy(update={"pontos": 89}),)})
    elif alteracao == "valor":
        ab = cand.abastecimento.model_copy(update={"valor": Decimal("300.01")})
        inv = inv.model_copy(update={"transacao": inv.transacao.model_copy(update={"valor": Decimal("300.01")}),
                                     "candidatos": (cand.model_copy(update={"abastecimento": ab}),)})
    elif alteracao in {"consolidado", "bloqueado"}:
        caso.caixa = caso.caixa.model_copy(update={alteracao: True})
    elif alteracao == "sem_venda":
        caso.venda = None
    elif alteracao == "cancelada":
        caso.venda["cancelada"] = "S"
    elif alteracao in {"sem_nsu", "sem_autorizacao"}:
        inv = inv.model_copy(update={"transacao": inv.transacao.model_copy(update={
            "nsu" if alteracao == "sem_nsu" else "autorizacao": None,
        })})
    elif alteracao == "sem_admin":
        caso.admins = []
    elif alteracao == "admin_inativa":
        caso.admins[0]["ativo"] = False
    elif alteracao == "ambigua":
        caso.admins.append({**caso.admins[0], "codigo": 302})
    elif alteracao == "valor_abastecimento":
        inv = inv.model_copy(update={"candidatos": (cand.model_copy(update={
            "abastecimento": cand.abastecimento.model_copy(update={"valor": Decimal("40")}),
        }),)})
    elif alteracao == "nao_dinheiro":
        inv = inv.model_copy(update={"candidatos": (cand.model_copy(update={"venda_em_dinheiro": False}),)})
    caso.inv = inv
    p = proposta(caso)
    assert not p.elegivel and p.payload is None
    assert motivo in p.texto


def test_limite_exato_dia_e_por_cartao(caso):
    assert proposta(caso, total=Decimal("965.25")).elegivel
    assert not proposta(caso, total=Decimal("965.26")).elegivel
    cand = caso.inv.candidatos[0]
    caso.inv = caso.inv.model_copy(update={
        "transacao": caso.inv.transacao.model_copy(update={"valor": Decimal("300")}),
        "candidatos": (cand.model_copy(update={
            "abastecimento": cand.abastecimento.model_copy(update={"valor": Decimal("300")}),
        }),),
    })
    assert proposta(caso).elegivel


@pytest.fixture
def erp(caso, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\nLOGOS_CARTAO_AUTOMATICO=0\n", encoding="utf-8")
    monkeypatch.setenv("CHAVE_SINTETICA", "CHAVE-NAO-REAL")
    monkeypatch.setattr(piloto, "carregar_unidades", lambda: {74014: caso.unidade})
    p = proposta(caso)
    state = SimpleNamespace(cartoes=[], saldo=(Decimal("1000"), Decimal("500")), requests=[],
                            sem_delta=False, nsu_errado=False, erro_post=None, erro_delete=False,
                            proposta=p, env=env, diretorio=tmp_path / "auditoria")

    async def preparar(*args, **kwargs):
        return [state.proposta]

    async def caixas(*args, **kwargs):
        return [caso.caixa]

    async def cartoes(*args, **kwargs):
        return list(state.cartoes)

    async def saldos(*args, **kwargs):
        return state.saldo

    def handler(request):
        state.requests.append(request.method)
        if request.method == "POST":
            if state.erro_post:
                return httpx.Response(state.erro_post, json={"erro": "CHAVE-NAO-REAL"})
            state.cartoes = [C(901, "34.75", "11:26", nsu="OUTRO" if state.nsu_errado else p.nsu,
                               aut=p.payload["autorizacao"]).model_copy(update={
                "venda_codigo": 101, "caixa_codigo": 201,
            })]
            if not state.sem_delta:
                state.saldo = (Decimal("965.25"), Decimal("534.75"))
            return httpx.Response(201, json={"cartaoCodigo": 901})
        if state.erro_delete:
            return httpx.Response(500)
        state.cartoes = []
        state.saldo = (Decimal("1000"), Decimal("500"))
        return httpx.Response(204)

    incluir_original, excluir_original = escrita.incluir_cartao, escrita.excluir_cartao

    async def incluir(*args, **kwargs):
        return await incluir_original(*args, **kwargs, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def excluir(*args, **kwargs):
        return await excluir_original(*args, **kwargs, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    monkeypatch.setattr(piloto, "preparar", preparar)
    monkeypatch.setattr(piloto, "buscar_caixas", caixas)
    monkeypatch.setattr(piloto, "_cartoes", cartoes)
    monkeypatch.setattr(piloto, "_saldos", saldos)
    monkeypatch.setattr(escrita, "incluir_cartao", incluir)
    monkeypatch.setattr(escrita, "excluir_cartao", excluir)
    return state


async def confirmar(erp, **kwargs):
    return await piloto.confirmar(74014, DIA, erp.proposta.nsu, autor="diretor:sintético",
                                  caminho_env=erp.env, diretorio=erp.diretorio, **kwargs)


@pytest.mark.asyncio
async def test_confirmacao_verifica_saldos_nsu_e_impede_repeticao(erp):
    r = await confirmar(erp)
    assert r["estado"] == "confirmado"
    assert r["antes"] == ["1000", "500"] and r["depois"] == ["965.25", "534.75"]
    assert erp.requests == ["POST"]
    assert piloto.resumo_lancamentos([74014], DIA, diretorio=erp.diretorio) == "Lancei 1 cartão · R$ 34,75"
    with pytest.raises(piloto.PilotoErro, match="não vou repetir"):
        await confirmar(erp)
    assert erp.requests == ["POST"]


@pytest.mark.asyncio
@pytest.mark.parametrize("falha", ["sem_delta", "nsu_errado"])
async def test_201_sem_confirmacao_desfaz_e_confere_exclusao(erp, falha):
    setattr(erp, falha, True)
    r = await confirmar(erp)
    assert r == {"estado": "desfeito", "mensagem": "LANÇAMENTO DESFEITO — CONFERIR NA TELA"}
    assert erp.requests == ["POST", "DELETE"]
    assert not erp.cartoes and erp.saldo == (Decimal("1000"), Decimal("500"))
    assert piloto.resumo_lancamentos([74014], DIA, diretorio=erp.diretorio) is None
    assert piloto._total_dia(74014, DIA, erp.diretorio) == Decimal("34.75")
    h = piloto.historico(74014, DIA, diretorio=erp.diretorio)
    assert next(e for e in h if e["estado"] == "desfazendo")["recriar"] == erp.proposta.payload


@pytest.mark.asyncio
async def test_falha_ao_desfazer_bloqueia_repeticao(erp):
    erp.sem_delta = erp.erro_delete = True
    with pytest.raises(piloto.PilotoErro, match="NÃO CONSEGUI"):
        await confirmar(erp)
    assert erp.requests == ["POST", "DELETE"]
    with pytest.raises(piloto.PilotoErro, match="não conferida"):
        await confirmar(erp)
    assert erp.requests == ["POST", "DELETE"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_permissao_negada_para_sem_repetir(erp, status):
    erp.erro_post = status
    with pytest.raises(piloto.PilotoErro, match="Quality"):
        await confirmar(erp)
    assert erp.requests == ["POST"]


@pytest.mark.asyncio
async def test_perdeu_permissao_apos_post_para_sem_tentar_delete(erp, monkeypatch):
    chamadas = 0
    async def cartoes(*args):
        nonlocal chamadas
        chamadas += 1
        if chamadas > 1:
            raise piloto.WebPostoErro("HTTP 403", status_http=403)
        return []
    monkeypatch.setattr(piloto, "_cartoes", cartoes)
    with pytest.raises(piloto.PilotoErro, match="Quality"):
        await confirmar(erp)
    assert erp.requests == ["POST"]
    with pytest.raises(piloto.PilotoErro):
        await confirmar(erp)
    assert erp.requests == ["POST"]


@pytest.mark.asyncio
async def test_travas_arquivo_impedem_qualquer_envio(erp, monkeypatch):
    erp.env.write_text("WEBPOSTO_WRITES=0\nLOGOS_ERP_ESCRITA=0\n", encoding="utf-8")
    monkeypatch.setenv("WEBPOSTO_WRITES", "1")
    monkeypatch.setenv("LOGOS_ERP_ESCRITA", "1")
    with pytest.raises(piloto.PilotoErro, match="WEBPOSTO_WRITES"):
        await confirmar(erp)
    assert not erp.requests


@pytest.mark.asyncio
async def test_reconsulta_antes_de_gravar_e_previa_obsoleta(erp):
    erp.cartoes = [C(1, "34.75", "11:26", nsu=erp.proposta.nsu)]
    with pytest.raises(piloto.PilotoErro, match="já existe"):
        await confirmar(erp)
    assert not erp.requests
    erp.cartoes = []
    with pytest.raises(piloto.PilotoErro, match="mudaram"):
        await confirmar(erp, acao_id="outra-previa")
    assert not erp.requests


@pytest.mark.asyncio
async def test_caixa_consolidado_entre_previa_e_confirmacao_nao_escreve(erp, caso):
    caso.caixa = caso.caixa.model_copy(update={"consolidado": True})
    with pytest.raises(piloto.PilotoErro, match="consolidado"):
        await confirmar(erp)
    assert not erp.requests


@pytest.mark.asyncio
async def test_recusar_nao_escreve_e_impede_aprovar(erp):
    r = await piloto.decidir(74014, DIA, erp.proposta.id, "recusar", autor="diretor",
                              diretorio=erp.diretorio, caminho_env=erp.env)
    assert r["estado"] == "recusado"
    assert not erp.requests
    with pytest.raises(piloto.PilotoErro, match="decidido"):
        await confirmar(erp)


@pytest.mark.asyncio
async def test_desfazer_somente_cartao_proprio_ainda_inalterado(erp):
    await confirmar(erp)
    r = await piloto.decidir(74014, DIA, erp.proposta.id, "desfazer", autor="diretor",
                              diretorio=erp.diretorio, caminho_env=erp.env)
    assert r["estado"] == "desfeito" and erp.requests == ["POST", "DELETE"]
    with pytest.raises(piloto.PilotoErro, match="não está disponível"):
        await piloto.decidir(74014, DIA, erp.proposta.id, "desfazer", autor="diretor",
                              diretorio=erp.diretorio, caminho_env=erp.env)


def test_auditoria_corrompida_nao_vira_historico_vazio(tmp_path):
    pasta = tmp_path / "74014"
    pasta.mkdir()
    (pasta / "historico.json").write_text("quebrado", encoding="utf-8")
    with pytest.raises(escrita.BarreiraCartaoErro, match="auditoria"):
        escrita.ler_auditoria(74014, tmp_path)
    with pytest.raises(escrita.BarreiraCartaoErro, match="auditoria"):
        escrita.gravar_auditoria(74014, {}, tmp_path)


def test_bloqueio_exclusivo_entre_processos(tmp_path):
    with piloto._exclusivo(74014, tmp_path):
        with pytest.raises(piloto.PilotoErro, match="operação"):
            with piloto._exclusivo(74014, tmp_path):
                pytest.fail("não pode entrar")
    assert not (tmp_path / "74014" / "operacao.lock").exists()


@pytest.mark.asyncio
async def test_automatico_desligado_nao_consulta_nem_escreve(erp, monkeypatch):
    preparar = AsyncMock(side_effect=AssertionError("Não deve consultar"))
    monkeypatch.setattr(piloto, "preparar", preparar)
    monkeypatch.setenv("LOGOS_CARTAO_AUTOMATICO", "1")
    assert await piloto.executar_automatico(74014, DIA, caminho_env=erp.env) == []
    preparar.assert_not_called()


@pytest.mark.asyncio
async def test_automatico_utiliza_o_mesmo_caminho_e_para_apos_desfazer(erp):
    erp.env.write_text("WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\nLOGOS_CARTAO_AUTOMATICO=1\n", encoding="utf-8")
    erp.sem_delta = True
    r = await piloto.executar_automatico(74014, DIA, caminho_env=erp.env, diretorio=erp.diretorio)
    assert [e["estado"] for e in r] == ["desfeito"]
    assert erp.requests == ["POST", "DELETE"]


@pytest.mark.asyncio
async def test_cli_previa_usa_texto_do_logos_sem_escrever(erp, capsys, monkeypatch):
    from src.jobs import lancar_cartao
    monkeypatch.setattr(lancar_cartao, "load_dotenv", lambda *a, **kw: None)
    assert await lancar_cartao.executar_previa(74014, DIA) == 0
    assert erp.proposta.texto in capsys.readouterr().out
    assert not erp.requests


@pytest.mark.asyncio
async def test_preparar_busca_caixa_da_venda_em_vez_de_adivinhar(caso, monkeypatch):
    monkeypatch.setattr(piloto, "carregar_unidades", lambda: {74014: caso.unidade})
    monkeypatch.setattr(piloto, "conciliar_pagbank", AsyncMock(return_value=SimpleNamespace(a_maior=(caso.inv,))))
    monkeypatch.setattr(piloto, "buscar_caixas", AsyncMock(return_value=[caso.caixa]))
    monkeypatch.setattr(piloto, "buscar_nomes_funcionarios", AsyncMock(return_value={7: "WANDERSON DA SILVA"}))
    monkeypatch.setattr(piloto, "_saldos", AsyncMock(return_value=(Decimal("1000"), Decimal("500"))))
    monkeypatch.setattr(piloto, "_total_dia", lambda *a: Decimal(0))
    async def paginar(cfg, rota, params):
        return caso.admins if "ADMINISTRADORAS" in rota else [caso.venda]
    monkeypatch.setattr(piloto, "paginar", paginar)
    ps = await piloto.preparar(74014, DIA)
    assert len(ps) == 1 and ps[0].payload["caixaCodigo"] == 201


@pytest.mark.asyncio
async def test_reconsulta_cartao_rede_obtem_caixa_pela_venda_oficial(caso, monkeypatch):
    p = proposta(caso)
    cartao = C(1, "34.75", "11:26", nsu=p.nsu, aut=p.payload["autorizacao"]).model_copy(
        update={"venda_codigo": 101})
    assert cartao.caixa_codigo is None
    monkeypatch.setattr(piloto, "buscar_cartoes", AsyncMock(return_value=[cartao]))
    consultar = AsyncMock(return_value=[caso.venda])
    monkeypatch.setattr(piloto, "paginar", consultar)
    atualizados = await piloto._cartoes(caso.unidade, DIA, p)
    assert atualizados[0].caixa_codigo == 201
    assert piloto._compativel(atualizados[0], p)
    assert consultar.await_args.args[2]["vendaCodigo"] == 101
    assert not piloto._compativel(atualizados[0].model_copy(update={"autorizacao": "outra"}), p)


@pytest.mark.asyncio
async def test_limite_diario_rechecado_dentro_da_trava(erp):
    for n, valor in enumerate(("300", "300", "300", "80")):
        outra = replace(erp.proposta, id=f"outra-acao-{n}", nsu=f"OUTRO-NSU-{n}", valor=Decimal(valor),
                        payload={**erp.proposta.payload, "nsu": f"OUTRO-NSU-{n}", "valor": float(valor)})
        piloto._registrar(outra, "reservado", "diretor", erp.diretorio)
        piloto._registrar(outra, "confirmado", "diretor", erp.diretorio, id_criado=800 + n)
    with pytest.raises(piloto.PilotoErro, match="1.000,00"):
        await confirmar(erp)
    assert not erp.requests


@pytest.mark.parametrize("conteudo", [
    "WEBPOSTO_WRITES=${LIBERAR}\nLOGOS_ERP_ESCRITA=1\n",
    "export WEBPOSTO_WRITES=1\nexport WEBPOSTO_WRITES=1\nLOGOS_ERP_ESCRITA=1\n",
    "WEBPOSTO_WRITES='1'\nLOGOS_ERP_ESCRITA=1\nLOGOS_ERP_ESCRITA=1\n",
])
def test_travas_nao_interpolam_e_detectam_export_duplicado(tmp_path, monkeypatch, conteudo):
    env = tmp_path / ".env"
    env.write_text(conteudo, encoding="utf-8")
    monkeypatch.setenv("LIBERAR", "1")
    assert escrita.verificar_travas_cartao(env)[0] is False


@pytest.mark.asyncio
async def test_sem_id_da_resposta_recupera_somente_novo_cartao_compativel(erp, monkeypatch):
    incluir = escrita.incluir_cartao
    async def sem_id(*args, **kwargs):
        resultado = await incluir(*args, **kwargs)
        return {**resultado, "id_criado": None}
    monkeypatch.setattr(escrita, "incluir_cartao", sem_id)
    assert (await confirmar(erp))["estado"] == "confirmado"
    assert erp.requests == ["POST"]


@pytest.mark.asyncio
async def test_timeout_do_post_nao_repete_nem_exclui_id_desconhecido(erp, monkeypatch):
    monkeypatch.setattr(escrita, "incluir_cartao", AsyncMock(side_effect=httpx.ReadTimeout("Não exibir URL")))
    with pytest.raises(piloto.PilotoErro, match="não repita"):
        await confirmar(erp)
    assert not erp.requests
    assert piloto.historico(74014, DIA, diretorio=erp.diretorio)[-1]["estado"] == "incerto"


@pytest.mark.asyncio
async def test_resumo_do_diretor_inclui_so_cartoes_confirmados(erp, monkeypatch):
    from .test_pendencias import criar_diario
    from src.modules.cash_reconciliation.application.resumo_diario import gerar_resumo_diario
    await confirmar(erp)
    r = criar_diario(DIA, 74014)
    # Leitura padrão do resumo aponta para a auditoria temporária deste caso.
    monkeypatch.setattr(escrita, "DIRETORIO_AUDITORIA_PADRAO", erp.diretorio)
    texto = gerar_resumo_diario(DIA, [r], [74014], set(), {74014: 0})
    assert "Lancei 1 cartão · R$ 34,75" in texto


@pytest.fixture
def telegram_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_DIRETOR_CHAT_ID=123\nTELEGRAM_DIRETOR_USER_ID=123\n", encoding="utf-8")
    return env


@pytest.mark.asyncio
async def test_telegram_envia_texto_e_botoes_somente_ao_diretor(caso, telegram_env, tmp_path, monkeypatch):
    p = proposta(caso)
    monkeypatch.setattr(piloto, "preparar", AsyncMock(return_value=[p]))
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200, json={"ok": True, "result": {}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await telegram_cartoes.enviar_propostas(74014, DIA, token="TOKEN-FAKE", caminho_env=telegram_env,
                                                banco=tmp_path / "telegram.db", client=client)
    import json
    dados = json.loads(requests[0].content)
    assert dados["chat_id"] == "123" and dados["text"] == p.texto
    botoes = dados["reply_markup"]["inline_keyboard"][0]
    assert [b["text"] for b in botoes] == [f"Lançar · {p.caixa_curto}", "Não lançar"]
    assert "caixa 201" not in dados["text"]
    assert "201" not in botoes[0]["text"]
    assert all(len(b["callback_data"].encode()) <= 64 for b in botoes)


@pytest.mark.asyncio
@pytest.mark.parametrize("estranho", [False, True])
async def test_callback_privado_um_toque_e_repeticao(telegram_env, tmp_path, monkeypatch, estranho):
    banco = tmp_path / "telegram.db"
    with telegram_cartoes._conectar(banco) as con:
        con.execute("INSERT INTO propostas VALUES(?,?,?,?,?,?)",
                    ("ticket", 74014, str(DIA), "id-sintetico", (agora() + timedelta(hours=1)).isoformat(), "pendente"))
    decidir = AsyncMock(return_value={"estado": "confirmado", "mensagem": "Conferido"})
    monkeypatch.setattr(piloto, "decidir", decidir)
    callback = {"from": {"id": 999 if estranho else 123},
                "message": {"chat": {"id": 123, "type": "private"}}, "data": "cartao:s:ticket"}
    if estranho:
        with pytest.raises(piloto.PilotoErro, match="diretor"):
            await telegram_cartoes.processar_callback(callback, caminho_env=telegram_env, banco=banco)
        decidir.assert_not_called()
    else:
        assert (await telegram_cartoes.processar_callback(callback, caminho_env=telegram_env, banco=banco))["estado"] == "confirmado"
        assert decidir.await_args.args[:4] == (74014, DIA, "id-sintetico", "aprovar")
        with pytest.raises(piloto.PilotoErro, match="já foi decidida"):
            await telegram_cartoes.processar_callback(callback, caminho_env=telegram_env, banco=banco)
        assert decidir.await_count == 1


@pytest.mark.asyncio
async def test_http_perfil_e_mesmo_caminho_de_aprovacao(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.modules.cash_reconciliation.interfaces import http
    from src.interfaces.http.dependencies import get_current_user
    app = FastAPI()
    app.include_router(http.router)
    usuario = {"role": "diretor", "sub": "diretor-sintetico"}
    app.dependency_overrides[get_current_user] = lambda: usuario
    monkeypatch.setattr(http, "require_unit_access", lambda *a: None)
    decidir = AsyncMock(return_value={"estado": "confirmado", "mensagem": "Conferido"})
    monkeypatch.setattr(piloto, "decidir", decidir)
    with TestClient(app) as client:
        for role in ("gerente", "auditor", "tv"):
            usuario["role"] = role
            for acao in ("aprovar", "recusar", "desfazer"):
                assert client.post(f"/api/v1/cash-audit/lancamentos-logos/id/{acao}",
                                   json={"unidade": 74014, "dia": str(DIA)}).status_code == 403
        decidir.assert_not_called()
        usuario["role"] = "diretor"
        response = client.post("/api/v1/cash-audit/lancamentos-logos/id/aprovar", json={"unidade": 74014, "dia": str(DIA)})
        assert response.status_code == 200
        assert decidir.await_count == 1
