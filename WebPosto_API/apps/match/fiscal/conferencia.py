"""Conferência antes do envio do pacote: o que retém o envio e o que só avisa."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from apps.match import banco, coletas
from apps.match.fiscal import repositorio as repo

AVISO_NFSE = ("NFS-e: se alguma prefeitura não envia ao sistema nacional, as notas dela só entram por Importar.")
_JANELA_ERRO = timedelta(days=3)
_LIMITE_RESUMO = timedelta(hours=48)


@dataclass(frozen=True)
class Achado:
    nivel: Literal["retem", "aviso"]
    texto: str


def _tem_chave(con, empresa) -> bool:
    posto = banco.obter_posto(con, empresa["posto_id"]) if empresa["posto_id"] else None
    return posto is not None and coletas.tem_chave_webposto(con, posto)


def conferir(con, empresa_id: int, competencia: str, agora: datetime) -> list[Achado]:
    empresa = repo.obter_empresa(con, empresa_id)
    achados: list[Achado] = []
    if empresa["posto_id"] is not None and not _tem_chave(con, empresa):
        achados.append(Achado("retem", "Empresa sem chave do webPosto: as NF-e não estão sendo capturadas. "
                                       "Cadastre a chave em Postos."))
    erros = [c for c in repo.capturas_recentes(con, empresa_id, agora - _JANELA_ERRO) if c["situacao"] == "erro"]
    if erros:
        achados.append(Achado("retem", f"A captura das notas deu erro nos últimos 3 dias ({len(erros)} vez(es)). "
                                       "Abra Buscar notas e confira a última busca."))
    docs = repo.documentos_da_competencia(con, empresa_id, competencia)
    velhos = [d for d in docs if d["situacao"] == "so_resumo"
              and datetime.fromisoformat(d["capturado_em"]) < agora - _LIMITE_RESUMO]
    if velhos:
        achados.append(Achado("retem", f"{len(velhos)} nota(s) continuam sem XML no webPosto há mais de 48 horas. "
                                       "Confira no webPosto ou envie mesmo assim."))
    for d in docs:
        if d["cte_numero"]:
            achados.append(Achado("aviso", f"CT-e {d['cte_numero']} (frete da nota {d['numero']}) citado pelo "
                                           "webPosto ainda sem XML; chega na próxima versão."))
    achados.append(Achado("aviso", AVISO_NFSE))
    return achados


def texto_retencao(achados: list[Achado]) -> str:
    return " ".join(a.texto for a in achados if a.nivel == "retem")
