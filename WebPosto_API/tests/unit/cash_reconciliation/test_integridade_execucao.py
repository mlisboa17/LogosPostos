from datetime import date, timedelta
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest

from src.jobs import noturno as composicao
from src.modules.cash_reconciliation.adapters import saude_robo, pagbank_edi
from src.modules.cash_reconciliation.application import fontes_falta
from src.modules.cash_reconciliation.domain.execucao import ResultadoDiario
from src.modules.cash_reconciliation.domain.fechamento import ResultadoAuditoria
from src.modules.cash_reconciliation.domain.explicacao import ConferenciaMais
from src.modules.cash_reconciliation.domain.integridade_execucao import ExecucaoNoturna, FonteExecucao
from src.modules.cash_reconciliation.domain.models import Proveniencia, Unidade
from src.modules.cash_reconciliation.domain.recebimentos import ResultadoRecebimentos
from src.modules.cash_reconciliation.domain.recebimentos import RecebimentoAdquirente, ResumoCasados
from src.modules.cash_reconciliation.domain.tempo import agora
from src.modules.cash_reconciliation.jobs import noturno
from src.modules.webposto_integration.http import paginar, WebPostoErro

DIA = date(2026, 10, 14)
CODIGO = 321


def fonte(execucao, **updates):
    valores = dict(
        nome="fechamento", unidade=CODIGO, dia=execucao.dia, run_id=execucao.run_id,
        coletado_em=agora(), cobertura_inicio=execucao.dia, cobertura_fim=execucao.dia,
        estado="SUCCESS", permite_vazio=True,
    )
    valores.update(updates)
    return FonteExecucao(**valores)


def registro(execucao):
    proveniencia = Proveniencia(
        execucao_id=execucao.run_id, executado_em=agora(), versao_regra="sintetica",
        fonte_sangrias="", extratos=(), outras_fontes=(),
    )
    return ResultadoDiario(
        empresa_codigo=CODIGO, dia=execucao.dia,
        fechamento=ResultadoAuditoria(
            empresa_codigo=CODIGO, inicio=execucao.dia, fim=execucao.dia,
            caixas=(), proveniencia=proveniencia,
        ),
        recebimentos=ResultadoRecebimentos(empresa_codigo=CODIGO, dia=execucao.dia, adquirentes=()),
        proveniencia=proveniencia, versoes_regras=(), fontes_execucao=(fonte(execucao),),
    )


@pytest.fixture
def isolado(monkeypatch, tmp_path):
    unidade = Unidade(empresa_codigo=CODIGO, nome="Posto sintético", chave_env="TESTE_CHAVE", destinos=())
    monkeypatch.setenv("WEBPOSTO_WRITES", "0")
    monkeypatch.setenv("LOGOS_CARTAO_AUTOMATICO", "0")
    monkeypatch.setattr(noturno, "carregar_unidades", lambda: {CODIGO: unidade})
    monkeypatch.setattr(composicao, "carregar_unidades", lambda: {CODIGO: unidade})
    monkeypatch.setattr(saude_robo, "DIRETORIO_RESUMOS", tmp_path / "resumos")
    monkeypatch.setattr(saude_robo, "CAMINHO_ESTADO", tmp_path / "resumos" / "estado_robo.json")
    monkeypatch.setattr(noturno, "pendencias_do_dia", lambda r: [])
    monkeypatch.setattr(noturno, "executar_reincidencia_mes", lambda *a, **k: [])
    monkeypatch.setattr(noturno.repositorio_pendencias, "contar_abertas_somente_leitura", lambda **k: 0)

    async def anexar(r, u):
        return r

    monkeypatch.setattr(fontes_falta, "anexar_fontes_falta", anexar)
    return unidade


@pytest.mark.parametrize("estado", ["SUCCESS", "EMPTY_VALID"])
def test_sucesso_e_vazio_validado_permite_publicacao(estado):
    run = ExecucaoNoturna(dia=DIA)
    run.registrar(fonte(run, estado=estado))
    assert not run.permite_publicacao()
    run.finalizar()
    assert run.audit_status == "AUDIT_COMPLETE"
    assert run.permite_publicacao()


