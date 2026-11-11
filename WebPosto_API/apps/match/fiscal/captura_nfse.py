"""Busca das NFS-e recebidas no sistema nacional (ADN), com o certificado de cada empresa."""
from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from apps.match import caminhos
from apps.match.banco import _agora
from apps.match.fiscal import certificados, repositorio as repo
from src.modules.fiscal_docs import acervo, adn_nfse as adn
from src.modules.fiscal_docs.modelos import FUSO, XmlInvalido
from src.modules.fiscal_docs.parser import ler

logger = logging.getLogger(__name__)
FONTE = "adn"
_ESPERA_VAZIA = timedelta(hours=1)
_ESPERA_ERRO = timedelta(minutes=15)
_MAX_LOTES = 20          # modo lote: até 50 documentos por chamada
_MAX_UNITARIOS = 200     # modo um por vez (manual oficial), por execução
_EVENTOS_CANCELA = (b"e101101", b"e105102")  # cancelamento e cancelamento por substituição
_TRAVA = threading.Lock()
MSG_SEM_CERTIFICADO = "Envie o certificado desta empresa para buscar as notas de serviço."
MSG_NENHUMA = ("Nenhuma nota nova no sistema nacional. Se você sabe que existem notas, a prefeitura pode não "
               "enviar para o sistema nacional: baixe o XML no portal da prefeitura e use Importar.")
_MSG_ERRO = {
    "certificado": "O sistema nacional recusou o certificado. Confira se é o certificado desta empresa e se ainda vale.",
    "indisponivel": "O sistema nacional não respondeu agora. O Logos Match tenta de novo sozinho.",
    "resposta": "O sistema nacional recusou a consulta. O Logos Match tenta de novo sozinho.",
}


@dataclass
class ResultadoBusca:
    empresa_id: int
    situacao: str  # ok | erro | sem_certificado
    novas: int
    mensagem: str


def _guardar(con, empresa, doc_adn: adn.DocumentoAdn, base) -> bool:
    """True se entrou uma nota nova. Nota de outro CNPJ (ex.: emitida pela empresa) é ignorada."""
    if "EVENTO" in doc_adn.tipo:
        if any(m in doc_adn.xml for m in _EVENTOS_CANCELA):
            repo.marcar_cancelada(con, doc_adn.chave)
        return False
    doc = ler(doc_adn.xml)
    if repo.so_digitos(doc.destinatario_cnpj) != empresa["cnpj"]:
        return False
    caminho = acervo.gravar(base, empresa["cnpj"], doc, doc_adn.xml, FONTE)
    return repo.gravar_documento(con, empresa["id"], doc, caminho, hashlib.sha256(doc_adn.xml).hexdigest(), FONTE)


def buscar_empresa(con, empresa_id: int, agora: datetime | None = None, *,
                   client: httpx.Client | None = None) -> ResultadoBusca:
    agora = agora or datetime.now(timezone.utc)
    empresa = repo.obter_empresa(con, empresa_id)
    credencial = certificados.carregar(con, empresa_id)
    if credencial is None:
        return ResultadoBusca(empresa_id, "sem_certificado", 0, MSG_SEM_CERTIFICADO)
    fila = repo.nsu_de(con, empresa_id)
    if fila["proxima_consulta_em"] and datetime.fromisoformat(fila["proxima_consulta_em"]) > agora:
        hora = datetime.fromisoformat(fila["proxima_consulta_em"]).astimezone(FUSO)
        return ResultadoBusca(empresa_id, "ok", 0, "O sistema nacional já foi consultado há pouco. "
                                                   f"Tente de novo a partir de {hora:%H:%M}.")
    consulta = empresa["cnpj"]  # obrigatório: sem cnpjConsulta o ADN responde REJEICAO
    proprio = client is None
    iniciada, nsu = _agora(), fila["ultimo_nsu"]
    novas = ilegiveis = 0
    base = caminhos.fiscal(con)
    try:
        http = client or adn.cliente(*credencial)
        try:
            modo_lote, erro_lote, chamadas = True, "", 0
            while chamadas < (_MAX_LOTES if modo_lote else _MAX_UNITARIOS):
                try:
                    lote = adn.distribuir(http, nsu if modo_lote else nsu + 1, consulta, lote=modo_lote)
                except adn.AdnErro as exc:
                    if modo_lote and exc.tipo == "resposta":  # o ADN não aceitou o lote: um por vez
                        modo_lote, erro_lote = False, exc.detalhe
                        continue
                    if erro_lote:
                        exc.detalhe = f"em lote: {erro_lote}; um por vez: {exc.detalhe}"
                    raise
                chamadas += 1
                if lote.vazio:
                    repo.salvar_nsu(con, empresa_id, nsu, agora + _ESPERA_VAZIA)
                    break
                for d in lote.documentos:
                    try:
                        if d.xml is None:
                            raise XmlInvalido("arquivo ilegível")
                        novas += _guardar(con, empresa, d, base)
                    except (ValueError, ArithmeticError):  # XML inválido, data ou valor estranho
                        ilegiveis += 1
                    nsu = max(nsu, d.nsu)
                repo.salvar_nsu(con, empresa_id, nsu, None)  # só avança depois de gravar
        finally:
            if proprio:
                http.close()
    except adn.AdnErro as exc:
        repo.salvar_nsu(con, empresa_id, nsu, agora + _ESPERA_ERRO)
        msg = _MSG_ERRO[exc.tipo] + (f" Resposta do sistema nacional: {exc.detalhe}." if exc.detalhe else "")
        repo.registrar_captura(con, empresa_id, FONTE, iniciada, "erro", novas, 0, msg)
        return ResultadoBusca(empresa_id, "erro", novas, msg)
    msg = f"{novas} nota(s) nova(s)." if novas else MSG_NENHUMA
    if ilegiveis:
        msg += f" {ilegiveis} documento(s) não puderam ser lidos."
    repo.registrar_captura(con, empresa_id, FONTE, iniciada, "ok", novas, 0, None)
    return ResultadoBusca(empresa_id, "ok", novas, msg)


def em_andamento() -> bool:
    return _TRAVA.locked()


def buscar_todas(con_factory) -> list[ResultadoBusca]:
    """Todas as empresas ativas com certificado. Uma falha não impede as outras."""
    if not _TRAVA.acquire(blocking=False):
        return []
    con = con_factory()
    try:
        resultados = []
        for e in repo.listar_empresas(con):
            if not e["ativo"] or certificados.situacao(con, e["id"]) is None:
                continue
            try:
                resultados.append(buscar_empresa(con, e["id"]))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Busca NFS-e falhou empresa=%s tipo=%s", e["id"], type(exc).__name__)
        return resultados
    finally:
        con.close()
        _TRAVA.release()
