"use client";

import React, { useEffect, useMemo, useState, useTransition } from "react";
import {
  fetchFechamentoCaixa,
  fetchFiltrosOperacionais,
  fetchPendenciasCaixa,
  fetchRelatorioCaixa,
} from "@/lib/cash-audit-api";
import type {
  AlertaCaixa,
  AuditoriaCaixaItem,
  DiaConsolidado,
  FechamentoFiltrosParams,
  FiltrosOperacionaisResponse,
  FuncionarioFechamento,
  MovimentoDespesa,
  PendenciaCaixa,
  RelatorioCaixaItem,
  ResultadoAuditoriaFechamento,
  SeveridadeAlerta,
} from "@/types/cash-audit";
import { presetRange, todayRecife } from "@/lib/datetime-br";
import { fmtBRL } from "@/lib/format";
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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertCircleIcon,
  AlertTriangleIcon,
  ArrowDownRightIcon,
  CalendarDaysIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClockIcon,
  CopyIcon,
  FileTextIcon,
  FilterIcon,
  FuelIcon,
  LayersIcon,
  ReceiptIcon,
  RefreshCwIcon,
  ShieldAlertIcon,
  SlidersHorizontalIcon,
  WalletIcon,
  UsersIcon,
  XIcon,
} from "lucide-react";

export const UNIDADES_DISPONIVEIS = [
  { id: 74014, nome: "Real / Posto Doze", rotulo: "Posto Doze Filial II (Real)", apelido: "Real" },
  { id: 5555, nome: "Casa Caiada", rotulo: "AP Casa Caiada", apelido: "Casa Caiada" },
  { id: 11495, nome: "Rio Doce / VIP", rotulo: "Posto VIP (Rio Doce)", apelido: "VIP" },
  { id: 118508, nome: "Abreu e Lima / Conv. 24h", rotulo: "Conveniência 24 Horas", apelido: "Conv. 24h" },
];

