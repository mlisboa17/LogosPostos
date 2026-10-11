"""Aplicação para identificação de despesas pagas sem lançamento no ERP (somente leitura).

Regras da SPRINT DESPESAS_00 (PARTE A) e RN-ERP-003:
1. Ler extratos OFX da unidade (BB e todos da pasta PAGBANK; deduplicar por FITID);
2. Débito está 'registrado' se casar (valor igual ou até +10% de juros; data +-3 dias do pagamento) com:
   - baixa de título (pagamento[] de V1/TITULOS_PAGAR);
   - título em aberto (vencimento -10/+40 dias);
   - débito de V1/MOVIMENTOS_CONTA da conta.
   Cada registro casa uma vez.
3. Ignorar transferências entre empresas do grupo (Posto VIP, Casa Caiada, Igarassu,
   Posto Real, Loja de Conveniência, Posto Doze/"C C D", Alexandre, Posto Avenida),
   aplicações/resgates bancários (Rende Fácil, CDB, Ourocap, etc.), tarifas e taxas bancárias,
   e vendas/antecipações da adquirente.
4. Para cada débito não registrado (despesa avulsa):
   - Extrair data, banco, valor, favorecido e tipo (PIX pessoa, QR Code, boleto, imposto);
   - Sugerir classificação (plano de contas, centro de custo, fornecedor):
     (a) mesmo favorecido já tem título ou movimento no webPosto -> mesmo plano e centro;
     (b) palavra-chave da descrição (pedreiro, piso, fardas, FGTS, etc.);
     (c) senão -> 'a classificar'.
   - Impostos FGTS / CEF Matriz identificados com observação 'conferir - folha'.
5. Saída: tabela formatada no terminal + planilha XLSX em data/despesas_avulsas/.
"""
from __future__ import annotations

import glob
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
from ..domain.tempo import formatar_data

logger = logging.getLogger(__name__)

# Empresas do grupo que não representam despesas avulsas
EMPRESAS_GRUPO_PADRAO = {
    "CASA CAIADA",
    "POSTO DOZE",
    "DOZE FILIAL",
    "CONVENIENCIA",
    "CONVENIENCIA 24",
    "LOJA DE CONVENIENCIA",
    "POSTO VIP",
    "POSTO REAL",
    "ABREU E LIMA",
    "IGARASSU",
    "CCD",
    "C C D",
    "ALEXANDRE",
    "POSTO AVENIDA",
}

# Aplicações financeiras automáticas e investimentos
APLICACOES_BANCARIAS_PADRAO = {
    "RENDE FACIL",
    "RENDA FIXA",
    "CDB",
    "OUROCAP",
    "POUPANCA",
    "APLICACAO",
    "RESGATE",
    "BB RENDE FACIL",
    "BB AGIL",
    "APL.AUTOMATICA",
    "APL AUTOMATICA",
}

# Tarifas e taxas bancárias
TARIFAS_BANCARIAS_PADRAO = {
    "TARIFA",
    "TAXA EXTRATO",
    "TAR PACOTE",
    "TAR TED",
    "TAR PIX",
    "MANUTENCAO",
    "IOF",
    "TAXA CARTAO",
    "DEB.TARIFA",
    "SEGURO CARTAO PROTEGIDO",
    "CARTAO PROTEGIDO",
}

# Palavras societárias a ignorar na busca por similaridade de fornecedor
STOP_WORDS = {
    "LTDA", "EIRELI", "S/A", "SA", "COMERCIO", "SERVICOS", "SERVICO",
    "TRANSPORTE", "TRANSPORTES", "COMBUSTIVEIS", "COMBUSTIVEL",
    "POSTO", "POSTOS", "AUTO", "BRASIL", "ENERGIA", "DISTRIBUIDORA",
    "ASSOCIADOS", "EMPRESAS", "VAREJO", "FILIAL", "ME", "EPP",
}


def normalizar_texto(txt: str | None) -> str:
    """Remove acentuação e converte para maiúsculas."""
    if not txt:
        return ""
    t = unicodedata.normalize("NFKD", str(txt)).encode("ASCII", "ignore").decode("ASCII")
    return t.upper().strip()


