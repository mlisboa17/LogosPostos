"""Total declarado pelo diretor; não é uma coleta do portal nem autoriza escrita."""
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field

from ..config import carregar_unidades
from ..domain.explicacao import ParteFalta
from ..domain.explicacao import ConferenciaMais
from ..domain.tempo import DataHoraLocal, agora, para_local
from .pix_cnpj import pessoa, venda_proxima
from .resumo_diario import identificar_caixa, moeda_br

DIRETORIO = Path(__file__).resolve().parents[4] / "data" / "mais_pagamentos"


class PixInformado(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    momento: DataHoraLocal
    valor: Decimal = Field(gt=0, allow_inf_nan=False, decimal_places=2)


class TotalMaisPagamentos(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    unidade: int
    dia: date
    total: Decimal = Field(ge=0, allow_inf_nan=False, decimal_places=2)
    fonte: str = "total informado pelo diretor"
    informado_em: DataHoraLocal
    pix: tuple[PixInformado, ...] = ()


def ler_valor(valor: str) -> Decimal:
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+),\d{2}", valor):
        raise ValueError("Informe o valor em reais, por exemplo 10741,86.")
    return Decimal(valor.replace(".", "").replace(",", "."))


def carregar(unidade: int, dia: date) -> TotalMaisPagamentos | None:
    caminho = DIRETORIO / str(unidade) / f"{dia.isoformat()}.json"
    try:
        texto = caminho.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        r = TotalMaisPagamentos.model_validate_json(texto)
        if r.unidade != unidade or r.dia != dia or any(p.momento.date() != dia for p in r.pix):
            raise ValueError("Escopo incorreto.")
        return r
    except ValueError:
        raise ValueError("Total Mais Pagamentos local inválido; confira unidade, dia e valores.") from None


def salvar(total: TotalMaisPagamentos) -> Path:
    if total.unidade not in carregar_unidades() or any(p.momento.date() != total.dia for p in total.pix):
        raise ValueError("Total Mais Pagamentos fora do escopo de unidade/dia.")
    caminho = DIRETORIO / str(total.unidade) / f"{total.dia.isoformat()}.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=caminho.parent, suffix=".tmp", delete=False) as f:
            temporario = Path(f.name)
            f.write(total.model_dump_json(indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, caminho)
    finally:
        if temporario and temporario.exists():
            temporario.unlink()
    return caminho


def comparar(registro, unidade, total, abastecimentos=(), itens_dinheiro=frozenset()):
    if total.unidade != registro.empresa_codigo or total.dia != registro.dia:
        raise ValueError("Total Mais Pagamentos fora do escopo do relatório.")
    caixas = registro.fechamento.caixas if registro.fechamento else ()
    modalidades = [m for a in caixas for m in a.modalidades if m.modalidade == "transfBanc"]
    if not modalidades:
        return ConferenciaMais(total=total.total, webposto=None, aviso="Transf. Crédito indisponível no caixa."), ()
    erp = sum((m.apurado for m in modalidades), Decimal(0))
    conf = ConferenciaMais(total=total.total, webposto=erp)
    if conf.diferenca == 0:
        return conf, ()
    if len(caixas) != 1:
        return conf.model_copy(update={"aviso": "Total do dia não identifica o caixa; conferir à mão, sem repartir a diferença."}), ()
    cx = caixas[0].caixa
    rotulo = identificar_caixa(unidade.apelido or unidade.nome, cx, [cx], curto=True)
    partes, usados = [], set()
    for p in total.pix:
        a = venda_proxima(abastecimentos, itens_dinheiro, total.unidade, total.dia, p.valor, p.momento)
        if a and a.caixa_codigo == cx.codigo and a.venda_codigo not in usados:
            usados.add(a.venda_codigo)
            partes.append(ParteFalta(
                referencia=f"mais:{total.dia}:{a.venda_codigo}", caixa_codigo=cx.codigo,
                descricao=f"PIX Mais Pagamentos lançado como dinheiro — {pessoa(a)}, {a.momento:%H:%M}",
                valor=p.valor, fonte=total.fonte,
                correcao=f"No caixa {rotulo}, venda {a.venda_codigo} das {a.momento:%H:%M} de {moeda_br(a.valor)} "
                         f"de {pessoa(a)}: trocar Dinheiro → Transferência Bancária / conta MAIS PAGAMENTOS.",
            ))
    restante = conf.diferenca - sum((p.valor for p in partes), Decimal(0))
    if restante:
        partes.append(ParteFalta(
            referencia=f"mais:{total.dia}:total", caixa_codigo=cx.codigo,
            descricao=f"Mais Pagamentos: portal {moeda_br(total.total)} × Transf. Crédito {moeda_br(erp)}"
                      " — frentista não identificado (total do dia, sem venda/hora)",
            valor=restante, fonte=total.fonte,
            correcao=f"No caixa {rotulo}, localizar o PIX e sua venda antes de corrigir: "
                     "trocar Dinheiro → Transferência Bancária / conta MAIS PAGAMENTOS. "
                     "Sem venda/hora não atribuo a diferença a um frentista.",
        ))
    return conf, tuple(partes)


def interpretar(texto: str, *, hoje: date | None = None, unidade_contexto: int | None = None):
    hoje = hoje or agora().date()
    match = re.fullmatch(r"Mais Pagamentos (.+?) (\d{2}/\d{2}(?:/\d{4})?) ([\d.,]+)"
                         r"(?:\s+(\d{2}:\d{2}) ([\d.,]+))?", texto.strip(), re.IGNORECASE)
    if match:
        nome, dia, valor, hora, detalhe = match.groups()
        unidades = [u for u in carregar_unidades().values()
                    if nome.casefold() in {str(u.empresa_codigo), (u.apelido or "").casefold(), u.nome.casefold()}]
        if len(unidades) != 1:
            raise ValueError("Unidade Mais Pagamentos não identificada.")
        codigo = unidades[0].empresa_codigo
    else:
        match = re.fullmatch(r"(\d{2}/\d{2}(?:/\d{4})?) (\d{2}:\d{2}) ([\d.,]+)", texto.strip())
        if not match:
            raise ValueError("Use: Mais Pagamentos Doze 14/10 10741,86 [14:35 500,00].")
        if unidade_contexto is None:
            raise ValueError("Responda ao total Mais Pagamentos do posto para identificar a unidade.")
        dia, hora, detalhe = match.groups()
        codigo, valor = unidade_contexto, None
    d = datetime.strptime(dia if len(dia) == 10 else f"{dia}/{hoje.year}", "%d/%m/%Y").date()
    anterior = carregar(codigo, d)
    if valor is None and anterior is None:
        raise ValueError("Informe primeiro o total Mais Pagamentos desta unidade e dia.")
    pix = list(anterior.pix if anterior else ())
    if hora:
        p = PixInformado(momento=para_local(datetime.combine(d, datetime.strptime(hora, "%H:%M").time())),
                         valor=ler_valor(detalhe))
        if p not in pix:
            pix.append(p)
    return TotalMaisPagamentos(unidade=codigo, dia=d, total=ler_valor(valor) if valor else anterior.total,
                               informado_em=agora(), pix=tuple(pix))