@pytest.mark.parametrize("estado", ["FAILED", "BLOCKED", "NOT_COLLECTED", "STALE"])
def test_fonte_obrigatoria_invalida_bloqueia(estado):
    run = ExecucaoNoturna(dia=DIA)
    run.registrar(fonte(run, estado=estado))
    run.finalizar()
    assert run.audit_status == "AUDIT_FAILED"
    assert not run.permite_publicacao()
    aviso = run.aviso_operacional({CODIGO: "Posto sintético"})
    assert estado in aviso and "não emitiu conclusão financeira" in aviso
    assert "R$" not in aviso


def test_vazio_sem_contrato_nao_e_sucesso():
    run = ExecucaoNoturna(dia=DIA)
    run.registrar(fonte(run, estado="EMPTY_VALID", permite_vazio=False))
    run.finalizar()
    assert run.fontes[0].estado == "FAILED"


@pytest.mark.parametrize("mudanca", ["run", "hora", "dia", "cobertura", "sem_timestamp"])
def test_evidencia_antiga_ou_sem_cobertura_e_stale(mudanca):
    run = ExecucaoNoturna(dia=DIA)
    updates = {
        "run": {"run_id": "run-anterior"},
        "hora": {"coletado_em": run.iniciado_em - timedelta(seconds=1)},
        "dia": {"dia": DIA - timedelta(days=1)},
        "cobertura": {"cobertura_fim": DIA - timedelta(days=1)},
        "sem_timestamp": {"coletado_em": None},
    }[mudanca]
    original = fonte(run, **updates)
    run.registrar(original)
    run.finalizar()
    assert run.fontes[0].estado == "STALE"
    assert run.fontes[0].run_id == original.run_id
    assert run.fontes[0].coletado_em == original.coletado_em
    assert not run.permite_publicacao()


def test_parcial_e_opcional_nao_inventa_obrigacao():
    run = ExecucaoNoturna(dia=DIA)
    run.fontes = [fonte(run), fonte(run, nome="PAGBANK", estado="FAILED")]
    run.finalizar()
    assert run.audit_status == "AUDIT_PARTIAL"
    run.registrar(fonte(run, nome="PAGBANK", estado="FAILED", obrigatoria=False))
    assert run.permite_publicacao()


@pytest.mark.parametrize("antigo", [True, False])
async def test_snapshot_do_mesmo_dia_exige_run_corrente(monkeypatch, tmp_path, isolado, antigo):
    run = ExecucaoNoturna(dia=DIA)
    outro = ExecucaoNoturna(dia=DIA)
    resultado = registro(outro if antigo else run)
    chamadas = []

    async def coletar(*args, **kwargs):
        return resultado

    monkeypatch.setattr(noturno, "coletar_unidade", coletar)
    monkeypatch.setattr(noturno, "gerar_resumo_diario", lambda *a: chamadas.append(True) or "FINANCEIRO")
    saida = await noturno.executar(DIA, diretorio=tmp_path / "snapshots", execucao=run)
    assert saida == (1 if antigo else 0)
    assert bool(chamadas) is not antigo
    assert run.audit_status == ("AUDIT_FAILED" if antigo else "AUDIT_COMPLETE")
    assert ("FINANCEIRO" in saude_robo.caminho_resumo(DIA).read_text(encoding="utf-8")) is not antigo


async def test_cache_existente_nao_substitui_coleta_falha(monkeypatch, tmp_path, isolado):
    from src.modules.cash_reconciliation.adapters.persistencia import salvar_dia
    run = ExecucaoNoturna(dia=DIA)
    historico = registro(ExecucaoNoturna(dia=DIA))
    caminho = salvar_dia(historico, diretorio=tmp_path / "snapshots")
    original = caminho.read_bytes()

    async def falhar(*a, **k):
        raise RuntimeError("detalhe privado")

    monkeypatch.setattr(noturno, "coletar_unidade", falhar)
    monkeypatch.setattr(noturno, "gerar_resumo_diario", lambda *a: pytest.fail("Resumo financeiro proibido"))
    assert await noturno.executar(DIA, diretorio=tmp_path / "snapshots", execucao=run) == 1
    assert caminho.read_bytes() == original
    assert not run.permite_publicacao()
    assert "detalhe privado" not in run.model_dump_json()


