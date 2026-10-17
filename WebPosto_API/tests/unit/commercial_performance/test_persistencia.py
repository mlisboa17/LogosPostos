from datetime import date, datetime
from decimal import Decimal

import pytest

from src.modules.commercial_performance.adapters import persistencia
from src.modules.commercial_performance.config import POSTOS
from src.modules.commercial_performance.domain.models import Placar, Proveniencia
from src.jobs import noturno as composicao_noturno


def placar_sintetico():
    return Placar(
        posto=11495,
        mes="2026-10",
        dia=date(2026, 10, 2),
        parcial=True,
        dias_mes=31,
        dias_restantes=30,
        frentistas_ativos=1,
        acumulado=Decimal("20"),
        realizado_dia=Decimal("10"),
        atendimentos=2,
        abastecimentos=2,
        atendimentos_fallback=2,
        ticket=Decimal("10"),
        projecao=Decimal("310"),
        nivel_projetado="abaixo_bronze",
        percentual_aditivado=Decimal(0),
        niveis={},
        diario=(),
        frentistas=(),
        mix=(),
        proveniencia=Proveniencia(
            executado_em=datetime(2026, 10, 2, 12),
            execucao_id="execucao-sintetica",
            versao_regra="PLACAR_V1",
            fontes=("/INTEGRACAO/V1/ABASTECIMENTOS",),
            metas_cadastradas=False,
        ),
    )


def test_snapshot_mensal_persiste_e_nao_regrede_data(tmp_path, caplog):
    original = placar_sintetico()
    caminho = persistencia.salvar_placar(original, diretorio=tmp_path)
    assert caminho == tmp_path / "2026-10" / "11495.json"
    assert persistencia.carregar_placar(11495, "2026-10", diretorio=tmp_path) == original

    antigo = original.model_copy(update={"dia": date(2026, 10, 1)})
    persistencia.salvar_placar(antigo, diretorio=tmp_path)

    assert persistencia.carregar_placar(11495, "2026-10", diretorio=tmp_path) == original
    assert "Snapshot antigo ignorado posto=11495 mes=2026-10" in caplog.text
    assert list(caminho.parent.iterdir()) == [caminho]


def test_snapshot_corrompido_e_isolado_sem_expor_conteudo(tmp_path, caplog):
    caminho = persistencia.caminho_placar(11495, "2026-10", tmp_path)
    caminho.parent.mkdir()
    caminho.write_text("conteudo secreto invalido", encoding="utf-8")

    with pytest.raises(persistencia.PersistenciaErro) as erro:
        persistencia.carregar_placar(11495, "2026-10", diretorio=tmp_path)

    assert "secreto" not in str(erro.value) + caplog.text


def test_falha_atomica_preserva_snapshot_anterior(monkeypatch, tmp_path):
    original = placar_sintetico()
    persistencia.salvar_placar(original, diretorio=tmp_path)

    def falhar(*args):
        raise OSError("detalhe interno")

    monkeypatch.setattr(persistencia.os, "replace", falhar)
    with pytest.raises(persistencia.PersistenciaErro, match="persistir"):
        persistencia.salvar_placar(
            original.model_copy(update={"acumulado": Decimal("30")}),
            diretorio=tmp_path,
        )

    assert persistencia.carregar_placar(11495, "2026-10", diretorio=tmp_path) == original
    assert len(list((tmp_path / "2026-10").iterdir())) == 1


async def test_composicao_noturna_persiste_placar(monkeypatch, tmp_path):
    monkeypatch.setattr(composicao_noturno, "POSTOS", POSTOS)
    chamadas = []

    async def obter(posto, mes, dia, *, forcar_coleta):
        assert forcar_coleta is True
        chamadas.append((posto, mes, dia))
        return placar_sintetico().model_copy(update={"posto": posto})

    monkeypatch.setattr(composicao_noturno, "obter_placar", obter)

    falhas, unidades_com_falha = await composicao_noturno._executar_placar(
        date(2026, 10, 2),
        timeout=60,
        diretorio=tmp_path / "placar",
    )

    assert falhas == 0
    assert unidades_com_falha == set()
    assert chamadas == [(posto, "2026-10", date(2026, 10, 2)) for posto in (11495, 74014, 5555)]
    for posto in (11495, 74014, 5555):
        assert persistencia.carregar_placar(
            posto,
            "2026-10",
            diretorio=tmp_path / "placar",
        ) == placar_sintetico().model_copy(update={"posto": posto})
