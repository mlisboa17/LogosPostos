"""Testes sintéticos para identificação de candidatos a baixa de títulos por extrato (PARTE A).

Nenhum teste acessa o webPosto real ou o sistema de arquivos externo.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest

from src.modules.cash_reconciliation.application.titulos_pagos_sem_baixa import (
    PreviaBaixaTitulos,
    TituloCandidato,
    eh_transferencia_propria_ou_aplicacao,
    encontrar_candidatos_baixa,
    fornecedor_confere_extrato,
    formatar_relatorio_previa,
)
from src.modules.cash_reconciliation.domain.models import ContaExtratoConfig, Unidade


def _criar_unidade_teste() -> Unidade:
    return Unidade.model_validate(
        {
            "empresa_codigo": 74014,
            "nome": "POSTO DOZE FILIAL II",
            "apelido": "Doze",
            "chave_env": "WEBPOSTO_API_KEY_DOZE",
            "destinos": [],
            "contas_extrato": [
                {"banco": "BB", "conta_sufixo": "4068-X", "cd_conta": 86248},
                {"banco": "PAGBANK", "conta_sufixo": "9048-8", "cd_conta": 86188},
            ],
        }
    )


def _contas_mock_padrao():
    return [
        {"contaCodigo": 86248, "descricao": "BANCO 24H - DOZE FILIAL", "ativo": True},
        {"contaCodigo": 86188, "descricao": "PAGBANK DOZE FILIAL", "ativo": True},
    ]


def _gerar_ofx_bytes(
    banco: str = "BB",
    conta: str = "4068-X",
    lancamentos: list[tuple[str, str, str, str]] = None,
) -> bytes:
    """Gera conteúdo OFX SGML sintético.
    lancamentos = [(fitid, data_str, valor_str, memo)]
    """
    bankid = "1" if banco == "BB" else "290"
    trans_xml = ""
    for fitid, dt, val, memo in lancamentos or []:
        trntype = "DEBIT" if float(val) < 0 else "CREDIT"
        trans_xml += f"""
