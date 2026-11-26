"""
Tax Advisor IA - Auditor tributário permanente.

Valida e monitora:
- NCM (Nomenclatura Comum do Mercosul)
- CEST (Código Especificador da Substituição Tributária)
- CST (Código de Situação Tributária)
- CFOP (Código Fiscal de Operações)
- ICMS, PIS, COFINS

Objetivo: Identificar riscos fiscais e oportunidades de otimização tributária.
Risco evitado = redução de multas, juros e retrabalho.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class TaxAdvisorAnalyzer:
    """Auditor tributário de produtos e operações"""

    def __init__(self, webposto_client, db_client, config: dict | None = None):
        self.client = webposto_client
        self.db = db_client
        self.config = config or {
            "estado": "PE",  # Pernambuco - customizar por filial
            "regime": "SIMPLES",  # Regime tributário
        }

        # Tabelas de referência (devem vir do WebPostos ou BD)
        self.ncm_validos = self._load_valid_ncm()
        self.cest_vigentes = self._load_valid_cest()
        self.cst_icms = self._load_valid_cst_icms()
        self.icms_rates = self._load_icms_rates()

    # ========== 1. VALIDAR NCM ==========

    async def validate_ncm(self, produto_id: str, ncm: str) -> dict:
        """
        Validar NCM de um produto.

        NCM = Nomenclatura Comum do Mercosul (8 dígitos, sem dígito verificador)
        - Valida formato e presença na tabela vigente

        Retorna: validação, categoria, alíquota
        """

        problemas = []

        # 1. Validar formato
        if not ncm or len(ncm) != 8:
            problemas.append(f"NCM deve ter 8 dígitos. Recebido: {ncm}")
            return {
                "produto_id": produto_id,
                "ncm": ncm,
                "is_valid": False,
                "fonte_tabela": "exemplo_local",
                "problemas": problemas,
                "avisos": [],
            }

        if not ncm.isdigit():
            problemas.append(f"NCM deve conter apenas dígitos. Recebido: {ncm}")
            return {
                "produto_id": produto_id,
                "ncm": ncm,
                "is_valid": False,
                "fonte_tabela": "exemplo_local",
                "problemas": problemas,
                "avisos": [],
            }

        # 2. Tabela local é apenas exemplo — ausência NÃO é erro fiscal definitivo
        avisos: list[str] = []
        if ncm not in self.ncm_validos:
            avisos.append(
                f"NCM {ncm} ausente da tabela local de exemplo "
                "(fonte_tabela=exemplo_local; não constitui erro fiscal definitivo)"
            )

        # 3. Buscar informações do NCM (se houver na amostra local)
        ncm_info = self.ncm_validos.get(ncm, {})

        is_valid = len(problemas) == 0

        return {
            "produto_id": produto_id,
            "ncm": ncm,
            "is_valid": is_valid,
            "fonte_tabela": "exemplo_local",
            "categoria": ncm_info.get("categoria", "DESCONHECIDA"),
            "descricao": ncm_info.get("descricao", ""),
            "aliquota_ii": ncm_info.get("aliquota_ii", 0),  # Imposto de Importação
            "problemas": problemas,
            "avisos": avisos,
        }

    # ========== 2. VALIDAR CEST ==========

    async def validate_cest(self, produto_id: str, cest: str) -> dict:
        """
        Validar CEST (Código Especificador da Substituição Tributária).

        CEST = 7 dígitos (ou vazio se não for substituído)
        """

        problemas = []

        # CEST é opcional
        if not cest:
            return {
                "produto_id": produto_id,
                "cest": cest,
                "is_valid": True,
                "tipo": "SEM_CEST",
                "problemas": [],
            }

        # Validar formato
        if len(cest) != 7:
            problemas.append(f"CEST deve ter 7 dígitos. Recebido: {cest}")
            return {
                "produto_id": produto_id,
                "cest": cest,
                "is_valid": False,
                "problemas": problemas,
            }

        if not cest.isdigit():
            problemas.append(f"CEST deve conter apenas dígitos")

        # Verificar vigência
        if cest not in self.cest_vigentes:
            problemas.append(f"CEST {cest} não encontrado na tabela vigente")

        is_valid = len(problemas) == 0

        return {
            "produto_id": produto_id,
            "cest": cest,
            "is_valid": is_valid,
            "tipo": "COM_CEST",
            "descricao": self.cest_vigentes.get(cest, {}).get("descricao", ""),
            "problemas": problemas,
        }

    # ========== 3. VALIDAR CST ICMS ==========

    async def validate_cst_icms(
        self, produto_id: str, cst: str, regime: str = None
    ) -> dict:
        """
        Validar CST ICMS (Código de Situação Tributária).

        CST = 2 dígitos
        Varia conforme regime (Simples, Lucro Real, etc)
        """

        regime = regime or self.config.get("regime", "SIMPLES")
        problemas = []

        # Validar formato
        if not cst or len(cst) != 2:
            problemas.append(f"CST ICMS deve ter 2 dígitos. Recebido: {cst}")
            return {
                "produto_id": produto_id,
                "cst_icms": cst,
                "regime": regime,
                "is_valid": False,
                "problemas": problemas,
            }

        if not cst.isdigit():
            problemas.append("CST ICMS deve conter apenas dígitos")

        # Validar por regime
        cst_validos_por_regime = self.cst_icms.get(regime, {})
        if cst not in cst_validos_por_regime:
            problemas.append(
                f"CST {cst} não é válido para regime {regime}. "
                f"Válidos: {', '.join(cst_validos_por_regime.keys())}"
            )

        is_valid = len(problemas) == 0

        return {
            "produto_id": produto_id,
            "cst_icms": cst,
            "regime": regime,
            "is_valid": is_valid,
            "descricao": cst_validos_por_regime.get(cst, {}).get("descricao", ""),
            "problemas": problemas,
        }

    # ========== 4. DETECTAR DIVERGÊNCIAS TRIBUTÁRIAS ==========

    async def detect_tax_divergences(self, periodo_dias: int = 30) -> list[dict]:
        """
        Detectar produtos com classificação inconsistente.

        Verifica:
        - Mesmo produto com NCM diferente
        - CST não alinhado com NCM
        - CEST faltando quando deveria existir
        """

        logger.info(f"Detectando divergências tributárias ({periodo_dias} dias)...")

        divergencias = []

        # 1. Buscar notas de entrada (compras)
        data_inicial = (
            datetime.now() - __import__("datetime").timedelta(days=periodo_dias)
        ).isoformat()

        notas = await self.client.get(
            "/INTEGRACAO/V1/NOTAS_ENTRADA",
            params={"data_inicial": data_inicial},
        )

        if not notas:
            return []

        # 2. Agrupar por produto e verificar inconsistências
        produtos_ncm = {}  # produto_id -> list(ncm)
        produtos_cst = {}  # produto_id -> list(cst)

        for nota in notas:
            for item in nota.get("itens", []):
                produto_id = item.get("produto_id")
                ncm = item.get("ncm")
                cst = item.get("cst_icms")

                if produto_id:
                    if produto_id not in produtos_ncm:
                        produtos_ncm[produto_id] = set()
                    if ncm:
                        produtos_ncm[produto_id].add(ncm)

                    if produto_id not in produtos_cst:
                        produtos_cst[produto_id] = set()
                    if cst:
                        produtos_cst[produto_id].add(cst)

        # 3. Detectar inconsistências
        for produto_id, ncms in produtos_ncm.items():
            if len(ncms) > 1:
                divergencias.append(
                    {
                        "tipo": "NCM_INCONSISTENTE",
                        "produto_id": produto_id,
                        "ncms_encontrados": list(ncms),
                        "severidade": "ALTA",
                        "problema": f"Produto {produto_id} tem {len(ncms)} NCMs diferentes",
                        "recomendacao": f"Unificar NCM para {list(ncms)[0]}",
                    }
                )

        for produto_id, csts in produtos_cst.items():
            if len(csts) > 1:
                divergencias.append(
                    {
                        "tipo": "CST_INCONSISTENTE",
                        "produto_id": produto_id,
                        "csts_encontrados": list(csts),
                        "severidade": "MÉDIA",
                        "problema": f"Produto {produto_id} tem {len(csts)} CSTs diferentes",
                        "recomendacao": f"Revisar e unificar CST",
                    }
                )

        logger.info(f"Encontradas {len(divergencias)} divergências")

        return divergencias

    # ========== 5. VALIDAR ICMS/PIS/COFINS ==========

    async def validate_tax_calculation(
        self, produto_id: str, ncm: str, estado: str, base_calculo: Decimal
    ) -> dict:
        """
        Validar cálculo de ICMS, PIS, COFINS.

        Verifica se as alíquotas estão corretas e se há diferenças com tabelas
        """

        logger.info(f"Validando cálculo de impostos para {produto_id}")

        estado = estado or self.config.get("estado", "PE")

        # Buscar alíquotas
        aliquota_icms = self._get_icms_rate(ncm, estado)
        aliquota_pis = self._get_pis_rate(ncm)
        aliquota_cofins = self._get_cofins_rate(ncm)

        # Calcular
        icms = (base_calculo * Decimal(aliquota_icms)) / Decimal("100")
        pis = (base_calculo * Decimal(aliquota_pis)) / Decimal("100")
        cofins = (base_calculo * Decimal(aliquota_cofins)) / Decimal("100")

        total_impostos = icms + pis + cofins
        margem_liquida = base_calculo - total_impostos

        return {
            "produto_id": produto_id,
            "base_calculo": float(base_calculo),
            "aliquota_icms": aliquota_icms,
            "aliquota_pis": aliquota_pis,
            "aliquota_cofins": aliquota_cofins,
            "icms": float(icms),
            "pis": float(pis),
            "cofins": float(cofins),
            "total_impostos": float(total_impostos),
            "margem_liquida": float(margem_liquida),
            "percentual_impostos": float((total_impostos / base_calculo * 100))
            if base_calculo > 0
            else 0,
        }

    # ========== 6. DETECTAR PRODUTOS SEM CLASSIFICAÇÃO ==========

    async def find_unclassified_products(self) -> list[dict]:
        """
        Encontrar produtos sem NCM/CEST/CST adequado.

        Produtos que nunca tiveram documentação tributária preenchida.
        """

        logger.info("Procurando produtos sem classificação tributária...")

        # 1. Buscar todos produtos
        produtos = await self.client.get("/INTEGRACAO/V1/PRODUTOS")

        if not produtos:
            return []

        sem_classificacao = []

        for produto in produtos:
            produto_id = produto.get("produto_id")
            ncm = produto.get("ncm")
            cest = produto.get("cest")

            # Marcar se falta classificação
            if not ncm or ncm == "" or ncm == "00000000":
                sem_classificacao.append(
                    {
                        "produto_id": produto_id,
                        "descricao": produto.get("descricao", ""),
                        "tipo_falta": "NCM_FALTANDO",
                        "severidade": "ALTA",
                        "recomendacao": "Classificar produto com NCM válido",
                    }
                )

        logger.info(f"Encontrados {len(sem_classificacao)} produtos sem classificação")

        return sem_classificacao

    # ========== 7. GERAR RELATÓRIO EXECUTIVO ==========

    async def generate_tax_audit_report(self) -> dict:
        """
        Gerar relatório consolidado de auditoria tributária.

        Inclui:
        - Divergências encontradas
        - Produtos sem classificação
        - Risco tributário estimado
        - Ações recomendadas
        """

        logger.info("Gerando relatório de auditoria tributária...")

        # 1. Executar validações
        divergencias = await self.detect_tax_divergences()
        sem_classificacao = await self.find_unclassified_products()

        # 2. Consolidar problemas
        problemas_criticos = len([d for d in divergencias if d["severidade"] == "ALTA"])
        problemas_totais = len(divergencias) + len(sem_classificacao)

        # 3. Estimar risco fiscal
        # Cada divergência alta = R$ 5k de risco potencial
        risco_fiscal_estimado = problemas_criticos * 5000

        # 4. Próximas ações
        acoes = []
        if divergencias:
            acoes.append(f"Corrigir {len(divergencias)} divergências de classificação")
        if sem_classificacao:
            acoes.append(
                f"Classificar {len(sem_classificacao)} produtos sem NCM/CEST"
            )
        if not acoes:
            acoes.append("Auditoria tributária OK - manter monitoramento")

        report = {
            "data_audit": datetime.now().isoformat(),
            "periodo": "últimos 30 dias",
            "estado": self.config.get("estado", "PE"),
            "regime": self.config.get("regime", "SIMPLES"),
            "problemas_encontrados": problemas_totais,
            "problemas_criticos": problemas_criticos,
            "divergencias": divergencias[:20],  # Top 20
            "produtos_sem_classificacao": len(sem_classificacao),
            "risco_fiscal_estimado": risco_fiscal_estimado,
            "recomendacoes": acoes,
            "status": "CRÍTICO" if problemas_criticos > 0 else "OK",
        }

        return report

    # ========== FUNÇÕES AUXILIARES ==========

    def _load_valid_ncm(self) -> dict:
        """Carregar tabela de NCMs válidos"""
        # TODO: Carregar do WebPostos ou BD
        # Por enquanto retorna exemplo
        return {
            "27160000": {"categoria": "COMBUSTÍVEL", "descricao": "Óleos minerais"},
            "34021000": {
                "categoria": "LIMPEZA",
                "descricao": "Preparações tensoativas",
            },
            "22029000": {
                "categoria": "BEBIDA",
                "descricao": "Água mineral e gaseificada",
            },
        }

    def _load_valid_cest(self) -> dict:
        """Carregar tabela de CEST vigentes"""
        return {
            "0100100": {"descricao": "Combustível - Gasolina"},
            "0100300": {"descricao": "Combustível - Diesel"},
        }

    def _load_valid_cst_icms(self) -> dict:
        """Carregar CST válidos por regime"""
        return {
            "SIMPLES": {
                "00": {"descricao": "Tributada integralmente"},
                "20": {"descricao": "Isenta"},
                "41": {"descricao": "Não tributada"},
            },
            "LUCRO_REAL": {
                "00": {"descricao": "Tributada integralmente"},
                "10": {"descricao": "Tributada com substituição"},
            },
        }

    def _load_icms_rates(self) -> dict:
        """Carregar alíquotas de ICMS"""
        return {
            "PE": {
                "27160000": 12.0,  # Combustível
                "34021000": 18.0,  # Limpeza
            }
        }

    def _get_icms_rate(self, ncm: str, estado: str) -> float:
        """Obter alíquota ICMS"""
        return self.icms_rates.get(estado, {}).get(ncm, 0.0)

    def _get_pis_rate(self, ncm: str) -> float:
        """Obter alíquota PIS"""
        # Simplificado: 1.65% para maioria dos produtos
        return 1.65

    def _get_cofins_rate(self, ncm: str) -> float:
        """Obter alíquota COFINS"""
        # Simplificado: 7.6% para maioria dos produtos
        return 7.6
