"""CLI para identificação de despesas bancárias sem lançamento no ERP (somente leitura).

Exemplo:
    python -m src.jobs.despesas_avulsas --unidade 74014 --de 01/08/2026 --ate 30/09/2026
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from src.modules.cash_reconciliation.application.despesas_sem_lancamento import (
    DespesaAvulsa,
    EvidenciaTriagem,
    ResumoDespesasAvulsas,
    formatar_resumo_terminal,
    gerar_planilha_despesas_xlsx,
    identificar_despesas_sem_lancamento,
    resolver_caminhos_extratos_padrao,
)
from src.modules.cash_reconciliation.config import carregar_unidades


@dataclass(frozen=True)
class SnapshotLocal:
    endpoint: str
    empresa_codigo: int
    data_inicial: date
    data_final: date
    capturado_em: datetime
    origem_atualizada_em: datetime
    sha256: str
    declaracao_cobertura: str
    status_cobertura: str = "COBERTURA_NAO_VERIFICADA"


def criar_demo_sintetica(
    data_de: date, data_ate: date, referencia: datetime,
) -> tuple[ResumoDespesasAvulsas, SnapshotLocal, SnapshotLocal]:
    if data_de > data_ate:
        raise ValueError("Período sintético invertido.")
    valor = Decimal("125.600000000000000001")
    data_amostra = min(data_de + timedelta(days=14), data_ate)
    hashes = [hashlib.sha256(f"OFX sintetico {n:03d}".encode()).hexdigest() for n in range(1, 6)]
    origens = tuple(f"OFX-SINTETICO-{n:03d}.ofx:{sha}" for n, sha in enumerate(hashes, 1))
    descricao = "PIX ENVIADO - FAVORECIDO FICTICIO"
    resumo = ResumoDespesasAvulsas(
        unidade_codigo=0, unidade_nome="EMPRESA-SINTETICA-001",
        data_de=data_de, data_ate=data_ate,
        despesas=(DespesaAvulsa(
            data=data_amostra, banco="BANCO-FICTICIO", conta_sufixo="CONTA-SINTETICA",
            valor=valor, fitid="FITID-SINTETICO-001", favorecido="FAVORECIDO FICTICIO",
            descricao_extrato=descricao, tipo="PIX pessoa",
            sugestao_plano_codigo=None, sugestao_plano_nome="",
            sugestao_centro_codigo=None, sugestao_centro_nome="",
            sugestao_fornecedor_codigo=None, sugestao_fornecedor_nome="",
            origem_sugestao="pendente de evidência; revisão humana obrigatória",
            observacao="Candidato provável; não confirmado como despesa sem lançamento.",
            empresa_codigo=0, conta_webposto_codigo=0,
            origem_extrato=origens[0], hash_extrato=hashes[0],
            evidencia_conciliacao=(
                "Cobertura ERP não verificada; candidato pendente de revisão humana. "
                "Não é possível concluir conciliação ou ausência de lançamento."
            ),
        ),),
        total_geral=valor, totais_por_tipo={"PIX pessoa": (1, valor)},
        debitos_ignorados_qtd=0, debitos_ignorados_total=Decimal("0"),
        debitos_registrados_qtd=0, debitos_registrados_total=Decimal("0"),
        movimentacoes_auditadas=(EvidenciaTriagem(
            empresa_codigo=0, conta_webposto_codigo=0, banco="BANCO-FICTICIO",
            conta_sufixo="CONTA-SINTETICA", data=data_amostra, valor=valor,
            fitid="FITID-SINTETICO-002", origem="OFX:BANCO-FICTICIO",
            origem_extrato=origens[1], hash_extrato=hashes[1], descricao=descricao,
            classificacao="CLASSIFICACAO_DESCONHECIDA", status="AMBIGUO",
            evidencia_conciliacao="FITID repetido com dados divergentes entre extratos.",
            origens_extrato=origens[1:3],
        ),),
        fontes_nao_mapeadas=(origens[3],), fontes_cobertura_incompleta=(origens[4],),
    )
    snapshots: list[SnapshotLocal] = []
    for nome, inicio, fim in (
        ("TITULOS_PAGAR", data_de - timedelta(days=45), data_ate + timedelta(days=45)),
        ("MOVIMENTOS_CONTA", data_de, data_ate),
    ):
        snapshots.append(SnapshotLocal(
            endpoint=f"/INTEGRACAO/V1/{nome}", empresa_codigo=0,
            data_inicial=inicio, data_final=fim,
            capturado_em=referencia - timedelta(minutes=2),
            origem_atualizada_em=referencia - timedelta(minutes=3),
            sha256=hashlib.sha256(f"snapshot sintetico {nome}".encode()).hexdigest(),
            declaracao_cobertura="DECLARADA" if nome == "TITULOS_PAGAR" else "NAO_DECLARADA",
        ))
    return resumo, snapshots[0], snapshots[1]


def _json_valor(valor: object) -> str:
    if isinstance(valor, Decimal):
        return format(valor, "f")
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    raise TypeError(f"Tipo não suportado no relatório FIN-02: {type(valor).__name__}.")


def serializar_relatorio_json(
    resumo: ResumoDespesasAvulsas,
    snapshot_titulos: SnapshotLocal,
    snapshot_movimentos: SnapshotLocal,
    *,
    referencia_temporal: datetime,
    max_idade_horas: int,
) -> str:
    """Exporta somente a amostra tipada, sem consultar ou interpretar dados operacionais."""
    if referencia_temporal.utcoffset() is None:
        raise ValueError("Referência temporal deve conter fuso.")
    if type(max_idade_horas) is not int or not 1 <= max_idade_horas <= 168:
        raise ValueError("Idade máxima deve estar entre 1 e 168 horas.")
    esperado, titulos, movimentos = criar_demo_sintetica(
        resumo.data_de, resumo.data_ate, referencia_temporal,
    )
    if (
        type(resumo.triagem_completa) is not bool
        or not set(resumo.fontes_nao_mapeadas).issubset(esperado.fontes_nao_mapeadas)
        or not set(resumo.fontes_cobertura_incompleta).issubset(esperado.fontes_cobertura_incompleta)
        or resumo != replace(
            esperado, triagem_completa=resumo.triagem_completa,
            fontes_nao_mapeadas=resumo.fontes_nao_mapeadas,
            fontes_cobertura_incompleta=resumo.fontes_cobertura_incompleta,
        )
    ):
        raise ValueError("O relatório não corresponde à amostra sintética permitida.")
    snapshots = {"titulos": snapshot_titulos, "movimentos": snapshot_movimentos}
    for nome, snapshot, modelo in (
        ("titulos", snapshot_titulos, titulos),
        ("movimentos", snapshot_movimentos, movimentos),
    ):
        if snapshot != modelo:
            raise ValueError(f"Metadados do snapshot de {nome} incompatíveis ou desatualizados.")
    payload = {
        "schema_version": 1, "sintetico": True, "cnpj_sintetico": "00.000.000/0000-00",
        "referencia_temporal": referencia_temporal, "max_idade_horas": max_idade_horas,
        "snapshots": {nome: asdict(snapshot) for nome, snapshot in snapshots.items()},
        "resumo": asdict(resumo),
    }
    return json.dumps(payload, default=_json_valor, ensure_ascii=False, sort_keys=True, indent=2)


def gravar_relatorio_json(
    resumo: ResumoDespesasAvulsas,
    snapshot_titulos: SnapshotLocal,
    snapshot_movimentos: SnapshotLocal,
    *,
    caminho_saida: Path | str,
    referencia_temporal: datetime,
    max_idade_horas: int,
) -> Path:
    caminho = Path(caminho_saida)
    if caminho.suffix.lower() != ".json":
        raise ValueError("O relatório exige extensão .json.")
    conteudo = serializar_relatorio_json(
        resumo, snapshot_titulos, snapshot_movimentos,
        referencia_temporal=referencia_temporal, max_idade_horas=max_idade_horas,
    )
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo + "\n", encoding="utf-8")
    return caminho


def _executar_demo(
    data_de: date, data_ate: date, *, caminho_json: str | None,
    caminho_xlsx: str, referencia_temporal: datetime, max_idade_horas: int,
) -> int:
    resumo, titulos, movimentos = criar_demo_sintetica(data_de, data_ate, referencia_temporal)
    serializar_relatorio_json(
        resumo, titulos, movimentos, referencia_temporal=referencia_temporal,
        max_idade_horas=max_idade_horas,
    )
    xlsx = Path(caminho_xlsx)
    if xlsx.suffix.lower() != ".xlsx":
        raise ValueError("A planilha exige extensão .xlsx.")
    if caminho_json and Path(caminho_json).resolve() == xlsx.resolve():
        raise ValueError("JSON e XLSX não podem usar o mesmo caminho.")
    if caminho_json and Path(caminho_json).suffix.lower() != ".json":
        raise ValueError("O relatório exige extensão .json.")
    gerar_planilha_despesas_xlsx(resumo, xlsx, sintetico=True)
    if caminho_json:
        gravar_relatorio_json(
            resumo, titulos, movimentos, caminho_saida=caminho_json,
            referencia_temporal=referencia_temporal, max_idade_horas=max_idade_horas,
        )
    print("DEMONSTRAÇÃO — DADOS SINTÉTICOS; COBERTURA_NAO_VERIFICADA; sem operação financeira.")
    return 0


def _parse_data_br(val: str) -> date:
    """Converte dd/mm/aaaa ou aaaa-mm-dd em objeto date."""
    val = val.strip()
    if "/" in val:
        return datetime.strptime(val, "%d/%m/%Y").date()
    return date.fromisoformat(val)


async def _executar(
    empresa_codigo: int,
    data_de: date,
    data_ate: date,
    caminhos_extratos: list[str] | None = None,
    top_n: int = 20,
) -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    unidades = carregar_unidades()
    unidade = unidades.get(empresa_codigo)
    if not unidade:
        print(f"Erro: unidade {empresa_codigo} não encontrada no cadastro.", file=sys.stderr)
        return 1

    rotas = caminhos_extratos
    if not rotas:
        rotas_p = resolver_caminhos_extratos_padrao(empresa_codigo)
        rotas = [str(p) for p in rotas_p]
        if not rotas:
            print(
                f"Aviso: nenhum extrato padrão encontrado para a unidade {empresa_codigo} "
                "em C:/Projetos/LOGOS/extratos/.",
                file=sys.stderr,
            )

    print(
        f"Analisando despesas sem lançamento para {unidade.nome} ({empresa_codigo}) "
        f"de {data_de.strftime('%d/%m/%Y')} a {data_ate.strftime('%d/%m/%Y')}...\n"
    )

    resumo = await identificar_despesas_sem_lancamento(
        unidade=unidade,
        data_de=data_de,
        data_ate=data_ate,
        caminhos_extratos=rotas,
    )

    # 1. Imprime relatório no terminal
    relatorio_txt = formatar_resumo_terminal(resumo, top_n=top_n)
    print(relatorio_txt)

    # 2. Salva planilha XLSX em data/despesas_avulsas/
    de_str = data_de.strftime("%Y%m%d")
    ate_str = data_ate.strftime("%Y%m%d")
    caminho_xlsx = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "despesas_avulsas"
        / f"despesas_avulsas_{empresa_codigo}_{de_str}_{ate_str}.xlsx"
    )
    salvo = gerar_planilha_despesas_xlsx(resumo, caminho_xlsx)
    print(f"\nPlanilha Excel gerada com sucesso em: {salvo}\n")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identifica débitos no extrato bancário sem lançamento no webPosto (somente leitura)."
    )
    parser.add_argument(
        "--unidade",
        type=int,
        default=74014,
        help="Código da empresa no webPosto (padrão: 74014 - Doze)",
    )
    parser.add_argument(
        "--de",
        type=str,
        required=True,
        help="Data inicial no formato dd/mm/aaaa",
    )
    parser.add_argument(
        "--ate",
        type=str,
        required=True,
        help="Data final no formato dd/mm/aaaa",
    )
    parser.add_argument(
        "--extrato",
        action="append",
        dest="extratos",
        help="Caminho de arquivo OFX (pode ser passado múltiplas vezes; se omitido, busca padrão da unidade)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Quantidade de maiores despesas a exibir no terminal (padrão: 20)",
    )
    parser.add_argument("--demo-sintetica", action="store_true", help="Somente amostra fictícia local")
    parser.add_argument("--json-saida", help="JSON opcional, exclusivo de --demo-sintetica")
    parser.add_argument("--xlsx-saida", help="XLSX sintético local")
    parser.add_argument("--referencia-temporal", help="Timestamp ISO-8601 com fuso")
    parser.add_argument("--max-idade-horas", type=int)

    args = parser.parse_args()
    if any(
        valor is not None and not valor.strip()
        for valor in (args.json_saida, args.xlsx_saida, args.referencia_temporal)
    ):
        parser.error("Caminhos e referência demonstrativa não podem ser vazios.")

    try:
        data_de = _parse_data_br(args.de)
        data_ate = _parse_data_br(args.ate)
    except Exception as exc:
        print(f"Erro ao interpretar datas: {exc}. Utilize o formato dd/mm/aaaa.", file=sys.stderr)
        sys.exit(1)

    if data_de > data_ate:
        print("Erro: data inicial (--de) não pode ser posterior à data final (--ate).", file=sys.stderr)
        sys.exit(1)

    if args.demo_sintetica:
        if args.extratos or any(
            "--unidade".startswith(arg.split("=")[0])
            for arg in sys.argv[1:] if arg.startswith("--")
        ):
            parser.error("A demonstração não aceita unidade ou extratos operacionais.")
        try:
            referencia = (
                datetime.fromisoformat(args.referencia_temporal)
                if args.referencia_temporal else datetime.now(timezone.utc)
            )
            ret = _executar_demo(
                data_de, data_ate, caminho_json=args.json_saida,
                caminho_xlsx=args.xlsx_saida or "fin02-demo-sintetica.xlsx",
                referencia_temporal=referencia,
                max_idade_horas=168 if args.max_idade_horas is None else args.max_idade_horas,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        sys.exit(ret)
    if any(valor is not None for valor in (
        args.json_saida, args.xlsx_saida, args.referencia_temporal, args.max_idade_horas,
    )):
        parser.error("Exportação demonstrativa exige --demo-sintetica; modo operacional não autorizado.")

    ret = asyncio.run(
        _executar(
            empresa_codigo=args.unidade,
            data_de=data_de,
            data_ate=data_ate,
            caminhos_extratos=args.extratos,
            top_n=args.top,
        )
    )
    sys.exit(ret)


if __name__ == "__main__":
    main()