@pytest.mark.parametrize("writes,automatico", [
    (None, "0"), ("", "0"), ("1", "0"), ("inválido", "0"), ("0", "1"), ("0", "inválido"),
])
async def test_configuracao_bloqueada_sem_coleta(monkeypatch, tmp_path, isolado, writes, automatico):
    if writes is None:
        monkeypatch.delenv("WEBPOSTO_WRITES", raising=False)
    else:
        monkeypatch.setenv("WEBPOSTO_WRITES", writes)
    monkeypatch.setenv("LOGOS_CARTAO_AUTOMATICO", automatico)
    monkeypatch.setattr(noturno, "coletar_unidade", lambda *a, **k: pytest.fail("Não deve coletar"))
    run = ExecucaoNoturna(dia=DIA)
    assert await noturno.executar(DIA, diretorio=tmp_path / "snapshots", execucao=run) == 1
    assert run.fontes[0].estado == "BLOCKED"
    assert "BLOCKED_CONFIG" in run.aviso_operacional({})
    assert not (tmp_path / "snapshots").exists()
    salvo = ExecucaoNoturna.model_validate_json(
        (tmp_path / "resumos" / "execucoes" / f"{run.run_id}.json").read_text(encoding="utf-8")
    )
    assert salvo.run_id == run.run_id and salvo.terminado_em is not None
    assert not saude_robo.carregar_estado().resumo_gerado


async def test_coleta_vazia_valida_vem_de_consulta_executada(monkeypatch, isolado):
    run = ExecucaoNoturna(dia=DIA)
    resultado = registro(run)

    async def auditar(*a):
        return resultado.fechamento

    monkeypatch.setattr(noturno, "auditar_unidade", auditar)
    coletado = await noturno.coletar_unidade(isolado, DIA, run.run_id)
    fonte_caixa = coletado.fontes_execucao[0]
    assert fonte_caixa.estado == "EMPTY_VALID" and fonte_caixa.permite_vazio
    assert fonte_caixa.run_id == run.run_id and fonte_caixa.coletado_em >= run.iniciado_em


@pytest.mark.parametrize("completo,sucesso", [(False, True), (False, False), (True, False), (True, True)])
def test_delivery_nao_altera_auditoria(monkeypatch, tmp_path, isolado, completo, sucesso):
    run = ExecucaoNoturna(dia=DIA)
    resultado = registro(run)
    run.fontes = [fonte(run, estado="SUCCESS" if completo else "FAILED")]
    if not completo:
        resultado = resultado.model_copy(update={"fontes_execucao": tuple(run.fontes)})
    run.finalizar()
    estado_inicial = run.audit_status
    textos = []
    documentos = []
    monkeypatch.setenv("TELEGRAM_ENVIO", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "sintetico")
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "11")
    monkeypatch.setattr(composicao, "_coletar_dados_telegram",
                        lambda *a: {} if completo else pytest.fail("Não deve compor"))
    monkeypatch.setattr(composicao, "_mensagens_telegram", lambda *a: ["FINANCEIRO"])
    monkeypatch.setattr(composicao, "_criar_planilha_telegram",
                        lambda *a: tmp_path / "sintetica.xlsx" if completo else pytest.fail("Sem XLSX"))

    def enviar(texto, **k):
        textos.append(texto)
        return [SimpleNamespace(sucesso=sucesso, status_http=None, tipo_erro="sintetico")]

    monkeypatch.setattr(composicao, "enviar_mensagem", enviar)
    monkeypatch.setattr(composicao, "enviar_documento",
                        lambda *a, **k: documentos.append(True) or [SimpleNamespace(sucesso=True)])
    ledger = tmp_path / "envios.json"
    composicao._tentar_envio_telegram(
        DIA, dia_manual=True, enviar_manual=True, reenviar=False,
        caminho_registro=ledger, execucao=run, resultados=[resultado],
    )
    assert run.audit_status == estado_inicial
    assert run.delivery_status == ("DELIVERY_SUCCESS" if sucesso else "DELIVERY_FAILED")
    assert bool(documentos) is completo
    assert ("FINANCEIRO" in textos[0]) is completo
    assert run.run_id in ledger.read_text(encoding="utf-8")