def extrair_favorecido(descricao: str) -> str:
    """Extrai nome limpo do favorecido a partir do texto do extrato."""
    d = descricao.strip()
    prefixos = [
        r"^PIX ENVIADO\s*-\s*",
        r"^PIX TRANSF\s*-\s*",
        r"^QR CODE PIX ENVIADO\s*-\s*",
        r"^QR CODE PIX TRANSF\s*-\s*",
        r"^PAGAMENTO DE CONTA\s*-\s*",
        r"^COBRANCA\s*-\s*",
        r"^BOLETO\s*-\s*",
        r"^TRANSFERENCIA\s*-\s*",
    ]
    for p in prefixos:
        d = re.sub(p, "", d, flags=re.IGNORECASE).strip()

    # Se começa com dígitos de CPF/CNPJ (ex: "60.618.750 Diego Lemos")
    d = re.sub(r"^\d{2,3}[\.\d\/-]+\s*", "", d).strip()
    return d or descricao


def classificar_tipo_despesa(descricao: str) -> str:
    """Classifica o tipo do débito bancário conforme regra do negócio."""
    d = normalizar_texto(descricao)

    # 1. Impostos e guias públicas
    termos_imposto = [
        "RECEITA FEDERAL", "DARF", "CEF MATRIZ", "MUNICIPIO DO RECIFE",
        "PREFEITURA", "FGTS", "ICMS", "SIMPLES", "GPS", "INSS", "SEFAZ",
    ]
    if any(t in d for t in termos_imposto):
        return "imposto"

    # 2. QR Code PIX
    if "QR CODE" in d or "QR-CODE" in d:
        return "QR Code"

    # 3. Boletos e pagamentos de conta
    termos_boleto = [
        "PAGAMENTO DE CONTA", "COBRANCA", "BOLETO", "CONVENIO", "TITULO",
    ]
    if any(t in d for t in termos_boleto):
        return "boleto"

    # 4. PIX enviado para pessoas ou empresas avulsas
    if "PIX ENVIADO" in d or "PIX TRANSF" in d or "PIX" in d:
        return "PIX pessoa"

    return "outros"


def eh_debito_ignorado(
    descricao: str,
    empresas_grupo: set[str] = EMPRESAS_GRUPO_PADRAO,
    aplicacoes: set[str] = APLICACOES_BANCARIAS_PADRAO,
    tarifas: set[str] = TARIFAS_BANCARIAS_PADRAO,
) -> tuple[bool, str]:
    """Retorna True e o motivo se o débito for transferência do grupo, aplicação ou tarifa."""
    d = normalizar_texto(descricao)

    for emp in empresas_grupo:
        if emp in d:
            return True, f"empresa_grupo ({emp})"

    for app in aplicacoes:
        if app in d:
            return True, f"aplicacao ({app})"

    for tar in tarifas:
        if tar in d:
            return True, f"tarifa ({tar})"

    return False, ""


def texto_confere(texto_a: str, texto_b: str) -> bool:
    """Verifica se há correspondência relevante de palavras entre dois textos."""
    norm_a = normalizar_texto(texto_a)
    norm_b = normalizar_texto(texto_b)

    palavras_a = {
        p for p in re.findall(r"[A-Z0-9]{4,}", norm_a)
        if p not in STOP_WORDS
    }
    palavras_b = {
        p for p in re.findall(r"[A-Z0-9]{4,}", norm_b)
        if p not in STOP_WORDS
    }

    if not palavras_a or not palavras_b:
        return False

    return bool(palavras_a.intersection(palavras_b))


@dataclass(frozen=True)
class DespesaAvulsa:
    data: date
    banco: str
    conta_sufixo: str
    valor: Decimal
    fitid: str
    favorecido: str
    descricao_extrato: str
    tipo: str  # "PIX pessoa", "QR Code", "boleto", "imposto", "outros"
    sugestao_plano_codigo: int | None
    sugestao_plano_nome: str
    sugestao_centro_codigo: int | None
    sugestao_centro_nome: str
    sugestao_fornecedor_codigo: int | None
    sugestao_fornecedor_nome: str
    origem_sugestao: str
    observacao: str = ""


@dataclass(frozen=True)
class ResumoDespesasAvulsas:
    unidade_codigo: int
    unidade_nome: str
    data_de: date
    data_ate: date
    despesas: tuple[DespesaAvulsa, ...]
    total_geral: Decimal
    totais_por_tipo: dict[str, tuple[int, Decimal]]
    debitos_ignorados_qtd: int
    debitos_ignorados_total: Decimal
    debitos_registrados_qtd: int
    debitos_registrados_total: Decimal


