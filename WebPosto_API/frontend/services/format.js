const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const numberFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export const BRAZIL_TIMEZONE = "America/Recife";

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: BRAZIL_TIMEZONE,
});

const timeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: BRAZIL_TIMEZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const isoDateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: BRAZIL_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function localDateValue(value) {
  if (value instanceof Date) return value;
  const raw = String(value).trim();
  const completo = /^\d{4}-\d{2}-\d{2}$/.test(raw)
    ? `${raw}T00:00:00-03:00`
    : /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(raw)
      ? `${raw}-03:00`
      : raw;
  return new Date(completo);
}

export function recifeDateISO(value = new Date()) {
  const date = localDateValue(value);
  if (Number.isNaN(date.getTime())) throw new Error("Data inválida.");
  const parts = Object.fromEntries(
    isoDateFormatter.formatToParts(date).map(({ type, value }) => [type, value])
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function formatCurrency(value) {
  if (value === null || value === undefined || value === "") return "sem dados";
  const number = Number(String(value).replace(",", "."));
  if (Number.isNaN(number)) return formatMissing(value);
  return currencyFormatter.format(number);
}

export function formatDate(value) {
  if (!value) return "sem dados";
  const date = localDateValue(value);
  if (Number.isNaN(date.getTime())) return formatMissing(value);
  return dateFormatter.format(date);
}

export function formatTime(value) {
  if (!value) return "sem dados";
  const date = localDateValue(value);
  if (Number.isNaN(date.getTime())) return formatMissing(value);
  return timeFormatter.format(date);
}

export function formatDateTime(value) {
  if (!value) return "sem dados";
  const date = localDateValue(value);
  if (Number.isNaN(date.getTime())) return formatMissing(value);
  return `${dateFormatter.format(date)} ${timeFormatter.format(date)}`;
}

export function asText(value) {
  if (value === null || value === undefined || value === "") return "";
  return String(value);
}

export function formatMissing(value) {
  const text = asText(value).trim();
  return text || "—";
}

export function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "sem dados";
  const number = Number(value);
  if (Number.isNaN(number)) return formatMissing(value);
  return numberFormatter.format(number);
}

export function toSearchText(value) {
  return asText(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}