def test_metadata_ausente_e_lista_incompleta_reprovam_publicacao():
    run = ExecucaoNoturna(dia=DIA)
    resultado = registro(run)
    run.fontes = [fonte(run)]
    run.finalizar()
    noturno.validar_registros(run, [resultado.model_copy(update={"fontes_execucao": ()})])
    assert not run.permite_publicacao()
    run.fontes = [fonte(run)]
    noturno.validar_registros(run, [])
    assert not run.permite_publicacao()


def test_composicao_telegram_usa_resultado_em_memoria_nao_snapshot(monkeypatch, isolado):
    run = ExecucaoNoturna(dia=DIA)
    atual = registro(run)
    run.fontes = list(atual.fontes_execucao)
    run.finalizar()
    monkeypatch.setattr(composicao.persistencia_caixa, "carregar_dia",
                        lambda *a, **k: pytest.fail("Não deve recarregar snapshot do dia"))
    monkeypatch.setattr(composicao.repositorio_pendencias, "contar_vencidas_somente_leitura", lambda **k: 0)
    dados = composicao._coletar_dados_telegram(DIA, [atual], run)
    assert dados["resultados"][0].proveniencia.execucao_id == run.run_id


@pytest.mark.parametrize("payload", [{}, {"resultados": None}, [], {"resultados": [None]}])
async def test_webposto_payload_invalido_nao_e_vazio_valido(monkeypatch, isolado, payload):
    monkeypatch.setenv("TESTE_CHAVE", "sintetica")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
        base_url="https://sintetico.invalid",
    ) as client:
        with pytest.raises(WebPostoErro):
            await paginar(isolado, "/sintetico", {}, client=client)


async def test_webposto_vazio_explicito_e_valido(monkeypatch, isolado):
    monkeypatch.setenv("TESTE_CHAVE", "sintetica")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"resultados": []})),
        base_url="https://sintetico.invalid",
    ) as client:
        assert await paginar(isolado, "/sintetico", {}, client=client) == []


@pytest.mark.parametrize("payload", [{}, {"detalhes": None}, []])
async def test_pagbank_payload_invalido_nao_e_vazio(monkeypatch, payload):
    monkeypatch.setenv(f"PAGBANK_USER_{CODIGO}", "sintetico")
    monkeypatch.setenv(f"PAGBANK_TOKEN_{CODIGO}", "sintetico")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
        base_url="https://sintetico.invalid",
    ) as client:
        with pytest.raises(pagbank_edi.PagBankErro):
            await pagbank_edi.buscar_transacoes(CODIGO, DIA, client=client)


def test_bootstrap_dotenv_independe_do_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    esperado = Path(composicao.__file__).resolve().parents[2] / ".env"
    assert composicao.CAMINHO_ENV == esperado and esperado.is_absolute()


def test_legado_permanece_legivel_mas_nao_prova_execucao_atual():
    run = ExecucaoNoturna(dia=DIA)
    payload = registro(run).model_dump(mode="json")
    payload.pop("fontes_execucao")
    legado = ResultadoDiario.model_validate(payload)
    assert legado.fontes_execucao == ()
    run.fontes = [fonte(run, estado="NOT_COLLECTED")]
    noturno.validar_registros(run, [legado])
    run.finalizar()
    assert not run.permite_publicacao()


