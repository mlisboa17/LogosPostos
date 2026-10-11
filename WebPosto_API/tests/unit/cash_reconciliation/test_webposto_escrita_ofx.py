"""Testes unitários da barreira reforçada de escrita de OFX no webPosto (SPRINT 17B.1).

Garante que TODAS as regras da BARREIRA são estritamente respeitadas:
1. Só OFX;
2. Só esta escrita (/INTEGRACAO/V1/OFXS);
3. Só 'dias inexistentes' (proibidos EXCLUIR_DIAS_SISTEMA e IMPORTAR_DIAS_ARQUIVO);
4. Duas travas lidas EXCLUSIVAMENTE do arquivo .env (ignora process env, recusa duplicidade);
5. Débito bloqueado até confirmação formal pela Quality (lotes com débito recusados; créditos passam);
6. Anti-reenvio por (cdConta, dia) independentemente do arquivo/hash;
7. Dia 10/10/2026 na conta 86188 bloqueado até liberação explícita (--liberar-dia);
8. Sucesso só com conferência: mensagem "ENVIADO — CONFERIR NA TELA" e registro de conferência;
9. Conta certa (mapa units.json conferido com V1/CONTAS);
10. Limites (máximo 7 dias e período no passado).
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
    confirmar_conferencia_historico,
    enviar_ofx_webposto,
    formatar_transacao_webposto,
    liberar_dia_historico,
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
    arquivo = tmp_path / f"extrato_{dias_atras}_{acctid}.ofx"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def _criar_ofx_creditos_apenas(tmp_path: Path, bankid: str = "290", acctid: str = "84369048-8", dias_atras: int = 2) -> Path:
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
  <FITID>fit-credito-1</FITID>
  <MEMO>PIX RECEBIDO CLIENTE 12345678901</MEMO>
</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>"""
    arquivo = tmp_path / f"extrato_credito_{dias_atras}.ofx"
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
async def test_travas_so_do_arquivo_env_ignora_process_environ(tmp_path, monkeypatch):
    """Garante que variáveis no os.environ NÃO liberam o envio se o arquivo .env não as contiver."""
    env_file = tmp_path / ".env"
    env_file.write_text("WEBPOSTO_REDE_NOME=TESTE\n", encoding="utf-8")

    # Injeta no ambiente do processo
    monkeypatch.setenv("WEBPOSTO_WRITES", "1")
    monkeypatch.setenv("LOGOS_OFX_IMPORTACAO", "1")

    # Deve bloquear porque o arquivo .env não tem as travas
    ok, motivo = verificar_travas_ambiente(env_file)
    assert ok is False
    assert "WEBPOSTO_WRITES != 1 no arquivo .env" in motivo

    # Agora escreve no arquivo .env apenas WEBPOSTO_WRITES=1
    env_file.write_text("WEBPOSTO_WRITES=1\n", encoding="utf-8")
    ok2, motivo2 = verificar_travas_ambiente(env_file)
    assert ok2 is False
    assert "LOGOS_OFX_IMPORTACAO != 1 no arquivo .env" in motivo2

    # Agora coloca ambas = 1 no arquivo .env
    env_file.write_text("WEBPOSTO_WRITES=1\nLOGOS_OFX_IMPORTACAO=1\n", encoding="utf-8")
    ok3, motivo3 = verificar_travas_ambiente(env_file)
    assert ok3 is True
    assert "Travas de escrita liberadas" in motivo3


@pytest.mark.asyncio
async def test_trava_duplicada_no_arquivo_env_recusa(tmp_path):
    """Garante que chaves duplicadas no .env são recusadas com número das linhas exatas."""
    env_file = tmp_path / ".env"
    conteudo = (
        "WEBPOSTO_REDE_NOME=REDE\n"        # linha 1
        "WEBPOSTO_WRITES=1\n"              # linha 2
        "LOGOS_OFX_IMPORTACAO=1\n"         # linha 3
        "# Comentario intermediario\n"     # linha 4
        "WEBPOSTO_WRITES=0\n"              # linha 5
    )
    env_file.write_text(conteudo, encoding="utf-8")

    ok, motivo = verificar_travas_ambiente(env_file)
    assert ok is False
    assert "trava duplicada no .env, linha 2 e 5" in motivo


@pytest.mark.asyncio
async def test_debito_bloqueado_sem_confirmacao_da_quality(tmp_path, monkeypatch, mock_webposto_transport):
    """Garante que qualquer lote que contenha débito é recusado enquanto Quality não confirmar o formato."""
    unidade = _criar_unidade_teste()
    arquivo_ofx_com_debito = _criar_ofx_sintetico(tmp_path)
    client = httpx.AsyncClient(transport=mock_webposto_transport, base_url="https://fake-webposto")
    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")

    # Sem formato confirmado -> recusa tanto na prévia quanto no envio
    with pytest.raises(BarreiraOfxErro, match="formato de débito não confirmado pela Quality"):
        await enviar_ofx_webposto(
            unidade,
            arquivo_ofx_com_debito,
            confirmar=False,
            client=client,
            diretorio_historico=tmp_path / "hist",
            formato_tipo_debito_confirmado=None,
        )


