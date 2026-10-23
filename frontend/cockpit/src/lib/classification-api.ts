import type {
  HistoricoEvento,
  ItemFilaRevisao,
  MetricasRevisaoIA,
  PlanoContaFolha,
} from "@/types/classification";

const API_BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8050"
    : "";

export async function fetchPendencias(
  status?: string,
  empresaCodigo?: number,
): Promise<ItemFilaRevisao[]> {
  const params = new URLSearchParams();
  if (status && status !== "TODOS") params.set("status", status);
  if (empresaCodigo) params.set("empresa_codigo", String(empresaCodigo));

  const res = await fetch(`${API_BASE}/api/v1/classification-review/pendencias?${params}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Falha ao buscar pendências (${res.status})`);
  }
  const data = await res.json();
  return data.itens ?? [];
}

export async function fetchDetalhesPendencia(id: number): Promise<ItemFilaRevisao> {
  const res = await fetch(`${API_BASE}/api/v1/classification-review/pendencias/${id}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Falha ao buscar detalhes da pendência (${res.status})`);
  }
  return res.json();
}

export async function fetchHistoricoPendencia(id: number): Promise<HistoricoEvento[]> {
  const res = await fetch(`${API_BASE}/api/v1/classification-review/pendencias/${id}/historico`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Falha ao buscar histórico (${res.status})`);
  }
  const data = await res.json();
  return data.eventos ?? [];
}

export async function classificarPendencia(
  id: number,
  payload: {
    versao: number;
    plano_definitivo_codigo: number;
    plano_definitivo_descricao?: string;
    centro_custo_definitivo_codigo?: number;
    justificativa?: string;
  },
): Promise<{ status: string; item: ItemFilaRevisao }> {
  const res = await fetch(`${API_BASE}/api/v1/classification-review/pendencias/${id}/classificar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Falha ao classificar pendência (${res.status})`);
  }
  return res.json();
}

export async function bloquearPendencia(
  id: number,
  payload: {
    versao: number;
    motivo: string;
    travas?: string[];
  },
): Promise<{ status: string; item: ItemFilaRevisao }> {
  const res = await fetch(`${API_BASE}/api/v1/classification-review/pendencias/${id}/bloquear`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Falha ao bloquear pendência (${res.status})`);
  }
  return res.json();
}

export async function cancelarPendencia(
  id: number,
  payload: {
    versao: number;
    motivo: string;
  },
): Promise<{ status: string; item: ItemFilaRevisao }> {
  const res = await fetch(`${API_BASE}/api/v1/classification-review/pendencias/${id}/cancelar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Falha ao cancelar pendência (${res.status})`);
  }
  return res.json();
}

export async function fetchPlanosValidos(): Promise<PlanoContaFolha[]> {
  const res = await fetch(`${API_BASE}/api/v1/classification-review/planos-validos`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Falha ao obter planos folha válidos (${res.status})`);
  }
  const data = await res.json();
  return data.planos ?? [];
}

export async function fetchMetricasRevisao(): Promise<MetricasRevisaoIA> {
  const res = await fetch(`${API_BASE}/api/v1/classification-review/metricas`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Falha ao obter métricas da fila (${res.status})`);
  }
  return res.json();
}