def test_premmia_historico_nao_e_recarimbado_nem_publica_valores():
    run = ExecucaoNoturna(dia=DIA)
    resultado = registro(run)
    anterior = run.iniciado_em - timedelta(days=1)
    premmia = fonte(run, nome="PREMMIA", obrigatoria=False, coletado_em=anterior, origem="arquivo_mensal")
    resultado = resultado.model_copy(update={
        "fontes_execucao": (*resultado.fontes_execucao, premmia),
        "recebimentos": resultado.recebimentos.model_copy(update={"adquirentes": (
            RecebimentoAdquirente(adquirente="PREMMIA", situacao="ok",
                                  casados=ResumoCasados(quantidade=1, total="123.45")),
        )}),
    })
    run.fontes = list(resultado.fontes_execucao)
    run.finalizar()
    atual, = noturno.registros_para_publicacao(run, [resultado])
    item, = atual.recebimentos.adquirentes
    assert run.audit_status == "AUDIT_COMPLETE"
    assert item.situacao == "pendente" and item.casados is None
    assert "STALE" in item.erro
    assert run.fontes[-1].coletado_em == anterior
    assert str(resultado.recebimentos.adquirentes[0].casados.total) == "123.45"


@pytest.mark.parametrize("completo", [True, False])
def test_main_persiste_mesmo_run_antes_e_depois_do_envio(monkeypatch, tmp_path, isolado, completo):
    monkeypatch.setattr(sys, "argv", ["noturno", "--dia", "14/10/2026", "--enviar-telegram"])
    monkeypatch.setattr(composicao.persistencia_caixa, "DIRETORIO", tmp_path / "snapshots")
    chamadas_env = []
    monkeypatch.setattr(composicao, "load_dotenv", lambda path, **kw: chamadas_env.append((path, kw)))
    vistos = []

    async def executar(dia, **kwargs):
        run = kwargs["execucao"]
        assert (tmp_path / "resumos" / "execucoes" / f"{run.run_id}.json").exists()
        atual = registro(run)
        run.fontes = [fonte(run, estado="SUCCESS" if completo else "FAILED")]
        atual = atual.model_copy(update={"fontes_execucao": tuple(run.fontes)})
        kwargs["resultados_execucao"].append(atual)
        run.finalizar()
        return 0 if completo else 1

    def enviar(dia, *, execucao, resultados, **kwargs):
        vistos.append(execucao.run_id)
        assert resultados[0].proveniencia.execucao_id == execucao.run_id
        execucao.delivery_status = "DELIVERY_SUCCESS"

    monkeypatch.setattr(composicao, "executar", executar)
    monkeypatch.setattr(composicao, "_tentar_envio_telegram", enviar)
    assert composicao.main() == (0 if completo else 1)
    assert chamadas_env == [(composicao.CAMINHO_ENV, {"override": False})]
    salvo = ExecucaoNoturna.model_validate_json(
        (tmp_path / "resumos" / "execucoes" / f"{vistos[0]}.json").read_text(encoding="utf-8")
    )
    assert salvo.audit_status == ("AUDIT_COMPLETE" if completo else "AUDIT_FAILED")
    assert salvo.delivery_status == "DELIVERY_SUCCESS"


async def test_cursor_repetido_nao_finge_cobertura_completa(monkeypatch, isolado):
    monkeypatch.setenv("TESTE_CHAVE", "sintetica")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json={"resultados": [{"codigo": 1}], "ultimoCodigo": 1},
        )), base_url="https://sintetico.invalid",
    ) as client:
        with pytest.raises(WebPostoErro, match="cursor"):
            await paginar(isolado, "/sintetico", {}, client=client)


@pytest.mark.parametrize("payload", [
    {"detalhes": [], "pagination": {"totalPages": 2}},
    {"detalhes": [{}], "pagination": {"totalPages": 0}},
    {"detalhes": [{}]},
])
async def test_pagbank_nao_aceita_cobertura_incompleta(monkeypatch, payload):
    monkeypatch.setenv(f"PAGBANK_USER_{CODIGO}", "sintetico")
    monkeypatch.setenv(f"PAGBANK_TOKEN_{CODIGO}", "sintetico")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
        base_url="https://sintetico.invalid",
    ) as client:
        with pytest.raises(pagbank_edi.PagBankErro):
            await pagbank_edi.buscar_transacoes(CODIGO, DIA, client=client)


