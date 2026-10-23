"""Leitura de NF-e (modelo 55), com ou sem protocolo (`nfeProc`/`NFe`)."""
from __future__ import annotations

from decimal import Decimal

from ._xml import Leitor, data_hora, nome_local, raiz
from .modelos import DocumentoFiscal, Impostos, Item, Transporte, XmlInvalido, competencia_de

NS = "http://www.portalfiscal.inf.br/nfe"
_L = Leitor(NS)
_ZERO = Decimal("0")
MOD_FRETE = {"0": "CIF", "1": "FOB", "2": "Terceiros", "3": "Próprio rem.",
             "4": "Próprio dest.", "9": "Sem frete"}
_AUTORIZADA = {"100", "150"}
_CAMPOS_MONO = ("vICMSMono", "vICMSMonoRet", "vICMSMonoOp")


def _icms_mono(det) -> Decimal | None:
    total = None
    for grupo in list(_L.no(det, "imposto/ICMS") or []):
        for campo in _CAMPOS_MONO:
            v = _L.dec(grupo, campo)
            if v is not None:
                total = (total or _ZERO) + v
    return total


def _item(det) -> Item:
    prod = _L.no(det, "prod")
    return Item(
        n_item=int(det.get("nItem") or 0),
        codigo=_L.txt(prod, "cProd") or "",
        descricao=_L.txt(prod, "xProd") or "",
        ncm=_L.txt(prod, "NCM"),
        cfop=_L.txt(prod, "CFOP"),
        cprod_anp=_L.txt(prod, "comb/cProdANP"),
        quantidade=_L.dec(prod, "qCom") or _ZERO,
        unidade=_L.txt(prod, "uCom") or "",
        valor_unitario=_L.dec(prod, "vUnCom") or _ZERO,
        valor_total=_L.dec(prod, "vProd") or _ZERO,
        icms_mono=_icms_mono(det),
    )


def _transporte(inf) -> Transporte | None:
    t = _L.no(inf, "transp")
    if t is None:
        return None
    mod = _L.txt(t, "modFrete") or "9"
    vol = _L.no(t, "vol")
    return Transporte(
        mod_frete=mod,
        mod_frete_texto=MOD_FRETE.get(mod, mod),
        transportadora_cnpj=_L.txt(t, "transporta/CNPJ") or _L.txt(t, "transporta/CPF"),
        transportadora_nome=_L.txt(t, "transporta/xNome"),
        placa=_L.txt(t, "veicTransp/placa"),
        uf_placa=_L.txt(t, "veicTransp/UF"),
        volumes=_L.dec(vol, "qVol"),
        peso_bruto=_L.dec(vol, "pesoB"),
    )


def ler_nfe(xml: bytes) -> DocumentoFiscal:
    r = raiz(xml)
    if nome_local(r) == "nfeProc":
        nfe = _L.no(r, "NFe")
        cstat = _L.txt(r, "protNFe/infProt/cStat")
    elif nome_local(r) == "NFe":
        nfe, cstat = r, None
    else:
        raise XmlInvalido("Não é uma NF-e.")
    inf = _L.no(nfe, "infNFe")
    if inf is None:
        raise XmlInvalido("NF-e sem infNFe.")
    chave = (inf.get("Id") or "").removeprefix("NFe")
    if len(chave) != 44 or not chave.isdigit():
        raise XmlInvalido("Chave da NF-e inválida.")
    ide, emit, tot = _L.no(inf, "ide"), _L.no(inf, "emit"), _L.no(inf, "total/ICMSTot")
    emissao = data_hora(_L.txt(ide, "dhEmi") or _L.txt(ide, "dEmi"), "dhEmi")
    itens = tuple(_item(d) for d in _L.nos(inf, "det"))
    return DocumentoFiscal(
        tipo="nfe",
        chave=chave,
        numero=_L.txt(ide, "nNF") or "",
        serie=_L.txt(ide, "serie"),
        emissao_em=emissao,
        competencia=competencia_de(emissao),
        emitente_cnpj=_L.txt(emit, "CNPJ") or _L.txt(emit, "CPF") or "",
        emitente_nome=_L.txt(emit, "xNome") or "",
        destinatario_cnpj=_L.txt(inf, "dest/CNPJ") or _L.txt(inf, "dest/CPF"),
        valor_total=_L.dec(tot, "vNF") or _ZERO,
        impostos=Impostos(
            icms=_L.dec(tot, "vICMS") or _ZERO,
            icms_st=_L.dec(tot, "vST") or _ZERO,
            ipi=_L.dec(tot, "vIPI") or _ZERO,
            frete=_L.dec(tot, "vFrete") or _ZERO,
        ),
        situacao="autorizada" if cstat in _AUTORIZADA else "so_resumo",
        combustivel=any(i.cprod_anp for i in itens),
        itens=itens,
        transporte=_transporte(inf),
    )
