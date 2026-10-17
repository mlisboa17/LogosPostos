"""Coleta diaria somente leitura, isolada por unidade e adquirente."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from pathlib import Path

from ..adapters.persistencia import carregar_dia, salvar_dia
from ..adapters import pendencias as repositorio_pendencias
from ..adapters import saude_robo
from ..adapters import premmia_portal
from ..adapters.webposto_http import WebPostoErro
from ..application.auditar_fechamento import auditar_unidade
from ..application.gerar_pendencias import (
    executar_reincidencia_mes,
    pendencias_do_dia,
)
from ..application.resumo_diario import gerar_resumo_diario
from ..application.recebimentos import TIMEOUT_ETAPA, conciliar_adquirente
from ..config import carregar_unidades
from ..domain.execucao import ResultadoDiario
from ..domain.integridade_execucao import ExecucaoNoturna, FonteExecucao
from ..domain.explicacao import ConferenciaMais, ConferenciaPixCnpj
from ..domain.models import Proveniencia, Unidade
from ..domain.recebimentos import ResultadoRecebimentos, RecebimentoAdquirente
from ..domain.tempo import FUSO, agora, formatar_data, formatar_data_hora, ler_data, ler_data_hora
from ..rules.cartoes import VERSAO as VERSAO_CARTOES
from ..rules.fechamento import VERSAO as VERSAO_FECHAMENTO

logger = logging.getLogger("src.modules.cash_reconciliation.jobs.noturno")
VERSAO_JOB = "CASH_AUDIT_NOTURNO_V2"
ExecutarPlacar = Callable[[date, float, Path | None, ExecucaoNoturna], Awaitable[tuple[int, set[int]]]]


class FormatoLogBrasil(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return formatar_data_hora(datetime.fromtimestamp(record.created, FUSO))


async def coletar_unidade(
    unidade: Unidade,
    dia: date,
    execucao_id: str,
    *,
    timeout: float = TIMEOUT_ETAPA,
    aviso_premmia: str | None = None,
) -> ResultadoDiario:
    empresa = unidade.empresa_codigo
    fechamento = None
    erro_fechamento = None
    try:
        fechamento = await asyncio.wait_for(auditar_unidade(empresa, dia, dia), timeout=timeout)
        if fechamento.empresa_codigo != empresa or fechamento.inicio != dia or fechamento.fim != dia:
            raise ValueError("Resultado fora do escopo.")
    except TimeoutError:
        erro_fechamento = "tempo limite excedido"
    except Exception as exc:
        # Fronteira do job: isola erros sem registrar corpo, URL ou mensagem do fornecedor.
        logger.warning("Fechamento unidade=%s dia=%s tipo=%s", empresa, formatar_data(dia), type(exc).__name__)
        erro_fechamento = "falha ao consultar fechamento"
    if erro_fechamento:
        fechamento = None
    fontes_execucao = [FonteExecucao(
        nome="fechamento", unidade=empresa, dia=dia, run_id=execucao_id,
        coletado_em=agora(), cobertura_inicio=dia, cobertura_fim=dia, permite_vazio=True,
        estado="FAILED" if erro_fechamento else "SUCCESS" if fechamento and fechamento.caixas else "EMPTY_VALID",
        motivo=erro_fechamento,
    )]
    logger.info(
        "Fechamento unidade=%s dia=%s situacao=%s caixas=%s",
        empresa, formatar_data(dia), "erro" if erro_fechamento else "ok", len(fechamento.caixas) if fechamento else 0,
    )
    adquirentes = []
    for configurada in unidade.adquirentes:
        if configurada.nome == "PREMMIA" and aviso_premmia:
            item = await conciliar_adquirente(
                empresa,
                dia,
                configurada,
                timeout=timeout,
                aviso_premmia=aviso_premmia,
            )
        else:
            item = await conciliar_adquirente(empresa, dia, configurada, timeout=timeout)
        adquirentes.append(item)
        obrigatoria = configurada.nome != "PREMMIA" and configurada.situacao.value != "pendente"
        vazio = (
            item.casados is not None and item.casados.quantidade == 0
            and not any((item.a_maior, item.a_menor, item.pares_provaveis, item.grupos_provaveis,
                         item.divergencias_valor, item.transacoes_canceladas, item.alertas,
                         item.formas, item.sem_fonte))
        )
        coletado_em = agora() if item.situacao == "ok" else None
        if configurada.nome == "PREMMIA" and item.situacao == "ok":
            try:
                _, coletas = premmia_portal.ler_mensal(premmia_portal.caminho_mensal(unidade, dia))
                instante = next((c["Coletado em"] for c in coletas if c["Dia"] == dia.isoformat()), None)
                coletado_em = ler_data_hora(str(instante)) if instante is not None else None
            except (OSError, ValueError, premmia_portal.PremmiaErro) as exc:
                logger.warning("Premmia sem evidência temporal unidade=%s tipo=%s",
                               empresa, type(exc).__name__)
                coletado_em = None
        fontes_execucao.append(FonteExecucao(
            nome=configurada.nome, unidade=empresa, dia=dia, run_id=execucao_id,
            coletado_em=coletado_em,
            cobertura_inicio=dia if item.situacao == "ok" else None,
            cobertura_fim=dia if item.situacao == "ok" else None,
            obrigatoria=obrigatoria, permite_vazio=True,
            estado=(("EMPTY_VALID" if vazio else "SUCCESS") if item.situacao == "ok" else
                    "BLOCKED" if item.situacao == "credencial inválida" else
                    "FAILED" if item.erro or item.situacao == "erro" else "NOT_COLLECTED"),
            motivo=("Fonte não disponível; conferir configuração ou coleta." if item.situacao != "ok" else None),
            origem="arquivo_mensal" if configurada.nome == "PREMMIA" else "consulta_remota",
        ))
        logger.info(
            "Recebimentos unidade=%s adquirente=%s situacao=%s casados=%s maior=%s menor=%s pares=%s",
            empresa, item.adquirente, item.situacao,
            item.casados.quantidade if item.casados else "-",
            len(item.a_maior) if item.casados else "-", len(item.a_menor) if item.casados else "-",
            len(item.pares_provaveis) if item.casados else "-",
        )
    fontes = set(fechamento.proveniencia.outras_fontes if fechamento else ())
    if fechamento and fechamento.proveniencia.fonte_sangrias:
        fontes.add(fechamento.proveniencia.fonte_sangrias)
    for item in adquirentes:
        if item.proveniencia:
            fontes.update(item.proveniencia.outras_fontes)
    registro = ResultadoDiario(
        empresa_codigo=empresa, dia=dia, fechamento=fechamento, erro_fechamento=erro_fechamento,
        recebimentos=ResultadoRecebimentos(empresa_codigo=empresa, dia=dia, adquirentes=tuple(adquirentes)),
        proveniencia=Proveniencia(
            execucao_id=execucao_id, executado_em=agora(), versao_regra=VERSAO_JOB,
            fonte_sangrias=fechamento.proveniencia.fonte_sangrias if fechamento else "",
            extratos=(), outras_fontes=tuple(sorted(fontes)),
        ),
        versoes_regras=(VERSAO_FECHAMENTO, VERSAO_CARTOES, "RN-CARTAO-010"),
        conferencia_recebimentos=True,
        fontes_execucao=tuple(fontes_execucao),
    )
    from ..application.fontes_falta import anexar_fontes_falta
    registro = await anexar_fontes_falta(registro, unidade)
    for nome, conf, disponivel, erro in (
        ("PIX_CNPJ", registro.pix_cnpj, bool(registro.pix_cnpj and registro.pix_cnpj.coberto),
         registro.pix_cnpj.erro if registro.pix_cnpj else None),
        ("MAIS_TOTAL", registro.mais_pagamentos,
         bool(registro.mais_pagamentos and registro.mais_pagamentos.total is not None),
         registro.mais_pagamentos.aviso
         if registro.mais_pagamentos and registro.mais_pagamentos.total is None else None),
    ):
        fontes_execucao.append(FonteExecucao(
            nome=nome, unidade=empresa, obrigatoria=False, dia=dia,
            estado="FAILED" if erro else "SUCCESS" if disponivel else "NOT_COLLECTED",
            run_id=execucao_id, coletado_em=agora() if conf else None,
            cobertura_inicio=dia if disponivel else None, cobertura_fim=dia if disponivel else None,
            motivo="Fonte local indisponível ou não conferida." if erro or not disponivel else None,
            origem="declaracao_local" if nome == "MAIS_TOTAL" else "arquivo_ofx",
            referencia_em=registro.mais_pagamentos.informado_em
            if nome == "MAIS_TOTAL" and registro.mais_pagamentos else None,
            evidencias=registro.pix_cnpj.fontes if nome == "PIX_CNPJ" and registro.pix_cnpj else (),
        ))
    return registro.model_copy(update={"fontes_execucao": tuple(fontes_execucao)})


def validar_registros(execucao: ExecucaoNoturna, resultados: list[ResultadoDiario]) -> None:
    esperadas = {f.unidade for f in execucao.fontes if f.nome == "fechamento" and f.unidade is not None}
    if not esperadas:
        execucao.registrar(FonteExecucao(
            nome="escopo", dia=execucao.dia, estado="BLOCKED",
            motivo="Nenhuma cobertura de unidades validada para publicação.",
        ))
    por_unidade = {r.empresa_codigo: r for r in resultados}
    if len(por_unidade) != len(resultados) or not set(por_unidade).issubset(esperadas):
        execucao.registrar(FonteExecucao(
            nome="registros", dia=execucao.dia, estado="FAILED",
            motivo="Registros duplicados ou fora das unidades desta execução.",
        ))
    for codigo in esperadas:
        registro = por_unidade.get(codigo)
        if registro is None:
            execucao.registrar(FonteExecucao(
                nome="fechamento", unidade=codigo, dia=execucao.dia,
                motivo="Registro da execução atual indisponível.",
            ))
            continue
        nomes_presentes = {f.nome for f in registro.fontes_execucao if f.unidade == codigo}
        for esperada in list(execucao.fontes):
            if (esperada.unidade == codigo and esperada.nome != "placar"
                    and esperada.nome not in nomes_presentes and esperada.estado in {"SUCCESS", "EMPTY_VALID"}):
                execucao.registrar(esperada.model_copy(update={
                    "estado": "NOT_COLLECTED", "motivo": "Registro sem evidência desta fonte.",
                }))
        if (registro.dia != execucao.dia or registro.proveniencia.execucao_id != execucao.run_id
                or not execucao.iniciado_em <= registro.proveniencia.executado_em
                <= (execucao.terminado_em or agora())):
            execucao.registrar(FonteExecucao(
                nome="fechamento", unidade=codigo, dia=registro.dia, estado="STALE",
                run_id=registro.proveniencia.execucao_id,
                coletado_em=registro.proveniencia.executado_em,
                motivo="Snapshot não pertence à coleta corrente; publicação bloqueada.",
            ))
            continue
        for fonte in registro.fontes_execucao:
            fonte_esperada = next((f for f in execucao.fontes
                             if (f.unidade, f.nome) == (codigo, fonte.nome)), None)
            if fonte.unidade == codigo:
                execucao.registrar(fonte.model_copy(update={
                    "obrigatoria": fonte_esperada.obrigatoria if fonte_esperada else fonte.obrigatoria,
                }))
    execucao.avaliar()


def registros_para_publicacao(
    execucao: ExecucaoNoturna, resultados: list[ResultadoDiario],
) -> list[ResultadoDiario]:
    validar_registros(execucao, resultados)
    if not execucao.permite_publicacao():
        raise ValueError("Auditoria corrente incompleta; relatório financeiro bloqueado.")
    atuais = []
    for registro in resultados:
        adquirentes = []
        for item in registro.recebimentos.adquirentes:
            fonte = next((f for f in execucao.fontes
                          if f.unidade == registro.empresa_codigo and f.nome == item.adquirente), None)
            if fonte and not fonte.obrigatoria and fonte.estado not in {"SUCCESS", "EMPTY_VALID"}:
                instante = formatar_data_hora(fonte.coletado_em) if fonte.coletado_em else "indisponível"
                item = RecebimentoAdquirente(
                    adquirente=item.adquirente, situacao="pendente",
                    erro=f"{fonte.estado}: fonte opcional não validada; última coleta {instante}.",
                )
            adquirentes.append(item)
        mais = registro.mais_pagamentos
        pix = registro.pix_cnpj
        partes = registro.partes_falta
        for f in execucao.fontes:
            if (f.unidade != registro.empresa_codigo or f.obrigatoria
                    or f.estado in {"SUCCESS", "EMPTY_VALID"}):
                continue
            if f.nome == "MAIS_TOTAL" and registro.mais_pagamentos:
                mais = ConferenciaMais(
                    total=None, webposto=None, aviso=f"{f.estado}: declaração não validada.",
                    informado_em=registro.mais_pagamentos.informado_em,
                )
                partes = tuple(p for p in partes if not p.referencia.startswith("mais:"))
            elif f.nome == "PIX_CNPJ" and registro.pix_cnpj:
                pix = ConferenciaPixCnpj(
                    erro=f"{f.estado}: extrato não validado para esta execução.",
                    fontes=registro.pix_cnpj.fontes,
                )
                partes = tuple(p for p in partes if not p.referencia.startswith("pix-cnpj:"))
        atuais.append(registro.model_copy(update={
            "recebimentos": registro.recebimentos.model_copy(update={"adquirentes": tuple(adquirentes)}),
            "mais_pagamentos": mais, "pix_cnpj": pix, "partes_falta": partes,
        }))
    return atuais


async def executar(
    dia: date, *, diretorio: Path | None = None, diretorio_placar: Path | None = None,
    diretorio_pendencias: Path | None = None, timeout: float = TIMEOUT_ETAPA,
    executar_placar: ExecutarPlacar | None = None,
    execucao: ExecucaoNoturna | None = None,
    resultados_execucao: list[ResultadoDiario] | None = None,
) -> int:
    execucao = execucao or ExecucaoNoturna(dia=dia)
    saude_robo.salvar_execucao(execucao)
    configuracao_valida = (
        execucao.dia == dia and os.getenv("WEBPOSTO_WRITES") == "0"
        and os.getenv("LOGOS_CARTAO_AUTOMATICO", "0") == "0"
    )
    execucao.registrar(FonteExecucao(
        nome="configuracao", dia=dia, run_id=execucao.run_id,
        estado="SUCCESS" if configuracao_valida else "BLOCKED",
        coletado_em=agora(), cobertura_inicio=dia, cobertura_fim=dia,
        motivo=None if configuracao_valida else
        "BLOCKED_CONFIG: job exige configuração somente leitura e modo automático desligado.",
    ))
    if not configuracao_valida:
        logger.error("Execucao bloqueada: configuração somente leitura inválida run=%s.", execucao.run_id)
        execucao.finalizar()
        saude_robo.salvar_execucao(execucao)
        saude_robo.salvar_resumo(dia, execucao.aviso_operacional({}))
        saude_robo.salvar_estado(saude_robo.EstadoRobo(
            ultima_execucao=agora(), dia_processado=dia, unidades_processadas=(),
            unidades_com_falha=(), resumo_gerado=False, execucao=execucao,
        ))
        return 1
    execucao_id = execucao.run_id
    falhas = 0
    unidades = carregar_unidades()
    unidades_processadas = [unidade.empresa_codigo for unidade in unidades.values()]
    unidades_com_falha: set[int] = set()
    unidades_com_aviso: set[int] = set()
    resultados = []
    for unidade in unidades.values():
        execucao.registrar(FonteExecucao(nome="fechamento", unidade=unidade.empresa_codigo, dia=dia))
        for adq in unidade.adquirentes:
            execucao.registrar(FonteExecucao(
                nome=adq.nome, unidade=unidade.empresa_codigo, dia=dia,
                obrigatoria=adq.nome != "PREMMIA" and adq.situacao.value != "pendente",
            ))
    if not unidades:
        execucao.registrar(FonteExecucao(nome="unidades", dia=dia, estado="BLOCKED",
                                        motivo="Nenhuma unidade configurada para auditoria."))
    for unidade in unidades.values():
        try:
            aviso_premmia = None
            if unidade.premmia_ativo:
                try:
                    await premmia_portal.coletar(unidade, ate=dia)
                except Exception as exc:
                    # Fronteira do portal: falha de coleta e aviso sanitizado, nao falha da unidade.
                    etapa = getattr(exc, "etapa", None) or "validar/persistir XLSX"
                    logger.warning("Premmia coleta unidade=%s etapa=%s tipo=%s",
                                   unidade.empresa_codigo, etapa, type(exc).__name__)
                    try:
                        coletados = premmia_portal.dias_coletados(premmia_portal.caminho_mensal(unidade, dia))
                        anteriores = [d for d in coletados if d <= dia]
                        ultima = max(anteriores).strftime("%d/%m") if anteriores else "indisponíveis"
                    except Exception as erro_historico:
                        logger.warning("Premmia unidade=%s histórico de coleta indisponível tipo=%s",
                                       unidade.empresa_codigo, type(erro_historico).__name__)
                        ultima = "indisponíveis"
                    aviso_premmia = f"coleta não realizada hoje ({etapa}) — dados até {ultima}"
                    if isinstance(exc, (premmia_portal.PremmiaVerificacaoHumana, premmia_portal.PremmiaIntegridadeAviso)):
                        aviso_premmia += f" · {exc}"
                    unidades_com_aviso.add(unidade.empresa_codigo)
            if aviso_premmia:
                resultado = await coletar_unidade(
                    unidade,
                    dia,
                    execucao_id,
                    timeout=timeout,
                    aviso_premmia=aviso_premmia,
                )
            else:
                resultado = await coletar_unidade(unidade, dia, execucao_id, timeout=timeout)
            salvar_dia(resultado, diretorio=diretorio)
            resultados.append(resultado)
            novas = pendencias_do_dia(resultado)
            novas.extend(executar_reincidencia_mes(
                unidade.empresa_codigo,
                dia,
                carregar=lambda empresa, data: carregar_dia(empresa, data, diretorio=diretorio),
            ))
            if novas:
                repositorio_pendencias.registrar(novas, banco=diretorio_pendencias)
            if resultado.erro_fechamento or any(
                item.situacao == "erro" and item.adquirente != "PREMMIA" for item in resultado.recebimentos.adquirentes
            ):
                falhas += 1
                unidades_com_falha.add(unidade.empresa_codigo)
            if any(
                item.situacao == "credencial inválida" or (item.adquirente == "PREMMIA" and (item.erro or item.situacao == "erro"))
                for item in resultado.recebimentos.adquirentes
            ):
                unidades_com_aviso.add(unidade.empresa_codigo)
            logger.info("Persistido unidade=%s dia=%s execucao=%s", unidade.empresa_codigo, formatar_data(dia), execucao_id)
        except Exception as exc:
            logger.error(
                "Unidade nao concluida unidade=%s dia=%s tipo=%s",
                unidade.empresa_codigo, formatar_data(dia), type(exc).__name__,
            )
            falhas += 1
            unidades_com_falha.add(unidade.empresa_codigo)
            execucao.registrar(FonteExecucao(
                nome="processamento", unidade=unidade.empresa_codigo, dia=dia, estado="FAILED",
                motivo=f"Falha ao concluir unidade ({type(exc).__name__}).",
            ))
    if executar_placar is not None:
        try:
            falhas_placar, unidades_com_falha_placar = await executar_placar(
                dia, timeout, diretorio_placar, execucao,
            )
            falhas += falhas_placar
            unidades_com_falha.update(unidades_com_falha_placar)
            if falhas_placar:
                execucao.registrar(FonteExecucao(nome="placar", dia=dia, estado="FAILED",
                                                motivo="Coleta comercial não concluída."))
        except Exception as exc:
            logger.error("Placar nao concluido tipo=%s", type(exc).__name__)
            falhas += 1
            execucao.registrar(FonteExecucao(nome="placar", dia=dia, estado="FAILED",
                                            motivo="Coleta comercial não concluída."))

    validar_registros(execucao, resultados)
    execucao.finalizar()
    unidades_com_falha.update(
        f.unidade for f in execucao.fontes if f.obrigatoria and f.unidade is not None
        and f.unidade in unidades and f.estado not in {"SUCCESS", "EMPTY_VALID"}
    )
    if resultados_execucao is not None:
        resultados_execucao.extend(resultados)
    resumo_gerado = False
    try:
        completo = execucao.permite_publicacao()
        pendencias_abertas = {
            unidade: repositorio_pendencias.contar_abertas_somente_leitura(
                unidade=unidade,
                banco=diretorio_pendencias,
            )
            for unidade in unidades_processadas
        } if completo else {}
        resumo = gerar_resumo_diario(
            dia,
            registros_para_publicacao(execucao, resultados),
            unidades_processadas,
            unidades_com_falha,
            pendencias_abertas,
        ) if completo else execucao.aviso_operacional(
            {codigo: u.apelido or u.nome for codigo, u in unidades.items()}
        )
        saude_robo.salvar_resumo(dia, resumo)
        resumo_gerado = execucao.permite_publicacao()
    except (OSError, repositorio_pendencias.ErroPersistenciaPendencias, saude_robo.PersistenciaEstadoErro) as exc:
        logger.error(
            "Resumo diario nao concluido dia=%s tipo=%s",
            formatar_data(dia), type(exc).__name__,
        )
        falhas += 1
        execucao.registrar(FonteExecucao(nome="resumo", dia=dia, estado="FAILED",
                                        motivo="Falha ao persistir resumo da execução."))
        execucao.avaliar()
        saude_robo.salvar_resumo(dia, execucao.aviso_operacional({}))
    saude_robo.salvar_execucao(execucao)
    try:
        saude_robo.salvar_estado(saude_robo.EstadoRobo(
            ultima_execucao=agora(),
            dia_processado=dia,
            unidades_processadas=tuple(unidades_processadas),
            unidades_com_falha=tuple(sorted(unidades_com_falha)),
            unidades_com_aviso=tuple(sorted(unidades_com_aviso)),
            resumo_gerado=resumo_gerado,
            execucao=execucao,
        ))
    except saude_robo.PersistenciaEstadoErro as exc:
        logger.error("Estado do robo nao concluido tipo=%s", type(exc).__name__)
        falhas += 1
        execucao.registrar(FonteExecucao(nome="estado", dia=dia, estado="FAILED",
                                        motivo="Falha ao persistir estado da execução."))
        execucao.avaliar()
        saude_robo.salvar_resumo(dia, execucao.aviso_operacional({}))
        saude_robo.salvar_execucao(execucao)
    logger.info(
        "Execucao terminada dia=%s unidades_com_falha=%s unidades_com_aviso=%s execucao=%s",
        formatar_data(dia),
        len(unidades_com_falha),
        len(unidades_com_aviso),
        execucao_id,
    )
    return 1 if falhas or not execucao.permite_publicacao() else 0


def _dia(valor: str) -> date:
    try:
        return ler_data(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def main() -> int:
    from src.jobs.noturno import main as executar_composicao

    return executar_composicao()


if __name__ == "__main__":
    raise SystemExit(main())