@pytest.mark.asyncio
async def test_credito_only_passa_na_previa(tmp_path, monkeypatch, mock_webposto_transport):
    """Garante que lote exclusivamente com créditos segue normalmente na prévia sem bloqueio de débito."""
    unidade = _criar_unidade_teste()
    arquivo_ofx_creditos = _criar_ofx_creditos_apenas(tmp_path)
    client = httpx.AsyncClient(transport=mock_webposto_transport, base_url="https://fake-webposto")
    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")

    res = await enviar_ofx_webposto(
        unidade,
        arquivo_ofx_creditos,
        confirmar=False,
        client=client,
        diretorio_historico=tmp_path / "hist",
    )
    assert res.sucesso is True
    assert res.modo == "previa"
    assert res.previa.quantidade == 1
    assert res.previa.total_creditos == Decimal("250.00")
    assert res.previa.total_debitos == Decimal("0.00")


@pytest.mark.asyncio
async def test_anti_reenvio_por_conta_e_dia(tmp_path, monkeypatch, mock_webposto_transport):
    """Garante que o bloqueio anti-reenvio é por (cdConta, dia), mesmo com arquivo diferente."""
    unidade = _criar_unidade_teste()
    dias_atras = 3
    dt_alvo = ontem() - timedelta(days=dias_atras)

    arq1 = _criar_ofx_creditos_apenas(tmp_path, acctid="84369048-8", dias_atras=dias_atras)
    dir_hist = tmp_path / "hist"
    env_file = tmp_path / ".env"
    env_file.write_text("WEBPOSTO_WRITES=1\nLOGOS_OFX_IMPORTACAO=1\n", encoding="utf-8")

    client = httpx.AsyncClient(transport=mock_webposto_transport, base_url="https://fake-webposto")
    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")

    # 1. Envio inicial do dia
    res1 = await enviar_ofx_webposto(
        unidade,
        arq1,
        confirmar=True,
        client=client,
        diretorio_historico=dir_hist,
        caminho_env=env_file,
    )
    assert res1.sucesso is True
    assert res1.modo == "enviado"

    # 2. Cria OUTRO arquivo com outro nome e conteúdo diferente para o MESMO dia e conta
    arq2 = tmp_path / "outro_arquivo_segundo.ofx"
    arq2.write_text(arq1.read_text(encoding="utf-8").replace("fit-credito-1", "fit-credito-2-outro"), encoding="utf-8")

    # Tentativa com o novo arquivo para a mesma conta e dia deve ser BLOQUEADA
    with pytest.raises(BarreiraOfxErro, match="já foi importada anteriormente"):
        await enviar_ofx_webposto(
            unidade,
            arq2,
            confirmar=True,
            client=client,
            diretorio_historico=dir_hist,
            caminho_env=env_file,
        )


@pytest.mark.asyncio
async def test_dia_10_10_86188_bloqueado_ate_liberar_dia(tmp_path):
    """Garante que o dia 10/10/2026 na conta 86188 fica bloqueado e só é liberado com --liberar-dia."""
    dir_hist = tmp_path / "hist"
    empresa = 74014
    conta = 86188
    dia = date(2026, 10, 10)

    # Cria histórico simulando o incidente de 10/10/2026
    pasta = dir_hist / str(empresa)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo_hist = pasta / "historico.json"
    registro_incidente = [
        {
            "arquivo": "PagBank_Doze_Outubro2026.ofx.ofx",
            "sha256": "hash12345",
            "empresa_codigo": empresa,
            "cd_conta": conta,
            "data_inicial": "2026-10-10",
            "data_final": "2026-10-10",
            "status": "importado com débitos errados — aguardando correção",
            "data_envio": "2026-10-11T17:07:43",
        }
    ]
    arquivo_hist.write_text(json.dumps(registro_incidente), encoding="utf-8")

    # 1. Verificação deve falhar com a mensagem específica
    with pytest.raises(BarreiraOfxErro, match="importado com débitos errados — aguardando correção"):
        verificar_duplicidade_historico(dir_hist, empresa, conta, dia, dia)

    # 2. Executa a liberação explícita via função do CLI
    reg_liberacao = liberar_dia_historico(
        dir_hist,
        empresa,
        conta,
        dia,
        motivo="Autorizado pelo diretor após alinhamento com a Quality",
    )
    assert reg_liberacao["status"] == "dia_liberado"

    # 3. Agora a verificação de duplicidade deve PASSAR
    verificar_duplicidade_historico(dir_hist, empresa, conta, dia, dia)