export function CashAuditLive() {
  // Estado dos Filtros Globais
  const [unidadeSelecionada, setUnidadeSelecionada] = useState<number>(11495); // Default: Posto VIP
  const [presetAtivo, setPresetAtivo] = useState<"hoje" | "ontem" | "7d" | "15d" | "30d" | "mes">("7d");
  const [dataInicio, setDataInicio] = useState<string>(() => presetRange("7d").inicio);
  const [dataFim, setDataFim] = useState<string>(() => presetRange("7d").fim);

  // Modo de Visualização (Analítico x Consolidado)
  const [modoVisualizacao, setModoVisualizacao] = useState<"analitico" | "consolidado">("analitico");
  const [diasExpandidos, setDiasExpandidos] = useState<Record<string, boolean>>({});

  // Metadados Operacionais Dinâmicos (WebPosto)
  const [filtrosMeta, setFiltrosMeta] = useState<FiltrosOperacionaisResponse | null>(null);
  const [loadingFiltros, setLoadingFiltros] = useState<boolean>(false);

  // Filtros Operacionais Selecionados
  const [tipoData, setTipoData] = useState<"movimento" | "fiscal">("movimento");
  const [centroCusto, setCentroCusto] = useState<string>("todos");
  const [turno, setTurno] = useState<string>("todos");
  const [pdv, setPdv] = useState<string>("todos");
  const [funcionario, setFuncionario] = useState<string>("todos");

  // Estados de Dados
  const [dadosAuditoria, setDadosAuditoria] = useState<ResultadoAuditoriaFechamento | null>(null);
  const [pendencias, setPendencias] = useState<PendenciaCaixa[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [erroMsg, setErroMsg] = useState<string | null>(null);

  // Linhas Expandidas (Accordion)
  const [caixasExpandidos, setCaixasExpandidos] = useState<Record<number, boolean>>({});

  // Sheet de Relatório Executivo (Markdown)
  const [sheetRelatorioAberto, setSheetRelatorioAberto] = useState<boolean>(false);
  const [relatorioCarregando, setRelatorioCarregando] = useState<boolean>(false);
  const [relatorioMarkdown, setRelatorioMarkdown] = useState<string>("");
  const [copiadoFeedback, setCopiadoFeedback] = useState<boolean>(false);

  const [isPending, startTransition] = useTransition();

  const toggleExpansaoDia = (dia: string) => {
    setDiasExpandidos((prev) => ({
      ...prev,
      [dia]: !prev[dia],
    }));
  };

  // Dicionários para exibição rápida de nomes amigáveis
  const funcionariosMap = useMemo(() => {
    const map = new Map<number, string>();
    if (filtrosMeta?.funcionarios) {
      for (const f of filtrosMeta.funcionarios) {
        map.set(f.codigo, f.nome);
      }
    }
    return map;
  }, [filtrosMeta]);

  const centrosCustoMap = useMemo(() => {
    const map = new Map<number, string>();
    if (filtrosMeta?.centros_custo) {
      for (const c of filtrosMeta.centros_custo) {
        map.set(c.codigo, c.nome);
      }
    }
    return map;
  }, [filtrosMeta]);

  // Agrupamento Consolidado / Sintético por Data
  const diasConsolidados = useMemo<DiaConsolidado[]>(() => {
    if (!dadosAuditoria?.caixas) return [];
    const mapaDias = new Map<string, AuditoriaCaixaItem[]>();
    for (const item of dadosAuditoria.caixas) {
      const d = item.caixa.data;
      if (!mapaDias.has(d)) mapaDias.set(d, []);
      mapaDias.get(d)!.push(item);
    }

    const resultado: DiaConsolidado[] = [];
    for (const [dia, caixasDoDia] of mapaDias.entries()) {
      const pdvs = Array.from(new Set(caixasDoDia.map((c) => c.caixa.pdv_codigo))).sort();
      const funcs = Array.from(
        new Set(
          caixasDoDia.flatMap((c) => [
            c.caixa.funcionario_codigo,
            ...(c.funcionarios_participantes || []).map((p) => p.codigo),
          ])
        )
      ).sort();
      const turnos = Array.from(new Set(caixasDoDia.map((c) => c.caixa.turno))).sort();

      let apuradoTotal = 0;
      let declaradoTotal = 0;
      let quebraTotal = 0;
      let severidade: SeveridadeAlerta | null = null;

      const modalidadesMap = new Map<
        string,
        { rotulo: string; apresentado: number; apurado: number; diferenca: number }
      >();
      const alertasTotais: AlertaCaixa[] = [];
      const despesasTotais: MovimentoDespesa[] = [];

      for (const item of caixasDoDia) {
        quebraTotal += Number(item.quebra || 0);
        if (item.severidade === "vermelho") {
          severidade = "vermelho";
        } else if (item.severidade === "laranja" && severidade !== "vermelho") {
          severidade = "laranja";
        }

        for (const m of item.modalidades) {
          const key = m.modalidade;
          const ap = Number(m.apresentado || 0);
          const apu = Number(m.apurado || 0);
          const dif = Number(m.diferenca || 0);

          declaradoTotal += ap;
          apuradoTotal += apu;

          if (!modalidadesMap.has(key)) {
            modalidadesMap.set(key, { rotulo: m.rotulo, apresentado: 0, apurado: 0, diferenca: 0 });
          }
          const mod = modalidadesMap.get(key)!;
          mod.apresentado += ap;
          mod.apurado += apu;
          mod.diferenca += dif;
        }

        if (item.alertas) {
          alertasTotais.push(...item.alertas);
        }
        if (item.despesas) {
          despesasTotais.push(...item.despesas);
        }
      }

      resultado.push({
        data: dia,
        totalCaixas: caixasDoDia.length,
        pdvs,
        funcionarios: funcs,
        turnos,
        apuradoTotal,
        declaradoTotal,
        quebraTotal,
        severidade,
        caixas: caixasDoDia,
        modalidadesConsolidadas: Array.from(modalidadesMap.entries()).map(([k, v]) => ({
          modalidade: k,
          ...v,
        })),
        alertasTotais,
        despesasTotais,
      });
    }

    return resultado.sort((a, b) => b.data.localeCompare(a.data));
  }, [dadosAuditoria?.caixas]);

  const aplicarPreset = (preset: "hoje" | "ontem" | "7d" | "15d" | "30d" | "mes") => {
    setPresetAtivo(preset);
    const range = presetRange(preset);
    setDataInicio(range.inicio);
    setDataFim(range.fim);
  };

  const carregarDados = (customFiltros?: {
    tipoData?: "movimento" | "fiscal";
    centroCusto?: string;
    turno?: string;
    pdv?: string;
    funcionario?: string;
    inicio?: string;
    fim?: string;
    unidade?: number;
  }) => {
    setLoading(true);
    setErroMsg(null);

    const u = customFiltros?.unidade ?? unidadeSelecionada;
    const ini = customFiltros?.inicio ?? dataInicio;
    const f = customFiltros?.fim ?? dataFim;
    const td = customFiltros?.tipoData ?? tipoData;
    const cc = customFiltros?.centroCusto ?? centroCusto;
    const tr = customFiltros?.turno ?? turno;
    const p = customFiltros?.pdv ?? pdv;
    const fn = customFiltros?.funcionario ?? funcionario;

    const queryParams: FechamentoFiltrosParams = {
      tipo_data: td,
      centro_custo: cc !== "todos" ? Number(cc) : undefined,
      turno: tr !== "todos" ? tr : undefined,
      pdv_codigo: p !== "todos" ? Number(p) : undefined,
      funcionario_codigo: fn !== "todos" ? Number(fn) : undefined,
    };

    startTransition(async () => {
      try {
        const [fechamentoRes, pendenciasRes] = await Promise.all([
          fetchFechamentoCaixa(u, ini, f, queryParams),
          fetchPendenciasCaixa(u, "aberta").catch(() => []),
        ]);
        setDadosAuditoria(fechamentoRes);
        setPendencias(pendenciasRes);
      } catch (err: any) {
        setErroMsg(err.message || "Erro desconhecido ao carregar auditoria de caixa.");
      } finally {
        setLoading(false);
      }
    });
  };

  // 1. Mudança de unidade: carrega os metadados operacionais do WebPosto e reseta filtros filhos
  useEffect(() => {
    let ativo = true;
    setLoadingFiltros(true);
    setCentroCusto("todos");
    setTurno("todos");
    setPdv("todos");
    setFuncionario("todos");

    fetchFiltrosOperacionais(unidadeSelecionada)
      .then((dados) => {
        if (ativo) {
          setFiltrosMeta(dados);
        }
      })
      .catch((err) => {
        console.warn("Falha ao carregar metadados operacionais:", err);
      })
      .finally(() => {
        if (ativo) {
          setLoadingFiltros(false);
        }
      });

    return () => {
      ativo = false;
    };
  }, [unidadeSelecionada]);

  // 2. Consulta automática ao trocar Unidade ou Intervalo de Datas
  useEffect(() => {
    carregarDados({
      unidade: unidadeSelecionada,
      inicio: dataInicio,
      fim: dataFim,
      centroCusto: "todos",
      turno: "todos",
      pdv: "todos",
      funcionario: "todos",
    });
  }, [unidadeSelecionada, dataInicio, dataFim]);

  const limparFiltrosOperacionais = () => {
    setTipoData("movimento");
    setCentroCusto("todos");
    setTurno("todos");
    setPdv("todos");
    setFuncionario("todos");
    carregarDados({
      tipoData: "movimento",
      centroCusto: "todos",
      turno: "todos",
      pdv: "todos",
      funcionario: "todos",
    });
  };

  const temFiltroAtivo =
    centroCusto !== "todos" ||
    turno !== "todos" ||
    pdv !== "todos" ||
    funcionario !== "todos" ||
    tipoData !== "movimento";


  const toggleExpansaoCaixa = (caixaCodigo: number) => {
    setCaixasExpandidos((prev) => ({
      ...prev,
      [caixaCodigo]: !prev[caixaCodigo],
    }));
  };

  const abrirRelatorioExecutivo = async () => {
    setSheetRelatorioAberto(true);
    setRelatorioCarregando(true);
    setCopiadoFeedback(false);
    try {
      // Consulta o relatório para a data mais recente do filtro selecionado
      const res = await fetchRelatorioCaixa(dataFim, unidadeSelecionada);
      const relatorioUnidade =
        res.relatorios.find((r) => r.unidade === unidadeSelecionada) || res.relatorios[0];
      setRelatorioMarkdown(relatorioUnidade?.markdown || "Nenhum relatório disponível para a data.");
    } catch (err: any) {
      setRelatorioMarkdown(`Erro ao carregar relatório: ${err.message}`);
    } finally {
      setRelatorioCarregando(false);
    }
  };

  const copiarMarkdown = () => {
    if (relatorioMarkdown) {
      navigator.clipboard.writeText(relatorioMarkdown);
      setCopiadoFeedback(true);
      setTimeout(() => setCopiadoFeedback(false), 2000);
    }
  };

  // Cálculos de Resumo / KPIs
  const caixas = dadosAuditoria?.caixas ?? [];
  const totalCaixas = caixas.length;

  const faturamentoTotal = caixas.reduce((acc, item) => {
    const apurado = Number(item.caixa.apurado || 0);
    return acc + apurado;
  }, 0);

  const totalSangrias = useMemo(() => {
    if (dadosAuditoria?.total_sangrias !== undefined) {
      return Number(dadosAuditoria.total_sangrias || 0);
    }
    return caixas.reduce((acc, item) => {
      const sangriasCx = (item.sangrias || []).reduce(
        (sAcc, s) => sAcc + Number(s.valor || 0),
        0
      );
      return acc + (Number(item.total_sangrias || 0) || sangriasCx);
    }, 0);
  }, [dadosAuditoria, caixas]);

  const quebraTotalLiquida = Number(dadosAuditoria?.quebra_total || 0);
  const totalComAlertaVermelho = caixas.filter((c) => c.severidade === "vermelho").length;
  const totalComAlertaLaranja = caixas.filter((c) => c.severidade === "laranja").length;

  const totalFaltososGeral = useMemo(() => {
    let count = 0;
    for (const c of caixas) {
      const particsFalta = (c.funcionarios_participantes || []).filter(
        (p) => Number(p.quebra_sobra || 0) < 0
      );
      if (particsFalta.length > 0) {
        count += particsFalta.length;
      } else if (Number(c.quebra || 0) < 0) {
        count += 1;
      }
    }
    return count;
  }, [caixas]);

  return (
    <div className="flex-1 space-y-6 p-4 md:p-6 lg:p-8">
      {/* Cabeçalho da Página */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 shadow-inner">
              <ReceiptIcon className="size-5" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white">
                Auditoria de Fechamento de Caixa
              </h1>
              <p className="text-sm text-slate-400">
                Conferência diária, despesas de pista, conciliação de espécies e controle de quebras (FECHAMENTO_V4).
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {pendencias.length > 0 && (
            <Badge variant="outline" className="border-red-600/80 bg-red-950/70 text-red-300 gap-1.5 py-1 px-3">
              <ShieldAlertIcon className="size-3.5" />
              <span>{pendencias.length} pendências abertas</span>
            </Badge>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={abrirRelatorioExecutivo}
            className="border-slate-700 bg-slate-800/90 hover:bg-slate-700 text-slate-200 gap-2"
          >
            <FileTextIcon className="size-4 text-cyan-400" />
            <span>Ver Relatório do Dia</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => carregarDados()}
            disabled={loading || isPending}
            className="border-slate-700 bg-slate-800/90 hover:bg-slate-700 text-slate-200 gap-2"
          >
            <RefreshCwIcon className={`size-4 ${loading ? "animate-spin text-cyan-400" : ""}`} />
            <span>Atualizar</span>
          </Button>
        </div>
      </div>

      {/* Barra de Filtros */}
      <Card className="border-slate-800 bg-slate-900/90 shadow-lg">
        <CardContent className="p-4 sm:p-5 space-y-4">
          {/* Linha 1: Unidade, Tipo de Data e Datas */}
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            {/* Seletor de Unidade */}
            <div className="space-y-1.5 flex-1 max-w-sm">
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Unidade / Posto
              </Label>
              <select
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white shadow-sm transition-colors focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                value={unidadeSelecionada}
                onChange={(e) => setUnidadeSelecionada(Number(e.target.value))}
              >
                {UNIDADES_DISPONIVEIS.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.rotulo} (Cód. {u.id})
                  </option>
                ))}
              </select>
            </div>

            {/* Tipo de Data: Radio/Toggle */}
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Tipo de Data
              </Label>
              <div className="flex items-center rounded-lg border border-slate-700 bg-slate-800 p-0.5">
                <button
                  type="button"
                  onClick={() => setTipoData("movimento")}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    tipoData === "movimento"
                      ? "bg-cyan-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Data Movimento
                </button>
                <button
                  type="button"
                  onClick={() => setTipoData("fiscal")}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    tipoData === "fiscal"
                      ? "bg-cyan-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Data Fiscal
                </button>
              </div>
            </div>

            {/* Modo de Visualização: Analítico x Consolidado */}
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Visualização
              </Label>
              <div className="flex items-center rounded-lg border border-slate-700 bg-slate-800 p-0.5">
                <button
                  type="button"
                  onClick={() => setModoVisualizacao("analitico")}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    modoVisualizacao === "analitico"
                      ? "bg-cyan-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Analítico (Turnos)
                </button>
                <button
                  type="button"
                  onClick={() => setModoVisualizacao("consolidado")}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    modoVisualizacao === "consolidado"
                      ? "bg-cyan-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Consolidado (Sintético)
                </button>
              </div>
            </div>

            {/* Presets de Período */}
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Atalhos
              </Label>
              <div className="flex items-center gap-1.5 flex-wrap">
                <Button
                  type="button"
                  variant={presetAtivo === "hoje" ? "default" : "outline"}
                  size="sm"
                  onClick={() => aplicarPreset("hoje")}
                  className={presetAtivo === "hoje" ? "bg-cyan-600 hover:bg-cyan-500 text-white text-xs h-8" : "border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs h-8"}
                >
                  Hoje
                </Button>
                <Button
                  type="button"
                  variant={presetAtivo === "ontem" ? "default" : "outline"}
                  size="sm"
                  onClick={() => aplicarPreset("ontem")}
                  className={presetAtivo === "ontem" ? "bg-cyan-600 hover:bg-cyan-500 text-white text-xs h-8" : "border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs h-8"}
                >
                  Ontem
                </Button>
                <Button
                  type="button"
                  variant={presetAtivo === "7d" ? "default" : "outline"}
                  size="sm"
                  onClick={() => aplicarPreset("7d")}
                  className={presetAtivo === "7d" ? "bg-cyan-600 hover:bg-cyan-500 text-white text-xs h-8" : "border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs h-8"}
                >
                  7 dias
                </Button>
                <Button
                  type="button"
                  variant={presetAtivo === "15d" ? "default" : "outline"}
                  size="sm"
                  onClick={() => aplicarPreset("15d")}
                  className={presetAtivo === "15d" ? "bg-cyan-600 hover:bg-cyan-500 text-white text-xs h-8" : "border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs h-8"}
                >
                  15 dias
                </Button>
                <Button
                  type="button"
                  variant={presetAtivo === "30d" ? "default" : "outline"}
                  size="sm"
                  onClick={() => aplicarPreset("30d")}
                  className={presetAtivo === "30d" ? "bg-cyan-600 hover:bg-cyan-500 text-white text-xs h-8" : "border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs h-8"}
                >
                  30 dias
                </Button>
                <Button
                  type="button"
                  variant={presetAtivo === "mes" ? "default" : "outline"}
                  size="sm"
                  onClick={() => aplicarPreset("mes")}
                  className={presetAtivo === "mes" ? "bg-cyan-600 hover:bg-cyan-500 text-white text-xs h-8" : "border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs h-8"}
                >
                  Mês Atual
                </Button>
              </div>
            </div>

            {/* Date Pickers */}
            <div className="flex items-center gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="data-inicio" className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Data Inicial
                </Label>
                <Input
                  id="data-inicio"
                  type="date"
                  value={dataInicio}
                  onChange={(e) => {
                    setDataInicio(e.target.value);
                    setPresetAtivo("7d");
                  }}
                  className="w-36 border-slate-700 bg-slate-800 text-white text-xs h-9"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="data-fim" className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Data Final
                </Label>
                <Input
                  id="data-fim"
                  type="date"
                  value={dataFim}
                  onChange={(e) => {
                    setDataFim(e.target.value);
                    setPresetAtivo("7d");
                  }}
                  className="w-36 border-slate-700 bg-slate-800 text-white text-xs h-9"
                />
              </div>
            </div>
          </div>

          {/* Linha 2: Metadados Operacionais Dinâmicos (WebPosto - Zero Hardcode) */}
          <div className="pt-3 border-t border-slate-800/80">
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2">
                <SlidersHorizontalIcon className="size-3.5 text-cyan-400" />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Filtros Operacionais da Filial
                </span>
                {loadingFiltros ? (
                  <span className="inline-flex items-center gap-1 text-[11px] text-cyan-400">
                    <RefreshCwIcon className="size-3 animate-spin" />
                    Carregando do ERP...
                  </span>
                ) : (
                  <span className="text-[11px] text-slate-500">
                    ({filtrosMeta?.centros_custo.length ?? 0} centros · {filtrosMeta?.funcionarios.length ?? 0} operadores · {filtrosMeta?.pdvs.length ?? 0} PDVs)
                  </span>
                )}
              </div>

              {temFiltroAtivo && (
                <button
                  type="button"
                  onClick={limparFiltrosOperacionais}
                  className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors"
                >
                  <XIcon className="size-3" />
                  <span>Limpar filtros operacionais</span>
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
              {/* Centro de Custo */}
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-400">
                  Centro de Custo
                </Label>
                <select
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white shadow-sm transition-colors focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  value={centroCusto}
                  onChange={(e) => setCentroCusto(e.target.value)}
                  disabled={loadingFiltros}
                >
                  <option value="todos">Todos os Centros</option>
                  {filtrosMeta?.centros_custo.map((c) => (
                    <option key={c.codigo} value={c.codigo}>
                      {c.nome} (Cód. {c.codigo})
                    </option>
                  ))}
                </select>
              </div>

              {/* Turno */}
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-400">
                  Turno
                </Label>
                <select
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white shadow-sm transition-colors focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  value={turno}
                  onChange={(e) => setTurno(e.target.value)}
                  disabled={loadingFiltros}
                >
                  <option value="todos">Todos os Turnos</option>
                  {filtrosMeta?.turnos.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              {/* PDV */}
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-400">
                  PDV / Ponto de Venda
                </Label>
                <select
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white shadow-sm transition-colors focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  value={pdv}
                  onChange={(e) => setPdv(e.target.value)}
                  disabled={loadingFiltros}
                >
                  <option value="todos">Todos os PDVs</option>
                  {filtrosMeta?.pdvs.map((p) => (
                    <option key={p.codigo} value={p.codigo}>
                      {p.nome}
                    </option>
                  ))}
                </select>
              </div>

              {/* Funcionário / Operador */}
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-400">
                  Operador / Frentista
                </Label>
                <select
                  className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white shadow-sm transition-colors focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  value={funcionario}
                  onChange={(e) => setFuncionario(e.target.value)}
                  disabled={loadingFiltros}
                >
                  <option value="todos">
                    Todos os Operadores ({filtrosMeta?.funcionarios.length ?? 0})
                  </option>
                  {filtrosMeta?.funcionarios.map((f) => (
                    <option key={f.codigo} value={f.codigo}>
                      {f.nome} (Cód. {f.codigo})
                    </option>
                  ))}
                </select>
              </div>

              {/* Botão Consultar */}
              <div>
                <Button
                  type="button"
                  onClick={() => carregarDados()}
                  disabled={loading || isPending}
                  className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs h-9 gap-2 shadow-sm"
                >
                  <FilterIcon className="size-3.5" />
                  <span>Consultar</span>
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Alertas de Erro */}
      {erroMsg && (
        <div className="flex items-center gap-3 rounded-xl border border-red-800/80 bg-red-950/60 p-4 text-sm text-red-200">
          <AlertCircleIcon className="size-5 shrink-0 text-red-400" />
          <div className="flex-1">
            <p className="font-semibold text-red-300">Falha na consulta</p>
            <p className="text-xs text-red-200/90">{erroMsg}</p>
          </div>
        </div>
      )}

      {/* Cards de KPIs Executivos */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {/* Total Faturado */}
        <Card className="border-slate-800 bg-slate-900/90 shadow-md">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-medium uppercase tracking-wider text-slate-400">
              Total Faturado
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-white flex items-center justify-between">
              <span>{loading ? "..." : fmtBRL(faturamentoTotal)}</span>
              <FuelIcon className="size-5 text-cyan-400" />
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-slate-400">
            Vendas apuradas de {totalCaixas} turnos ({diasConsolidados.length} dias)
          </CardContent>
        </Card>

        {/* Total de Sangrias */}
        <Card className="border-slate-800 bg-slate-900/90 shadow-md">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-medium uppercase tracking-wider text-slate-400">
              Total de Sangrias
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-amber-300 flex items-center justify-between">
              <span>{loading ? "..." : fmtBRL(totalSangrias)}</span>
              <ArrowDownRightIcon className="size-5 text-amber-400" />
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-slate-400">
            Recolhido para cofres e contas no período
          </CardContent>
        </Card>

        {/* Quebra Líquida Geral */}
        <Card className={`border-slate-800 bg-slate-900/90 shadow-md ${quebraTotalLiquida < 0 ? "border-red-900/60 bg-red-950/30" : ""}`}>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-medium uppercase tracking-wider text-slate-400">
              Quebra Líquida Geral
            </CardDescription>
            <CardTitle className={`text-2xl font-bold flex items-center justify-between ${quebraTotalLiquida < 0 ? "text-red-400 font-mono" : "text-emerald-400 font-mono"}`}>
              <span>{loading ? "..." : fmtBRL(quebraTotalLiquida)}</span>
              {quebraTotalLiquida < 0 ? (
                <ShieldAlertIcon className="size-5 text-red-400" />
              ) : (
                <CheckCircle2Icon className="size-5 text-emerald-400" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs">
            {totalFaltososGeral > 0 ? (
              <span className="text-red-400 font-semibold">{totalFaltososGeral} operador(es) com falta no período</span>
            ) : quebraTotalLiquida < 0 ? (
              <span className="text-red-400 font-medium">Diferença negativa consolidada</span>
            ) : (
              <span className="text-emerald-400 font-medium">Caixas conformes / sem quebra</span>
            )}
          </CardContent>
        </Card>

        {/* Total de Caixas / Turnos */}
        <Card className="border-slate-800 bg-slate-900/90 shadow-md">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-medium uppercase tracking-wider text-slate-400">
              Caixas / Turnos Auditados
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-white flex items-center justify-between">
              <span>{loading ? "..." : totalCaixas}</span>
              <ClockIcon className="size-5 text-slate-500" />
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-slate-400">
            {totalComAlertaVermelho > 0 ? (
              <span className="text-red-400 font-semibold">{totalComAlertaVermelho} com falta sem vale lançado</span>
            ) : (
              <span>Conformidade operacional geral</span>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tabela Principal de Caixas */}
      <Card className="border-slate-800 bg-slate-900/90 shadow-xl overflow-hidden">
        <CardHeader className="border-b border-slate-800/80 bg-slate-950/40 px-5 py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="text-lg font-bold text-white flex items-center gap-2">
                {modoVisualizacao === "consolidado" ? (
                  <>
                    <LayersIcon className="size-5 text-cyan-400" />
                    <span>Visão Consolidada de Caixas (Sintético por Dia)</span>
                  </>
                ) : (
                  <span>Turnos e Fechamentos de Caixa (Analítico)</span>
                )}
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                {modoVisualizacao === "consolidado"
                  ? "Soma diária unificada de apuração, declaração, espécies e quebra líquida por filial."
                  : "Detalhamento dos caixas operacionais, apuração vs declaração e justificativas."}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2.5">
              <div className="flex items-center rounded-lg border border-slate-700 bg-slate-800 p-0.5">
                <button
                  type="button"
                  onClick={() => setModoVisualizacao("analitico")}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    modoVisualizacao === "analitico"
                      ? "bg-cyan-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Analítico
                </button>
                <button
                  type="button"
                  onClick={() => setModoVisualizacao("consolidado")}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    modoVisualizacao === "consolidado"
                      ? "bg-cyan-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Consolidado
                </button>
              </div>

              {dadosAuditoria?.proveniencia?.versao_regra && (
                <span className="rounded bg-slate-800 px-2 py-1 text-slate-300 font-mono text-xs">
                  {dadosAuditoria.proveniencia.versao_regra}
                </span>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader className="bg-slate-950/80 text-xs text-slate-400">
                <TableRow className="border-slate-800 hover:bg-transparent">
                  <TableHead className="w-10"></TableHead>
                  <TableHead className="text-slate-300 font-semibold">Status / Alerta</TableHead>
                  <TableHead className="text-slate-300 font-semibold">
                    {modoVisualizacao === "consolidado" ? "Data Movimento" : "Data / Turno"}
                  </TableHead>
                  <TableHead className="text-slate-300 font-semibold">
                    {modoVisualizacao === "consolidado" ? "Consolidação (Turnos / PDVs / Operadores)" : "Operador / PDV"}
                  </TableHead>
                  <TableHead className="text-right text-slate-300 font-semibold">Esperado</TableHead>
                  <TableHead className="text-right text-slate-300 font-semibold">Declarado</TableHead>
                  <TableHead className="text-right text-slate-300 font-semibold">Quebra / Sobra</TableHead>
                  <TableHead className="text-center text-slate-300 font-semibold">Ação</TableHead>
                </TableRow>
              </TableHeader>

              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={8} className="h-40 text-center text-slate-400">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <RefreshCwIcon className="size-6 animate-spin text-cyan-400" />
                        <span className="text-xs">Consultando dados no WebPosto...</span>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : caixas.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="h-32 text-center text-slate-400 text-sm">
                      Nenhum fechamento de caixa encontrado para o período e unidade selecionados.
                    </TableCell>
                  </TableRow>
                ) : modoVisualizacao === "consolidado" ? (
                  /* VISÃO CONSOLIDADA (SINTÉTICA POR DIA) */
                  diasConsolidados.map((dia) => {
                    const expandido = !!diasExpandidos[dia.data];
                    const temAlertaVermelho = dia.severidade === "vermelho";
                    const temAlertaLaranja = dia.severidade === "laranja";
                    const quebraNum = dia.quebraTotal;

                    const faltososDoDia = dia.caixas.flatMap((c) => {
                      const particsFalta = (c.funcionarios_participantes || []).filter(
                        (p) => Number(p.quebra_sobra || 0) < 0
                      );
                      if (particsFalta.length > 0) {
                        return particsFalta.map((p) => ({
                          codigo: p.codigo,
                          nome: p.nome,
                          responsavel: !!p.responsavel,
                          quebra_sobra: Number(p.quebra_sobra),
                          status_vale: p.status_vale || "pendente_sem_vale",
                          valor_vale_falta: Number(p.valor_vale_falta || 0),
                          caixa_codigo: c.caixa.codigo,
                          turno: c.caixa.turno,
                        }));
                      }
                      if (Number(c.quebra || 0) < 0) {
                        return [{
                          codigo: c.caixa.funcionario_codigo,
                          nome: funcionariosMap.get(c.caixa.funcionario_codigo) || `Operador #${c.caixa.funcionario_codigo}`,
                          responsavel: true,
                          quebra_sobra: Number(c.quebra),
                          status_vale: c.desconto_falta?.situacao === "descontado" ? "com_vale" : "pendente_sem_vale",
                          valor_vale_falta: Number(c.desconto_falta?.total_vale || 0),
                          caixa_codigo: c.caixa.codigo,
                          turno: c.caixa.turno,
                        }];
                      }
                      return [];
                    });

                    return (
                      <React.Fragment key={dia.data}>
                        <TableRow
                          className={`border-slate-800/60 transition-colors hover:bg-slate-800/40 cursor-pointer ${
                            temAlertaVermelho ? "bg-red-950/10" : ""
                          }`}
                          onClick={() => toggleExpansaoDia(dia.data)}
                        >
                          {/* Ícone de Expansão */}
                          <TableCell className="w-10 px-3 text-slate-500">
                            {expandido ? (
                              <ChevronUpIcon className="size-4 text-cyan-400" />
                            ) : (
                              <ChevronDownIcon className="size-4" />
                            )}
                          </TableCell>

                          {/* Status / Alerta Consolidado */}
                          <TableCell>
                            <div className="flex flex-col gap-1 items-start">
                              {temAlertaVermelho ? (
                                <Badge variant="destructive" className="bg-red-600 text-white text-[11px] gap-1 font-semibold shadow-sm">
                                  <AlertCircleIcon className="size-3" />
                                  <span>Falta s/ Vale no Dia</span>
                                </Badge>
                              ) : temAlertaLaranja ? (
                                <Badge variant="outline" className="border-amber-600 bg-amber-950/80 text-amber-300 text-[11px] gap-1 font-medium">
                                  <AlertTriangleIcon className="size-3" />
                                  <span>Divergência no Dia</span>
                                </Badge>
                              ) : (
                                <Badge variant="outline" className="border-emerald-600 bg-emerald-950/70 text-emerald-300 text-[11px] gap-1">
                                  <CheckCircle2Icon className="size-3" />
                                  <span>Dia Consolidado OK</span>
                                </Badge>
                              )}

                              {dia.alertasTotais.length > 0 && (
                                <span className="text-[10px] text-slate-400 font-medium">
                                  {dia.alertasTotais.length} alerta(s)
                                </span>
                              )}
                            </div>
                          </TableCell>

                          {/* Data Movimento */}
                          <TableCell>
                            <div className="text-sm font-bold text-white flex items-center gap-1.5">
                              <CalendarDaysIcon className="size-3.5 text-cyan-400" />
                              <span>{dia.data}</span>
                            </div>
                            <div className="text-xs text-slate-400">
                              {dia.totalCaixas} caixa(s) / turno(s) no dia
                            </div>
                          </TableCell>

                          {/* Consolidação: PDVs & Operadores */}
                          <TableCell>
                            <div className="text-sm text-slate-200 font-medium">
                              {dia.funcionarios.length} operador(es) no dia
                            </div>
                            <div className="text-xs text-slate-400">
                              PDV(s): {dia.pdvs.join(", ")} {dia.turnos.length > 0 ? `· ${dia.turnos.join(", ")}` : ""}
                            </div>

                            {/* Apontamento Direto de Faltas no Dia */}
                            {faltososDoDia.length > 0 && (
                              <div className="mt-2 rounded-lg border border-red-500/80 bg-red-950/80 p-2 shadow-sm">
                                <div className="flex items-center gap-1.5 text-[11px] font-bold text-red-300 uppercase tracking-wide">
                                  <AlertCircleIcon className="size-3.5 text-red-400 shrink-0" />
                                  <span>Faltas Registradas no Dia ({faltososDoDia.length}):</span>
                                </div>
                                <div className="mt-1 space-y-1">
                                  {faltososDoDia.map((op, oIdx) => {
                                    const temVale = op.status_vale === "com_vale" || op.valor_vale_falta > 0;
                                    return (
                                      <div
                                        key={oIdx}
                                        className="flex flex-wrap items-center justify-between gap-1.5 py-1 px-2 rounded bg-black/60 border border-red-900/60 text-xs"
                                      >
                                        <div className="flex items-center gap-1.5 text-white">
                                          <span className="font-semibold text-red-200">{op.nome}</span>
                                          <span className="text-[10px] text-slate-400 font-mono">#{op.codigo}</span>
                                          <span className="text-[10px] text-slate-400">({op.turno})</span>
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                          <span className="font-mono font-bold text-red-400 text-xs">
                                            {fmtBRL(op.quebra_sobra)}
                                          </span>
                                          {temVale ? (
                                            <Badge className="bg-emerald-950 text-emerald-300 border border-emerald-700 text-[9px] py-0 px-1 gap-1">
                                              <CheckCircle2Icon className="size-2.5" />
                                              <span>Vale OK ({fmtBRL(op.valor_vale_falta || Math.abs(op.quebra_sobra))})</span>
                                            </Badge>
                                          ) : (
                                            <Badge variant="destructive" className="bg-red-600 text-white font-bold text-[9px] py-0 px-1 shadow animate-pulse">
                                              PENDENTE S/ VALE
                                            </Badge>
                                          )}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                          </TableCell>

                          {/* Esperado Total */}
                          <TableCell className="text-right">
                            <div className="text-sm font-semibold text-slate-200">
                              {fmtBRL(dia.apuradoTotal)}
                            </div>
                            <div className="text-[11px] text-slate-400">apurado total</div>
                          </TableCell>

                          {/* Declarado Total */}
                          <TableCell className="text-right">
                            <div className="text-sm font-semibold text-slate-200">
                              {fmtBRL(dia.declaradoTotal)}
                            </div>
                            <div className="text-[11px] text-slate-400">informado total</div>
                          </TableCell>

                          {/* Quebra Líquida */}
                          <TableCell className="text-right">
                            <div
                              className={`text-sm font-bold ${
                                quebraNum < 0 ? "text-red-400" : quebraNum > 0 ? "text-emerald-400" : "text-slate-300"
                              }`}
                            >
                              {fmtBRL(quebraNum)}
                            </div>
                            <div className="text-[11px] text-slate-400">quebra líquida</div>
                          </TableCell>

                          {/* Ação */}
                          <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => toggleExpansaoDia(dia.data)}
                              className="h-8 text-xs text-cyan-400 hover:text-cyan-300 hover:bg-cyan-950/40"
                            >
                              {expandido ? "Ocultar" : "Detalhar"}
                            </Button>
                          </TableCell>
                        </TableRow>

                        {/* Accordion Consolidado: Tabela por Modalidade e Detalhes do Dia */}
                        {expandido && (
                          <TableRow className="bg-slate-950/70 border-b border-slate-800">
                            <TableCell colSpan={8} className="p-4 sm:p-6">
                              <div className="space-y-5 rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 sm:p-5">
                                {/* Cabeçalho da Expansão */}
                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                                  <div>
                                    <h4 className="text-sm font-bold text-white flex items-center gap-2">
                                      <LayersIcon className="size-4 text-cyan-400" />
                                      Consolidação das Espécies e Caixas de {dia.data}
                                    </h4>
                                    <p className="text-xs text-slate-400">
                                      Total de {dia.totalCaixas} turno(s) auditados de forma unificada.
                                    </p>
                                  </div>
                                  <div className="text-xs text-slate-300 font-mono bg-slate-800/80 px-2.5 py-1 rounded border border-slate-700">
                                    Quebra do Dia:{" "}
                                    <span className={quebraNum < 0 ? "text-red-400 font-bold" : "text-emerald-400 font-bold"}>
                                      {fmtBRL(quebraNum)}
                                    </span>
                                  </div>
                                </div>

                                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                                  {/* Modalidades Consolidadas */}
                                  <div className="space-y-2">
                                    <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                      <WalletIcon className="size-4 text-cyan-400" />
                                      Totais Consolidados por Espécie / Forma
                                    </h5>
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                      <table className="w-full text-xs">
                                        <thead className="bg-slate-950 text-slate-400">
                                          <tr>
                                            <th className="p-2 text-left">Modalidade</th>
                                            <th className="p-2 text-right">Informado</th>
                                            <th className="p-2 text-right">Apurado</th>
                                            <th className="p-2 text-right">Diferença</th>
                                          </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-800/60 bg-slate-900/50">
                                          {dia.modalidadesConsolidadas.map((m) => (
                                            <tr key={m.modalidade} className="hover:bg-slate-800/30">
                                              <td className="p-2 font-medium text-slate-300">{m.rotulo}</td>
                                              <td className="p-2 text-right text-slate-300">{fmtBRL(m.apresentado)}</td>
                                              <td className="p-2 text-right text-slate-300">{fmtBRL(m.apurado)}</td>
                                              <td
                                                className={`p-2 text-right font-medium ${
                                                  m.diferenca < 0
                                                    ? "text-red-400"
                                                    : m.diferenca > 0
                                                    ? "text-emerald-400"
                                                    : "text-slate-400"
                                                }`}
                                              >
                                                {fmtBRL(m.diferenca)}
                                              </td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  </div>

                                  {/* Caixas Individuais que compõem o dia */}
                                  <div className="space-y-2">
                                    <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                      <ClockIcon className="size-4 text-cyan-400" />
                                      Turnos Individuais Deste Dia ({dia.caixas.length})
                                    </h5>
                                    <div className="space-y-2">
                                      {dia.caixas.map((cxItem) => {
                                        const opNome =
                                          funcionariosMap.get(cxItem.caixa.funcionario_codigo) ||
                                          `Operador #${cxItem.caixa.funcionario_codigo}`;
                                        const ccNome =
                                          centrosCustoMap.get(cxItem.caixa.centro_custo || 0) ||
                                          (cxItem.caixa.centro_custo ? `CC ${cxItem.caixa.centro_custo}` : "");
                                        const qk = Number(cxItem.quebra || 0);

                                        return (
                                          <div
                                            key={cxItem.caixa.codigo}
                                            className="flex items-center justify-between p-2.5 rounded-lg border border-slate-800 bg-slate-950/40 text-xs"
                                          >
                                            <div>
                                              <div className="font-medium text-slate-200">
                                                {opNome} · {cxItem.caixa.turno || "Turno Único"}
                                              </div>
                                              <div className="text-[11px] text-slate-400">
                                                PDV {cxItem.caixa.pdv_codigo} {ccNome ? `· ${ccNome}` : ""}
                                              </div>
                                            </div>
                                            <div className="text-right">
                                              <div className="text-slate-300">
                                                {fmtBRL(Number(cxItem.caixa.apurado || 0))}
                                              </div>
                                              <div
                                                className={`font-mono font-medium ${
                                                  qk < 0 ? "text-red-400" : qk > 0 ? "text-emerald-400" : "text-slate-400"
                                                }`}
                                              >
                                                {fmtBRL(qk)}
                                              </div>
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                </div>

                                {/* Despesas Consolidadas se houver */}
                                {dia.despesasTotais.length > 0 && (
                                  <div className="space-y-2 pt-2 border-t border-slate-800/60">
                                    <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                      <FuelIcon className="size-4 text-amber-400" />
                                      Despesas de Pista Consolidadas ({dia.despesasTotais.length})
                                    </h5>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                      {dia.despesasTotais.map((desp, dIdx) => (
                                        <div
                                          key={dIdx}
                                          className="flex items-center justify-between p-2 rounded border border-slate-800 bg-slate-950/40 text-xs"
                                        >
                                          <span className="text-slate-300">
                                            {desp.descricao || desp.plano_conta_nome || "Despesa Operacional"}
                                          </span>
                                          <span className="font-mono text-amber-300 font-semibold">
                                            {fmtBRL(Number(desp.valor))}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        )}
                      </React.Fragment>
                    );
                  })
                ) : (
                  caixas.map((item) => {
                    const cx = item.caixa;
                    const quebraNum = Number(item.quebra || 0);
                    const expandido = !!caixasExpandidos[cx.codigo];

                    // Saldo esperado total vs declarado total
                    const declaradoTotal = item.modalidades.reduce(
                      (acc, m) => acc + Number(m.apresentado || 0),
                      0,
                    );
                    const esperadoTotal = item.modalidades.reduce(
                      (acc, m) => acc + Number(m.apurado || 0),
                      0,
                    );

                    // Alertas
                    const temAlertaVermelho = item.severidade === "vermelho";
                    const temAlertaLaranja = item.severidade === "laranja";

                    const particsFalta = (item.funcionarios_participantes || []).filter(
                      (p) => Number(p.quebra_sobra || 0) < 0
                    );
                    const faltososCx = particsFalta.length > 0
                      ? particsFalta
                      : quebraNum < 0
                        ? [{
                            codigo: cx.funcionario_codigo,
                            nome: funcionariosMap.get(cx.funcionario_codigo) || `Operador #${cx.funcionario_codigo}`,
                            responsavel: true,
                            quebra_sobra: quebraNum,
                            status_vale: item.desconto_falta?.situacao === "descontado" ? "com_vale" : "pendente_sem_vale",
                            valor_vale_falta: item.desconto_falta?.total_vale || 0,
                          }]
                        : [];

                    return (
                      <React.Fragment key={cx.codigo}>
                        <TableRow
                          className={`border-slate-800/60 transition-colors hover:bg-slate-800/40 cursor-pointer ${
                            temAlertaVermelho ? "bg-red-950/10" : ""
                          }`}
                          onClick={() => toggleExpansaoCaixa(cx.codigo)}
                        >
                          {/* Ícone de Expansão */}
                          <TableCell className="w-10 px-3 text-slate-500">
                            {expandido ? (
                              <ChevronUpIcon className="size-4 text-cyan-400" />
                            ) : (
                              <ChevronDownIcon className="size-4" />
                            )}
                          </TableCell>

                          {/* Status / Badge */}
                          <TableCell>
                            <div className="flex flex-col gap-1 items-start">
                              {!cx.fechado ? (
                                <Badge variant="outline" className="border-blue-700 bg-blue-950/80 text-blue-300 text-[11px] gap-1">
                                  <ClockIcon className="size-3" />
                                  <span>Caixa Aberto</span>
                                </Badge>
                              ) : temAlertaVermelho ? (
                                <Badge variant="destructive" className="bg-red-600 text-white text-[11px] gap-1 font-semibold shadow-sm">
                                  <AlertCircleIcon className="size-3" />
                                  <span>Falta &gt; R$ 10 s/ Vale</span>
                                </Badge>
                              ) : temAlertaLaranja ? (
                                <Badge variant="outline" className="border-amber-600 bg-amber-950/80 text-amber-300 text-[11px] gap-1 font-medium">
                                  <AlertTriangleIcon className="size-3" />
                                  <span>Divergência / Despesa</span>
                                </Badge>
                              ) : (
                                <Badge variant="outline" className="border-emerald-600 bg-emerald-950/70 text-emerald-300 text-[11px] gap-1">
                                  <CheckCircle2Icon className="size-3" />
                                  <span>100% Conforme</span>
                                </Badge>
                              )}

                              {item.alertas.length > 0 && (
                                <span className="text-[10px] text-slate-400 font-medium">
                                  {item.alertas.length} alerta(s)
                                </span>
                              )}
                            </div>
                          </TableCell>

                          {/* Data / Turno */}
                          <TableCell>
                            <div className="text-sm font-medium text-white">{cx.data}</div>
                            <div className="text-xs text-slate-400">
                              Turno {cx.turno || "Único"} · Abertura: {cx.abertura ? cx.abertura.slice(11, 16) : "--:--"}
                            </div>
                          </TableCell>

                          {/* Operador / PDV */}
                          <TableCell>
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span
                                className="text-sm text-slate-200 font-medium truncate max-w-[190px]"
                                title={funcionariosMap.get(cx.funcionario_codigo) || `Operador #${cx.funcionario_codigo}`}
                              >
                                {funcionariosMap.get(cx.funcionario_codigo) || `Operador #${cx.funcionario_codigo}`}
                              </span>
                              {item.funcionarios_participantes && item.funcionarios_participantes.length > 1 && (
                                <Badge
                                  variant="outline"
                                  className="text-[10px] py-0 px-1.5 border-cyan-800 bg-cyan-950/70 text-cyan-300 font-mono font-medium"
                                  title={`${item.funcionarios_participantes.length} operadores participaram da prestação de contas deste turno`}
                                >
                                  +{item.funcionarios_participantes.length - 1} op.
                                </Badge>
                              )}
                            </div>
                            <div className="text-xs text-slate-400 flex items-center gap-1 mt-0.5">
                              <span className="text-[11px] text-slate-500 font-mono">Resp: #{cx.funcionario_codigo}</span>
                              <span>·</span>
                              <span>PDV {cx.pdv_codigo}</span>
                              {cx.centro_custo && (
                                <>
                                  <span>·</span>
                                  <span>{centrosCustoMap.get(cx.centro_custo) || `CC ${cx.centro_custo}`}</span>
                                </>
                              )}
                            </div>

                            {/* Apontamento Direto do(s) Frentista(s) Faltoso(s) */}
                            {faltososCx.length > 0 && (
                              <div className="mt-2 rounded-lg border border-red-500/80 bg-red-950/80 p-2 shadow-sm">
                                <div className="flex items-center gap-1.5 text-[11px] font-bold text-red-300 uppercase tracking-wide">
                                  <AlertCircleIcon className="size-3.5 text-red-400 shrink-0" />
                                  <span>Responsável(eis) pela Falta no Turno:</span>
                                </div>
                                <div className="mt-1 space-y-1">
                                  {faltososCx.map((op, oIdx) => {
                                    const temVale = op.status_vale === "com_vale" || Number(op.valor_vale_falta || 0) > 0;
                                    return (
                                      <div
                                        key={oIdx}
                                        className="flex flex-wrap items-center justify-between gap-1.5 py-1 px-2 rounded bg-black/60 border border-red-900/60 text-xs"
                                      >
                                        <div className="flex items-center gap-1.5 font-medium text-white">
                                          <span className="font-semibold text-red-200">{op.nome}</span>
                                          <span className="font-mono text-[10px] text-slate-400">#{op.codigo}</span>
                                          {op.responsavel && (
                                            <Badge variant="outline" className="text-[9px] py-0 px-1 border-amber-600 bg-amber-950 text-amber-300">
                                              Resp.
                                            </Badge>
                                          )}
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                          <span className="font-mono font-bold text-red-400 text-xs">
                                            {fmtBRL(Number(op.quebra_sobra))}
                                          </span>
                                          {temVale ? (
                                            <Badge className="bg-emerald-950 text-emerald-300 border border-emerald-700 text-[9px] py-0 px-1 gap-1">
                                              <CheckCircle2Icon className="size-2.5" />
                                              <span>Vale OK ({fmtBRL(Number(op.valor_vale_falta || Math.abs(Number(op.quebra_sobra))))})</span>
                                            </Badge>
                                          ) : (
                                            <Badge variant="destructive" className="bg-red-600 text-white font-bold text-[9px] py-0 px-1 shadow animate-pulse">
                                              PENDENTE S/ VALE
                                            </Badge>
                                          )}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                          </TableCell>

                          {/* Esperado */}
                          <TableCell className="text-right">
                            <div className="text-sm font-medium text-slate-200">
                              {fmtBRL(esperadoTotal || Number(cx.apurado || 0))}
                            </div>
                            <div className="text-[11px] text-slate-400">apurado</div>
                          </TableCell>

                          {/* Declarado */}
                          <TableCell className="text-right">
                            <div className="text-sm font-medium text-slate-200">
                              {fmtBRL(declaradoTotal)}
                            </div>
                            <div className="text-[11px] text-slate-400">informado</div>
                          </TableCell>

                          {/* Quebra / Sobra */}
                          <TableCell className="text-right">
                            <div
                              className={`text-sm font-bold ${
                                quebraNum < 0 ? "text-red-400" : quebraNum > 0 ? "text-emerald-400" : "text-slate-300"
                              }`}
                            >
                              {fmtBRL(quebraNum)}
                            </div>
                            <div className="text-[11px] text-slate-400">
                              {quebraNum < 0 ? "falta líquida" : quebraNum > 0 ? "sobra" : "exato"}
                            </div>
                            {faltososCx.length > 0 && (
                              <Badge variant="destructive" className="mt-1 text-[10px] py-0 px-1.5 bg-red-900/90 border-red-700 text-red-200 font-normal">
                                {faltososCx.length === 1 ? `${faltososCx[0].nome.split(" ")[0]} faltoso` : `${faltososCx.length} faltosos`}
                              </Badge>
                            )}
                          </TableCell>

                          {/* Ação */}
                          <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => toggleExpansaoCaixa(cx.codigo)}
                              className="h-8 text-xs text-cyan-400 hover:text-cyan-300 hover:bg-cyan-950/40"
                            >
                              {expandido ? "Ocultar" : "Detalhar"}
                            </Button>
                          </TableCell>
                        </TableRow>

                        {/* Linha Expandida: Modalidades e Despesas */}
                        {expandido && (
                          <TableRow className="bg-slate-950/70 border-b border-slate-800">
                            <TableCell colSpan={8} className="p-4 sm:p-6">
                              <div className="space-y-5 rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 sm:p-5">
                                {/* Alertas Críticos do Caixa */}
                                {item.alertas.length > 0 && (
                                  <div className="space-y-2">
                                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                      <ShieldAlertIcon className="size-4 text-amber-400" />
                                      Alertas Operacionais deste Turno
                                    </h4>
                                    <div className="grid grid-cols-1 gap-2">
                                      {item.alertas.map((alerta, idx) => (
                                        <div
                                          key={idx}
                                          className={`flex items-start gap-2.5 rounded-lg p-2.5 text-xs ${
                                            alerta.severidade === "vermelho"
                                              ? "border border-red-900/60 bg-red-950/40 text-red-300"
                                              : "border border-amber-900/60 bg-amber-950/40 text-amber-300"
                                          }`}
                                        >
                                          <AlertTriangleIcon className="size-4 shrink-0 mt-0.5" />
                                          <div className="flex-1">
                                            <span className="font-semibold uppercase tracking-wider mr-2 text-[10px] rounded px-1.5 py-0.5 bg-black/40">
                                              {alerta.codigo}
                                            </span>
                                            <span>{alerta.mensagem}</span>
                                            {alerta.valor && (
                                              <span className="ml-2 font-mono font-bold">
                                                (Valor: {fmtBRL(Number(alerta.valor))})
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Prestação de Contas por Frentista / Operador */}
                                <div className="space-y-2.5">
                                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 border-b border-slate-800 pb-2">
                                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                                      <UsersIcon className="size-4 text-cyan-400" />
                                      Prestação de Contas por Frentista / Operador ({item.funcionarios_participantes?.length || 1})
                                    </h4>
                                    <span className="text-[11px] text-slate-400">
                                      Rateio e apuração individual por operador com vendas e quebras neste caixa
                                    </span>
                                  </div>

                                  <div className="rounded-lg border border-slate-800 overflow-hidden shadow-sm">
                                    <table className="w-full text-xs">
                                      <thead className="bg-slate-950 text-slate-400 font-medium">
                                        <tr className="border-b border-slate-800">
                                          <th className="p-2.5 text-left">Frentista / Operador</th>
                                          <th className="p-2.5 text-left">Função</th>
                                          <th className="p-2.5 text-right">Valor Apurado</th>
                                          <th className="p-2.5 text-right">Valor Declarado</th>
                                          <th className="p-2.5 text-right">Quebra / Sobra</th>
                                          <th className="p-2.5 text-right">Vales Associados</th>
                                          <th className="p-2.5 text-center">Status</th>
                                        </tr>
                                      </thead>
                                      <tbody className="divide-y divide-slate-800/60 bg-slate-900/60">
                                        {/* Linha 1: TODOS (Consolidado do Turno) */}
                                        <tr className="bg-cyan-950/20 font-semibold border-b border-cyan-900/30">
                                          <td className="p-2.5 text-cyan-300 flex items-center gap-1.5">
                                            <LayersIcon className="size-3.5 text-cyan-400" />
                                            <span>TODOS (Consolidado do Turno)</span>
                                          </td>
                                          <td className="p-2.5 text-slate-400 font-normal">Turno Completo</td>
                                          <td className="p-2.5 text-right text-slate-200">
                                            {fmtBRL(esperadoTotal || Number(cx.apurado || 0))}
                                          </td>
                                          <td className="p-2.5 text-right text-slate-200">
                                            {fmtBRL(declaradoTotal)}
                                          </td>
                                          <td
                                            className={`p-2.5 text-right font-bold ${
                                              quebraNum < 0 ? "text-red-400" : quebraNum > 0 ? "text-emerald-400" : "text-slate-300"
                                            }`}
                                          >
                                            {fmtBRL(quebraNum)}
                                          </td>
                                          <td className="p-2.5 text-right text-amber-300 font-mono">
                                            {fmtBRL(
                                              (item.funcionarios_participantes || []).reduce(
                                                (acc, p) => acc + Number(p.vales_associados || 0),
                                                0
                                              )
                                            )}
                                          </td>
                                          <td className="p-2.5 text-center">
                                            {quebraNum < -10 ? (
                                              <Badge variant="destructive" className="bg-red-600/90 text-white text-[10px] py-0 px-1.5">
                                                Quebra Geral
                                              </Badge>
                                            ) : quebraNum === 0 ? (
                                              <Badge variant="outline" className="border-emerald-600 bg-emerald-950/60 text-emerald-300 text-[10px] py-0 px-1.5">
                                                Batido
                                              </Badge>
                                            ) : (
                                              <Badge variant="outline" className="border-slate-700 bg-slate-800 text-slate-300 text-[10px] py-0 px-1.5">
                                                Conferido
                                              </Badge>
                                            )}
                                          </td>
                                        </tr>

                                        {/* Linhas individuais de cada frentista participante */}
                                        {(item.funcionarios_participantes && item.funcionarios_participantes.length > 0
                                          ? item.funcionarios_participantes
                                          : [
                                              {
                                                codigo: cx.funcionario_codigo,
                                                nome: funcionariosMap.get(cx.funcionario_codigo) || `Operador #${cx.funcionario_codigo}`,
                                                funcao: "Responsável do Turno",
                                                responsavel: true,
                                                valor_apurado: esperadoTotal || Number(cx.apurado || 0),
                                                valor_declarado: declaradoTotal,
                                                quebra_sobra: quebraNum,
                                                vales_associados: 0,
                                                alertas: [],
                                              },
                                            ]
                                        ).map((frentista, fIdx) => {
                                          const qkFrentista = Number(frentista.quebra_sobra || 0);
                                          const valeFrentista = Number(frentista.vales_associados || 0);

                                          return (
                                            <tr key={fIdx} className="hover:bg-slate-800/40 transition-colors">
                                              <td className="p-2.5">
                                                <div className="font-medium text-slate-200 flex items-center gap-1.5">
                                                  <span>{frentista.nome}</span>
                                                  {frentista.responsavel && (
                                                    <Badge variant="outline" className="text-[9px] py-0 px-1 border-cyan-700 bg-cyan-950/80 text-cyan-300">
                                                      Responsável
                                                    </Badge>
                                                  )}
                                                </div>
                                                <div className="text-[10px] text-slate-400 font-mono">
                                                  Cód: #{frentista.codigo}
                                                </div>
                                              </td>
                                              <td className="p-2.5 text-slate-400">
                                                {frentista.funcao || (frentista.responsavel ? "Responsável" : "Frentista")}
                                              </td>
                                              <td className="p-2.5 text-right font-medium text-slate-300">
                                                {fmtBRL(Number(frentista.valor_apurado || 0))}
                                              </td>
                                              <td className="p-2.5 text-right font-medium text-slate-300">
                                                {fmtBRL(Number(frentista.valor_declarado || 0))}
                                              </td>
                                              <td
                                                className={`p-2.5 text-right font-bold ${
                                                  qkFrentista < 0
                                                    ? "text-red-400"
                                                    : qkFrentista > 0
                                                    ? "text-emerald-400"
                                                    : "text-slate-400"
                                                }`}
                                              >
                                                {fmtBRL(qkFrentista)}
                                              </td>
                                              <td className="p-2.5 text-right font-mono text-amber-300">
                                                {valeFrentista > 0 ? fmtBRL(valeFrentista) : "—"}
                                              </td>
                                              <td className="p-2.5 text-center">
                                                {qkFrentista < -10 ? (
                                                  <Badge variant="destructive" className="bg-red-600/90 text-white text-[10px] py-0 px-1.5 font-medium">
                                                    Falta ({fmtBRL(qkFrentista)})
                                                  </Badge>
                                                ) : qkFrentista < 0 ? (
                                                  <Badge variant="outline" className="border-amber-600 bg-amber-950/60 text-amber-300 text-[10px] py-0 px-1.5">
                                                    Falta ({fmtBRL(qkFrentista)})
                                                  </Badge>
                                                ) : qkFrentista > 0 ? (
                                                  <Badge variant="outline" className="border-cyan-600 bg-cyan-950/60 text-cyan-300 text-[10px] py-0 px-1.5">
                                                    Sobra (+{fmtBRL(qkFrentista)})
                                                  </Badge>
                                                ) : (
                                                  <Badge variant="outline" className="border-emerald-600 bg-emerald-950/60 text-emerald-300 text-[10px] py-0 px-1.5">
                                                    Batido
                                                  </Badge>
                                                )}
                                              </td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>

                                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                                  {/* Sub-tabela: Modalidades de Pagamento */}
                                  <div className="space-y-2">
                                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                      <WalletIcon className="size-4 text-cyan-400" />
                                      Conferência por Espécie / Forma
                                    </h4>
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                      <table className="w-full text-xs">
                                        <thead className="bg-slate-950 text-slate-400">
                                          <tr>
                                            <th className="p-2 text-left">Modalidade</th>
                                            <th className="p-2 text-right">Apresentado</th>
                                            <th className="p-2 text-right">Apurado</th>
                                            <th className="p-2 text-right">Diferença</th>
                                          </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-800/60">
                                          {item.modalidades.map((mod, mIdx) => {
                                            const diff = Number(mod.diferenca || 0);
                                            return (
                                              <tr key={mIdx} className="hover:bg-slate-800/30">
                                                <td className="p-2 text-slate-200 font-medium">{mod.rotulo}</td>
                                                <td className="p-2 text-right text-slate-300">{fmtBRL(Number(mod.apresentado))}</td>
                                                <td className="p-2 text-right text-slate-300">{fmtBRL(Number(mod.apurado))}</td>
                                                <td className={`p-2 text-right font-semibold ${diff < 0 ? "text-red-400" : diff > 0 ? "text-emerald-400" : "text-slate-400"}`}>
                                                  {fmtBRL(diff)}
                                                </td>
                                              </tr>
                                            );
                                          })}
                                        </tbody>
                                      </table>
                                    </div>
                                  </div>

                                  {/* Sub-tabela: Despesas de Pista */}
                                  <div className="space-y-2">
                                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                      <ReceiptIcon className="size-4 text-emerald-400" />
                                      Despesas Operacionais do Caixa
                                    </h4>
                                    {!item.despesas || item.despesas.length === 0 ? (
                                      <div className="rounded-lg border border-slate-800 p-4 text-center text-xs text-slate-400">
                                        Nenhuma despesa de pista registrada para este turno.
                                      </div>
                                    ) : (
                                      <div className="rounded-lg border border-slate-800 overflow-hidden">
                                        <table className="w-full text-xs">
                                          <thead className="bg-slate-950 text-slate-400">
                                            <tr>
                                              <th className="p-2 text-left">Descrição / Plano</th>
                                              <th className="p-2 text-center">Tipo</th>
                                              <th className="p-2 text-right">Valor</th>
                                            </tr>
                                          </thead>
                                          <tbody className="divide-y divide-slate-800/60">
                                            {item.despesas.map((desp, dIdx) => (
                                              <tr key={dIdx} className="hover:bg-slate-800/30">
                                                <td className="p-2 text-slate-200">
                                                  <div className="font-medium">{desp.descricao || "Sem descrição"}</div>
                                                  <div className="text-[10px] text-slate-400">
                                                    Plano: {desp.plano_conta_nome || desp.plano_conta_codigo || "Não vinculado"}
                                                  </div>
                                                </td>
                                                <td className="p-2 text-center">
                                                  <Badge variant="outline" className="text-[10px] border-slate-700 bg-slate-800 text-slate-300">
                                                    {desp.tipo}
                                                  </Badge>
                                                </td>
                                                <td className="p-2 text-right font-medium text-amber-300">
                                                  {fmtBRL(Number(desp.valor))}
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </TableCell>
                          </TableRow>
                        )}
                      </React.Fragment>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Sheet Lateral com o Relatório Executivo Markdown */}
      <Sheet open={sheetRelatorioAberto} onOpenChange={setSheetRelatorioAberto}>
        <SheetContent className="w-full sm:max-w-xl md:max-w-2xl bg-slate-950 border-slate-800 text-white overflow-y-auto">
          <SheetHeader className="pb-4 border-b border-slate-800">
            <div className="flex items-center justify-between">
              <SheetTitle className="text-lg font-bold text-white flex items-center gap-2">
                <FileTextIcon className="size-5 text-cyan-400" />
                Relatório Executivo de Caixa
              </SheetTitle>
              <Button
                variant="outline"
                size="sm"
                onClick={copiarMarkdown}
                disabled={relatorioCarregando}
                className="border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700 gap-1.5 text-xs"
              >
                <CopyIcon className="size-3.5" />
                <span>{copiadoFeedback ? "Copiado!" : "Copiar"}</span>
              </Button>
            </div>
            <SheetDescription className="text-xs text-slate-400">
              Resumo gerado pelo robô de auditoria para {dataFim}.
            </SheetDescription>
          </SheetHeader>

          <div className="py-4">
            {relatorioCarregando ? (
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-slate-400 text-xs">
                <RefreshCwIcon className="size-6 animate-spin text-cyan-400" />
                <span>Carregando relatório markdown...</span>
              </div>
            ) : (
              <div className="rounded-xl border border-slate-800/80 bg-slate-900/90 p-4 font-mono text-xs text-slate-200 whitespace-pre-wrap leading-relaxed shadow-inner">
                {relatorioMarkdown}
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
