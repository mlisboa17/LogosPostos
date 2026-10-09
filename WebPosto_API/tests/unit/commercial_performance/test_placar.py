import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.modules.commercial_performance.adapters import webposto
from src.modules.commercial_performance.application import placar
from src.modules.commercial_performance.config import MetasErro, POSTOS, ler_metas
from src.modules.commercial_performance.domain.models import Abastecimento, MetasPosto, Produto, Proveniencia
from src.modules.commercial_performance.rules.placar import calcular, referencia
from src.modules.webposto_integration.http import WebPostoErro

DIA = date(2026, 10, 2)
PROV = Proveniencia(executado_em=datetime(2026, 10, 2, 12), execucao_id="sintetico",
                    versao_regra="PLACAR_V1", fontes=("sintetica",), metas_cadastradas=False)
PRODUTOS = {1: Produto(codigo=1, nome="Gasolina comum sintetica", aditivado=False),
            2: Produto(codigo=2, nome="Gasolina aditivada sintetica", aditivado=True)}


def abastecimento(codigo, dia, litros=10, frentista=7, venda=None, produto=1, posto=11495):
    return Abastecimento(codigo=codigo, empresa_codigo=posto, momento=datetime(2026, 10, dia, 10),
                         litros=litros, produto=produto, frentista=frentista, venda=venda)


def calcular_teste(linhas=(), metas=None, dia=DIA, hoje=DIA, produtos=PRODUTOS):
    return calcular(11495, "2026-10", dia, hoje, linhas, produtos, {}, metas, PROV)


def test_atendimento_venda_distinta_fallback_ticket_e_isolamento():
    resultado = calcular_teste([
        abastecimento(1, 1, 10, venda=10), abastecimento(2, 1, 20, venda=10),
        abastecimento(3, 2, 10), abastecimento(4, 2, 999, posto=5555),
        abastecimento(5, 3, 999),
    ])
    assert resultado.acumulado == 40
    assert resultado.atendimentos == 2
    assert resultado.abastecimentos == 3
    assert resultado.atendimentos_fallback == 1
    assert resultado.ticket == 20
    assert resultado.frentistas[0].ticket == 20
    assert resultado.frentistas[0].meta_ticket is None
    assert resultado.diario[0].litros == 30


def test_metas_vivas_percentuais_projecao_e_ticket_individual():
    metas = MetasPosto(bronze=310, prata=400, ouro=500, frentistas={7: {"meta_ticket": 25}})
    resultado = calcular_teste([abastecimento(1, 1, 30), abastecimento(2, 2, 10)], metas)
    assert resultado.dias_restantes == 30
    assert resultado.frentistas_ativos == 1
    assert resultado.niveis["bronze"].faltante == 270
    assert resultado.niveis["bronze"].meta_viva == Decimal(280) / 30
    assert resultado.niveis["bronze"].meta_viva_frentista == Decimal(280) / 30
    assert resultado.niveis["bronze"].media_exigida == 10
    assert resultado.niveis["bronze"].status_media == "acima"
    assert resultado.niveis["bronze"].status_viva == "acima"
    assert resultado.projecao == 640
    assert resultado.nivel_projetado == "ouro"
    assert resultado.frentistas[0].ganho_bico == 5
    assert resultado.frentistas[0].abaixo_meta is True
    assert resultado.frentistas[0].impacto_projetado == 775


def test_metas_atingidas_nunca_tem_faltante_negativo():
    resultado = calcular_teste([abastecimento(1, 1, 1000)], MetasPosto(bronze=10, prata=20, ouro=30))
    assert all(n.faltante == n.meta_viva == 0 for n in resultado.niveis.values())


def test_fim_de_mes_fechado_sem_divisao_zero_e_hoje_parcial():
    metas = MetasPosto(bronze=310, prata=400, ouro=500)
    fim = date(2026, 10, 31)
    resultado = calcular_teste([abastecimento(1, 31)], metas, dia=fim, hoje=date(2026, 11, 1))
    assert resultado.dias_restantes == 0 and not resultado.parcial
    assert resultado.niveis["bronze"].meta_viva is None
    assert resultado.projecao == resultado.acumulado
    parcial = calcular_teste([], metas, dia=fim, hoje=fim)
    assert parcial.dias_restantes == 1 and parcial.parcial


