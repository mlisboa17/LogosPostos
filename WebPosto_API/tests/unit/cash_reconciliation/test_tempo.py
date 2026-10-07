import logging
import re
import runpy
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from src.modules.cash_reconciliation.application.auditar_fechamento import auditar
from src.modules.cash_reconciliation.application.conciliar import conciliar as conciliar_depositos
from src.modules.cash_reconciliation.application.conciliar_cartoes import conciliar
from src.modules.cash_reconciliation import config
from src.modules.cash_reconciliation.adapters import persistencia
from src.modules.cash_reconciliation.adapters.webposto_cartoes import buscar_contexto_vendas, para_abastecimento
from src.modules.cash_reconciliation.domain import tempo
from src.modules.cash_reconciliation.domain.models import DepositoBancario, Proveniencia, Sangria, Unidade
from src.modules.cash_reconciliation.jobs import noturno

FUSO = tempo.FUSO
DIA = date(2026, 10, 5)


def test_ontem_na_virada_utc(monkeypatch):
    instante_utc = datetime(2026, 10, 8, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(tempo, "time", lambda: instante_utc.timestamp())
    assert tempo.agora() == datetime(2026, 10, 7, 22, tzinfo=FUSO)
    assert tempo.hoje() == date(2026, 10, 7)
    assert tempo.ontem() == date(2026, 10, 6)
    assert tempo.agora().tzinfo == FUSO


def test_converte_z_para_recife_sem_descartar_fuso():
    local = tempo.ler_data_hora("2026-10-05T03:28:48Z")
    assert local == datetime(2026, 10, 5, 0, 28, 48, tzinfo=FUSO)
    assert local.utcoffset() == timedelta(hours=-3)


def test_sem_fuso_preserva_horario():
    original = datetime(2026, 10, 5, 14, 5, 30)
    local = tempo.para_local(original)
    assert (local.hour, local.minute, local.second) == (14, 5, 30)
    assert local.tzinfo == FUSO


def test_formatadores_brasil():
    valor = datetime(2026, 10, 7, 17, 5, tzinfo=timezone.utc)
    assert tempo.formatar_data(date(2026, 10, 7)) == "07/10/2026"
    assert tempo.formatar_hora(valor) == "14:05"
    assert tempo.formatar_data_hora(valor) == "07/10/2026 14:05"
    assert tempo.formatar_data(datetime(2026, 10, 8, 1, tzinfo=timezone.utc)) == "07/10/2026"


@pytest.mark.parametrize("texto", ["07/10/2026", "2026-10-07"])
def test_ler_data_e_cli_aceitam_dois_formatos(texto):
    assert tempo.ler_data(texto) == noturno._dia(texto) == date(2026, 10, 7)


@pytest.mark.parametrize("texto", ["31/02/2026", "2026-02-30", "07/10/26", "invalida", "7/10/2026"])
def test_data_invalida_erro_portugues(texto):
    with pytest.raises(ValueError, match="Data inválida"):
        tempo.ler_data(texto)


def test_todas_proveniencias_tem_fuso():
    dia = date(2026, 10, 5)
    unidade = Unidade(empresa_codigo=321, nome="Sintetica", chave_env="TESTE", destinos=())
    resultados = [
        auditar(321, [], {}, [], dia, dia),
        conciliar(321, "PAGBANK", dia, [], [], [], set()),
        conciliar_depositos(unidade, [], {}, dia, dia),
    ]
    for resultado in resultados:
        assert resultado.proveniencia.executado_em.tzinfo == FUSO
        assert resultado.model_dump(mode="json")["proveniencia"]["executado_em"].endswith("-03:00")


def test_proveniencia_historica_sem_fuso_normalizada():
    prov = Proveniencia(
        execucao_id="sintetica", executado_em="2026-10-07T14:05:00",
        versao_regra="TESTE", fonte_sangrias="", extratos=(),
    )
    assert prov.model_dump(mode="json")["executado_em"] == "2026-10-07T14:05:00-03:00"


def test_abastecimento_utc_muda_data_quando_necessario():
    abastecimento = para_abastecimento({
        "abastecimentoCodigo": 1, "empresaCodigo": 321, "dataHoraAbastecimento": "2026-10-06T01:28:48Z",
        "valorTotal": 10, "codigoFrentista": 1, "vendaItemCodigo": 1,
    })
    assert abastecimento.momento == datetime(2026, 10, 5, 22, 28, 48, tzinfo=FUSO)


async def test_pix_utc_convertido_e_hora_preservada(monkeypatch):
    unidade = Unidade(empresa_codigo=321, nome="Sintetica", chave_env="TESTE", destinos=())
    monkeypatch.setenv("TESTE", "chave-sintetica")

    def handler(req):
        if req.url.path.endswith("/VENDAS"):
            rows = [{"empresaCodigo": 321, "vendaCodigo": 1, "dataHora": "2026-10-05T03:28:48Z", "cancelada": "N"}]
        elif req.url.path.endswith("/VENDAS_FORMA_PAGAMENTO"):
            rows = [{"empresaCodigo": 321, "vendaCodigo": 1, "tipoFormaPagamento": "B", "valorPagamento": 10}]
        else:
            rows = []
        return httpx.Response(200, json={"resultados": rows, "ultimoCodigo": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://sintetico.invalid") as client:
        _, pix = await buscar_contexto_vendas(unidade, DIA, DIA, client=client)
    assert pix[0].momento == datetime(2026, 10, 5, 0, 28, 48, tzinfo=FUSO)


def test_deposito_sem_hora_tem_referencia_local():
    deposito = DepositoBancario(
        fitid="sintetico", banco="TESTE", conta="TESTE", valor="10", data=DIA, momento=None, canal="outro",
    )
    assert deposito.referencia == datetime(2026, 10, 5, 0, tzinfo=FUSO)


def test_alerta_sangria_usa_hora_recife_sem_alterar_regra():
    from .test_fechamento import caixa
    from src.modules.cash_reconciliation.rules.fechamento import auditar_caixa

    sangria = Sangria(
        codigo=1, empresa_codigo=5555, caixa_codigo=1, conta_codigo=None, funcionario_codigo=1,
        valor="10", momento="2026-10-05T17:05:00Z",
    )
    resultado = auditar_caixa(caixa(), (), [sangria])
    assert "às 14:05" in resultado.alertas[0].mensagem


def test_log_noturno_exibe_data_hora_brasil():
    instante = datetime(2026, 10, 8, 1, tzinfo=timezone.utc)
    record = logging.LogRecord("sintetico", logging.INFO, "", 0, "mensagem", (), None)
    record.created = instante.timestamp()
    assert noturno.FormatoLogBrasil("%(asctime)s %(message)s").format(record) == "07/10/2026 22:00 mensagem"


def test_modulo_nao_permite_relogios_sem_helper_ou_descarte_de_fuso():
    modulo = Path(tempo.__file__).resolve().parents[1]
    proibido = re.compile(r"\bdatetime\.now\s*\(|\bdate\.today\s*\(|\butcnow\s*\(|\.replace\s*\(\s*tzinfo\s*=\s*None")
    encontrados = [
        str(caminho.relative_to(modulo))
        for caminho in modulo.rglob("*.py")
        if proibido.search(caminho.read_text(encoding="utf-8"))
    ]
    assert encontrados == []


def test_cli_como_main_grava_resumo_brasileiro_sem_rede(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBPOSTO_WRITES", "0")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args: None)
    monkeypatch.setattr(config, "carregar_unidades", lambda: {})
    monkeypatch.setattr(persistencia, "DIRETORIO", tmp_path)
    monkeypatch.setattr(sys, "argv", ["noturno", "--dia", "06/10/2026"])
    modulo_logger = logging.getLogger("src.modules.cash_reconciliation")
    monkeypatch.setattr(modulo_logger, "level", modulo_logger.level)
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        with pytest.raises(SystemExit) as saida:
            runpy.run_module(noturno.__name__, run_name="__main__")
    assert saida.value.code == 0
    resumo = (tmp_path / "noturno.log").read_text(encoding="utf-8")
    assert re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2} INFO ", resumo)
    assert "Execucao terminada dia=06/10/2026 unidades_com_falha=0" in resumo