def resolver_caminhos_extratos_padrao(empresa_codigo: int) -> list[Path]:
    """Resolve caminhos padrão dos extratos locais para a unidade."""
    caminhos: list[Path] = []
    base_extratos = Path("C:/Projetos/LOGOS/extratos")
    if not base_extratos.is_dir():
        return caminhos

    # 1. Extratos do Banco do Brasil
    for p in sorted(base_extratos.glob("extrato_bb_*.ofx")):
        caminhos.append(p)

    # 2. Extratos do PagBank
    pasta_pagbank = base_extratos / "PAGBANK"
    if pasta_pagbank.is_dir():
        for p in sorted(pasta_pagbank.glob("*.ofx")):
            caminhos.append(p)

    return caminhos


async def identificar_despesas_sem_lancamento(
    unidade: Unidade,
    data_de: date,
    data_ate: date,
    *,
    caminhos_extratos: Sequence[Path | str] | None = None,
    extratos_mock: Sequence[ExtratoBancario] | None = None,
    titulos_mock: Sequence[dict[str, Any]] | None = None,
    movimentos_mock: Sequence[dict[str, Any]] | None = None,
    planos_mock: Sequence[dict[str, Any]] | None = None,
    centros_mock: Sequence[dict[str, Any]] | None = None,
    fornecedores_mock: Sequence[dict[str, Any]] | None = None,
    client: httpx.AsyncClient | None = None,
) -> ResumoDespesasAvulsas:
    """Identifica débitos do extrato sem registro correspondente no webPosto."""

    # 1. Ler os extratos OFX (deduplicando por FITID)
    extratos: list[ExtratoBancario] = []
    if extratos_mock is not None:
        extratos = list(extratos_mock)
    else:
        rotas = caminhos_extratos or resolver_caminhos_extratos_padrao(unidade.empresa_codigo)
        for r in rotas:
            p = Path(r)
            if p.is_file():
                try:
                    extratos.append(ler_arquivo(p))
                except Exception as exc:
                    logger.warning("Falha ao ler extrato %s: %s", p, exc)

    debitos_extrato: list[dict[str, Any]] = []
    fitids_vistos: set[tuple[str, str]] = set()

    for ext in extratos:
        banco = ext.banco.upper()
        for l in ext.lancamentos:
            if not l.eh_debito:
                continue
            if l.data < data_de or l.data > data_ate:
                continue
            chave_dedup = (banco, l.fitid)
            if chave_dedup in fitids_vistos:
                continue
            fitids_vistos.add(chave_dedup)
            debitos_extrato.append({
                "banco": banco,
                "conta_sufixo": ext.conta_sufixo,
                "data": l.data,
                "valor": abs(l.valor),
                "fitid": l.fitid,
                "descricao": l.descricao,
                "lancamento": l,
            })

    # 2. Filtrar débitos ignorados (grupo, aplicações, tarifas)
    debitos_validos: list[dict[str, Any]] = []
    debitos_ignorados_qtd = 0
    debitos_ignorados_total = Decimal("0")

    for d in debitos_extrato:
        ign, _ = eh_debito_ignorado(d["descricao"])
        if ign:
            debitos_ignorados_qtd += 1
            debitos_ignorados_total += d["valor"]
        else:
            debitos_validos.append(d)

    # 3. Carregar dados do webPosto
    # 3.1 Títulos a pagar
    if titulos_mock is not None:
        titulos_brutos = titulos_mock
    else:
        # Busca período abrangente de títulos
        d_ini = data_de - timedelta(days=45)
        d_fim = data_ate + timedelta(days=45)
        titulos_brutos = await paginar(
            unidade,
            "/INTEGRACAO/V1/TITULOS_PAGAR",
            {
                "empresaCodigo": unidade.empresa_codigo,
                "dataInicial": d_ini.isoformat(),
                "dataFinal": d_fim.isoformat(),
            },
            client=client,
        )

    # 3.2 Movimentos de conta
    if movimentos_mock is not None:
        movimentos_brutos = movimentos_mock
    else:
        movimentos_brutos = []
        contas_extrato = getattr(unidade, "contas_extrato", ())
        codigos_contas = [ce.cd_conta for ce in contas_extrato] if contas_extrato else [None]
        for c_cod in codigos_contas:
            params: dict[str, Any] = {
                "empresaCodigo": unidade.empresa_codigo,
                "dataInicial": data_de.isoformat(),
                "dataFinal": data_ate.isoformat(),
            }
            if c_cod:
                params["contaCodigo"] = c_cod
            try:
                movs = await paginar(
                    unidade,
                    "/INTEGRACAO/V1/MOVIMENTOS_CONTA",
                    params,
                    client=client,
                )
                movimentos_brutos.extend(movs)
            except Exception as exc:
                logger.warning("Erro ao consultar movimentos de conta (%s): %s", c_cod, exc)

    # 3.3 Catálogos para classificação (Planos de Conta, Centros de Custo, Fornecedores)
    if planos_mock is not None:
        planos_lista = planos_mock
    else:
        try:
            planos_lista = await paginar(
                unidade,
                "/INTEGRACAO/V1/PLANOS_CONTA_GERENCIAL",
                {"empresaCodigo": unidade.empresa_codigo},
                client=client,
            )
        except Exception:
            planos_lista = []
    planos_map = {p["planoContaCodigo"]: p["descricao"] for p in planos_lista}

    if centros_mock is not None:
        centros_lista = centros_mock
    else:
        try:
            centros_lista = await paginar(
                unidade,
                "/INTEGRACAO/V1/CENTROS_CUSTO",
                {"empresaCodigo": unidade.empresa_codigo},
                client=client,
            )
        except Exception:
            centros_lista = []
    cc_map = {c["centroCustoCodigo"]: c["descricao"] for c in centros_lista}

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
        except Exception:
            fornecedores_lista = []
    forn_map = {f["fornecedorCodigo"]: f for f in fornecedores_lista}

    # 4. Cruzamento: Casar registros para eliminar débitos já registrados
    # Cada registro casa uma única vez
    debitos_restantes = list(debitos_validos)
    registrados_qtd = 0
    registrados_total = Decimal("0")

    # 4.1 Casamento com débitos de MOVIMENTOS_CONTA
    movs_debitos = [
        m for m in movimentos_brutos
        if "bito" in (m.get("tipo") or "").lower() or m.get("tipo") == "DEBITO"
    ]
    movs_usados: set[int] = set()

    for d in list(debitos_restantes):
        v_deb = d["valor"]
        dt_deb = d["data"]
        match_mov = None
        for m in movs_debitos:
            m_cod = m.get("codigo") or m.get("movimentoContaCodigo")
            if m_cod in movs_usados:
                continue
            v_m = Decimal(str(m.get("valor") or 0))
            if v_m <= v_deb <= (v_m * Decimal("1.10")):
                try:
                    dt_m = date.fromisoformat(m["dataMovimento"])
                    if abs((dt_deb - dt_m).days) <= 3:
                        match_mov = m
                        break
                except Exception:
                    pass
        if match_mov:
            m_cod = match_mov.get("codigo") or match_mov.get("movimentoContaCodigo")
            movs_usados.add(m_cod)
            registrados_qtd += 1
            registrados_total += v_deb
            debitos_restantes.remove(d)

    # 4.2 Casamento com baixas de títulos (pagamento[] de V1/TITULOS_PAGAR)
    baixas_usadas: set[tuple[int, int]] = set()
    for d in list(debitos_restantes):
        v_deb = d["valor"]
        dt_deb = d["data"]
        match_baixa = None
        for t in titulos_brutos:
            t_cod = t.get("tituloPagarCodigo") or t.get("tituloCodigo")
            for idx, pag in enumerate(t.get("pagamento") or []):
                chave_pag = (t_cod, idx)
                if chave_pag in baixas_usadas:
                    continue
                v_pag = Decimal(str(pag.get("valor") or 0))
                if v_pag <= v_deb <= (v_pag * Decimal("1.10")):
                    dp_str = pag.get("dataPagamento")
                    if dp_str:
                        try:
                            dt_pag = date.fromisoformat(dp_str)
                            if abs((dt_deb - dt_pag).days) <= 3:
                                match_baixa = chave_pag
                                break
                        except Exception:
                            pass
            if match_baixa:
                break
        if match_baixa:
            baixas_usadas.add(match_baixa)
            registrados_qtd += 1
            registrados_total += v_deb
            debitos_restantes.remove(d)

    # 4.3 Casamento com títulos em aberto (vencimento -10/+40 dias e fornecedor confere)
    titulos_abertos = [
        t for t in titulos_brutos
        if t.get("situacao") == "Aberto" and t.get("vencimento")
    ]
    titulos_abertos_usados: set[int] = set()

    for d in list(debitos_restantes):
        v_deb = d["valor"]
        dt_deb = d["data"]
        match_tit = None
        for t in titulos_abertos:
            t_cod = t.get("tituloPagarCodigo") or t.get("tituloCodigo")
            if t_cod in titulos_abertos_usados:
                continue
            v_t = Decimal(str(t.get("valor") or 0))
            if v_t <= v_deb <= (v_t * Decimal("1.10")):
                try:
                    venc = date.fromisoformat(t["vencimento"])
                    if (venc - timedelta(days=10)) <= dt_deb <= (venc + timedelta(days=40)):
                        forn = t.get("nomeFornecedor") or ""
                        if texto_confere(forn, d["descricao"]):
                            match_tit = t_cod
                            break
                except Exception:
                    pass
        if match_tit:
            titulos_abertos_usados.add(match_tit)
            registrados_qtd += 1
            registrados_total += v_deb
            debitos_restantes.remove(d)

    # 4.4 Casamento com pagamentos agrupados (soma de títulos do mesmo fornecedor)
    # Exemplo: frete IPSEP somado
    tits_por_forn: dict[str, list[dict[str, Any]]] = {}
    for t in titulos_abertos:
        t_cod = t.get("tituloPagarCodigo") or t.get("tituloCodigo")
        if t_cod not in titulos_abertos_usados:
            fn = t.get("nomeFornecedor") or "SEM FORNECEDOR"
            tits_por_forn.setdefault(fn, []).append(t)

    for d in list(debitos_restantes):
        v_deb = d["valor"]
        match_agrup = None
        for fn, t_list in list(tits_por_forn.items()):
            soma = sum((Decimal(str(x.get("valor") or 0)) for x in t_list), Decimal("0"))
            if soma > 0 and soma <= v_deb <= (soma * Decimal("1.10")):
                if texto_confere(fn, d["descricao"]):
                    match_agrup = (fn, t_list)
                    break
        if match_agrup:
            fn, t_list = match_agrup
            for x in t_list:
                x_cod = x.get("tituloPagarCodigo") or x.get("tituloCodigo")
                titulos_abertos_usados.add(x_cod)
            tits_por_forn.pop(fn, None)
            registrados_qtd += 1
            registrados_total += v_deb
            debitos_restantes.remove(d)

    # 5. Formatar despesas avulsas restantes e gerar sugestão de classificação
    despesas_avulsas: list[DespesaAvulsa] = []
    totais_por_tipo: dict[str, tuple[int, Decimal]] = {}

    # Ordenar por valor decrescente
    debitos_restantes.sort(key=lambda x: x["valor"], reverse=True)

    # Centro de custo padrão (PISTA) se disponível
    cc_padrao_cod = 7295 if 7295 in cc_map else (next(iter(cc_map.keys())) if cc_map else None)
    cc_padrao_nome = cc_map.get(cc_padrao_cod, "PISTA") if cc_padrao_cod else ""

    for d in debitos_restantes:
        v_deb = d["valor"]
        desc = d["descricao"]
        tipo = classificar_tipo_despesa(desc)
        favorecido = extrair_favorecido(desc)

        # Sugestão de classificação
        sug_plano_cod: int | None = None
        sug_plano_nome = ""
        sug_cc_cod: int | None = None
        sug_cc_nome = ""
        sug_forn_cod: int | None = None
        sug_forn_nome = ""
        origem_sugestao = "a classificar"
        obs = ""

        # Flag especial para FGTS / CEF Matriz
        if tipo == "imposto" and ("CEF MATRIZ" in normalizar_texto(desc) or "FGTS" in normalizar_texto(desc)):
            obs = "conferir - folha"

        # (a) Busca por mesmo favorecido em títulos a pagar
        match_hist_tit = None
        for t in titulos_brutos:
            fn = t.get("nomeFornecedor") or ""
            if texto_confere(fn, favorecido) or texto_confere(fn, desc):
                match_hist_tit = t
                break

        if match_hist_tit:
            sug_forn_cod = match_hist_tit.get("fornecedorCodigo")
            sug_forn_nome = match_hist_tit.get("nomeFornecedor") or ""
            sug_plano_cod = match_hist_tit.get("planoContaGerencialCodigo")
            sug_plano_nome = match_hist_tit.get("planoContaGerencialDescricao") or planos_map.get(sug_plano_cod, "")
            sug_cc_cod = match_hist_tit.get("centroCustoCodigo")
            sug_cc_nome = match_hist_tit.get("centroCustoDescricao") or cc_map.get(sug_cc_cod, "")
            t_cod = match_hist_tit.get("tituloPagarCodigo") or match_hist_tit.get("tituloCodigo")
            origem_sugestao = f"mesmo fornecedor em título {t_cod} ({sug_forn_nome})"
        else:
            # (b) Busca em movimentos manuais anteriores
            match_hist_mov = None
            for m in movimentos_brutos:
                desc_m = m.get("descricao") or ""
                if texto_confere(desc_m, favorecido) or texto_confere(desc_m, desc):
                    match_hist_mov = m
                    break
            if match_hist_mov:
                sug_plano_cod = match_hist_mov.get("planoContaGerencialCodigo")
                sug_plano_nome = planos_map.get(sug_plano_cod, f"Plano {sug_plano_cod}")
                sug_cc_cod = match_hist_mov.get("centroCustoCodigo")
                sug_cc_nome = cc_map.get(sug_cc_cod, f"CC {sug_cc_cod}")
                origem_sugestao = f"lançamento de {match_hist_mov.get('dataMovimento')} ({match_hist_mov.get('descricao')})"
            else:
                # (c) Regras aprendidas por palavras-chave
                d_norm = normalizar_texto(desc)
                if "PEDREIRO" in d_norm:
                    sug_plano_cod = 66430
                    sug_plano_nome = planos_map.get(66430, "PEDREIRO")
                    sug_cc_cod = cc_padrao_cod
                    sug_cc_nome = cc_padrao_nome
                    origem_sugestao = "palavra-chave 'PEDREIRO'"
                elif "PISO" in d_norm:
                    sug_plano_cod = 194968
                    sug_plano_nome = planos_map.get(194968, "MANUTENCAO PISO/CANALETAS")
                    sug_cc_cod = cc_padrao_cod
                    sug_cc_nome = cc_padrao_nome
                    origem_sugestao = "palavra-chave 'PISO'"
                elif "FARDA" in d_norm:
                    sug_plano_cod = 29057
                    sug_plano_nome = planos_map.get(29057, "FARDAS E UNIFORMES")
                    sug_cc_cod = cc_padrao_cod
                    sug_cc_nome = cc_padrao_nome
                    origem_sugestao = "palavra-chave 'FARDA'"
                elif tipo == "imposto" and "DARF" in d_norm or "RECEITA FEDERAL" in d_norm:
                    sug_plano_cod = 29128
                    sug_plano_nome = planos_map.get(29128, "H07 - DARF")
                    sug_cc_cod = cc_padrao_cod
                    sug_cc_nome = cc_padrao_nome
                    origem_sugestao = "imposto federal DARF"
                elif tipo == "imposto" and ("FGTS" in d_norm or "CEF MATRIZ" in d_norm):
                    sug_plano_cod = 29086
                    sug_plano_nome = planos_map.get(29086, "ENCARGOS SOCIAIS / FGTS")
                    sug_cc_cod = cc_padrao_cod
                    sug_cc_nome = cc_padrao_nome
                    origem_sugestao = "guia CEF Matriz / FGTS"
                else:
                    sug_plano_nome = "A CLASSIFICAR"
                    sug_cc_cod = cc_padrao_cod
                    sug_cc_nome = cc_padrao_nome
                    origem_sugestao = "a classificar"

        item = DespesaAvulsa(
            data=d["data"],
            banco=d["banco"],
            conta_sufixo=d["conta_sufixo"],
            valor=v_deb,
            fitid=d["fitid"],
            favorecido=favorecido,
            descricao_extrato=desc,
            tipo=tipo,
            sugestao_plano_codigo=sug_plano_cod,
            sugestao_plano_nome=sug_plano_nome,
            sugestao_centro_codigo=sug_cc_cod,
            sugestao_centro_nome=sug_cc_nome,
            sugestao_fornecedor_codigo=sug_forn_cod,
            sugestao_fornecedor_nome=sug_forn_nome,
            origem_sugestao=origem_sugestao,
            observacao=obs,
        )
        despesas_avulsas.append(item)

        # Atualiza totais por tipo
        qtd, tot = totais_por_tipo.get(tipo, (0, Decimal("0")))
        totais_por_tipo[tipo] = (qtd + 1, tot + v_deb)

    total_geral = sum((d.valor for d in despesas_avulsas), Decimal("0"))

    return ResumoDespesasAvulsas(
        unidade_codigo=unidade.empresa_codigo,
        unidade_nome=unidade.nome,
        data_de=data_de,
        data_ate=data_ate,
        despesas=tuple(despesas_avulsas),
        total_geral=total_geral,
        totais_por_tipo=totais_por_tipo,
        debitos_ignorados_qtd=debitos_ignorados_qtd,
        debitos_ignorados_total=debitos_ignorados_total,
        debitos_registrados_qtd=registrados_qtd,
        debitos_registrados_total=registrados_total,
    )