def test_mes_sem_meta_sem_movimento():
    resultado = calcular_teste()
    assert resultado.acumulado == 0 and resultado.niveis == {}
    assert resultado.ticket is None and resultado.frentistas == ()
    assert len(resultado.diario) == 2
    assert resultado.nivel_projetado is None


def test_ativos_cruzam_mes_e_nao_inflam_volume_do_mes():
    anterior = Abastecimento(codigo=9, empresa_codigo=11495, momento=datetime(2026, 9, 30),
                             litros=100, produto=1, frentista=8)
    resultado = calcular_teste([anterior, abastecimento(1, 1)])
    assert resultado.frentistas_ativos == 2
    assert resultado.acumulado == 10


def test_mix_ranking_e_codigo_desconhecido_sem_nome_inventado():
    resultado = calcular_teste([abastecimento(1, 1, 10), abastecimento(2, 2, 30, frentista=8, produto=2)])
    assert resultado.percentual_aditivado == 75
    assert resultado.frentistas[0].codigo == 8
    assert resultado.frentistas[0].ranking_volume == 1
    assert resultado.mix[1].percentual == 75
    desconhecido = calcular_teste([abastecimento(1, 1, produto=999, frentista=None)])
    assert desconhecido.percentual_aditivado is None
    assert desconhecido.mix[0].nome is None
    assert desconhecido.frentistas[0].nome is None


@pytest.mark.parametrize("mes,dia", [("2026-13", DIA), ("../2026-10", DIA), ("2026-10", date(2026, 10, 3))])
def test_referencia_rejeita_invalidos_e_futuro(mes, dia):
    with pytest.raises(ValueError):
        referencia(mes, DIA, dia)


def test_referencia_mes_passado_fecha_no_ultimo_dia():
    assert referencia("2026-09", DIA) == date(2026, 9, 30)


@pytest.mark.parametrize("metas", [dict(bronze=0, prata=10, ouro=20), dict(bronze=20, prata=10, ouro=30),
                                    dict(bronze=10, prata=20, ouro=30, frentistas={7: {"meta_ticket": 0}})])
def test_metas_invalidas(metas):
    with pytest.raises(ValidationError):
        MetasPosto(**metas)


def test_metas_ausentes_validas_corrompidas_e_mes_divergente(tmp_path):
    assert ler_metas("2026-10", diretorio=tmp_path) is None
    caminho = tmp_path / "2026-10.json"
    caminho.write_text(json.dumps({"mes": "2026-10", "definido_por": "Sintetico", "postos": {}}))
    assert ler_metas("2026-10", diretorio=tmp_path).postos == {}
    for conteudo in ("segredo invalido", json.dumps({"mes": "2026-09", "definido_por": "Sintetico", "postos": {}})):
        caminho.write_text(conteudo)
        with pytest.raises(MetasErro, match="Arquivo de metas invalido"):
            ler_metas("2026-10", diretorio=tmp_path)


def test_codigo_duplicado_nao_conta_duas_vezes():
    linha = abastecimento(1, 1)
    with pytest.raises(ValueError, match="duplicados"):
        calcular_teste([linha, linha])


async def test_adapter_filtra_afericao_tenant_data_e_mapeia_venda(monkeypatch):
    registro = {"abastecimentoCodigo": 1, "empresaCodigo": 11495, "dataHoraAbastecimento": "2026-10-02T03:00:00Z",
                "quantidade": 10, "codigoProduto": 1, "codigoFrentista": 7, "vendaItemCodigo": 2, "afericao": "N"}
    dados = {
        webposto.PATHS["abastecimentos"]: [registro, {**registro, "afericao": "S"}, {**registro, "empresaCodigo": 5555}],
        webposto.PATHS["itens"]: [{"empresaCodigo": 11495, "vendaItemCodigo": 2, "vendaCodigo": 3}],
        webposto.PATHS["produtos"]: [{"produtoCodigo": 1, "nome": "Gasolina ADITIVADA sintetica"}],
        webposto.PATHS["funcionarios"]: [{"empresaCodigo": 11495, "funcionarioCodigo": 7, "nome": "Sintetico",
                                        "cpf": "nao deve ser mapeado"},
                                       {"empresaCodigo": 5555, "funcionarioCodigo": 8, "nome": "Outro sintetico"}],
    }

    async def paginar(unidade, path, params):
        assert params["empresaCodigo"] == 11495
        return dados[path]

    monkeypatch.setattr(webposto, "paginar", paginar)
    linhas, produtos, funcionarios = await webposto.buscar(POSTOS[11495], DIA, DIA)
    assert len(linhas) == 1 and linhas[0].venda == 3
    assert linhas[0].momento.hour == 0
    assert produtos[1].aditivado and funcionarios == {7: "Sintetico"}
    assert "cpf" not in linhas[0].model_dump_json()


