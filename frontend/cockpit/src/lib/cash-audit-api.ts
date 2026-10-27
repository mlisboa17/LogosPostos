import type {
  FechamentoFiltrosParams,
  FiltrosOperacionaisResponse,
  PendenciaCaixa,
  RelatorioCaixaResponse,
  ResultadoAuditoriaFechamento,
} from "@/types/cash-audit";

const API_BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8040"
    : "";

function getAuthHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token") || localStorage.getItem("access_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }
  return headers;
}

export async function fetchFiltrosOperacionais(
  unidade: number,
): Promise<FiltrosOperacionaisResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/cash-audit/filtros-operacionais?unidade=${unidade}`,
    {
      cache: "default",
      credentials: "include",
      headers: getAuthHeaders(),
    },
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Falha ao carregar filtros operacionais (${res.status})`);
  }

  return res.json();
}

export async function fetchFechamentoCaixa(
  unidade: number,
  inicio: string,
  fim: string,
  filtros?: FechamentoFiltrosParams,
): Promise<ResultadoAuditoriaFechamento> {
  const params = new URLSearchParams({
    unidade: String(unidade),
    inicio,
    fim,
  });

  if (filtros?.centro_custo) {
    params.set("centro_custo", String(filtros.centro_custo));
  }
  if (filtros?.turno && filtros.turno !== "todos") {
    params.set("turno", filtros.turno);
  }
  if (filtros?.funcionario_codigo) {
    params.set("funcionario_codigo", String(filtros.funcionario_codigo));
  }
  if (filtros?.pdv_codigo) {
    params.set("pdv_codigo", String(filtros.pdv_codigo));
  }
  if (filtros?.tipo_data) {
    params.set("tipo_data", filtros.tipo_data);
  }
  if (filtros?.consolidado) {
    params.set("consolidado", "true");
  }

  const res = await fetch(`${API_BASE}/api/v1/cash-audit/fechamento?${params}`, {
    cache: "no-store",
    credentials: "include",
    headers: getAuthHeaders(),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Falha ao consultar fechamento de caixa (${res.status})`);
  }

  return res.json();
}

export async function fetchRelatorioCaixa(
  dia: string,
  unidade?: number,
  gravado: boolean = false,
): Promise<RelatorioCaixaResponse> {
  const params = new URLSearchParams({ dia });
  if (unidade) params.set("unidade", String(unidade));
  if (gravado) params.set("gravado", "true");

  const res = await fetch(`${API_BASE}/api/v1/cash-audit/relatorio-caixa?${params}`, {
    cache: "no-store",
    credentials: "include",
    headers: getAuthHeaders(),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Falha ao obter relatório executivo de caixa (${res.status})`);
  }

  return res.json();
}

export async function fetchPendenciasCaixa(
  unidade?: number,
  status: string = "aberta",
): Promise<PendenciaCaixa[]> {
  const params = new URLSearchParams();
  if (status && status !== "todas") params.set("status", status);
  if (unidade) params.set("unidade", String(unidade));

  const res = await fetch(`${API_BASE}/api/v1/cash-audit/pendencias?${params}`, {
    cache: "no-store",
    credentials: "include",
    headers: getAuthHeaders(),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Falha ao obter pendências (${res.status})`);
  }

  return res.json();
}
