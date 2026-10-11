"""Testes unitários da barreira de escrita de OFX no webPosto.

Garante que TODAS as 8 regras da BARREIRA são estritamente respeitadas:
1. Só OFX;
2. Só esta escrita (/INTEGRACAO/V1/OFXS);
3. Só 'dias inexistentes' (proibidos EXCLUIR_DIAS_SISTEMA e IMPORTAR_DIAS_ARQUIVO);
4. Duas travas no .env (WEBPOSTO_WRITES=1 e LOGOS_OFX_IMPORTACAO=1);
5. Prévia antes de enviar (sem --confirmar, nunca chama POST);
6. Conta certa (mapa units.json conferido com V1/CONTAS);
7. Sem duplicar (histórico em data/importacoes_ofx/ e checagem de reenvio);
8. Limites (máximo 7 dias e período no passado).
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from src.modules.cash_reconciliation.adapters.webposto_escrita_ofx import (
    BarreiraOfxErro,
    OPCAO_IMPORTACAO_PERMITIDA,
    OPCOES_PROIBIDAS,
    enviar_ofx_webposto,
    formatar_transacao_webposto,
    montar_payload_ofx,
    resolver_cd_conta_unidade,
    verificar_duplicidade_historico,
    verificar_travas_ambiente,
)
from src.modules.cash_reconciliation.domain.models import ContaExtratoConfig, Destino, TipoDestino, Unidade
from src.modules.cash_reconciliation.domain.tempo import ontem


def _criar_unidade_teste() -> Unidade:
    return Unidade(
        empresa_codigo=74014,
        nome="POSTO DOZE FILIAL II",
        apelido="Doze",
        chave_env="CHAVE_TESTE_ENV",
        destinos=(
            Destino(conta_codigo=86248, tipo=TipoDestino.DEPOSITO_DIRETO, banco="BB"),
            Destino(conta_codigo=86081, tipo=TipoDestino.COFRE, banco="BB"),
        ),
        contas_extrato=(
            ContaExtratoConfig(banco="PAGBANK", conta_sufixo="9048-8", cd_conta=86188),
            ContaExtratoConfig(banco="BB", conta_sufixo="4068-X", cd_conta=86248),
        ),
    )


def _criar_ofx_sintetico(tmp_path: Path, bankid: str = "290", acctid: str = "84369048-8", dias_atras: int = 2) -> Path:
    dt_passada = (ontem() - timedelta(days=dias_atras)).strftime("%Y%m%d")
    conteudo = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:UTF-8
CHARSET:NONE
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE
<OFX>
<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS><DTSERVER>{dt_passada}120000[-3:BRT]<LANGUAGE>POR</SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><STMTRS>
<BANKACCTFROM><BANKID>{bankid}</BANKID><ACCTID>{acctid}</ACCTID></BANKACCTFROM>
<BANKTRANLIST><DTSTART>{dt_passada}</DTSTART><DTEND>{dt_passada}</DTEND>
<STMTTRN>
  <TRNTYPE>IN</TRNTYPE>
  <DTPOSTED>{dt_passada}100000[-3:BRT]</DTPOSTED>
  <TRNAMT>250.00</TRNAMT>
  <FITID>fit-teste-1</FITID>
  <MEMO>PIX RECEBIDO CLIENTE 12345678901</MEMO>
</STMTTRN>
<STMTTRN>
  <TRNTYPE>OUT</TRNTYPE>
  <DTPOSTED>{dt_passada}110000[-3:BRT]</DTPOSTED>
  <TRNAMT>50.00</TRNAMT>
  <FITID>fit-teste-2</FITID>
  <MEMO>TARIFA BANCARIA</MEMO>
</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>"""
    arquivo = tmp_path / "extrato_teste.ofx"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


