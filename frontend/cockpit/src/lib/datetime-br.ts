/** Fuso do posto — Recife/PE (UTC-3, sem horário de verão). */
export const APP_TIMEZONE = "America/Recife";

/** YYYY-MM-DD no fuso de Recife */
export function formatDateBR(d: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: APP_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

export function todayRecife(): string {
  return formatDateBR(new Date());
}

export function nowRecifeLabel(): string {
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: APP_TIMEZONE,
    dateStyle: "full",
    timeStyle: "medium",
  }).format(new Date());
}

function addDaysFromIso(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, (m ?? 1) - 1, (d ?? 1) + delta));
  return formatDateBR(dt);
}

export function presetRange(
  id: "hoje" | "ontem" | "7d" | "15d" | "30d" | "mes"
): { inicio: string; fim: string } {
  const fim = todayRecife();
  if (id === "hoje") return { inicio: fim, fim };
  if (id === "ontem") {
    const s = addDaysFromIso(fim, -1);
    return { inicio: s, fim: s };
  }
  if (id === "15d") return { inicio: addDaysFromIso(fim, -14), fim };
  if (id === "30d") return { inicio: addDaysFromIso(fim, -29), fim };
  if (id === "mes") {
    const [y, m] = fim.split("-");
    return { inicio: `${y}-${m}-01`, fim };
  }
  return { inicio: addDaysFromIso(fim, -6), fim };
}
