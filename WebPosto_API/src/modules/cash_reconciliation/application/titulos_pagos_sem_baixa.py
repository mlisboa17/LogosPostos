"""Aplicação para identificação de títulos a pagar já quitados no banco (somente leitura).

Regras da SPRINT BAIXA_00 (PARTE A) e RN-ERP-003:
1. Ler títulos (últimos 120 dias) e extratos OFX da unidade (deduplicados por FITID);
2. Débitos já usados por títulos pagos (mesmo valor, dataPagamento +- 1 dia) saem da disputa;
3. Candidato = título 'Aberto', vencido, com um único débito de valor exato, data entre
   vencimento -10 e +40 dias e nome do fornecedor no texto do extrato (palavras >= 4 letras,
   sem acento, excluindo termos corporativos genéricos).
   - Transferências próprias (Casa Caiada, Posto Doze, etc.) e aplicações bancárias nunca quitam título;
   - Valor exato sem nome -> 'conferir à mão' (não baixa);
   - Dois títulos para o mesmo débito, ou dois débitos para o mesmo título -> 'ambíguo' (não baixa);
   - Pagamento agrupado (1 débito = soma de títulos em aberto) -> 'agrupado — conferir à mão';
4. Conta da baixa resolvida pelo mapa da unidade em units.json conferido com V1/CONTAS;
5. Prévia somente leitura: totais por grupo (pronto / conferir à mão / ambíguo / agrupado).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

import httpx

from ..adapters.extrato_reader import ExtratoBancario, LancamentoBancario, ler_arquivo
from ..adapters.webposto_http import paginar
from ..domain.models import Unidade
from ..domain.tempo import hoje as hoje_data, formatar_data

logger = logging.getLogger(__name__)

STOP_WORDS_GENERICAS = {
    "LTDA", "EIRELI", "S/A", "SA", "COMERCIO", "SERVICOS", "SERVICO",
    "TRANSPORTE", "TRANSPORTES", "COMBUSTIVEIS", "COMBUSTIVEL",
    "POSTO", "POSTOS", "AUTO", "BRASIL", "ENERGIA", "DISTRIBUIDORA",
    "ASSOCIADOS", "EMPRESAS", "VAREJO", "FILIAL", "ME", "EPP",
}

PROPRIAS_EMPRESAS = {
    "CASA CAIADA", "POSTO DOZE", "DOZE FILIAL", "CONVENIENCIA 24",
    "POSTO VIP", "POSTO REAL", "ABREU E LIMA",
}

APLICACOES_BANCARIAS = {
    "RENDE FACIL", "RENDA FIXA", "CDB", "OUROCAP", "POUPANCA", "APLICACAO",
}

APELIDOS_FORNECEDORES_PADRAO = {
    "VECTOR": ["ICTUS", "ICTUS ENG"],
    "COPERGAS": ["COMPANHIA PERNAMBUCANA", "PERNAMBUCANA DE GAS"],
    "INMETRO": ["INSTITUTO NACIONAL", "METROLOGIA", "METROLOG"],
    "M&A EQUIPAMENTOS PARA POSTOS": ["M E BARRETO", "BARRETO", "WANDERLEY"],
    "SINDCOMBUSTIVEIS": ["SIND DO COM VAREJ", "SINDCOMBUSTIVEIS"],
}


def normalizar_texto(txt: str | None) -> str:
    if not txt:
        return ""
    t = unicodedata.normalize("NFKD", str(txt)).encode("ASCII", "ignore").decode("ASCII")
    return t.upper().strip()


def eh_transferencia_propria_ou_aplicacao(desc: str) -> bool:
    d = normalizar_texto(desc)
    for emp in PROPRIAS_EMPRESAS:
        if emp in d:
            return True
    for app in APLICACOES_BANCARIAS:
        if app in d:
            return True
    return False


def extrair_palavras_chave(
    nome: str,
    apelidos: Sequence[str] | None = None,
    stop_words: set[str] = STOP_WORDS_GENERICAS,
) -> list[str]:
    palavras: set[str] = set()
    for p in re.findall(r"[A-Z0-9]{4,}", normalizar_texto(nome)):
        if p not in stop_words:
            palavras.add(p)
    if apelidos:
        for ap in apelidos:
            for p in re.findall(r"[A-Z0-9]{4,}", normalizar_texto(ap)):
                if p not in stop_words:
                    palavras.add(p)
    return list(palavras)


def fornecedor_confere_extrato(
    nome_fornecedor: str,
    desc_extrato: str,
    razao_social: str = "",
    fantasia: str = "",
    apelidos_map: dict[str, list[str]] = APELIDOS_FORNECEDORES_PADRAO,
) -> bool:
    desc_norm = normalizar_texto(desc_extrato)
    nome_norm = normalizar_texto(nome_fornecedor)

    apelidos: list[str] = []
    for k, v in apelidos_map.items():
        k_norm = normalizar_texto(k)
        if k_norm in nome_norm or nome_norm in k_norm:
            apelidos.extend(v)

    palavras = extrair_palavras_chave(nome_fornecedor, apelidos)
    if razao_social:
        palavras.extend(extrair_palavras_chave(razao_social))
    if fantasia:
        palavras.extend(extrair_palavras_chave(fantasia))

    palavras_unicas = set(palavras)
    for p in palavras_unicas:
        if p in desc_norm:
            return True
    return False


@dataclass(frozen=True)
class TituloCandidato:
    titulo_codigo: int
    fornecedor_nome: str
    plano_contas: str
    vencimento: date
    valor: Decimal
    banco: str
    debito_data: date
    debito_texto: str
    cd_conta: int
    nome_conta: str
    status: str  # "pronto", "conferir_mao", "ambiguo", "agrupado"
    motivo: str = ""


@dataclass(frozen=True)
class PreviaBaixaTitulos:
    unidade_codigo: int
    unidade_nome: str
    data_referencia: date
    dias_historico: int
    prontos: tuple[TituloCandidato, ...]
    conferir_mao: tuple[TituloCandidato, ...]
    ambiguos: tuple[TituloCandidato, ...]
    agrupados: tuple[TituloCandidato, ...]

    @property
    def total_prontos(self) -> Decimal:
        return sum((t.valor for t in self.prontos), Decimal("0"))

    @property
    def total_conferir_mao(self) -> Decimal:
        return sum((t.valor for t in self.conferir_mao), Decimal("0"))

    @property
    def total_ambiguos(self) -> Decimal:
        return sum((t.valor for t in self.ambiguos), Decimal("0"))

    @property
    def total_agrupados(self) -> Decimal:
        return sum((t.valor for t in self.agrupados), Decimal("0"))


@dataclass
class _ItemDebito:
    banco: str
    conta_sufixo: str
    lancamento: LancamentoBancario


async def encontrar_candidatos_baixa(
    unidade: Unidade,
    caminhos_extratos: Sequence[Path | str],
    *,
    data_referencia: date | None = None,
    dias_historico: int = 120,
    client: httpx.AsyncClient | None = None,
    titulos_mock: list[dict[str, Any]] | None = None,
    contas_mock: list[dict[str, Any]] | None = None,
    fornecedores_mock: list[dict[str, Any]] | None = None,
    apelidos_map: dict[str, list[str]] = APELIDOS_FORNECEDORES_PADRAO,
) -> PreviaBaixaTitulos:
    """Encontra candidatos a baixa de títulos por extratos (somente leitura)."""
    hoje = data_referencia or hoje_data()
    data_inicial = hoje - timedelta(days=dias_historico)

    # 1. Carrega títulos do webPosto (últimos 120 dias)
    if titulos_mock is not None:
        titulos_brutos = titulos_mock
    else:
        titulos_brutos = await paginar(
            unidade,
            "/INTEGRACAO/V1/TITULOS_PAGAR",
            {
                "empresaCodigo": unidade.empresa_codigo,
                "dataInicial": data_inicial.isoformat(),
                "dataFinal": hoje.isoformat(),
            },
            client=client,
        )

    # Carrega contas cadastradas do webPosto
    if contas_mock is not None:
        contas_cadastradas = contas_mock
    else:
        contas_cadastradas = await paginar(
            unidade,
            "/INTEGRACAO/V1/CONTAS",
            {"empresaCodigo": unidade.empresa_codigo},
            client=client,
        )
    contas_ativas_map = {
        c["contaCodigo"]: c for c in contas_cadastradas if c.get("ativo", True)
    }

    # Carrega fornecedores para resolução de razão social
    if fornecedores_mock is not None:
        fornecedores_lista = fornecedores_mock
    else:
        try:
            fornecedores_lista = await paginar(
                unidade,
                "/INTEGRACAO/V1/FORNECEDORES",
                {},
                client=client,
            )
        except Exception as exc:
            logger.warning("Não foi possível carregar fornecedores: %s", exc)
            fornecedores_lista = []
    forn_map = {f["fornecedorCodigo"]: f for f in fornecedores_lista}

    # Mapa de conta por banco configurado na unidade em units.json
    conta_por_banco: dict[str, tuple[int, str]] = {}
    for ce in getattr(unidade, "contas_extrato", ()):
        c_info = contas_ativas_map.get(ce.cd_conta)
        if c_info:
            conta_por_banco[ce.banco.upper()] = (
                ce.cd_conta,
                c_info.get("descricao") or f"Conta {ce.cd_conta}",
            )

    # 1b. Ler extratos OFX (deduplicando lançamentos por FITID)
    debitos_vistos: set[tuple[str, str]] = set()
    debitos_disponiveis: list[_ItemDebito] = []

    for caminho in caminhos_extratos:
        p = Path(caminho)
        if not p.is_file():
            continue
        try:
            extrato = ler_arquivo(p)
        except Exception as exc:
            logger.warning("Falha ao ler extrato %s: %s", p, exc)
            continue

        for l in extrato.lancamentos:
            if l.eh_debito:
                chave_dedup = (extrato.banco.upper(), l.fitid)
                if chave_dedup in debitos_vistos:
                    continue
                debitos_vistos.add(chave_dedup)
                debitos_disponiveis.append(
                    _ItemDebito(
                        banco=extrato.banco.upper(),
                        conta_sufixo=extrato.conta_sufixo,
                        lancamento=l,
                    )
                )

    # 2. Débitos já usados por títulos pagos saem da disputa
    # (mesmo valor exato, dataPagamento +- 1 dia)
    titulos_pagos = [t for t in titulos_brutos if t.get("situacao") == "Pago"]
    for tp in titulos_pagos:
        val_tp = Decimal(str(tp.get("valor") or 0))
        datas_pag: list[date] = []
        if tp.get("dataPagamento"):
            try:
                datas_pag.append(date.fromisoformat(tp["dataPagamento"]))
            except ValueError:
                pass
        for pag in tp.get("pagamento") or []:
            if pag.get("dataPagamento"):
                try:
                    d_p = date.fromisoformat(pag["dataPagamento"])
                    if d_p not in datas_pag:
                        datas_pag.append(d_p)
                except ValueError:
                    pass

        for item in list(debitos_disponiveis):
            l = item.lancamento
            if abs(l.valor) == val_tp:
                for dp in datas_pag:
                    if abs((l.data - dp).days) <= 1:
                        debitos_disponiveis.remove(item)
                        break
                else:
                    continue
                break

    # 3. Candidatos = títulos 'Aberto', vencidos
    titulos_abertos = [
        t for t in titulos_brutos
        if t.get("situacao") == "Aberto" and t.get("vencimento")
    ]
    titulos_vencidos = []
    for t in titulos_abertos:
        try:
            venc = date.fromisoformat(t["vencimento"])
            if venc <= hoje:
                titulos_vencidos.append(t)
        except ValueError:
            pass

    # Detecta pagamentos agrupados (1 débito = soma de títulos em aberto do mesmo fornecedor)
    # Agrupa títulos vencidos por fornecedor
    titulos_por_fornecedor: dict[str, list[dict[str, Any]]] = {}
    for t in titulos_vencidos:
        forn_nome = t.get("nomeFornecedor") or "SEM FORNECEDOR"
        titulos_por_fornecedor.setdefault(forn_nome, []).append(t)

    titulos_agrupados_set: set[int] = set()
    candidatos_agrupados: list[TituloCandidato] = []

    for forn_nome, tits_forn in titulos_por_fornecedor.items():
        if len(tits_forn) > 1:
            soma_forn = sum((Decimal(str(t.get("valor") or 0)) for t in tits_forn), Decimal("0"))
            for item in debitos_disponiveis:
                l = item.lancamento
                if abs(l.valor) == soma_forn and not eh_transferencia_propria_ou_aplicacao(l.descricao):
                    # Identificado débito agrupado
                    cd_conta, nome_conta = conta_por_banco.get(item.banco, (0, "Conta não identificada"))
                    for t in tits_forn:
                        t_cod = t["tituloPagarCodigo"]
                        titulos_agrupados_set.add(t_cod)
                        candidatos_agrupados.append(
                            TituloCandidato(
                                titulo_codigo=t_cod,
                                fornecedor_nome=forn_nome,
                                plano_contas=t.get("planoContaGerencialDescricao") or "",
                                vencimento=date.fromisoformat(t["vencimento"]),
                                valor=Decimal(str(t.get("valor") or 0)),
                                banco=item.banco,
                                debito_data=l.data,
                                debito_texto=l.descricao,
                                cd_conta=cd_conta,
                                nome_conta=nome_conta,
                                status="agrupado",
                                motivo=f"1 débito de R$ {abs(l.valor):,.2f} quita {len(tits_forn)} títulos somados de {forn_nome}",
                            )
                        )
                    break

    # Cruzamento 1-a-1: débito de valor exato e data entre vencimento -10 e +40 dias
    matches_por_titulo: dict[int, list[_ItemDebito]] = {
        t["tituloPagarCodigo"]: [] for t in titulos_vencidos
    }
    matches_por_debito: dict[int, list[dict[str, Any]]] = {
        id(d.lancamento): [] for d in debitos_disponiveis
    }

    for t in titulos_vencidos:
        if t["tituloPagarCodigo"] in titulos_agrupados_set:
            continue
        val_t = Decimal(str(t.get("valor") or 0))
        venc = date.fromisoformat(t["vencimento"])
        d_min = venc - timedelta(days=10)
        d_max = venc + timedelta(days=40)

        for d in debitos_disponiveis:
            l = d.lancamento
            if eh_transferencia_propria_ou_aplicacao(l.descricao):
                continue
            if abs(l.valor) == val_t and d_min <= l.data <= d_max:
                matches_por_titulo[t["tituloPagarCodigo"]].append(d)
                matches_por_debito[id(l)].append(t)

    prontos: list[TituloCandidato] = []
    conferir_mao: list[TituloCandidato] = []
    ambiguos: list[TituloCandidato] = []

    for t in titulos_vencidos:
        t_cod = t["tituloPagarCodigo"]
        if t_cod in titulos_agrupados_set:
            continue

        debs = matches_por_titulo[t_cod]
        if not debs:
            continue

        val_t = Decimal(str(t.get("valor") or 0))
        venc = date.fromisoformat(t["vencimento"])
        plano = t.get("planoContaGerencialDescricao") or ""
        forn_nome = t.get("nomeFornecedor") or ""

        # Mais de um débito para o mesmo título -> ambíguo
        if len(debs) > 1:
            primeiro_deb = debs[0]
            cd_conta, nome_conta = conta_por_banco.get(primeiro_deb.banco, (0, "Indefinida"))
            ambiguos.append(
                TituloCandidato(
                    titulo_codigo=t_cod,
                    fornecedor_nome=forn_nome,
                    plano_contas=plano,
                    vencimento=venc,
                    valor=val_t,
                    banco=primeiro_deb.banco,
                    debito_data=primeiro_deb.lancamento.data,
                    debito_texto=primeiro_deb.lancamento.descricao,
                    cd_conta=cd_conta,
                    nome_conta=nome_conta,
                    status="ambiguo",
                    motivo=f"{len(debs)} débitos compatíveis para o mesmo título",
                )
            )
            continue

        deb = debs[0]
        l = deb.lancamento
        tits_compatíveis = matches_por_debito[id(l)]

        # Mais de um título para o mesmo débito -> ambíguo
        if len(tits_compatíveis) > 1:
            cd_conta, nome_conta = conta_por_banco.get(deb.banco, (0, "Indefinida"))
            ambiguos.append(
                TituloCandidato(
                    titulo_codigo=t_cod,
                    fornecedor_nome=forn_nome,
                    plano_contas=plano,
                    vencimento=venc,
                    valor=val_t,
                    banco=deb.banco,
                    debito_data=l.data,
                    debito_texto=l.descricao,
                    cd_conta=cd_conta,
                    nome_conta=nome_conta,
                    status="ambiguo",
                    motivo=f"{len(tits_compatíveis)} títulos compatíveis para o mesmo débito",
                )
            )
            continue

        # 1 título para 1 débito único
        f_info = forn_map.get(t.get("fornecedorCodigo"), {})
        razao = f_info.get("razao") or ""
        fantasia = f_info.get("fantasia") or ""
        confere_nome = fornecedor_confere_extrato(
            forn_nome, l.descricao, razao, fantasia, apelidos_map=apelidos_map
        )

        cd_conta_info = conta_por_banco.get(deb.banco)
        if not cd_conta_info:
            conferir_mao.append(
                TituloCandidato(
                    titulo_codigo=t_cod,
                    fornecedor_nome=forn_nome,
                    plano_contas=plano,
                    vencimento=venc,
                    valor=val_t,
                    banco=deb.banco,
                    debito_data=l.data,
                    debito_texto=l.descricao,
                    cd_conta=0,
                    nome_conta="Sem conta ativa no webPosto",
                    status="conferir_mao",
                    motivo=f"Conta bancária para {deb.banco} não encontrada ou inativa",
                )
            )
            continue

        cd_conta, nome_conta = cd_conta_info

        if confere_nome:
            prontos.append(
                TituloCandidato(
                    titulo_codigo=t_cod,
                    fornecedor_nome=forn_nome,
                    plano_contas=plano,
                    vencimento=venc,
                    valor=val_t,
                    banco=deb.banco,
                    debito_data=l.data,
                    debito_texto=l.descricao,
                    cd_conta=cd_conta,
                    nome_conta=nome_conta,
                    status="pronto",
                    motivo="Valor exato e nome do fornecedor presente no extrato",
                )
            )
        else:
            conferir_mao.append(
                TituloCandidato(
                    titulo_codigo=t_cod,
                    fornecedor_nome=forn_nome,
                    plano_contas=plano,
                    vencimento=venc,
                    valor=val_t,
                    banco=deb.banco,
                    debito_data=l.data,
                    debito_texto=l.descricao,
                    cd_conta=cd_conta,
                    nome_conta=nome_conta,
                    status="conferir_mao",
                    motivo="Valor exato sem confirmação do nome do fornecedor no extrato",
                )
            )

    return PreviaBaixaTitulos(
        unidade_codigo=unidade.empresa_codigo,
        unidade_nome=unidade.nome,
        data_referencia=hoje,
        dias_historico=dias_historico,
        prontos=tuple(prontos),
        conferir_mao=tuple(conferir_mao),
        ambiguos=tuple(ambiguos),
        agrupados=tuple(candidatos_agrupados),
    )


def formatar_relatorio_previa(previa: PreviaBaixaTitulos) -> str:
    """Formata a prévia completa em texto estruturado para console e chat."""
    linhas: list[str] = []
    div = "=" * 80
    subdiv = "-" * 80

    linhas.append(div)
    linhas.append("  LOGOS — PRÉVIA DE CANDIDATOS A BAIXA DE TÍTULOS PAGOS (SOMENTE LEITURA)")
    linhas.append(div)
    linhas.append(f"Unidade:         {previa.unidade_nome} ({previa.unidade_codigo})")
    linhas.append(f"Data Referência: {formatar_data(previa.data_referencia)}")
    linhas.append(f"Janela Títulos:  Últimos {previa.dias_historico} dias")
    linhas.append(div)

    # 1. Prontos para baixar
    linhas.append(f"1. PRONTOS PARA BAIXAR: {len(previa.prontos)} títulos (R$ {previa.total_prontos:,.2f})")
    linhas.append(subdiv)
    if previa.prontos:
        for p in previa.prontos:
            linhas.append(
                f"  [{p.titulo_codigo}] R$ {p.valor:>10.2f} | Venc: {formatar_data(p.vencimento)} | "
                f"Forn: {p.fornecedor_nome:<30} | Plano: {p.plano_contas:<25} | "
                f"Baixa: {p.banco} ({p.nome_conta}) em {formatar_data(p.debito_data)} | "
                f"Extrato: {p.debito_texto}"
            )
    else:
        linhas.append("  (Nenhum título pronto para baixar)")

    # 2. Conferir à mão
    linhas.append("")
    linhas.append(f"2. CONFERIR À MÃO: {len(previa.conferir_mao)} títulos (R$ {previa.total_conferir_mao:,.2f})")
    linhas.append(subdiv)
    if previa.conferir_mao:
        for m in previa.conferir_mao:
            linhas.append(
                f"  [{m.titulo_codigo}] R$ {m.valor:>10.2f} | Venc: {formatar_data(m.vencimento)} | "
                f"Forn: {m.fornecedor_nome:<30} | Motivo: {m.motivo} | "
                f"Extrato: {formatar_data(m.debito_data)} ({m.banco}) {m.debito_texto}"
            )
    else:
        linhas.append("  (Nenhum título para conferir à mão)")

    # 3. Ambíguos
    linhas.append("")
    linhas.append(f"3. AMBÍGUOS: {len(previa.ambiguos)} títulos (R$ {previa.total_ambiguos:,.2f})")
    linhas.append(subdiv)
    if previa.ambiguos:
        for a in previa.ambiguos:
            linhas.append(
                f"  [{a.titulo_codigo}] R$ {a.valor:>10.2f} | Venc: {formatar_data(a.vencimento)} | "
                f"Forn: {a.fornecedor_nome:<30} | Motivo: {a.motivo}"
            )
    else:
        linhas.append("  (Nenhum título ambíguo)")

    # 4. Agrupados — conferir à mão
    linhas.append("")
    linhas.append(f"4. AGRUPADO — CONFERIR À MÃO: {len(previa.agrupados)} títulos (R$ {previa.total_agrupados:,.2f})")
    linhas.append(subdiv)
    if previa.agrupados:
        for ag in previa.agrupados:
            linhas.append(
                f"  [{ag.titulo_codigo}] R$ {ag.valor:>10.2f} | Venc: {formatar_data(ag.vencimento)} | "
                f"Forn: {ag.fornecedor_nome:<30} | Débito: {formatar_data(ag.debito_data)} ({ag.banco}) | "
                f"Motivo: {ag.motivo}"
            )
    else:
        linhas.append("  (Nenhum pagamento agrupado detectado)")

    linhas.append(div)
    linhas.append("RESUMO:")
    linhas.append(f"  Prontos para baixar:       {len(previa.prontos):>3} títulos | R$ {previa.total_prontos:>12,.2f}")
    linhas.append(f"  Conferir à mão:            {len(previa.conferir_mao):>3} títulos | R$ {previa.total_conferir_mao:>12,.2f}")
    linhas.append(f"  Ambíguos:                  {len(previa.ambiguos):>3} títulos | R$ {previa.total_ambiguos:>12,.2f}")
    linhas.append(f"  Agrupados (conferir à mão):{len(previa.agrupados):>3} títulos | R$ {previa.total_agrupados:>12,.2f}")
    linhas.append(div)
    linhas.append("STATUS: SOMENTE LEITURA (Nenhuma alteração foi realizada no webPosto)")
    linhas.append(div)

    return "\n".join(linhas)