<STMTTRN>
<TRNTYPE>{trntype}</TRNTYPE>
<DTPOSTED>{dt}120000[-3:BRT]</DTPOSTED>
<TRNAMT>{val}</TRNAMT>
<FITID>{fitid}</FITID>
<MEMO>{memo}</MEMO>
</STMTTRN>
"""
    conteudo = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEVERSION:102
NEWFILEVERSION:102

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0</CODE>
<SEVERITY>INFO</SEVERITY>
</STATUS>
<DTSERVER>20261011120000[-3:BRT]</DTSERVER>
<LANGUAGE>POR</LANGUAGE>
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1001</TRNUID>
<STATUS>
<CODE>0</CODE>
<SEVERITY>INFO</SEVERITY>
</STATUS>
<STMTRS>
<CURDEF>BRL</CURDEF>
<BANKACCTFROM>
<BANKID>{bankid}</BANKID>
<ACCTID>{conta}</ACCTID>
<ACCTTYPE>CHECKING</ACCTTYPE>
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20260801120000[-3:BRT]</DTSTART>
<DTEND>20261011120000[-3:BRT]</DTEND>
{trans_xml}
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""
    return conteudo.encode("utf-8")


@pytest.mark.asyncio
async def test_titulo_aberto_vencido_com_debito_exato_e_nome_vira_pronto(tmp_path: Path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = tmp_path / "extrato_bb.ofx"
    arquivo_ofx.write_bytes(
        _gerar_ofx_bytes(
            banco="BB",
            lancamentos=[("FIT1", "20260914", "-1400.00", "Pagamento de Boleto - DUNAX LUBRIFICANTES LTDA")],
        )
    )

    titulos_mock = [
        {
            "tituloPagarCodigo": 3171998,
            "situacao": "Aberto",
            "valor": 1400.00,
            "vencimento": "2026-09-14",
            "nomeFornecedor": "DUNAX LUBRIFICANTES LTDA PE VAREJO",
            "planoContaGerencialDescricao": "LUBRIFICANTES",
        }
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arquivo_ofx],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    assert len(previa.prontos) == 1
    p = previa.prontos[0]
    assert p.titulo_codigo == 3171998
    assert p.valor == Decimal("1400.00")
    assert p.cd_conta == 86248
    assert p.banco == "BB"
    assert p.status == "pronto"
    assert len(previa.conferir_mao) == 0
    assert len(previa.ambiguos) == 0


@pytest.mark.asyncio
async def test_titulo_pago_elimina_debito_da_disputa(tmp_path: Path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = tmp_path / "extrato_bb.ofx"
    arquivo_ofx.write_bytes(
        _gerar_ofx_bytes(
            banco="BB",
            lancamentos=[("FIT_PAGO", "20260910", "-500.00", "Pagamento de Boleto - FORNECEDOR TESTE")],
        )
    )

    # 1 título pago já consumiu o débito de 500.00
    # 1 título aberto tem o mesmo valor de 500.00
    titulos_mock = [
        {
            "tituloPagarCodigo": 100,
            "situacao": "Pago",
            "valor": 500.00,
            "dataPagamento": "2026-09-10",
            "nomeFornecedor": "FORNECEDOR TESTE",
        },
        {
            "tituloPagarCodigo": 200,
            "situacao": "Aberto",
            "valor": 500.00,
            "vencimento": "2026-09-10",
            "nomeFornecedor": "FORNECEDOR TESTE",
        },
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arquivo_ofx],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    # Como o débito foi consumido pelo título pago, o aberto não acha débito
    assert len(previa.prontos) == 0
    assert len(previa.conferir_mao) == 0
    assert len(previa.ambiguos) == 0


@pytest.mark.asyncio
async def test_valor_exato_sem_nome_fornecedor_vira_conferir_a_mao(tmp_path: Path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = tmp_path / "extrato_bb.ofx"
    arquivo_ofx.write_bytes(
        _gerar_ofx_bytes(
            banco="BB",
            lancamentos=[("FIT_SEM_NOME", "20260915", "-350.00", "Pagamento de Boleto - DESTINATARIO DESCONHECIDO")],
        )
    )

    titulos_mock = [
        {
            "tituloPagarCodigo": 300,
            "situacao": "Aberto",
            "valor": 350.00,
            "vencimento": "2026-09-15",
            "nomeFornecedor": "FORNECEDOR REAL LTDA",
        }
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arquivo_ofx],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    assert len(previa.prontos) == 0
    assert len(previa.conferir_mao) == 1
    m = previa.conferir_mao[0]
    assert m.titulo_codigo == 300
    assert "sem confirmação do nome" in m.motivo


@pytest.mark.asyncio
async def test_dois_titulos_mesmo_debito_vira_ambiguo(tmp_path: Path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = tmp_path / "extrato_bb.ofx"
    arquivo_ofx.write_bytes(
        _gerar_ofx_bytes(
            banco="BB",
            lancamentos=[("FIT_DUPLO", "20260914", "-447.50", "Pagamento de Boleto - M E Barreto Wanderley")],
        )
    )

    # 2 títulos em aberto com o mesmo valor de 447.50 para um único débito
    titulos_mock = [
        {
            "tituloPagarCodigo": 3153566,
            "situacao": "Aberto",
            "valor": 447.50,
            "vencimento": "2026-08-28",
            "nomeFornecedor": "M&A EQUIPAMENTOS PARA POSTOS",
        },
        {
            "tituloPagarCodigo": 3153567,
            "situacao": "Aberto",
            "valor": 447.50,
            "vencimento": "2026-09-12",
            "nomeFornecedor": "M&A EQUIPAMENTOS PARA POSTOS",
        },
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arquivo_ofx],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    assert len(previa.prontos) == 0
    assert len(previa.ambiguos) == 2
    for a in previa.ambiguos:
        assert "títulos compatíveis para o mesmo débito" in a.motivo


@pytest.mark.asyncio
async def test_dois_debitos_mesmo_titulo_vira_ambiguo(tmp_path: Path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = tmp_path / "extrato_bb.ofx"
    arquivo_ofx.write_bytes(
        _gerar_ofx_bytes(
            banco="BB",
            lancamentos=[
                ("FIT_1", "20260916", "-436.00", "Pagamento de Boleto - M E BARRETO WANDERLEY"),
                ("FIT_2", "20261007", "-436.00", "Pagamento de Boleto - M E BARRETO WANDERLEY"),
            ],
        )
    )

    titulos_mock = [
        {
            "tituloPagarCodigo": 3171987,
            "situacao": "Aberto",
            "valor": 436.00,
            "vencimento": "2026-09-16",
            "nomeFornecedor": "M&A EQUIPAMENTOS PARA POSTOS",
        }
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arquivo_ofx],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    assert len(previa.prontos) == 0
    assert len(previa.ambiguos) == 1
    assert "débitos compatíveis para o mesmo título" in previa.ambiguos[0].motivo


@pytest.mark.asyncio
async def test_pagamento_agrupado_vira_agrupado_conferir_a_mao(tmp_path: Path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = tmp_path / "extrato_bb.ofx"
    arquivo_ofx.write_bytes(
        _gerar_ofx_bytes(
            banco="BB",
            lancamentos=[("FIT_AGR", "20260920", "-600.00", "Pagamento de Boleto - IPSEP TRANSPORTE")],
        )
    )

    # Dois títulos de 300 cada do mesmo fornecedor que somam 600
    titulos_mock = [
        {
            "tituloPagarCodigo": 1,
            "situacao": "Aberto",
            "valor": 300.00,
            "vencimento": "2026-09-10",
            "nomeFornecedor": "IPSEP TRANSPORTE",
        },
        {
            "tituloPagarCodigo": 2,
            "situacao": "Aberto",
            "valor": 300.00,
            "vencimento": "2026-09-15",
            "nomeFornecedor": "IPSEP TRANSPORTE",
        },
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arquivo_ofx],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    assert len(previa.prontos) == 0
    assert len(previa.agrupados) == 2
    for ag in previa.agrupados:
        assert ag.status == "agrupado"
        assert "quita 2 títulos somados" in ag.motivo


@pytest.mark.asyncio
async def test_transferencia_propria_ou_aplicacao_ignorado(tmp_path: Path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = tmp_path / "extrato_bb.ofx"
    arquivo_ofx.write_bytes(
        _gerar_ofx_bytes(
            banco="BB",
            lancamentos=[
                ("FIT_TR", "20261002", "-3500.00", "Transferência enviada - 02/10 18:20 A POSTO CASA CAIADA LTDA"),
                ("FIT_RF", "20261005", "-2000.00", "BB Rende Fácil - Rende Facil"),
            ],
        )
    )

    titulos_mock = [
        {
            "tituloPagarCodigo": 3075737,
            "situacao": "Aberto",
            "valor": 3500.00,
            "vencimento": "2026-10-05",
            "nomeFornecedor": "SULAMERICA COMPANHIA DE SEGURO SAUDE",
        },
        {
            "tituloPagarCodigo": 400,
            "situacao": "Aberto",
            "valor": 2000.00,
            "vencimento": "2026-10-05",
            "nomeFornecedor": "SULAMERICA COMPANHIA DE SEGURO SAUDE",
        },
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arquivo_ofx],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    # Débitos de transferências próprias e aplicações não devem casar com títulos
    assert len(previa.prontos) == 0
    assert len(previa.conferir_mao) == 0
    assert len(previa.ambiguos) == 0


@pytest.mark.asyncio
async def test_apelidos_fornecedor_reconhecidos(tmp_path: Path):
    unidade = _criar_unidade_teste()
    arquivo_ofx = tmp_path / "extrato_pagbank.ofx"
    arquivo_ofx.write_bytes(
        _gerar_ofx_bytes(
            banco="PAGBANK",
            lancamentos=[
                ("FIT_VEC", "20260902", "-4475.36", "Pagamento de conta - Ictus Eng Com E Servicos Ltda"),
                ("FIT_COP", "20260902", "-58589.32", "Pagamento de Boleto - COMPANHIA PERNAMBUCANA DE GAS"),
            ],
        )
    )

    titulos_mock = [
        {
            "tituloPagarCodigo": 3166170,
            "situacao": "Aberto",
            "valor": 4475.36,
            "vencimento": "2026-09-01",
            "nomeFornecedor": "VECTOR",
        },
        {
            "tituloPagarCodigo": 3166169,
            "situacao": "Aberto",
            "valor": 58589.32,
            "vencimento": "2026-09-01",
            "nomeFornecedor": "COPERGAS",
        },
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arquivo_ofx],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    assert len(previa.prontos) == 2
    codigos = {p.titulo_codigo for p in previa.prontos}
    assert codigos == {3166170, 3166169}


@pytest.mark.asyncio
async def test_deduplicacao_por_fitid(tmp_path: Path):
    unidade = _criar_unidade_teste()
    lcto = [("FIT_UNICO", "20260914", "-1400.00", "Pagamento de Boleto - DUNAX LUBRIFICANTES LTDA")]
    # Dois arquivos com o mesmo lançamento e mesmo FITID
    arq1 = tmp_path / "extrato1.ofx"
    arq2 = tmp_path / "extrato2.ofx"
    arq1.write_bytes(_gerar_ofx_bytes(banco="BB", lancamentos=lcto))
    arq2.write_bytes(_gerar_ofx_bytes(banco="BB", lancamentos=lcto))

    titulos_mock = [
        {
            "tituloPagarCodigo": 3171998,
            "situacao": "Aberto",
            "valor": 1400.00,
            "vencimento": "2026-09-14",
            "nomeFornecedor": "DUNAX LUBRIFICANTES LTDA",
        }
    ]

    previa = await encontrar_candidatos_baixa(
        unidade=unidade,
        caminhos_extratos=[arq1, arq2],
        data_referencia=date(2026, 10, 11),
        titulos_mock=titulos_mock,
        contas_mock=_contas_mock_padrao(),
    )

    # Não deve se tornar ambíguo por causa da duplicidade do arquivo
    assert len(previa.prontos) == 1
    assert previa.prontos[0].titulo_codigo == 3171998


def test_formatar_relatorio_previa():
    previa = PreviaBaixaTitulos(
        unidade_codigo=74014,
        unidade_nome="POSTO DOZE FILIAL II",
        data_referencia=date(2026, 10, 11),
        dias_historico=120,
        prontos=(
            TituloCandidato(
                titulo_codigo=1001,
                fornecedor_nome="DUNAX LUBRIFICANTES",
                plano_contas="LUBRIFICANTES",
                vencimento=date(2026, 9, 14),
                valor=Decimal("1400.00"),
                banco="BB",
                debito_data=date(2026, 9, 14),
                debito_texto="Pagamento Boleto DUNAX",
                cd_conta=86248,
                nome_conta="BANCO 24H - DOZE FILIAL",
                status="pronto",
            ),
        ),
        conferir_mao=(),
        ambiguos=(),
        agrupados=(),
    )
    relatorio = formatar_relatorio_previa(previa)
    assert "POSTO DOZE FILIAL II (74014)" in relatorio
    assert "PRONTOS PARA BAIXAR: 1 títulos (R$ 1,400.00)" in relatorio
    assert "SOMENTE LEITURA" in relatorio
