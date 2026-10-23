"""Leitura de NFS-e do padrão nacional (Sistema Nacional NFS-e / ADN).

Competência: `dCompet` da DPS quando existe (é o mês que a contabilidade usa para serviço);
senão, a data de emissão.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from ._xml import Leitor, data_hora, nome_local, raiz
from .modelos import DocumentoFiscal, Impostos, XmlInvalido, competencia_de

NS = "http://www.sped.fazenda.gov.br/nfse"
_L = Leitor(NS)
_ZERO = Decimal("0")


def ler_nfse(xml: bytes) -> DocumentoFiscal:
    r = raiz(xml)
    if nome_local(r) != "NFSe":
        raise XmlInvalido("Não é uma NFS-e do padrão nacional.")
    inf = _L.no(r, "infNFSe")
    if inf is None:
        raise XmlInvalido("NFS-e sem infNFSe.")
    chave = re.sub(r"^\D+", "", inf.get("Id") or "")
    if not chave.isdigit():
        raise XmlInvalido("Chave da NFS-e inválida.")
    dps = _L.no(inf, "DPS/infDPS")
    emissao = data_hora(_L.txt(dps, "dhEmi") or _L.txt(inf, "dhProc"), "dhEmi")
    compet = _L.txt(dps, "dCompet")
    competencia = date.fromisoformat(compet).strftime("%Y-%m") if compet else competencia_de(emissao)
    valores = _L.no(inf, "valores")
    return DocumentoFiscal(
        tipo="nfse",
        chave=chave,
        numero=_L.txt(inf, "nNFSe") or "",
        serie=None,
        emissao_em=emissao,
        competencia=competencia,
        emitente_cnpj=_L.txt(inf, "emit/CNPJ") or _L.txt(dps, "prest/CNPJ") or "",
        emitente_nome=_L.txt(inf, "emit/xNome") or _L.txt(dps, "prest/xNome") or "",
        destinatario_cnpj=_L.txt(dps, "toma/CNPJ") or _L.txt(dps, "toma/CPF"),
        valor_total=_L.dec(dps, "valores/vServPrest/vServ") or _L.dec(valores, "vBC") or _ZERO,
        impostos=Impostos(
            iss=_L.dec(valores, "vISSQN") or _ZERO,
            retencoes=_L.dec(valores, "vTotalRet") or _ZERO,
        ),
        situacao="autorizada",
        combustivel=False,
        descricao_servico=_L.txt(dps, "serv/cServ/xDescServ"),
    )
