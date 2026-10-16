"""PIX de clientes pela conta configurada, sem confundir repasses com vendas."""
from datetime import date
from pathlib import Path

from ..adapters.extrato_reader import ExtratoBancario, ler_ofx
from ..domain.cartoes import Abastecimento, CartaoErp
from ..domain.explicacao import ConferenciaPixCnpj, ParteFalta
from ..domain.models import Unidade
from .despesas_sem_lancamento import EMPRESAS_GRUPO_PADRAO, normalizar_texto

DIRETORIO_PAGBANK = Path(r"C:\Projetos\LOGOS\extratos\PAGBANK")
FORNECEDORES = ("VIBRA", "PETROBRAS", "IPIRANGA", "RAIZEN")


def ler_extratos_unidade(unidade: Unidade, dia: date, pasta: Path | None = None):
    contas = {c.conta_sufixo for c in unidade.contas_extrato if c.banco == "PAGBANK"}
    if not contas:
        return ()
    extratos = []
    for caminho in sorted((pasta or DIRETORIO_PAGBANK).glob("*.ofx")):
        extrato = ler_ofx(caminho.read_bytes())
        if (extrato.banco == "PAGBANK" and extrato.conta_sufixo in contas
                and extrato.inicio and extrato.fim and extrato.inicio <= dia <= extrato.fim):
            extratos.append(extrato)
    return tuple(extratos)


def venda_proxima(abastecimentos, itens_dinheiro, unidade, dia, valor, momento):
    if momento is None:
        return None
    vendas = {}
    for a in abastecimentos:
        if (a.empresa_codigo == unidade and a.momento.date() == dia and a.valor == valor
                and a.venda_codigo and a.caixa_codigo and a.venda_item_codigo in itens_dinheiro
                and abs((a.momento - momento).total_seconds()) <= 600):
            vendas[a.venda_codigo] = a
    return next(iter(vendas.values())) if len(vendas) == 1 else None


def pessoa(a: Abastecimento) -> str:
    return (f"{a.nome_frentista or 'nome indisponível'} ({a.frentista})"
            if a.frentista is not None else "frentista não identificado")


def conferir_pix_cnpj(unidade: Unidade, dia: date, extratos: tuple[ExtratoBancario, ...],
                      transferencias: list[CartaoErp], abastecimentos: list[Abastecimento],
                      itens_dinheiro: set[int]):
    contas = {c.conta_sufixo for c in unidade.contas_extrato if c.banco == "PAGBANK"}
    fontes = [e for e in extratos if e.banco == "PAGBANK" and e.conta_sufixo in contas
              and e.inicio and e.fim and e.inicio <= dia <= e.fim]
    if not fontes:
        return ConferenciaPixCnpj(), ()
    vistos = {}
    for e in fontes:
        for l in e.lancamentos:
            if l.data != dia:
                continue
            chave = (e.conta_sufixo, l.fitid)
            if l.fitid.startswith("TRN_"):
                raise ValueError("Extrato PIX sem FITID: não é possível deduplicar com segurança.")
            anterior = vistos.get(chave)
            if anterior and (anterior.valor, anterior.data, anterior.descricao) != (l.valor, l.data, l.descricao):
                raise ValueError("FITID conflitante nos extratos PIX da unidade.")
            vistos[chave] = l
    clientes, ignorados = [], 0
    for l in vistos.values():
        texto = normalizar_texto(l.descricao)
        if l.valor <= 0 or "PIX RECEBIDO" not in texto:
            continue
        if any(n in texto for n in (*EMPRESAS_GRUPO_PADRAO, *FORNECEDORES)):
            ignorados += 1
        else:
            clientes.append(l)
    manuais = {c.codigo: c for c in transferencias
               if c.empresa_codigo == unidade.empresa_codigo and c.momento.date() == dia
               and ("PIX CNPJ" in c.administradora.upper()
                    or ("PIX (VENDA)" in c.administradora.upper()
                        and "PAGBANK" in c.administradora.upper()))}
    proximos = {
        l.fitid: [c for c in manuais.values() if l.momento and c.valor == l.valor
                 and abs((c.momento - l.momento).total_seconds()) <= 600]
        for l in clientes
    }
    casados, usados, partes, pendencias = 0, set(), [], []
    vendas_usadas = set()
    for l in clientes:
        candidatos = proximos[l.fitid]
        if len(candidatos) == 1 and sum(candidatos[0] in cs for cs in proximos.values()) == 1:
            casados += 1
            usados.add(candidatos[0].codigo)
            continue
        a = venda_proxima(abastecimentos, itens_dinheiro, unidade.empresa_codigo, dia, l.valor, l.momento)
        if candidatos or a is None or a.venda_codigo in vendas_usadas:
            pendencias.append(f"PIX CNPJ {l.valor:.2f}: conferir valor/hora; venda ou transferência não identificada com segurança.")
            continue
        vendas_usadas.add(a.venda_codigo)
        pendencias.append(f"PIX CNPJ {l.valor:.2f} não lançado: conferir venda {a.venda_codigo} de {pessoa(a)}.")
        partes.append(ParteFalta(
            referencia=f"pix-cnpj:{l.fitid}", caixa_codigo=a.caixa_codigo,
            descricao=f"PIX CNPJ não lançado — {pessoa(a)}, {a.momento:%H:%M}",
            valor=l.valor, fonte="Extrato PagBank × vendas",
            correcao=f"No caixa do dia {dia:%d/%m}, venda {a.venda_codigo} das {a.momento:%H:%M} "
                     f"de R$ {a.valor:.2f} de {pessoa(a)}: trocar Dinheiro → Transferência Bancária / conta PAGBANK.",
        ))
    pendencias.extend(f"Transferência PIX CNPJ {c.valor:.2f} de {c.responsavel}: sem PIX de cliente correspondente no extrato."
                      for codigo, c in manuais.items() if codigo not in usados)
    return ConferenciaPixCnpj(coberto=True, clientes=len(clientes), ignorados=ignorados, casados=casados,
                             pendencias=tuple(pendencias), fontes=tuple(e.sha256 for e in fontes)), tuple(partes)
