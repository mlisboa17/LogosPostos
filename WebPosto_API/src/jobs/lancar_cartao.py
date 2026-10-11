"""Job CLI de prévia de lançamento de cartões no webPosto (Sprint 18a).

Uso:
  python -m src.jobs.lancar_cartao --unidade <cod> --dia dd/mm/aaaa

Nesta sprint (18a):
- Apenas prévia de leitura; NADA é enviado ao webPosto.
- A opção --confirmar sempre recusa com: 'piloto não liberado (Sprint 18b)'.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.modules.cash_reconciliation.adapters.webposto_escrita_cartao import (
    BarreiraCartaoErro,
    montar_payload_cartao,
    resolver_administradora_codigo,
    resolver_caminho_env,
)
from src.modules.cash_reconciliation.adapters.webposto_http import paginar
from src.modules.cash_reconciliation.application.classificar_recebimentos import (
    classificar_recebimentos,
)
from src.modules.cash_reconciliation.application.recebimentos import conciliar_recebimentos
from src.modules.cash_reconciliation.config import carregar_unidades

logger = logging.getLogger(__name__)


def formatar_moeda(v: Any) -> str:
    try:
        val = Decimal(str(v or 0))
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {v}"


async def coletar_propostas_do_dia(empresa_codigo: int, dia: date) -> list[Any]:
    """Coleta propostas do dia via conciliação ao vivo e propostas persistidas."""
    candidatos = []

    # 1. Tenta conciliação ao vivo
    try:
        resultado = await conciliar_recebimentos(empresa_codigo, dia)
        classificados = classificar_recebimentos(resultado)
        for c in classificados:
            if c.grupo == 2:
                candidatos.append(c)
    except Exception as exc:
        logger.warning("Falha ao conciliar ao vivo unidade=%s dia=%s: %s", empresa_codigo, dia, exc)

    # 2. Verifica se há propostas persistidas em disco para o mesmo dia
    dir_propostas = Path("data/propostas_lancamento") / str(empresa_codigo)
    if not dir_propostas.is_dir():
        dir_propostas = Path("WebPosto_API/data/propostas_lancamento") / str(empresa_codigo)

    if dir_propostas.is_dir():
        for arq in dir_propostas.glob("*.json"):
            try:
                dados = json.loads(arq.read_text(encoding="utf-8"))
                momento = dados.get("momento")
                if momento and str(momento).startswith(dia.isoformat()):
                    # Se não estiver já presente por id
                    if not any(getattr(c, "id", None) == dados.get("id") for c in candidatos):
                        candidatos.append(dados)
            except Exception:
                continue

    return candidatos


async def executar_previa(empresa_codigo: int, dia: date, confirmar: bool = False) -> int:
    """Executa a prévia de elegibilidade de cartões para a unidade e data."""
    # Barreira estrita da Sprint 18a: --confirmar é expressamente recusado
    if confirmar:
        print("ERRO: piloto não liberado (Sprint 18b)")
        return 1

    load_dotenv(resolver_caminho_env())
    unidades = carregar_unidades()
    unidade = unidades.get(empresa_codigo)
    if not unidade:
        print(f"ERRO: Unidade {empresa_codigo} não encontrada na configuração de unidades.")
        return 1

    print(f"\n{'='*75}")
    print(f" PRÉVIA DE LANÇAMENTO DE CARTÕES — UNIDADE {empresa_codigo} ({unidade.nome})")
    print(f" Data de movimento: {dia.strftime('%d/%m/%Y')} | Modo: Somente Leitura (Sprint 18a)")
    print(f"{'='*75}")

    # Consulta administradoras ativas cadastradas no webPosto
    print(f"Consultando administradoras cadastradas para {unidade.apelido}...")
    try:
        administradoras = await paginar(unidade, "/INTEGRACAO/V1/ADMINISTRADORAS", {"empresaCodigo": empresa_codigo})
        print(f"Total de administradoras cadastradas no webPosto: {len(administradoras)}")
    except Exception as exc:
        print(f"AVISO: Falha ao consultar administradoras na API: {exc}")
        administradoras = []

    # Coleta propostas
    print(f"Buscando propostas de correção para o dia {dia.strftime('%d/%m/%Y')}...")
    propostas = await coletar_propostas_do_dia(empresa_codigo, dia)
    print(f"Total de propostas encontradas: {len(propostas)}")

    elegiveis = []
    bloqueadas = []

    for prop in propostas:
        # Extrai atributos de forma uniforme
        if isinstance(prop, dict):
            prop_id = prop.get("id", "s/n")
            frentista_cod = prop.get("frentista")
            frentista_nome = prop.get("nome_frentista") or "Nome não informado"
            valor = prop.get("valor", 0)
            nsu = prop.get("nsu")
            autorizacao = prop.get("autorizacao")
            adquirente = prop.get("adquirente") or "PAGBANK"
            forma = prop.get("forma") or ""
            venda = prop.get("venda")
            caixa = prop.get("caixa")
        else:
            prop_id = getattr(prop, "id", "s/n")
            frentista_cod = getattr(prop, "frentista", None)
            frentista_nome = getattr(prop, "nome_frentista", None) or "Nome não informado"
            valor = getattr(prop, "valor", 0)
            nsu = getattr(prop, "nsu", None)
            autorizacao = getattr(prop, "autorizacao", None)
            adquirente = getattr(prop, "adquirente", "PAGBANK")
            forma = getattr(prop, "forma", "")
            venda = getattr(prop, "venda", None)
            caixa = getattr(prop, "caixa", None)

        # 1. Tenta resolver administradora
        cod_adm = None
        motivo_bloqueio = None
        try:
            cod_adm = resolver_administradora_codigo(empresa_codigo, adquirente, forma, administradoras)
        except Exception as exc:
            motivo_bloqueio = f"Administradora não resolvida: {exc}"

        # 2. Tenta montar payload estrito
        payload = None
        if not motivo_bloqueio and cod_adm:
            try:
                payload = montar_payload_cartao(
                    prop,
                    cod_adm,
                    nsu=nsu,
                    autorizacao=autorizacao,
                    venda=venda,
                    caixa=caixa,
                    frentista=frentista_cod,
                    valor=valor,
                    data_movimento=dia,
                )
            except BarreiraCartaoErro as exc:
                motivo_bloqueio = str(exc)
            except Exception as exc:
                motivo_bloqueio = f"Falha na montagem: {exc}"

        if payload and not motivo_bloqueio:
            elegiveis.append({
                "id": prop_id,
                "frentista_cod": frentista_cod,
                "frentista_nome": frentista_nome,
                "valor": valor,
                "nsu": nsu,
                "autorizacao": autorizacao,
                "administradora_cod": cod_adm,
                "forma": forma,
                "venda": venda,
                "caixa": caixa,
                "payload": payload,
            })
        else:
            bloqueadas.append({
                "id": prop_id,
                "frentista_cod": frentista_cod,
                "frentista_nome": frentista_nome,
                "valor": valor,
                "nsu": nsu,
                "forma": forma,
                "venda": venda,
                "motivo": motivo_bloqueio or "Critérios de elegibilidade não atendidos",
            })

    # Exibição
    print(f"\n{'-'*75}")
    print(f" RESULTADO DA PRÉVIA: {len(elegiveis)} ELEGÍVEIS | {len(bloqueadas)} NÃO ELEGÍVEIS")
    print(f"{'-'*75}")

    if elegiveis:
        print(f"\n[+] PROPOSTAS ELEGÍVEIS PARA LANÇAMENTO ({len(elegiveis)}):")
        for idx, item in enumerate(elegiveis, 1):
            print(f"\n  #{idx} Proposta: {item['id'][:12]}...")
            print(f"     Frentista:       {item['frentista_nome']} (código {item['frentista_cod']})")
            print(f"     Valor:           {formatar_moeda(item['valor'])}")
            print(f"     NSU:             {item['nsu']}")
            print(f"     Autorização:     {item['autorizacao']}")
            print(f"     Administradora:  código {item['administradora_cod']} ({item['forma']})")
            print(f"     Venda / Caixa:   venda {item['venda']} | caixa {item['caixa']}")
            resumo_payload = {
                "vendaCodigo": item['payload']["vendaCodigo"],
                "administradoraCodigo": item['payload']["administradoraCodigo"],
                "caixaCodigo": item['payload']["caixaCodigo"],
                "dataMovimento": item['payload']["dataMovimento"],
                "autorizacao": item['payload']["autorizacao"],
                "nsu": item['payload']["nsu"],
                "valor": item['payload']["valor"],
                "funcionarioCodigo": item['payload']["funcionarioCodigo"],
            }
            print(f"     Payload Resumido: {json.dumps(resumo_payload, ensure_ascii=False)}")
    else:
        print("\n[i] Nenhuma proposta elegível encontrada com todos os requisitos completos (NSU, autorização, venda, caixa, frentista, administradora).")

    if bloqueadas:
        print(f"\n[-] PROPOSTAS NÃO ELEGÍVEIS / BLOQUEADAS ({len(bloqueadas)}):")
        for idx, item in enumerate(bloqueadas, 1):
            print(f"  #{idx} Proposta: {item['id'][:12]}... | Valor: {formatar_moeda(item['valor'])} | Venda: {item['venda']} | Frentista: {item['frentista_nome']} ({item['frentista_cod']})")
            print(f"     Motivo da recusa: {item['motivo']}")

    print(f"\n{'='*75}")
    print(" ATENÇÃO: Nenhuma alteração foi realizada no webPosto.")
    print(" A porta de escrita está isolada e desligada. Envio real requer aprovação (Sprint 18b).")
    print(f"{'='*75}\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Prévia de lançamento de cartão no webPosto (Sprint 18a)")
    parser.add_argument("--unidade", type=int, required=True, help="Código da unidade / filial (ex: 5555, 74014)")
    parser.add_argument("--dia", type=str, required=True, help="Data no formato dd/mm/aaaa (ex: 10/10/2026)")
    parser.add_argument("--confirmar", action="store_true", help="Confirmação de envio (recusada na Sprint 18a)")

    args = parser.parse_args()

    # Validação do formato do dia
    try:
        dia = datetime.strptime(args.dia.strip(), "%d/%m/%Y").date()
    except ValueError:
        print(f"ERRO: Data inválida '{args.dia}'. Utilize o formato dd/mm/aaaa.")
        sys.exit(1)

    codigo_retorno = asyncio.run(executar_previa(args.unidade, dia, args.confirmar))
    sys.exit(codigo_retorno)


if __name__ == "__main__":
    main()
