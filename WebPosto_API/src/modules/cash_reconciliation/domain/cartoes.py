"""Conciliacao de recebimentos eletronicos (cartao/PIX/Premmia) x webPosto, por dia e unidade.

Somente leitura: o sistema classifica e sugere; correcao no ERP e humana (WEBPOSTO_WRITES=0).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from .models import Proveniencia
from .tempo import DataHoraLocal


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class TransacaoAdquirente(_Frozen):
    """Comprovante eletronico informado pela adquirente (PagBank, PIX, Premmia...)."""
    adquirente: str
    identificador: str            # tid / movimento_api_codigo
    nsu: str | None
    autorizacao: str | None
    valor: Decimal
    momento: DataHoraLocal
    bandeira: str | None = None
    terminal: str | None = None   # numero de serie da maquininha (compartilhada)


class CartaoErp(_Frozen):
    """Recebimento eletronico lancado no webPosto (V1/CARTOES)."""
    codigo: int
    empresa_codigo: int
    venda_codigo: int | None
    valor: Decimal
    momento: DataHoraLocal
    administradora: str
    nsu: str | None
    nsu_tef: str | None
    autorizacao: str | None


class Abastecimento(_Frozen):
    codigo: int
    empresa_codigo: int
    momento: DataHoraLocal
    bico: int | None
    valor: Decimal
    frentista: int | None          # codigoFrentista (identfid)
    venda_item_codigo: int | None


class Atribuicao(str, Enum):
    ATRIBUIDO = "atribuido"            # >= 80 pontos e candidato unico: associa sozinho
    SUGESTAO = "sugestao"              # 50-79 pontos ou empate: confirmacao humana
    SEM_ABASTECIMENTO = "sem_abastecimento"


class Candidato(_Frozen):
    abastecimento: Abastecimento
    pontos: int
    motivos: tuple[str, ...]
    venda_em_dinheiro: bool


class Investigacao(_Frozen):
    """Recebimento na adquirente sem lancamento correspondente no webPosto (a maior)."""
    transacao: TransacaoAdquirente
    atribuicao: Atribuicao
    frentista: int | None             # so preenchido quando ATRIBUIDO
    candidatos: tuple[Candidato, ...]
    troca_de_forma: bool              # venda do abastecimento lancada como dinheiro


class Casamento(_Frozen):
    transacao: TransacaoAdquirente
    cartao: CartaoErp
    chave: str                        # "nsu" | "autorizacao" | "valor_hora"


class ParProvavel(_Frozen):
    """Mesmo valor e mesmo dia nos dois lados: provavel lancamento manual com hora/NSU divergente."""
    investigacao: Investigacao
    cartao: CartaoErp


class GrupoProvavel(_Frozen):
    investigacoes: tuple[Investigacao, ...]
    cartao: CartaoErp


class ResultadoCartoes(_Frozen):
    empresa_codigo: int
    adquirente: str
    dia: date
    casados: tuple[Casamento, ...]
    a_maior: tuple[Investigacao, ...]  # recebido na adquirente, ausente no webPosto
    a_menor: tuple[CartaoErp, ...]     # lancado no webPosto, nao recebido na adquirente
    pares_provaveis: tuple[ParProvavel, ...] = ()
    grupos_provaveis: tuple[GrupoProvavel, ...] = ()
    proveniencia: Proveniencia
