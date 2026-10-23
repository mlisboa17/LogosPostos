"use client";

import { useEffect, useState, useTransition } from "react";
import {
  bloquearPendencia,
  cancelarPendencia,
  classificarPendencia,
  fetchDetalhesPendencia,
  fetchHistoricoPendencia,
  fetchMetricasRevisao,
  fetchPendencias,
  fetchPlanosValidos,
} from "@/lib/classification-api";
import type {
  EstadoRevisao,
  HistoricoEvento,
  ItemFilaRevisao,
  MetricasRevisaoIA,
  PlanoContaFolha,
} from "@/types/classification";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ClockIcon,
  LockIcon,
  ShieldCheckIcon,
  SparklesIcon,
  XCircleIcon,
} from "lucide-react";

const EMPRESAS_NOMES: Record<number, string> = {
  5555: "AP Casa Caiada",
  5556: "Posto doze",
  5557: "Posto VIP",
  5558: "Posto Real (Bloqueado)",
};

export function ClassificationReviewLive() {
  const [pendencias, setPendencias] = useState<ItemFilaRevisao[]>([]);
  const [metricas, setMetricas] = useState<MetricasRevisaoIA | null>(null);
  const [planosValidos, setPlanosValidos] = useState<PlanoContaFolha[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filtros
  const [filtroStatus, setFiltroStatus] = useState<string>("TODOS");
  const [filtroEmpresa, setFiltroEmpresa] = useState<string>("todas");

  // Item selecionado para revisão
  const [selecionado, setSelecionado] = useState<ItemFilaRevisao | null>(null);
  const [historico, setHistorico] = useState<HistoricoEvento[]>([]);
  const [planoEscolhido, setPlanoEscolhido] = useState<number | "">("");
  const [centroCustoEscolhido, setCentroCustoEscolhido] = useState<string>("7295");
  const [justificativa, setJustificativa] = useState<string>("");

  const [isPending, startTransition] = useTransition();

  const carregarDados = () => {
    setLoading(true);
    setErrorMsg(null);
    const emp = filtroEmpresa !== "todas" ? Number(filtroEmpresa) : undefined;

    Promise.all([
      fetchPendencias(filtroStatus, emp),
      fetchMetricasRevisao().catch(() => null),
      fetchPlanosValidos().catch(() => []),
    ])
      .then(([itens, m, p]) => {
        setPendencias(itens);
        setMetricas(m);
        setPlanosValidos(p);
        if (selecionado) {
          const atualizado = itens.find((it) => it.id === selecionado.id);
          if (atualizado) setSelecionado(atualizado);
        }
      })
      .catch((err) => {
        setErrorMsg(err.message || "Erro ao carregar pendências");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    carregarDados();
  }, [filtroStatus, filtroEmpresa]);

  const abrirRevisao = (item: ItemFilaRevisao) => {
    setSelecionado(item);
    setSuccessMsg(null);
    setErrorMsg(null);
    setPlanoEscolhido(
      item.sugestao_plano_codigo && item.sugestao_plano_codigo !== 198966
        ? item.sugestao_plano_codigo
        : ""
    );
    setJustificativa("");

    fetchHistoricoPendencia(item.id)
      .then(setHistorico)
      .catch(() => setHistorico([]));
  };

  const handleClassificar = () => {
    if (!selecionado || !planoEscolhido) {
      setErrorMsg("Selecione um plano de contas folha válido.");
      return;
    }
    if (planoEscolhido === 198966) {
      setErrorMsg("A conta 198966 é temporária e não pode ser definida como plano definitivo.");
      return;
    }

    const planoObj = planosValidos.find((p) => p.plano_conta_codigo === Number(planoEscolhido));

    startTransition(async () => {
      try {
        setErrorMsg(null);
        const res = await classificarPendencia(selecionado.id, {
          versao: selecionado.versao,
          plano_definitivo_codigo: Number(planoEscolhido),
          plano_definitivo_descricao: planoObj?.descricao || "",
          centro_custo_definitivo_codigo: Number(centroCustoEscolhido) || undefined,
          justificativa: justificativa.trim() || undefined,
        });
        setSuccessMsg(`Pendência #${selecionado.id} classificada com sucesso.`);
        setSelecionado(res.item);
        carregarDados();
        fetchHistoricoPendencia(selecionado.id).then(setHistorico);
      } catch (err: any) {
        setErrorMsg(err.message || "Erro ao classificar pendência.");
      }
    });
  };

  const handleBloquear = () => {
    if (!selecionado) return;
    const motivo = prompt("Motivo do bloqueio:");
    if (!motivo) return;

    startTransition(async () => {
      try {
        setErrorMsg(null);
        const res = await bloquearPendencia(selecionado.id, {
          versao: selecionado.versao,
          motivo,
          travas: ["BLOQUEIO_MANUAL_OPERADOR"],
        });
        setSuccessMsg(`Pendência #${selecionado.id} bloqueada.`);
        setSelecionado(res.item);
        carregarDados();
        fetchHistoricoPendencia(selecionado.id).then(setHistorico);
      } catch (err: any) {
        setErrorMsg(err.message || "Erro ao bloquear pendência.");
      }
    });
  };

  const handleCancelar = () => {
    if (!selecionado) return;
    const motivo = prompt("Motivo do cancelamento:");
    if (!motivo) return;

    startTransition(async () => {
      try {
        setErrorMsg(null);
        const res = await cancelarPendencia(selecionado.id, {
          versao: selecionado.versao,
          motivo,
        });
        setSuccessMsg(`Pendência #${selecionado.id} cancelada.`);
        setSelecionado(res.item);
        carregarDados();
        fetchHistoricoPendencia(selecionado.id).then(setHistorico);
      } catch (err: any) {
        setErrorMsg(err.message || "Erro ao cancelar pendência.");
      }
    });
  };

  return (
    <div className="space-y-6 p-4 lg:p-6">
      {/* Banner de Segurança & Governança */}
      <div className="flex flex-col gap-2 rounded-xl border border-cyan-800/40 bg-cyan-950/20 p-4 text-cyan-200 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <ShieldCheckIcon className="size-6 text-cyan-400" />
          <div>
            <div className="font-semibold text-white">
              Fila Local de Revisão e Aprendizagem · Cockpit LOGOS
            </div>
            <div className="text-xs text-cyan-300/80">
              Ambiente de triagem humana estritamente isolado.{" "}
              <strong className="text-white">ERP WRITES = ZERO</strong> (sem POST, PUT, PATCH ou
              DELETE no webPosto).
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="border-cyan-600 bg-cyan-950/60 text-cyan-300">
            Conta 198966 Bloqueada
          </Badge>
          <Badge variant="outline" className="border-amber-600 bg-amber-950/60 text-amber-300">
            Conta 27173 Débito Bloqueado
          </Badge>
        </div>
      </div>

      {/* KPIs & Métricas da IA */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card className="border-amber-900/40 bg-slate-900/80">
          <CardHeader className="pb-2">
            <CardDescription className="text-amber-400">Pendentes de Revisão</CardDescription>
            <CardTitle className="text-2xl text-white">
              {metricas?.total_pendentes ?? pendencias.filter((p) => p.status === "PENDENTE_REVISAO").length}
            </CardTitle>
          </CardHeader>
        </Card>

        <Card className="border-red-900/40 bg-slate-900/80">
          <CardHeader className="pb-2">
            <CardDescription className="text-red-400">Bloqueados por Travas</CardDescription>
            <CardTitle className="text-2xl text-white">
              {metricas?.total_bloqueados ?? pendencias.filter((p) => p.status === "BLOQUEADO").length}
            </CardTitle>
          </CardHeader>
        </Card>

        <Card className="border-emerald-900/40 bg-slate-900/80">
          <CardHeader className="pb-2">
            <CardDescription className="text-emerald-400">Classificados</CardDescription>
            <CardTitle className="text-2xl text-white">
              {metricas?.total_classificados ?? pendencias.filter((p) => p.status === "CLASSIFICADO").length}
            </CardTitle>
          </CardHeader>
        </Card>

        <Card className="border-cyan-900/40 bg-slate-900/80">
          <CardHeader className="pb-2">
            <CardDescription className="text-cyan-400">Acurácia IA (Sugestões)</CardDescription>
            <CardTitle className="flex items-center gap-2 text-2xl text-white">
              <SparklesIcon className="size-5 text-cyan-400" />
              {metricas?.taxa_acerto_ia ?? 0}%
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Alertas */}
      {errorMsg && (
        <div className="flex items-center gap-2 rounded-lg border border-red-800 bg-red-950/50 p-3 text-sm text-red-200">
          <AlertTriangleIcon className="size-4 shrink-0 text-red-400" />
          <span>{errorMsg}</span>
        </div>
      )}
      {successMsg && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-800 bg-emerald-950/50 p-3 text-sm text-emerald-200">
          <CheckCircle2Icon className="size-4 shrink-0 text-emerald-400" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Filtros e Tabela de Pendências */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-7 space-y-4">
          <Card className="border-slate-800 bg-slate-900/90">
            <CardHeader className="pb-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <CardTitle className="text-white">Fila de Classificação</CardTitle>
                  <CardDescription className="text-slate-400">
                    Clique em um item para revisar e selecionar o plano oficial definitivo.
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-white"
                    value={filtroStatus}
                    onChange={(e) => setFiltroStatus(e.target.value)}
                  >
                    <option value="TODOS">Todos os status</option>
                    <option value="PENDENTE_REVISAO">Pendentes</option>
                    <option value="CLASSIFICADO">Classificados</option>
                    <option value="BLOQUEADO">Bloqueados</option>
                    <option value="CANCELADO">Cancelados</option>
                  </select>
                  <select
                    className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-white"
                    value={filtroEmpresa}
                    onChange={(e) => setFiltroEmpresa(e.target.value)}
                  >
                    <option value="todas">Todas empresas</option>
                    <option value="5555">Casa Caiada (5555)</option>
                    <option value="5556">Posto doze (5556)</option>
                    <option value="5557">Posto VIP (5557)</option>
                  </select>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-slate-950/50">
                  <TableRow className="border-slate-800">
                    <TableHead className="text-slate-400">ID / Data</TableHead>
                    <TableHead className="text-slate-400">Empresa / Conta</TableHead>
                    <TableHead className="text-slate-400">Descrição</TableHead>
                    <TableHead className="text-right text-slate-400">Valor</TableHead>
                    <TableHead className="text-center text-slate-400">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pendencias.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-slate-500">
                        {loading ? "Carregando pendências..." : "Nenhuma pendência encontrada."}
                      </TableCell>
                    </TableRow>
                  ) : (
                    pendencias.map((item) => {
                      const isSelected = selecionado?.id === item.id;
                      return (
                        <TableRow
                          key={item.id}
                          className={`cursor-pointer border-slate-800 hover:bg-slate-800/50 ${
                            isSelected ? "bg-slate-800/80" : ""
                          }`}
                          onClick={() => abrirRevisao(item)}
                        >
                          <TableCell className="text-xs">
                            <div className="font-semibold text-white">#{item.id}</div>
                            <div className="text-slate-400">{item.data_movimento}</div>
                          </TableCell>
                          <TableCell className="text-xs">
                            <div className="text-slate-200">
                              {EMPRESAS_NOMES[item.empresa_codigo] || `Empresa ${item.empresa_codigo}`}
                            </div>
                            <div className="text-slate-400">Conta: {item.conta_financeira_codigo}</div>
                          </TableCell>
                          <TableCell className="text-xs">
                            <div className="max-w-[180px] truncate font-medium text-slate-100" title={item.descricao}>
                              {item.descricao}
                            </div>
                            {item.sugestao_plano_descricao && (
                              <div className="text-cyan-400 text-[11px] truncate">
                                Sugestão: {item.sugestao_plano_descricao} ({Math.round(item.confianca_ia * 100)}%)
                              </div>
                            )}
                          </TableCell>
                          <TableCell className="text-right text-xs font-semibold text-emerald-400">
                            {item.valor_formatado}
                          </TableCell>
                          <TableCell className="text-center">
                            {item.status === "PENDENTE_REVISAO" && (
                              <Badge className="bg-amber-950 text-amber-300 border-amber-800 text-[10px]">
                                PENDENTE
                              </Badge>
                            )}
                            {item.status === "CLASSIFICADO" && (
                              <Badge className="bg-emerald-950 text-emerald-300 border-emerald-800 text-[10px]">
                                CLASSIFICADO
                              </Badge>
                            )}
                            {item.status === "BLOQUEADO" && (
                              <Badge className="bg-red-950 text-red-300 border-red-800 text-[10px]">
                                BLOQUEADO
                              </Badge>
                            )}
                            {item.status === "CANCELADO" && (
                              <Badge className="bg-slate-800 text-slate-400 border-slate-700 text-[10px]">
                                CANCELADO
                              </Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        {/* Painel Lateral de Revisão Humana */}
        <div className="lg:col-span-5 space-y-4">
          {selecionado ? (
            <Card className="border-cyan-800/50 bg-slate-900/95 shadow-xl">
              <CardHeader className="border-b border-slate-800 pb-3">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base text-white">
                      Revisão da Pendência #{selecionado.id}
                    </CardTitle>
                    <CardDescription className="text-xs text-slate-400">
                      Versão: v{selecionado.versao} · Hash: {selecionado.hash_idempotencia.slice(0, 8)}...
                    </CardDescription>
                  </div>
                  <Badge variant="outline" className="border-slate-700 text-slate-300 text-xs">
                    {selecionado.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 pt-4 text-xs">
                {/* Dados da Movimentação */}
                <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-950/60 p-3 border border-slate-800">
                  <div>
                    <span className="text-slate-400">Empresa:</span>
                    <div className="font-semibold text-white">
                      {EMPRESAS_NOMES[selecionado.empresa_codigo] || selecionado.empresa_codigo}
                    </div>
                  </div>
                  <div>
                    <span className="text-slate-400">Conta Financeira:</span>
                    <div className="font-semibold text-white">
                      {selecionado.conta_financeira_codigo}
                    </div>
                  </div>
                  <div>
                    <span className="text-slate-400">Data Movimento:</span>
                    <div className="font-semibold text-white">{selecionado.data_movimento}</div>
                  </div>
                  <div>
                    <span className="text-slate-400">Valor:</span>
                    <div className="font-semibold text-emerald-400">{selecionado.valor_formatado}</div>
                  </div>
                  <div className="col-span-2 pt-1 border-t border-slate-800">
                    <span className="text-slate-400">Descrição:</span>
                    <div className="font-medium text-white">{selecionado.descricao}</div>
                  </div>
                </div>

                {/* Evidências Sanitizadas */}
                {selecionado.referencia_evidencias && (
                  <div className="rounded-lg bg-slate-950/40 p-3 border border-slate-800">
                    <div className="font-semibold text-slate-300 mb-1 flex items-center gap-1.5">
                      <LockIcon className="size-3.5 text-cyan-400" />
                      Evidências (Sanitizadas)
                    </div>
                    <p className="text-slate-400 font-mono text-[11px] break-all">
                      {selecionado.referencia_evidencias}
                    </p>
                  </div>
                )}

                {/* Sugestão da IA & Confiança */}
                <div className="rounded-lg bg-slate-950/40 p-3 border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-cyan-300 flex items-center gap-1">
                      <SparklesIcon className="size-3.5" /> Sugestão da IA:
                    </span>
                    <Badge variant="outline" className="border-cyan-700 text-cyan-300">
                      {Math.round(selecionado.confianca_ia * 100)}% Confiança
                    </Badge>
                  </div>
                  <div className="text-slate-200">
                    {selecionado.sugestao_plano_codigo ? (
                      <span>
                        <strong>{selecionado.sugestao_plano_codigo}</strong> — {selecionado.sugestao_plano_descricao}
                      </span>
                    ) : (
                      <span className="text-slate-500">Nenhuma sugestão automática</span>
                    )}
                  </div>
                  {selecionado.justificativa_ia && (
                    <div className="text-slate-400 italic text-[11px]">
                      "{selecionado.justificativa_ia}"
                    </div>
                  )}
                </div>

                {/* Travas Encontradas */}
                {selecionado.travas_encontradas.length > 0 && (
                  <div className="rounded-lg bg-red-950/20 p-3 border border-red-900/40">
                    <div className="font-semibold text-red-300 mb-1 flex items-center gap-1.5">
                      <AlertTriangleIcon className="size-3.5 text-red-400" />
                      Travas Impeditivas Ativas:
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {selecionado.travas_encontradas.map((trava, idx) => (
                        <Badge key={idx} variant="destructive" className="text-[10px]">
                          {trava}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Seleção de Plano Definitivo */}
                <div className="space-y-3 rounded-lg bg-slate-950/70 p-3 border border-cyan-900/50">
                  <Label className="text-cyan-300 font-semibold block">
                    Plano de Contas Oficial Definitivo (Somente Folha Candidata)
                  </Label>
                  <select
                    className="w-full rounded-md border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-cyan-500 focus:outline-none"
                    value={planoEscolhido}
                    onChange={(e) => setPlanoEscolhido(e.target.value ? Number(e.target.value) : "")}
                  >
                    <option value="">-- Selecione a conta folha oficial --</option>
                    {planosValidos.map((plano) => (
                      <option key={plano.plano_conta_codigo} value={plano.plano_conta_codigo}>
                        {plano.hierarquia} · {plano.plano_conta_codigo} - {plano.descricao}
                      </option>
                    ))}
                  </select>
                  <p className="text-[10px] text-slate-400">
                    * Contas-pai e a conta temporária 198966 foram categoricamente excluídas.
                  </p>

                  <div>
                    <Label className="text-slate-300 text-xs">Justificativa da Classificação:</Label>
                    <Input
                      className="mt-1 border-slate-700 bg-slate-800 text-xs text-white"
                      placeholder="Ex: Documento fiscal auditado confirmando despesa..."
                      value={justificativa}
                      onChange={(e) => setJustificativa(e.target.value)}
                    />
                  </div>

                  {/* Botões de Ação */}
                  <div className="flex items-center gap-2 pt-2">
                    <Button
                      size="sm"
                      className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs"
                      disabled={isPending || !planoEscolhido || selecionado.status === "CLASSIFICADO"}
                      onClick={handleClassificar}
                    >
                      <CheckCircle2Icon className="mr-1.5 size-4" />
                      Classificar (Local)
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-red-800 text-red-300 hover:bg-red-950 text-xs"
                      disabled={isPending || selecionado.status === "BLOQUEADO"}
                      onClick={handleBloquear}
                    >
                      Bloquear
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-slate-400 hover:bg-slate-800 text-xs"
                      disabled={isPending || selecionado.status === "CANCELADO"}
                      onClick={handleCancelar}
                    >
                      Cancelar
                    </Button>
                  </div>
                </div>

                {/* Histórico Imutável */}
                <div className="space-y-2 pt-2">
                  <div className="font-semibold text-slate-300 flex items-center gap-1.5">
                    <ClockIcon className="size-3.5 text-slate-400" />
                    Trilha Auditável de Mudanças
                  </div>
                  <div className="max-h-36 overflow-y-auto rounded-md border border-slate-800 bg-slate-950/50 p-2 space-y-1.5">
                    {historico.length === 0 ? (
                      <div className="text-slate-500 text-[11px]">Nenhum histórico registrado.</div>
                    ) : (
                      historico.map((h) => (
                        <div key={h.id} className="text-[11px] border-b border-slate-900 pb-1">
                          <div className="flex items-center justify-between text-slate-400">
                            <span className="font-semibold text-cyan-300">{h.acao}</span>
                            <span>{new Date(h.timestamp).toLocaleTimeString()}</span>
                          </div>
                          <div className="text-slate-300">
                            Por: <span className="text-white">{h.usuario_ou_sistema}</span>
                            {h.status_anterior && (
                              <span> ({h.status_anterior} → {h.status_novo})</span>
                            )}
                          </div>
                          {h.justificativa && (
                            <div className="text-slate-500 italic">"{h.justificativa}"</div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-slate-800 bg-slate-900/40 p-8 text-center text-slate-500">
              Selecione uma pendência na tabela ao lado para visualizar os detalhes e realizar a
              classificação humana.
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