def gerar_planilha_despesas_xlsx(
    resumo: ResumoDespesasAvulsas,
    caminho_saida: Path | str,
) -> Path:
    """Gera planilha Excel XLSX com os débitos avulsos e resumo por tipo."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws_despesas = wb.active
    ws_despesas.title = "Despesas Avulsas"

    # Estilos
    cor_cabecalho = "1F4E78"  # Azul corporativo escuro
    fill_cabecalho = PatternFill(start_color=cor_cabecalho, end_color=cor_cabecalho, fill_type="solid")
    font_cabecalho = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_titulo = Font(name="Calibri", size=14, bold=True, color=cor_cabecalho)
    font_dado = Font(name="Calibri", size=10)
    border_fina = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # Título do relatório
    ws_despesas.merge_cells("A1:K1")
    ws_despesas["A1"] = (
        f"DESPESAS AVULSAS (SEM LANÇAMENTO NO ERP) — {resumo.unidade_nome} "
        f"({formatar_data(resumo.data_de)} a {formatar_data(resumo.data_ate)})"
    )
    ws_despesas["A1"].font = font_titulo
    ws_despesas["A1"].alignment = Alignment(horizontal="left", vertical="center")

    cabecalhos = [
        "Data", "Banco", "Conta", "Valor (R$)", "Tipo", "Favorecido",
        "Descrição Extrato", "Sugestão Plano de Contas", "Sugestão Centro de Custo",
        "Origem da Sugestão", "Observação",
    ]

    for col_idx, h in enumerate(cabecalhos, 1):
        cell = ws_despesas.cell(row=3, column=col_idx, value=h)
        cell.fill = fill_cabecalho
        cell.font = font_cabecalho
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_idx, d in enumerate(resumo.despesas, 4):
        plano_txt = (
            f"{d.sugestao_plano_nome} ({d.sugestao_plano_codigo})"
            if d.sugestao_plano_codigo else d.sugestao_plano_nome
        )
        cc_txt = (
            f"{d.sugestao_centro_nome} ({d.sugestao_centro_codigo})"
            if d.sugestao_centro_codigo else d.sugestao_centro_nome
        )
        valores = [
            formatar_data(d.data),
            d.banco,
            d.conta_sufixo,
            float(d.valor),
            d.tipo,
            d.favorecido,
            d.descricao_extrato,
            plano_txt,
            cc_txt,
            d.origem_sugestao,
            d.observacao,
        ]
        for col_idx, val in enumerate(valores, 1):
            cell = ws_despesas.cell(row=row_idx, column=col_idx, value=val)
            cell.font = font_dado
            cell.border = border_fina
            if col_idx == 4:
                cell.number_format = "R$ #,##0.00"
                cell.alignment = Alignment(horizontal="right")
            elif col_idx in (1, 2, 3, 5):
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.alignment = Alignment(horizontal="left")

    # Linha de total
    tot_row = len(resumo.despesas) + 4
    ws_despesas.cell(row=tot_row, column=3, value="TOTAL GERAL").font = Font(name="Calibri", size=11, bold=True)
    c_tot = ws_despesas.cell(row=tot_row, column=4, value=float(resumo.total_geral))
    c_tot.font = Font(name="Calibri", size=11, bold=True)
    c_tot.number_format = "R$ #,##0.00"

    # Ajuste de larguras de coluna
    for col in ws_despesas.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or "")) for cell in col[2:])
        ws_despesas.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # Aba 2: Resumo
    ws_resumo = wb.create_sheet(title="Resumo por Tipo")
    ws_resumo["A1"] = f"RESUMO POR TIPO — {resumo.unidade_nome}"
    ws_resumo["A1"].font = font_titulo
    ws_resumo["A1"].alignment = Alignment(horizontal="left", vertical="center")

    cab_res = ["Tipo de Despesa", "Quantidade", "Total (R$)", "% do Total"]
    for col_idx, h in enumerate(cab_res, 1):
        cell = ws_resumo.cell(row=3, column=col_idx, value=h)
        cell.fill = fill_cabecalho
        cell.font = font_cabecalho
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row_r = 4
    for tipo, (qtd, tot) in sorted(resumo.totais_por_tipo.items(), key=lambda x: x[1][1], reverse=True):
        pct = float(tot / resumo.total_geral) if resumo.total_geral else 0.0
        ws_resumo.cell(row=row_r, column=1, value=tipo).alignment = Alignment(horizontal="left")
        ws_resumo.cell(row=row_r, column=2, value=qtd).alignment = Alignment(horizontal="center")
        c_v = ws_resumo.cell(row=row_r, column=3, value=float(tot))
        c_v.number_format = "R$ #,##0.00"
        c_v.alignment = Alignment(horizontal="right")
        c_p = ws_resumo.cell(row=row_r, column=4, value=pct)
        c_p.number_format = "0.0%"
        c_p.alignment = Alignment(horizontal="right")
        for c in range(1, 5):
            ws_resumo.cell(row=row_r, column=c).border = border_fina
        row_r += 1

    # Totais na aba resumo
    ws_resumo.cell(row=row_r, column=1, value="TOTAL DESPESAS AVULSAS").font = Font(name="Calibri", bold=True)
    ws_resumo.cell(row=row_r, column=2, value=len(resumo.despesas)).font = Font(name="Calibri", bold=True)
    c_rt = ws_resumo.cell(row=row_r, column=3, value=float(resumo.total_geral))
    c_rt.font = Font(name="Calibri", bold=True)
    c_rt.number_format = "R$ #,##0.00"
    c_pt = ws_resumo.cell(row=row_r, column=4, value=1.0)
    c_pt.font = Font(name="Calibri", bold=True)
    c_pt.number_format = "0.0%"

    row_r += 2
    ws_resumo.cell(row=row_r, column=1, value="Débitos ignorados (grupo/aplicação/tarifa):")
    ws_resumo.cell(row=row_r, column=2, value=resumo.debitos_ignorados_qtd)
    c_ign = ws_resumo.cell(row=row_r, column=3, value=float(resumo.debitos_ignorados_total))
    c_ign.number_format = "R$ #,##0.00"

    row_r += 1
    ws_resumo.cell(row=row_r, column=1, value="Débitos já registrados no ERP:")
    ws_resumo.cell(row=row_r, column=2, value=resumo.debitos_registrados_qtd)
    c_reg = ws_resumo.cell(row=row_r, column=3, value=float(resumo.debitos_registrados_total))
    c_reg.number_format = "R$ #,##0.00"

    for col in ws_resumo.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or "")) for cell in col[2:])
        ws_resumo.column_dimensions[col_letter].width = max(max_len + 4, 15)

    p_saida = Path(caminho_saida)
    p_saida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(p_saida)
    return p_saida


def formatar_resumo_terminal(resumo: ResumoDespesasAvulsas, top_n: int = 20) -> str:
    """Formata tabela de saída para terminal e chat."""
    div = "=" * 110
    subdiv = "-" * 110
    linhas: list[str] = [
        div,
        f"DESPESAS AVULSAS PAGAS NA RUA (SEM LANÇAMENTO) — {resumo.unidade_nome} ({resumo.unidade_codigo})",
        f"Período: {formatar_data(resumo.data_de)} a {formatar_data(resumo.data_ate)}",
        div,
        "",
        f"RESUMO POR TIPO ({len(resumo.despesas)} despesas | R$ {resumo.total_geral:,.2f}):",
        subdiv,
    ]

    for tipo, (qtd, tot) in sorted(resumo.totais_por_tipo.items(), key=lambda x: x[1][1], reverse=True):
        pct = (tot / resumo.total_geral * 100) if resumo.total_geral else Decimal("0")
        linhas.append(f"  {tipo:<15} : {qtd:>2d} lançamentos | R$ {tot:>12,.2f} ({pct:>5.1f}%)")

    linhas.extend([
        subdiv,
        f"  Débitos ignorados (grupo/aplicação/tarifa): {resumo.debitos_ignorados_qtd} (R$ {resumo.debitos_ignorados_total:,.2f})",
        f"  Débitos já registrados no webPosto       : {resumo.debitos_registrados_qtd} (R$ {resumo.debitos_registrados_total:,.2f})",
        "",
        f"OS {top_n} MAIORES PAGAMENTOS AVULSOS:",
        subdiv,
    ])

    for i, d in enumerate(resumo.despesas[:top_n], 1):
        plano_txt = (
            f"{d.sugestao_plano_nome} ({d.sugestao_plano_codigo})"
            if d.sugestao_plano_codigo else d.sugestao_plano_nome
        )
        cc_txt = f"{d.sugestao_centro_nome}" if d.sugestao_centro_nome else "-"
        obs_txt = f" [{d.observacao}]" if d.observacao else ""
        linhas.append(
            f"{i:2d}. {formatar_data(d.data)} | R$ {d.valor:>10.2f} | {d.banco:<7} | {d.tipo:<10} | "
            f"Favorecido: {d.favorecido}{obs_txt}"
        )
        linhas.append(
            f"    Extrato   : {d.descricao_extrato}"
        )
        linhas.append(
            f"    Sugestão  : Plano={plano_txt} | CC={cc_txt} | Origem: {d.origem_sugestao}"
        )
        linhas.append("")

    linhas.append(div)
    return "\n".join(linhas)