@pytest.mark.asyncio
async def test_mensagem_enviado_conferir_na_tela(tmp_path, monkeypatch, mock_webposto_transport):
    """Garante que após envio bem-sucedido a mensagem exibe 'ENVIADO — CONFERIR NA TELA'."""
    unidade = _criar_unidade_teste()
    arquivo_ofx = _criar_ofx_creditos_apenas(tmp_path)
    client = httpx.AsyncClient(transport=mock_webposto_transport, base_url="https://fake-webposto")
    dir_hist = tmp_path / "hist"
    env_file = tmp_path / ".env"
    env_file.write_text("WEBPOSTO_WRITES=1\nLOGOS_OFX_IMPORTACAO=1\n", encoding="utf-8")

    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")

    res = await enviar_ofx_webposto(
        unidade,
        arquivo_ofx,
        confirmar=True,
        client=client,
        diretorio_historico=dir_hist,
        caminho_env=env_file,
    )
    assert res.sucesso is True
    assert res.modo == "enviado"
    assert res.mensagem == "ENVIADO — CONFERIR NA TELA"

    # Verifica registro gravado no histórico
    hist = json.loads((dir_hist / str(unidade.empresa_codigo) / "historico.json").read_text(encoding="utf-8"))
    assert hist[-1]["status"] == "enviado_aguardando_conferencia"
    assert Decimal(hist[-1]["total_creditos"]) == Decimal("250.00")
    assert Decimal(hist[-1]["total_debitos"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_confirmar_conferencia_registrada_no_historico(tmp_path):
    """Garante que a confirmação de conferência pelo diretor é registrada no histórico."""
    dir_hist = tmp_path / "hist"
    empresa = 74014
    conta = 86188
    dia = date(2026, 10, 10)

    reg = confirmar_conferencia_historico(dir_hist, empresa, conta, dia, usuario="diretor")
    assert reg["tipo"] == "conferencia_confirmada"
    assert reg["status"] == "conferencia_confirmada"

    hist = json.loads((dir_hist / str(empresa) / "historico.json").read_text(encoding="utf-8"))
    assert len(hist) == 1
    assert hist[0]["dia"] == "2026-10-10"
    assert hist[0]["usuario"] == "diretor"


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
async def test_regra_8_limite_de_7_dias_e_periodo_no_passado(tmp_path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = _criar_ofx_creditos_apenas(tmp_path)

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
async def test_formato_movimentos_conta_em_portugues_com_variante_confirmada(tmp_path, monkeypatch, mock_webposto_transport):
    """Garante formatação correta de transações quando formato de débito é informado."""
    unidade = _criar_unidade_teste()
    arquivo_ofx = _criar_ofx_sintetico(tmp_path)
    client = httpx.AsyncClient(transport=mock_webposto_transport, base_url="https://fake-webposto")
    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")
    res = await enviar_ofx_webposto(
        unidade,
        arquivo_ofx,
        confirmar=False,
        client=client,
        diretorio_historico=tmp_path / "hist",
        formato_tipo_debito_confirmado="DEBITO_PORTUGUES",
    )
    assert res.payload_enviado is not None
    transacoes = res.payload_enviado["transacoes"]
    assert len(transacoes) == 2
    t1, t2 = transacoes
    assert t1["tipo"] == "Crédito"
    assert t1["valor"] == 250.0
    assert t1["tipoTransacao"] is None

    assert t2["tipo"] == "Débito"
    assert t2["valor"] == 50.0
    assert t2["tipoTransacao"] is None


@pytest.mark.asyncio
async def test_permissao_escrita_403_tratada_com_clareza(tmp_path, monkeypatch):
    unidade = _criar_unidade_teste()
    arquivo_ofx = _criar_ofx_creditos_apenas(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("WEBPOSTO_WRITES=1\nLOGOS_OFX_IMPORTACAO=1\n", encoding="utf-8")

    def handler_403(request: httpx.Request) -> httpx.Response:
        if "/INTEGRACAO/V1/CONTAS" in str(request.url):
            return httpx.Response(200, json={"resultados": [{"contaCodigo": 86188, "descricao": "PAGBANK", "ativo": True}]})
        if "/INTEGRACAO/V1/OFXS" in str(request.url):
            return httpx.Response(403, json={"erro": "Acesso negado para escrita"})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler_403), base_url="https://fake-webposto")
    monkeypatch.setenv("CHAVE_TESTE_ENV", "token_valido")

    with pytest.raises(BarreiraOfxErro, match="não possui permissão de escrita"):
        await enviar_ofx_webposto(
            unidade,
            arquivo_ofx,
            confirmar=True,
            client=client,
            diretorio_historico=tmp_path / "hist",
            caminho_env=env_file,
        )
