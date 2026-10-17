"""Evidence and publication policy for one read-only nightly execution."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .tempo import DataHoraLocal, agora, formatar_data, formatar_data_hora

EstadoFonte = Literal["SUCCESS", "EMPTY_VALID", "FAILED", "BLOCKED", "STALE", "NOT_COLLECTED"]
EstadoAuditoria = Literal["AUDIT_COMPLETE", "AUDIT_PARTIAL", "AUDIT_FAILED"]
EstadoEntrega = Literal["NOT_ATTEMPTED", "DELIVERY_SUCCESS", "DELIVERY_FAILED", "SKIPPED"]
VALIDOS = {"SUCCESS", "EMPTY_VALID"}


class FonteExecucao(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nome: str
    unidade: int | None = None
    obrigatoria: bool = True
    estado: EstadoFonte = "NOT_COLLECTED"
    run_id: str | None = None
    dia: date
    coletado_em: DataHoraLocal | None = None
    cobertura_inicio: date | None = None
    cobertura_fim: date | None = None
    permite_vazio: bool = False
    motivo: str | None = None
    origem: str = "consulta_remota"
    referencia_em: DataHoraLocal | None = None
    evidencias: tuple[str, ...] = ()


class ExecucaoNoturna(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    iniciado_em: DataHoraLocal = Field(default_factory=agora)
    terminado_em: DataHoraLocal | None = None
    dia: date
    versao: str = "PROD_SAFE_01"
    audit_status: EstadoAuditoria = "AUDIT_FAILED"
    delivery_status: EstadoEntrega = "NOT_ATTEMPTED"
    document_delivery_status: EstadoEntrega = "NOT_ATTEMPTED"
    erro_publicacao: str | None = None
    fontes: list[FonteExecucao] = Field(default_factory=list)

    def registrar(self, fonte: FonteExecucao) -> None:
        self.fontes = [
            f for f in self.fontes if (f.unidade, f.nome) != (fonte.unidade, fonte.nome)
        ] + [fonte]

    def avaliar(self) -> EstadoAuditoria:
        verificadas = []
        for fonte in self.fontes:
            if fonte.estado in VALIDOS:
                atual = (
                    fonte.run_id == self.run_id and fonte.dia == self.dia
                    and fonte.coletado_em is not None
                    and self.iniciado_em <= fonte.coletado_em <= (self.terminado_em or agora())
                    and fonte.cobertura_inicio is not None and fonte.cobertura_fim is not None
                    and fonte.cobertura_inicio <= self.dia <= fonte.cobertura_fim
                )
                if not atual:
                    fonte = fonte.model_copy(update={
                        "estado": "STALE", "motivo": "Evidência sem vínculo ou cobertura da execução atual.",
                    })
                elif fonte.estado == "EMPTY_VALID" and not fonte.permite_vazio:
                    fonte = fonte.model_copy(update={
                        "estado": "FAILED", "motivo": "Ausência de registros não validada pelo contrato.",
                    })
            verificadas.append(fonte)
        self.fontes = verificadas
        obrigatorias = [f for f in self.fontes if f.obrigatoria]
        if obrigatorias and all(f.estado in VALIDOS for f in obrigatorias):
            self.audit_status = "AUDIT_COMPLETE"
        elif any(f.estado in VALIDOS and f.nome != "configuracao" for f in obrigatorias):
            self.audit_status = "AUDIT_PARTIAL"
        else:
            self.audit_status = "AUDIT_FAILED"
        return self.audit_status

    def finalizar(self) -> None:
        self.terminado_em = agora()
        self.avaliar()

    def permite_publicacao(self) -> bool:
        return self.avaliar() == "AUDIT_COMPLETE" and self.terminado_em is not None

    def aviso_operacional(self, nomes: dict[int, str]) -> str:
        linhas = [
            "⚠️ LOGOS — AUDITORIA NÃO CONCLUÍDA", "",
            f"Data: {formatar_data(self.dia)}",
            f"Execução: {self.run_id[:12]} · {self.audit_status}", "",
        ]
        for fonte in self.fontes:
            if fonte.estado in VALIDOS:
                continue
            posto = nomes.get(fonte.unidade, "Execução geral") if fonte.unidade is not None else "Execução geral"
            instante = formatar_data_hora(fonte.coletado_em) if fonte.coletado_em else "indisponível"
            linhas.extend([
                f"{posto} · {fonte.nome}: {fonte.estado}",
                fonte.motivo or "Fonte não validada para esta execução.",
                f"Última evidência desta fonte: {instante}"
                + (f" · execução {fonte.run_id[:12]}" if fonte.run_id else ""),
            ])
        linhas.extend(["", "O LOGOS não emitiu conclusão financeira para esta execução."])
        return "\n".join(linhas) + "\n"