async def test_fonte_falha_nao_retorna_volume_ficticio(monkeypatch):
    monkeypatch.setattr(placar, "hoje", lambda: DIA)
    monkeypatch.setattr(placar, "ler_metas", lambda *args: None)
    monkeypatch.setattr(placar, "carregar_placar", lambda *args, **kwargs: None)

    async def falhar(*args):
        raise WebPostoErro("segredo")

    monkeypatch.setattr(placar, "buscar", falhar)
    with pytest.raises(placar.FonteIndisponivel, match="Fonte indisponivel") as erro:
        await placar.obter_placar(11495, "2026-10")
    assert "segredo" not in str(erro.value)


async def test_snapshot_anterior_complementa_so_o_dia_corrente(monkeypatch):
    ontem = date(2026, 10, 1)
    anterior = calcular(
        11495, "2026-10", ontem, DIA,
        [abastecimento(1, 1, 10, venda=100)],
        PRODUTOS, {7: "Nome sintetico"}, None, PROV,
    )
    linhas = [
        abastecimento(1, 1, 10, venda=100),
        abastecimento(2, 2, 10, venda=200, produto=2),
        abastecimento(3, 2, 10, venda=200, produto=2),
    ]
    chamadas = []

    async def buscar(posto, inicio, fim):
        chamadas.append((posto.empresa_codigo, inicio, fim))
        return linhas, PRODUTOS, {7: "Nome sintetico"}

    monkeypatch.setattr(placar, "hoje", lambda: DIA)
    monkeypatch.setattr(placar, "ler_metas", lambda *args: None)
    monkeypatch.setattr(placar, "carregar_placar", lambda *args, **kwargs: anterior)
    monkeypatch.setattr(placar, "buscar", buscar)

    resultado = await placar.obter_placar(11495, "2026-10")

    assert chamadas == [(11495, date(2026, 9, 26), DIA)]
    assert resultado.acumulado == 30
    assert resultado.realizado_dia == 20
    assert resultado.atendimentos == 2
    assert resultado.abastecimentos == 3
    assert [item.litros for item in resultado.diario] == [10, 20]
    assert resultado.frentistas[0].ticket == 15
    assert resultado.percentual_aditivado == Decimal(200) / 3
    assert [item.percentual for item in resultado.mix] == [Decimal(100) / 3, Decimal(200) / 3]


async def test_dia_fechado_retorna_snapshot_sem_consultar_fonte(monkeypatch):
    snapshot = calcular_teste([abastecimento(1, 1)], dia=date(2026, 10, 1), hoje=DIA)
    monkeypatch.setattr(placar, "hoje", lambda: DIA)
    monkeypatch.setattr(placar, "ler_metas", lambda *args: None)
    monkeypatch.setattr(placar, "carregar_placar", lambda *args, **kwargs: snapshot)

    async def proibido(*args):
        pytest.fail("Dia persistido não deve consultar a fonte.")

    monkeypatch.setattr(placar, "buscar", proibido)

    assert await placar.obter_placar(11495, "2026-10", date(2026, 10, 1)) == snapshot


def test_fronteira_comercial_sem_import_cash():
    modulo = Path(placar.__file__).resolve().parents[1]
    for caminho in modulo.rglob("*.py"):
        assert "cash_reconciliation" not in caminho.read_text(encoding="utf-8")