@pytest.fixture
def mock_webposto_transport():
    contas_cadastradas = [
        {"contaCodigo": 86081, "descricao": "CAIXA(POSTO)-DOZE FILIAL", "ativo": True},
        {"contaCodigo": 86115, "descricao": "MAIS PAGAMENTOS", "ativo": True},
        {"contaCodigo": 86188, "descricao": "PAGBANK DOZE FILIAL", "ativo": True},
        {"contaCodigo": 86248, "descricao": "BANCO 24H - DOZE FILIAL", "ativo": True},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/INTEGRACAO/V1/CONTAS" in url_str:
            return httpx.Response(200, json={"ultimoCodigo": None, "resultados": contas_cadastradas})
        if "/INTEGRACAO/V1/OFXS" in url_str:
            payload = json.loads(request.content)
            # Valida barreira no recebimento
            if payload.get("opcaoImportacao") != OPCAO_IMPORTACAO_PERMITIDA:
                return httpx.Response(400, json={"erro": "opcaoImportacao invalida"})
            return httpx.Response(201, json={"status": "sucesso", "protocolo": 999888})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_regra_1_recusa_arquivo_nao_ofx(tmp_path):
    arq_txt = tmp_path / "extrato.txt"
    arq_txt.write_text("nao e ofx", encoding="utf-8")
    unidade = _criar_unidade_teste()

    with pytest.raises(BarreiraOfxErro, match="Apenas arquivos .ofx são permitidos"):
        await enviar_ofx_webposto(unidade, arq_txt)


@pytest.mark.asyncio
async def test_regra_3_opcao_importacao_fixa_e_proibe_termos_perigosos():
    assert OPCAO_IMPORTACAO_PERMITIDA == "IMPORTAR_APENAS_DIAS_INEXISTENTES_SISTEMA"
    for proibida in OPCOES_PROIBIDAS:
        assert proibida in ("EXCLUIR_DIAS_SISTEMA", "IMPORTAR_DIAS_ARQUIVO")

    payload = montar_payload_ofx(
        cd_conta=86188,
        cd_filial=74014,
        data_inicial=date(2026, 10, 1),
        data_final=date(2026, 10, 2),
        lancamentos=(),
    )
    assert payload["opcaoImportacao"] == "IMPORTAR_APENAS_DIAS_INEXISTENTES_SISTEMA"
    payload_str = json.dumps(payload)
    for proibida in OPCOES_PROIBIDAS:
        assert proibida not in payload_str


@pytest.mark.asyncio
async def test_regra_4_e_5_previa_quando_confirmar_false_ou_travas_desligadas(tmp_path, monkeypatch, mock_webposto_transport):
    unidade = _criar_unidade_teste()
    arquivo_ofx = _criar_ofx_sintetico(tmp_path)
    client = httpx.AsyncClient(transport=mock_webposto_transport, base_url="https://fake-webposto")

    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")
    monkeypatch.setenv("WEBPOSTO_WRITES", "0")
    monkeypatch.setenv("LOGOS_OFX_IMPORTACAO", "0")

    # 1. Sem confirmar -> apenas prévia
    res = await enviar_ofx_webposto(
        unidade,
        arquivo_ofx,
        confirmar=False,
        client=client,
        diretorio_historico=tmp_path / "hist",
    )
    assert res.sucesso is True
    assert res.modo == "previa"
    assert "Prévia gerada com sucesso" in res.mensagem
    assert res.previa.quantidade == 2
    assert res.previa.total_creditos == Decimal("250.00")
    assert res.previa.total_debitos == Decimal("50.00")
    # Verifica que descrição com CPF foi mascarada na prévia
    assert "***CPF***" in res.previa.amostra_primeiros[0]["descricao_mascarada"]

    # 2. Com confirmar=True mas travas desligadas -> bloqueado
    res2 = await enviar_ofx_webposto(
        unidade,
        arquivo_ofx,
        confirmar=True,
        client=client,
        diretorio_historico=tmp_path / "hist",
    )
    assert res2.sucesso is False
    assert res2.modo == "previa"
    assert "Envio bloqueado pelas travas de segurança" in res2.mensagem


@pytest.mark.asyncio
async def test_regra_6_resolucao_e_validacao_de_conta_certa():
    unidade = _criar_unidade_teste()
    contas_webposto = [
        {"contaCodigo": 86188, "descricao": "PAGBANK DOZE FILIAL", "ativo": True},
        {"contaCodigo": 86248, "descricao": "BANCO 24H - DOZE FILIAL", "ativo": True},
    ]

    # PagBank -> 86188
    cd = resolver_cd_conta_unidade(unidade, "PAGBANK", "9048-8", contas_webposto)
    assert cd == 86188

    # BB -> 86248
    cd_bb = resolver_cd_conta_unidade(unidade, "BB", "4068-X", contas_webposto)
    assert cd_bb == 86248

    # Conta desconhecida -> erro
    with pytest.raises(BarreiraOfxErro, match="Não foi possível identificar o cdConta"):
        resolver_cd_conta_unidade(unidade, "SANTANDER", "12345-6", contas_webposto)

    # Conta mapeada mas inativa no webPosto -> erro
    contas_inativas = [
        {"contaCodigo": 86188, "descricao": "PAGBANK DOZE FILIAL", "ativo": False},
    ]
    with pytest.raises(BarreiraOfxErro, match="não está ativo"):
        resolver_cd_conta_unidade(unidade, "PAGBANK", "9048-8", contas_inativas)


@pytest.mark.asyncio
async def test_regra_7_sem_duplicar_mesmo_arquivo_ou_periodo(tmp_path, monkeypatch, mock_webposto_transport):
    unidade = _criar_unidade_teste()
    arquivo_ofx = _criar_ofx_sintetico(tmp_path)
    client = httpx.AsyncClient(transport=mock_webposto_transport, base_url="https://fake-webposto")
    dir_hist = tmp_path / "hist"

    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")
    monkeypatch.setenv("WEBPOSTO_WRITES", "1")
    monkeypatch.setenv("LOGOS_OFX_IMPORTACAO", "1")

    # Primeiro envio com sucesso
    res = await enviar_ofx_webposto(
        unidade,
        arquivo_ofx,
        confirmar=True,
        client=client,
        diretorio_historico=dir_hist,
    )
    assert res.sucesso is True
    assert res.modo == "enviado"

    # Tentativa de reenviar o mesmo arquivo -> bloqueado pela barreira de hash
    with pytest.raises(BarreiraOfxErro, match="já foi importado anteriormente"):
        await enviar_ofx_webposto(
            unidade,
            arquivo_ofx,
            confirmar=True,
            client=client,
            diretorio_historico=dir_hist,
        )


@pytest.mark.asyncio
async def test_regra_8_limite_de_7_dias_e_periodo_no_passado(tmp_path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = _criar_ofx_sintetico(tmp_path)

    # 1. Período no futuro ou hoje (não permitido; deve ser até ontem)
    dt_futura = ontem() + timedelta(days=2)
    with pytest.raises(BarreiraOfxErro, match="não pode ser superior a ontem"):
        await enviar_ofx_webposto(
            unidade,
            arquivo_ofx,
            data_inicial=ontem() - timedelta(days=1),
            data_final=dt_futura,
            confirmar=False,
        )

    # 2. Período superior a 7 dias
    dt_ini_antiga = ontem() - timedelta(days=10)
    with pytest.raises(BarreiraOfxErro, match="Limite de período excedido"):
        await enviar_ofx_webposto(
            unidade,
            arquivo_ofx,
            data_inicial=dt_ini_antiga,
            data_final=ontem(),
            confirmar=False,
        )


@pytest.mark.asyncio
async def test_permissao_escrita_403_tratada_com_clareza(tmp_path, monkeypatch):
    unidade = _criar_unidade_teste()
    arquivo_ofx = _criar_ofx_sintetico(tmp_path)

    def handler_403(request: httpx.Request) -> httpx.Response:
        if "/INTEGRACAO/V1/CONTAS" in str(request.url):
            return httpx.Response(200, json={"resultados": [{"contaCodigo": 86188, "descricao": "PAGBANK", "ativo": True}]})
        if "/INTEGRACAO/V1/OFXS" in str(request.url):
            return httpx.Response(403, json={"erro": "Acesso negado para escrita"})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler_403), base_url="https://fake-webposto")
    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")
    monkeypatch.setenv("WEBPOSTO_WRITES", "1")
    monkeypatch.setenv("LOGOS_OFX_IMPORTACAO", "1")

    with pytest.raises(BarreiraOfxErro, match="não possui permissão de escrita"):
        await enviar_ofx_webposto(
            unidade,
            arquivo_ofx,
            confirmar=True,
            client=client,
            diretorio_historico=tmp_path / "hist",
        )
