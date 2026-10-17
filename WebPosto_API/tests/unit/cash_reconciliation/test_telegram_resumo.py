from datetime import date
import sys

import pytest

from src.jobs import telegram
from src.shared.notificacao.telegram import ResultadoDestinatario


@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-sintetico")
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "11")
    monkeypatch.setattr(telegram, "caminho_resumo", lambda dia: tmp_path / f"{dia.isoformat()}.md")
    monkeypatch.setattr(sys, "argv", ["telegram", "--reenviar-resumo", "13/10/2026"])
    envios = []

    def enviar(texto, **kwargs):
        envios.append((texto, kwargs))
        return [ResultadoDestinatario("11", True, 200)]

    monkeypatch.setattr(telegram, "enviar_mensagem", enviar)
    return tmp_path, envios


def test_reenvia_somente_resumo_gravado_sem_coletar(cli):
    pasta, envios = cli
    texto = "🌙 LOGOS — Caixas\n\nVIP · Loja — falta R$ 102,08\n"
    caminho = pasta / "2026-10-13.md"
    caminho.write_text(texto, encoding="utf-8")
    antes = caminho.read_bytes()
    assert telegram.main() == 0
    assert len(envios) == 1
    enviado, configuracao = envios[0]
    assert enviado.startswith("<b>LOGOS — REENVIO HISTÓRICO</b>")
    assert "não representa nova coleta ou auditoria atual" in enviado
    assert enviado.endswith(texto.strip())
    assert configuracao == {"token": "token-sintetico", "chat_ids": ["11"], "parse_mode": "HTML"}
    assert caminho.read_bytes() == antes


def test_resumo_inexistente_nao_envia(cli, capsys):
    _, envios = cli
    assert telegram.main() == 1
    assert not envios
    assert "Nenhum envio realizado" in capsys.readouterr().out


def test_resumo_vazio_nao_envia(cli):
    pasta, envios = cli
    (pasta / "2026-10-13.md").write_text(" \n", encoding="utf-8")
    assert telegram.main() == 1
    assert not envios


def test_reenvio_longo_divide_e_interrompe_apos_falha(cli, monkeypatch):
    pasta, envios = cli
    (pasta / "2026-10-13.md").write_text("linha sintética\n" * 900, encoding="utf-8")
    assert telegram.main() == 0
    assert len(envios) > 1
    assert all(len(t.encode("utf-16-le")) // 2 <= 4000 for t, _ in envios)
    falhas = []

    def falhar(*args, **kwargs):
        falhas.append(args)
        return [ResultadoDestinatario("11", False, 401)]

    monkeypatch.setattr(telegram, "enviar_mensagem", falhar)
    assert telegram.main() == 1
    assert len(falhas) == 1


@pytest.mark.parametrize("valor", ["13/10/2026", "1/10/2026", "2026-10-13", "31/02/2026"])
def test_data_estrita(valor):
    import argparse

    if valor == "13/10/2026":
        assert telegram._dia_resumo(valor) == date(2026, 10, 13)
    else:
        with pytest.raises(argparse.ArgumentTypeError):
            telegram._dia_resumo(valor)


def test_sem_opcao_explicita_nao_envia(cli, monkeypatch):
    _, envios = cli
    monkeypatch.setattr(sys, "argv", ["telegram"])
    with pytest.raises(SystemExit) as erro:
        telegram.main()
    assert erro.value.code == 2
    assert not envios