@pytest.mark.parametrize("etapa", ["resumo", "estado"])
async def test_falha_de_persistencia_nao_deixa_resumo_normal(monkeypatch, tmp_path, isolado, etapa):
    run = ExecucaoNoturna(dia=DIA)

    async def coletar(*a, **k):
        return registro(run)

    monkeypatch.setattr(noturno, "coletar_unidade", coletar)
    monkeypatch.setattr(noturno, "gerar_resumo_diario", lambda *a: "FINANCEIRO")
    original = saude_robo.salvar_resumo
    tentativas = []

    def salvar_resumo(*a, **k):
        if etapa == "resumo" and not tentativas:
            tentativas.append(True)
            raise saude_robo.PersistenciaEstadoErro("sintetico")
        return original(*a, **k)

    def salvar_estado(*a, **k):
        raise saude_robo.PersistenciaEstadoErro("sintetico")

    monkeypatch.setattr(saude_robo, "salvar_resumo", salvar_resumo)
    if etapa == "estado":
        monkeypatch.setattr(saude_robo, "salvar_estado", salvar_estado)
    assert await noturno.executar(DIA, diretorio=tmp_path / "snapshots", execucao=run) == 1
    assert not run.permite_publicacao()
    texto = saude_robo.caminho_resumo(DIA).read_text(encoding="utf-8")
    assert "FINANCEIRO" not in texto and "AUDITORIA NÃO CONCLUÍDA" in texto


@pytest.mark.parametrize("etapa", ["documento", "ledger"])
def test_erro_apos_entrega_preserva_sucesso_real_da_mensagem(monkeypatch, tmp_path, isolado, etapa):
    run = ExecucaoNoturna(dia=DIA)
    atual = registro(run)
    run.fontes = list(atual.fontes_execucao)
    run.finalizar()
    monkeypatch.setenv("TELEGRAM_ENVIO", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "sintetico")
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "11")
    monkeypatch.setattr(composicao, "_coletar_dados_telegram", lambda *a: {})
    monkeypatch.setattr(composicao, "_mensagens_telegram", lambda *a: ["FINANCEIRO"])
    monkeypatch.setattr(composicao, "_criar_planilha_telegram", lambda *a: tmp_path / "sintetica.xlsx")
    monkeypatch.setattr(composicao, "enviar_mensagem",
                        lambda *a, **k: [SimpleNamespace(sucesso=True)])

    def falhar(*a, **k):
        raise OSError("privado")

    monkeypatch.setattr(composicao, "enviar_documento",
                        falhar if etapa == "documento" else lambda *a, **k: [SimpleNamespace(sucesso=True)])
    if etapa == "ledger":
        monkeypatch.setattr(composicao, "_registrar_envio_telegram", falhar)
    composicao._tentar_envio_telegram(
        DIA, dia_manual=True, enviar_manual=True, reenviar=False, execucao=run,
        resultados=[atual], caminho_registro=tmp_path / "envios.json",
    )
    assert run.audit_status == "AUDIT_COMPLETE"
    assert run.delivery_status == "DELIVERY_SUCCESS"
    assert run.document_delivery_status == ("DELIVERY_FAILED" if etapa == "documento" else "DELIVERY_SUCCESS")
    assert run.erro_publicacao and "privado" not in run.erro_publicacao


async def test_aviso_de_atribuicao_nao_invalida_declaracao_mais(monkeypatch, isolado):
    run = ExecucaoNoturna(dia=DIA)
    atual = registro(run)
    declarado_em = run.iniciado_em - timedelta(days=1)

    async def auditar(*a):
        return atual.fechamento

    async def anexar(r, u):
        return r.model_copy(update={"mais_pagamentos": ConferenciaMais(
            total="10.00", webposto="8.00", informado_em=declarado_em,
            aviso="Total do dia não identifica o caixa; conferir à mão.",
        )})

    monkeypatch.setattr(noturno, "auditar_unidade", auditar)
    monkeypatch.setattr(fontes_falta, "anexar_fontes_falta", anexar)
    coletado = await noturno.coletar_unidade(isolado, DIA, run.run_id)
    mais = next(f for f in coletado.fontes_execucao if f.nome == "MAIS_TOTAL")
    assert mais.estado == "SUCCESS" and not mais.obrigatoria
    assert mais.origem == "declaracao_local" and mais.referencia_em == declarado_em
