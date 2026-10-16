"""Um único caminho de aprovação para comando, painel, Telegram e robô."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from ..adapters import webposto_escrita_cartao as escrita
from ..adapters.webposto_caixas import buscar_apresentados, buscar_caixas
from ..adapters.webposto_cartoes import buscar_cartoes
from ..adapters.webposto_http import WebPostoErro, paginar
from ..config import carregar_unidades
from ..domain.cartoes import Investigacao
from ..domain.models import Unidade
from ..domain.tempo import agora, para_local
from ...webposto_integration.funcionarios import buscar_nomes_funcionarios
from .conciliar_cartoes import conciliar_pagbank
from .resumo_diario import identificar_caixa, moeda_br

LIMITE_CARTAO = Decimal("300")
LIMITE_DIA = Decimal("1000")
ESTADOS_PENDENTES = {"incerto", "reservado", "enviado", "desfazendo", "falha_conferencia", "entrou_sem_conferencia"}


class PilotoErro(ValueError):
    pass


@dataclass(frozen=True)
class PropostaCartao:
    id: str
    unidade: int
    dia: date
    nsu: str | None
    valor: Decimal
    caixa: str
    frentista: str
    texto: str
    motivo: str | None
    evidencias: tuple[str, ...]
    payload: dict[str, Any] | None
    caixa_curto: str = ""

    @property
    def elegivel(self) -> bool:
        return self.motivo is None and self.payload is not None

    def publica(self) -> dict:
        return {
            "id": self.id, "unidade": self.unidade, "dia": self.dia.isoformat(),
            "nsu_final": self.nsu[-4:] if self.nsu else None, "valor": str(self.valor),
            "caixa": self.caixa, "frentista": self.frentista, "texto": self.texto,
            "caixa_curto": self.caixa_curto,
            "elegivel": self.elegivel, "motivo": self.motivo, "evidencias": list(self.evidencias),
        }


def explicar_cartao(
    *, caixa: str, momento, forma: str, valor: Decimal, frentista: str,
    venda: int | None, administradora: str, nsu: str | None, motivo: str | None,
    saldos: tuple[Decimal, Decimal] | None = None,
) -> str:
    momento = para_local(momento)
    if motivo:
        return f"{caixa}, {momento:%d/%m/%Y %H:%M} — {moeda_br(valor)}: {motivo}."
    texto = (
        f"{caixa}, {momento:%d/%m/%Y %H:%M} — o PagBank recebeu um "
        f"{forma.title()} de {moeda_br(valor)} do frentista {frentista}, venda {venda}, "
        "mas o cartão não está lançado no webPosto. Por isso o caixa mostra "
        f"{moeda_br(valor)} a mais em dinheiro do que deveria. Posso lançar "
        f"({administradora}, NSU final {(nsu or '')[-4:]}). Depois de lançar, "
        f"o dinheiro esperado cai {moeda_br(valor)} e o cartão sobe {moeda_br(valor)}."
    )
    if saldos is not None:
        dinheiro, cartao = saldos
        texto += (
            f" Antes: dinheiro {moeda_br(dinheiro)} · cartão {moeda_br(cartao)}."
            f" Depois de lançar: dinheiro {moeda_br(dinheiro - valor)} · cartão {moeda_br(cartao + valor)}."
        )
    return texto


def historico(unidade: int, dia: date, *, diretorio: Path | None = None) -> list[dict]:
    return [
        h for h in escrita.ler_auditoria(unidade, diretorio)
        if h.get("dia") == dia.isoformat() and h.get("estado")
    ]


def _total_dia(unidade: int, dia: date, diretorio: Path | None) -> Decimal:
    # Reservas incertas e lançamentos desfeitos também consomem o limite bruto.
    reservas = {
        h["acao_id"]: Decimal(h["valor"]) for h in historico(unidade, dia, diretorio=diretorio)
        if h["estado"] == "reservado"
    }
    return sum(reservas.values(), Decimal(0))


def avaliar(
    unidade: Unidade, dia: date, inv: Investigacao, *, venda: dict | None,
    caixas, administradoras: list[dict], total_dia: Decimal,
    nomes_funcionarios: dict[int, str] | None = None,
    saldos: tuple[Decimal, Decimal] | None = None,
) -> PropostaCartao:
    t = inv.transacao
    candidato = inv.candidatos[0] if len(inv.candidatos) == 1 else None
    ab = candidato.abastecimento if candidato else None
    cx = next((c for c in caixas if venda and c.codigo == venda.get("caixaCodigo")), None)
    posto = unidade.apelido or unidade.nome
    rotulo = identificar_caixa(posto, cx, caixas, nomes_funcionarios) if cx else f"{posto} · caixa não identificado"
    frentista = (
        f"{ab.nome_frentista.strip()} ({ab.frentista})" if ab and ab.nome_frentista and ab.nome_frentista.strip()
        else f"funcionário {ab.frentista}" if ab else "frentista não identificado"
    )
    motivo = None
    forma = (t.bandeira or "").upper()
    if t.adquirente != "PAGBANK" or any(p in forma for p in ("PIX", "BACEN")):
        motivo = "não é cartão PagBank — é PIX/BACEN ou outra fonte, conferir à mão"
    elif t.situacao is not None or t.momento.date() != dia or t.valor <= 0:
        motivo = "recebimento não aprovado ou fora do dia, conferir à mão"
    elif not candidato:
        motivo = "há dois ou mais abastecimentos possíveis" if inv.candidatos else "não encontrei o abastecimento desta venda"
    elif candidato.pontos < 90:
        motivo = "não consegui confirmar com segurança o abastecimento desta venda"
    elif ab is None or ab.empresa_codigo != unidade.empresa_codigo or ab.valor != t.valor or not candidato.venda_em_dinheiro:
        motivo = "o abastecimento não confirma este valor em dinheiro"
    elif not ab.venda_codigo or not ab.frentista or not venda:
        motivo = "faltam dados da venda ou do frentista"
    elif venda.get("empresaCodigo") != unidade.empresa_codigo or venda.get("vendaCodigo") != ab.venda_codigo or venda.get("cancelada") not in (False, "N", 0):
        motivo = "a venda está cancelada ou não pertence a este posto"
    elif cx is None or cx.empresa_codigo != unidade.empresa_codigo or cx.data != dia:
        motivo = "não consegui confirmar o caixa desta venda"
    elif cx.consolidado or cx.bloqueado:
        motivo = "o caixa já está consolidado ou bloqueado"
    elif t.valor > LIMITE_CARTAO:
        motivo = "o valor ultrapassa R$ 300,00; conferir à mão"
    elif total_dia + t.valor > LIMITE_DIA:
        motivo = "o limite de R$ 1.000,00 do posto neste dia foi atingido"
    elif not t.nsu or not t.autorizacao:
        motivo = "faltam o NSU ou a autorização do recebimento"
    elif saldos is None:
        motivo = "não consegui consultar o dinheiro e os cartões do caixa; conferir à mão"
    payload = None
    descricao = ""
    if motivo is None:
        try:
            adm = escrita.resolver_administradora_codigo(unidade, "PAGBANK", forma, administradoras)
            descricao = next(
                a["descricao"] for a in administradoras
                if int(a.get("administradoraCodigo") or a.get("codigo") or 0) == adm
            ).title().replace("Pagseguro", "PagSeguro")
            payload = escrita.montar_payload_cartao(
                {}, adm, nsu=t.nsu, autorizacao=t.autorizacao, venda=ab.venda_codigo,
                caixa=cx.codigo, frentista=ab.frentista, valor=t.valor, data_movimento=dia,
            )
            payload["centroCustoCodigo"] = cx.centro_custo
        except escrita.BarreiraCartaoErro:
            motivo = "não consegui escolher uma única administradora; conferir à mão"
    evidencias = tuple(candidato.motivos) if candidato else ()
    if candidato:
        evidencias += (f"Abastecimento {ab.codigo}; venda {ab.venda_codigo}; {candidato.pontos} pontos",)
    identidade = {
        "unidade": unidade.empresa_codigo, "dia": str(dia), "transacao": t.model_dump(mode="json"),
        "payload": payload, "evidencias": evidencias,
    }
    identificador = hashlib.sha256(json.dumps(identidade, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    texto = explicar_cartao(
        caixa=rotulo, momento=t.momento, forma=forma, valor=t.valor, frentista=frentista,
        venda=ab.venda_codigo if ab else None, administradora=descricao, nsu=t.nsu, motivo=motivo,
        saldos=saldos,
    )
    return PropostaCartao(identificador, unidade.empresa_codigo, dia, t.nsu, t.valor, rotulo,
                         frentista, texto, motivo, evidencias, payload,
                         identificar_caixa(posto, cx, caixas, nomes_funcionarios, curto=True) if cx else rotulo)


async def historico_publico(unidade: int, dia: date, eventos: list[dict]) -> list[dict]:
    if not eventos:
        return []
    cfg = carregar_unidades()[unidade]
    caixas = await buscar_caixas(cfg, dia, dia)
    nomes = await buscar_nomes_funcionarios(cfg, dia, dia)
    resultado = []
    for h in eventos:
        codigo = (h.get("payload") or {}).get("caixaCodigo")
        cx = next((c for c in caixas if c.codigo == codigo), None)
        rotulo = (
            identificar_caixa(cfg.apelido or cfg.nome, cx, caixas, nomes)
            if cx else f"{cfg.apelido or cfg.nome} · caixa não identificado"
        )
        texto = h.get("texto", "")
        antigo = h.get("caixa")
        if antigo and texto.startswith(antigo):
            texto = rotulo + texto[len(antigo):]
        elif codigo is not None and str(codigo) in texto:
            texto = f"{rotulo} — consulte a auditoria para os detalhes desta ação."
        if h.get("explicacao"):
            texto += f" Atenção: {h['explicacao']}."
        if h.get("mensagem_resolucao"):
            texto += f" {h['mensagem_resolucao']}"
        resultado.append({
            **{k: v for k, v in h.items() if k not in {"payload", "recriar", "nsu"}},
            "caixa": rotulo, "texto": texto,
            "caixa_curto": identificar_caixa(cfg.apelido or cfg.nome, cx, caixas, nomes, curto=True) if cx else rotulo,
        })
    return resultado


async def preparar(unidade: int, dia: date, *, diretorio: Path | None = None) -> list[PropostaCartao]:
    cfg = carregar_unidades().get(unidade)
    if cfg is None or dia > agora().date():
        raise PilotoErro("Posto ou data inválidos.")
    resultado = await conciliar_pagbank(unidade, dia)
    caixas = await buscar_caixas(cfg, dia, dia)
    nomes = await buscar_nomes_funcionarios(cfg, dia, dia)
    admins = await paginar(cfg, "/INTEGRACAO/V1/ADMINISTRADORAS", {"empresaCodigo": unidade})
    propostas = []
    saldos_por_caixa = {}
    for inv in resultado.a_maior:
        candidato = inv.candidatos[0] if len(inv.candidatos) == 1 else None
        codigo = candidato.abastecimento.venda_codigo if candidato else None
        vendas = await paginar(cfg, "/INTEGRACAO/V1/VENDAS", {
            "empresaCodigo": unidade, "vendaCodigo": codigo,
            "dataInicial": str(dia), "dataFinal": str(dia),
        }) if codigo else []
        vendas = [v for v in vendas if v.get("empresaCodigo") == unidade and v.get("vendaCodigo") == codigo]
        caixa_codigo = vendas[0].get("caixaCodigo") if len(vendas) == 1 else None
        if caixa_codigo is not None and any(c.codigo == caixa_codigo for c in caixas):
            if caixa_codigo not in saldos_por_caixa:
                saldos_por_caixa[caixa_codigo] = await _saldos(cfg, dia, caixa_codigo)
        propostas.append(avaliar(cfg, dia, inv, venda=vendas[0] if len(vendas) == 1 else None,
                                 caixas=caixas, administradoras=admins,
                                 nomes_funcionarios=nomes, saldos=saldos_por_caixa.get(caixa_codigo),
                                 total_dia=_total_dia(unidade, dia, diretorio)))
    return propostas


@contextmanager
def _exclusivo(unidade: int, diretorio: Path | None):
    pasta = escrita.resolver_diretorio_auditoria(unidade, diretorio)
    pasta.mkdir(parents=True, exist_ok=True)
    lock = pasta / "operacao.lock"
    try:
        arquivo = lock.open("x", encoding="ascii")
    except FileExistsError:
        raise PilotoErro("Já existe uma operação neste posto; aguarde ou confira a auditoria antes de liberar.") from None
    try:
        with arquivo:
            arquivo.write(agora().isoformat())
            arquivo.flush()
            yield
    finally:
        lock.unlink()


def _registrar(p: PropostaCartao, estado: str, autor: str, diretorio, **dados) -> dict:
    evento = {
        **p.publica(), "acao_id": p.id, "estado": estado, "instante": agora().isoformat(),
        "autorizado_por": autor, "nsu": p.nsu, "payload": p.payload, **dados,
    }
    escrita.gravar_auditoria(p.unidade, evento, diretorio)
    return evento


def _travas(caminho_env):
    ok, motivo = escrita.verificar_travas_cartao(caminho_env)
    if not ok:
        raise PilotoErro(f"Travas desligadas ou inválidas: {motivo}")


def diagnosticar_erro(exc: Exception, etapa: str) -> dict:
    status = getattr(exc, "status_http", None)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    mensagem = escrita.mensagem_segura(str(exc))
    if isinstance(exc, escrita.BarreiraCartaoErro) and "trava" in mensagem.lower():
        etapa = "travas"
    if status in (401, 403):
        permissao = "escrita" if etapa in {"envio", "desfazer"} else "consulta"
        explicacao = f"o webPosto recusou: sem permissão de {permissao} ({status}) — pedir à Quality"
    elif status == 400:
        explicacao = "o webPosto recusou os dados (400) — conferir os campos do cartão"
    elif status is not None:
        explicacao = f"o webPosto recusou a operação ({status}) — conferir na tela"
    elif isinstance(exc, httpx.RequestError) or mensagem in {
        "ReadTimeout", "ConnectTimeout", "ConnectError", "ReadError", "RemoteProtocolError",
    }:
        explicacao = "sem resposta do webPosto — conferir na tela antes de repetir"
    elif etapa == "travas":
        explicacao = "travas desligadas ou inválidas — nenhum novo envio autorizado"
    else:
        explicacao = "não consegui concluir a operação — conferir na tela antes de repetir"
    return {
        "tipo_erro": type(exc).__name__, "status_http": status, "etapa": etapa,
        "mensagem_erro": mensagem, "explicacao": explicacao,
    }


async def _saldos(cfg, dia, caixa) -> tuple[Decimal, Decimal]:
    dados = await buscar_apresentados(cfg, dia, dia, {caixa})
    if caixa not in dados:
        raise PilotoErro("Não consegui consultar o dinheiro e os cartões do caixa.")
    modalidades = {m.modalidade: m.apurado for m in dados[caixa]}
    if "dinheiro" not in modalidades or "cartao" not in modalidades:
        raise PilotoErro("O fechamento não informa dinheiro e cartão; lançamento bloqueado.")
    return modalidades["dinheiro"], modalidades["cartao"]


async def _cartoes(cfg, dia, proposta):
    cartoes = await buscar_cartoes(cfg, dia - timedelta(days=1), dia + timedelta(days=1))
    # CartaoRede não informa caixaCodigo; o vínculo oficial vem da venda.
    vendas = await paginar(cfg, "/INTEGRACAO/V1/VENDAS", {
        "empresaCodigo": cfg.empresa_codigo, "vendaCodigo": proposta.payload["vendaCodigo"],
        "dataInicial": str(dia), "dataFinal": str(dia),
    })
    vendas = [v for v in vendas if v.get("empresaCodigo") == cfg.empresa_codigo
              and v.get("vendaCodigo") == proposta.payload["vendaCodigo"]
              and v.get("cancelada") in (False, "N", 0)]
    caixa = vendas[0].get("caixaCodigo") if len(vendas) == 1 else None
    return [
        c.model_copy(update={"caixa_codigo": caixa})
        if c.venda_codigo == proposta.payload["vendaCodigo"] else c
        for c in cartoes
    ]


def _nsu(c, nsu):
    return nsu.strip().upper() in {(c.nsu or "").strip().upper(), (c.nsu_tef or "").strip().upper()}


def _compativel(c, p):
    return (_nsu(c, p.nsu) and c.valor == p.valor and c.caixa_codigo == p.payload["caixaCodigo"]
            and c.venda_codigo == p.payload["vendaCodigo"] and c.empresa_codigo == p.unidade
            and c.momento.date() == p.dia and c.autorizacao == p.payload["autorizacao"])


async def confirmar(
    unidade: int, dia: date, nsu: str, *, autor: str, acao_id: str | None = None,
    caminho_env: Path | None = None, diretorio: Path | None = None,
) -> dict:
    if not nsu or not nsu.strip() or nsu.startswith("…"):
        raise PilotoErro("Escolha um único cartão pelo NSU completo.")
    nsu = nsu.strip().upper()
    _travas(caminho_env)
    with _exclusivo(unidade, diretorio):
        eventos = historico(unidade, dia, diretorio=diretorio)
        ultimos = {h["acao_id"]: h for h in eventos}
        if any(h["estado"] in ESTADOS_PENDENTES for h in ultimos.values()):
            raise PilotoErro("Existe uma operação não conferida neste posto/dia. Pare e confira na tela.")
        anteriores = [h for h in eventos
                      if (h.get("nsu") or (h.get("payload") or {}).get("nsu", "")).strip().upper() == nsu]
        if anteriores:
            raise PilotoErro("Este cartão já foi decidido ou tentado. Confira o histórico; não vou repetir.")
        propostas = [p for p in await preparar(unidade, dia, diretorio=diretorio) if (p.nsu or "").strip().upper() == nsu]
        if len(propostas) != 1:
            raise PilotoErro("Não encontrei um único cartão faltante com esse NSU.")
        p = propostas[0]
        if acao_id and p.id != acao_id:
            raise PilotoErro("Os dados mudaram desde a prévia. Atualize e aprove novamente.")
        if not p.elegivel:
            raise PilotoErro(p.motivo or "Cartão não elegível.")
        if _total_dia(unidade, dia, diretorio) + p.valor > LIMITE_DIA:
            raise PilotoErro("O limite de R$ 1.000,00 do posto neste dia foi atingido.")
        cfg = carregar_unidades()[unidade]
        caixa = p.payload["caixaCodigo"]
        existentes = await _cartoes(cfg, dia, p)
        if any(_nsu(c, nsu) for c in existentes):
            raise PilotoErro("O cartão já existe no webPosto; não vou lançar novamente.")
        cx = next((c for c in await buscar_caixas(cfg, dia, dia) if c.codigo == caixa), None)
        if cx is None or cx.consolidado or cx.bloqueado:
            raise PilotoErro("O caixa mudou ou está consolidado/bloqueado.")
        antes = await _saldos(cfg, dia, caixa)
        _travas(caminho_env)
        _registrar(p, "reservado", autor, diretorio, antes=list(map(str, antes)))
        try:
            resposta = await escrita.incluir_cartao(
                cfg, p.payload, acao_id=p.id, evidencias=p.evidencias, autorizado_por=autor,
                caminho_env=caminho_env, diretorio_auditoria=diretorio,
            )
        except (WebPostoErro, httpx.HTTPError, OSError, ValueError) as exc:
            diagnostico = diagnosticar_erro(exc, "envio")
            _registrar(p, "incerto", autor, diretorio, **diagnostico)
            raise PilotoErro(f"{diagnostico['explicacao']}. Pare e confira na tela; não repita.") from exc
        id_criado = resposta["id_criado"]
        if isinstance(id_criado, str) and id_criado.isascii() and id_criado.isdigit():
            id_criado = int(id_criado)
        _registrar(p, "enviado", autor, diretorio, id_criado=id_criado, antes=list(map(str, antes)))
        try:
            depois_cartoes = await _cartoes(cfg, dia, p)
            novos = [c for c in depois_cartoes if c.codigo not in {a.codigo for a in existentes} and _compativel(c, p)]
            if id_criado is None and len(novos) == 1:
                id_criado = novos[0].codigo
            depois = await _saldos(cfg, dia, caixa)
            if (len(novos) == 1 and novos[0].codigo == id_criado
                    and depois == (antes[0] - p.valor, antes[1] + p.valor)):
                _registrar(p, "confirmado", autor, diretorio, id_criado=id_criado,
                           antes=list(map(str, antes)), depois=list(map(str, depois)))
                return {"estado": "confirmado", "mensagem": f"Lancei 1 cartão · {moeda_br(p.valor)}. Conferido por NSU e no caixa.",
                        "antes": list(map(str, antes)), "depois": list(map(str, depois))}
            _registrar(p, "falha_conferencia", autor, diretorio, id_criado=id_criado,
                       **diagnosticar_erro(PilotoErro("Cartão ou saldos não conferem com o lançamento esperado."), "conferência"))
        except (WebPostoErro, httpx.HTTPError, OSError, ValueError) as exc:
            diagnostico = diagnosticar_erro(exc, "conferência")
            _registrar(p, "falha_conferencia", autor, diretorio, id_criado=id_criado, **diagnostico)
            if diagnostico["status_http"] in (401, 403):
                _registrar(p, "incerto", autor, diretorio, id_criado=id_criado, **diagnostico)
                raise PilotoErro("Conferência bloqueada por HTTP 401/403. Pare e peça permissão à Quality; "
                                "CONFERIR NA TELA antes de qualquer outra operação.") from exc
        if not isinstance(id_criado, int) or isinstance(id_criado, bool) or id_criado in {c.codigo for c in existentes}:
            _registrar(p, "incerto", autor, diretorio, **diagnosticar_erro(
                PilotoErro("Sem identificação segura do cartão criado para desfazer."), "conferência",
            ))
            raise PilotoErro("LANÇAMENTO NÃO CONFERIDO — sem identificação segura para desfazer. CONFERIR NA TELA.")
        await _excluir(cfg, p, id_criado, antes, autor, caminho_env, diretorio)
        return {"estado": "desfeito", "mensagem": "LANÇAMENTO DESFEITO — CONFERIR NA TELA"}


async def _excluir(cfg, p, codigo, esperado, autor, caminho_env, diretorio):
    # O payload completo é preservado antes de qualquer DELETE.
    _registrar(p, "desfazendo", autor, diretorio, id_criado=codigo, recriar=p.payload)
    try:
        cx = next((c for c in await buscar_caixas(cfg, p.dia, p.dia)
                   if c.codigo == p.payload["caixaCodigo"]), None)
        if cx is None or cx.consolidado or cx.bloqueado:
            raise PilotoErro("Caixa consolidado/bloqueado; não vou excluir.")
        await escrita.excluir_cartao(cfg, codigo, acao_id=p.id, autorizado_por=autor,
                                    caminho_env=caminho_env, diretorio_auditoria=diretorio)
        cartoes = await _cartoes(cfg, p.dia, p)
        saldos = await _saldos(cfg, p.dia, p.payload["caixaCodigo"])
        if any(c.codigo == codigo for c in cartoes) or saldos != esperado:
            raise PilotoErro("A exclusão não foi confirmada no caixa.")
    except (WebPostoErro, httpx.HTTPError, OSError, ValueError) as exc:
        diagnostico = diagnosticar_erro(exc, "desfazer")
        _registrar(p, "incerto", autor, diretorio, id_criado=codigo, **diagnostico)
        raise PilotoErro("NÃO CONSEGUI CONFERIR O DESFAZER — CONFERIR NA TELA. Não repita.") from exc
    _registrar(p, "desfeito", autor, diretorio, id_criado=codigo)


async def resolver(
    unidade: int, dia: date, nsu: str, *, autor: str, diretorio: Path | None = None,
) -> dict:
    """Resolve apenas a auditoria local; nunca chama a porta de escrita."""
    if not nsu or not nsu.strip() or nsu.strip().startswith("…"):
        raise PilotoErro("Escolha um único cartão pelo NSU completo.")
    cfg = carregar_unidades().get(unidade)
    if cfg is None or dia > agora().date():
        raise PilotoErro("Posto ou data inválidos.")
    nsu = nsu.strip().upper()
    with _exclusivo(unidade, diretorio):
        eventos = historico(unidade, dia, diretorio=diretorio)
        por_acao = {}
        for h in eventos:
            if (h.get("nsu") or (h.get("payload") or {}).get("nsu", "")).strip().upper() == nsu:
                por_acao.setdefault(h["acao_id"], []).append(h)
        pendentes = [hs for hs in por_acao.values() if hs[-1]["estado"] in ESTADOS_PENDENTES]
        if len(pendentes) != 1:
            raise PilotoErro("Não encontrei uma única operação pendente com esse NSU; nenhum lançamento realizado.")
        hs = pendentes[0]
        h = hs[-1]
        payload = h.get("payload")
        if not isinstance(payload, dict) or not payload.get("caixaCodigo") or not payload.get("vendaCodigo"):
            raise PilotoErro("Auditoria sem vínculo seguro com a venda e o caixa; conferir à mão.")
        p = PropostaCartao(
            h["acao_id"], unidade, dia, nsu, Decimal(h["valor"]), h["caixa"],
            h["frentista"], h["texto"], None, tuple(h["evidencias"]), payload,
            h.get("caixa_curto", ""),
        )
        antes_raw = next((e["antes"] for e in reversed(hs) if e.get("antes") is not None), None)
        try:
            cartoes = await _cartoes(cfg, dia, p)
            saldos = await _saldos(cfg, dia, payload["caixaCodigo"])
        except (WebPostoErro, httpx.HTTPError, OSError, ValueError) as exc:
            diagnostico = diagnosticar_erro(exc, "conferência")
            _registrar(p, "incerto", autor, diretorio, **diagnostico)
            raise PilotoErro(f"{diagnostico['explicacao']}. O bloqueio continua; nenhum lançamento realizado.") from exc
        encontrados = [c for c in cartoes if _nsu(c, nsu)]
        if encontrados:
            codigos = [c.codigo for c in encontrados]
            mensagem = (
                f"Encontrei {len(encontrados)} cartão com o NSU final {nsu[-4:]} no webPosto "
                f"(lançamento: {', '.join(map(str, codigos))}). "
                "Registrei entrou_sem_conferencia. Não excluí nem lancei nada. "
                "O bloqueio continua: o diretor precisa conferir na tela e decidir."
            )
            estado = "entrou_sem_conferencia"
        else:
            if not isinstance(antes_raw, list) or len(antes_raw) != 2:
                raise PilotoErro("Auditoria sem saldos anteriores confiáveis; o bloqueio continua. Conferir na tela.")
            try:
                antes = tuple(Decimal(v) for v in antes_raw)
            except (InvalidOperation, TypeError, ValueError):
                raise PilotoErro("Auditoria com saldos anteriores inválidos; o bloqueio continua. Conferir na tela.") from None
            if not all(v.is_finite() for v in antes) or saldos != antes:
                mensagem = "Nenhum cartão encontrado, mas os saldos mudaram; o bloqueio continua. Conferir na tela."
                _registrar(p, "incerto", autor, diretorio, depois=list(map(str, saldos)),
                           **diagnosticar_erro(PilotoErro(mensagem), "conferência"))
                raise PilotoErro(mensagem)
            codigos = []
            estado = "nao_entrou"
            mensagem = (
                f"O cartão de {moeda_br(p.valor)}, NSU final {nsu[-4:]}, não entrou no webPosto. "
                f"Dinheiro {moeda_br(saldos[0])} e cartão {moeda_br(saldos[1])}, iguais aos de antes. "
                "Registrei nao_entrou, resolvido com autorização do diretor, e liberei o bloqueio "
                "desta operação no posto/dia. Nenhum lançamento realizado."
            )
        _registrar(p, estado, autor, diretorio, antes=antes_raw, depois=list(map(str, saldos)),
                   codigos_encontrados=codigos, mensagem_resolucao=mensagem)
        return {"estado": estado, "mensagem": mensagem}


async def decidir(
    unidade: int, dia: date, acao_id: str, decisao: str, *, autor: str,
    caminho_env: Path | None = None, diretorio: Path | None = None,
) -> dict:
    if decisao not in {"aprovar", "recusar", "desfazer"}:
        raise PilotoErro("Decisão inválida.")
    if decisao == "desfazer":
        _travas(caminho_env)
        with _exclusivo(unidade, diretorio):
            eventos = [h for h in historico(unidade, dia, diretorio=diretorio) if h["acao_id"] == acao_id]
            if not eventos or eventos[-1]["estado"] != "confirmado":
                raise PilotoErro("Este lançamento não está disponível para desfazer.")
            h = eventos[-1]
            p = PropostaCartao(acao_id, unidade, dia, h["payload"]["nsu"], Decimal(h["valor"]),
                              h["caixa"], h["frentista"], h["texto"], None, tuple(h["evidencias"]), h["payload"])
            cfg = carregar_unidades()[unidade]
            cx = next((c for c in await buscar_caixas(cfg, dia, dia) if c.codigo == p.payload["caixaCodigo"]), None)
            if cx is None or cx.consolidado or cx.bloqueado:
                raise PilotoErro("Caixa consolidado, bloqueado ou indisponível; não posso desfazer.")
            cartoes = await _cartoes(cfg, dia, p)
            if not any(c.codigo == h["id_criado"] and _compativel(c, p) for c in cartoes):
                raise PilotoErro("O cartão mudou desde o lançamento; conferir à mão.")
            antes = await _saldos(cfg, dia, cx.codigo)
            await _excluir(cfg, p, h["id_criado"], (antes[0] + p.valor, antes[1] - p.valor),
                           autor, caminho_env, diretorio)
            return {"estado": "desfeito", "mensagem": "LANÇAMENTO DESFEITO — CONFERIR NA TELA"}
    propostas = [p for p in await preparar(unidade, dia, diretorio=diretorio) if p.id == acao_id]
    if len(propostas) != 1:
        raise PilotoErro("A proposta mudou ou não está mais disponível. Atualize a prévia.")
    p = propostas[0]
    if decisao == "aprovar":
        return await confirmar(unidade, dia, p.nsu, autor=autor, acao_id=acao_id,
                               caminho_env=caminho_env, diretorio=diretorio)
    with _exclusivo(unidade, diretorio):
        if any(h["acao_id"] == acao_id for h in historico(unidade, dia, diretorio=diretorio)):
            raise PilotoErro("Esta proposta já foi decidida.")
        _registrar(p, "recusado", autor, diretorio)
    return {"estado": "recusado", "mensagem": "Não vou lançar este cartão."}


def resumo_lancamentos(unidades: list[int], dia: date, *, diretorio: Path | None = None) -> str | None:
    ultimos = {}
    for unidade in unidades:
        for h in historico(unidade, dia, diretorio=diretorio):
            ultimos[h["acao_id"]] = h
    confirmados = [h for h in ultimos.values() if h["estado"] == "confirmado"]
    if not confirmados:
        return None
    total = sum((Decimal(h["valor"]) for h in confirmados), Decimal(0))
    rotulo = "cartão" if len(confirmados) == 1 else "cartões"
    return f"Lancei {len(confirmados)} {rotulo} · {moeda_br(total)}"


def automatico_ativado(caminho_env: Path | None = None) -> bool:
    if not escrita.resolver_caminho_env(caminho_env).is_file():
        return False
    valores = escrita.ler_travas(caminho_env)["LOGOS_CARTAO_AUTOMATICO"]
    if not valores:
        return False
    if len(valores) != 1 or valores[0][1] not in {"0", "1"}:
        raise PilotoErro("Trava LOGOS_CARTAO_AUTOMATICO inválida ou duplicada; robô bloqueado.")
    return valores[0][1] == "1"


async def executar_automatico(unidade: int, dia: date, *, caminho_env=None, diretorio=None) -> list[dict]:
    if not automatico_ativado(caminho_env):
        return []
    _travas(caminho_env)
    propostas = await preparar(unidade, dia, diretorio=diretorio)
    resultados = []
    for p in propostas:
        if not p.elegivel:
            continue
        # Qualquer falha interrompe o lote; jamais repetir uma reserva incerta.
        resultado = await confirmar(unidade, dia, p.nsu, autor="automático", acao_id=p.id,
                                    caminho_env=caminho_env, diretorio=diretorio)
        resultados.append(resultado)
        if resultado["estado"] != "confirmado":
            break
    return resultados
